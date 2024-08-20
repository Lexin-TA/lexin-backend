import pytest
import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from internal.auth import verify_password, create_access_token, JWT_REFRESH_SECRET_KEY, JWT_ALGORITHM
from main import app
from internal.database import get_session
from models.UserModel import User

BASE_TEST_URL = '/api/v1/user'


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
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user@example.com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    user_data = response.json()

    return user_data


@pytest.fixture(name="login")
def login_fixture(client: TestClient, user):
    # Create request to login.
    req_url = f"{BASE_TEST_URL}/token"
    req_data = {"username": "user@example.com",
                "password": "string"}
    response = client.post(url=req_url, data=req_data)

    token_data = response.json()

    return token_data


def test_register(session: Session, client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user@example.com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    data = response.json()

    # Check database for newly created user.
    statement = select(User).where(User.id == data["id"])
    result = session.exec(statement)
    db_user = result.first()

    is_password_verified = verify_password(req_json["password"], db_user.password)

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 3
    assert data["id"] is not None
    assert data["email"] == req_json["email"]
    assert data["fullname"] == req_json["fullname"]

    assert db_user.id == data["id"]
    assert db_user.email == data["email"]
    assert db_user.fullname == data["fullname"]
    assert is_password_verified


def test_register_invalid_email_no_at_sign(client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user_with_no_at_sign_example.com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    # Testing assertions.
    assert response.status_code == 422


def test_register_invalid_email_no_period(client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user@example_with_no_period_com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    # Testing assertions.
    assert response.status_code == 422


def test_register_unique_email(user: user_fixture, client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user@example.com",
                "fullname": "string",
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    # Testing assertions.
    assert response.status_code == 422


def test_login(client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": "user@example.com",
                "fullname": "string",
                "password": "string"}
    client.post(url=req_url, json=req_json)

    # Create request to login.
    req_url = f"{BASE_TEST_URL}/token"
    req_data = {"username": "user@example.com",
                "password": "string"}
    response = client.post(url=req_url, data=req_data)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 3
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None
    assert data["token_type"] == "Bearer"


def test_login_incorrect_credentials(user: user_fixture, client: TestClient):
    # Create request to login.
    req_url = f"{BASE_TEST_URL}/token"
    req_data = {"username": "user@example.com",
                "password": "wrong password"}
    response = client.post(url=req_url, data=req_data)

    # Testing assertions.
    assert response.status_code == 401


def test_read_users_me(user: user_fixture, login: login_fixture, client: TestClient):
    # Create request for user registration.
    user_data = user

    # Create request to login.
    token_data = login

    # Create request to read users me.
    access_token = token_data["access_token"]

    req_url = f"{BASE_TEST_URL}/me"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 3
    assert data["id"] is not None
    assert data["email"] == user_data["email"]
    assert data["fullname"] == user_data["fullname"]


def test_read_users_me_invalid_token(user: user_fixture, login: login_fixture, client: TestClient):
    # Create request to read users me.
    access_token = "some_invalid_access_token"

    req_url = f"{BASE_TEST_URL}/me"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    # Testing assertions.
    assert response.status_code == 401


def test_read_users_me_invalid_token_no_user_id_payload(user: user_fixture, login: login_fixture, client: TestClient):
    # Create token without 'sub' payload.
    token_data_no_sub = {}
    access_token = create_access_token(data=token_data_no_sub)

    # Create request to read users me.
    req_url = f"{BASE_TEST_URL}/me"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    # Testing assertions.
    assert response.status_code == 401


def test_read_users_me_invalid_token_no_user_id_found(user: user_fixture, login: login_fixture, client: TestClient):
    # Create token with invalid user id.
    token_data_invalid_user_id = {"sub": 42}
    access_token = create_access_token(data=token_data_invalid_user_id)

    # Create request to read users me.
    req_url = f"{BASE_TEST_URL}/me"
    req_headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get(url=req_url, headers=req_headers)

    # Testing assertions.
    assert response.status_code == 401


def test_refresh_access_token(user: user_fixture, login: login_fixture, client: TestClient):
    refresh_token = login["refresh_token"]

    # Create request to read users me.
    req_url = f"{BASE_TEST_URL}/refresh"
    req_json = {"refresh_token": refresh_token}
    response = client.post(url=req_url, json=req_json)

    data = response.json()

    # Testing assertions.
    assert response.status_code == 200
    assert len(data) == 3
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None
    assert data["token_type"] == "Bearer"


def test_refresh_access_token_expired_refresh_token(user: user_fixture, login: login_fixture, client: TestClient):
    # Create expired refresh token.
    token_data_expired = {"sub": user['id'], "exp": 0}
    refresh_token = jwt.encode(token_data_expired, JWT_REFRESH_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Create request to read users me.
    req_url = f"{BASE_TEST_URL}/refresh"
    req_json = {"refresh_token": refresh_token}
    response = client.post(url=req_url, json=req_json)

    # Testing assertions.
    assert response.status_code == 401


def test_refresh_access_token_invalid_refresh_token(user: user_fixture, login: login_fixture, client: TestClient):
    # Create invalid refresh token.
    refresh_token = "some_invalid_refresh_token"

    # Create request to read users me.
    req_url = f"{BASE_TEST_URL}/refresh"
    req_json = {"refresh_token": refresh_token}
    response = client.post(url=req_url, json=req_json)

    # Testing assertions.
    assert response.status_code == 401
