"""Tests for team member management (role changes, activate/deactivate)."""
import re

from app.core.database import SessionLocal
from app.models import Notification


def _invite_accept(client, staff_headers, email, role, password="Passw0rd1"):
    """Create a real staff account with the given role via the invite flow.
    Returns (auth_headers, user_id). Keeps demo accounts untouched."""
    r = client.post("/api/invites", json={"email": email, "role": role}, headers=staff_headers)
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        body = (db.query(Notification).filter(Notification.recipient == email)
                .order_by(Notification.id.desc()).first().body)
    finally:
        db.close()
    token = re.search(r"accept-invite\.html\?token=([\w\-]+)", body).group(1)
    res = client.post("/api/invites/accept", json={"token": token, "full_name": f"User {email}", "password": password})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, res.json()["user"]["id"]


def test_owner_changes_role_and_status(client, staff_headers):
    _, uid = _invite_accept(client, staff_headers, "mgmt-a@apexrepair.com", "technician")

    # Promote to manager.
    r = client.patch(f"/api/team/members/{uid}", json={"role": "manager"}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["role"] == "manager"

    # Deactivate, then reactivate.
    r = client.patch(f"/api/team/members/{uid}", json={"is_active": False}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = client.patch(f"/api/team/members/{uid}", json={"is_active": True}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["is_active"] is True


def test_cannot_edit_self(client, staff_headers):
    me = next(m for m in client.get("/api/team/members", headers=staff_headers).json()
              if m["email"] == "admin@apexrepair.com")
    r = client.patch(f"/api/team/members/{me['id']}", json={"role": "manager"}, headers=staff_headers)
    assert r.status_code == 400


def test_manager_cannot_manage_owners_or_grant_owner(client, staff_headers):
    mgr_headers, _ = _invite_accept(client, staff_headers, "mgmt-mgr@apexrepair.com", "manager")
    owner = next(m for m in client.get("/api/team/members", headers=staff_headers).json()
                 if m["email"] == "admin@apexrepair.com")
    _, tech_id = _invite_accept(client, staff_headers, "mgmt-tech@apexrepair.com", "technician")

    # A manager cannot modify an owner...
    assert client.patch(f"/api/team/members/{owner['id']}", json={"is_active": False}, headers=mgr_headers).status_code == 403
    # ...nor promote anyone to owner.
    assert client.patch(f"/api/team/members/{tech_id}", json={"role": "owner"}, headers=mgr_headers).status_code == 403
    # ...but can manage a non-owner.
    assert client.patch(f"/api/team/members/{tech_id}", json={"role": "service_writer"}, headers=mgr_headers).status_code == 200


def test_technician_forbidden(client, staff_headers):
    tech_headers, _ = _invite_accept(client, staff_headers, "mgmt-t2@apexrepair.com", "technician")
    _, other = _invite_accept(client, staff_headers, "mgmt-t3@apexrepair.com", "technician")
    assert client.get("/api/team/members", headers=tech_headers).status_code == 403
    assert client.patch(f"/api/team/members/{other}", json={"role": "manager"}, headers=tech_headers).status_code == 403


def test_unknown_member_404(client, staff_headers):
    assert client.patch("/api/team/members/999999", json={"role": "manager"}, headers=staff_headers).status_code == 404


def test_members_list_includes_email_and_status(client, staff_headers):
    members = client.get("/api/team/members", headers=staff_headers).json()
    assert members and all({"email", "role", "is_active", "full_name"} <= set(m) for m in members)
    assert all(m["role"] != "customer" for m in members)  # portal users excluded
