"""Public integration API (v1), authenticated with an X-API-Key header."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_org
from app.core.database import get_db
from app.models import WorkOrder
from app.schemas import WorkOrderSummary

router = APIRouter(prefix="/api/v1", tags=["integration"])


@router.get("/work-orders", response_model=list[WorkOrderSummary])
def api_list_work_orders(
    limit: int = 50,
    db: Session = Depends(get_db),
    organization_id: int = Depends(get_api_key_org),
):
    """List the org's work orders. Auth: `X-API-Key: sf_...`"""
    return db.scalars(
        select(WorkOrder)
        .where(WorkOrder.organization_id == organization_id)
        .order_by(WorkOrder.created_at.desc())
        .limit(min(limit, 200))
    ).all()


@router.get("/work-orders/{wo_id}", response_model=WorkOrderSummary)
def api_get_work_order(
    wo_id: int, db: Session = Depends(get_db), organization_id: int = Depends(get_api_key_org)
):
    wo = db.scalar(
        select(WorkOrder).where(WorkOrder.id == wo_id, WorkOrder.organization_id == organization_id)
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    return wo
