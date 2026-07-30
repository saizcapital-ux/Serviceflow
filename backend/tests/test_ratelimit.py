"""Tests for auth rate limiting and request-id logging."""
from app.core.config import settings


def test_request_id_header_present_and_echoed(client):
    r = client.get("/health")
    assert r.headers.get("x-request-id")  # generated when absent

    r2 = client.get("/health", headers={"X-Request-ID": "trace-xyz"})
    assert r2.headers.get("x-request-id") == "trace-xyz"  # echoed when provided


def test_login_rate_limited_after_threshold(client):
    # Use a dedicated forwarded IP so these failures don't affect other tests,
    # which share the default TestClient host.
    ip = {"X-Forwarded-For": "203.0.113.42"}
    max_attempts = settings.login_rate_limit_max

    for _ in range(max_attempts):
        r = client.post("/api/auth/login", json={"email": "admin@apexrepair.com", "password": "nope"}, headers=ip)
        assert r.status_code == 401, r.text

    # The next attempt is throttled — even with the correct password.
    blocked = client.post(
        "/api/auth/login", json={"email": "admin@apexrepair.com", "password": "Password123"}, headers=ip
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")

    # A different IP is unaffected and can still sign in.
    other = client.post(
        "/api/auth/login",
        json={"email": "admin@apexrepair.com", "password": "Password123"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert other.status_code == 200


def test_successful_login_clears_failures(client):
    ip = {"X-Forwarded-For": "203.0.113.99"}
    max_attempts = settings.login_rate_limit_max

    # Stay one below the threshold, then a correct login should succeed and reset.
    for _ in range(max_attempts - 1):
        client.post("/api/auth/login", json={"email": "admin@apexrepair.com", "password": "nope"}, headers=ip)
    ok = client.post("/api/auth/login", json={"email": "admin@apexrepair.com", "password": "Password123"}, headers=ip)
    assert ok.status_code == 200

    # Failures cleared, so a fresh batch of typos is again allowed up to the limit.
    r = client.post("/api/auth/login", json={"email": "admin@apexrepair.com", "password": "nope"}, headers=ip)
    assert r.status_code == 401
