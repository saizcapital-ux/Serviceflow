"""Authentication endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.ratelimit import client_ip, enforce_login_rate_limit, record_attempt
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import PasswordResetToken, User
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services import audit, notifications

router = APIRouter(prefix="/api/auth", tags=["auth"])

RESET_TTL_MINUTES = 60


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """JSON login used by the SPA."""
    ip = client_ip(request)
    enforce_login_rate_limit(db, ip)
    try:
        user = _authenticate(db, payload.email, payload.password)
    except HTTPException:
        record_attempt(db, ip, payload.email, successful=False)
        raise
    record_attempt(db, ip, payload.email, successful=True)
    token = create_access_token(user.id, {"role": user.role.value, "org": user.organization_id})
    audit.record(db, organization_id=user.organization_id, actor=user, action="user.login",
                 summary=f"{user.full_name} signed in", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/token", response_model=TokenResponse)
def login_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form login so the Swagger 'Authorize' button works."""
    ip = client_ip(request)
    enforce_login_rate_limit(db, ip)
    try:
        user = _authenticate(db, form.username, form.password)
    except HTTPException:
        record_attempt(db, ip, form.username, successful=False)
        raise
    record_attempt(db, ip, form.username, successful=True)
    token = create_access_token(user.id, {"role": user.role.value, "org": user.organization_id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Start a password reset. Always returns 202 so we never reveal whether an
    email is registered."""
    # An IP already throttled for failed logins can't pivot to reset-email spam.
    enforce_login_rate_limit(db, client_ip(request))
    user = db.scalar(select(User).where(User.email == payload.email.lower(), User.is_active.is_(True)))
    if user:
        raw_token = generate_token()
        db.add(PasswordResetToken(
            user_id=user.id, token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MINUTES),
        ))
        db.flush()
        notifications.notify_password_reset(
            db, organization_id=user.organization_id, email=user.email,
            token=raw_token, name=user.full_name,
        )
        db.commit()
    return {"detail": "If that email is registered, a reset link is on its way."}


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Complete a password reset with a valid, unused, unexpired token."""
    prt = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == hash_token(payload.token)
    ))
    expires = prt.expires_at if prt else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not prt or prt.used_at is not None or expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")

    user = db.get(User, prt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")

    user.hashed_password = hash_password(payload.password)
    prt.used_at = datetime.now(timezone.utc)
    # Invalidate any other outstanding reset tokens for this user.
    for other in db.scalars(select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
    )).all():
        other.used_at = datetime.now(timezone.utc)
    audit.record(db, organization_id=user.organization_id, actor=user, action="user.password_reset",
                 summary=f"{user.full_name} reset their password", entity_type="user", entity_id=user.id)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, {"role": user.role.value, "org": user.organization_id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))
