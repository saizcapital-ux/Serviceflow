"""Team endpoints: staff directory (for assignment dropdowns) and member
management (role changes, activate/deactivate) for owners and managers."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.core.database import get_db
from app.models import User, UserRole
from app.schemas import TeamMemberOut, TeamMemberUpdate, UserSummary
from app.services import audit

router = APIRouter(prefix="/api/users", tags=["team"])

# Team administration is limited to owners and managers.
require_manager = require_roles(UserRole.owner, UserRole.manager)


@router.get("", response_model=list[UserSummary])
def list_users(role: UserRole | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    stmt = select(User).where(
        User.organization_id == user.organization_id,
        User.is_active.is_(True),
        User.role != UserRole.customer,
    )
    if role:
        stmt = stmt.where(User.role == role)
    return db.scalars(stmt.order_by(User.full_name)).all()


# ---- Member management (owner/manager) ----
# Mounted on a second router so the path is /api/team/members, not /api/users.
team_router = APIRouter(prefix="/api/team", tags=["team"])


@team_router.get("/members", response_model=list[TeamMemberOut])
def list_members(db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """All staff (active and inactive) in the org, for management."""
    members = db.scalars(
        select(User).where(
            User.organization_id == user.organization_id,
            User.role != UserRole.customer,
        ).order_by(User.is_active.desc(), User.full_name)
    ).all()
    return members


def _active_owner_count(db: Session, organization_id: int, *, exclude_id: int) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.role == UserRole.owner,
            User.is_active.is_(True),
            User.id != exclude_id,
        )
    ) or 0


@team_router.patch("/members/{member_id}", response_model=TeamMemberOut)
def update_member(
    member_id: int,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Change a teammate's role and/or active status, with safety guards."""
    target = db.get(User, member_id)
    if not target or target.organization_id != user.organization_id or target.role == UserRole.customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found.")
    if target.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "You can't change your own role or status here — use Account settings.")

    new_role = payload.role if payload.role is not None else target.role
    new_active = payload.is_active if payload.is_active is not None else target.is_active

    # Managers may not administer owners or grant the owner role.
    if user.role == UserRole.manager and (target.role == UserRole.owner or new_role == UserRole.owner):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an owner can manage owners.")

    # Never leave the organization without an active owner.
    demoting_owner = target.role == UserRole.owner and new_role != UserRole.owner
    deactivating_owner = target.role == UserRole.owner and not new_active
    if (demoting_owner or deactivating_owner) and _active_owner_count(
        db, user.organization_id, exclude_id=target.id
    ) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The organization must have at least one active owner.")

    changes = []
    if payload.role is not None and payload.role != target.role:
        changes.append(f"role {target.role.value} → {payload.role.value}")
        target.role = payload.role
    if payload.is_active is not None and payload.is_active != target.is_active:
        changes.append("reactivated" if payload.is_active else "deactivated")
        target.is_active = payload.is_active

    if changes:
        audit.record(
            db, organization_id=user.organization_id, actor=user, action="team.member_updated",
            summary=f"{target.full_name}: " + ", ".join(changes), entity_type="user", entity_id=target.id,
        )
        db.commit()
        db.refresh(target)
    return target
