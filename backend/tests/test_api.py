"""API tests: auth, RBAC/tenant isolation, work-order lifecycle, portal."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_login_bad_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@apexrepair.com", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_is_rejected(client):
    assert client.get("/api/dashboard").status_code == 401


def test_dashboard_has_open_work_orders(client, staff_headers):
    r = client.get("/api/dashboard", headers=staff_headers)
    assert r.status_code == 200
    assert r.json()["open_work_orders"] >= 1


def test_customer_cannot_access_staff_endpoint(client, portal_headers):
    assert client.get("/api/dashboard", headers=portal_headers).status_code == 403


def test_portal_only_sees_own_work_orders(client, portal_headers):
    r = client.get("/api/portal/work-orders", headers=portal_headers)
    assert r.status_code == 200
    numbers = {w["number"] for w in r.json()}
    # Acme jobs present, Gulf Coast jobs (WO-2026-0003/0004) absent.
    assert "WO-2026-0001" in numbers
    assert "WO-2026-0003" not in numbers


def test_create_work_order_and_advance_status(client, staff_headers):
    customers = client.get("/api/customers", headers=staff_headers).json()
    cid = customers[0]["id"]
    created = client.post(
        "/api/work-orders",
        headers=staff_headers,
        json={"customer_id": cid, "title": "Test intake job", "service_type": "shop_repair"},
    )
    assert created.status_code == 201, created.text
    wo = created.json()
    assert wo["status"] == "intake"
    assert wo["number"].startswith("WO-")

    # Valid transition intake -> inspection
    ok = client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers,
                     json={"status": "inspection"})
    assert ok.status_code == 200 and ok.json()["status"] == "inspection"

    # Invalid transition inspection -> shipped is rejected by the state machine
    bad = client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers,
                      json={"status": "shipped"})
    assert bad.status_code == 409


def test_portal_quote_approval_advances_work_order(client, staff_headers, portal_headers):
    # Find Acme's quote_pending job (WO-2026-0002) and its quote via portal.
    orders = client.get("/api/portal/work-orders", headers=portal_headers).json()
    target = next(w for w in orders if w["number"] == "WO-2026-0002")
    detail = client.get(f"/api/portal/work-orders/{target['id']}", headers=portal_headers).json()
    pending = next(q for q in detail["quotes"] if q["status"] == "sent")

    r = client.post(f"/api/portal/quotes/{pending['id']}/decision", headers=portal_headers,
                    json={"approve": True, "note": "Go ahead"})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    after = client.get(f"/api/portal/work-orders/{target['id']}", headers=portal_headers).json()
    assert after["status"] == "approved"
