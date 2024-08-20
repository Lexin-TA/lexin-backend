import pytest
import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from internal.auth import verify_password, create_access_token, JWT_REFRESH_SECRET_KEY, JWT_ALGORITHM
from main import app
from internal.database import get_session
from models.UserGoogleModel import UserGoogle
from models.UserModel import User
from services.UserGoogleService import get_user_by_google_sub, create_user_from_google_info

BASE_TEST_URL = '/api/v1/user'

GOOGLE_ID_TOKEN_EXAMPLE = {
 # These six fields are included in all Google ID Tokens.
 "iss": "https://accounts.google.com",
 "sub": "110169484474386276334",
 "azp": "1008719970978-hb24n2dstb40o45d4feuo2ukqmcc6381.apps.googleusercontent.com",
 "aud": "1008719970978-hb24n2dstb40o45d4feuo2ukqmcc6381.apps.googleusercontent.com",
 "iat": "1433978353",
 "exp": "1433981953",

 # These seven fields are only included when the user has granted the "profile" and
 # "email" OAuth scopes to the application.
 "email": "testuser@gmail.com",
 "email_verified": "true",
 "name": "Test User",
 "picture": "https://lh4.googleusercontent.com/-kYgzyAWpZzJ/ABCDEFGHI/AAAJKLMNOP/tIXL9Ir44LE/s99-c/photo.jpg",
 "given_name": "Test",
 "family_name": "User",
 "locale": "en"
}


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


@pytest.fixture(name="user_test")
def user_test_fixture(client: TestClient):
    # Create request for user registration.
    req_url = f"{BASE_TEST_URL}/register"
    req_json = {"email": GOOGLE_ID_TOKEN_EXAMPLE["email"],
                "fullname": GOOGLE_ID_TOKEN_EXAMPLE["name"],
                "password": "string"}
    response = client.post(url=req_url, json=req_json)

    user_data = response.json()

    return user_data


@pytest.fixture(name="create_user_from_google_user")
def create_user_from_google_user_fixture(session: Session):
    # Create User object from UserGoogle data.
    user_google = UserGoogle(sub=GOOGLE_ID_TOKEN_EXAMPLE["sub"],
                             email=GOOGLE_ID_TOKEN_EXAMPLE["email"],
                             name=GOOGLE_ID_TOKEN_EXAMPLE["name"],
                             picture=GOOGLE_ID_TOKEN_EXAMPLE["picture"])

    db_user = create_user_from_google_info(session=session, user_google=user_google)

    return db_user


@pytest.fixture(name="login")
def login_fixture(client: TestClient, user):
    # Create request to login.
    req_url = f"{BASE_TEST_URL}/token"
    req_data = {"username": "user@example.com",
                "password": "string"}
    response = client.post(url=req_url, data=req_data)

    token_data = response.json()

    return token_data


def test_create_user_from_google_info_user_exist_in_database(
        session: Session,
        client: TestClient,
        user_test: user_test_fixture,
        create_user_from_google_user: create_user_from_google_user_fixture
):
    # Create User object from UserGoogle data.
    db_user = create_user_from_google_user

    # Testing assertions.
    assert db_user is not None
    assert db_user.id is not None
    assert db_user.email == GOOGLE_ID_TOKEN_EXAMPLE["email"]
    assert db_user.fullname == GOOGLE_ID_TOKEN_EXAMPLE["name"]
    assert db_user.google_sub == GOOGLE_ID_TOKEN_EXAMPLE["sub"]


def test_create_user_from_google_info_user_not_exist_in_database(
        session: Session,
        user: user_fixture,
        create_user_from_google_user: create_user_from_google_user_fixture
):
    # Create User object from UserGoogle data.
    db_user = create_user_from_google_user

    # Testing assertions.
    assert db_user is not None
    assert db_user.id is not None
    assert db_user.email == GOOGLE_ID_TOKEN_EXAMPLE["email"]
    assert db_user.fullname == GOOGLE_ID_TOKEN_EXAMPLE["name"]
    assert db_user.google_sub == GOOGLE_ID_TOKEN_EXAMPLE["sub"]


def test_get_user_by_google_sub(
        session: Session,
        user_test: user_test_fixture,
        create_user_from_google_user: create_user_from_google_user_fixture
):
    # Create User object from UserGoogle data.
    _ = create_user_from_google_user

    # Get User object by google sub.
    db_user = get_user_by_google_sub(session=session, google_sub=GOOGLE_ID_TOKEN_EXAMPLE["sub"])

    # Testing assertions.
    assert db_user is not None
    assert db_user.id is not None
    assert db_user.email == GOOGLE_ID_TOKEN_EXAMPLE["email"]
    assert db_user.fullname == GOOGLE_ID_TOKEN_EXAMPLE["name"]
    assert db_user.google_sub == GOOGLE_ID_TOKEN_EXAMPLE["sub"]
