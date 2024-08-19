import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from main import app
from internal.database import get_session

BASE_TEST_URL = '/api/v1/health-check'


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


def test_health_check(session: Session, client: TestClient):
    req_url = BASE_TEST_URL
    response = client.get(req_url)

    data = response.json()

    assert response.status_code == 200
    assert data['detail'] == 'Hello World from backend application.'
