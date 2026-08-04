"""Equipment spec templates: per-organization fields to capture for each
equipment type. Read by any staff; managed by owners/managers."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.core.database import get_db
from app.models import EquipmentSpecField, EquipmentType, User, UserRole
from app.schemas import SpecFieldCreate, SpecFieldOut, SpecFieldUpdate
from app.services import audit

router = APIRouter(prefix="/api/spec-templates", tags=["spec-templates"])

require_manager = require_roles(UserRole.owner, UserRole.manager)


@router.get("", response_model=list[SpecFieldOut])
def list_fields(
    equipment_type: EquipmentType | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(EquipmentSpecField).where(EquipmentSpecField.organization_id == user.organization_id)
    if equipment_type is not None:
        stmt = stmt.where(EquipmentSpecField.equipment_type == equipment_type.value)
    stmt = stmt.order_by(EquipmentSpecField.equipment_type, EquipmentSpecField.position, EquipmentSpecField.id)
    return db.scalars(stmt).all()


@router.post("", response_model=SpecFieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: SpecFieldCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    field = EquipmentSpecField(
        organization_id=user.organization_id,
        equipment_type=payload.equipment_type.value,
        label=payload.label.strip(),
        unit=(payload.unit or None),
        position=payload.position,
    )
    db.add(field)
    audit.record(db, organization_id=user.organization_id, actor=user, action="spec_field.created",
                 summary=f"Added spec '{field.label}' for {field.equipment_type}",
                 entity_type="spec_field", entity_id=None)
    db.commit()
    db.refresh(field)
    return field


def _owned(db: Session, field_id: int, user: User) -> EquipmentSpecField:
    field = db.get(EquipmentSpecField, field_id)
    if not field or field.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Spec field not found.")
    return field


@router.patch("/{field_id}", response_model=SpecFieldOut)
def update_field(field_id: int, payload: SpecFieldUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require_manager)):
    field = _owned(db, field_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        field.label = data["label"].strip()
    if "unit" in data:
        field.unit = data["unit"] or None
    if "position" in data and data["position"] is not None:
        field.position = data["position"]
    db.commit()
    db.refresh(field)
    return field


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(field_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    field = _owned(db, field_id, user)
    db.delete(field)
    audit.record(db, organization_id=user.organization_id, actor=user, action="spec_field.deleted",
                 summary=f"Removed spec '{field.label}' for {field.equipment_type}",
                 entity_type="spec_field", entity_id=None)
    db.commit()
