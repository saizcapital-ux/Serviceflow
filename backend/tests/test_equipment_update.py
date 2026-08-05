"""Tests for editing existing equipment (incl. specs)."""


def _make_eq(client, staff_headers):
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    return client.post("/api/equipment", json={
        "customer_id": cid, "equipment_type": "motor", "tag": "UPD-1",
        "nameplate_data": {"Horsepower": "100", "Legacy": "keep-me"},
    }, headers=staff_headers).json()


def test_update_fields_and_specs(client, staff_headers):
    eq = _make_eq(client, staff_headers)
    r = client.patch(f"/api/equipment/{eq['id']}", json={
        "manufacturer": "Baldor",
        "nameplate_data": {"Horsepower": "150", "RPM": "1780"},
    }, headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["manufacturer"] == "Baldor"
    assert body["nameplate_data"] == {"Horsepower": "150", "RPM": "1780"}


def test_partial_update_leaves_other_fields(client, staff_headers):
    eq = _make_eq(client, staff_headers)
    r = client.patch(f"/api/equipment/{eq['id']}", json={"tag": "UPD-RENAMED"}, headers=staff_headers)
    assert r.status_code == 200
    assert r.json()["tag"] == "UPD-RENAMED"
    assert r.json()["manufacturer"] == eq["manufacturer"]  # untouched


def test_update_missing_equipment_404(client, staff_headers):
    assert client.patch("/api/equipment/999999", json={"tag": "x"}, headers=staff_headers).status_code == 404


def test_update_requires_staff(client, portal_headers):
    assert client.patch("/api/equipment/1", json={"tag": "x"}, headers=portal_headers).status_code == 403
