"""Tests for self-service account settings (profile + password change)."""


def _fresh_user(client, staff_headers, email, password="Original1"):
    """Invite + accept a dedicated user so tests don't disturb demo logins.
    Returns an auth header dict for the new account."""
    from app.core.database import SessionLocal
    from app.models import Notification
    import re

    client.post("/api/invites", json={"email": email, "role": "technician"}, headers=staff_headers)
    db = SessionLocal()
    try:
        body = (
            db.query(Notification).filter(Notification.recipient == email)
            .order_by(Notification.id.desc()).first().body
        )
    finally:
        db.close()
    token = re.search(r"accept-invite\.html\?token=([\w\-]+)", body).group(1)
    res = client.post("/api/invites/accept", json={"token": token, "full_name": "Original Name", "password": password})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, res.json()["user"]["id"]


def test_update_display_name(client, staff_headers):
    headers, _ = _fresh_user(client, staff_headers, "acct-name@apexrepair.com")

    r = client.patch("/api/auth/me", json={"full_name": "  Renamed Person  "}, headers=headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Renamed Person"  # trimmed

    # Persisted.
    assert client.get("/api/auth/me", headers=headers).json()["full_name"] == "Renamed Person"


def test_update_name_rejects_blank(client, staff_headers):
    headers, _ = _fresh_user(client, staff_headers, "acct-blank@apexrepair.com")
    assert client.patch("/api/auth/me", json={"full_name": "   "}, headers=headers).status_code == 422


def test_change_password_flow(client, staff_headers):
    email = "acct-pw@apexrepair.com"
    headers, _ = _fresh_user(client, staff_headers, email, password="Original1")

    # Wrong current password is rejected.
    assert client.post("/api/auth/change-password",
                       json={"current_password": "wrong", "new_password": "NewSecret1"},
                       headers=headers).status_code == 400

    # New password identical to current is rejected.
    assert client.post("/api/auth/change-password",
                       json={"current_password": "Original1", "new_password": "Original1"},
                       headers=headers).status_code == 400

    # Too-short new password fails validation.
    assert client.post("/api/auth/change-password",
                       json={"current_password": "Original1", "new_password": "short"},
                       headers=headers).status_code == 422

    # Valid change works.
    ok = client.post("/api/auth/change-password",
                     json={"current_password": "Original1", "new_password": "NewSecret1"},
                     headers=headers)
    assert ok.status_code == 200

    # Old password no longer logs in; new one does.
    assert client.post("/api/auth/login", json={"email": email, "password": "Original1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "NewSecret1"}).status_code == 200


def test_account_endpoints_require_auth(client):
    assert client.patch("/api/auth/me", json={"full_name": "X"}).status_code == 401
    assert client.post("/api/auth/change-password",
                       json={"current_password": "a", "new_password": "abcdefgh"}).status_code == 401
