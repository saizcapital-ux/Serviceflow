"""Customer portal endpoints — scoped strictly to the logged-in customer."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import (
    Customer,
    Equipment,
    EventType,
    Invoice,
    Quote,
    ServiceType,
    TestResult,
    User,
    UserRole,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)
from app.schemas import (
    EquipmentOut,
    EventOut,
    InvoiceOut,
    PortalMessageCreate,
    QuoteDecision,
    QuoteOut,
    ServiceRequestCreate,
    TestReportOut,
    TestResultOut,
    WorkOrderDetail,
    WorkOrderSummary,
)
from app.services import audit, notifications, workflow

router = APIRouter(prefix="/api/portal", tags=["portal"])


def require_portal(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.customer or not user.customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Customer portal access only.")
    return user


@router.get("/work-orders", response_model=list[WorkOrderSummary])
def my_work_orders(db: Session = Depends(get_db), user: User = Depends(require_portal)):
    stmt = (
        select(WorkOrder)
        .where(
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.customer_id == user.customer_id,
        )
        .order_by(WorkOrder.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/work-orders/{wo_id}", response_model=WorkOrderDetail)
def my_work_order_detail(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_portal)):
    wo = db.scalar(
        select(WorkOrder)
        .where(
            WorkOrder.id == wo_id,
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.customer_id == user.customer_id,
        )
        .options(
            selectinload(WorkOrder.customer),
            selectinload(WorkOrder.equipment),
            selectinload(WorkOrder.events),
            selectinload(WorkOrder.findings),
            selectinload(WorkOrder.quotes).selectinload(Quote.lines),
            selectinload(WorkOrder.invoices).selectinload(Invoice.lines),
            selectinload(WorkOrder.attachments),
        )
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    # Hide internal-only events from the customer.
    wo.events = [e for e in wo.events if e.visible_to_customer]
    return wo


@router.post("/work-orders/{wo_id}/messages", response_model=WorkOrderDetail, status_code=status.HTTP_201_CREATED)
def post_message(
    wo_id: int, payload: PortalMessageCreate,
    db: Session = Depends(get_db), user: User = Depends(require_portal),
):
    """Let a customer post a message on their own work order; it appears on the
    timeline and notifies the shop's intake staff."""
    wo = db.scalar(
        select(WorkOrder).where(
            WorkOrder.id == wo_id,
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.customer_id == user.customer_id,
        )
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")

    db.add(WorkOrderEvent(
        work_order_id=wo.id, event_type=EventType.note,
        message=f"{user.full_name}: {payload.message}",
        created_by=user.id, visible_to_customer=True,
    ))
    customer = db.get(Customer, user.customer_id)
    notifications.notify_staff_customer_message(
        db, wo, customer.name if customer else user.full_name, payload.message
    )
    audit.record(db, organization_id=user.organization_id, actor=user, action="portal.message_posted",
                 summary=f"Customer message on {wo.number}", entity_type="work_order", entity_id=wo.id)
    db.commit()
    return my_work_order_detail(wo.id, db, user)


@router.get("/work-orders/{wo_id}/tests", response_model=TestReportOut)
def my_work_order_tests(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_portal)):
    """Read-only test/inspection report for the customer's own work order."""
    from app.api.routers.tests import compute_overall  # local import avoids a cycle at load time
    wo = db.scalar(select(WorkOrder).where(
        WorkOrder.id == wo_id, WorkOrder.organization_id == user.organization_id,
        WorkOrder.customer_id == user.customer_id))
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    results = db.scalars(
        select(TestResult).where(TestResult.work_order_id == wo_id)
        .order_by(TestResult.position, TestResult.id)
    ).all()
    return TestReportOut(overall=compute_overall(results),
                         items=[TestResultOut.model_validate(r) for r in results])


