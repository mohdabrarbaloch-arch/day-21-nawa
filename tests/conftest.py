"""Shared fixtures.

The database is a throwaway SQLite file per test session, and the speech
service is never called: tests that need audio use a fake synthesiser. That
keeps the suite fast and deterministic, and means it passes on a machine with
no network.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="nawa-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-in-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_factory(client):
    """Register a user and return (token, user dict)."""

    def make(password: str = "goodpass1234"):
        # Unique per call: the schema is created once per session, so a
        # counter would collide across test modules.
        email = f"user-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "Test User"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return body["access_token"], body["user"]

    return make


@pytest.fixture
def auth_headers(user_factory):
    token, _ = user_factory()
    return {"Authorization": f"Bearer {token}"}
