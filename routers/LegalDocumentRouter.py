from typing import Annotated

from fastapi import APIRouter, UploadFile, Query
from starlette.responses import StreamingResponse

from internal.auth import JWTDecodeDep
from internal.database import SessionDep
from internal.elastic import ESClientDep
from models.LegalDocumentBookmarkModel import LegalDocumentBookmarkRead, LegalDocumentBookmarkCreate
from services import LegalDocumentService

router = APIRouter(prefix="/legal-document")


@router.post("/mapping")
def create_legal_document_mappings(es_client: ESClientDep):
    create_mapping_result = LegalDocumentService.get_create_legal_document_mappings(es_client)

    return create_mapping_result


@router.delete("/mapping")
def delete_legal_document_mappings(es_client: ESClientDep):
    delete_mapping_result = LegalDocumentService.get_delete_legal_document_mappings(es_client)

    return delete_mapping_result


@router.delete("/files")
def delete_all_legal_document_files():
    delete_files_result = LegalDocumentService.get_delete_all_legal_document_files()

    return delete_files_result


@router.post("/upload")
def upload_legal_document(es_client: ESClientDep, file: UploadFile) -> dict:
    upload_result = LegalDocumentService.get_upload_legal_document(es_client, file)

    return upload_result


@router.get("/download/{document_id}")
def download_legal_document(es_client: ESClientDep, document_id: str, resource_index: int = 0) -> StreamingResponse:
    download_result = LegalDocumentService.get_download_legal_document(
        es_client,
        view_mode=False,
        document_id=document_id,
        resource_index=resource_index
    )

    return download_result


@router.get("/view/{document_id}")
def view_legal_document_file(es_client: ESClientDep, document_id: str) -> StreamingResponse:
    view_result = LegalDocumentService.get_download_legal_document(
        es_client,
        view_mode=True,
        document_id=document_id
    )

    return view_result


@router.get("/detail/{document_id}")
def get_legal_document_by_id(es_client: ESClientDep, document_id: str) -> dict:
    search_result = LegalDocumentService.search_legal_document_detail_by_id(es_client, document_id)

    return search_result


@router.get("/detail-content/{document_id}")
def get_legal_document_content_by_id(
        es_client: ESClientDep, document_id: str, resource_index: int = 0,
        page_number: int = Query(1, ge=1), page_size: int = Query(25, ge=1)
) -> list[dict]:
    search_result = LegalDocumentService.search_legal_document_content_by_id(
        es_client, document_id, resource_index,
        page_number, page_size
    )

    return search_result


@router.get("/detail-list")
def get_legal_document_by_id_list(
        es_client: ESClientDep, document_id: Annotated[list[str], Query()]
) -> list[dict]:
    search_result = LegalDocumentService.search_legal_document_detail_by_id_list(es_client, document_id)

    return search_result


@router.get("/search")
def search_legal_document(
        es_client: ESClientDep, query: str, page: int = Query(1, ge=1), size: int = Query(10, ge=1),
        jenis_bentuk_peraturan: Annotated[list[str] | None, Query()] = None,
        status: str = None,
        sort: str = None
) -> dict:
    search_result = LegalDocumentService.search_legal_document(
        es_client, query, page, size,
        jenis_bentuk_peraturan, status, sort
    )

    return search_result


@router.get("/distinct-of-field")
def get_legal_document_distinct_of_field(es_client: ESClientDep, field: str, size: int = 16) -> list[dict]:
    distinct_of_field = LegalDocumentService.get_legal_document_distinct_value_of_field(es_client, field, size)

    return distinct_of_field


@router.post("/bookmark", response_model=LegalDocumentBookmarkRead)
def create_legal_document_bookmark(
    *, session: SessionDep, token_payload: JWTDecodeDep, legal_document_bookmark_create: LegalDocumentBookmarkCreate
):
    bookmark_result = LegalDocumentService.get_create_legal_document_bookmark(
        session, token_payload, legal_document_bookmark_create
    )

    return bookmark_result


@router.get("/bookmark")
def read_legal_document_bookmark_by_user(*, session: SessionDep, token_payload: JWTDecodeDep, es_client: ESClientDep):
    bookmarks = LegalDocumentService.get_read_legal_document_bookmark_by_user(
        session,
        token_payload,
        es_client
    )

    return bookmarks


@router.delete("/bookmark/{document_id}")
def delete_legal_document_bookmark_by_document_id(
        *, session: SessionDep, token_payload: JWTDecodeDep, document_id: str
):
    delete_response = LegalDocumentService.get_delete_legal_document_bookmark_by_document_id(
        session,
        token_payload,
        document_id
    )

    return delete_response
