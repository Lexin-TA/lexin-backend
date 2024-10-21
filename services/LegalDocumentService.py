import json
import math
import os
import zipfile
import time
from typing import IO

import fitz
from dotenv import load_dotenv
from elasticsearch import ApiError
from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from internal.auth import JWTDecodeDep
from internal.elastic import ESClientDep
from internal.google_cloud_storage import upload_gcs_file, download_gcs_file, GOOGLE_BUCKET_NAME, delete_all_gcs_file
from models.LegalDocumentBookmarkModel import LegalDocumentBookmark, LegalDocumentBookmarkCreate
from models.LegalDocumentModel import LegalDocumentCreate, ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS

# Load Environment Variables.
load_dotenv()

GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME = os.getenv('GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME')
ELASTICSEARCH_LEGAL_DOCUMENT_INDEX = os.getenv('ELASTICSEARCH_LEGAL_DOCUMENT_INDEX')
LEGAL_DOCUMENT_METADATA_JSON_FILENAME = "metadata.json"


def get_create_legal_document_mappings(es_client: ESClientDep):
    """Create initial index mappings of legal documents."""
    es_response = es_client.indices.create(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        body=ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS
    )

    return es_response


def get_delete_legal_document_mappings(es_client: ESClientDep):
    """Create initial index mappings of legal documents."""
    es_response = es_client.indices.delete(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        ignore=[400, 404]
    )

    return es_response


def get_delete_all_legal_document_files():
    delete_response = delete_all_gcs_file(GOOGLE_BUCKET_NAME)

    return delete_response


def extract_text_pdf(file: IO[bytes]) -> str:
    """Extracts text from a PDF file using PyMuPDF."""
    try:
        pdf_data = file.read()
        pdf_document = fitz.open(stream=pdf_data, filetype="pdf")

        text = ""
        for page in pdf_document:
            text += page.get_text()
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return text


def index_legal_document(es_client: ESClientDep, document_data: dict):
    # Validate legal document model.
    try:
        legal_document_create = LegalDocumentCreate(**document_data)
        _ = LegalDocumentCreate.model_validate(legal_document_create)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # # Check if a document with the same filename already exists
    # search_result = es_client.search(
    #     index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
    #     query={
    #         "constant_score": {
    #             "filter": {
    #                 "term": {
    #                     "filenames": legal_document_create.filenames
    #                 }
    #
    #             }
    #         }
    #     }
    # )
    #
    # # If a document with this title exists, raise an error
    # if search_result["hits"]["total"]["value"] > 0:
    #     raise HTTPException(status_code=400, detail="An index with this filename already exists.")

    # Index the document with an auto-generated ID
    try:
        es_response = es_client.index(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, document=document_data)
    except ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.body)

    result = {
        "es_id": es_response["_id"],
        "es_filenames": legal_document_create.filenames,
    }

    return result


