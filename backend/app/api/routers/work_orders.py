"""Work-order lifecycle endpoints (staff)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import (
    ChecklistItem,
    ChecklistTemplate,
    Equipment,
    EventType,
    Finding,
    Invoice,
    Organization,
    Part,
    PartUsage,
    Quote,
    QuoteLine,
    QuoteStatus,
    TimeEntry,
    User,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)
from app.schemas import (
    ApplyTemplate,
    CostingSummary,
    FindingCreate,
    FindingOut,
    PartUsageCreate,
    PartUsageOut,
    QuoteCreate,
    QuoteOut,
    ScheduleRequest,
    StatusChangeRequest,
    TimeEntryCreate,
    TimeEntryOut,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderSummary,
    WorkOrderUpdate,
)
from app.services import audit, notifications, webhooks, workflow
from app.services.pdf import render_work_order_pdf

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
            selectinload(WorkOrder.invoices).selectinload(Invoice.lines),
            selectinload(WorkOrder.time_entries),
            selectinload(WorkOrder.parts_used),
            selectinload(WorkOrder.checklist_items),
            selectinload(WorkOrder.attachments),
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
    equipment_id: int | None = None,
    location_id: int | None = None,
    assigned_to: int | None = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(WorkOrder).where(WorkOrder.organization_id == user.organization_id)
    if status_filter:
        stmt = stmt.where(WorkOrder.status == status_filter)
    if open_only:
        stmt = stmt.where(WorkOrder.status.in_(workflow.OPEN_STATUSES))
    if assigned_to:
        stmt = stmt.where(WorkOrder.assigned_to == assigned_to)
    if customer_id:
        stmt = stmt.where(WorkOrder.customer_id == customer_id)
    if equipment_id:
        stmt = stmt.where(WorkOrder.equipment_id == equipment_id)
    if location_id:
        stmt = stmt.where(WorkOrder.location_id == location_id)
    if service_type:
        stmt = stmt.where(WorkOrder.service_type == service_type)
    return db.scalars(stmt.order_by(WorkOrder.created_at.desc())).all()


@router.get("/export.csv")
def export_work_orders(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Download all work orders as CSV (with customer & equipment names)."""
    wos = db.scalars(
        select(WorkOrder)
        .where(WorkOrder.organization_id == user.organization_id)
        .options(selectinload(WorkOrder.customer), selectinload(WorkOrder.equipment))
        .order_by(WorkOrder.created_at.desc())
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Number", "Status", "Priority", "Service type", "Customer", "Equipment",
                "PO number", "Promised", "Estimate", "Actual", "Created"])
    for o in wos:
        w.writerow([
            o.number, o.status.value, o.priority.value, o.service_type.value,
            o.customer.name if o.customer else "",
            (o.equipment.tag or o.equipment.serial_number or "") if o.equipment else "",
            o.po_number or "", o.promised_date or "", f"{o.total_estimate:.2f}",
            f"{o.total_actual:.2f}", o.created_at.date().isoformat() if o.created_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="work-orders.csv"'},
    )


def _notify_if_newly_assigned(db: Session, wo: WorkOrder, previous_assigned_to, actor: User) -> None:
    """Email + feed-notify the assignee when a work order is newly assigned to
    someone other than the person making the change."""
    if wo.assigned_to and wo.assigned_to != previous_assigned_to and wo.assigned_to != actor.id:
        assignee = db.get(User, wo.assigned_to)
        notifications.notify_assignment(db, wo, assignee, actor.full_name)


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
    audit.record(db, organization_id=user.organization_id, actor=user, action="work_order.created",
                 summary=f"Created work order {number} — {wo.title}", entity_type="work_order", entity_id=wo.id)
    _notify_if_newly_assigned(db, wo, None, user)
    db.commit()
    return _load_detail(db, wo.id, user.organization_id)


@router.get("/{wo_id}", response_model=WorkOrderDetail)
def get_work_order(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return _load_detail(db, wo_id, user.organization_id)


@router.get("/{wo_id}/traveler.pdf")
def work_order_traveler(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Printable shop-floor job traveler (PDF)."""
    wo = _load_detail(db, wo_id, user.organization_id)
    org = db.get(Organization, user.organization_id)
    part_names = {p.id: p for p in db.scalars(
        select(Part).where(Part.organization_id == user.organization_id)).all()}
    parts = [(pu, (part_names.get(pu.part_id).name if part_names.get(pu.part_id) else f"Part #{pu.part_id}"))
             for pu in wo.parts_used]
    pdf = render_work_order_pdf(
        org=org, work_order=wo, customer=wo.customer, equipment=wo.equipment,
        findings=wo.findings, checklist=wo.checklist_items, parts=parts,
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{wo.number}-traveler.pdf"'})


@router.patch("/{wo_id}", response_model=WorkOrderDetail)
def update_work_order(
    wo_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    wo = _load_detail(db, wo_id, user.organization_id)
    previous_assigned_to = wo.assigned_to
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("assigned_to") is not None:
        assignee = db.get(User, fields["assigned_to"])
        if not assignee or assignee.organization_id != user.organization_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Assigned user not found.")
    for field, value in fields.items():
        setattr(wo, field, value)
    _notify_if_newly_assigned(db, wo, previous_assigned_to, user)
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
    if payload.visible_to_customer:
        notifications.notify_customer_status(
            db, wo, payload.message or f"Status updated to {payload.status.value.replace('_', ' ')}."
        )
    audit.record(db, organization_id=user.organization_id, actor=user, action="work_order.status_changed",
                 summary=f"{wo.number} → {payload.status.value.replace('_', ' ')}",
                 entity_type="work_order", entity_id=wo.id, meta={"status": payload.status.value})
    webhooks.dispatch(db, user.organization_id, "work_order.status_changed",
                      {"id": wo.id, "number": wo.number, "status": payload.status.value})
    db.commit()
    return _load_detail(db, wo_id, user.organization_id)


@router.post("/{wo_id}/schedule", response_model=WorkOrderDetail)
def schedule_visit(wo_id: int, payload: ScheduleRequest, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Schedule (or reschedule) a field visit and optionally assign a technician."""
    wo = _load_detail(db, wo_id, user.organization_id)
    previous_assigned_to = wo.assigned_to
    wo.scheduled_at = payload.scheduled_at
    if payload.assigned_to is not None:
        tech = db.get(User, payload.assigned_to)
        if not tech or tech.organization_id != user.organization_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Assigned user not found.")
        wo.assigned_to = payload.assigned_to
        _notify_if_newly_assigned(db, wo, previous_assigned_to, user)
    when = payload.scheduled_at.strftime("%b %d, %Y %I:%M %p")
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id, event_type=EventType.field_visit, created_by=user.id,
            message=f"Field visit scheduled for {when}.", visible_to_customer=True,
        )
    )
    if payload.notify_customer:
        notifications.notify_customer_status(db, wo, f"Field visit scheduled for {when}.")
    audit.record(db, organization_id=user.organization_id, actor=user, action="work_order.scheduled",
                 summary=f"Scheduled field visit for {wo.number} on {when}",
                 entity_type="work_order", entity_id=wo.id)
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
    notifications.notify_quote_sent(db, wo, quote.number, quote.total)
    audit.record(db, organization_id=user.organization_id, actor=user, action="quote.sent",
                 summary=f"Sent quote {quote.number} on {wo.number} (${quote.total:,.2f})",
                 entity_type="work_order", entity_id=wo.id)
    db.commit()
    db.refresh(quote)
    return quote


@router.post("/{wo_id}/time-entries", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def log_time(wo_id: int, payload: TimeEntryCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    wo = _load_detail(db, wo_id, user.organization_id)
    entry = TimeEntry(
        work_order_id=wo.id,
        user_id=payload.user_id or user.id,
        hours=payload.hours,
        note=payload.note,
        worked_on=payload.worked_on or date.today(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{wo_id}/checklist/apply", response_model=WorkOrderDetail)
def apply_checklist(wo_id: int, payload: ApplyTemplate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Instantiate a traveler template's steps as checklist items on this job."""
    wo = _load_detail(db, wo_id, user.organization_id)
    tmpl = db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.id == payload.template_id,
            ChecklistTemplate.organization_id == user.organization_id,
        )
    )
    if not tmpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    start = len(wo.checklist_items)
    for i, label in enumerate(tmpl.items):
        db.add(ChecklistItem(work_order_id=wo.id, label=label, position=start + i))
    db.commit()
    return _load_detail(db, wo_id, user.organization_id)


@router.post("/{wo_id}/parts", response_model=PartUsageOut, status_code=status.HTTP_201_CREATED)
def consume_part(wo_id: int, payload: PartUsageCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Record part usage on a job and decrement inventory stock."""
    wo = _load_detail(db, wo_id, user.organization_id)
    part = db.scalar(select(Part).where(Part.id == payload.part_id, Part.organization_id == user.organization_id))
    if not part:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Part not found.")
    if part.quantity_on_hand < payload.quantity:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only {part.quantity_on_hand} of {part.sku} in stock.")
    part.quantity_on_hand -= payload.quantity
    usage = PartUsage(work_order_id=wo.id, part_id=part.id, quantity=payload.quantity,
                      unit_price=part.unit_price, used_by=user.id)
    db.add(usage)
    audit.record(db, organization_id=user.organization_id, actor=user, action="part.consumed",
                 summary=f"Used {payload.quantity} × {part.sku} on {wo.number}",
                 entity_type="part", entity_id=part.id)
    db.commit()
    db.refresh(usage)
    return usage


@router.get("/{wo_id}/costing", response_model=CostingSummary)
def costing(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    wo = _load_detail(db, wo_id, user.organization_id)
    org = db.get(Organization, user.organization_id)
    rate = org.labor_cost_rate if org else 95.0
    hours = round(sum(t.hours for t in wo.time_entries), 2)
    labor_cost = round(hours * rate, 2)
    estimate = wo.total_estimate or 0.0
    invoiced = round(sum(i.total for i in wo.invoices), 2)
    margin = round(estimate - labor_cost, 2)
    return CostingSummary(
        logged_hours=hours, labor_rate=rate, labor_cost=labor_cost, estimate=estimate,
        invoiced=invoiced, margin=margin,
        margin_pct=round(margin / estimate * 100, 1) if estimate else None,
    )
