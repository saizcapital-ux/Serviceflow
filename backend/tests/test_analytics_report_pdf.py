"""Tests for the analytics PDF report endpoint."""


def test_report_pdf_download(client, staff_headers):
    r = client.get("/api/analytics/report.pdf", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 1000
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".pdf" in r.headers.get("content-disposition", "")


def test_report_pdf_is_staff_only(client, portal_headers):
    assert client.get("/api/analytics/report.pdf", headers=portal_headers).status_code == 403


def test_report_pdf_requires_auth(client):
    assert client.get("/api/analytics/report.pdf").status_code == 401
