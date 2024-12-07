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
from internal.message_broker import publish_message_with_response
from internal.websocket import WebSocketManager
from models.ChatMessageModel import ChatMessageCreate, ChatMessage, ChatMessageBase, ChatMessageQueryDocument, \
    ChatMessageInference, ChatMessageInferenceQuestion
from models.ChatRoomModel import ChatRoomCreate, ChatRoom, ChatRoomUpdate
from services.LegalDocumentService import search_legal_document

# Load Environment Variables.
load_dotenv()

RAG_URL = os.getenv('RAG_URL')
ELASTICSEARCH_LEGAL_DOCUMENT_INDEX = os.getenv('ELASTICSEARCH_LEGAL_DOCUMENT_INDEX')

# Initialize websocket manager.
websocket_manager = WebSocketManager()

# Initialize OpenAI client.
openai_client = OpenAI()


# Websocket endpoint for generative search chat with RAG endpoint.
async def get_websocket_endpoint(
        session: Session, websocket: WebSocket, es_client: ESClientDep, token: str, chat_room_id: int
):
    # Check if chat_room exists and current user is owner of chat room.
    token_payload = jwt_decode_access(token)
    user_id = token_payload.get('sub')

    db_chat_room = get_chat_room_by_id(session, chat_room_id)

    is_owner = is_user_owner_of_chat_room(user_id, db_chat_room)
    if is_owner is False:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # Add websocket connection to WebSocketManager.
    await websocket_manager.connect(websocket, chat_room_id)

    try:
        while True:
            # Receive question string from frontend service.
            user_question_dict = await websocket.receive_json()
            user_question = str(user_question_dict["question"])

            # Send user prompt to RAG inference endpoint.
            message = ChatMessageInferenceQuestion(question=user_question)
            rag_answer_dict = get_chat_inference_helper(session, token_payload, chat_room_id, message, es_client)
            rag_answer = rag_answer_dict

            # Save user question and rag answer to database.
            chat_message_create = ChatMessageCreate(question=user_question,
                                                    answer=rag_answer)
            _ = create_chat_message(session, chat_message_create, chat_room_id)

            # Broadcast message json to frontend (in case of multiple tabs in browser).
            response_json = {
                "rag_result": rag_answer
            }
            await websocket_manager.broadcast(response_json, chat_room_id)

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
        chat_room_id: int,
        message: ChatMessageInferenceQuestion,
        es_client: ESClientDep
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
        _ = ChatMessageInferenceQuestion.model_validate(chat_message_inference)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # Do inference.
    # inference = publish_message_with_response(chat_message_inference.dict())

    # Retrieve relevant documents
    documents = search_elasticsearch(es_client, message.question)

    if not documents:
        print("No relevant documents found.")
        return

    # Generate response with OpenAI
    inference = generate_response_with_rag(chat_message_inference.dict(), documents)

    return inference


def search_elasticsearch(es_client, query, size=5):
    """
    Search for relevant documents in Elasticsearch.
    """

    search_result = es_client.search(
        index=ELASTICSEARCH_LEGAL_DOCUMENT_INDEX,
        size=size,
        query={
            "function_score": {
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"title": query}},
                            {"match": {"jenis_bentuk_peraturan": query}},
                            {"match": {"tentang": query}},
                            {"match": {"content_text": query}},
                            {
                                "nested": {
                                    "path": "dasar_hukum",
                                    "query": {
                                        "match": {"dasar_hukum.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "mengubah",
                                    "query": {
                                        "match": {"mengubah.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "diubah_oleh",
                                    "query": {
                                        "match": {"diubah_oleh.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "mencabut",
                                    "query": {
                                        "match": {"mencabut.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "dicabut_oleh",
                                    "query": {
                                        "match": {"dicabut_oleh.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "melaksanakan_amanat_peraturan",
                                    "query": {
                                        "match": {"melaksanakan_amanat_peraturan.title": query}
                                    }
                                }
                            },
                            {
                                "nested": {
                                    "path": "dilaksanakan_oleh_peraturan_pelaksana",
                                    "query": {
                                        "match": {"dilaksanakan_oleh_peraturan_pelaksana.title": query}
                                    }
                                }
                            },
                        ]
                    }
                },
                "functions": [
                    {
                        "linear": {
                            "ditetapkan_tanggal": {
                                "origin": "now",
                                "scale": "365d",
                                "offset": "365d",
                                "decay": 0.5
                            }
                        }
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "UNDANG-UNDANG DASAR"}},
                        "weight": 2.4
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "KETETAPAN MAJELIS PERMUSYAWARATAN RAKYAT"}},
                        "weight": 2.2
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "UNDANG-UNDANG"}},
                        "weight": 2.0
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN PEMERINTAH PENGGANTI UNDANG-UNDANG"}},
                        "weight": 2.0
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN PEMERINTAH"}},
                        "weight": 1.8
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN PRESIDEN"}},
                        "weight": 1.6
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN MENTERI"}},
                        "weight": 1.4
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN DAERAH"}},
                        "weight": 1.2
                    },
                    {
                        "filter": {"term": {"jenis_bentuk_peraturan": "PERATURAN BADAN/LEMBAGA"}},
                        "weight": 1.0
                    },
                ],
                "boost_mode": "avg"
            }
        },

        source={
            "includes": [
                "content_text"
            ]
        },
    )

    # Extract content from hits
    documents = [
        hit["_source"]["content_text"][0] for hit in search_result["hits"]["hits"]
    ]

    return documents


def generate_response_with_rag(query, documents):
    """
    Use OpenAI API to generate a response augmented with retrieved documents.
    """
    doc_str_list = []
    for doc in documents:
        doc_str = ' '.join(doc)
        doc_str_list.append(doc_str)

    # Combine documents into a single context
    prompt = (f"Answer the question with these additional legal documents context if they are relevant:\n\n"
              f"{documents}\n\n"
              f"Question: {query}\n\n"
              f"Answer:")

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that answers question about Indonesian law and regulations. "
                           "Respond using Indonesian language"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
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
