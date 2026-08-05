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
    User,
    UserRole,
    WorkOrder,
)

log = logging.getLogger("serviceflow.notifications")


def _dispatch_email(recipient: str, subject: str, body: str) -> None:
    """Send via SMTP if configured, otherwise log (console backend).

    Supports both implicit TLS (SMTP_SSL, port 465) and STARTTLS (port 587),
    with a connection timeout so a slow mail server can't hang a request.
    """
    if not settings.smtp_host:
        log.info("[email → %s] %s\n%s", recipient, subject, body)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = recipient
    if settings.smtp_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout)
    with server:
        if not settings.smtp_ssl:
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


# Staff roles that triage inbound work at intake.
_INTAKE_ROLES = (UserRole.owner, UserRole.manager, UserRole.service_writer)


def _notify_intake_staff(db: Session, wo: WorkOrder, subject: str, body: str) -> None:
    """Fan a notification out to every active intake-role user in the org."""
    staff = db.scalars(
        select(User).where(
            User.organization_id == wo.organization_id,
            User.role.in_(_INTAKE_ROLES),
            User.is_active.is_(True),
        )
    ).all()
    for member in staff:
        if not member.email:
            continue
        record_and_send(
            db, organization_id=wo.organization_id, customer_id=wo.customer_id, work_order_id=wo.id,
            recipient=member.email, subject=subject, body=body,
        )


def notify_staff_new_request(db: Session, wo: WorkOrder, customer_name: str) -> None:
    """Email the shop's intake staff that a customer submitted a new service request."""
    _notify_intake_staff(
        db, wo,
        subject=f"New service request {wo.number} from {customer_name}",
        body=(f"A customer submitted a repair request through the portal:\n\n"
              f"  Work order: {wo.number}\n  Customer:   {customer_name}\n"
              f"  Priority:   {wo.priority.value}\n  Problem:    {wo.title}\n\n"
              f"It's waiting at intake in Serviceflow — review and schedule the inspection.\n"),
    )


def notify_staff_request_withdrawn(db: Session, wo: WorkOrder, customer_name: str) -> None:
    """Email the shop's intake staff that a customer withdrew a request before work began."""
    _notify_intake_staff(
        db, wo,
        subject=f"Service request {wo.number} withdrawn by {customer_name}",
        body=(f"{customer_name} withdrew their repair request through the portal before work began:\n\n"
              f"  Work order: {wo.number}\n  Problem:    {wo.title}\n\n"
              f"It has been cancelled. No action is needed.\n"),
    )


def notify_assignment(db: Session, wo: WorkOrder, assignee: User, assigner_name: str) -> None:
    """Notify a staff member that a work order was assigned to them."""
    if not assignee or not assignee.email:
        return
    record_and_send(
        db, organization_id=wo.organization_id, customer_id=wo.customer_id, work_order_id=wo.id,
        recipient=assignee.email,
        subject=f"You've been assigned {wo.number}",
        body=(f"Hi {assignee.full_name},\n\n{assigner_name} assigned you to work order "
              f"{wo.number} ({wo.title}).\n\n"
              f"  Priority: {wo.priority.value}\n"
              f"  Status:   {wo.status.value.replace('_', ' ')}\n\n"
              f"Open it in Serviceflow to get started.\n"),
    )


def notify_invite(
    db: Session,
    *,
    organization_id: int,
    email: str,
    token: str,
    inviter_name: str,
    org_name: str,
    role: str,
) -> None:
    """Email a prospective staff member their invitation link."""
    link = f"{settings.app_base_url}/accept-invite.html?token={token}"
    record_and_send(
        db, organization_id=organization_id, recipient=email,
        subject=f"You're invited to join {org_name} on Serviceflow",
        body=(f"Hello,\n\n{inviter_name} invited you to join {org_name} on Serviceflow "
              f"as a {role.replace('_', ' ')}.\n\n"
              f"Accept the invitation and set your password here:\n{link}\n\n"
              f"This link expires in 7 days. If you weren't expecting this, you can ignore it.\n"),
    )


def notify_password_reset(
    db: Session, *, organization_id: int, email: str, token: str, name: str
) -> None:
    """Email a user a single-use password-reset link."""
    link = f"{settings.app_base_url}/reset-password.html?token={token}"
    record_and_send(
        db, organization_id=organization_id, recipient=email,
        subject="Reset your Serviceflow password",
        body=(f"Hello {name},\n\nWe received a request to reset your Serviceflow password.\n\n"
              f"Set a new password here:\n{link}\n\n"
              f"This link expires in 1 hour. If you didn't request this, you can safely ignore "
              f"this email — your password won't change.\n"),
    )


def notify_staff_customer_message(db: Session, wo: WorkOrder, customer_name: str, message: str) -> None:
    """Email the shop's intake staff that a customer replied on a work order."""
    excerpt = message if len(message) <= 240 else message[:237] + "…"
    _notify_intake_staff(
        db, wo,
        subject=f"New message on {wo.number} from {customer_name}",
        body=(f"{customer_name} posted a message on work order {wo.number} ({wo.title}):\n\n"
              f"  \"{excerpt}\"\n\n"
              f"Open it in Serviceflow to reply.\n"),
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
