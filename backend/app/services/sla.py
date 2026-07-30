"""SLA helpers: classify jobs against their promised (committed) date."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.models import WorkOrder, WorkOrderStatus

DUE_SOON_DAYS = 3
OPEN_STATES = {
    WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.quote_pending,
    WorkOrderStatus.approved, WorkOrderStatus.in_repair, WorkOrderStatus.testing,
    WorkOrderStatus.ready, WorkOrderStatus.on_hold,
}
DONE_STATES = {WorkOrderStatus.shipped, WorkOrderStatus.closed}


def is_open(wo: WorkOrder) -> bool:
    return wo.status in OPEN_STATES


def is_overdue(wo: WorkOrder, today: date | None = None) -> bool:
    today = today or date.today()
    return is_open(wo) and wo.promised_date is not None and wo.promised_date < today


def is_due_soon(wo: WorkOrder, today: date | None = None) -> bool:
    today = today or date.today()
    if not (is_open(wo) and wo.promised_date is not None):
        return False
    delta = (wo.promised_date - today).days
    return 0 <= delta <= DUE_SOON_DAYS


def on_time_delivery(completed: list[WorkOrder]) -> tuple[int, int]:
    """Return (on_time_count, total_with_promised_date) for completed jobs."""
    on_time = total = 0
    for wo in completed:
        if wo.status not in DONE_STATES or wo.promised_date is None:
            continue
        total += 1
        finished = wo.updated_at or datetime.now(timezone.utc)
        finished_date = (finished if finished.tzinfo else finished.replace(tzinfo=timezone.utc)).date()
        if finished_date <= wo.promised_date:
            on_time += 1
    return on_time, total
