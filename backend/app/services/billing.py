"""Billing domain logic: build invoices from approved quotes."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, InvoiceStatus, Quote, QuoteStatus, WorkOrder


class BillingError(ValueError):
    """Raised when an invoice cannot be created."""


def next_invoice_number(db: Session, organization_id: int) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"INV-{year}-"
    count = db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.organization_id == organization_id, Invoice.number.like(f"{prefix}%"))
    )
    return f"{prefix}{(count or 0) + 1:04d}"


def create_invoice_from_quote(
    db: Session, wo: WorkOrder, *, quote_id: int | None, due_in_days: int, notes: str | None
) -> Invoice:
    """Create an invoice by copying the approved quote's lines and totals."""
    approved = [q for q in wo.quotes if q.status == QuoteStatus.approved]
    if quote_id is not None:
        quote = next((q for q in wo.quotes if q.id == quote_id), None)
        if quote is None:
            raise BillingError("Quote not found on this work order.")
        if quote.status != QuoteStatus.approved:
            raise BillingError("Only an approved quote can be invoiced.")
    else:
        if not approved:
            raise BillingError("This work order has no approved quote to invoice.")
        quote = sorted(approved, key=lambda q: q.created_at)[-1]

    invoice = Invoice(
        organization_id=wo.organization_id,
        number=next_invoice_number(db, wo.organization_id),
        work_order_id=wo.id,
        customer_id=wo.customer_id,
        status=InvoiceStatus.sent,
        subtotal=quote.subtotal,
        tax=quote.tax,
        total=quote.total,
        notes=notes,
        due_date=date.today() + timedelta(days=due_in_days),
    )
    db.add(invoice)
    db.flush()
    for ql in quote.lines:
        db.add(
            InvoiceLine(
                invoice_id=invoice.id, kind=ql.kind, description=ql.description,
                quantity=ql.quantity, unit_price=ql.unit_price, line_total=ql.line_total,
            )
        )
    wo.total_actual = quote.total
    db.flush()
    return invoice
