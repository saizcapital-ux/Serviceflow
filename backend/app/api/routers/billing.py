"""SaaS subscription billing endpoints (Serviceflow's own revenue)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models import Organization, User, UserRole
from app.schemas import CheckoutRequest, PlanOut, SubscriptionOut
from app.services import saas_billing

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(user: User = Depends(get_current_user)):
    return [PlanOut(**{k: p[k] for k in ("id", "name", "price_monthly", "seats", "features")})
            for p in saas_billing.PLANS.values()]


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")
    return org


@router.post("/checkout")
def checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.owner)),
):
    org = db.get(Organization, user.organization_id)
    try:
        result = saas_billing.start_checkout(db, org, payload.plan_id)
    except saas_billing.BillingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return result


@router.post("/cancel", response_model=SubscriptionOut)
def cancel_subscription(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.owner))):
    org = db.get(Organization, user.organization_id)
    saas_billing.cancel(db, org)
    db.commit()
    db.refresh(org)
    return org


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook: activate the subscription when checkout completes.

    No-op in mock mode. In real mode, verifies the signature and activates the
    org's plan from the session metadata.
    """
    if not settings.stripe_enabled:
        return {"received": True, "mode": "mock"}

    import stripe  # lazy import

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception as exc:  # invalid signature/payload
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid webhook: {exc}")

    if event["type"] == "checkout.session.completed":
        meta = event["data"]["object"].get("metadata", {})
        org = db.get(Organization, int(meta.get("org_id", 0)))
        if org and meta.get("plan_id"):
            org.stripe_subscription_id = event["data"]["object"].get("subscription")
            saas_billing.activate_plan(db, org, meta["plan_id"])
            db.commit()
    return {"received": True}
