"""Notification service.

Records every notification in the DB and dispatches it through a pluggable
backend. In dev (no SMTP configured) it uses a console backend that logs the
message — so the flow is fully exercised without external services. Wiring a
real provider (SMTP for email, Twilio for SMS) is a config/backend change.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Contact,
    Customer,
    Notification,
    NotificationChannel,
    NotificationStatus,
    WorkOrder,
)

log = logging.getLogger("serviceflow.notifications")


def _dispatch_email(recipient: str, subject: str, body: str) -> None:
    """Send via SMTP if configured, otherwise log (console backend)."""
    if not settings.smtp_host:
        log.info("[email → %s] %s\n%s", recipient, subject, body)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = recipient
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def _dispatch_sms(recipient: str, body: str) -> None:  # pragma: no cover - stub
    """Placeholder for a real SMS provider (e.g. Twilio)."""
    log.info("[sms → %s] %s", recipient, body)


def record_and_send(
    db: Session,
    *,
    organization_id: int,
    recipient: str,
    subject: str,
    body: str,
    channel: NotificationChannel = NotificationChannel.email,
    customer_id: int | None = None,
    work_order_id: int | None = None,
) -> Notification:
    """Persist a Notification and attempt delivery. Never raises to the caller."""
    note = Notification(
        organization_id=organization_id, customer_id=customer_id, work_order_id=work_order_id,
        channel=channel, recipient=recipient, subject=subject, body=body,
        status=NotificationStatus.queued,
    )
    db.add(note)
    db.flush()
    if not settings.notifications_enabled or not recipient:
        note.status = NotificationStatus.queued
        return note
    try:
        if channel == NotificationChannel.sms:
            _dispatch_sms(recipient, body)
        else:
            _dispatch_email(recipient, subject, body)
        note.status = NotificationStatus.sent
        note.sent_at = datetime.now(timezone.utc)
    except Exception as exc:  # delivery failures must not break the request
        note.status = NotificationStatus.failed
        note.error = str(exc)
        log.warning("Notification delivery failed: %s", exc)
    return note


def _customer_email(db: Session, customer_id: int) -> str | None:
    customer = db.get(Customer, customer_id)
    if customer and customer.email:
        return customer.email
    contact = db.scalar(select(Contact).where(Contact.customer_id == customer_id))
    return contact.email if contact else None


def notify_customer_status(db: Session, wo: WorkOrder, message: str) -> None:
    """Email the customer that their repair status changed."""
    email = _customer_email(db, wo.customer_id)
    if not email:
        return
    record_and_send(
        db, organization_id=wo.organization_id, customer_id=wo.customer_id, work_order_id=wo.id,
        recipient=email, subject=f"Update on repair {wo.number}: {message}",
        body=(f"Hello,\n\nThere's an update on your repair {wo.number} ({wo.title}):\n\n"
              f"{message}\n\nLog in to your Serviceflow portal to see the full status and history.\n"),
    )


def notify_quote_sent(db: Session, wo: WorkOrder, quote_number: str, total: float) -> None:
    email = _customer_email(db, wo.customer_id)
    if not email:
        return
    record_and_send(
        db, organization_id=wo.organization_id, customer_id=wo.customer_id, work_order_id=wo.id,
        recipient=email, subject=f"Quote {quote_number} ready for approval — ${total:,.2f}",
        body=(f"Hello,\n\nA quote for repair {wo.number} ({wo.title}) is ready for your approval:\n\n"
              f"Quote {quote_number}: ${total:,.2f}\n\nApprove or decline it in your Serviceflow portal.\n"),
    )
