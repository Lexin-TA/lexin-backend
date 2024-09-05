from fastapi import APIRouter, UploadFile
from starlette.responses import StreamingResponse

from internal.elastic import ESClientDep
from services import LegalDocumentService

router = APIRouter(prefix="/legal-document")


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
