"""Tests for self-serve organization signup."""
import uuid


def _email():
    return f"owner-{uuid.uuid4().hex[:8]}@newshop.com"


def test_signup_creates_org_owner_and_logs_in(client):
    email = _email()
    r = client.post("/api/auth/signup", json={
        "organization_name": "Gulf Coast Motor Works", "full_name": "Casey Lee",
        "email": email, "password": "Secret123",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    assert body["user"]["role"] == "owner"
    assert body["user"]["email"] == email

    headers = {"Authorization": f"Bearer {body['access_token']}"}

    # Brand-new tenant starts empty and isolated from the demo org.
    assert client.get("/api/work-orders", headers=headers).json() == []
    assert client.get("/api/customers", headers=headers).json() == []
    # ...but has a default location so work orders can be created immediately.
    locations = client.get("/api/locations", headers=headers).json()
    assert [loc["name"] for loc in locations] == ["Main Shop"]

    # The new owner can sign in.
    assert client.post("/api/auth/login", json={"email": email, "password": "Secret123"}).status_code == 200


def test_signup_rejects_duplicate_email(client):
    # admin@apexrepair.com already exists (seed).
    r = client.post("/api/auth/signup", json={
        "organization_name": "Another Shop", "full_name": "Dup",
        "email": "admin@apexrepair.com", "password": "Secret123",
    })
    assert r.status_code == 409


def test_signup_validation(client):
    # Short password.
    assert client.post("/api/auth/signup", json={
        "organization_name": "Valid Shop Name", "full_name": "X", "email": _email(), "password": "short",
    }).status_code == 422
    # Too-short org name.
    assert client.post("/api/auth/signup", json={
        "organization_name": "X", "full_name": "Y", "email": _email(), "password": "Secret123",
    }).status_code == 422


def test_signup_generates_unique_slugs(client):
    name = "Identical Shop Name"
    a = client.post("/api/auth/signup", json={
        "organization_name": name, "full_name": "A", "email": _email(), "password": "Secret123"})
    b = client.post("/api/auth/signup", json={
        "organization_name": name, "full_name": "B", "email": _email(), "password": "Secret123"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["user"]["organization_id"] != b.json()["user"]["organization_id"]
