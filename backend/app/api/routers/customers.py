"""Customer & equipment management (staff only)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_staff
from app.core.config import settings
from app.core.database import get_db
from app.models import Customer, Equipment, User
from app.schemas import CustomerCreate, CustomerOut, EquipmentCreate, EquipmentOut
from app.services.qr import qr_svg

router = APIRouter(prefix="/api", tags=["customers"])


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    q: str | None = Query(None, description="Search by name or account number"),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = (
        select(Customer)
        .where(Customer.organization_id == user.organization_id, Customer.is_active.is_(True))
        .options(selectinload(Customer.contacts))
        .order_by(Customer.name)
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Customer.name.ilike(like)) | (Customer.account_number.ilike(like)))
    return db.scalars(stmt).all()


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    exists = db.scalar(
        select(Customer).where(
            Customer.organization_id == user.organization_id,
            Customer.account_number == payload.account_number,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "That account number is already in use.")
    customer = Customer(organization_id=user.organization_id, **payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id, Customer.organization_id == user.organization_id)
        .options(selectinload(Customer.contacts))
    )
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    return customer


@router.get("/equipment", response_model=list[EquipmentOut])
def list_equipment(
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(Equipment).where(
        Equipment.organization_id == user.organization_id, Equipment.is_active.is_(True)
    )
    if customer_id:
        stmt = stmt.where(Equipment.customer_id == customer_id)
    return db.scalars(stmt.order_by(Equipment.created_at.desc())).all()


@router.post("/equipment", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id, Customer.organization_id == user.organization_id
        )
    )
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    equipment = Equipment(organization_id=user.organization_id, **payload.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.get("/equipment/{equipment_id}", response_model=EquipmentOut)
def get_equipment(equipment_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    equipment = db.scalar(
        select(Equipment).where(
            Equipment.id == equipment_id, Equipment.organization_id == user.organization_id
        )
    )
    if not equipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    return equipment


@router.get("/equipment/{equipment_id}/qr.svg")
def equipment_qr(equipment_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """SVG QR code that deep-links to this asset (scan to open its history)."""
    equipment = db.scalar(
        select(Equipment).where(
            Equipment.id == equipment_id, Equipment.organization_id == user.organization_id
        )
    )
    if not equipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    url = f"{settings.app_base_url}/app/#/equipment/{equipment_id}"
    return Response(content=qr_svg(url), media_type="image/svg+xml")
