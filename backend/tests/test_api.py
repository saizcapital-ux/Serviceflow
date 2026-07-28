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


def _acme_id(client, staff_headers):
    return client.get("/api/customers", headers=staff_headers).json()[0]["id"]


def test_invoice_from_approved_quote_and_pdf(client, staff_headers):
    # WO-2026-0001 has an approved quote in the seed.
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = next(w for w in wos if w["number"] == "WO-2026-0001")
    created = client.post(f"/api/work-orders/{wo['id']}/invoices", headers=staff_headers,
                          json={"due_in_days": 30, "notes": "Net 30"})
    assert created.status_code == 201, created.text
    inv = created.json()
    assert inv["number"].startswith("INV-")
    assert inv["total"] > 0 and len(inv["lines"]) == 3

    # PDF export returns a real PDF
    pdf = client.get(f"/api/invoices/{inv['id']}/pdf", headers=staff_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    # Mark paid
    paid = client.post(f"/api/invoices/{inv['id']}/paid", headers=staff_headers, json={"paid": True})
    assert paid.status_code == 200 and paid.json()["status"] == "paid"


def test_invoice_requires_approved_quote(client, staff_headers):
    # WO-2026-0003 (field service) has no approved quote.
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = next(w for w in wos if w["number"] == "WO-2026-0003")
    r = client.post(f"/api/work-orders/{wo['id']}/invoices", headers=staff_headers, json={})
    assert r.status_code == 409


def test_analytics_summary(client, staff_headers):
    a = client.get("/api/analytics/summary", headers=staff_headers).json()
    assert set(a) >= {"completed_30d", "avg_turnaround_days", "revenue_by_month",
                      "status_counts", "by_type", "tech_workload", "paid_revenue"}
    assert len(a["revenue_by_month"]) == 6
    assert a["paid_revenue"] >= 692.8
    # Priya Nair logged 14.5h in the seed
    assert any(r["hours"] >= 14.5 for r in a["tech_workload"])


def test_analytics_requires_staff(client, portal_headers):
    assert client.get("/api/analytics/summary", headers=portal_headers).status_code == 403


def test_billing_plans_and_mock_checkout(client, staff_headers):
    plans = client.get("/api/billing/plans", headers=staff_headers).json()
    ids = {p["id"] for p in plans}
    assert {"starter", "pro", "enterprise"} <= ids

    # Owner subscribes (mock mode activates immediately)
    r = client.post("/api/billing/checkout", headers=staff_headers, json={"plan_id": "enterprise"})
    assert r.status_code == 200, r.text
    assert r.json().get("mock") is True
    sub = client.get("/api/billing/subscription", headers=staff_headers).json()
    assert sub["plan"] == "enterprise" and sub["subscription_status"] == "active"
    assert sub["seats"] == 100


def test_billing_unknown_plan_rejected(client, staff_headers):
    r = client.post("/api/billing/checkout", headers=staff_headers, json={"plan_id": "platinum"})
    assert r.status_code == 400


def test_billing_checkout_owner_only(client, portal_headers):
    # Portal (customer) cannot checkout; also non-owner staff is blocked.
    assert client.post("/api/billing/checkout", headers=portal_headers, json={"plan_id": "pro"}).status_code == 403


def test_billing_non_owner_staff_blocked(client):
    tok = client.post("/api/auth/login", json={"email": "tech@apexrepair.com", "password": "Password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/billing/checkout", headers=h, json={"plan_id": "pro"}).status_code == 403


def test_schedule_field_visit(client, staff_headers):
    techs = client.get("/api/users?role=technician", headers=staff_headers).json()
    assert techs, "seed should include a technician"
    wos = client.get("/api/work-orders?service_type=field_service", headers=staff_headers).json()
    wo = wos[0]
    r = client.post(f"/api/work-orders/{wo['id']}/schedule", headers=staff_headers,
                    json={"scheduled_at": "2026-08-01T14:00:00Z", "assigned_to": techs[0]["id"]})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["assigned_to"] == techs[0]["id"]
    assert detail["scheduled_at"] is not None
    # A field_visit event lands on the timeline
    assert any(e["event_type"] == "field_visit" for e in detail["events"])


def test_users_endpoint_excludes_customers(client, staff_headers):
    users = client.get("/api/users", headers=staff_headers).json()
    assert users and all(u["role"] != "customer" for u in users)


def test_status_change_creates_notification(client, staff_headers):
    # Create a fresh job, move intake -> inspection (customer-visible), expect a notification.
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    wo = client.post("/api/work-orders", headers=staff_headers,
                     json={"customer_id": cid, "title": "Notify test"}).json()
    before = len(client.get("/api/notifications", headers=staff_headers).json())
    client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers,
                json={"status": "inspection", "message": "Started inspection", "visible_to_customer": True})
    notes = client.get("/api/notifications", headers=staff_headers).json()
    assert len(notes) == before + 1
    latest = notes[0]
    assert latest["work_order_id"] == wo["id"]
    assert latest["channel"] == "email"
    assert latest["status"] in ("sent", "queued")


def test_internal_status_change_creates_no_notification(client, staff_headers):
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    wo = client.post("/api/work-orders", headers=staff_headers,
                     json={"customer_id": cid, "title": "Silent test"}).json()
    before = len(client.get("/api/notifications", headers=staff_headers).json())
    client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers,
                json={"status": "inspection", "visible_to_customer": False})
    after = len(client.get("/api/notifications", headers=staff_headers).json())
    assert after == before  # internal-only change does not notify the customer


