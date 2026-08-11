"""One-click sample data so a brand-new shop can explore the full workflow.

Loads a single demo customer with a piece of equipment and an in-progress work
order (all tagged with a recognizable marker), and can remove them just as
easily. Owner/manager only, and never touches real records — everything is
scoped to the marked demo customer.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import (
    Contact,
    Customer,
    Equipment,
    EquipmentType,
    EventType,
    Priority,
    ServiceType,
    User,
    UserRole,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)
from app.schemas import SampleDataResult
from app.services import audit, workflow

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# Distinctive account number that marks the demo customer for safe cleanup.
SAMPLE_ACCOUNT = "SAMPLE-DEMO"

require_owner_manager = require_roles(UserRole.owner, UserRole.manager)


def _sample_customer(db: Session, org_id: int) -> Customer | None:
    return db.scalar(
        select(Customer).where(
            Customer.organization_id == org_id, Customer.account_number == SAMPLE_ACCOUNT
        )
    )


@router.post("/sample-data", response_model=SampleDataResult, status_code=status.HTTP_201_CREATED)
def load_sample_data(db: Session = Depends(get_db), user: User = Depends(require_owner_manager)):
    """Create a demo customer + equipment + work order to explore the workflow."""
    org = user.organization_id
    if _sample_customer(db, org):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Sample data is already loaded. Remove it first to reload a fresh copy.",
        )

    customer = Customer(
        organization_id=org,
        name="Riverside Water District (sample)",
        account_number=SAMPLE_ACCOUNT,
        email="maintenance@riverside-water.example",
        phone="(555) 010-4477",
        billing_address="1200 Treatment Plant Rd\nRiverside, CA 92501",
        approval_limit=5000.0,
    )
    db.add(customer)
    db.flush()
    db.add(
        Contact(
            customer_id=customer.id,
            name="Dana Ortiz",
            title="Maintenance Supervisor",
            email="dana.ortiz@riverside-water.example",
            phone="(555) 010-4480",
        )
    )

    equipment = Equipment(
        organization_id=org,
        customer_id=customer.id,
        tag="MTR-DEMO-01",
        equipment_type=EquipmentType.motor,
        manufacturer="Baldor",
        model="EM4400T",
        serial_number="DEMO-SN-88213",
        nameplate_data={"hp": "100", "rpm": "1785", "voltage": "460", "frame": "444T"},
        location="Intake Pump House — Pump #2",
    )
    db.add(equipment)
    db.flush()

    number = workflow.next_work_order_number(db, org)
    wo = WorkOrder(
        organization_id=org,
        number=number,
        customer_id=customer.id,
        equipment_id=equipment.id,
        service_type=ServiceType.shop_repair,
        priority=Priority.high,
        status=WorkOrderStatus.inspection,
        title="Bearing noise & high vibration on intake pump motor",
        problem_description=(
            "Customer reports loud grinding from the drive-end bearing and elevated "
            "vibration under load. Suspect failed bearing; inspect windings while open."
        ),
        promised_date=date.today() + timedelta(days=5),
    )
    db.add(wo)
    db.flush()
    db.add_all(
        [
            WorkOrderEvent(
                work_order_id=wo.id,
                event_type=EventType.status_change,
                to_status=WorkOrderStatus.intake,
                message=f"Work order {number} created and received at intake.",
                created_by=user.id,
                visible_to_customer=True,
            ),
            WorkOrderEvent(
                work_order_id=wo.id,
                event_type=EventType.status_change,
                from_status=WorkOrderStatus.intake,
                to_status=WorkOrderStatus.inspection,
                message="Teardown started — inspecting bearings and windings.",
                created_by=user.id,
                visible_to_customer=True,
            ),
        ]
    )
    audit.record(
        db, organization_id=org, actor=user, action="onboarding.sample_loaded",
        summary="Loaded sample data (demo customer, equipment, work order)",
        entity_type="customer", entity_id=customer.id,
    )
    db.commit()
    return SampleDataResult(
        customer_id=customer.id,
        equipment_id=equipment.id,
        work_order_id=wo.id,
        work_order_number=number,
    )


@router.delete("/sample-data", response_model=SampleDataResult)
def remove_sample_data(db: Session = Depends(get_db), user: User = Depends(require_owner_manager)):
    """Delete the demo customer and everything scoped to it."""
    org = user.organization_id
    customer = _sample_customer(db, org)
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No sample data to remove.")

    work_orders = db.scalars(
        select(WorkOrder).where(
            WorkOrder.organization_id == org, WorkOrder.customer_id == customer.id
        )
    ).all()
    equipment = db.scalars(
        select(Equipment).where(
            Equipment.organization_id == org, Equipment.customer_id == customer.id
        )
    ).all()
    result = SampleDataResult(
        customer_id=customer.id,
        equipment_id=equipment[0].id if equipment else None,
        work_order_id=work_orders[0].id if work_orders else None,
        work_order_number=work_orders[0].number if work_orders else None,
    )
    # Work orders cascade their events/quotes/etc.; equipment has no such cascade
    # to work orders, so remove work orders first, then equipment, then customer.
    for wo in work_orders:
        db.delete(wo)
    for eq in equipment:
        db.delete(eq)
    db.delete(customer)
    audit.record(
        db, organization_id=org, actor=user, action="onboarding.sample_removed",
        summary="Removed sample data", entity_type="customer", entity_id=customer.id,
    )
    db.commit()
    return result
