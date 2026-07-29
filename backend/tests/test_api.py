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


def test_po_number_set_and_approval_limit(client, staff_headers, portal_headers):
    # Acme has an approval_limit of 2000 in the seed. Build a fresh over-limit quote.
    acme = next(c for c in client.get("/api/customers", headers=staff_headers).json()
                if c["account_number"] == "ACME-001")
    assert acme["approval_limit"] == 2000.0
    wo = client.post("/api/work-orders", headers=staff_headers,
                     json={"customer_id": acme["id"], "title": "PO limit test"}).json()
    client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers, json={"status": "inspection"})
    quote = client.post(f"/api/work-orders/{wo['id']}/quotes", headers=staff_headers,
                        json={"lines": [{"kind": "labor", "description": "Big job", "quantity": 1,
                                         "unit_price": 5000}], "tax_rate": 0}).json()
    assert quote["total"] > 2000.0  # exceeds Acme's approval limit

    # Portal approves with a PO number; it should land on the work order.
    r = client.post(f"/api/portal/quotes/{quote['id']}/decision", headers=portal_headers,
                    json={"approve": True, "po_number": "PO-99887"})
    assert r.status_code == 200
    after = client.get(f"/api/work-orders/{wo['id']}", headers=staff_headers).json()
    assert after["po_number"] == "PO-99887"


def test_staff_can_set_po_number(client, staff_headers):
    wo = client.get("/api/work-orders", headers=staff_headers).json()[0]
    r = client.patch(f"/api/work-orders/{wo['id']}", headers=staff_headers, json={"po_number": "PO-STAFF-1"})
    assert r.status_code == 200 and r.json()["po_number"] == "PO-STAFF-1"


def test_checklist_apply_and_toggle(client, staff_headers):
    templates = client.get("/api/checklist-templates", headers=staff_headers).json()
    assert templates, "seed should include traveler templates"
    tmpl = next(t for t in templates if t["equipment_type"] == "pump")
    # Apply to a fresh job
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    wo = client.post("/api/work-orders", headers=staff_headers,
                     json={"customer_id": cid, "title": "Checklist test"}).json()
    detail = client.post(f"/api/work-orders/{wo['id']}/checklist/apply", headers=staff_headers,
                         json={"template_id": tmpl["id"]}).json()
    items = detail["checklist_items"]
    assert len(items) == len(tmpl["items"])
    assert all(not it["is_done"] for it in items)

    # Toggle the first item done
    r = client.patch(f"/api/checklist-items/{items[0]['id']}", headers=staff_headers, json={"is_done": True})
    assert r.status_code == 200 and r.json()["is_done"] is True


def test_seeded_motor_job_has_checklist(client, staff_headers):
    wos = client.get("/api/work-orders", headers=staff_headers).json()
    wo = next(w for w in wos if w["number"] == "WO-2026-0001")
    detail = client.get(f"/api/work-orders/{wo['id']}", headers=staff_headers).json()
    items = detail["checklist_items"]
    assert len(items) == 9  # motor rewind traveler
    assert sum(1 for it in items if it["is_done"]) == 5


