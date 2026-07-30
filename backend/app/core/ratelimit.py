"""DB-backed sliding-window rate limiting for authentication endpoints.

Login happens before we know the tenant, so attempts are keyed by client IP.
A single failed-attempt table backs the window; successful logins don't count
against the limit.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import LoginAttempt


def client_ip(request: Request) -> str:
    """Best-effort client IP, honoring the proxy's X-Forwarded-For (Render/Netlify)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First hop is the original client.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_login_rate_limit(db: Session, ip: str) -> None:
    """Raise 429 if this IP has too many recent failed attempts."""
    window_start = datetime.now(timezone.utc) - timedelta(minutes=settings.login_rate_limit_window_min)
    failures = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.ip == ip,
            LoginAttempt.successful.is_(False),
            LoginAttempt.created_at >= window_start,
        )
    )
    if failures is not None and failures >= settings.login_rate_limit_max:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(settings.login_rate_limit_window_min * 60)},
        )


def record_attempt(db: Session, ip: str, email: str | None, successful: bool) -> None:
    """Log an attempt. On success, clear this IP's prior failures so a legitimate
    user isn't throttled by earlier typos."""
    db.add(LoginAttempt(ip=ip, email=(email or None), successful=successful))
    if successful:
        for prior in db.scalars(
            select(LoginAttempt).where(
                LoginAttempt.ip == ip, LoginAttempt.successful.is_(False)
            )
        ).all():
            db.delete(prior)
    db.commit()
