import os
from typing import Sequence

import httpx
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status, WebSocketException

from internal.auth import JWTDecodeDep, jwt_decode_access
from internal.websocket import WebSocketManager
from models.ChatMessageModel import ChatMessageCreate, ChatMessage
from models.ChatRoomModel import ChatRoomCreate, ChatRoom


# Load Environment Variables.
load_dotenv()

RAG_URL = os.getenv('RAG_URL')

manager = WebSocketManager()


# Websocket endpoint for generative search chat with RAG endpoint.
async def get_websocket_endpoint(
        session: Session, websocket: WebSocket, token: str, chat_room_id: int
):
    # Check if chat_room exists and current user is owner of chat room.
    token_payload = jwt_decode_access(token)
    user_id = token_payload.get('sub')

    db_chat_room = is_user_owner_of_chat_room(session, user_id, chat_room_id)
    if db_chat_room is False:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # Add websocket connection to WebSocketManager.
    await manager.connect(websocket, chat_room_id)

    try:
        while True:
            # Receive message json from frontend service and save user prompt chat message.
            message_json = await websocket.receive_json()

            chat_message_create = ChatMessageCreate(**message_json)
            _ = create_chat_message(session, chat_message_create, chat_room_id)

            # Send user prompt to RAG inference endpoint and save rag inference chat message.
            response_json = await get_rag_inference_endpoint(message_json)

            chat_message_create = ChatMessageCreate(**response_json)
            _ = create_chat_message(session, chat_message_create, chat_room_id)

            # Broadcast message json to frontend (in case of multiple tabs in browser).
            await manager.broadcast(message_json, chat_room_id)
    except WebSocketDisconnect:
        manager.disconnect(chat_room_id)


# Send user prompt to RAG inference endpoint.
async def get_rag_inference_endpoint(message_json: dict):
    url = RAG_URL

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=message_json)
            response_data = response.json()

            return response_data

        except httpx.RequestError as exc:
            # This block catches network-related errors (e.g., DNS failures, refused connections).
            return {"message": f"Request to external API failed: {str(exc)}"}

        except httpx.HTTPStatusError as exc:
            # This block catches cases where the external API responds with a 4xx or 5xx error status code.
            return {"message": f"Error response from external API {str(exc)}"}


# Create chat room with the user's initial prompt as the tittle.
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


# Receive all chat rooms owned by a user.
def get_read_chat_room_by_user_id(
        session: Session, token_payload: JWTDecodeDep
) -> Sequence[ChatRoom]:
    user_id = token_payload.get("sub")

    try:
        statement = select(ChatRoom).where(ChatRoom.user_id == user_id)
        result = session.exec(statement)
        db_chat_rooms = result.all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_rooms


# Receive all messages in a chat room by its id.
def get_read_chat_room_messages(
        session: Session, token_payload: JWTDecodeDep, chat_room_id: int
) -> Sequence[ChatMessage]:
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = is_user_owner_of_chat_room(session, user_id, chat_room_id)

    if db_chat_room is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Return chat messages.
    db_chat_messages = db_chat_room.chat_messages

    return db_chat_messages


# Get chat room by its id.
def get_chat_room_by_id(session: Session, chat_room_id: int) -> ChatRoom:
    try:
        statement = select(ChatRoom).where(ChatRoom.id == chat_room_id)
        result = session.exec(statement)
        db_chat_room = result.first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_room


# Delete chat room by its id.
def get_delete_chat_room_by_id(session: Session, token_payload: JWTDecodeDep, chat_room_id: int) -> dict:
    try:
        # Check if current user owns the chat room.
        user_id = token_payload.get("sub")
        db_chat_room = is_user_owner_of_chat_room(session, user_id, chat_room_id)

        if db_chat_room is False:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

        # Execute delete chat room.
        session.delete(db_chat_room)
        session.commit()

    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return {"ok": True}


# Create chat message inside a chat room.
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


def is_user_owner_of_chat_room(session, user_id: int, chat_room_id: id):
    # Check if current user is owner of chat room.
    db_chat_room = get_chat_room_by_id(session, chat_room_id)
    chat_room_user_id = db_chat_room.user_id

    if user_id != chat_room_user_id:
        return False

    return db_chat_room