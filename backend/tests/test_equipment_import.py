"""Tests for bulk equipment CSV import."""


def _customer_name(client, staff_headers):
    return client.get("/api/customers", headers=staff_headers).json()[0]["name"]


def test_import_template_has_spec_columns(client, staff_headers):
    r = client.get("/api/spec-templates/import-template.csv?equipment_type=motor", headers=staff_headers)
    assert r.status_code == 200
    header = r.text.strip().splitlines()[0]
    assert header.startswith("Customer,Tag,Manufacturer,Model,Serial,")
    assert "Horsepower" in header


def test_import_creates_equipment_with_specs(client, staff_headers):
    cust = _customer_name(client, staff_headers)
    csv = (
        "Customer,Tag,Manufacturer,Model,Serial,Horsepower,RPM\n"
        f"{cust},IMPT-1,GE,5KS,SN-A,300,3600\n"
        f"{cust},IMPT-2,WEG,W22,SN-B,75,1800\n"
    )
    r = client.post("/api/spec-templates/import", data={"equipment_type": "motor"},
                    files={"file": ("assets.csv", csv, "text/csv")}, headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2 and body["errors"] == []

    report = client.get("/api/spec-templates/report?equipment_type=motor", headers=staff_headers).json()
    row = next(e for e in report["equipment"] if e["tag"] == "IMPT-1")
    assert row["specs"]["Horsepower"] == "300" and row["customer"] == cust


def test_import_reports_row_errors(client, staff_headers):
    cust = _customer_name(client, staff_headers)
    csv = (
        "Customer,Tag,Horsepower\n"
        f"{cust},OK-ROW,50\n"
        "Ghost Customer,BAD-ROW,10\n"
        ",NO-CUST,20\n"
    )
    r = client.post("/api/spec-templates/import", data={"equipment_type": "motor"},
                    files={"file": ("assets.csv", csv, "text/csv")}, headers=staff_headers)
    body = r.json()
    assert body["created"] == 1
    msgs = " ".join(e["error"] for e in body["errors"])
    assert "not found" in msgs and "Missing Customer" in msgs
    rows = [e["row"] for e in body["errors"]]
    assert 3 in rows and 4 in rows  # 1-based incl. header


def test_import_requires_customer_column(client, staff_headers):
    csv = "Tag,Horsepower\nX,10\n"
    r = client.post("/api/spec-templates/import", data={"equipment_type": "motor"},
                    files={"file": ("assets.csv", csv, "text/csv")}, headers=staff_headers)
    assert r.status_code == 400


def test_import_requires_staff(client, portal_headers):
    csv = "Customer,Tag\nX,Y\n"
    r = client.post("/api/spec-templates/import", data={"equipment_type": "motor"},
                    files={"file": ("assets.csv", csv, "text/csv")}, headers=portal_headers)
    assert r.status_code == 403
