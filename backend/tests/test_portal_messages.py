"""Tests for customer portal messages on a work order."""


def _portal_wo(client, portal_headers):
    wos = client.get("/api/portal/work-orders", headers=portal_headers).json()
    assert wos, "portal customer should own a work order"
    return wos[0]


def test_customer_message_appears_on_both_timelines(client, portal_headers, staff_headers):
    wo = _portal_wo(client, portal_headers)

    before = len(client.get("/api/notifications", headers=staff_headers).json())
    r = client.post(f"/api/portal/work-orders/{wo['id']}/messages",
                    json={"message": "Any update on my motor?"}, headers=portal_headers)
    assert r.status_code == 201
    assert any("Any update on my motor?" in (e.get("message") or "") for e in r.json()["events"])

    # Staff were notified.
    assert len(client.get("/api/notifications", headers=staff_headers).json()) > before

    # Staff see the message on their view of the same work order.
    number = wo["number"]
    staff_wo = next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                    if w["number"] == number)
    detail = client.get(f"/api/work-orders/{staff_wo['id']}", headers=staff_headers).json()
    assert any("Any update on my motor?" in (e.get("message") or "") for e in detail["events"])


def test_cannot_message_foreign_work_order(client, portal_headers, staff_headers):
    owned = {w["id"] for w in client.get("/api/portal/work-orders", headers=portal_headers).json()}
    foreign = next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                   if w["id"] not in owned)
    assert client.post(f"/api/portal/work-orders/{foreign['id']}/messages",
                       json={"message": "sneaky"}, headers=portal_headers).status_code == 404


def test_empty_message_rejected(client, portal_headers):
    wo = _portal_wo(client, portal_headers)
    assert client.post(f"/api/portal/work-orders/{wo['id']}/messages",
                       json={"message": ""}, headers=portal_headers).status_code == 422


def test_staff_cannot_use_portal_message_endpoint(client, staff_headers):
    assert client.post("/api/portal/work-orders/1/messages",
                       json={"message": "hi"}, headers=staff_headers).status_code == 403
