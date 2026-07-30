"""Global search across work orders, customers, and equipment (staff)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Customer, Equipment, User, WorkOrder

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    org = user.organization_id
    like = f"%{q}%"
    results: list[dict] = []

    wos = db.scalars(
        select(WorkOrder)
        .where(WorkOrder.organization_id == org, (WorkOrder.number.ilike(like)) | (WorkOrder.title.ilike(like)))
        .order_by(WorkOrder.created_at.desc())
        .limit(6)
    ).all()
    for w in wos:
        results.append({"type": "work_order", "id": w.id, "label": w.number,
                        "sub": w.title, "route": f"#/workorders/{w.id}"})

    customers = db.scalars(
        select(Customer)
        .where(Customer.organization_id == org, Customer.is_active.is_(True),
               (Customer.name.ilike(like)) | (Customer.account_number.ilike(like)))
        .order_by(Customer.name)
        .limit(6)
    ).all()
    for c in customers:
        results.append({"type": "customer", "id": c.id, "label": c.name,
                        "sub": c.account_number, "route": f"#/customers/{c.id}"})

    equipment = db.scalars(
        select(Equipment)
        .where(Equipment.organization_id == org, Equipment.is_active.is_(True),
               (Equipment.tag.ilike(like)) | (Equipment.serial_number.ilike(like))
               | (Equipment.manufacturer.ilike(like)) | (Equipment.model.ilike(like)))
        .order_by(Equipment.created_at.desc())
        .limit(6)
    ).all()
    for e in equipment:
        label = e.tag or e.serial_number or f"{e.manufacturer or ''} {e.model or ''}".strip() or "Asset"
        results.append({"type": "equipment", "id": e.id, "label": label,
                        "sub": f"{e.manufacturer or ''} {e.model or ''}".strip() or e.equipment_type.value,
                        "route": f"#/equipment/{e.id}"})

    return {"query": q, "results": results}
