"""Tests for work-order timeline notes."""


def _first_wo(client, staff_headers):
    return client.get("/api/work-orders", headers=staff_headers).json()[0]


def test_add_internal_note(client, staff_headers):
    wo = _first_wo(client, staff_headers)
    r = client.post(f"/api/work-orders/{wo['id']}/notes",
                    json={"message": "Waiting on bearing delivery"}, headers=staff_headers)
    assert r.status_code == 201
    notes = [e for e in r.json()["events"] if e["event_type"] == "note"]
    assert any(e["message"] == "Waiting on bearing delivery" and e["visible_to_customer"] is False for e in notes)


def test_empty_note_rejected(client, staff_headers):
    wo = _first_wo(client, staff_headers)
    assert client.post(f"/api/work-orders/{wo['id']}/notes", json={"message": "   "},
                       headers=staff_headers).status_code == 201  # whitespace is non-empty by min_length
    assert client.post(f"/api/work-orders/{wo['id']}/notes", json={"message": ""},
                       headers=staff_headers).status_code == 422


def test_note_requires_staff(client, portal_headers):
    # Portal users can't post staff notes (route is staff-only).
    assert client.post("/api/work-orders/1/notes", json={"message": "hi"},
                       headers=portal_headers).status_code == 403


def test_customer_visible_note_reaches_portal_internal_stays_hidden(client, staff_headers, portal_headers):
    # Pick a work order that the portal customer (buyer@acmepower.com) owns.
    portal_wos = client.get("/api/portal/work-orders", headers=portal_headers).json()
    assert portal_wos, "portal customer should own at least one work order"
    number = portal_wos[0]["number"]
    staff_wo = next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                    if w["number"] == number)

    client.post(f"/api/work-orders/{staff_wo['id']}/notes",
                json={"message": "INTERNAL ONLY note"}, headers=staff_headers)
    client.post(f"/api/work-orders/{staff_wo['id']}/notes",
                json={"message": "Shared update for you", "visible_to_customer": True}, headers=staff_headers)

    detail = client.get(f"/api/portal/work-orders/{portal_wos[0]['id']}", headers=portal_headers).json()
    messages = [e.get("message") for e in detail["events"]]
    assert "Shared update for you" in messages
    assert "INTERNAL ONLY note" not in messages
    assert all(e["visible_to_customer"] for e in detail["events"])
