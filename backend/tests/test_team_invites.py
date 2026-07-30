"""Tests for team invitations and password reset."""
import re

from app.core.database import SessionLocal
from app.models import Notification


def _latest_token(recipient: str, page: str) -> str:
    """Pull the raw token out of the most recent emailed link for `recipient`.

    `page` is the frontend page the link points at, e.g. "accept-invite.html".
    """
    db = SessionLocal()
    try:
        note = (
            db.query(Notification)
            .filter(Notification.recipient == recipient)
            .order_by(Notification.id.desc())
            .first()
        )
        assert note is not None, f"no notification for {recipient}"
        m = re.search(rf"{re.escape(page)}\?token=([\w\-]+)", note.body)
        assert m, f"no token link in notification body: {note.body!r}"
        return m.group(1)
    finally:
        db.close()


def _staff(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "Password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_invite_lifecycle_and_accept(client, staff_headers):
    email = "invitee1@apexrepair.com"

    created = client.post("/api/invites", json={"email": email, "role": "technician"}, headers=staff_headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"

    # Appears in the org's invite list, attributed to the inviter.
    listing = client.get("/api/invites", headers=staff_headers)
    assert listing.status_code == 200
    row = next(i for i in listing.json() if i["email"] == email)
    assert row["status"] == "pending"
    assert row["invited_by_name"]

    token = _latest_token(email, "accept-invite.html")

    # Public lookup returns who/what the invite is for.
    lk = client.get(f"/api/invites/accept?token={token}")
    assert lk.status_code == 200
    assert lk.json()["email"] == email
    assert lk.json()["role"] == "technician"

    # Accept -> account created, caller is logged in.
    acc = client.post("/api/invites/accept", json={"token": token, "full_name": "New Tech", "password": "Secret123"})
    assert acc.status_code == 201, acc.text
    assert acc.json()["user"]["email"] == email
    assert acc.json()["user"]["role"] == "technician"
    assert acc.json()["access_token"]

    # The new user can now sign in.
    assert client.post("/api/auth/login", json={"email": email, "password": "Secret123"}).status_code == 200

    # Token is single-use.
    assert client.get(f"/api/invites/accept?token={token}").status_code == 400
    assert client.post(
        "/api/invites/accept", json={"token": token, "full_name": "x", "password": "Secret123"}
    ).status_code == 400


def test_non_manager_cannot_invite(client):
    tech = _staff(client, "tech@apexrepair.com")  # technician role
    assert client.post("/api/invites", json={"email": "x@apexrepair.com", "role": "technician"}, headers=tech).status_code == 403
    assert client.get("/api/invites", headers=tech).status_code == 403


def test_cannot_invite_customer_role(client, staff_headers):
    r = client.post("/api/invites", json={"email": "cust@apexrepair.com", "role": "customer"}, headers=staff_headers)
    assert r.status_code == 422


def test_duplicate_member_rejected(client, staff_headers):
    # admin@apexrepair.com already exists on the team.
    r = client.post("/api/invites", json={"email": "admin@apexrepair.com", "role": "manager"}, headers=staff_headers)
    assert r.status_code == 409


def test_revoke_invite(client, staff_headers):
    email = "revokeme@apexrepair.com"
    created = client.post("/api/invites", json={"email": email, "role": "manager"}, headers=staff_headers)
    invite_id = created.json()["id"]
    token = _latest_token(email, "accept-invite.html")

    rev = client.post(f"/api/invites/{invite_id}/revoke", headers=staff_headers)
    assert rev.status_code == 200
    assert rev.json()["status"] == "revoked"

    # A revoked token no longer works.
    assert client.get(f"/api/invites/accept?token={token}").status_code == 400


def test_short_password_rejected_on_accept(client, staff_headers):
    email = "shortpw@apexrepair.com"
    client.post("/api/invites", json={"email": email, "role": "technician"}, headers=staff_headers)
    token = _latest_token(email, "accept-invite.html")
    r = client.post("/api/invites/accept", json={"token": token, "full_name": "Y", "password": "short"})
    assert r.status_code == 422


def test_forgot_and_reset_password(client, staff_headers):
    # Use a freshly-provisioned account so demo logins stay intact for other tests.
    email = "resetme@apexrepair.com"
    client.post("/api/invites", json={"email": email, "role": "technician"}, headers=staff_headers)
    invite_token = _latest_token(email, "accept-invite.html")
    client.post("/api/invites/accept", json={"token": invite_token, "full_name": "Reset Me", "password": "Original1"})

    # Unknown emails still return 202 (no account enumeration).
    assert client.post("/api/auth/forgot-password", json={"email": "ghost@notreal-shop.com"}).status_code == 202

    assert client.post("/api/auth/forgot-password", json={"email": email}).status_code == 202
    reset_token = _latest_token(email, "reset-password.html")

    done = client.post("/api/auth/reset-password", json={"token": reset_token, "password": "Updated123"})
    assert done.status_code == 200
    assert done.json()["user"]["email"] == email

    # Old password no longer works; new one does.
    assert client.post("/api/auth/login", json={"email": email, "password": "Original1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "Updated123"}).status_code == 200

    # Reset token is single-use.
    assert client.post("/api/auth/reset-password", json={"token": reset_token, "password": "Another12"}).status_code == 400


def test_reset_with_bad_token_rejected(client):
    assert client.post("/api/auth/reset-password", json={"token": "nonsense", "password": "Whatever1"}).status_code == 400
