"""Operational dashboard metrics for staff."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import (
    Customer,
    Equipment,
    EquipmentSpecField,
    Priority,
    ServiceType,
    TestTemplateItem,
    User,
    WorkOrder,
    WorkOrderStatus,
)
from app.schemas import DashboardStats, SetupProgress, StatusCount, WorkOrderSummary
from app.services import sla, workflow

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
def dashboard(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    org = user.organization_id
    loc = (WorkOrder.location_id == location_id,) if location_id else ()
    base = select(func.count()).select_from(WorkOrder).where(WorkOrder.organization_id == org, *loc)

    def count(*conditions) -> int:
        return db.scalar(base.where(*conditions)) or 0

    by_status_rows = db.execute(
        select(WorkOrder.status, func.count())
        .where(WorkOrder.organization_id == org, *loc)
        .group_by(WorkOrder.status)
    ).all()

    recent = db.scalars(
        select(WorkOrder)
        .where(WorkOrder.organization_id == org, *loc)
        .order_by(WorkOrder.updated_at.desc())
        .limit(8)
    ).all()

    # Onboarding progress is org-wide (not location-scoped): does this org exist yet?
    def org_exists(model) -> bool:
        return bool(
            db.scalar(select(func.count()).select_from(model).where(model.organization_id == org))
        )

    staff_count = db.scalar(
        select(func.count()).select_from(User).where(
            User.organization_id == org, User.customer_id.is_(None), User.is_active.is_(True)
        )
    ) or 0
    setup = SetupProgress(
        has_customer=org_exists(Customer),
        has_equipment=org_exists(Equipment),
        has_work_order=org_exists(WorkOrder),
        has_team=staff_count > 1,
        has_template=org_exists(TestTemplateItem) or org_exists(EquipmentSpecField),
    )

    today = date.today()
    open_states = WorkOrder.status.in_(sla.OPEN_STATES)
    return DashboardStats(
        open_work_orders=count(WorkOrder.status.in_(workflow.OPEN_STATUSES)),
        rush_jobs=count(
            WorkOrder.priority == Priority.rush, WorkOrder.status.in_(workflow.OPEN_STATUSES)
        ),
        awaiting_approval=count(WorkOrder.status == WorkOrderStatus.quote_pending),
        ready_to_ship=count(WorkOrder.status == WorkOrderStatus.ready),
        field_visits_scheduled=count(
            WorkOrder.service_type == ServiceType.field_service,
            WorkOrder.status.in_(workflow.OPEN_STATUSES),
        ),
        overdue_open=count(open_states, WorkOrder.promised_date < today),
        due_soon_open=count(
            open_states, WorkOrder.promised_date >= today,
            WorkOrder.promised_date <= today + timedelta(days=sla.DUE_SOON_DAYS),
        ),
        by_status=[StatusCount(status=s, count=c) for s, c in by_status_rows],
        recent=[WorkOrderSummary.model_validate(w) for w in recent],
        setup=setup,
    )
