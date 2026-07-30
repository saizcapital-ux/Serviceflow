"""Tests for first-pass-yield analytics."""


def test_first_pass_yield_in_summary(client, staff_headers):
    r = client.get("/api/analytics/summary", headers=staff_headers)
    assert r.status_code == 200
    body = r.json()

    # Keys are present in the summary payload.
    for key in ("first_pass_yield_pct", "jobs_tested", "jobs_reworked"):
        assert key in body

    # The seed tests two jobs and reworks one (WO-2026-0004 fails its first
    # test: testing → in_repair → testing → ready), so yield is 50%.
    assert body["jobs_tested"] == 2
    assert body["jobs_reworked"] == 1
    assert body["first_pass_yield_pct"] == 50.0


def test_fpy_null_safe_when_nothing_tested(client, portal_headers):
    """Analytics is staff-only; a portal user must not reach it (guards the
    division-by-zero path from ever being publicly hit)."""
    assert client.get("/api/analytics/summary", headers=portal_headers).status_code == 403
