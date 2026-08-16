"""Accounts-receivable aging: bucket math, per-customer rollup, status
filtering, CSV export, and RBAC."""
from datetime import date, timedelta

from app.api.routers.receivables import _bucket
from app.core.database import SessionLocal
from app.models import Customer, Invoice, InvoiceStatus, WorkOrder


def _headers(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "Password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_bucket_boundaries():
    assert _bucket(-5) == "current"
    assert _bucket(0) == "current"
    assert _bucket(1) == "d1_30"
    assert _bucket(30) == "d1_30"
    assert _bucket(31) == "d31_60"
    assert _bucket(60) == "d31_60"
    assert _bucket(61) == "d61_90"
    assert _bucket(90) == "d61_90"
    assert _bucket(91) == "d90_plus"


def _seed_invoices(entries):
    """Insert invoices directly with explicit due dates + status. Returns
    (organization_id, customer_id, [invoice_ids]) and a cleanup callable."""
    db = SessionLocal()
    try:
        wo = db.query(WorkOrder).first()
        org_id, cust_id = wo.organization_id, wo.customer_id
        # A unique number prefix so we can find/clean our rows.
        base = db.query(Invoice).count() + 1000
        ids = []
        for i, (days_overdue, total, status) in enumerate(entries):
            inv = Invoice(
                organization_id=org_id, number=f"TEST-AR-{base + i}",
                work_order_id=wo.id, customer_id=cust_id, status=status,
                subtotal=total, tax=0.0, total=total,
                due_date=date.today() - timedelta(days=days_overdue),
            )
            db.add(inv)
            db.flush()
            ids.append(inv.id)
        db.commit()
    finally:
        db.close()

    def cleanup():
        d = SessionLocal()
        try:
            for iid in ids:
                obj = d.get(Invoice, iid)
                if obj:
                    d.delete(obj)
            d.commit()
        finally:
            d.close()

    return org_id, cust_id, ids, cleanup


def test_aging_rollup_and_status_filter(client, staff_headers):
    # current, 1-30, 31-60, 61-90, 90+, plus a paid one that must be ignored.
    _org, cust_id, _ids, cleanup = _seed_invoices([
        (-3, 100.0, InvoiceStatus.sent),   # current
        (10, 200.0, InvoiceStatus.sent),   # 1-30
        (45, 400.0, InvoiceStatus.sent),   # 31-60
        (75, 800.0, InvoiceStatus.sent),   # 61-90
        (120, 1600.0, InvoiceStatus.sent), # 90+
        (200, 9999.0, InvoiceStatus.paid), # ignored (paid)
        (5, 5000.0, InvoiceStatus.draft),  # ignored (not issued)
    ])
    try:
        rep = client.get("/api/receivables", headers=staff_headers)
        assert rep.status_code == 200, rep.text
        r = rep.json()
        # Our seeded outstanding total is 3100; the seed DB may hold other
        # invoices, so assert our amounts are *included*, not exact equality.
        assert r["total_outstanding"] >= 3100.0
        assert r["current"] >= 100.0
        assert r["d1_30"] >= 200.0
        assert r["d31_60"] >= 400.0
        assert r["d61_90"] >= 800.0
        assert r["d90_plus"] >= 1600.0
        # The paid/draft invoices are excluded from the book entirely.
        assert r["total_outstanding"] < 9999.0 + 5000.0

        me = next(c for c in r["customers"] if c["customer_id"] == cust_id)
        assert me["current"] >= 100.0 and me["d90_plus"] >= 1600.0
        assert me["oldest_days"] >= 120
        assert me["open_count"] >= 5
    finally:
        cleanup()


def test_paying_removes_from_book(client, staff_headers):
    _org, cust_id, ids, cleanup = _seed_invoices([(50, 750.0, InvoiceStatus.sent)])
    try:
        before = client.get("/api/receivables", headers=staff_headers).json()["total_outstanding"]
        # Mark it paid through the real endpoint.
        assert client.post(f"/api/invoices/{ids[0]}/paid", headers=staff_headers,
                           json={"paid": True}).status_code == 200
        after = client.get("/api/receivables", headers=staff_headers).json()["total_outstanding"]
        assert round(before - after, 2) == 750.0
    finally:
        cleanup()


def test_csv_export(client, staff_headers):
    _org, _cust, _ids, cleanup = _seed_invoices([(40, 321.0, InvoiceStatus.sent)])
    try:
        r = client.get("/api/receivables/report.csv", headers=staff_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        body = r.text
        assert "Customer" in body and "TOTAL" in body and "321.00" in body
    finally:
        cleanup()


def test_requires_staff(client):
    portal = _headers(client, "buyer@acmepower.com")
    assert client.get("/api/receivables", headers=portal).status_code == 403
