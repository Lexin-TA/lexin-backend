import os

import fitz
from dotenv import load_dotenv
from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from internal.elastic import ESClientDep
from internal.google_cloud_storage import upload_gcs_file, download_gcs_file
from models.LegalDocumentModel import LegalDocumentCreate

# Load Environment Variables.
load_dotenv()

GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME = os.getenv('GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME')


def extract_text_pdf(file: UploadFile) -> str:
    """Extracts text from a PDF file using PyMuPDF."""
    pdf_data = file.file.read()
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

    text = ""
    for page in pdf_document:
        text += page.get_text()

    return text


def index_legal_document(es_client: ESClientDep, document_data: dict):
    legal_document_create = LegalDocumentCreate(**document_data)
    _ = LegalDocumentCreate.model_validate(legal_document_create)

    # Check if a document with the same title already exists
    search_result = es_client.search(
        index="documents",
        query={
            "match": {
                "title": legal_document_create.tittle
            }
        }
    )

    # If a document with this title exists, raise an error
    if search_result["hits"]["total"]["value"] > 0:
        raise HTTPException(status_code=400, detail="A document with this title already exists.")

    # Index the document with an auto-generated ID
    es_response = es_client.index(index="legal_document", document=document_data)

    result = {
        "es_result": es_response["result"],
        "es_index": es_response["_index"],
        "es_id": es_response["_id"],
    }

    return result


def get_upload_legal_document(es_client: ESClientDep, file: UploadFile):
    """Upload a PDF file, extract text, and index it."""

    # Check file type.
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # Upload the PDF to Google Cloud Storage
    blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{file.filename}"
    gcs_url = upload_gcs_file(file, blob_name)

    # At this point, the file pointer is at the end of the file
    # This is because the file is read first, then uploaded to google cloud storage.
    # If we try to read again, it will return an empty string or nothing
    # Reset the pointer to the beginning
    file.file.seek(0)

    # Extract text from the PDF
    pdf_text = extract_text_pdf(file)

    # Index the extracted text and GCS URL into Elasticsearch
    document_data = {
        "tittle": file.filename,
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
    elastic_response = es_client.get(index="legal_document", id=document_id)
    document = elastic_response["_source"]

    # Check if the document exists
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get the GCS URL
    gcs_url = document.get("resource_url")
    if not gcs_url:
        raise HTTPException(status_code=404, detail="Resource URL not found")

    # Download the file from GCS
    url_splits = gcs_url.split("/")
    blob_name = "/".join(url_splits[4:])

    downloaded_file = download_gcs_file(blob_name)
    downloaded_file_name = elastic_response["_source"]["tittle"]

    if view_mode:
        # Select header to view the pdf file.
        header = {"Content-Disposition": f"inline; filename={downloaded_file_name}"}
    else:
        # Select header to download the pdf file.
        header = {"Content-Disposition": f"attachment; filename={downloaded_file_name}"}

    return StreamingResponse(
        downloaded_file,
        media_type="application/pdf",
        headers=header
    )


def get_search_legal_document(es_client: ESClientDep, query: str):
    """Search documents in Elasticsearch."""
    es_response = es_client.search(
        index="legal_document",
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
