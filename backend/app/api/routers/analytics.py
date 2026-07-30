"""Analytics/reporting endpoints (staff)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models import Organization, User
from app.services import analytics
from app.services.pdf import render_analytics_pdf

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return analytics.summary(db, user.organization_id)


@router.get("/reliability")
def analytics_reliability(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return analytics.asset_reliability(db, user.organization_id)


@router.get("/report.pdf")
def analytics_report_pdf(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Download the shop-performance report as a PDF."""
    org = db.get(Organization, user.organization_id)
    summary = analytics.summary(db, user.organization_id)
    reliability = analytics.asset_reliability(db, user.organization_id)
    pdf = render_analytics_pdf(
        org=org, summary=summary, reliability=reliability,
        generated_at=datetime.now(timezone.utc),
    )
    filename = f"shop-performance-{datetime.now(timezone.utc):%Y%m%d}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
