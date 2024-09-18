import io
import json
import os
import zipfile
from typing import BinaryIO, IO

import fitz
from dotenv import load_dotenv
from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from internal.auth import JWTDecodeDep
from internal.elastic import ESClientDep
from internal.google_cloud_storage import upload_gcs_file, download_gcs_file
from models.LegalDocumentBookmarkModel import LegalDocumentBookmark
from models.LegalDocumentModel import LegalDocumentCreate, ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS

# Load Environment Variables.
load_dotenv()

GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME = os.getenv('GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME')
ELASTICSEARCH_LEGAL_DOCUMENT_INDEX = os.getenv('ELASTICSEARCH_LEGAL_DOCUMENT_INDEX')
METADATA_FILENAME = "metadata.json"


def extract_text_pdf(file: IO[bytes]) -> str:
    """Extracts text from a PDF file using PyMuPDF."""
    pdf_data = file.read()
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

    text = ""
    for page in pdf_document:
        text += page.get_text()

    return text


def get_create_legal_document_mappings(es_client: ESClientDep):
    """Create initial index mappings of legal documents."""
    es_response = es_client.indices.create(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        body=ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS
    )

    return es_response


def index_legal_document(es_client: ESClientDep, document_data: dict):
    legal_document_create = LegalDocumentCreate(**document_data)
    _ = LegalDocumentCreate.model_validate(legal_document_create)

    # Check if a document with the same filename already exists
    search_result = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        query={
            "term": {
                "filename.keyword": {
                    "value": legal_document_create.filename
                }
            }
        }
    )

    # If a document with this title exists, raise an error
    if search_result["hits"]["total"]["value"] > 0:
        raise HTTPException(status_code=400, detail="A document with this filename already exists.")

    # Index the document with an auto-generated ID
    es_response = es_client.index(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, document=document_data)

    result = {
        "es_id": es_response["_id"],
        "es_filename": legal_document_create.filename,
    }

    return result


def get_upload_bulk_legal_document(es_client: ESClientDep, file: UploadFile):
    """Bulk upload PDF files to google cloud storage, extract text, and index it to elasticsearch."""

    # Check if file type is zip.
    content_type = file.content_type
    is_zip_content_type = False

    if content_type == "application/zip" or content_type == "application/x-zip-compressed":
        is_zip_content_type = True
    if not is_zip_content_type:
        raise HTTPException(status_code=400, detail="Only zip files are allowed.")

    # Read uploaded zip file.
    with zipfile.ZipFile(file.file, 'r') as zip_file:
        # Check if metadata json file exists within the zip file.
        filename_in_zip_list = zip_file.namelist()
        if METADATA_FILENAME not in filename_in_zip_list:
            raise HTTPException(status_code=400, detail="metadata.json not found.")
        else:
            filename_in_zip_list.remove(METADATA_FILENAME)

        # Extract metadata json file contents as a dictionary.
        with zip_file.open(METADATA_FILENAME) as extracted_file:
            metadata_content = extracted_file.read()
            metadata_list = json.loads(metadata_content)

        # Iterate metadata dictionary.
        failed_upload_result = []
        success_upload_result = []
        filename_in_metadata_list = []

        for metadata in metadata_list:
            filename = metadata["filename"]
            filename_in_metadata_list.append(filename)

            # Read a filename inside the zip file based on the metadata dictionary.
            with zip_file.open(filename) as extracted_file:
                try:
                    # Upload legal document to google cloud storage and index to elasticsearch.
                    upload_result = upload_bulk_legal_document_helper(es_client, extracted_file, metadata)
                    success_upload_result.append(upload_result)

                except HTTPException as e:
                    # Append filenames that failed to upload.
                    failed_upload_result.append({filename: str(e)})

    # Prepare response for filenames with no metadata.
    filename_in_zip_set = set(filename_in_zip_list)
    filename_in_metadata_set = set(filename_in_metadata_list)

    filename_with_no_metadata = filename_in_zip_set.difference(filename_in_metadata_set)
    for filename in filename_with_no_metadata:
        failed_upload_result.append({filename: "No metadata detected."})

    # Prepare bulk upload response.
    result = {
        "failed_upload_result": failed_upload_result,
        "success_upload_result": success_upload_result
    }

    return result


