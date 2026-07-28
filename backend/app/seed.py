"""Seed the database with a realistic demo tenant.

Run:  python -m app.seed
Creates one service center, staff + a portal customer, equipment, and work
orders spanning the full lifecycle so the UI has something to show.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Attachment,
    ChecklistItem,
    ChecklistTemplate,
    Contact,
    Customer,
    Equipment,
    EquipmentType,
    EventType,
    Finding,
    FindingSeverity,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Organization,
    Part,
    Priority,
    Quote,
    QuoteLine,
    QuoteStatus,
    ServiceType,
    TimeEntry,
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
        org = Organization(
            name="Apex Rotating Equipment Repair", slug="apex-repair", plan="pro",
            subscription_status="active", seats=20,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=24),
            trial_ends_at=datetime.now(timezone.utc) - timedelta(days=6),
        )
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
                        shipping_address="1400 Turbine Rd, Dock 3, Houston, TX",
                        approval_limit=2000.0)
        gulf = Customer(organization_id=org.id, name="Gulf Coast Chemicals", account_number="GULF-014",
                        email="reliability@gulfcoastchem.com", phone="(555) 771-9080",
                        billing_address="88 Refinery Way, Beaumont, TX",
                        approval_limit=10000.0)
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
        db.add_all([
            TimeEntry(work_order_id=wo1.id, user_id=tech.id, hours=6.5,
                      note="Teardown, strip old winding, clean core", worked_on=today - timedelta(days=2)),
            TimeEntry(work_order_id=wo1.id, user_id=tech.id, hours=8.0,
                      note="Rewind stator, connect & lace", worked_on=today - timedelta(days=1)),
        ])
        # Demo attachment: a nameplate image stored via the storage backend.
        from app.services.storage import make_key, storage  # local import to avoid import cycles at module load
        nameplate_svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='420' height='260'>"
            "<rect width='420' height='260' fill='#12314f'/>"
            "<rect x='12' y='12' width='396' height='236' fill='none' stroke='#5aa0e6' stroke-width='2'/>"
            "<text x='210' y='46' fill='#fff' font-family='Arial' font-size='20' font-weight='bold' "
            "text-anchor='middle'>SIEMENS 1LE2</text>"
            "<text x='30' y='96' fill='#cfe0f2' font-family='monospace' font-size='16'>HP: 250   RPM: 1785</text>"
            "<text x='30' y='128' fill='#cfe0f2' font-family='monospace' font-size='16'>VOLTS: 460   FRAME: 449T</text>"
            "<text x='30' y='160' fill='#cfe0f2' font-family='monospace' font-size='16'>S/N: SN-MTR-88213</text>"
            "<text x='30' y='210' fill='#f59e0b' font-family='Arial' font-size='14'>Nameplate photo (demo)</text></svg>"
        )
        key = make_key(org.id, wo1.id, "nameplate.svg")
        storage.save(key, nameplate_svg.encode())
        db.add(Attachment(work_order_id=wo1.id, filename="nameplate.svg", content_type="image/svg+xml",
                          url=key, kind="nameplate", uploaded_by=tech.id))

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
        db.add_all([
            Notification(organization_id=org.id, customer_id=acme.id, work_order_id=wo2.id,
                         channel=NotificationChannel.email, recipient="buyer@acmepower.com",
                         subject="Quote WO-2026-0002-Q1 ready for approval — $2,224.54",
                         body="A quote is ready for your approval in the portal.",
                         status=NotificationStatus.sent, sent_at=datetime.now(timezone.utc) - timedelta(hours=3)),
            Notification(organization_id=org.id, customer_id=acme.id, work_order_id=wo1.id,
                         channel=NotificationChannel.email, recipient="buyer@acmepower.com",
                         subject="Update on repair WO-2026-0001: In repair",
                         body="Your 250HP motor rewind is now in progress.",
                         status=NotificationStatus.sent, sent_at=datetime.now(timezone.utc) - timedelta(hours=1)),
        ])

        # 3) Pump — field service scheduled
        wo3 = make_wo("WO-2026-0003", gulf, pump,
                      "On-site vibration analysis & alignment — 3196 transfer pump",
                      "Elevated vibration reported at Unit 5. Dispatch tech for field diagnosis and laser alignment.",
                      [WorkOrderStatus.intake],
                      ServiceType.field_service, Priority.rush, assigned=tech, promised_offset=2)
        wo3.scheduled_at = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=2)
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

        # 5) Older closed motor job (history) — invoiced & paid
        wo5 = make_wo("WO-2025-0288", acme, motor,
                      "Annual PM — 250HP motor bearing greasing & testing",
                      "Routine preventive maintenance and surge test.",
                      [WorkOrderStatus.intake, WorkOrderStatus.inspection, WorkOrderStatus.in_repair,
                       WorkOrderStatus.testing, WorkOrderStatus.ready, WorkOrderStatus.shipped,
                       WorkOrderStatus.closed],
                      ServiceType.shop_repair, Priority.low, assigned=tech, promised_offset=-30)
        inv = Invoice(organization_id=org.id, number="INV-2025-0031", work_order_id=wo5.id,
                      customer_id=acme.id, status=InvoiceStatus.paid, subtotal=640, tax=52.80,
                      total=692.80, due_date=today - timedelta(days=15),
                      issued_at=datetime.now(timezone.utc) - timedelta(days=48),
                      paid_at=datetime.now(timezone.utc) - timedelta(days=20),
                      notes="Net 30. Thank you.")
        db.add(inv); db.flush()
        inv.lines = [
            InvoiceLine(invoice_id=inv.id, kind="labor", description="Preventive maintenance & surge test",
                        quantity=4, unit_price=135, line_total=540),
            InvoiceLine(invoice_id=inv.id, kind="part", description="Bearing grease & consumables",
                        quantity=1, unit_price=100, line_total=100),
        ]
        wo5.total_actual = 692.80

        # Checklist templates (travelers) + apply the motor one to WO-2026-0001.
        motor_tmpl = ChecklistTemplate(
            organization_id=org.id, name="Motor rewind traveler", equipment_type=EquipmentType.motor,
            items=["Incoming inspection & photos", "Record nameplate data", "Megger / surge test",
                   "Strip & clean core", "Rewind stator", "VPI / bake", "Reassemble & align",
                   "Run test & vibration check", "Final QC sign-off"])
        pump_tmpl = ChecklistTemplate(
            organization_id=org.id, name="Pump overhaul traveler", equipment_type=EquipmentType.pump,
            items=["Disassemble & inspect", "Measure clearances", "Replace bearings & seals",
                   "Balance impeller", "Reassemble", "Hydro / performance test", "Final QC sign-off"])
        db.add_all([motor_tmpl, pump_tmpl])
        db.flush()
        for i, label in enumerate(motor_tmpl.items):
            db.add(ChecklistItem(work_order_id=wo1.id, label=label, position=i,
                                 is_done=i < 5))  # first 5 steps done on the in-repair job

        # Parts / inventory catalog (one intentionally below reorder point).
        db.add_all([
            Part(organization_id=org.id, sku="BRG-6314", name="Bearing 6314 (DE)",
                 description="Deep-groove ball bearing, 70mm bore", unit_cost=32.0, unit_price=68.0,
                 quantity_on_hand=24, reorder_point=8, location="Bin A-12"),
            Part(organization_id=org.id, sku="BRG-6314N", name="Bearing 6314 (NDE)",
                 description="Deep-groove ball bearing, insulated", unit_cost=41.0, unit_price=86.0,
                 quantity_on_hand=6, reorder_point=8, location="Bin A-13"),
            Part(organization_id=org.id, sku="MW-14AWG", name="Magnet wire 14 AWG (lb)",
                 description="Class H magnet wire", unit_cost=9.5, unit_price=18.0,
                 quantity_on_hand=140, reorder_point=50, location="Rack C"),
            Part(organization_id=org.id, sku="SEAL-KIT-3196", name="Seal kit — Goulds 3196",
                 description="Mechanical seal rebuild kit", unit_cost=120.0, unit_price=260.0,
                 quantity_on_hand=3, reorder_point=4, location="Bin D-04"),
            Part(organization_id=org.id, sku="TQ-SW-SMB", name="Limitorque torque switch",
                 description="SMB torque switch assembly", unit_cost=180.0, unit_price=340.0,
                 quantity_on_hand=5, reorder_point=2, location="Bin E-01"),
        ])

        db.flush()
        # Backdate the closed job's start so turnaround reads realistically
        # (updated_at is refreshed to ~now on commit via onupdate).
        wo5.created_at = datetime.now(timezone.utc) - timedelta(days=9)

        db.commit()
        print("Seed complete.")
        print("  Staff:    admin@apexrepair.com / writer@apexrepair.com / tech@apexrepair.com")
        print("  Customer: buyer@acmepower.com")
        print("  Password (all): Password123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
