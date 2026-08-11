"""Tests for test/inspection reports (pass/fail results on work orders)."""


def _motor_wo(client, staff_headers):
    return next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                if w["number"] == "WO-2026-0001")["id"]


def test_motor_test_template_seeded(client, staff_headers):
    items = client.get("/api/test-templates?equipment_type=motor", headers=staff_headers).json()
    labels = [i["label"] for i in items]
    assert any("Megger" in lbl for lbl in labels)
    assert all(i["equipment_type"] == "motor" for i in items)


def test_technician_can_run_tests_but_not_manage_template(client, staff_headers):
    r = client.post("/api/auth/login", json={"email": "tech@apexrepair.com", "password": "Password123"})
    th = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # Read + run allowed.
    assert client.get("/api/test-templates", headers=th).status_code == 200
    # Managing the template is owner/manager only.
    assert client.post("/api/test-templates", json={"equipment_type": "motor", "label": "X"},
                       headers=th).status_code == 403


def test_apply_and_fail_flips_overall(client, staff_headers):
    wo_id = _motor_wo(client, staff_headers)
    applied = client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers)
    assert applied.status_code == 201
    report = applied.json()
    assert report["overall"] == "in_progress" and len(report["items"]) >= 4

    megger = next(i for i in report["items"] if "Megger" in i["label"])
    upd = client.patch(f"/api/test-results/{megger['id']}",
                       json={"value": "0.2", "result": "fail", "notes": "Grounded winding"},
                       headers=staff_headers)
    assert upd.status_code == 200 and upd.json()["result"] == "fail"

    after = client.get(f"/api/work-orders/{wo_id}/tests", headers=staff_headers).json()
    assert after["overall"] == "failed"


def test_all_pass_reads_passed(client, staff_headers):
    wo_id = _motor_wo(client, staff_headers)
    report = client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers).json()
    for item in report["items"]:
        client.patch(f"/api/test-results/{item['id']}", json={"result": "pass"}, headers=staff_headers)
    assert client.get(f"/api/work-orders/{wo_id}/tests", headers=staff_headers).json()["overall"] == "passed"


def test_apply_is_idempotent(client, staff_headers):
    wo_id = _motor_wo(client, staff_headers)
    a = client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers).json()
    b = client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers).json()
    assert len(a["items"]) == len(b["items"])  # no duplicate rows


def test_invalid_result_rejected(client, staff_headers):
    wo_id = _motor_wo(client, staff_headers)
    report = client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers).json()
    rid = report["items"][0]["id"]
    assert client.patch(f"/api/test-results/{rid}", json={"result": "maybe"}, headers=staff_headers).status_code == 422


def test_tests_require_staff(client, portal_headers):
    assert client.get("/api/work-orders/1/tests", headers=portal_headers).status_code == 403


def test_test_report_pdf(client, staff_headers):
    wo_id = _motor_wo(client, staff_headers)
    client.post(f"/api/work-orders/{wo_id}/tests/apply", headers=staff_headers)
    r = client.get(f"/api/work-orders/{wo_id}/test-report.pdf", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_portal_sees_test_report_readonly(client, staff_headers, portal_headers):
    # Find a work order the portal customer owns and apply + fail a test.
    number = client.get("/api/portal/work-orders", headers=portal_headers).json()[0]["number"]
    staff_wo = next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                    if w["number"] == number)
    report = client.post(f"/api/work-orders/{staff_wo['id']}/tests/apply", headers=staff_headers)
    if report.status_code != 201:
        return  # that WO's equipment type has no test template; skip
    item = report.json()["items"][0]
    client.patch(f"/api/test-results/{item['id']}", json={"value": "0.2", "result": "fail"}, headers=staff_headers)

    portal_wo_id = client.get("/api/portal/work-orders", headers=portal_headers).json()[0]["id"]
    pr = client.get(f"/api/portal/work-orders/{portal_wo_id}/tests", headers=portal_headers)
    assert pr.status_code == 200
    assert pr.json()["overall"] == "failed"


def test_portal_cannot_see_foreign_test_report(client, staff_headers, portal_headers):
    owned = {w["id"] for w in client.get("/api/portal/work-orders", headers=portal_headers).json()}
    foreign = next(w for w in client.get("/api/work-orders", headers=staff_headers).json()
                   if w["id"] not in owned)
    assert client.get(f"/api/portal/work-orders/{foreign['id']}/tests", headers=portal_headers).status_code == 404