def upload_bulk_legal_document_helper(
        es_client: ESClientDep, extracted_file: IO[bytes], metadata: dict
):
    filename = metadata['filename']

    # Upload the PDF to Google Cloud Storage
    blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{filename}"
    gcs_url = upload_gcs_file(extracted_file, blob_name)

    # Reset the pointer to the beginning
    extracted_file.seek(0)

    # Extract text from the PDF
    pdf_text = extract_text_pdf(extracted_file)

    # Index the extracted text and GCS URL into Elasticsearch
    document_data = {
        "content": pdf_text,
        "resource_url": gcs_url
    }

    # Update document data with the metadata.
    document_data.update(metadata)

    # Send index document request.
    es_response = index_legal_document(es_client, document_data)

    # Prepare return dictionary.
    upload_result = {
        "id": es_response["es_id"],
        "filename": es_response["es_filename"],
        "resource_url": gcs_url
    }

    return upload_result


def get_upload_legal_document(es_client: ESClientDep, file: UploadFile):
    """Upload a PDF file, extract text, and index it."""

    # Check file type.
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # Upload the PDF to Google Cloud Storage
    blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{file.filename}"
    gcs_url = upload_gcs_file(file.file, blob_name)

    # At this point, the file pointer is at the end of the file
    # This is because the file is read first, then uploaded to google cloud storage.
    # If we try to read again, it will return an empty string or nothing
    # Reset the pointer to the beginning
    file.file.seek(0)

    # Extract text from the PDF
    pdf_text = extract_text_pdf(file.file)

    # Index the extracted text and GCS URL into Elasticsearch
    document_data = {
        "title": file.filename,
        "content": pdf_text,
        "resource_url": gcs_url
    }

    es_response = index_legal_document(es_client, document_data)

    # Prepare return dictionary.
    es_response.update({"resource_url": gcs_url})

    return es_response


def get_download_legal_document(es_client: ESClientDep, view_mode: bool, document_id: str):
    """Download the original PDF from Google Cloud Storage."""

    # Retrieve the document from Elasticsearch.
    elastic_response = es_client.get(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, id=document_id)
    document = elastic_response["_source"]

    # Check if the document exists
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get the GCS URL
    gcs_url = document.get("resource_url")
    if not gcs_url:
        raise HTTPException(status_code=404, detail="Resource URL not found")

    # Download the file from GCS
    # url splits: ['https:', '', 'storage.cloud.google.com', 'lexin-ta.appspot.com', 'legal_document', 'some_file.pdf']
    url_splits = gcs_url.split("/")
    blob_name = "/".join(url_splits[4:])
    blob_file_name = url_splits[-1]

    downloaded_file = download_gcs_file(blob_name)

    if view_mode:
        # Select header to view the pdf file.
        header = {"Content-Disposition": f"inline; filename={blob_file_name}"}
    else:
        # Select header to download the pdf file.
        header = {"Content-Disposition": f"attachment; filename={blob_file_name}"}

    return StreamingResponse(
        downloaded_file,
        media_type="application/pdf",
        headers=header
    )


def get_search_legal_document(es_client: ESClientDep, query: str):
    """Search documents in Elasticsearch."""
    es_response = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        query={
            "match": {
                "content": query
            }
        }
    )

    es_hits = {
        "es_hits": es_response["hits"]["hits"]
    }

    return es_hits


def get_create_legal_document_bookmark(session: Session, token_payload: JWTDecodeDep, document_id: str):
    """Bookmark the user's documents"""
    user_id = token_payload.get("sub")
    db_legal_document_bookmark = LegalDocumentBookmark(user_id=user_id,
                                                       document_id=document_id)

    try:
        session.add(db_legal_document_bookmark)
        session.commit()
        session.refresh(db_legal_document_bookmark)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_legal_document_bookmark


def get_read_legal_document_bookmark(session: Session, token_payload: JWTDecodeDep):
    user_id = token_payload.get("sub")

    try:
        statement = select(LegalDocumentBookmark).where(LegalDocumentBookmark.user_id == user_id)
        result = session.exec(statement)
        db_chat_rooms = result.all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_rooms
