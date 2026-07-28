"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import (
    EquipmentType,
    EventType,
    FindingSeverity,
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
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    promised_date: date | None = None


class WorkOrderUpdate(BaseModel):
    priority: Priority | None = None
    title: str | None = None
    problem_description: str | None = None
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


class WorkOrderSummary(ORMModel):
    id: int
    number: str
    title: str
    status: WorkOrderStatus
    priority: Priority
    service_type: ServiceType
    customer_id: int
    equipment_id: int | None = None
    promised_date: date | None = None
    total_estimate: float
    created_at: datetime
    updated_at: datetime


class WorkOrderDetail(WorkOrderSummary):
    problem_description: str | None = None
    assigned_to: int | None = None
    scheduled_at: datetime | None = None
    total_actual: float
    customer: CustomerOut | None = None
    equipment: EquipmentOut | None = None
    events: list[EventOut] = []
    findings: list[FindingOut] = []
    quotes: list[QuoteOut] = []


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
