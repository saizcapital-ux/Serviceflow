"""Accounts-receivable aging: which customers owe what, and how overdue it is.

Reads existing invoices — no schema change. An invoice counts as outstanding
when it has been issued (status = sent) but not yet paid or voided. Each is
aged from its due date (or issue date when no due date is set)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Customer, Invoice, InvoiceStatus, User
from app.schemas import ReceivablesCustomer, ReceivablesReport

router = APIRouter(prefix="/api/receivables", tags=["receivables"])


def _bucket(days_overdue: int) -> str:
    """Map days-past-due to an aging bucket key."""
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "d1_30"
    if days_overdue <= 60:
        return "d31_60"
    if days_overdue <= 90:
        return "d61_90"
    return "d90_plus"


_BUCKETS = ("current", "d1_30", "d31_60", "d61_90", "d90_plus")


def _build_report(db: Session, organization_id: int) -> ReceivablesReport:
    today = date.today()
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == organization_id,
            Invoice.status == InvoiceStatus.sent,
        )
    ).all()

    names = {
        c.id: c.name
        for c in db.scalars(
            select(Customer).where(Customer.organization_id == organization_id)
        ).all()
    }

    # Per-customer accumulator.
    per: dict[int, dict] = {}
    totals = {b: 0.0 for b in _BUCKETS}

    for inv in invoices:
        basis = inv.due_date or (inv.issued_at.date() if inv.issued_at else today)
        days_overdue = (today - basis).days
        bucket = _bucket(days_overdue)
        amount = round(inv.total or 0.0, 2)

        row = per.setdefault(inv.customer_id, {
            **{b: 0.0 for b in _BUCKETS},
            "open_count": 0, "oldest_days": 0,
        })
        row[bucket] += amount
        row["open_count"] += 1
        row["oldest_days"] = max(row["oldest_days"], max(days_overdue, 0))
        totals[bucket] += amount

    customers = []
    for cid, row in per.items():
        total = round(sum(row[b] for b in _BUCKETS), 2)
        customers.append(ReceivablesCustomer(
            customer_id=cid,
            customer_name=names.get(cid, f"Customer #{cid}"),
            total=total,
            current=round(row["current"], 2),
            d1_30=round(row["d1_30"], 2),
            d31_60=round(row["d31_60"], 2),
            d61_90=round(row["d61_90"], 2),
            d90_plus=round(row["d90_plus"], 2),
            open_count=row["open_count"],
            oldest_days=row["oldest_days"],
        ))
    # Worst offenders first: most overdue money at the top.
    customers.sort(key=lambda c: (c.d90_plus + c.d61_90 + c.d31_60, c.total), reverse=True)

    return ReceivablesReport(
        as_of=today,
        total_outstanding=round(sum(totals.values()), 2),
        current=round(totals["current"], 2),
        d1_30=round(totals["d1_30"], 2),
        d31_60=round(totals["d31_60"], 2),
        d61_90=round(totals["d61_90"], 2),
        d90_plus=round(totals["d90_plus"], 2),
        customers=customers,
    )


@router.get("", response_model=ReceivablesReport)
def receivables(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return _build_report(db, user.organization_id)


@router.get("/report.csv")
def receivables_csv(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    report = _build_report(db, user.organization_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Customer", "Current", "1-30", "31-60", "61-90", "90+", "Total", "Open invoices", "Oldest (days)"])
    for c in report.customers:
        w.writerow([c.customer_name, f"{c.current:.2f}", f"{c.d1_30:.2f}", f"{c.d31_60:.2f}",
                    f"{c.d61_90:.2f}", f"{c.d90_plus:.2f}", f"{c.total:.2f}", c.open_count, c.oldest_days])
    w.writerow(["TOTAL", f"{report.current:.2f}", f"{report.d1_30:.2f}", f"{report.d31_60:.2f}",
                f"{report.d61_90:.2f}", f"{report.d90_plus:.2f}", f"{report.total_outstanding:.2f}", "", ""])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="receivables-{report.as_of.isoformat()}.csv"'},
    )
