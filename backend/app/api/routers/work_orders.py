"""Work-order lifecycle endpoints (staff)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import (
    Equipment,
    EventType,
    Finding,
    Quote,
    QuoteLine,
    QuoteStatus,
    User,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)
from app.schemas import (
    FindingCreate,
    FindingOut,
    QuoteCreate,
    QuoteOut,
    StatusChangeRequest,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderSummary,
    WorkOrderUpdate,
)
from app.services import workflow

router = APIRouter(prefix="/api/work-orders", tags=["work-orders"])


def _load_detail(db: Session, wo_id: int, org_id: int) -> WorkOrder:
    wo = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == wo_id, WorkOrder.organization_id == org_id)
        .options(
            selectinload(WorkOrder.customer),
            selectinload(WorkOrder.equipment),
            selectinload(WorkOrder.events),
            selectinload(WorkOrder.findings),
            selectinload(WorkOrder.quotes).selectinload(Quote.lines),
        )
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    return wo


@router.get("", response_model=list[WorkOrderSummary])
def list_work_orders(
    status_filter: WorkOrderStatus | None = Query(None, alias="status"),
    service_type: str | None = None,
    customer_id: int | None = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(WorkOrder).where(WorkOrder.organization_id == user.organization_id)
    if status_filter:
        stmt = stmt.where(WorkOrder.status == status_filter)
    if open_only:
        stmt = stmt.where(WorkOrder.status.in_(workflow.OPEN_STATUSES))
    if customer_id:
        stmt = stmt.where(WorkOrder.customer_id == customer_id)
    if service_type:
        stmt = stmt.where(WorkOrder.service_type == service_type)
    return db.scalars(stmt.order_by(WorkOrder.created_at.desc())).all()


@router.post("", response_model=WorkOrderDetail, status_code=status.HTTP_201_CREATED)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    if payload.equipment_id:
        eq = db.scalar(
            select(Equipment).where(
                Equipment.id == payload.equipment_id, Equipment.organization_id == user.organization_id
            )
        )
        if not eq:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    number = workflow.next_work_order_number(db, user.organization_id)
    wo = WorkOrder(organization_id=user.organization_id, number=number, **payload.model_dump())
    db.add(wo)
    db.flush()
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id,
            event_type=EventType.status_change,
            to_status=WorkOrderStatus.intake,
            message=f"Work order {number} created and received at intake.",
            created_by=user.id,
            visible_to_customer=True,
        )
    )
    db.commit()
    return _load_detail(db, wo.id, user.organization_id)


@router.get("/{wo_id}", response_model=WorkOrderDetail)
def get_work_order(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return _load_detail(db, wo_id, user.organization_id)


@router.patch("/{wo_id}", response_model=WorkOrderDetail)
def update_work_order(
    wo_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    wo = _load_detail(db, wo_id, user.organization_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(wo, field, value)
    db.commit()
    return _load_detail(db, wo_id, user.organization_id)


@router.post("/{wo_id}/status", response_model=WorkOrderDetail)
def change_status(
    wo_id: int, payload: StatusChangeRequest, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    wo = _load_detail(db, wo_id, user.organization_id)
    try:
        workflow.transition_status(
            db,
            wo,
            payload.status,
            user_id=user.id,
            message=payload.message,
            visible_to_customer=payload.visible_to_customer,
        )
    except workflow.TransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return _load_detail(db, wo_id, user.organization_id)


@router.post("/{wo_id}/findings", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
def add_finding(
    wo_id: int, payload: FindingCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    wo = _load_detail(db, wo_id, user.organization_id)
    finding = Finding(work_order_id=wo.id, created_by=user.id, **payload.model_dump())
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/{wo_id}/quotes", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    wo_id: int, payload: QuoteCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    wo = _load_detail(db, wo_id, user.organization_id)
    quote = Quote(
        work_order_id=wo.id,
        number=workflow.next_quote_number(db, wo.number, len(wo.quotes)),
        status=QuoteStatus.sent,
        valid_until=payload.valid_until,
    )
    db.add(quote)
    db.flush()
    for line_in in payload.lines:
        line = QuoteLine(
            quote_id=quote.id,
            kind=line_in.kind,
            description=line_in.description,
            quantity=line_in.quantity,
            unit_price=line_in.unit_price,
            line_total=round(line_in.quantity * line_in.unit_price, 2),
        )
        db.add(line)
        quote.lines.append(line)
    quote.subtotal, quote.tax, quote.total = workflow.compute_quote_totals(quote.lines, payload.tax_rate)

    # Sending a quote moves an inspected job to "quote_pending".
    if wo.status in (WorkOrderStatus.inspection, WorkOrderStatus.intake):
        try:
            workflow.transition_status(
                db, wo, WorkOrderStatus.quote_pending, user_id=user.id,
                message=f"Quote {quote.number} sent to customer for approval (${quote.total:,.2f}).",
            )
        except workflow.TransitionError:
            pass
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id, event_type=EventType.quote_sent, created_by=user.id,
            message=f"Quote {quote.number} issued: ${quote.total:,.2f}.", visible_to_customer=True,
        )
    )
    db.commit()
    db.refresh(quote)
    return quote
