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
LEGAL_DOCUMENT_METADATA_JSON_FILENAME = "metadata.json"


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
            "constant_score": {
                "filter": {
                    "term": {
                        "filename": legal_document_create.filename
                    }

                }
            }
        }
    )

    # If a document with this title exists, raise an error
    if search_result["hits"]["total"]["value"] > 0:
        raise HTTPException(status_code=400, detail="An index with this filename already exists.")

    # Index the document with an auto-generated ID
    es_response = es_client.index(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, document=document_data)

    result = {
        "es_id": es_response["_id"],
        "es_filename": legal_document_create.filename,
    }

    return result


def get_upload_legal_document(es_client: ESClientDep, file: UploadFile):
    """
    Parse the zip file containing legal document pdfs and metadata json, so it can be uploaded to the system.

    Example of the file structure inside the zip file would be as follows:
        - metadata.json
        - uu-no-53-tahun-2024.pdf
        - uu-no-36-tahun-2024.pdf
        ...

    Example of the metadata.json structure would contain information of the pdf files as follows:
    [
        {
            "title": "Undang-undang Nomor 53 Tahun 2024 Tentang Kota Bukittinggi di Provinsi Sumatera Barat",
            "jenis_bentuk_peraturan": "UNDANG-UNDANG",
            "pemrakarsa": "PEMERINTAH PUSAT",
            "nomor": 53,
            "tahun": 2024,
            "tentang": "KOTA BUKITTINGGI DI PROVINSI SUMATERA BARAT",
            "tempat_penetapan": "Jakarta",
            "ditetapkan_tanggal": "01 Januari 1970",
            "status": "Berlaku",
            "reference_url": "https://peraturan.go.id/files/uu-no-53-tahun-2024.pdf",
            "filename": "uu-no-53-tahun-2024.pdf"
        },
        {
            "title": "Undang-undang Nomor 36 Tahun 2024 Tentang Kabupaten Lampung Utara di Provinsi Lampung",
            "jenis_bentuk_peraturan": "UNDANG-UNDANG",
            "pemrakarsa": "PEMERINTAH PUSAT",
            "nomor": 36,
            "tahun": 2024,
            "tentang": "KABUPATEN LAMPUNG UTARA DI PROVINSI LAMPUNG",
            "tempat_penetapan": "Jakarta",
            "ditetapkan_tanggal": "01 Januari 1970",
            "status": "Berlaku",
            "reference_url": "https://peraturan.go.id/files/uu-no-36-tahun-2024.pdf",
            "filename": "uu-no-36-tahun-2024.pdf"
        },
        ...
    ]

    """

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
        filenames_in_zip_list = zip_file.namelist()

        if LEGAL_DOCUMENT_METADATA_JSON_FILENAME not in filenames_in_zip_list:
            raise HTTPException(status_code=400, detail="metadata.json not found.")
        else:
            filenames_in_zip_list.remove(LEGAL_DOCUMENT_METADATA_JSON_FILENAME)

        # Extract metadata json file contents as a dictionary.
        with zip_file.open(LEGAL_DOCUMENT_METADATA_JSON_FILENAME) as extracted_file:
            metadata_content = extracted_file.read()
            metadata_list = json.loads(metadata_content)

        parse_result = parse_legal_document_and_metadata_zip(
            es_client, zip_file, filenames_in_zip_list, metadata_list
        )

    return parse_result


def parse_legal_document_and_metadata_zip(
        es_client: ESClientDep, zip_file: zipfile, filenames_in_zip_list: list[str], metadata_list: list[dict]
):
    """Upload filenames that are described in the metadata into the system."""
    failed_upload_list = []
    successful_upload_list = []
    filenames_in_metadata_list = []

    # Iterate metadata dictionary.
    for metadata in metadata_list:
        filename = metadata["filename"]
        filenames_in_metadata_list.append(filename)

        # Read a filename inside the zip file based on the metadata dictionary.
        with zip_file.open(filename) as extracted_file:
            try:
                # Upload legal document to google cloud storage and index to elasticsearch.
                upload_result = upload_legal_document_helper(es_client, extracted_file, metadata)
                successful_upload_list.append(upload_result)

            except HTTPException as e:
                # Append filenames that failed to upload.
                failed_upload_list.append({filename: str(e)})

    # Prepare response for filenames with no metadata.
    filename_in_zip_set = set(filenames_in_zip_list)
    filename_in_metadata_set = set(filenames_in_metadata_list)

    filename_with_no_metadata = filename_in_zip_set.difference(filename_in_metadata_set)
    for filename in filename_with_no_metadata:
        failed_upload_list.append({filename: "No metadata detected."})

    # Prepare upload response.
    parse_result = {
        "failed_upload": failed_upload_list,
        "successful_upload": successful_upload_list,
    }

    return parse_result


def upload_legal_document_helper(
        es_client: ESClientDep, extracted_file: IO[bytes], metadata: dict
):
    """Upload PDF files to google cloud storage, extract text, and index it to elasticsearch."""
    filename = metadata['filename']

    # Upload the PDF to Google Cloud Storage
    blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{filename}"
    gcs_url = upload_gcs_file(extracted_file, blob_name)

    # At this point, the file pointer is at the end of the file
    # This is because the file is read first, then uploaded to google cloud storage.
    # If we try to read again, it will return an empty string or nothing
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
