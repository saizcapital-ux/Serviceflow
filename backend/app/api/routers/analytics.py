"""Analytics/reporting endpoints (staff)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import User
from app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return analytics.summary(db, user.organization_id)
