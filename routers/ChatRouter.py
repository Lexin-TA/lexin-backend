from fastapi import APIRouter, WebSocket

from internal.auth import JWTDecodeDep
from internal.database import SessionDep
from internal.elastic import ESClientDep
from models.ChatMessageModel import ChatMessageRead
from models.ChatRoomModel import ChatRoomRead, ChatRoomCreate
from services import ChatService

router = APIRouter(prefix="/chat")


@router.websocket("/ws")
async def websocket_endpoint(
        *, session: SessionDep, websocket: WebSocket, es_client: ESClientDep, token: str, chat_room_id: int
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


@router.get("/chat-room/{chat_room_id}", response_model=list[ChatMessageRead])
def read_chat_room_messages(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int):
    db_chat_messages = ChatService.get_read_chat_room_messages(session, token_payload, chat_room_id)

    return db_chat_messages


@router.delete("/chat-room/{chat_room_id}")
def delete_chat_room(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int) -> dict:
    result = ChatService.get_delete_chat_room_by_id(session, token_payload, chat_room_id)

    return result
