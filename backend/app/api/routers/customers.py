"""Customer & equipment management (staff only)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_staff
from app.core.config import settings
from app.core.database import get_db
from app.models import (
    Contact,
    Customer,
    Equipment,
    EquipmentSpecField,
    Location,
    Organization,
    User,
    WorkOrder,
)
from app.services.pdf import render_equipment_spec_sheet
from app.schemas import (
    ContactCreate,
    ContactOut,
    CustomerCreate,
    CustomerOut,
    EquipmentCreate,
    EquipmentOut,
    EquipmentUpdate,
)
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


@router.post("/customers/{customer_id}/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def add_contact(customer_id: int, payload: ContactCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    customer = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == user.organization_id)
    )
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    contact = Contact(customer_id=customer_id, **payload.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/equipment", response_model=list[EquipmentOut])
def list_equipment(
    customer_id: int | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(Equipment).where(
        Equipment.organization_id == user.organization_id, Equipment.is_active.is_(True)
    )
    if customer_id:
        stmt = stmt.where(Equipment.customer_id == customer_id)
    if location_id:
        stmt = stmt.where(Equipment.location_id == location_id)
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


@router.patch("/equipment/{equipment_id}", response_model=EquipmentOut)
def update_equipment(
    equipment_id: int, payload: EquipmentUpdate,
    db: Session = Depends(get_db), user: User = Depends(require_staff),
):
    equipment = db.scalar(
        select(Equipment).where(
            Equipment.id == equipment_id, Equipment.organization_id == user.organization_id
        )
    )
    if not equipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("location_id"):
        loc = db.get(Location, fields["location_id"])
        if not loc or loc.organization_id != user.organization_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found.")
    for field, value in fields.items():
        setattr(equipment, field, value)
    db.commit()
    db.refresh(equipment)
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


@router.get("/equipment/{equipment_id}/spec-sheet.pdf")
def equipment_spec_sheet(equipment_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Printable one-page asset spec sheet (identity, specs, repair history)."""
    equipment = db.scalar(
        select(Equipment).where(
            Equipment.id == equipment_id, Equipment.organization_id == user.organization_id
        )
    )
    if not equipment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    org = db.get(Organization, user.organization_id)
    customer = db.get(Customer, equipment.customer_id)
    spec_fields = [
        (f.label, f.unit) for f in db.scalars(
            select(EquipmentSpecField).where(
                EquipmentSpecField.organization_id == user.organization_id,
                EquipmentSpecField.equipment_type == equipment.equipment_type.value,
            ).order_by(EquipmentSpecField.position, EquipmentSpecField.id)
        ).all()
    ]
    history = db.scalars(
        select(WorkOrder).where(
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.equipment_id == equipment_id,
        ).order_by(WorkOrder.created_at.desc())
    ).all()
    pdf = render_equipment_spec_sheet(
        org=org, equipment=equipment, customer=customer, spec_fields=spec_fields, history=history
    )
    fname = f"spec-{equipment.tag or equipment.serial_number or equipment.id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})
