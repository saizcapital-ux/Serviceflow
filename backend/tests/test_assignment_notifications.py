"""Tests for work-order assignment notifications."""


def _tech_and_customer(client, staff_headers):
    users = client.get("/api/users", headers=staff_headers).json()
    tech = next(u for u in users if u["role"] == "technician")
    owner = next(u for u in users if u["role"] == "owner")
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    return tech, owner, cid


def _assign_notifs_for(client, staff_headers, number):
    subject = f"You've been assigned {number}"
    return [n for n in client.get("/api/notifications", headers=staff_headers).json() if n["subject"] == subject]


def _new_wo(client, staff_headers, cid, **extra):
    body = {"customer_id": cid, "title": "Assignment test", "priority": "normal",
            "service_type": "shop_repair", "problem_description": "x", **extra}
    r = client.post("/api/work-orders", json=body, headers=staff_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_notifies_assignee_on_create(client, staff_headers):
    tech, _, cid = _tech_and_customer(client, staff_headers)
    wo = _new_wo(client, staff_headers, cid, assigned_to=tech["id"])
    notifs = _assign_notifs_for(client, staff_headers, wo["number"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"]  # emailed to the assignee


def test_notifies_on_reassignment(client, staff_headers):
    tech, _, cid = _tech_and_customer(client, staff_headers)
    wo = _new_wo(client, staff_headers, cid)  # unassigned
    assert _assign_notifs_for(client, staff_headers, wo["number"]) == []

    r = client.patch(f"/api/work-orders/{wo['id']}", json={"assigned_to": tech["id"]}, headers=staff_headers)
    assert r.status_code == 200
    assert len(_assign_notifs_for(client, staff_headers, wo["number"])) == 1


def test_no_notification_for_self_assignment(client, staff_headers):
    _, owner, cid = _tech_and_customer(client, staff_headers)
    wo = _new_wo(client, staff_headers, cid, assigned_to=owner["id"])  # admin assigns self
    assert _assign_notifs_for(client, staff_headers, wo["number"]) == []


def test_no_notification_on_non_assignment_edit(client, staff_headers):
    tech, _, cid = _tech_and_customer(client, staff_headers)
    wo = _new_wo(client, staff_headers, cid, assigned_to=tech["id"])
    before = len(_assign_notifs_for(client, staff_headers, wo["number"]))
    client.patch(f"/api/work-orders/{wo['id']}", json={"title": "Renamed"}, headers=staff_headers)
    # Re-setting the same assignee is not a new assignment either.
    client.patch(f"/api/work-orders/{wo['id']}", json={"assigned_to": tech["id"]}, headers=staff_headers)
    assert len(_assign_notifs_for(client, staff_headers, wo["number"])) == before


def test_assign_to_unknown_user_rejected(client, staff_headers):
    _, _, cid = _tech_and_customer(client, staff_headers)
    wo = _new_wo(client, staff_headers, cid)
    assert client.patch(f"/api/work-orders/{wo['id']}", json={"assigned_to": 999999},
                        headers=staff_headers).status_code == 404
