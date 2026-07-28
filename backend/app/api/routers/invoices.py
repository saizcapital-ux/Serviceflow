"""Invoice endpoints: create from approved quote, list, PDF export, mark paid."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_staff
from app.core.database import get_db
from app.models import (
    Customer,
    Equipment,
    Invoice,
    InvoiceStatus,
    Organization,
    User,
    UserRole,
    WorkOrder,
)
from app.schemas import InvoiceCreate, InvoiceOut, MarkPaid
from app.services import billing
from app.services.pdf import render_invoice_pdf

router = APIRouter(prefix="/api", tags=["invoices"])


def _load_invoice(db: Session, invoice_id: int, org_id: int) -> Invoice:
    inv = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == org_id)
        .options(selectinload(Invoice.lines))
    )
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found.")
    return inv


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(customer_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    stmt = select(Invoice).where(Invoice.organization_id == user.organization_id).options(selectinload(Invoice.lines))
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    return db.scalars(stmt.order_by(Invoice.issued_at.desc())).all()


@router.post("/work-orders/{wo_id}/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(wo_id: int, payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    wo = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == wo_id, WorkOrder.organization_id == user.organization_id)
        .options(selectinload(WorkOrder.quotes))
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    try:
        invoice = billing.create_invoice_from_quote(
            db, wo, quote_id=payload.quote_id, due_in_days=payload.due_in_days, notes=payload.notes
        )
    except billing.BillingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return _load_invoice(db, invoice.id, user.organization_id)


@router.post("/invoices/{invoice_id}/paid", response_model=InvoiceOut)
def mark_paid(invoice_id: int, payload: MarkPaid, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    inv = _load_invoice(db, invoice_id, user.organization_id)
    inv.status = InvoiceStatus.paid if payload.paid else InvoiceStatus.sent
    inv.paid_at = datetime.now(timezone.utc) if payload.paid else None
    db.commit()
    return _load_invoice(db, invoice_id, user.organization_id)


def _render(db: Session, inv: Invoice) -> bytes:
    wo = db.get(WorkOrder, inv.work_order_id)
    customer = db.get(Customer, inv.customer_id)
    org = db.get(Organization, inv.organization_id)
    equipment = db.get(Equipment, wo.equipment_id) if wo and wo.equipment_id else None
    return render_invoice_pdf(org=org, invoice=inv, work_order=wo, customer=customer, equipment=equipment)


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """PDF download. Staff see any org invoice; portal users only their own."""
    inv = db.get(Invoice, invoice_id)
    if not inv or inv.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found.")
    if user.role == UserRole.customer and inv.customer_id != user.customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your invoice.")
    pdf = _render(db, inv)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{inv.number}.pdf"'},
    )
