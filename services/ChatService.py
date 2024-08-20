from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from fastapi import WebSocket, WebSocketDisconnect, HTTPException

from internal.auth import JWTDecodeDep
from internal.websocket import WebSocketManager
from models.ChatMessageModel import ChatMessageCreate, ChatMessage
from models.ChatRoomModel import ChatRoomCreate, ChatRoom

manager = WebSocketManager()

CHAT_ROOM_NOT_FOUND_MSG = 'Chat room not found.'


async def get_websocket_endpoint(
        session: Session, websocket: WebSocket, chat_room_id: int
):
    # Search for specified chat room in database.
    chat_room_db = get_chat_room_by_id(session, chat_room_id)
    if not chat_room_db:
        raise HTTPException(status_code=404, detail=CHAT_ROOM_NOT_FOUND_MSG)

    # Add websocket connection to WebSocketManager.
    await manager.connect(websocket, chat_room_id)

    # Handle sending and receiving of messages.
    try:
        while True:
            # Receive message json from frontend/RAG service.
            message_json = await websocket.receive_json()

            # Save chat message to database.
            chat_message_create = ChatMessageCreate(**message_json)
            _ = create_chat_message(session, chat_message_create, chat_room_id)

            # Send broadcast message json to frontend and RAG service.
            await manager.broadcast(message_json, chat_room_id)
    except WebSocketDisconnect:
        manager.disconnect(chat_room_id)


def get_create_chat_room(
        session: Session, token_payload: JWTDecodeDep, chat_room_create: ChatRoomCreate
) -> ChatRoom:
    db_chat_room = ChatRoom(tittle=chat_room_create.tittle,
                            user_id=token_payload.get("sub"))

    try:
        session.add(db_chat_room)
        session.commit()
        session.refresh(db_chat_room)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_room


def get_read_chat_message_by_chat_room_id(
        session: Session, chat_room_id: int
) -> list[ChatMessage]:
    try:
        statement = select(ChatMessage).where(ChatMessage.chat_room_id == chat_room_id)
        result = session.exec(statement)
        db_chat_message = result.all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_message


def get_chat_room_by_id(session: Session, chat_room_id: int) -> ChatRoom:
    try:
        statement = select(ChatRoom).where(ChatRoom.id == chat_room_id)
        result = session.exec(statement)
        db_chat_room = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_room


def delete_chat_room_by_id(session: Session, chat_room_id: int) -> dict:
    try:
        statement = select(ChatRoom).where(ChatRoom.id == chat_room_id)
        result = session.exec(statement)
        db_chat_room = result.first()

        session.delete(db_chat_room)
        session.commit()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return {"ok": True}


def create_chat_message(session: Session, chat_message_create: ChatMessageCreate, chat_room_id: int) -> ChatMessage:
    db_chat_message = ChatMessage(message=chat_message_create.message,
                                  chat_room_id=chat_room_id)

    try:
        session.add(db_chat_message)
        session.commit()
        session.refresh(db_chat_message)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_message
