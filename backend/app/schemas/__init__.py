"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    customer_id: int | None = None
    organization_id: int


# ---------- Customers ----------
class ContactOut(ORMModel):
    id: int
    name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None


class CustomerBase(BaseModel):
    name: str
    account_number: str
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    shipping_address: str | None = None
    approval_limit: float | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(ORMModel, CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    contacts: list[ContactOut] = []


# ---------- Equipment ----------
class EquipmentBase(BaseModel):
    customer_id: int
    tag: str | None = None
    equipment_type: EquipmentType = EquipmentType.other
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    nameplate_data: dict = Field(default_factory=dict)
    location: str | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentOut(ORMModel, EquipmentBase):
    id: int
    created_at: datetime


# ---------- Work orders ----------
class WorkOrderCreate(BaseModel):
    customer_id: int
    equipment_id: int | None = None
    service_type: ServiceType = ServiceType.shop_repair
    priority: Priority = Priority.normal
    title: str
    problem_description: str | None = None
    po_number: str | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    promised_date: date | None = None


class WorkOrderUpdate(BaseModel):
    priority: Priority | None = None
    title: str | None = None
    problem_description: str | None = None
    po_number: str | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    promised_date: date | None = None


class StatusChangeRequest(BaseModel):
    status: WorkOrderStatus
    message: str | None = None
    visible_to_customer: bool = True


class EventOut(ORMModel):
    id: int
    event_type: EventType
    from_status: WorkOrderStatus | None = None
    to_status: WorkOrderStatus | None = None
    message: str | None = None
    visible_to_customer: bool
    created_at: datetime


class FindingCreate(BaseModel):
    title: str
    detail: str | None = None
    severity: FindingSeverity = FindingSeverity.info


class FindingOut(ORMModel, FindingCreate):
    id: int
    created_at: datetime


class QuoteLineIn(BaseModel):
    kind: str = "labor"
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0


class QuoteLineOut(ORMModel, QuoteLineIn):
    id: int
    line_total: float


class QuoteCreate(BaseModel):
    lines: list[QuoteLineIn]
    tax_rate: float = 0.0
    valid_until: date | None = None


class QuoteOut(ORMModel):
    id: int
    number: str
    status: QuoteStatus
    subtotal: float
    tax: float
    total: float
    valid_until: date | None = None
    created_at: datetime
    lines: list[QuoteLineOut] = []


class QuoteDecision(BaseModel):
    approve: bool
    note: str | None = None
    po_number: str | None = None


class InvoiceLineOut(ORMModel):
    id: int
    kind: str
    description: str
    quantity: float
    unit_price: float
    line_total: float


class InvoiceOut(ORMModel):
    id: int
    number: str
    status: InvoiceStatus
    subtotal: float
    tax: float
    total: float
    notes: str | None = None
    due_date: date | None = None
    issued_at: datetime
    paid_at: datetime | None = None
    work_order_id: int
    customer_id: int
    lines: list[InvoiceLineOut] = []


class InvoiceCreate(BaseModel):
    """Create an invoice from the work order's approved quote (or all approved lines)."""
    quote_id: int | None = None  # defaults to the most recent approved quote
    due_in_days: int = 30
    notes: str | None = None


class MarkPaid(BaseModel):
    paid: bool = True


class PartBase(BaseModel):
    sku: str
    name: str
    description: str | None = None
    unit_cost: float = 0.0
    unit_price: float = 0.0
    quantity_on_hand: int = 0
    reorder_point: int = 0
    location: str | None = None


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    unit_cost: float | None = None
    unit_price: float | None = None
    quantity_on_hand: int | None = None
    reorder_point: int | None = None
    location: str | None = None


class PartOut(ORMModel, PartBase):
    id: int
    is_active: bool
    created_at: datetime


class PartAdjust(BaseModel):
    delta: int  # +receive / -consume/scrap
    reason: str | None = None


class PartUsageCreate(BaseModel):
    part_id: int
    quantity: int = Field(gt=0)


class PartUsageOut(ORMModel):
    id: int
    part_id: int
    quantity: int
    unit_price: float
    created_at: datetime


class ChecklistTemplateCreate(BaseModel):
    name: str
    equipment_type: EquipmentType | None = None
    items: list[str]


class ChecklistTemplateOut(ORMModel):
    id: int
    name: str
    equipment_type: EquipmentType | None = None
    items: list[str]


class ChecklistItemOut(ORMModel):
    id: int
    label: str
    is_done: bool
    note: str | None = None
    position: int


class ChecklistItemUpdate(BaseModel):
    is_done: bool | None = None
    note: str | None = None


class ApplyTemplate(BaseModel):
    template_id: int


class NotificationOut(ORMModel):
    id: int
    channel: NotificationChannel
    recipient: str
    subject: str
    status: NotificationStatus
    work_order_id: int | None = None
    customer_id: int | None = None
    created_at: datetime
    sent_at: datetime | None = None


class AttachmentOut(ORMModel):
    id: int
    work_order_id: int
    filename: str
    content_type: str | None = None
    kind: str
    created_at: datetime


class TimeEntryCreate(BaseModel):
    hours: float = Field(gt=0)
    note: str | None = None
    worked_on: date | None = None
    user_id: int | None = None  # defaults to the logged-in technician


class TimeEntryOut(ORMModel):
    id: int
    work_order_id: int
    user_id: int
    hours: float
    note: str | None = None
    worked_on: date


class CostingSummary(BaseModel):
    logged_hours: float
    labor_rate: float
    labor_cost: float
    estimate: float           # approved quote total (revenue)
    invoiced: float
    margin: float             # estimate - labor_cost
    margin_pct: float | None  # margin / estimate


class PlanOut(BaseModel):
    id: str
    name: str
    price_monthly: int
    seats: int
    features: list[str]


class SubscriptionOut(ORMModel):
    plan: str
    subscription_status: str
    seats: int
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None


class CheckoutRequest(BaseModel):
    plan_id: str


class UserSummary(ORMModel):
    id: int
    full_name: str
    role: UserRole


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    assigned_to: int | None = None
    notify_customer: bool = True


class WorkOrderSummary(ORMModel):
    id: int
    number: str
    title: str
    status: WorkOrderStatus
    priority: Priority
    service_type: ServiceType
    customer_id: int
    equipment_id: int | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    promised_date: date | None = None
    total_estimate: float
    created_at: datetime
    updated_at: datetime


class WorkOrderDetail(WorkOrderSummary):
    problem_description: str | None = None
    po_number: str | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    total_actual: float
    customer: CustomerOut | None = None
    equipment: EquipmentOut | None = None
    events: list[EventOut] = []
    findings: list[FindingOut] = []
    quotes: list[QuoteOut] = []
    invoices: list[InvoiceOut] = []
    time_entries: list[TimeEntryOut] = []
    attachments: list[AttachmentOut] = []
    parts_used: list[PartUsageOut] = []
    checklist_items: list[ChecklistItemOut] = []


# ---------- Dashboard ----------
class StatusCount(BaseModel):
    status: WorkOrderStatus
    count: int


class DashboardStats(BaseModel):
    open_work_orders: int
    rush_jobs: int
    awaiting_approval: int
    ready_to_ship: int
    field_visits_scheduled: int
    by_status: list[StatusCount]
    recent: list[WorkOrderSummary]


TokenResponse.model_rebuild()
