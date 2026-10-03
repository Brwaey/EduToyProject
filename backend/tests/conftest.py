import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ORIGIN = "http://127.0.0.1:5173"


@pytest.fixture
def app(tmp_path):
    return create_app(
        Settings(db_path=str(tmp_path / "test.sqlite3"), ai_key_path=str(tmp_path / "test.key"))
    )


@pytest.fixture
def client(app):
    with TestClient(app, headers={"Origin": ORIGIN}) as client:
        yield client


def register(client, username="researcher"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "display_name": "研究者",
            "password": "research-12345",
        },
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def auth(client):
    register(client)
    return client
