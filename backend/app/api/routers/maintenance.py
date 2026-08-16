"""Preventive-maintenance (PM) plans: recurring service schedules per asset.

Staff create a plan for an asset (interval + instructions); when it comes due
they generate a work order from it with one click, which advances the schedule.
Turns one-off repairs into recurring, planned service revenue.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import (
    Equipment,
    EventType,
    MaintenancePlan,
    Priority,
    ServiceType,
    User,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)
from app.schemas import (
    MaintenanceGenerateResult,
    MaintenancePlanCreate,
    MaintenancePlanOut,
    MaintenancePlanUpdate,
)
from app.services import audit, workflow

router = APIRouter(prefix="/api/maintenance-plans", tags=["maintenance"])

# A plan is "due soon" when it falls due within this many days.
DUE_SOON_DAYS = 30


def _equipment_label(eq: Equipment | None) -> str | None:
    if not eq:
        return None
    return eq.tag or eq.serial_number or (f"{eq.manufacturer} {eq.model}".strip() or None) \
        or f"Asset #{eq.id}"


def _to_out(plan: MaintenancePlan) -> MaintenancePlanOut:
    """Serialize a plan with denormalized equipment/customer context."""
    out = MaintenancePlanOut.model_validate(plan)
    eq = plan.equipment
    out.equipment_label = _equipment_label(eq)
    if eq and eq.customer:
        out.customer_id = eq.customer_id
        out.customer_name = eq.customer.name
    elif eq:
        out.customer_id = eq.customer_id
    return out


def _load(db: Session, plan_id: int, organization_id: int) -> MaintenancePlan:
    plan = db.scalar(
        select(MaintenancePlan)
        .where(MaintenancePlan.id == plan_id, MaintenancePlan.organization_id == organization_id)
        .options(selectinload(MaintenancePlan.equipment).selectinload(Equipment.customer))
    )
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance plan not found.")
    return plan


@router.get("", response_model=list[MaintenancePlanOut])
def list_plans(
    equipment_id: int | None = None,
    due: bool = False,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    """List PM plans for the org, soonest-due first. `due=true` returns only
    plans that are overdue or due within the next 30 days."""
    stmt = (
        select(MaintenancePlan)
        .where(MaintenancePlan.organization_id == user.organization_id)
        .options(selectinload(MaintenancePlan.equipment).selectinload(Equipment.customer))
        .order_by(MaintenancePlan.next_due_on, MaintenancePlan.id)
    )
    if equipment_id is not None:
        stmt = stmt.where(MaintenancePlan.equipment_id == equipment_id)
    if not include_inactive:
        stmt = stmt.where(MaintenancePlan.is_active.is_(True))
    if due:
        stmt = stmt.where(
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.next_due_on <= date.today() + timedelta(days=DUE_SOON_DAYS),
        )
    return [_to_out(p) for p in db.scalars(stmt).all()]


@router.post("", response_model=MaintenancePlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: MaintenancePlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    eq = db.scalar(
        select(Equipment).where(
            Equipment.id == payload.equipment_id,
            Equipment.organization_id == user.organization_id,
        )
    )
    if not eq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")

    interval = payload.interval_days
    if payload.next_due_on is not None:
        next_due = payload.next_due_on
    elif payload.last_service_on is not None:
        next_due = payload.last_service_on + timedelta(days=interval)
    else:
        next_due = date.today()

    plan = MaintenancePlan(
        organization_id=user.organization_id,
        equipment_id=eq.id,
        name=payload.name.strip(),
        interval_days=interval,
        service_type=payload.service_type.value,
        priority=payload.priority.value,
        instructions=(payload.instructions or None),
        last_service_on=payload.last_service_on,
        next_due_on=next_due,
    )
    db.add(plan)
    audit.record(
        db, organization_id=user.organization_id, actor=user, action="maintenance_plan.created",
        summary=f"Created PM plan '{plan.name}' (every {interval}d) for {_equipment_label(eq)}",
        entity_type="maintenance_plan", entity_id=None,
    )
    db.commit()
    return _to_out(_load(db, plan.id, user.organization_id))


@router.patch("/{plan_id}", response_model=MaintenancePlanOut)
def update_plan(
    plan_id: int,
    payload: MaintenancePlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    plan = _load(db, plan_id, user.organization_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        plan.name = data["name"].strip()
    if "interval_days" in data and data["interval_days"] is not None:
        plan.interval_days = data["interval_days"]
    if "service_type" in data and data["service_type"] is not None:
        plan.service_type = ServiceType(data["service_type"]).value
    if "priority" in data and data["priority"] is not None:
        plan.priority = Priority(data["priority"]).value
    if "instructions" in data:
        plan.instructions = data["instructions"] or None
    if "next_due_on" in data and data["next_due_on"] is not None:
        plan.next_due_on = data["next_due_on"]
    if "is_active" in data and data["is_active"] is not None:
        plan.is_active = data["is_active"]
    db.commit()
    return _to_out(_load(db, plan.id, user.organization_id))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    plan = _load(db, plan_id, user.organization_id)
    label = plan.name
    db.delete(plan)
    audit.record(
        db, organization_id=user.organization_id, actor=user, action="maintenance_plan.deleted",
        summary=f"Deleted PM plan '{label}'", entity_type="maintenance_plan", entity_id=plan_id,
    )
    db.commit()


@router.post("/{plan_id}/generate", response_model=MaintenanceGenerateResult, status_code=status.HTTP_201_CREATED)
def generate_work_order(plan_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Create a work order from a due plan and advance its schedule by one interval."""
    plan = _load(db, plan_id, user.organization_id)
    eq = plan.equipment
    if not eq:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan's equipment no longer exists.")

    number = workflow.next_work_order_number(db, user.organization_id)
    wo = WorkOrder(
        organization_id=user.organization_id,
        number=number,
        customer_id=eq.customer_id,
        equipment_id=eq.id,
        location_id=eq.location_id,
        service_type=ServiceType(plan.service_type),
        priority=Priority(plan.priority),
        status=WorkOrderStatus.intake,
        title=plan.name,
        problem_description=plan.instructions or f"Scheduled preventive maintenance: {plan.name}.",
        promised_date=plan.next_due_on,
    )
    db.add(wo)
    db.flush()
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id,
            event_type=EventType.status_change,
            to_status=WorkOrderStatus.intake,
            message=f"Work order {number} opened from PM plan '{plan.name}'.",
            created_by=user.id,
            visible_to_customer=True,
        )
    )

    today = date.today()
    plan.last_service_on = today
    plan.next_due_on = today + timedelta(days=plan.interval_days)

    audit.record(
        db, organization_id=user.organization_id, actor=user, action="maintenance_plan.generated",
        summary=f"Generated {number} from PM plan '{plan.name}'; next due {plan.next_due_on.isoformat()}",
        entity_type="work_order", entity_id=wo.id,
    )
    db.commit()
    return MaintenanceGenerateResult(
        work_order_id=wo.id, work_order_number=number, next_due_on=plan.next_due_on
    )
