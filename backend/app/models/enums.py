"""Enumerations used across the domain model."""
import enum


class UserRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    service_writer = "service_writer"
    technician = "technician"
    customer = "customer"  # portal user


class ServiceType(str, enum.Enum):
    shop_repair = "shop_repair"
    field_service = "field_service"


class Priority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    rush = "rush"


class EquipmentType(str, enum.Enum):
    motor = "motor"
    valve = "valve"
    actuator = "actuator"  # e.g. Limitorque
    pump = "pump"
    blower = "blower"
    gearbox = "gearbox"
    other = "other"


class WorkOrderStatus(str, enum.Enum):
    intake = "intake"
    inspection = "inspection"
    quote_pending = "quote_pending"
    approved = "approved"
    quote_rejected = "quote_rejected"
    in_repair = "in_repair"
    testing = "testing"
    ready = "ready"
    shipped = "shipped"
    closed = "closed"
    on_hold = "on_hold"
    cancelled = "cancelled"


class EventType(str, enum.Enum):
    status_change = "status_change"
    note = "note"
    quote_sent = "quote_sent"
    quote_decision = "quote_decision"
    assignment = "assignment"
    field_visit = "field_visit"


class FindingSeverity(str, enum.Enum):
    info = "info"
    minor = "minor"
    major = "major"
    critical = "critical"


class QuoteStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
