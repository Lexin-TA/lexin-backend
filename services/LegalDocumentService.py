import json
import math
import os
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import IO, List, Dict, Any

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
from internal.storage import upload_file, download_file, GOOGLE_BUCKET_NAME, clear_bucket, \
    delete_file
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
    delete_response = clear_bucket(GOOGLE_BUCKET_NAME)

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

    # Check if a document with the same filename already exists
    search_result = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        size=0,
        query={
            "terms": {
                "filenames": legal_document_create.filenames
            }
        }
    )

    # If a document with this title exists, raise an error
    if search_result["hits"]["total"]["value"] > 0:
        raise HTTPException(status_code=400, detail="An index with this filename already exists.")

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
            "pejabat_yang_menetapkan": "JOKO WIDODO",
            "status": "Berlaku",
            "tahun_pengundangan": "2024",
            "nomor_pengundangan": "123",
            "nomor_tambahan": null,
            "tanggal_pengundangan": "02-07-2024",
            "pejabat_pengundangan": "PRATIKNO",
            "mencabut": [
              "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "dasar_hukum": [
              "Undang-Undang Darurat Nomor 8 Tahun 1956 Tentang Pembentukan Daerah Otonom Kota-kota Besar, dalam Lingkungan Daerah Propinsi Sumatera Utara"
            ],
            "mengubah": [],
            "diubah_oleh": [],
            "dicabut_oleh": [],
            "melaksanakan_amanat_peraturan": [],
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

    upload_result = {"execution_time": execution_time, **parse_result}

    return upload_result


