"""Locations within a tenant (multi-site support)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.core.database import get_db
from app.models import Location, User, UserRole
from app.schemas import LocationCreate, LocationOut

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return db.scalars(
        select(Location)
        .where(Location.organization_id == user.organization_id, Location.is_active.is_(True))
        .order_by(Location.name)
    ).all()


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.owner, UserRole.manager)),
):
    if db.scalar(select(Location).where(
        Location.organization_id == user.organization_id, Location.code == payload.code
    )):
        raise HTTPException(status.HTTP_409_CONFLICT, "That location code already exists.")
    loc = Location(organization_id=user.organization_id, **payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc
