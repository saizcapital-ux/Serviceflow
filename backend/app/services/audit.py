"""Audit trail helper. Records who did what, when — org-wide.

`record` stages an AuditLog row on the current session (flush, no commit) so it
lands in the same transaction as the action it describes. It never raises.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog, User

log = logging.getLogger("serviceflow.audit")


def record(
    db: Session,
    *,
    organization_id: int,
    actor: User | None,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    meta: dict | None = None,
) -> None:
    try:
        db.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor.id if actor else None,
                actor_label=(actor.full_name or actor.email) if actor else "system",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                meta=meta or {},
            )
        )
        db.flush()
    except Exception as exc:  # auditing must never break the request
        log.warning("Failed to record audit event %s: %s", action, exc)
