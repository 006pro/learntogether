import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TEST_SECRET = "test-secret-key-that-is-long-enough-for-checks"


@pytest.fixture
def make_settings(tmp_path):
    """Settings pointing at a fresh SQLite file in a per-test temp directory."""

    def _make(**overrides) -> Settings:
        values = {
            "app_env": "development",
            "secret_key": TEST_SECRET,
            "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "dev_auth_enabled": True,
        }
        values.update(overrides)
        return Settings(**values)

    return _make


@pytest.fixture
def app(make_settings):
    return create_app(make_settings())


@pytest.fixture
def client(app):
    # Entering the context runs the lifespan, which creates the tables.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def other_client(app, client):
    """A second browser session against the same app and database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(app, client):
    session = app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def login(client: TestClient, name: str = "Ada") -> str:
    """Sign in through the development endpoint and return the session's CSRF token."""
    token = client.get("/auth/options").json()["csrf_token"]
    response = client.post("/auth/dev-login", json={"name": name}, headers={"X-CSRF-Token": token})
    assert response.status_code == 204, response.text
    return client.get("/api/me").json()["csrf_token"]


def add_topic(client: TestClient, token: str, name: str):
    return client.post("/api/topics", json={"name": name}, headers={"X-CSRF-Token": token})


def vote(client: TestClient, token: str, topic_id: int):
    return client.post(f"/api/topics/{topic_id}/vote", headers={"X-CSRF-Token": token})
