from fastapi import APIRouter, WebSocket, Query

from internal.auth import JWTDecodeDep
from internal.database import SessionDep
from internal.elastic import ESClientDep
from models.ChatMessageModel import ChatMessageRead, ChatMessageQueryDocument, ChatMessageInference, \
    ChatMessageInferenceQuestion
from models.ChatRoomModel import ChatRoomRead, ChatRoomCreate, ChatRoomUpdate
from services import ChatService

router = APIRouter(prefix="/chat")


@router.websocket("/ws")
async def websocket_endpoint(
        *, session: SessionDep, websocket: WebSocket, es_client: ESClientDep, token: str, chat_room_id: int = None
):
    result = await ChatService.get_websocket_endpoint(session, websocket, es_client, token, chat_room_id)

    return result


@router.post("/chat-room", response_model=ChatRoomRead)
def create_chat_room(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_create: ChatRoomCreate):
    db_chat_room = ChatService.get_create_chat_room(session, token_payload, chat_room_create)

    return db_chat_room


@router.get("/chat-room", response_model=list[ChatRoomRead])
def read_chat_room_by_user_id(*, session: SessionDep, token_payload: JWTDecodeDep):
    db_chat_rooms = ChatService.get_read_chat_room_by_user_id(session, token_payload)

    return db_chat_rooms


@router.get("/chat-room/{chat_room_id}", response_model=ChatRoomRead)
def read_chat_room_by_id(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int):
    db_chat_messages = ChatService.get_read_chat_room_by_id(session, token_payload, chat_room_id)

    return db_chat_messages


@router.patch("/chat-room/{chat_room_id}", response_model=ChatRoomRead)
def update_chat_room_bookmark_by_id(
        *, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int, chat_room_update: ChatRoomUpdate
):
    db_chat_room = ChatService.get_update_chat_room_bookmark(session, token_payload, chat_room_id, chat_room_update)

    return db_chat_room


@router.delete("/chat-room/{chat_room_id}")
def delete_chat_room_by_id(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int) -> dict:
    result = ChatService.get_delete_chat_room_by_id(session, token_payload, chat_room_id)

    return result


@router.get("/chat-room/bookmark", response_model=list[ChatRoomRead])
def read_chat_room_bookmark_by_user_id(*, session: SessionDep, token_payload: JWTDecodeDep):
    db_chat_rooms = ChatService.get_read_chat_room_bookmark_by_user_id(session, token_payload)

    return db_chat_rooms


@router.get("/chat-room/history/{chat_room_id}", response_model=list[ChatMessageRead])
def read_chat_room_history(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int):
    db_chat_messages = ChatService.get_chat_history_helper(session, token_payload, chat_room_id)

    return db_chat_messages


@router.post("/chat-room/documents/{chat_room_id}")
def read_chat_room_documents(
        *, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int, message: ChatMessageQueryDocument,
        es_client: ESClientDep, page: int = Query(1, ge=1), size: int = Query(10, ge=1),
        jenis_bentuk_peraturan: str = None,
        status: str = None,
        sort: str = "_score"
):
    legal_documents = ChatService.get_chat_documents_helper(
        session,
        token_payload, chat_room_id, message,
        es_client, page, size,
        jenis_bentuk_peraturan,
        status,
        sort
    )

    return legal_documents


@router.post("/chat-room/inference/{chat_room_id}")
def read_chat_room_inference(
        *, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int, message: ChatMessageInferenceQuestion
):
    rag_response = ChatService.get_chat_inference_helper(session, token_payload, chat_room_id, message)

    return rag_response
