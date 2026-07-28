"""Work-order domain logic: the status state machine, numbering, quote math."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EventType,
    Quote,
    QuoteLine,
    QuoteStatus,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)

# Allowed transitions. Empty set = terminal state.
ALLOWED_TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.intake: {WorkOrderStatus.inspection, WorkOrderStatus.on_hold, WorkOrderStatus.cancelled},
    WorkOrderStatus.inspection: {
        WorkOrderStatus.quote_pending,
        WorkOrderStatus.on_hold,
        WorkOrderStatus.cancelled,
    },
    WorkOrderStatus.quote_pending: {
        WorkOrderStatus.approved,
        WorkOrderStatus.quote_rejected,
        WorkOrderStatus.on_hold,
        WorkOrderStatus.cancelled,
    },
    WorkOrderStatus.approved: {WorkOrderStatus.in_repair, WorkOrderStatus.on_hold, WorkOrderStatus.cancelled},
    WorkOrderStatus.quote_rejected: {WorkOrderStatus.ready, WorkOrderStatus.cancelled, WorkOrderStatus.on_hold},
    WorkOrderStatus.in_repair: {WorkOrderStatus.testing, WorkOrderStatus.on_hold},
    WorkOrderStatus.testing: {WorkOrderStatus.ready, WorkOrderStatus.in_repair},
    WorkOrderStatus.ready: {WorkOrderStatus.shipped, WorkOrderStatus.closed},
    WorkOrderStatus.shipped: {WorkOrderStatus.closed},
    WorkOrderStatus.on_hold: {
        WorkOrderStatus.inspection,
        WorkOrderStatus.quote_pending,
        WorkOrderStatus.approved,
        WorkOrderStatus.in_repair,
        WorkOrderStatus.cancelled,
    },
    WorkOrderStatus.closed: set(),
    WorkOrderStatus.cancelled: set(),
}

OPEN_STATUSES = {
    WorkOrderStatus.intake,
    WorkOrderStatus.inspection,
    WorkOrderStatus.quote_pending,
    WorkOrderStatus.approved,
    WorkOrderStatus.in_repair,
    WorkOrderStatus.testing,
    WorkOrderStatus.ready,
    WorkOrderStatus.on_hold,
}


class TransitionError(ValueError):
    """Raised when a status change violates the state machine."""


def can_transition(current: WorkOrderStatus, target: WorkOrderStatus) -> bool:
    if current == target:
        return False
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition_status(
    db: Session,
    wo: WorkOrder,
    target: WorkOrderStatus,
    *,
    user_id: int | None,
    message: str | None = None,
    visible_to_customer: bool = True,
) -> WorkOrderEvent:
    """Validate and apply a status change, recording a timeline event."""
    if not can_transition(wo.status, target):
        raise TransitionError(f"Cannot move a work order from '{wo.status.value}' to '{target.value}'.")
    event = WorkOrderEvent(
        work_order_id=wo.id,
        event_type=EventType.status_change,
        from_status=wo.status,
        to_status=target,
        message=message,
        created_by=user_id,
        visible_to_customer=visible_to_customer,
    )
    wo.status = target
    db.add(event)
    return event


def next_work_order_number(db: Session, organization_id: int) -> str:
    """Generate a human-friendly WO number like WO-2026-0042 (per org, per year)."""
    year = datetime.now(timezone.utc).year
    prefix = f"WO-{year}-"
    count = db.scalar(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.organization_id == organization_id, WorkOrder.number.like(f"{prefix}%"))
    )
    return f"{prefix}{(count or 0) + 1:04d}"


def next_quote_number(db: Session, work_order_number: str, existing: int) -> str:
    return f"{work_order_number}-Q{existing + 1}"


def compute_quote_totals(lines: list[QuoteLine], tax_rate: float) -> tuple[float, float, float]:
    subtotal = round(sum(line.line_total for line in lines), 2)
    tax = round(subtotal * tax_rate, 2)
    return subtotal, tax, round(subtotal + tax, 2)


def apply_quote_decision(
    db: Session, quote: Quote, wo: WorkOrder, *, approve: bool, user_id: int | None, note: str | None
) -> WorkOrderEvent:
    """Customer (or staff) approves/rejects a quote; advances the work order."""
    quote.status = QuoteStatus.approved if approve else QuoteStatus.rejected
    quote.approved_by = user_id
    quote.decided_at = datetime.now(timezone.utc)
    target = WorkOrderStatus.approved if approve else WorkOrderStatus.quote_rejected
    verb = "approved" if approve else "rejected"
    event = transition_status(
        db,
        wo,
        target,
        user_id=user_id,
        message=f"Quote {quote.number} {verb} by customer." + (f" Note: {note}" if note else ""),
        visible_to_customer=True,
    )
    event.event_type = EventType.quote_decision
    if approve:
        wo.total_estimate = quote.total
    return event
