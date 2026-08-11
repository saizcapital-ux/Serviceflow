"""Tests for the equipment spec-sheet PDF."""


def _motor_id(client, staff_headers):
    return next(e for e in client.get("/api/equipment", headers=staff_headers).json()
                if e["tag"] == "MTR-4471")["id"]


def test_spec_sheet_pdf_download(client, staff_headers):
    eid = _motor_id(client, staff_headers)
    r = client.get(f"/api/equipment/{eid}/spec-sheet.pdf", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 800
    assert "spec-" in r.headers.get("content-disposition", "")


def test_spec_sheet_missing_404(client, staff_headers):
    assert client.get("/api/equipment/999999/spec-sheet.pdf", headers=staff_headers).status_code == 404


def test_spec_sheet_requires_staff(client, portal_headers):
    assert client.get("/api/equipment/1/spec-sheet.pdf", headers=portal_headers).status_code == 403
