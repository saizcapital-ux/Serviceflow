"""Team invitations: invite staff, list/revoke pending invites, and accept.

Inviting is restricted to owners and managers. Accepting is public (the invitee
has no account yet) and authenticated purely by the emailed token.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
)
from app.models import Invitation, Organization, User, UserRole
from app.schemas import (
    InviteAccept,
    InviteCreate,
    InviteLookup,
    InviteOut,
    TokenResponse,
    UserOut,
)
from app.services import audit, notifications

router = APIRouter(prefix="/api/invites", tags=["team"])

INVITE_TTL_DAYS = 7

# Only owners and managers may manage the team.
require_manager = require_roles(UserRole.owner, UserRole.manager)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite may return naive datetimes; treat them as UTC for comparisons."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _status(inv: Invitation) -> str:
    if inv.accepted_at:
        return "accepted"
    if inv.revoked_at:
        return "revoked"
    if _as_aware(inv.expires_at) < _now():
        return "expired"
    return "pending"


def _to_out(inv: Invitation, inviter_name: str | None) -> InviteOut:
    return InviteOut(
        id=inv.id, email=inv.email, role=inv.role, status=_status(inv),
        invited_by_name=inviter_name, expires_at=inv.expires_at,
        accepted_at=inv.accepted_at, created_at=inv.created_at,
    )


@router.get("", response_model=list[InviteOut])
def list_invites(db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """List the org's invitations, newest first."""
    invites = db.scalars(
        select(Invitation)
        .where(Invitation.organization_id == user.organization_id)
        .order_by(Invitation.created_at.desc())
    ).all()
    # Resolve inviter names in one pass.
    inviter_ids = {i.invited_by for i in invites if i.invited_by}
    names: dict[int, str] = {}
    if inviter_ids:
        for u in db.scalars(select(User).where(User.id.in_(inviter_ids))).all():
            names[u.id] = u.full_name
    return [_to_out(i, names.get(i.invited_by)) for i in invites]


@router.post("", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Create + email an invitation for a new staff member."""
    email = payload.email.lower()

    # Already a member of this org?
    existing_user = db.scalar(
        select(User).where(User.organization_id == user.organization_id, User.email == email)
    )
    if existing_user:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with that email is already on your team.")

    # Reuse an outstanding pending invite for the same email instead of duplicating.
    pending = db.scalar(
        select(Invitation).where(
            Invitation.organization_id == user.organization_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    raw_token = generate_token()
    if pending and _status(pending) == "pending":
        invite = pending
        invite.role = payload.role
        invite.token_hash = hash_token(raw_token)
        invite.expires_at = _now() + timedelta(days=INVITE_TTL_DAYS)
        invite.invited_by = user.id
    else:
        invite = Invitation(
            organization_id=user.organization_id, email=email, role=payload.role,
            token_hash=hash_token(raw_token), invited_by=user.id,
            expires_at=_now() + timedelta(days=INVITE_TTL_DAYS),
        )
        db.add(invite)
    db.flush()

    org = db.get(Organization, user.organization_id)
    notifications.notify_invite(
        db, organization_id=user.organization_id, email=email, token=raw_token,
        inviter_name=user.full_name, org_name=org.name if org else "Serviceflow",
        role=payload.role.value,
    )
    audit.record(
        db, organization_id=user.organization_id, actor=user, action="team.invited",
        summary=f"Invited {email} as {payload.role.value}", entity_type="invitation", entity_id=invite.id,
    )
    db.commit()
    db.refresh(invite)
    return _to_out(invite, user.full_name)


@router.post("/{invite_id}/revoke", response_model=InviteOut)
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    invite = db.get(Invitation, invite_id)
    if not invite or invite.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found.")
    if invite.accepted_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "That invitation has already been accepted.")
    if not invite.revoked_at:
        invite.revoked_at = _now()
        audit.record(
            db, organization_id=user.organization_id, actor=user, action="team.invite_revoked",
            summary=f"Revoked invitation for {invite.email}", entity_type="invitation", entity_id=invite.id,
        )
        db.commit()
        db.refresh(invite)
    return _to_out(invite, user.full_name)


def _valid_invite_by_token(db: Session, token: str) -> Invitation:
    invite = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if not invite or _status(invite) != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation link is invalid, revoked, or expired.")
    return invite


@router.get("/accept", response_model=InviteLookup)
def lookup_invite(token: str, db: Session = Depends(get_db)):
    """Public: validate a token and return who/what it's for (for the accept page)."""
    invite = _valid_invite_by_token(db, token)
    org = db.get(Organization, invite.organization_id)
    return InviteLookup(
        email=invite.email, role=invite.role,
        organization_name=org.name if org else "Serviceflow",
    )


@router.post("/accept", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def accept_invite(payload: InviteAccept, db: Session = Depends(get_db)):
    """Public: accept an invitation, creating the staff account, and log them in."""
    invite = _valid_invite_by_token(db, payload.token)

    # Guard against a matching account created between invite and accept.
    if db.scalar(select(User).where(
        User.organization_id == invite.organization_id, User.email == invite.email
    )):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account for this email already exists — try signing in.")

    new_user = User(
        organization_id=invite.organization_id, email=invite.email,
        hashed_password=hash_password(payload.password), full_name=payload.full_name.strip(),
        role=invite.role, is_active=True,
    )
    db.add(new_user)
    invite.accepted_at = _now()
    db.flush()
    audit.record(
        db, organization_id=invite.organization_id, actor=new_user, action="team.invite_accepted",
        summary=f"{new_user.full_name} accepted their invitation", entity_type="user", entity_id=new_user.id,
    )
    db.commit()
    db.refresh(new_user)

    token = create_access_token(new_user.id, {"role": new_user.role.value, "org": new_user.organization_id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(new_user))
