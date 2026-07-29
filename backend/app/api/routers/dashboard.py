"""Operational dashboard metrics for staff."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Priority, ServiceType, User, WorkOrder, WorkOrderStatus
from app.schemas import DashboardStats, StatusCount, WorkOrderSummary
from app.services import workflow

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
        by_status=[StatusCount(status=s, count=c) for s, c in by_status_rows],
        recent=[WorkOrderSummary.model_validate(w) for w in recent],
    )
