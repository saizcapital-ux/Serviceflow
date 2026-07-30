"""Parts & inventory catalog (staff)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Part, User
from app.schemas import PartAdjust, PartCreate, PartOut, PartUpdate
from app.services import audit

router = APIRouter(prefix="/api/parts", tags=["parts"])


def _get(db: Session, part_id: int, org_id: int) -> Part:
    part = db.scalar(select(Part).where(Part.id == part_id, Part.organization_id == org_id))
    if not part:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Part not found.")
    return part


@router.get("", response_model=list[PartOut])
def list_parts(
    q: str | None = Query(None),
    low_stock: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(Part).where(Part.organization_id == user.organization_id, Part.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Part.sku.ilike(like)) | (Part.name.ilike(like)))
    if low_stock:
        stmt = stmt.where(Part.quantity_on_hand <= Part.reorder_point)
    return db.scalars(stmt.order_by(Part.name)).all()


@router.post("", response_model=PartOut, status_code=status.HTTP_201_CREATED)
def create_part(payload: PartCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    if db.scalar(select(Part).where(Part.organization_id == user.organization_id, Part.sku == payload.sku)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That SKU already exists.")
    part = Part(organization_id=user.organization_id, **payload.model_dump())
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


@router.patch("/{part_id}", response_model=PartOut)
def update_part(part_id: int, payload: PartUpdate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    part = _get(db, part_id, user.organization_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(part, field, value)
    db.commit()
    db.refresh(part)
    return part


@router.post("/{part_id}/adjust", response_model=PartOut)
def adjust_stock(part_id: int, payload: PartAdjust, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    part = _get(db, part_id, user.organization_id)
    new_qty = part.quantity_on_hand + payload.delta
    if new_qty < 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Adjustment would drop stock below zero.")
    part.quantity_on_hand = new_qty
    audit.record(db, organization_id=user.organization_id, actor=user, action="part.adjusted",
                 summary=f"Adjusted {part.sku} by {payload.delta:+d} → {new_qty} on hand"
                         + (f" ({payload.reason})" if payload.reason else ""),
                 entity_type="part", entity_id=part.id)
    db.commit()
    db.refresh(part)
    return part
