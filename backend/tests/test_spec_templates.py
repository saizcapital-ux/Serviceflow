"""Tests for equipment spec templates."""


def test_seeded_defaults_present(client, staff_headers):
    motor = client.get("/api/spec-templates?equipment_type=motor", headers=staff_headers).json()
    labels = [f["label"] for f in motor]
    assert "Horsepower" in labels and "RPM" in labels
    assert all(f["equipment_type"] == "motor" for f in motor)
    # Ordered by position.
    positions = [f["position"] for f in motor]
    assert positions == sorted(positions)


def test_manager_crud_and_technician_read_only(client, staff_headers):
    # Owner creates a field.
    created = client.post("/api/spec-templates",
                          json={"equipment_type": "gearbox", "label": "Ratio", "unit": ":1"},
                          headers=staff_headers)
    assert created.status_code == 201
    fid = created.json()["id"]
    assert created.json()["equipment_type"] == "gearbox"

    # Update + delete.
    upd = client.patch(f"/api/spec-templates/{fid}", json={"label": "Gear Ratio"}, headers=staff_headers)
    assert upd.status_code == 200 and upd.json()["label"] == "Gear Ratio"
    assert client.delete(f"/api/spec-templates/{fid}", headers=staff_headers).status_code == 204
    assert client.patch(f"/api/spec-templates/{fid}", json={"label": "x"}, headers=staff_headers).status_code == 404


def test_technician_cannot_manage(client):
    r = client.post("/api/auth/login", json={"email": "tech@apexrepair.com", "password": "Password123"})
    th = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/spec-templates", headers=th).status_code == 200  # read allowed
    assert client.post("/api/spec-templates", json={"equipment_type": "motor", "label": "X"},
                       headers=th).status_code == 403


def test_invalid_equipment_type_rejected(client, staff_headers):
    assert client.post("/api/spec-templates", json={"equipment_type": "spaceship", "label": "X"},
                       headers=staff_headers).status_code == 422


def test_spec_fields_are_tenant_scoped(client, staff_headers):
    # A brand-new tenant sees no spec fields (they belong to the seed org only).
    import uuid
    tok = client.post("/api/auth/signup", json={
        "organization_name": "Spec Isolation Shop", "full_name": "Iso",
        "email": f"iso-{uuid.uuid4().hex[:8]}@shop.com", "password": "Secret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/spec-templates", headers=h).json() == []


def _make_motor(client, staff_headers, tag, nameplate):
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]
    return client.post("/api/equipment", json={
        "customer_id": cid, "equipment_type": "motor", "tag": tag, "nameplate_data": nameplate,
    }, headers=staff_headers)


def test_spec_report_columns_and_rows(client, staff_headers):
    _make_motor(client, staff_headers, "RPT-1", {"Horsepower": "250", "RPM": "1780"})
    rep = client.get("/api/spec-templates/report?equipment_type=motor", headers=staff_headers)
    assert rep.status_code == 200
    body = rep.json()
    assert "Horsepower" in body["fields"]
    row = next(e for e in body["equipment"] if e["tag"] == "RPT-1")
    assert row["specs"]["Horsepower"] == "250"
    # Every row exposes exactly the template fields (missing values blank).
    assert set(row["specs"].keys()) == set(body["fields"])


def test_spec_report_csv(client, staff_headers):
    _make_motor(client, staff_headers, "RPT-CSV", {"Horsepower": "60"})
    r = client.get("/api/spec-templates/report.csv?equipment_type=motor", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("Tag,Customer,Manufacturer,Model,Serial,Horsepower")
    assert any(line.startswith("RPT-CSV,") for line in lines)


def test_spec_report_requires_valid_type(client, staff_headers):
    assert client.get("/api/spec-templates/report?equipment_type=spaceship", headers=staff_headers).status_code == 422
