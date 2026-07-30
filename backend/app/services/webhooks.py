"""Outbound webhooks: sign and deliver event payloads, logging each attempt.

Delivery is best-effort and time-bounded (stdlib urllib, short timeout) so it
never hangs or breaks the triggering request. Every attempt is recorded as a
WebhookDelivery. A production build would move this to a background queue with
retries/backoff — the interface here stays the same.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import urllib.error
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Webhook, WebhookDelivery

log = logging.getLogger("serviceflow.webhooks")
TIMEOUT_S = 3


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _deliver_one(db: Session, hook: Webhook, event: str, payload: dict) -> WebhookDelivery:
    body = json.dumps({"event": event, "data": payload}).encode()
    delivery = WebhookDelivery(webhook_id=hook.id, event=event)
    try:
        req = urllib.request.Request(
            hook.url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Serviceflow-Event": event,
                "X-Serviceflow-Signature": f"sha256={sign(hook.secret, body)}",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (URL is tenant-configured)
            delivery.status_code = resp.status
            delivery.success = 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        delivery.status_code = exc.code
        delivery.success = False
        delivery.error = f"HTTP {exc.code}"
    except Exception as exc:  # connection refused, timeout, DNS, etc.
        delivery.success = False
        delivery.error = str(exc)[:400]
    db.add(delivery)
    return delivery


def dispatch(db: Session, organization_id: int, event: str, payload: dict) -> int:
    """Deliver `event` to every active webhook subscribed to it. Returns count."""
    hooks = db.scalars(
        select(Webhook).where(Webhook.organization_id == organization_id, Webhook.is_active.is_(True))
    ).all()
    sent = 0
    for hook in hooks:
        if "*" in hook.events or event in hook.events:
            _deliver_one(db, hook, event, payload)
            sent += 1
    return sent