def test_equipment_qr_svg(client, staff_headers):
    eq = client.get("/api/equipment", headers=staff_headers).json()[0]
    r = client.get(f"/api/equipment/{eq['id']}/qr.svg", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.startswith("<svg") and "rect" in r.text


def test_workorders_filter_by_equipment(client, staff_headers):
    eq = client.get("/api/equipment", headers=staff_headers).json()
    motor = next(e for e in eq if e["serial_number"] == "SN-MTR-88213")
    wos = client.get(f"/api/work-orders?equipment_id={motor['id']}", headers=staff_headers).json()
    assert wos and all(w["equipment_id"] == motor["id"] for w in wos)


def test_parts_catalog_and_low_stock(client, staff_headers):
    parts = client.get("/api/parts", headers=staff_headers).json()
    assert parts, "seed should include parts"
    low = client.get("/api/parts?low_stock=true", headers=staff_headers).json()
    # BRG-6314N (6 on hand, reorder 8) and SEAL-KIT-3196 (3/4) are below reorder
    low_skus = {p["sku"] for p in low}
    assert "BRG-6314N" in low_skus and "SEAL-KIT-3196" in low_skus


def test_create_part_duplicate_sku_rejected(client, staff_headers):
    body = {"sku": "TST-UNIQUE", "name": "Test part", "quantity_on_hand": 5, "reorder_point": 2}
    assert client.post("/api/parts", headers=staff_headers, json=body).status_code == 201
    assert client.post("/api/parts", headers=staff_headers, json=body).status_code == 409


def test_consume_part_decrements_stock(client, staff_headers):
    part = client.post("/api/parts", headers=staff_headers,
                       json={"sku": "CONS-1", "name": "Consumable", "quantity_on_hand": 5,
                             "unit_price": 10.0}).json()
    wo = client.get("/api/work-orders", headers=staff_headers).json()[0]
    r = client.post(f"/api/work-orders/{wo['id']}/parts", headers=staff_headers,
                    json={"part_id": part["id"], "quantity": 3})
    assert r.status_code == 201
    after = client.get("/api/parts?q=CONS-1", headers=staff_headers).json()[0]
    assert after["quantity_on_hand"] == 2
    # Over-consume is rejected
    bad = client.post(f"/api/work-orders/{wo['id']}/parts", headers=staff_headers,
                      json={"part_id": part["id"], "quantity": 99})
    assert bad.status_code == 409


def test_locations_and_filtering(client, staff_headers):
    locs = client.get("/api/locations", headers=staff_headers).json()
    codes = {l["code"] for l in locs}
    assert {"HOU", "BMT"} <= codes
    hou = next(l for l in locs if l["code"] == "HOU")

    # Work orders filter by location
    hou_wos = client.get(f"/api/work-orders?location_id={hou['id']}", headers=staff_headers).json()
    assert hou_wos and all(w["location_id"] == hou["id"] for w in hou_wos)

    # Dashboard accepts a location filter
    d = client.get(f"/api/dashboard?location_id={hou['id']}", headers=staff_headers).json()
    assert "open_work_orders" in d

    # Equipment filters by location too
    eq = client.get(f"/api/equipment?location_id={hou['id']}", headers=staff_headers).json()
    assert eq and all(e["location_id"] == hou["id"] for e in eq)


def test_create_location_manager_only_and_unique_code(client, staff_headers):
    # Owner can create
    r = client.post("/api/locations", headers=staff_headers, json={"name": "Dallas Branch", "code": "DAL"})
    assert r.status_code == 201
    # Duplicate code rejected
    assert client.post("/api/locations", headers=staff_headers, json={"name": "Dup", "code": "DAL"}).status_code == 409
    # A technician cannot create locations
    tok = client.post("/api/auth/login", json={"email": "tech@apexrepair.com", "password": "Password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/locations", headers=h, json={"name": "X", "code": "X1"}).status_code == 403


def test_api_key_auth_flow(client, staff_headers):
    created = client.post("/api/developer/api-keys", headers=staff_headers, json={"name": "Test integration"})
    assert created.status_code == 201
    body = created.json()
    full = body["key"]
    assert full.startswith("sf_") and body["prefix"] in full

    # The full key is not returned by the list endpoint (only prefix)
    listed = client.get("/api/developer/api-keys", headers=staff_headers).json()
    assert all("key" not in k for k in listed)

    # Use the key against the v1 integration API
    ok = client.get("/api/v1/work-orders", headers={"X-API-Key": full})
    assert ok.status_code == 200 and isinstance(ok.json(), list)

    # A bad key is rejected; a missing key is rejected
    assert client.get("/api/v1/work-orders", headers={"X-API-Key": "sf_bogus"}).status_code == 401
    assert client.get("/api/v1/work-orders").status_code == 401

    # Revoke → the key stops working
    client.delete(f"/api/developer/api-keys/{body['id']}", headers=staff_headers)
    assert client.get("/api/v1/work-orders", headers={"X-API-Key": full}).status_code == 401


def test_api_keys_owner_only(client):
    tok = client.post("/api/auth/login", json={"email": "writer@apexrepair.com", "password": "Password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/developer/api-keys", headers=h).status_code == 403


def test_webhook_delivery_recorded(client, staff_headers):
    # Point at a closed port so delivery fails fast and is recorded.
    hook = client.post("/api/developer/webhooks", headers=staff_headers,
                       json={"url": "http://127.0.0.1:9/hook", "events": ["*"]}).json()
    # Explicit test-fire records a delivery
    d = client.post(f"/api/developer/webhooks/{hook['id']}/test", headers=staff_headers).json()
    assert d["success"] is False and d["error"]

    # A real event (status change) also dispatches + records a delivery
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    wo = client.post("/api/work-orders", headers=staff_headers, json={"customer_id": cid, "title": "Hook test"}).json()
    client.post(f"/api/work-orders/{wo['id']}/status", headers=staff_headers, json={"status": "inspection"})
    deliveries = client.get(f"/api/developer/webhooks/{hook['id']}/deliveries", headers=staff_headers).json()
    assert any(dl["event"] == "work_order.status_changed" for dl in deliveries)

    # Clean up so the webhook doesn't affect other tests' status changes
    client.delete(f"/api/developer/webhooks/{hook['id']}", headers=staff_headers)


def test_audit_log_records_actions(client, staff_headers):
    # Login (staff_headers fixture) + creating a WO should both be audited.
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    client.post("/api/work-orders", headers=staff_headers, json={"customer_id": cid, "title": "Audit WO"})
    entries = client.get("/api/audit", headers=staff_headers).json()
    actions = {e["action"] for e in entries}
    assert "user.login" in actions
    assert "work_order.created" in actions
    # Filter works
    created = client.get("/api/audit?action=work_order.created", headers=staff_headers).json()
    assert created and all(e["action"] == "work_order.created" for e in created)


def test_audit_log_owner_manager_only(client):
    tok = client.post("/api/auth/login", json={"email": "tech@apexrepair.com", "password": "Password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/audit", headers=h).status_code == 403  # technician blocked


def test_global_search(client, staff_headers):
    # By work order number
    r = client.get("/api/search?q=WO-2026-0001", headers=staff_headers).json()
    assert any(x["type"] == "work_order" and x["label"] == "WO-2026-0001" for x in r["results"])
    # By customer name
    r = client.get("/api/search?q=Acme", headers=staff_headers).json()
    assert any(x["type"] == "customer" for x in r["results"])
    # By equipment serial
    r = client.get("/api/search?q=SN-MTR", headers=staff_headers).json()
    assert any(x["type"] == "equipment" for x in r["results"])
    # Every result carries a route
    assert all("route" in x for x in r["results"])


def test_search_requires_query_and_staff(client, staff_headers, portal_headers):
    assert client.get("/api/search", headers=staff_headers).status_code == 422  # q required
    assert client.get("/api/search?q=x", headers=portal_headers).status_code == 403


def test_create_customer_contact_and_equipment(client, staff_headers):
    # Create a customer
    cust = client.post("/api/customers", headers=staff_headers,
                       json={"name": "New Co", "account_number": "NEWCO-9"}).json()
    assert cust["id"]
    # Add a contact
    ct = client.post(f"/api/customers/{cust['id']}/contacts", headers=staff_headers,
                     json={"name": "Jane Doe", "title": "Planner", "email": "jane@newco.com"})
    assert ct.status_code == 201 and ct.json()["name"] == "Jane Doe"
    # It appears on the customer detail
    detail = client.get(f"/api/customers/{cust['id']}", headers=staff_headers).json()
    assert any(c["name"] == "Jane Doe" for c in detail["contacts"])
    # Add equipment for the customer
    eq = client.post("/api/equipment", headers=staff_headers,
                     json={"customer_id": cust["id"], "equipment_type": "pump", "tag": "PMP-NEW"})
    assert eq.status_code == 201 and eq.json()["tag"] == "PMP-NEW"


def test_add_contact_missing_customer_404(client, staff_headers):
    r = client.post("/api/customers/999999/contacts", headers=staff_headers, json={"name": "X"})
    assert r.status_code == 404


def test_asset_reliability(client, staff_headers):
    rows = client.get("/api/analytics/reliability", headers=staff_headers).json()
    assert isinstance(rows, list) and rows
    # The seeded motor (MTR-4471) has 2 work orders → MTBR computed
    motor = next((r for r in rows if r["tag"] == "MTR-4471"), None)
    assert motor is not None
    assert motor["repairs_total"] >= 2
    assert motor["mtbr_days"] is not None  # 2+ repairs -> interval known
    assert set(rows[0]) >= {"equipment_id", "repairs_12mo", "watch", "last_repair"}


def test_reliability_requires_staff(client, portal_headers):
    assert client.get("/api/analytics/reliability", headers=portal_headers).status_code == 403


def test_dashboard_sla_counts(client, staff_headers):
    d = client.get("/api/dashboard", headers=staff_headers).json()
    assert "overdue_open" in d and "due_soon_open" in d
    # WO-2026-0002 is seeded with a promised date 3 days in the past (overdue, open)
    assert d["overdue_open"] >= 1
    # WO-2026-0003/0004 are promised within a few days (due soon)
    assert d["due_soon_open"] >= 1


def test_analytics_on_time_pct(client, staff_headers):
    a = client.get("/api/analytics/summary", headers=staff_headers).json()
    assert "on_time_pct" in a
    # The one completed job (WO-2025-0288) was delivered before its promised date
    assert a["on_time_pct"] == 100.0


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
