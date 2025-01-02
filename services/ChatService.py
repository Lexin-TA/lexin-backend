import os
from typing import Sequence

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status, WebSocketException

from internal.auth import JWTDecodeDep, jwt_decode_access
from internal.elastic import ESClientDep
from internal.websocket import WebSocketManager
from models.ChatMessageModel import ChatMessageCreate, ChatMessage, ChatMessageBase, ChatMessageQueryDocument, \
    ChatMessageInference, ChatMessageInferenceQuestion, ChatMessageRead
from models.ChatRoomModel import ChatRoomCreate, ChatRoom, ChatRoomUpdate
from services.LegalDocumentService import search_legal_document, retrieve_document_text_content

# Load Environment Variables.
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize websocket manager.
websocket_manager = WebSocketManager()

# Initialize OpenAI client.
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# Websocket endpoint for generative search chat with RAG endpoint.
async def get_websocket_endpoint(
        session: Session, websocket: WebSocket, es_client: ESClientDep, token: str, chat_room_id: int = None
):
    # Get user id from jwt token.
    token_payload = jwt_decode_access(token)
    user_id = token_payload.get('sub')

    if chat_room_id:
        # If chat_room_id is specified, check ownership with the user id.
        db_chat_room = get_chat_room_by_id(session, chat_room_id)

        is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
        if is_owner is False:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    else:
        # If chat_room_id not available, create one with preset title.
        user_chat_rooms = get_read_chat_room_by_user_id(session, token_payload)

        chat_room_title = f"Chat room {len(user_chat_rooms)}"
        chat_room_create = ChatRoomCreate(title=chat_room_title)

        db_chat_room = get_create_chat_room(session, token_payload, chat_room_create)
        chat_room_id = db_chat_room.id

    # Add websocket connection to WebSocketManager.
    await websocket_manager.connect(websocket, chat_room_id)

    try:
        while True:
            # Receive question string from frontend service.
            user_question_dict = await websocket.receive_json()
            user_question = str(user_question_dict["question"])

            # Send user prompt to RAG inference endpoint.
            message = ChatMessageInferenceQuestion(question=user_question)
            rag_answer_dict = get_chat_inference_helper(session, token_payload, es_client, chat_room_id, message)
            rag_answer = str(rag_answer_dict["answer"])

            # Save user question and rag answer to database.
            chat_message_create = ChatMessageCreate(question=user_question,
                                                    answer=rag_answer)
            _ = create_chat_message(session, chat_message_create, chat_room_id)

            # Broadcast message json to frontend (in case of multiple tabs in browser).
            await websocket_manager.broadcast(rag_answer_dict, chat_room_id)

    except WebSocketDisconnect:
        websocket_manager.disconnect(chat_room_id)


def get_chat_history_helper(
        session: Session,
        token_payload: JWTDecodeDep,
        chat_room_id: int,
):
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Return chat messages.
    db_chat_messages = db_chat_room.chat_messages

    return db_chat_messages


def get_chat_documents_helper(
        session: Session,
        token_payload: JWTDecodeDep,
        chat_room_id: int,
        message: ChatMessageQueryDocument,
        es_client: ESClientDep,
        page: int | None,
        size: int | None,
        jenis_bentuk_peraturan: str | None,
        document_status: str | None,
        sort: str | None,
):
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # do search.
    legal_documents = search_legal_document(
        es_client=es_client, query=message.question, page=page, size=size,
        jenis_bentuk_peraturan=jenis_bentuk_peraturan,
        status=document_status,
        sort=sort
    )

    return legal_documents


def get_chat_inference_helper(
        session: Session,
        token_payload: JWTDecodeDep,
        es_client: ESClientDep,
        chat_room_id: int,
        message: ChatMessageInferenceQuestion,
):
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Add chat history
    db_chat_messages = db_chat_room.chat_messages

    chat_message_inference = ChatMessageInference(
        question=message.question,
        chat_history=db_chat_messages
    )

    # Validate the model.
    try:
        _ = ChatMessageInference.model_validate(chat_message_inference)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # Do retrival augmented generation.
    inference = retrieval_augmented_generation(es_client, chat_message_inference)

    # Prepare response.
    response = {"answer": inference}

    return response


