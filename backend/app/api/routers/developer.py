"""Developer settings (owner only): API keys and outbound webhooks."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles
from app.core.database import get_db
from app.core.security import generate_api_key
from app.models import ApiKey, User, UserRole, Webhook
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    WebhookCreate,
    WebhookDeliveryOut,
    WebhookOut,
)
from app.services import webhooks as webhook_service

router = APIRouter(prefix="/api/developer", tags=["developer"])
owner_only = require_roles(UserRole.owner)


# ---------- API keys ----------
@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_keys(db: Session = Depends(get_db), user: User = Depends(owner_only)):
    return db.scalars(
        select(ApiKey).where(ApiKey.organization_id == user.organization_id).order_by(ApiKey.created_at.desc())
    ).all()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_key(payload: ApiKeyCreate, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    full, prefix, hashed = generate_api_key()
    key = ApiKey(organization_id=user.organization_id, name=payload.name, prefix=prefix, hashed_key=hashed)
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=full)  # full key shown once


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: int, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == user.organization_id))
    if not key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found.")
    key.is_active = False
    db.commit()


# ---------- Webhooks ----------
@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(db: Session = Depends(get_db), user: User = Depends(owner_only)):
    return db.scalars(
        select(Webhook).where(Webhook.organization_id == user.organization_id).order_by(Webhook.created_at.desc())
    ).all()


@router.post("/webhooks", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
def create_webhook(payload: WebhookCreate, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    hook = Webhook(
        organization_id=user.organization_id, url=payload.url,
        events=payload.events or ["*"], secret=webhook_service.new_secret(),
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return hook


@router.delete("/webhooks/{hook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(hook_id: int, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    hook = db.scalar(select(Webhook).where(Webhook.id == hook_id, Webhook.organization_id == user.organization_id))
    if not hook:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    db.delete(hook)
    db.commit()


def _get_hook(db: Session, hook_id: int, org_id: int) -> Webhook:
    hook = db.scalar(select(Webhook).where(Webhook.id == hook_id, Webhook.organization_id == org_id))
    if not hook:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    return hook


@router.get("/webhooks/{hook_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(hook_id: int, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    hook = db.scalar(
        select(Webhook)
        .where(Webhook.id == hook_id, Webhook.organization_id == user.organization_id)
        .options(selectinload(Webhook.deliveries))
    )
    if not hook:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    return hook.deliveries[:50]


@router.post("/webhooks/{hook_id}/test", response_model=WebhookDeliveryOut)
def test_webhook(hook_id: int, db: Session = Depends(get_db), user: User = Depends(owner_only)):
    hook = _get_hook(db, hook_id, user.organization_id)
    delivery = webhook_service._deliver_one(db, hook, "ping", {"message": "Test event from Serviceflow"})
    db.commit()
    db.refresh(delivery)
    return delivery