def get_upload_legal_document(es_client: ESClientDep, file: UploadFile) -> dict:
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
            "title": "Undang-undang Nomor 25 Tahun 2024 Tentang Kota Pematangsiantar di Provinsi Sumatera Utara",
            "jenis_bentuk_peraturan": "UNDANG-UNDANG",
            "pemrakarsa": "PEMERINTAH PUSAT",
            "nomor": "25",
            "tahun": "2024",
            "tentang": "KOTA PEMATANGSIANTAR DI PROVINSI SUMATERA UTARA",
            "tempat_penetapan": "Jakarta",
            "ditetapkan_tanggal": "02-07-2024",
            "status": "Berlaku",
            "mencabut": [
                "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "dasar_hukum": [
                "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "mengubah": [],
            "diubah_oleh": [],
            "melaksanakan_amanat_peraturan": [],
            "dicabut_oleh": [],
            "dilaksanakan_oleh_peraturan_pelaksana": [],
            "filenames": [
                "uu-no-25-tahun-2024.pdf"
            ],
            "reference_urls": [
                "https://peraturan.go.id/files/uu-no-25-tahun-2024.pdf"
            ]
        },
        ...
    ]

    Example of the return value of this function would be as follows:
    {
        "failed_upload": [
            {
              "uu4-1983.pdf": "400: A file with this name already exists in storage."
            },
            {
              "uu1-1956.pdf": "400: A file with this name already exists in storage."
            },
            ...
        ],

        "successful_upload": [
            {
              "id": "SvjnqZIBmvGrAUeOG1CY",
              "filenames": [
                "uu-no-53-tahun-2024.pdf"
              ],
              "resource_urls": [
                "https://storage.cloud.google.com/lexin-ta.appspot.com/legal_document/uu-no-53-tahun-2024.pdf"
              ]
            },
            ...
        ],

        "execution_time": 538.141523361206
    }
    """
    start_time = time.time()

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

    # Calculate execution time of file upload.
    end_time = time.time()
    execution_time = end_time - start_time

    parse_result["execution_time"] = execution_time

    return parse_result


def parse_legal_document_and_metadata_zip(
        es_client: ESClientDep, zip_file: zipfile, filenames_in_zip_list: list[str], metadata_list: list[dict]
) -> dict:
    """Upload filenames that are described in the metadata into the system."""
    failed_upload_list = []
    succeeded_upload_list = []
    filenames_in_metadata_list = []

    # Iterate metadata dictionary.
    for metadata in metadata_list:
        metadata_parse_result = upload_legal_document_helper(es_client, metadata, zip_file)

        filenames_in_metadata_list.extend(metadata_parse_result["filename_list"])
        failed_upload_list.extend(metadata_parse_result["failed_uploads"])

        succeeded_upload_list.append(metadata_parse_result["succeeded_uploads"])

    # Prepare response for filenames with no metadata.
    filename_in_zip_set = set(filenames_in_zip_list)
    filename_in_metadata_set = set(filenames_in_metadata_list)

    filename_with_no_metadata = filename_in_zip_set.difference(filename_in_metadata_set)
    for filename in filename_with_no_metadata:
        failed_upload_list.append({filename: "No metadata detected."})

    # Prepare upload response.
    parse_result = {
        "failed_upload": failed_upload_list,
        "successful_upload": succeeded_upload_list,
    }

    return parse_result


def upload_legal_document_helper(es_client: ESClientDep, metadata: dict, zip_file: zipfile) -> dict:
    """Upload PDF files to google cloud storage, extract text, and index it to elasticsearch."""

    resource_urls = []
    content_list = []

    failed_uploads = []

    filename_list = [filename for filename in metadata["filenames"] if filename]

    # Read a filename inside the zip file based on the metadata dictionary.
    for filename in filename_list:
        with zip_file.open(filename) as extracted_file:
            try:
                # Upload the PDF to Google Cloud Storage
                blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{filename}"
                gcs_url = upload_gcs_file(GOOGLE_BUCKET_NAME, extracted_file, blob_name)

                # Reset the pointer to the beginning
                extracted_file.seek(0)

                # Extract text from the PDF
                pdf_text = extract_text_pdf(extracted_file)

                resource_urls.append(gcs_url)
                content_list.append(pdf_text)

            except HTTPException as e:
                # Append filenames that failed to upload.
                failed_uploads.append({filename: str(e)})

    # Create document data from metadata and upload results.
    document_data = metadata
    document_data["resource_urls"] = resource_urls
    document_data["content"] = content_list

    # Send index document request.
    es_response = index_legal_document(es_client, document_data)

    # try:
    #     es_response = index_legal_document(es_client, document_data)
    # except HTTPException as e:
    #     failed_uploads.append({filename: str(e)})

    metadata_result = {
        "id": es_response["es_id"],
        "filenames": document_data["filenames"],
        "resource_urls": document_data["resource_urls"]
    }

    # Prepare return response.
    result = {
        "filename_list": filename_list,
        "failed_uploads": failed_uploads,
        "succeeded_uploads": metadata_result,
    }

    return result


def get_download_legal_document(es_client: ESClientDep, view_mode: bool, document_id: str) -> StreamingResponse:
    """Download the original PDF from Google Cloud Storage."""

    # Retrieve the document from Elasticsearch.
    elastic_response = es_client.get(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, id=document_id)
    document = elastic_response["_source"]

    # Check if the document exists
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get the GCS URL
    gcs_url = document.get("resource_urls")[0]
    if not gcs_url:
        raise HTTPException(status_code=404, detail="Resource URL not found")

    # Download the file from GCS
    # url splits: ['https:', '', 'storage.cloud.google.com', 'lexin-ta.appspot.com', 'legal_document', 'some_file.pdf']
    url_splits = gcs_url.split("/")
    blob_name = "/".join(url_splits[4:])
    blob_file_name = url_splits[-1]

    downloaded_file = download_gcs_file(GOOGLE_BUCKET_NAME, blob_name)

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


def search_legal_document_detail_by_id(es_client: ESClientDep, document_id: str) -> dict:
    """Retrieve a single legal document with all of its metadata by id.

    The return value of this function is a dictionary as follows:
    {
        "_index": "legal_document",
        "_id": "cgHSHZIBIi1nR4ibuLUH",
        "_score": 1,
        "_source": {
            "title": "Undang-undang Nomor 25 Tahun 2024 Tentang Kota Pematangsiantar di Provinsi Sumatera Utara",
            "jenis_bentuk_peraturan": "UNDANG-UNDANG",
            "pemrakarsa": "PEMERINTAH PUSAT",
            "nomor": "25",
            "tahun": "2024",
            "tentang": "KOTA PEMATANGSIANTAR DI PROVINSI SUMATERA UTARA",
            "tempat_penetapan": "Jakarta",
            "ditetapkan_tanggal": "02-07-2024",
            "status": "Berlaku",
            "dasar_hukum": [
                "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "mengubah": [],
            "diubah_oleh": [],
            "mencabut": [
                "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "dicabut_oleh": [],
            "melaksanakan_amanat_peraturan": [],
            "dilaksanakan_oleh_peraturan_pelaksana": [],
            "filenames": [
                "uu-no-25-tahun-2024.pdf"
            ],
            "reference_urls": [
                "https://peraturan.go.id/files/uu-no-25-tahun-2024.pdf"
            ],
            "content": [
                "full text content of this file"
            ]
        }
    }
    """

    # Retrieve the documents from Elasticsearch.
    search_result = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        query={
            "ids": {
                "values": document_id
            }
        }
    )
    document_hits = search_result["hits"]["hits"][0]
    print("document hit")
    print(document_hits)

    return document_hits


def search_multiple_legal_document_by_id_list(es_client: ESClientDep, document_id: list[str]) -> list[dict]:
    """Retrieve multiple summarized legal document metadata by list of ids.

    The return value of this function is a list of dictionaries as follows:
    [
        {
            "_index": "legal_document",
            "_id": "cgHSHZIBIi1nR4ibuLUH",
            "_score": 1,
            "_source": {
                "title": "Undang-undang Nomor 24 Tahun 2019 Tentang Ekonomi Kreatif",
                "jenis_bentuk_peraturan": "UNDANG-UNDANG",
                "pemrakarsa": "PEMERINTAH PUSAT",
                "nomor": "24",
                "tahun": "2019",
                "tentang": "EKONOMI KREATIF",
                "tempat_penetapan": "Jakarta",
                "ditetapkan_tanggal": "24 Oktober 2019",
                "status": "Berlaku"
            }
        },
        ...
    ]
    """
    # Retrieve the documents from Elasticsearch.
    search_result = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        query={
            "ids": {
                "values": document_id
            }
        },
        source={
            "excludes": [
                "filenames",
                "content",
                "reference_urls",
                "resource_urls"
            ]
        }

    )
    document_hits = search_result["hits"]["hits"]

    return document_hits


def search_multiple_legal_document_by_content(
        es_client: ESClientDep, query: str, page: int = 1, size: int = 10,
        jenis_bentuk_peraturan: str = None,
        status: str = None,
        sort: str = "_score"
) -> dict:
    """Search documents by its content field in Elasticsearch.

    query                   : query string used to search document by its content
    page                    : determines which page to get (defaults to and starts with 1)
    size                    : the amount of returned document in a single query (defaults to 10)
    jenis_bentuk_peraturan  : string value used to filter jenis_bentuk_peraturan (such as "UNDANG-UNDANG")
    status                  : string value used to filter status (such as "Berlaku")
    sort                    : string value used to sort by field name descending (such as "ditetapkan_tanggal"),
                              defaults to sort by score
    """

    # Calculate the starting document based on the current page and page size
    from_ = (page - 1) * size

    # Write search parameter dictionary.
    search_parameters = {
        "index": ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        "from_": from_,
        "size": size,
        # Query string is used to search the document's content field
        "query": {
            "match": {
                "content": query
            }
        },
        # Exclude fields on the return search query value.
        "source": {
            "includes": [
                "title",
                "jenis_bentuk_peraturan",
                "pemrakarsa",
                "nomor",
                "tahun",
                "tentang",
                "tempat_penetapan",
                "nomditetapkan_tanggalor",
                "status"
            ]
        },
        # Aggregates all unique values of a field, also return it's count based on the search query.
        "aggs": {
            "jenis_bentuk_peraturan_uniques": {
                "terms": {
                    "field": "jenis_bentuk_peraturan"
                }
            },
            "status_uniques": {
                "terms": {
                    "field": "status"
                }
            }
        },
    }

    # Create filters if specified.
    post_filter = {}
    if jenis_bentuk_peraturan:
        post_filter["term"] = {"jenis_bentuk_peraturan": jenis_bentuk_peraturan}
    if status:
        post_filter["term"] = {"status": status}

    if post_filter:
        search_parameters["post_filter"] = post_filter

    # Create sorting by a field if specified.
    if sort:
        search_parameters["sort"] = [{sort: "desc"}]

    # Perform document search.
    try:
        es_response = es_client.search(**search_parameters)
    except ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # Extracting document hits and aggregations.
    es_hits = es_response["hits"]["hits"]
    es_aggregations = es_response["aggregations"]

    # Calculate total pages.
    es_total_hits = es_response["hits"]["total"]["value"]
    total_pages = math.ceil(es_total_hits / size)

    # Prepare return dictionary.
    pagination_res = {
        "page": page,
        "size": size,
        "total_hits": es_total_hits,
        "total_pages": total_pages,
        "hits": es_hits,
        "aggregations": es_aggregations
    }

    return pagination_res


def get_create_legal_document_bookmark(
        session: Session, token_payload: JWTDecodeDep, legal_document_bookmark_create: LegalDocumentBookmarkCreate
) -> LegalDocumentBookmark:
    """Bookmark the user's legal documents"""
    user_id = token_payload.get("sub")

    db_legal_document_bookmark = LegalDocumentBookmark(
        user_id=user_id,
        document_id=legal_document_bookmark_create.document_id
    )

    try:
        session.add(db_legal_document_bookmark)
        session.commit()
        session.refresh(db_legal_document_bookmark)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_legal_document_bookmark


def get_read_legal_document_bookmark_by_user(session: Session, token_payload: JWTDecodeDep, es_client: ESClientDep):
    """View the user's legal document bookmarks."""
    user_id = token_payload.get("sub")

    # Retrieve document ids from user's bookmarks.
    try:
        statement = select(LegalDocumentBookmark).where(LegalDocumentBookmark.user_id == user_id)
        result = session.exec(statement)
        db_legal_document_bookmark = result.all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    # Query elasticsearch using document id list.
    document_id_list = [doc.document_id for doc in db_legal_document_bookmark]
    document_hits = search_multiple_legal_document_by_id_list(es_client, document_id_list)

    return document_hits


def get_delete_legal_document_bookmark_by_document_id(
        session: Session, token_payload: JWTDecodeDep, document_id: str
) -> dict:
    """Delete the user's legal document bookmark by its document id."""
    user_id = token_payload.get("sub")

    # Retrieve document ids from user's bookmarks.
    try:
        statement = (select(LegalDocumentBookmark)
                     .where(LegalDocumentBookmark.user_id == user_id)
                     .where(LegalDocumentBookmark.document_id == document_id))
        result = session.exec(statement)
        db_legal_document_bookmark = result.first()

        session.delete(db_legal_document_bookmark)
        session.commit()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"ok": True}