def retrieval_augmented_generation(es_client: ESClientDep, chat_message_inference: ChatMessageInference):
    """ Perform RAG with legal documents from elasticsearch and inference from OpenAI. """
    query = chat_message_inference.question
    chat_history = chat_message_inference.chat_history

    # Retrieve text contents of relevant documents.
    documents = retrieve_document_text_content(es_client, query, size=3)

    # Augment the documents with the question query to produce a prompt
    prompt = augment_documents(query, documents)

    # Generate response with OpenAI.
    inference = generate_inference(prompt, chat_history)

    return inference


def augment_documents(query: str, documents: list[list[str]]) -> str:
    """ Augmented question query with retrieved documents to produce a suitable prompt. """
    doc_str_list = []
    for doc in documents:
        doc_str = ' '.join(doc)
        doc_str_list.append(doc_str)

    if doc_str_list:
        prompt = (f"Answer the question with these additional legal documents context if they are relevant:\n\n"
                  f"{doc_str_list}\n\n"
                  f"Question: {query}\n\n"
                  f"Answer:")
    else:
        prompt = (f"Question: {query}\n\n"
                  f"Answer:")

    return prompt


def generate_inference(prompt: str, chat_history: list[ChatMessageRead]):
    """ Use OpenAI API to generate a response from a prompt that's been augmented with retrieved documents. """

    # Prepare chat history messages following the format of OpenAPIs assistant messages.
    messages_history = []

    if chat_history:
        for history in chat_history:
            question = {
                "role": "user",
                "content": history.question
            }

            answer = {
                "role": "assistant",
                "content": history.answer
            }

            messages_history.append(question)
            messages_history.append(answer)

    # Craft prompt messages for OpenAPIs model.
    messages_prompt = [
        {
            "role": "system",
            "content": "You are a helpful assistant that answers question about laws in Indonesia. "
                       "Respond using Indonesian language"
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    # Do inference with chat history and crafted prompt
    messages = messages_history + messages_prompt

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    return completion.choices[0].message.content


# Create chat room with the user's initial prompt as the title.
def get_create_chat_room(
        session: Session, token_payload: JWTDecodeDep, chat_room_create: ChatRoomCreate
) -> ChatRoom:
    db_chat_room = ChatRoom(title=chat_room_create.title,
                            user_id=token_payload.get("sub"))

    try:
        session.add(db_chat_room)
        session.commit()
        session.refresh(db_chat_room)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_room


# Update the chat room's bookmark status.
def get_update_chat_room_bookmark(
        session: Session, token_payload: JWTDecodeDep, chat_room_id: int, chat_room_update: ChatRoomUpdate
) -> ChatRoom:
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Update chat room with new data.
    chat_room_data = chat_room_update.model_dump(exclude_unset=True)
    db_chat_room.sqlmodel_update(chat_room_data)

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


# Receive all chat rooms owned by a user that are bookmarked.
def get_read_chat_room_bookmark_by_user_id(
        session: Session, token_payload: JWTDecodeDep
) -> Sequence[ChatRoom]:
    user_id = token_payload.get("sub")

    try:
        statement = (select(ChatRoom)
                     .where(ChatRoom.user_id == user_id)
                     .where(ChatRoom.bookmark == True))
        result = session.exec(statement)
        db_chat_rooms = result.all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_rooms


# Receive chat room details by its id.
def get_read_chat_room_by_id(
        session: Session, token_payload: JWTDecodeDep, chat_room_id: int
) -> ChatRoom:
    # Check if current user is owner of chat room.
    user_id = token_payload.get('sub')
    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    return db_chat_room


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
        db_chat_room = get_chat_room_by_id(session, chat_room_id)

        is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
        if is_owner is False:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

        # Execute delete chat room.
        session.delete(db_chat_room)
        session.commit()

    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return {"ok": True}


# Create chat message inside a chat room.
def create_chat_message(session: Session, chat_message_create: ChatMessageCreate, chat_room_id: int) -> ChatMessage:
    db_chat_message = ChatMessage(question=chat_message_create.question,
                                  answer=chat_message_create.answer,
                                  chat_room_id=chat_room_id)

    try:
        session.add(db_chat_message)
        session.commit()
        session.refresh(db_chat_message)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=422, detail=str(e.orig))

    return db_chat_message


# Check if current user is owner of chat room.
def is_user_owner_of_chat_room(user_id: int, db_chat_room: ChatRoom):
    # Check if there is a chat room with the id.
    if not db_chat_room:
        return False

    # Check if the user owns the chat room .
    chat_room_user_id = db_chat_room.user_id

    if user_id != chat_room_user_id:
        return False

    return True
