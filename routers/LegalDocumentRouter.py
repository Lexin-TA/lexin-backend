from fastapi import APIRouter, UploadFile
from starlette.responses import StreamingResponse

from internal.auth import JWTDecodeDep
from internal.database import SessionDep
from internal.elastic import ESClientDep
from models.LegalDocumentBookmarkModel import LegalDocumentBookmarkRead
from services import LegalDocumentService

router = APIRouter(prefix="/legal-document")


@router.post("/create-mapping")
def create_legal_document_mappings(es_client: ESClientDep,):
    mapping_result = LegalDocumentService.get_create_legal_document_mappings(es_client)

    return mapping_result


@router.post("/upload")
def upload_legal_document(es_client: ESClientDep, file: UploadFile) -> dict:
    upload_result = LegalDocumentService.get_upload_legal_document(es_client, file)

    return upload_result


@router.get("/download")
def download_legal_document(es_client: ESClientDep, document_id: str) -> StreamingResponse:
    download_result = LegalDocumentService.get_download_legal_document(es_client,
                                                                       view_mode=False,
                                                                       document_id=document_id)

    return download_result


@router.get("/view")
def view_legal_document(es_client: ESClientDep, document_id: str) -> StreamingResponse:
    view_result = LegalDocumentService.get_download_legal_document(es_client,
                                                                   view_mode=True,
                                                                   document_id=document_id)
    return view_result


@router.get("/search")
def search_legal_document(es_client: ESClientDep, query: str) -> dict:
    search_result = LegalDocumentService.get_search_legal_document(es_client, query)

    return search_result


@router.post("/bookmark", response_model=LegalDocumentBookmarkRead)
def create_legal_document_bookmark(*, session: SessionDep, token_payload: JWTDecodeDep, document_id: str):
    bookmark_result = LegalDocumentService.get_create_legal_document_bookmark(session, token_payload, document_id)

    return bookmark_result


@router.get("/bookmark", response_model=list[LegalDocumentBookmarkRead])
def read_legal_document_bookmark(*, session: SessionDep, token_payload: JWTDecodeDep):
    db_legal_document_bookmarks = LegalDocumentService.get_read_legal_document_bookmark(session, token_payload)

    return db_legal_document_bookmarks
