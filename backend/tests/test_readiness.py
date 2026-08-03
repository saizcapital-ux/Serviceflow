"""Test the readiness endpoint."""


def test_ready_reports_database_ok(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "database": "ok"}


def test_health_is_liveness_only(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
