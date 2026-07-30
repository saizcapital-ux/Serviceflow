"""SaaS subscription billing (Serviceflow's own revenue).

Works with or without Stripe:
- If STRIPE_SECRET_KEY is set, `start_checkout` creates a real Stripe Checkout
  Session and the webhook activates the subscription.
- Otherwise it runs in **mock mode**: checkout activates the chosen plan
  immediately, so the whole flow is demoable without any Stripe account.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Organization

# Plan catalog. price_monthly in USD; stripe_price_id used only in real mode.
PLANS: dict[str, dict] = {
    "starter": {
        "id": "starter", "name": "Starter", "price_monthly": 99, "seats": 5,
        "stripe_price_id": "price_starter",
        "features": ["Up to 5 users", "Work orders & scheduling", "Customer portal", "Email notifications"],
    },
    "pro": {
        "id": "pro", "name": "Pro", "price_monthly": 249, "seats": 20,
        "stripe_price_id": "price_pro",
        "features": ["Up to 20 users", "Everything in Starter", "Invoicing & PDF export",
                     "Job costing & margins", "Field dispatch board"],
    },
    "enterprise": {
        "id": "enterprise", "name": "Enterprise", "price_monthly": 799, "seats": 100,
        "stripe_price_id": "price_enterprise",
        "features": ["Up to 100 users", "Everything in Pro", "Priority support",
                     "SSO (roadmap)", "Custom workflows (roadmap)"],
    },
}


class BillingError(ValueError):
    pass


def activate_plan(db: Session, org: Organization, plan_id: str) -> None:
    """Mark an org as subscribed to a plan (used by mock checkout and webhook)."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise BillingError(f"Unknown plan '{plan_id}'.")
    org.plan = plan_id
    org.seats = plan["seats"]
    org.subscription_status = "active"
    org.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)


def cancel(db: Session, org: Organization) -> None:
    org.subscription_status = "canceled"


def start_checkout(db: Session, org: Organization, plan_id: str) -> dict:
    """Return either a real Stripe checkout URL or a mock activation result."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise BillingError(f"Unknown plan '{plan_id}'.")

    if not settings.stripe_enabled:
        # Mock mode: activate immediately.
        activate_plan(db, org, plan_id)
        return {"mock": True, "status": "active", "plan": plan_id,
                "message": f"Subscribed to {plan['name']} (mock mode — no Stripe key configured)."}

    import stripe  # imported lazily; only needed in real mode

    stripe.api_key = settings.stripe_secret_key
    if not org.stripe_customer_id:
        customer = stripe.Customer.create(name=org.name, metadata={"org_id": org.id})
        org.stripe_customer_id = customer.id
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=org.stripe_customer_id,
        line_items=[{"price": plan["stripe_price_id"], "quantity": 1}],
        success_url=settings.billing_success_url,
        cancel_url=settings.billing_cancel_url,
        metadata={"org_id": org.id, "plan_id": plan_id},
    )
    return {"mock": False, "checkout_url": session.url}
