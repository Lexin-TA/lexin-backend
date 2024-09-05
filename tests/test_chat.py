import pytest
import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from internal.auth import verify_password, create_access_token, JWT_REFRESH_SECRET_KEY, JWT_ALGORITHM
from main import app
from internal.database import get_session
from models.ChatMessageModel import ChatMessage
from models.ChatRoomModel import ChatRoom
from models.UserModel import User
from services.ChatService import get_chat_room_by_id

URL_USER = '/api/v1/user'
URL_CHAT = '/api/v1/chat'


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        url="sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture(name="user")
def user_fixture(client: TestClient):
    # Create request for user registration.
    req_url = f"{URL_USER}/register"
    req_json = {"email": "user@example.com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    user_data = response.json()

    return user_data


@pytest.fixture(name="login")
def login_fixture(client: TestClient, user):
    # Create request to login.
    req_url = f"{URL_USER}/token"
    req_data = {"username": "user@example.com",
                "password": "string"}
    response = client.post(url=req_url, data=req_data)

    token_data = response.json()

    return token_data


@pytest.fixture(name="chat_room")
def chat_room_fixture(client: TestClient, login):
    # Get user data from user creation request.
    access_token = login["access_token"]

    # Create request for chat room creation.
    req_url = f"{URL_CHAT}/chat-room"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    req_json = {"title": "some initial user prompt."}
    response = client.post(url=req_url, headers=req_headers, json=req_json)

    chat_room_data = response.json()

    return chat_room_data


def test_create_chat_room(session: Session, client: TestClient, user: user_fixture, login: login_fixture):
    # Get user data from user creation request.
    user_id = user["id"]

    # Get token data from login request.
    access_token = login["access_token"]

    # Create request for chat room creation.
    req_url = f"{URL_CHAT}/chat-room"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    req_json = {"title": "some initial user prompt."}
    response = client.post(url=req_url, headers=req_headers, json=req_json)

    data = response.json()

    # Check database for newly created chat room.
    db_chat_room = get_chat_room_by_id(session, data["id"])

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 2
    assert data["id"] is not None
    assert data["title"] == req_json["title"]

    assert db_chat_room.id is not None
    assert db_chat_room.title == data["title"]
    assert db_chat_room.user_id == user_id


def test_read_chat_room_by_user_id(
        session: Session, client: TestClient, login: login_fixture, chat_room: chat_room_fixture
):
    # Get user data from user creation request.
    access_token = login["access_token"]

    # Create request for chat room deletion.
    req_url = f"{URL_CHAT}/chat-room/"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 1
    assert data[0]["id"] == chat_room['id']
    assert data[0]["title"] == chat_room["title"]


def test_delete_chat_room(session: Session, client: TestClient, login: login_fixture, chat_room: chat_room_fixture):
    # Get user data from user creation request.
    access_token = login["access_token"]

    # Get chat room data from chat room creation request.
    chat_room_id = chat_room['id']

    # Create request for chat room deletion.
    req_url = f"{URL_CHAT}/chat-room/{chat_room_id}"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.delete(url=req_url, headers=req_headers)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 1
    assert data["ok"] is True


def test_websocket_endpoint(session: Session, client: TestClient, login: login_fixture, chat_room: chat_room_fixture):
    # Get user data from user creation request.
    access_token = login["access_token"]

    # Get chat room data from chat room creation request.
    chat_room_id = chat_room['id']

    # Create websocket connection.
    req_param = f"?token={access_token}&chat_room_id={chat_room_id}"
    req_url = f"{URL_CHAT}/ws{req_param}"

    with client.websocket_connect(url=req_url) as websocket:
        message_json = {"message": "Hello World!"}
        websocket.send_json(message_json)
        response_json = websocket.receive_json()

    # Check database for newly created chat messages.
    db_chat_room = get_chat_room_by_id(session, chat_room_id)
    db_chat_messages = db_chat_room.chat_messages

    # Testing assertions.
    assert response_json["es_result"] is not None
    assert response_json["rag_result"] is not None

    assert len(db_chat_messages) == 1


def test_read_chat_room_messages(
        session: Session, client: TestClient, login: login_fixture, chat_room: chat_room_fixture
):
    # Get user data from user creation request.
    access_token = login["access_token"]

    # Get chat room data from chat room creation request.
    chat_room_id = chat_room['id']

    # Create request for reading messages of a chat room.
    req_url = f"{URL_CHAT}/chat-room/{chat_room_id}"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert data is not None
