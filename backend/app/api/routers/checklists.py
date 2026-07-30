"""Checklist templates (travelers) and per-job checklist items."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import ChecklistItem, ChecklistTemplate, User, WorkOrder
from app.schemas import (
    ChecklistItemOut,
    ChecklistItemUpdate,
    ChecklistTemplateCreate,
    ChecklistTemplateOut,
)

router = APIRouter(prefix="/api", tags=["checklists"])


@router.get("/checklist-templates", response_model=list[ChecklistTemplateOut])
def list_templates(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return db.scalars(
        select(ChecklistTemplate)
        .where(ChecklistTemplate.organization_id == user.organization_id)
        .order_by(ChecklistTemplate.name)
    ).all()


@router.post("/checklist-templates", response_model=ChecklistTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(payload: ChecklistTemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    tmpl = ChecklistTemplate(organization_id=user.organization_id, **payload.model_dump())
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.patch("/checklist-items/{item_id}", response_model=ChecklistItemOut)
def update_item(item_id: int, payload: ChecklistItemUpdate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    item = db.scalar(
        select(ChecklistItem)
        .join(WorkOrder, ChecklistItem.work_order_id == WorkOrder.id)
        .where(ChecklistItem.id == item_id, WorkOrder.organization_id == user.organization_id)
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found.")
    if payload.is_done is not None:
        item.is_done = payload.is_done
        item.completed_by = user.id if payload.is_done else None
        item.completed_at = datetime.now(timezone.utc) if payload.is_done else None
    if payload.note is not None:
        item.note = payload.note
    db.commit()
    db.refresh(item)
    return item
