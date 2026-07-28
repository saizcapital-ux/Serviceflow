"""Seed the database with a realistic demo tenant.

Run:  python -m app.seed
Creates one service center, staff + a portal customer, equipment, and work
orders spanning the full lifecycle so the UI has something to show.
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Contact,
    Customer,
    Equipment,
    EquipmentType,
    EventType,
    Finding,
    FindingSeverity,
    Organization,
    Priority,
    Quote,
    QuoteLine,
    QuoteStatus,
    ServiceType,
    User,
    UserRole,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderStatus,
)

PW = hash_password("Password123")


def reset() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed() -> None:
    reset()
    db = SessionLocal()
    try:
        org = Organization(name="Apex Rotating Equipment Repair", slug="apex-repair", plan="pro")
        db.add(org)
        db.flush()

        # ---- Staff users ----
        admin = User(organization_id=org.id, email="admin@apexrepair.com", hashed_password=PW,
                     full_name="Dana Okafor", role=UserRole.owner)
        writer = User(organization_id=org.id, email="writer@apexrepair.com", hashed_password=PW,
                      full_name="Marcus Reed", role=UserRole.service_writer)
        tech = User(organization_id=org.id, email="tech@apexrepair.com", hashed_password=PW,
                    full_name="Priya Nair", role=UserRole.technician)
        db.add_all([admin, writer, tech])
        db.flush()

        # ---- Customers ----
        acme = Customer(organization_id=org.id, name="Acme Power & Water", account_number="ACME-001",
                        email="maintenance@acmepower.com", phone="(555) 210-4433",
                        billing_address="1400 Turbine Rd, Houston, TX",
                        shipping_address="1400 Turbine Rd, Dock 3, Houston, TX")
        gulf = Customer(organization_id=org.id, name="Gulf Coast Chemicals", account_number="GULF-014",
                        email="reliability@gulfcoastchem.com", phone="(555) 771-9080",
                        billing_address="88 Refinery Way, Beaumont, TX")
        db.add_all([acme, gulf])
        db.flush()

        db.add_all([
            Contact(customer_id=acme.id, name="Sam Whitfield", title="Reliability Engineer",
                    email="buyer@acmepower.com", phone="(555) 210-4400"),
            Contact(customer_id=gulf.id, name="Lena Brooks", title="Maintenance Planner",
                    email="lena.brooks@gulfcoastchem.com", phone="(555) 771-9001"),
        ])

        # ---- Portal user (scoped to Acme) ----
        db.add(User(organization_id=org.id, email="buyer@acmepower.com", hashed_password=PW,
                    full_name="Sam Whitfield", role=UserRole.customer, customer_id=acme.id))

        # ---- Equipment ----
        motor = Equipment(organization_id=org.id, customer_id=acme.id, tag="MTR-4471",
                          equipment_type=EquipmentType.motor, manufacturer="Siemens", model="1LE2",
                          serial_number="SN-MTR-88213",
                          nameplate_data={"hp": 250, "rpm": 1785, "voltage": "460V", "frame": "449T"},
                          location="Cooling Tower Bay 2")
        limitorque = Equipment(organization_id=org.id, customer_id=acme.id, tag="VLV-0092",
                               equipment_type=EquipmentType.actuator, manufacturer="Limitorque",
                               model="SMB-000", serial_number="SN-LMT-33019",
                               nameplate_data={"torque_ft_lb": 500, "valve_size_in": 12, "class": "600#"},
                               location="Feedwater Header")
        pump = Equipment(organization_id=org.id, customer_id=gulf.id, tag="PMP-1180",
                         equipment_type=EquipmentType.pump, manufacturer="Goulds", model="3196",
                         serial_number="SN-PMP-55127",
                         nameplate_data={"flow_gpm": 800, "head_ft": 220, "seal": "double mechanical"},
                         location="Unit 5 Transfer")
        blower = Equipment(organization_id=org.id, customer_id=gulf.id, tag="BLW-2030",
                           equipment_type=EquipmentType.blower, manufacturer="Gardner Denver",
                           model="RBDH", serial_number="SN-BLW-77410",
                           nameplate_data={"cfm": 1200, "psi": 12}, location="Wastewater Aeration")
        db.add_all([motor, limitorque, pump, blower])
        db.flush()

        today = date.today()

        def make_wo(number, customer, equipment, title, problem, status_path, service_type,
                    priority, assigned=None, promised_offset=7):
            wo = WorkOrder(
                organization_id=org.id, number=number, customer_id=customer.id,
                equipment_id=equipment.id if equipment else None, service_type=service_type,
                priority=priority, status=status_path[-1], title=title, problem_description=problem,
                assigned_to=assigned.id if assigned else None,
                promised_date=today + timedelta(days=promised_offset),
            )
            db.add(wo)
            db.flush()
            prev = None
            for i, st in enumerate(status_path):
                db.add(WorkOrderEvent(
                    work_order_id=wo.id, event_type=EventType.status_change, from_status=prev,
                    to_status=st, created_by=(writer.id if i == 0 else tech.id), visible_to_customer=True,
                    message=f"Status set to {st.value.replace('_', ' ')}.",
                ))
                prev = st
            return wo

        # 1) Motor rewind — in repair
        wo1 = make_wo("WO-2026-0001", acme, motor,
                      "250HP motor failed to start — suspected winding fault",
                      "Motor tripped on overcurrent. Megger reads low. Customer requests rewind evaluation.",
                      [WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.quote_pending,
                       WorkOrderStatus.approved, WorkOrderStatus.in_repair],
                      ServiceType.shop_repair, Priority.high, assigned=tech)
        db.add_all([
            Finding(work_order_id=wo1.id, title="Grounded winding, phase B", severity=FindingSeverity.critical,
                    detail="Insulation resistance 0.2 MΩ. Burned turns visible at slot 14.", created_by=tech.id),
            Finding(work_order_id=wo1.id, title="Bearings within spec", severity=FindingSeverity.info,
                    detail="DE/NDE bearings show minimal wear; recommend replacement during rewind.",
                    created_by=tech.id),
        ])
        q1 = Quote(work_order_id=wo1.id, number="WO-2026-0001-Q1", status=QuoteStatus.approved,
                   valid_until=today + timedelta(days=30))
        db.add(q1); db.flush()
        q1.lines = [
            QuoteLine(quote_id=q1.id, kind="labor", description="Complete rewind, 250HP stator",
                      quantity=40, unit_price=145, line_total=5800),
            QuoteLine(quote_id=q1.id, kind="part", description="Magnet wire & insulation kit",
                      quantity=1, unit_price=2200, line_total=2200),
            QuoteLine(quote_id=q1.id, kind="part", description="DE/NDE bearing set (6314/6314)",
                      quantity=1, unit_price=480, line_total=480),
        ]
        q1.subtotal = 8480; q1.tax = 700; q1.total = 9180
        wo1.total_estimate = 9180
        db.add(WorkOrderEvent(work_order_id=wo1.id, event_type=EventType.quote_decision,
                              message="Quote WO-2026-0001-Q1 approved by customer.", visible_to_customer=True))

        # 2) Limitorque actuator — awaiting customer approval
        wo2 = make_wo("WO-2026-0002", acme, limitorque,
                      "Limitorque SMB actuator not reaching full travel",
                      "Actuator stalls at ~70% open. Torque switch suspected. Bench test requested.",
                      [WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.quote_pending],
                      ServiceType.shop_repair, Priority.normal, assigned=tech)
        q2 = Quote(work_order_id=wo2.id, number="WO-2026-0002-Q1", status=QuoteStatus.sent,
                   valid_until=today + timedelta(days=21))
        db.add(q2); db.flush()
        q2.lines = [
            QuoteLine(quote_id=q2.id, kind="labor", description="Disassemble, inspect, rebuild gear train",
                      quantity=12, unit_price=135, line_total=1620),
            QuoteLine(quote_id=q2.id, kind="part", description="Torque switch assembly",
                      quantity=1, unit_price=340, line_total=340),
            QuoteLine(quote_id=q2.id, kind="part", description="Seal & gasket kit", quantity=1,
                      unit_price=95, line_total=95),
        ]
        q2.subtotal = 2055; q2.tax = 169.54; q2.total = 2224.54
        db.add(WorkOrderEvent(work_order_id=wo2.id, event_type=EventType.quote_sent,
                              message="Quote WO-2026-0002-Q1 issued: $2,224.54.", visible_to_customer=True))

        # 3) Pump — field service scheduled
        wo3 = make_wo("WO-2026-0003", gulf, pump,
                      "On-site vibration analysis & alignment — 3196 transfer pump",
                      "Elevated vibration reported at Unit 5. Dispatch tech for field diagnosis and laser alignment.",
                      [WorkOrderStatus.intake],
                      ServiceType.field_service, Priority.rush, assigned=tech, promised_offset=2)
        wo3.scheduled_at = None
        db.add(WorkOrderEvent(work_order_id=wo3.id, event_type=EventType.field_visit,
                              message="Field visit scheduled for Unit 5.", visible_to_customer=True))

        # 4) Blower — ready to ship
        make_wo("WO-2026-0004", gulf, blower,
                "Rotary blower overhaul — bearing & timing gear replacement",
                "Scheduled overhaul. Replace bearings, timing gears, reset clearances, performance test.",
                [WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.quote_pending,
                 WorkOrderStatus.approved, WorkOrderStatus.in_repair, WorkOrderStatus.testing,
                 WorkOrderStatus.ready],
                ServiceType.shop_repair, Priority.normal, assigned=tech, promised_offset=1)

        # 5) Older closed motor job (history)
        make_wo("WO-2025-0288", acme, motor,
                "Annual PM — 250HP motor bearing greasing & testing",
                "Routine preventive maintenance and surge test.",
                [WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.in_repair,
                 WorkOrderStatus.testing, WorkOrderStatus.ready, WorkOrderStatus.shipped,
                 WorkOrderStatus.closed],
                ServiceType.shop_repair, Priority.low, assigned=tech, promised_offset=-30)

        db.commit()
        print("Seed complete.")
        print("  Staff:    admin@apexrepair.com / writer@apexrepair.com / tech@apexrepair.com")
        print("  Customer: buyer@acmepower.com")
        print("  Password (all): Password123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
