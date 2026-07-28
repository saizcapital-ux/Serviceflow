"""Team endpoints: list staff users (for assignment dropdowns)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import User, UserRole
from app.schemas import UserSummary

router = APIRouter(prefix="/api/users", tags=["team"])


@router.get("", response_model=list[UserSummary])
def list_users(role: UserRole | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    stmt = select(User).where(
        User.organization_id == user.organization_id,
        User.is_active.is_(True),
        User.role != UserRole.customer,
    )
    if role:
        stmt = stmt.where(User.role == role)
    return db.scalars(stmt.order_by(User.full_name)).all()
