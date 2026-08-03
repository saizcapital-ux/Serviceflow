"""Tests for security headers and the global exception handler."""
from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    # HSTS is production-only; the test env is development, so it must be absent.
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


def test_headers_on_error_responses(client):
    # A 404 still carries the baseline headers.
    r = client.get("/api/work-orders/99999")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_unhandled_exception_returns_clean_json_500():
    @app.get("/api/_boom_test")
    def _boom():
        raise RuntimeError("kaboom")

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/_boom_test")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error."
    assert "request_id" in body
    assert "kaboom" not in r.text  # no stack trace / internal detail leaked
    assert r.headers.get("x-content-type-options") == "nosniff"