def test_upload_and_fetch_attachment(client, staff_headers, portal_headers):
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = next(w for w in wos if w["number"] == "WO-2026-0001")  # Acme's job
    files = {"file": ("test.txt", b"hello nameplate", "text/plain")}
    up = client.post(f"/api/work-orders/{wo['id']}/attachments", headers=staff_headers,
                     files=files, data={"kind": "document"})
    assert up.status_code == 201, up.text
    att = up.json()
    assert att["filename"] == "test.txt" and att["kind"] == "document"

    # Fetch the file back (staff)
    got = client.get(f"/api/attachments/{att['id']}/file", headers=staff_headers)
    assert got.status_code == 200 and got.content == b"hello nameplate"

    # Portal (Acme) can fetch its own work order's attachment
    assert client.get(f"/api/attachments/{att['id']}/file", headers=portal_headers).status_code == 200


def test_attachment_rejects_bad_kind(client, staff_headers):
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = wos[0]
    r = client.post(f"/api/work-orders/{wo['id']}/attachments", headers=staff_headers,
                    files={"file": ("x.txt", b"x", "text/plain")}, data={"kind": "malware"})
    assert r.status_code == 422


def test_log_time_and_costing(client, staff_headers):
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = next(w for w in wos if w["number"] == "WO-2026-0001")  # seeded with 14.5h + approved quote
    before = client.get(f"/api/work-orders/{wo['id']}/costing", headers=staff_headers).json()
    assert before["logged_hours"] >= 14.5
    assert before["labor_cost"] == round(before["logged_hours"] * before["labor_rate"], 2)
    assert before["estimate"] > 0

    logged = client.post(f"/api/work-orders/{wo['id']}/time-entries", headers=staff_headers,
                         json={"hours": 2.5, "note": "Testing"})
    assert logged.status_code == 201
    after = client.get(f"/api/work-orders/{wo['id']}/costing", headers=staff_headers).json()
    assert round(after["logged_hours"] - before["logged_hours"], 2) == 2.5


def test_log_time_rejects_zero_hours(client, staff_headers):
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = wos[0]
    r = client.post(f"/api/work-orders/{wo['id']}/time-entries", headers=staff_headers, json={"hours": 0})
    assert r.status_code == 422  # Pydantic gt=0 validation


def test_portal_invoices_scoped_and_pdf_access(client, staff_headers, portal_headers):
    invs = client.get("/api/portal/invoices", headers=portal_headers).json()
    assert any(i["number"] == "INV-2025-0031" for i in invs)  # Acme's paid invoice
    # Portal can download its own invoice PDF
    inv_id = invs[0]["id"]
    assert client.get(f"/api/invoices/{inv_id}/pdf", headers=portal_headers).status_code == 200
