"""Notifications feed (staff): recent messages sent to customers."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    return db.scalars(
        select(Notification)
        .where(Notification.organization_id == user.organization_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).all()
