"""Test the assigned_to filter on the work-order list."""


def test_filter_by_assigned_to(client, staff_headers):
    users = client.get("/api/users", headers=staff_headers).json()
    tech = next(u for u in users if u["role"] == "technician")
    cid = client.get("/api/customers", headers=staff_headers).json()[0]["id"]

    made = client.post("/api/work-orders", json={
        "customer_id": cid, "title": "Filter target", "priority": "normal",
        "service_type": "shop_repair", "problem_description": "x", "assigned_to": tech["id"],
    }, headers=staff_headers).json()

    mine = client.get(f"/api/work-orders?assigned_to={tech['id']}", headers=staff_headers)
    assert mine.status_code == 200
    ids = {w["id"] for w in mine.json()}
    assert made["id"] in ids
    assert all(w["assigned_to"] == tech["id"] for w in mine.json())

    # A different, unassigned user's filter must not include it.
    other = next(u for u in users if u["id"] != tech["id"])
    others = client.get(f"/api/work-orders?assigned_to={other['id']}", headers=staff_headers).json()
    assert made["id"] not in {w["id"] for w in others}
