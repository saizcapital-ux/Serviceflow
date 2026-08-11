"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

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


class SignupRequest(BaseModel):
    """Self-serve registration: creates a new organization + its owner."""
    organization_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


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


# ---------- Team invitations ----------
# Staff roles an owner/manager may invite. Portal customers aren't invited here.
_INVITABLE_ROLES = {UserRole.owner, UserRole.manager, UserRole.service_writer, UserRole.technician}


class InviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.technician

    @field_validator("role")
    @classmethod
    def _staff_role_only(cls, v: UserRole) -> UserRole:
        if v not in _INVITABLE_ROLES:
            raise ValueError("You can only invite staff roles (owner, manager, service_writer, technician).")
        return v


class InviteOut(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    status: str  # pending | accepted | revoked | expired
    invited_by_name: str | None = None
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InviteLookup(BaseModel):
    """Public details shown on the accept-invite page for a valid token."""
    email: EmailStr
    role: UserRole
    organization_name: str


class InviteAccept(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class SpecFieldCreate(BaseModel):
    equipment_type: EquipmentType
    label: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=20)
    position: int = 0

    @field_validator("equipment_type", mode="before")
    @classmethod
    def _coerce_type(cls, v):
        return v.value if isinstance(v, EquipmentType) else v


class SpecFieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=20)
    position: int | None = None


class SpecFieldOut(ORMModel):
    id: int
    equipment_type: EquipmentType
    label: str
    unit: str | None = None
    position: int


_TEST_RESULTS = {"pending", "pass", "fail", "na"}


class TestTemplateItemCreate(BaseModel):
    equipment_type: EquipmentType
    label: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=20)
    position: int = 0

    @field_validator("equipment_type", mode="before")
    @classmethod
    def _coerce_type(cls, v):
        return v.value if isinstance(v, EquipmentType) else v


class TestTemplateItemUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=20)
    position: int | None = None


class TestTemplateItemOut(ORMModel):
    id: int
    equipment_type: EquipmentType
    label: str
    unit: str | None = None
    position: int


class TestResultOut(ORMModel):
    id: int
    label: str
    unit: str | None = None
    value: str | None = None
    result: str
    notes: str | None = None
    position: int


class TestResultUpdate(BaseModel):
    value: str | None = Field(default=None, max_length=120)
    result: str | None = None
    notes: str | None = None

    @field_validator("result")
    @classmethod
    def _valid_result(cls, v):
        if v is not None and v not in _TEST_RESULTS:
            raise ValueError("result must be one of: pending, pass, fail, na")
        return v


class TestReportOut(BaseModel):
    overall: str  # none | in_progress | passed | failed
    items: list[TestResultOut]


class TeamMemberOut(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool


class TeamMemberUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _staff_role_only(cls, v: UserRole | None) -> UserRole | None:
        if v is not None and v not in _INVITABLE_ROLES:
            raise ValueError("Role must be a staff role (owner, manager, service_writer, technician).")
        return v


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


# ---------- Customers ----------
class LocationCreate(BaseModel):
    name: str
    code: str
    address: str | None = None


class LocationOut(ORMModel):
    id: int
    name: str
    code: str
    address: str | None = None
    is_active: bool


class ContactOut(ORMModel):
    id: int
    name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None


class ContactCreate(BaseModel):
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
    location_id: int | None = None
    tag: str | None = None
    equipment_type: EquipmentType = EquipmentType.other
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    nameplate_data: dict = Field(default_factory=dict)
    location: str | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    tag: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    location: str | None = None
    location_id: int | None = None
    nameplate_data: dict | None = None


class EquipmentOut(ORMModel, EquipmentBase):
    id: int
    created_at: datetime


# ---------- Work orders ----------
class WorkOrderCreate(BaseModel):
    customer_id: int
    equipment_id: int | None = None
    location_id: int | None = None
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
    location_id: int | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    promised_date: date | None = None


class StatusChangeRequest(BaseModel):
    status: WorkOrderStatus
    message: str | None = None
    visible_to_customer: bool = True


class NoteCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    visible_to_customer: bool = False


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


class PortalMessageCreate(BaseModel):
    """A message a customer posts on one of their work orders."""
    message: str = Field(min_length=1, max_length=2000)


class ServiceRequestCreate(BaseModel):
    """A repair request submitted by a customer through the portal."""
    equipment_id: int | None = None
    title: str
    problem_description: str | None = None
    priority: Priority = Priority.normal
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


class ApiKeyOut(ORMModel):
    id: int
    name: str
    prefix: str
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyCreated(ApiKeyOut):
    key: str  # full key, shown only once


class WebhookCreate(BaseModel):
    url: str
    events: list[str] = ["*"]


class WebhookDeliveryOut(ORMModel):
    id: int
    event: str
    status_code: int | None = None
    success: bool
    error: str | None = None
    created_at: datetime


class WebhookOut(ORMModel):
    id: int
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime


class AuditLogOut(ORMModel):
    id: int
    actor_label: str
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    summary: str
    created_at: datetime


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
    location_id: int | None = None
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
class SampleDataResult(BaseModel):
    """IDs of the demo records created/removed by the onboarding sample loader."""

    customer_id: int
    equipment_id: int | None = None
    work_order_id: int | None = None
    work_order_number: str | None = None


class StatusCount(BaseModel):
    status: WorkOrderStatus
    count: int


class SetupProgress(BaseModel):
    """First-run onboarding milestones, computed org-wide (not location-scoped)."""

    has_customer: bool
    has_equipment: bool
    has_work_order: bool
    has_team: bool
    has_template: bool
    # Informational (not a milestone): whether the demo sample data is loaded.
    has_sample: bool = False

    @computed_field
    @property
    def done(self) -> int:
        return sum(
            [self.has_customer, self.has_equipment, self.has_work_order, self.has_team, self.has_template]
        )

    @computed_field
    @property
    def total(self) -> int:
        return 5

    @computed_field
    @property
    def complete(self) -> bool:
        return self.done == self.total


class DashboardStats(BaseModel):
    open_work_orders: int
    rush_jobs: int
    awaiting_approval: int
    ready_to_ship: int
    field_visits_scheduled: int
    overdue_open: int
    due_soon_open: int
    by_status: list[StatusCount]
    recent: list[WorkOrderSummary]
    setup: SetupProgress


TokenResponse.model_rebuild()