@router.get("/invoices", response_model=list[InvoiceOut])
def my_invoices(db: Session = Depends(get_db), user: User = Depends(require_portal)):
    stmt = (
        select(Invoice)
        .where(Invoice.organization_id == user.organization_id, Invoice.customer_id == user.customer_id)
        .options(selectinload(Invoice.lines))
        .order_by(Invoice.issued_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/equipment", response_model=list[EquipmentOut])
def my_equipment(db: Session = Depends(get_db), user: User = Depends(require_portal)):
    stmt = select(Equipment).where(
        Equipment.organization_id == user.organization_id,
        Equipment.customer_id == user.customer_id,
        Equipment.is_active.is_(True),
    )
    return db.scalars(stmt).all()


@router.post("/quotes/{quote_id}/decision", response_model=QuoteOut)
def decide_quote(
    quote_id: int, payload: QuoteDecision, db: Session = Depends(get_db), user: User = Depends(require_portal)
):
    quote = db.scalar(
        select(Quote).where(Quote.id == quote_id).options(selectinload(Quote.lines))
    )
    if not quote:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found.")
    wo = db.get(WorkOrder, quote.work_order_id)
    if not wo or wo.customer_id != user.customer_id or wo.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your quote.")
    if quote.status not in ("sent", "draft"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This quote has already been decided.")
    if payload.po_number:
        wo.po_number = payload.po_number
    try:
        workflow.apply_quote_decision(
            db, quote, wo, approve=payload.approve, user_id=user.id, note=payload.note
        )
    except workflow.TransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    audit.record(db, organization_id=user.organization_id, actor=user,
                 action="quote.approved" if payload.approve else "quote.rejected",
                 summary=f"Customer {'approved' if payload.approve else 'declined'} quote {quote.number}"
                         + (f" (PO {payload.po_number})" if payload.po_number else ""),
                 entity_type="work_order", entity_id=wo.id)
    db.commit()
    db.refresh(quote)
    return quote


@router.post("/service-requests", response_model=WorkOrderDetail, status_code=status.HTTP_201_CREATED)
def create_service_request(
    payload: ServiceRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_portal)
):
    """Customer-submitted repair request → a new work order at intake for the shop."""
    if payload.equipment_id is not None:
        eq = db.scalar(
            select(Equipment).where(
                Equipment.id == payload.equipment_id,
                Equipment.organization_id == user.organization_id,
                Equipment.customer_id == user.customer_id,
            )
        )
        if not eq:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    number = workflow.next_work_order_number(db, user.organization_id)
    wo = WorkOrder(
        organization_id=user.organization_id,
        number=number,
        customer_id=user.customer_id,
        equipment_id=payload.equipment_id,
        service_type=ServiceType.shop_repair,
        status=WorkOrderStatus.intake,
        priority=payload.priority,
        title=payload.title,
        problem_description=payload.problem_description,
        po_number=payload.po_number,
    )
    db.add(wo)
    db.flush()
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id,
            event_type=EventType.status_change,
            to_status=WorkOrderStatus.intake,
            message=f"Service request submitted by customer via portal — {number} received at intake.",
            created_by=user.id,
            visible_to_customer=True,
        )
    )
    audit.record(db, organization_id=user.organization_id, actor=user, action="service_request.created",
                 summary=f"Customer submitted service request {number} — {wo.title}",
                 entity_type="work_order", entity_id=wo.id)
    customer = db.get(Customer, user.customer_id)
    notifications.notify_staff_new_request(db, wo, customer.name if customer else user.full_name)
    db.commit()
    wo = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == wo.id)
        .options(
            selectinload(WorkOrder.customer),
            selectinload(WorkOrder.equipment),
            selectinload(WorkOrder.events),
            selectinload(WorkOrder.findings),
            selectinload(WorkOrder.quotes).selectinload(Quote.lines),
            selectinload(WorkOrder.invoices).selectinload(Invoice.lines),
            selectinload(WorkOrder.attachments),
        )
    )
    wo.events = [e for e in wo.events if e.visible_to_customer]
    return wo


@router.post("/work-orders/{wo_id}/withdraw", response_model=WorkOrderDetail)
def withdraw_work_order(
    wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_portal)
):
    """Customer withdraws their own request — allowed only while still at intake."""
    wo = db.scalar(
        select(WorkOrder).where(
            WorkOrder.id == wo_id,
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.customer_id == user.customer_id,
        )
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    if wo.status != WorkOrderStatus.intake:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This request is already being worked on and can no longer be withdrawn online — "
            "please contact the service center.",
        )
    try:
        workflow.transition_status(
            db, wo, WorkOrderStatus.cancelled, user_id=user.id,
            message="Request withdrawn by the customer before work began.",
            visible_to_customer=True,
        )
    except workflow.TransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    audit.record(db, organization_id=user.organization_id, actor=user, action="service_request.withdrawn",
                 summary=f"Customer withdrew request {wo.number}",
                 entity_type="work_order", entity_id=wo.id)
    customer = db.get(Customer, user.customer_id)
    notifications.notify_staff_request_withdrawn(db, wo, customer.name if customer else user.full_name)
    db.commit()
    fresh = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == wo.id)
        .options(
            selectinload(WorkOrder.customer),
            selectinload(WorkOrder.equipment),
            selectinload(WorkOrder.events),
            selectinload(WorkOrder.findings),
            selectinload(WorkOrder.quotes).selectinload(Quote.lines),
            selectinload(WorkOrder.invoices).selectinload(Invoice.lines),
            selectinload(WorkOrder.attachments),
        )
    )
    fresh.events = [e for e in fresh.events if e.visible_to_customer]
    return fresh