def parse_legal_document_and_metadata_zip(
    es_client: ESClientDep,
    zip_file: zipfile.ZipFile,
    filenames_in_zip_list: List[str],
    metadata_list: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """Upload filenames described in the metadata into the system and return results of succeeded and failed uploads."""

    failed_upload_list = []
    succeeded_upload_list = []
    filenames_in_metadata_list = []

    # Process each metadata entry in parallel
    with ThreadPoolExecutor() as executor:
        future_to_metadata = {
            executor.submit(upload_legal_document_helper, es_client, metadata, zip_file): metadata
            for metadata in metadata_list
        }

        for future in as_completed(future_to_metadata):
            metadata_parse_result = future.result()
            filenames_in_metadata_list.extend(metadata_parse_result["filenames"])

            if metadata_parse_result["is_success"]:
                succeeded_upload_list.append(metadata_parse_result)
            else:
                failed_upload_list.append(metadata_parse_result)

    # Identify files without metadata
    filename_in_zip_set = set(filenames_in_zip_list)
    filename_in_metadata_set = set(filenames_in_metadata_list)
    filenames_with_no_metadata = filename_in_zip_set - filename_in_metadata_set

    for filename in filenames_with_no_metadata:
        failed_upload_list.extend({filename: "No metadata detected."})

    return {
        "failed_upload": failed_upload_list,
        "successful_upload": succeeded_upload_list,
    }


def upload_legal_document_helper(
    es_client: ESClientDep,
    metadata: Dict[str, Any],
    zip_file: zipfile.ZipFile
) -> Dict[str, Any]:
    """Extract text from PDF files, upload to Google Cloud Storage, and index data in Elasticsearch."""

    try:
        # Parse files in parallel
        parse_result = parse_files_in_metadata(metadata, zip_file)
    except Exception as e:
        return build_failed_upload_response(metadata, str(e))

    # Upload parsed files in parallel to Google Cloud Storage
    resource_urls, content_list, blob_list = upload_files_to_gcs_in_parallel(parse_result)

    # Prepare and index document data
    document_data = {**metadata, "resource_urls": resource_urls, "content": content_list}
    try:
        es_response = index_legal_document(es_client, document_data)
    except Exception as e:
        cleanup_failed_upload(blob_list)
        return build_failed_upload_response(document_data, str(e))

    return build_succeeded_upload_response(document_data, es_response["es_id"])


def parse_files_in_metadata(metadata: Dict[str, Any], zip_file: zipfile.ZipFile) -> List[Dict[str, Any]]:
    """Parse files based on metadata, extracting text and reading file content in parallel."""
    parse_result = []

    with ThreadPoolExecutor() as executor:
        future_to_file = {
            executor.submit(parse_single_file, filename, zip_file): filename
            for filename in metadata["filenames"]
        }

        for future in as_completed(future_to_file):
            parse_result.append(future.result())

    return parse_result


def parse_single_file(filename: str, zip_file: zipfile.ZipFile) -> Dict[str, Any]:
    """Extract text and content of a single file from the zip."""
    with zip_file.open(filename) as file:
        pdf_text = extract_text_pdf(file)
        file.seek(0)
        return {
            "filename": filename,
            "content": pdf_text,
            "file": BytesIO(file.read())
        }


def upload_files_to_gcs_in_parallel(parse_result: List[Dict[str, Any]]) -> tuple:
    """Upload files to Google Cloud Storage in parallel and return resource URLs, content, and blob names."""
    resource_urls = []
    content_list = []
    blob_list = []

    with ThreadPoolExecutor() as executor:
        future_to_upload = {
            executor.submit(upload_single_file_to_gcs, parse): parse
            for parse in parse_result
        }

        for future in as_completed(future_to_upload):
            gcs_url, content, blob_name = future.result()
            resource_urls.append(gcs_url)
            content_list.append(content)
            blob_list.append(blob_name)

    return resource_urls, content_list, blob_list


def upload_single_file_to_gcs(parse: Dict[str, Any]) -> tuple:
    """Upload a single file to Google Cloud Storage and return its URL, content, and blob name."""
    filename = parse["filename"]
    file_byte = parse["file"]
    content = parse["content"]

    blob_name = f"{GOOGLE_BUCKET_LEGAL_DOCUMENT_FOLDER_NAME}/{filename}"
    gcs_url = upload_file(GOOGLE_BUCKET_NAME, file_byte, blob_name)

    return gcs_url, content, blob_name


def cleanup_failed_upload(blob_list: List[str]):
    """Delete files in Google Cloud Storage if upload fails."""
    for blob_name in blob_list:
        delete_file(GOOGLE_BUCKET_NAME, blob_name)


def build_failed_upload_response(metadata: Dict[str, Any], message: str) -> Dict[str, Any]:
    """Construct an error response dictionary."""
    return {
        "title": metadata.get("title", "Unknown Title"),
        "filenames": metadata.get("filenames", []),
        "is_success": False,
        "message": message
    }


def build_succeeded_upload_response(metadata: Dict[str, Any], es_id: str) -> Dict[str, Any]:
    """Construct a successful response dictionary."""
    return {
        "id": es_id,
        "title": metadata["title"],
        "filenames": metadata["filenames"],
        "resource_urls": metadata["resource_urls"],
        "is_success": True,
        "message": "Metadata upload succeeded."
    }


def get_download_legal_document(
        es_client: ESClientDep, view_mode: bool, document_id: str, resource_index: int = 0
) -> StreamingResponse:
    """Download the original PDF from Google Cloud Storage, defaults to the first file in resource_urls."""

    # Retrieve the document from Elasticsearch.
    elastic_response = es_client.get(index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX, id=document_id)
    document = elastic_response["_source"]

    # Check if the document exists
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get the GCS URL
    gcs_url = document.get("resource_urls")[resource_index]
    if not gcs_url:
        raise HTTPException(status_code=404, detail="Resource URL not found")

    # Download the file from GCS
    # url splits: ['https:', '', 'storage.cloud.google.com', 'lexin-ta.appspot.com', 'legal_document', 'some_file.pdf']
    url_splits = gcs_url.split("/")
    blob_name = "/".join(url_splits[4:])
    blob_file_name = url_splits[-1]

    downloaded_file = download_file(GOOGLE_BUCKET_NAME, blob_name)

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
        "_id": "tgGXuZIBIi1nR4ibTNYb",
        "_score": 1,
        "_source": {
            "title": "Undang-undang Nomor 4 Tahun 2020 Tentang Pengesahan Persetujuan Antara Pemerintah Republik Indonesia dan Kabinet Menteri Ukraina Tentang Kerja Sama dalam Bidang Pertahanan (agreement Between The Government of The Republic of Indonesia and The Cabinet of Ministers of Ukraine On Cooperation In The Field of Defence)",
            "jenis_bentuk_peraturan": "UNDANG-UNDANG",
            "pemrakarsa": "PEMERINTAH PUSAT",
            "nomor": "4",
            "tahun": "2020",
            "tentang": "PENGESAHAN PERSETUJUAN ANTARA PEMERINTAH REPUBLIK INDONESIA DAN KABINET MENTERI UKRAINA TENTANG KERJA SAMA DALAM BIDANG PERTAHANAN (AGREEMENT BETWEEN THE GOVERNMENT OF THE REPUBLIC OF INDONESIA AND THE CABINET OF MINISTERS OF UKRAINE ON COOPERATION IN THE FIELD OF DEFENCE)",
            "tempat_penetapan": "Jakarta",
            "ditetapkan_tanggal": "05-08-2020",
            "pejabat_yang_menetapkan": "JOKO WIDODO",
            "status": "Berlaku",
            "tahun_pengundangan": "2020",
            "nomor_pengundangan": "187",
            "nomor_tambahan": "6543",
            "tanggal_pengundangan": "06-08-2020",
            "pejabat_pengundangan": null,
            "dasar_hukum": [
                "Tentang Undang-undang Dasar Negara Republik Indonesia Tahun 1945",
                "Undang-Undang Nomor 24 Tahun 2000 Tentang Perjanjian Internasional"
            ],
            "mengubah": [],
            "diubah_oleh": [],
            "mencabut": [],
            "dicabut_oleh": [],
            "melaksanakan_amanat_peraturan": [],
            "dilaksanakan_oleh_peraturan_pelaksana": [],
            "filenames": [
                "uu4-2020bt.pdf",
                "uu4-2020pjl.pdf"
            ],
            "reference_urls": [
                "https://peraturan.go.id/files/uu4-2020bt.pdf",
                "https://peraturan.go.id/files/uu4-2020pjl.pdf"
            ],
            "resource_urls": [
                "https://storage.cloud.google.com/lexin-ta.appspot.com/legal_document/uu4-2020bt.pdf",
                "https://storage.cloud.google.com/lexin-ta.appspot.com/legal_document/uu4-2020pjl.pdf"
            ],
            "content": [
                "content of uu4-2020bt.pdf",
                "content of uu4-2020pjl.pdf"
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


def search_multiple_legal_document(
        es_client: ESClientDep, query: str, page: int = 1, size: int = 10,
        jenis_bentuk_peraturan: str = None,
        status: str = None,
        sort: str = "_score"
) -> dict:
    """Search documents using all of its field in Elasticsearch.

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
        # Query string is used to search the document using all of its field.
        "query": {
            "query_string": {
              "query": query,
              "fields": ["*"]
            }
        },
        # Exclude fields on the return search query value.
        "source": {
            "includes": [
                "title", "jenis_bentuk_peraturan",
                "pemrakarsa", "nomor", "tahun", "tentang",
                "tempat_penetapan", "ditetapkan_tanggal",
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


def get_legal_document_distinct_value_of_field(es_client: ESClientDep, field: str, size: int = 16):
    """Return a size amount of unique value of a field in legal document (defaults to size=16)."""
    try:
        es_response = es_client.search(
            index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
            size=0,
            aggs={
                "uniques": {
                    "terms": {
                        "field": field,
                        "size": size
                    }
                }
            }
        )
    except ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.body)

    # Extracting document hits and aggregations.
    es_buckets = es_response["aggregations"]["uniques"]["buckets"]

    return es_buckets


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
