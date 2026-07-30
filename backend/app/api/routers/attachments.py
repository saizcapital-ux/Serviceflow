"""Attachment endpoints: upload files/photos to a work order, serve them back."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_staff
from app.core.database import get_db
from app.models import Attachment, User, UserRole, WorkOrder
from app.schemas import AttachmentOut
from app.services.storage import make_key, storage

router = APIRouter(prefix="/api", tags=["attachments"])

ALLOWED_KINDS = {"photo", "nameplate", "report", "document"}
MAX_BYTES = 15 * 1024 * 1024  # 15 MB


@router.get("/work-orders/{wo_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return db.scalars(
        select(Attachment)
        .join(WorkOrder, Attachment.work_order_id == WorkOrder.id)
        .where(Attachment.work_order_id == wo_id, WorkOrder.organization_id == user.organization_id)
        .order_by(Attachment.created_at.desc())
    ).all()


@router.post("/work-orders/{wo_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    wo_id: int,
    file: UploadFile = File(...),
    kind: str = Form("document"),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    wo = db.scalar(
        select(WorkOrder).where(WorkOrder.id == wo_id, WorkOrder.organization_id == user.organization_id)
    )
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"kind must be one of {sorted(ALLOWED_KINDS)}")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 15 MB limit.")

    key = make_key(user.organization_id, wo_id, file.filename or "upload")
    storage.save(key, data)
    att = Attachment(
        work_order_id=wo_id, filename=file.filename or "upload",
        content_type=file.content_type, url=key, kind=kind, uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/attachments/{attachment_id}/file")
def get_attachment_file(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found.")
    wo = db.get(WorkOrder, att.work_order_id)
    if not wo or wo.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found.")
    if user.role == UserRole.customer and wo.customer_id != user.customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your attachment.")
    try:
        data = storage.load(att.url)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage.")
    return Response(
        content=data,
        media_type=att.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'},
    )
