"""Audit log feed — restricted to owners and managers."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import AuditLog, User, UserRole
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit(
    action: str | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.owner, UserRole.manager)),
):
    stmt = select(AuditLog).where(AuditLog.organization_id == user.organization_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all()
