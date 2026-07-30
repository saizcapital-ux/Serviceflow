"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """JSON login used by the SPA."""
    user = _authenticate(db, payload.email, payload.password)
    token = create_access_token(user.id, {"role": user.role.value, "org": user.organization_id})
    audit.record(db, organization_id=user.organization_id, actor=user, action="user.login",
                 summary=f"{user.full_name} signed in", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/token", response_model=TokenResponse)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form login so the Swagger 'Authorize' button works."""
    user = _authenticate(db, form.username, form.password)
    token = create_access_token(user.id, {"role": user.role.value, "org": user.organization_id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
