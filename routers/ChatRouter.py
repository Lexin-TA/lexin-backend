from fastapi import APIRouter, WebSocket

from internal.auth import JWTDecodeDep
from internal.database import SessionDep
from models.ChatMessageModel import ChatMessageRead
from models.ChatRoomModel import ChatRoomRead, ChatRoomCreate
from services import ChatService

router = APIRouter(prefix="/chat")


@router.websocket("/ws/{chat_room_id}")
async def websocket_endpoint(*, session: SessionDep, websocket: WebSocket, chat_room_id: int):
    result = await ChatService.get_websocket_endpoint(session, websocket, chat_room_id)

    return result


@router.post("/chat-room", response_model=ChatRoomRead)
def create_chat_room(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_create: ChatRoomCreate):
    db_chat_room = ChatService.get_create_chat_room(session, token_payload, chat_room_create)

    return db_chat_room


@router.get("/chat-room/{chat_room_id}", response_model=list[ChatMessageRead])
def read_chat_room_messages(*, session: SessionDep, token_payload: JWTDecodeDep, chat_room_id: int):
    db_chat_messages = ChatService.get_read_chat_message_by_chat_room_id(session, token_payload, chat_room_id)

    return db_chat_messages
