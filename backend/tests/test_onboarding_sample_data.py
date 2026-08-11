"""One-click sample-data loader: lifecycle, idempotency, and RBAC."""


def _headers(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "Password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cleanup(client, headers):
    # Best-effort removal so the shared seeded DB is left as we found it.
    client.delete("/api/onboarding/sample-data", headers=headers)


def test_sample_data_lifecycle(client, staff_headers):
    _cleanup(client, staff_headers)

    r = client.post("/api/onboarding/sample-data", headers=staff_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["customer_id"] and body["equipment_id"] and body["work_order_id"]
    assert body["work_order_number"]

    # The demo records are really there and reachable through the normal APIs.
    customers = client.get("/api/customers", headers=staff_headers).json()
    assert any(c["account_number"] == "SAMPLE-DEMO" for c in customers)
    wo = client.get(f"/api/work-orders/{body['work_order_id']}", headers=staff_headers)
    assert wo.status_code == 200
    assert wo.json()["equipment_id"] == body["equipment_id"]

    # The dashboard advertises that sample data is present.
    assert client.get("/api/dashboard", headers=staff_headers).json()["setup"]["has_sample"] is True

    # Loading again is refused rather than duplicating.
    assert client.post("/api/onboarding/sample-data", headers=staff_headers).status_code == 409

    # Removal cleans up the customer and everything scoped to it.
    assert client.delete("/api/onboarding/sample-data", headers=staff_headers).status_code == 200
    customers = client.get("/api/customers", headers=staff_headers).json()
    assert not any(c["account_number"] == "SAMPLE-DEMO" for c in customers)
    # WO is gone with it.
    assert client.get(f"/api/work-orders/{body['work_order_id']}", headers=staff_headers).status_code == 404
    # Nothing left to remove.
    assert client.delete("/api/onboarding/sample-data", headers=staff_headers).status_code == 404
    assert client.get("/api/dashboard", headers=staff_headers).json()["setup"]["has_sample"] is False


def test_sample_data_requires_owner_or_manager(client):
    tech = _headers(client, "tech@apexrepair.com")
    writer = _headers(client, "writer@apexrepair.com")
    assert client.post("/api/onboarding/sample-data", headers=tech).status_code == 403
    assert client.delete("/api/onboarding/sample-data", headers=tech).status_code == 403
    assert client.post("/api/onboarding/sample-data", headers=writer).status_code == 403
