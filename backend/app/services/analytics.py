"""Reporting aggregations. Computed in Python for DB portability."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Invoice,
    InvoiceStatus,
    TimeEntry,
    User,
    WorkOrder,
    WorkOrderStatus,
)

CLOSED_STATES = {WorkOrderStatus.closed, WorkOrderStatus.shipped}


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC for arithmetic."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def summary(db: Session, organization_id: int) -> dict:
    now = datetime.now(timezone.utc)
    wos = db.scalars(select(WorkOrder).where(WorkOrder.organization_id == organization_id)).all()
    invoices = db.scalars(select(Invoice).where(Invoice.organization_id == organization_id)).all()

    # Throughput: jobs completed in the last 30 / 90 days.
    completed = [w for w in wos if w.status in CLOSED_STATES]
    def done_since(days: int) -> int:
        cutoff = now - timedelta(days=days)
        return sum(1 for w in completed if (_aware(w.updated_at) or now) >= cutoff)

    # Average turnaround (days) from created to completed.
    turnarounds = [
        ((_aware(w.updated_at) or now) - _aware(w.created_at)).total_seconds() / 86400
        for w in completed if _aware(w.created_at)
    ]
    avg_turnaround = round(sum(turnarounds) / len(turnarounds), 1) if turnarounds else 0.0

    # Revenue by month (last 6 months), from invoices (exclude void).
    months = [(now - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(5, -1, -1)]
    rev = defaultdict(float)
    for inv in invoices:
        if inv.status == InvoiceStatus.void:
            continue
        key = _aware(inv.issued_at).strftime("%Y-%m")
        rev[key] += inv.total
    revenue_by_month = [{"month": m, "revenue": round(rev.get(m, 0.0), 2)} for m in months]

    # Open pipeline by status.
    status_counts = defaultdict(int)
    for w in wos:
        status_counts[w.status.value] += 1

    # Jobs by equipment type.
    by_type = defaultdict(int)
    for w in wos:
        et = w.equipment.equipment_type.value if w.equipment else "other"
        by_type[et] += 1

    # Technician workload (hours logged).
    entries = db.scalars(
        select(TimeEntry).join(WorkOrder, TimeEntry.work_order_id == WorkOrder.id)
        .where(WorkOrder.organization_id == organization_id)
    ).all()
    hours_by_user = defaultdict(float)
    for e in entries:
        hours_by_user[e.user_id] += e.hours
    users = {u.id: u.full_name for u in db.scalars(
        select(User).where(User.organization_id == organization_id)).all()}
    tech_workload = sorted(
        [{"technician": users.get(uid, f"User {uid}"), "hours": round(h, 1)} for uid, h in hours_by_user.items()],
        key=lambda r: r["hours"], reverse=True,
    )

    # SLA: on-time delivery rate among completed jobs with a promised date.
    from app.services import sla
    on_time, with_promise = sla.on_time_delivery(completed)
    on_time_pct = round(on_time / with_promise * 100, 1) if with_promise else None

    open_total = sum(1 for w in wos if w.status not in CLOSED_STATES
                     and w.status not in (WorkOrderStatus.cancelled,))
    paid_revenue = round(sum(i.total for i in invoices if i.status == InvoiceStatus.paid), 2)
    outstanding = round(sum(i.total for i in invoices
                            if i.status in (InvoiceStatus.sent, InvoiceStatus.draft)), 2)

    return {
        "completed_30d": done_since(30),
        "completed_90d": done_since(90),
        "open_total": open_total,
        "avg_turnaround_days": avg_turnaround,
        "on_time_pct": on_time_pct,
        "paid_revenue": paid_revenue,
        "outstanding_revenue": outstanding,
        "revenue_by_month": revenue_by_month,
        "status_counts": dict(status_counts),
        "by_type": dict(by_type),
        "tech_workload": tech_workload,
    }
