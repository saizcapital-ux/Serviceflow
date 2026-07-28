"""SQLAlchemy ORM tables — the single source of truth for the schema."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    EquipmentType,
    EventType,
    FindingSeverity,
    InvoiceStatus,
    NotificationChannel,
    NotificationStatus,
    Priority,
    QuoteStatus,
    ServiceType,
    UserRole,
    WorkOrderStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    # SaaS subscription (billing for Serviceflow itself).
    plan: Mapped[str] = mapped_column(String(40), default="trial")  # trial|starter|pro|enterprise
    subscription_status: Mapped[str] = mapped_column(String(20), default="trialing")  # trialing|active|past_due|canceled
    seats: Mapped[int] = mapped_column(Integer, default=5)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(80))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(80))
    # Internal fully-burdened labor cost per hour, used for job-costing/margin.
    labor_cost_rate: Mapped[float] = mapped_column(Float, default=95.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_user_org_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.technician)
    # Set only for portal users: scopes them to a single customer account.
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="users")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "account_number", name="uq_customer_org_acct"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    billing_address: Mapped[str | None] = mapped_column(Text)
    shipping_address: Mapped[str | None] = mapped_column(Text)
    # Quotes above this amount require a PO / explicit sign-off (null = no limit).
    approval_limit: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contacts: Mapped[list[Contact]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    equipment: Mapped[list[Equipment]] = relationship(back_populates="customer")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    tag: Mapped[str | None] = mapped_column(String(60))
    equipment_type: Mapped[EquipmentType] = mapped_column(Enum(EquipmentType), default=EquipmentType.other)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120), index=True)
    # Nameplate specs vary by type (HP/RPM/voltage for motors, torque/size for valves…).
    nameplate_data: Mapped[dict] = mapped_column(JSON, default=dict)
    location: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="equipment")
    work_orders: Mapped[list[WorkOrder]] = relationship(back_populates="equipment")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_wo_org_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), index=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType), default=ServiceType.shop_repair)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.normal)
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.intake, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem_description: Mapped[str | None] = mapped_column(Text)
    po_number: Mapped[str | None] = mapped_column(String(60))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promised_date: Mapped[date | None] = mapped_column(Date)
    total_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    total_actual: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship()
    equipment: Mapped[Equipment | None] = relationship(back_populates="work_orders")
    events: Mapped[list[WorkOrderEvent]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderEvent.created_at"
    )
    findings: Mapped[list[Finding]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    quotes: Mapped[list[Quote]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    time_entries: Mapped[list[TimeEntry]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    parts_used: Mapped[list[PartUsage]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    checklist_items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="ChecklistItem.position"
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )


class WorkOrderEvent(Base):
    __tablename__ = "work_order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), default=EventType.note)
    from_status: Mapped[WorkOrderStatus | None] = mapped_column(Enum(WorkOrderStatus))
    to_status: Mapped[WorkOrderStatus | None] = mapped_column(Enum(WorkOrderStatus))
    message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    visible_to_customer: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_order: Mapped[WorkOrder] = relationship(back_populates="events")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity), default=FindingSeverity.info)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_order: Mapped[WorkOrder] = relationship(back_populates="findings")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(Enum(QuoteStatus), default=QuoteStatus.draft)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    valid_until: Mapped[date | None] = mapped_column(Date)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_order: Mapped[WorkOrder] = relationship(back_populates="quotes")
    lines: Mapped[list[QuoteLine]] = relationship(back_populates="quote", cascade="all, delete-orphan")


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="labor")  # labor | part | misc
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    quote: Mapped[Quote] = relationship(back_populates="lines")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_invoice_org_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.sent, index=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_order: Mapped[WorkOrder] = relationship(back_populates="invoices")
    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="labor")  # labor | part | misc
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Optional: restrict the template to one equipment type (null = any).
    equipment_type: Mapped[EquipmentType | None] = mapped_column(Enum(EquipmentType))
    items: Mapped[list] = mapped_column(JSON, default=list)  # list[str] of step labels
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_order: Mapped[WorkOrder] = relationship(back_populates="checklist_items")


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_part_org_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    sku: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    location: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartUsage(Base):
    __tablename__ = "part_usages"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_order: Mapped[WorkOrder] = relationship(back_populates="parts_used")
    part: Mapped[Part] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str] = mapped_column(String(200), default="system")
    action: Mapped[str] = mapped_column(String(60), index=True)  # e.g. work_order.status_changed
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(Enum(NotificationChannel), default=NotificationChannel.email)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus), default=NotificationStatus.queued)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str | None] = mapped_column(Text)
    worked_on: Mapped[date] = mapped_column(Date, default=lambda: date.today())

    work_order: Mapped[WorkOrder] = relationship(back_populates="time_entries")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="document")  # photo|report|nameplate|document
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work_order: Mapped[WorkOrder] = relationship(back_populates="attachments")
