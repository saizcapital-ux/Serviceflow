"""Preventive-maintenance plans: CRUD, due-state derivation, WO generation,
dashboard rollup, tenant scoping, and RBAC."""
from datetime import date, timedelta


def _headers(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "Password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _an_equipment_id(client, headers):
    """Pick any asset from the seeded org."""
    customers = client.get("/api/customers", headers=headers).json()
    for c in customers:
        eq = client.get(f"/api/equipment?customer_id={c['id']}", headers=headers).json()
        if eq:
            return eq[0]["id"], c["id"]
    raise AssertionError("No seeded equipment found")


def _delete(client, headers, plan_id):
    client.delete(f"/api/maintenance-plans/{plan_id}", headers=headers)


def test_plan_lifecycle_and_due_states(client, staff_headers):
    eq_id, _ = _an_equipment_id(client, staff_headers)

    # An overdue plan: last serviced well over the interval ago.
    overdue = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "Quarterly vibration + lube",
        "interval_days": 90, "service_type": "field_service", "priority": "high",
        "next_due_on": (date.today() - timedelta(days=5)).isoformat(),
    })
    assert overdue.status_code == 201, overdue.text
    o = overdue.json()
    assert o["state"] == "overdue"
    assert o["days_until_due"] == -5
    assert o["equipment_label"]  # denormalized context is populated

    # A due-soon plan (within 30 days).
    soon = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "Annual insulation megger",
        "interval_days": 365,
        "next_due_on": (date.today() + timedelta(days=10)).isoformat(),
    })
    assert soon.json()["state"] == "due_soon"

    # next_due_on derived from last_service_on + interval when omitted. A 120-day
    # interval lands well outside the 30-day "due soon" window, so state is "ok".
    derived = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "Belt inspection", "interval_days": 120,
        "last_service_on": date.today().isoformat(),
    })
    assert derived.json()["next_due_on"] == (date.today() + timedelta(days=120)).isoformat()
    assert derived.json()["state"] == "ok"

    # due=true returns the overdue + due-soon plans but not the far-future one.
    due = client.get("/api/maintenance-plans?due=true", headers=staff_headers).json()
    due_ids = {p["id"] for p in due}
    assert o["id"] in due_ids and soon.json()["id"] in due_ids
    assert derived.json()["id"] not in due_ids

    for p in (o, soon.json(), derived.json()):
        _delete(client, staff_headers, p["id"])


def test_generate_work_order_advances_schedule(client, staff_headers):
    eq_id, cust_id = _an_equipment_id(client, staff_headers)
    plan = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "Semiannual PM", "interval_days": 180,
        "service_type": "field_service",
        "next_due_on": date.today().isoformat(),
        "instructions": "Grease bearings; check alignment.",
    }).json()

    gen = client.post(f"/api/maintenance-plans/{plan['id']}/generate", headers=staff_headers)
    assert gen.status_code == 201, gen.text
    result = gen.json()
    assert result["work_order_number"].startswith("WO-")
    assert result["next_due_on"] == (date.today() + timedelta(days=180)).isoformat()

    # The generated WO carries the plan's context.
    wo = client.get(f"/api/work-orders/{result['work_order_id']}", headers=staff_headers).json()
    assert wo["equipment_id"] == eq_id
    assert wo["customer_id"] == cust_id
    assert wo["title"] == "Semiannual PM"
    assert wo["service_type"] == "field_service"
    assert "Grease bearings" in (wo["problem_description"] or "")

    # The plan's schedule moved forward.
    listed = client.get(f"/api/maintenance-plans?equipment_id={eq_id}", headers=staff_headers).json()
    moved = next(p for p in listed if p["id"] == plan["id"])
    assert moved["last_service_on"] == date.today().isoformat()
    assert moved["next_due_on"] == (date.today() + timedelta(days=180)).isoformat()

    _delete(client, staff_headers, plan["id"])


def test_dashboard_reports_overdue_and_due_soon(client, staff_headers):
    eq_id, _ = _an_equipment_id(client, staff_headers)
    overdue = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "Dash overdue probe", "interval_days": 30,
        "next_due_on": (date.today() - timedelta(days=2)).isoformat(),
    }).json()

    m = client.get("/api/dashboard", headers=staff_headers).json()["maintenance"]
    assert m["overdue"] >= 1
    assert any(p["id"] == overdue["id"] for p in m["upcoming"])

    _delete(client, staff_headers, overdue["id"])


def test_update_and_deactivate(client, staff_headers):
    eq_id, _ = _an_equipment_id(client, staff_headers)
    plan = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": eq_id, "name": "To edit", "interval_days": 60,
        "next_due_on": (date.today() - timedelta(days=1)).isoformat(),
    }).json()

    patched = client.patch(f"/api/maintenance-plans/{plan['id']}", headers=staff_headers,
                           json={"name": "Renamed PM", "is_active": False})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed PM"
    assert patched.json()["state"] == "inactive"

    # Inactive plans drop out of the default and due lists.
    active = client.get("/api/maintenance-plans", headers=staff_headers).json()
    assert all(p["id"] != plan["id"] for p in active)
    with_inactive = client.get("/api/maintenance-plans?include_inactive=true", headers=staff_headers).json()
    assert any(p["id"] == plan["id"] for p in with_inactive)

    _delete(client, staff_headers, plan["id"])


def test_create_rejects_foreign_equipment(client, staff_headers):
    # An equipment id that doesn't belong to this org → 404, not a leak.
    r = client.post("/api/maintenance-plans", headers=staff_headers, json={
        "equipment_id": 999999, "name": "Nope", "interval_days": 30,
    })
    assert r.status_code == 404


def test_requires_staff(client):
    portal = _headers(client, "buyer@acmepower.com")
    assert client.get("/api/maintenance-plans", headers=portal).status_code == 403
    assert client.post("/api/maintenance-plans", headers=portal,
                       json={"equipment_id": 1, "name": "x", "interval_days": 30}).status_code == 403
