"""Pytest fixtures: isolated temp database seeded with demo data + a TestClient."""
import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file BEFORE importing app modules,
# so settings/engine bind to the test database.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ["SERVICEFLOW_DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seeded():
    seed()
    yield
    os.close(_DB_FD)
    os.unlink(_DB_PATH)


@pytest.fixture()
def client():
    return TestClient(app)


def _token(client, email, password="Password123"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def staff_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'admin@apexrepair.com')}"}


@pytest.fixture()
def portal_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'buyer@acmepower.com')}"}
