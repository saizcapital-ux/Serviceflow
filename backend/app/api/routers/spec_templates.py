"""Equipment spec templates: per-organization fields to capture for each
equipment type. Read by any staff; managed by owners/managers."""
import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_roles, require_staff
from app.core.database import get_db
from app.models import Customer, Equipment, EquipmentSpecField, EquipmentType, User, UserRole
from app.schemas import SpecFieldCreate, SpecFieldOut, SpecFieldUpdate
from app.services import audit

# Fixed (non-spec) columns in the import/template CSV.
_BASE_COLUMNS = ["Customer", "Tag", "Manufacturer", "Model", "Serial"]
MAX_IMPORT_ROWS = 2000

router = APIRouter(prefix="/api/spec-templates", tags=["spec-templates"])

require_manager = require_roles(UserRole.owner, UserRole.manager)


@router.get("", response_model=list[SpecFieldOut])
def list_fields(
    equipment_type: EquipmentType | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    stmt = select(EquipmentSpecField).where(EquipmentSpecField.organization_id == user.organization_id)
    if equipment_type is not None:
        stmt = stmt.where(EquipmentSpecField.equipment_type == equipment_type.value)
    stmt = stmt.order_by(EquipmentSpecField.equipment_type, EquipmentSpecField.position, EquipmentSpecField.id)
    return db.scalars(stmt).all()


def _report_data(db: Session, organization_id: int, equipment_type: EquipmentType):
    """Return (field_labels, rows) for every active asset of the given type."""
    fields = db.scalars(
        select(EquipmentSpecField).where(
            EquipmentSpecField.organization_id == organization_id,
            EquipmentSpecField.equipment_type == equipment_type.value,
        ).order_by(EquipmentSpecField.position, EquipmentSpecField.id)
    ).all()
    labels = [f.label for f in fields]

    equipment = db.scalars(
        select(Equipment).where(
            Equipment.organization_id == organization_id,
            Equipment.equipment_type == equipment_type,
            Equipment.is_active.is_(True),
        ).options(selectinload(Equipment.customer)).order_by(Equipment.tag)
    ).all()

    rows = []
    for eq in equipment:
        specs = eq.nameplate_data or {}
        rows.append({
            "id": eq.id,
            "tag": eq.tag,
            "customer": eq.customer.name if eq.customer else None,
            "manufacturer": eq.manufacturer,
            "model": eq.model,
            "serial_number": eq.serial_number,
            "specs": {label: specs.get(label, "") for label in labels},
        })
    return labels, rows


@router.get("/report")
def spec_report(
    equipment_type: EquipmentType,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Structured spec report: the template fields plus every asset's values."""
    labels, rows = _report_data(db, user.organization_id, equipment_type)
    return {"equipment_type": equipment_type.value, "fields": labels, "equipment": rows}


@router.get("/report.csv")
def spec_report_csv(
    equipment_type: EquipmentType,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Download the spec report as CSV (one row per asset)."""
    labels, rows = _report_data(db, user.organization_id, equipment_type)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Tag", "Customer", "Manufacturer", "Model", "Serial", *labels])
    for r in rows:
        writer.writerow([
            r["tag"] or "", r["customer"] or "", r["manufacturer"] or "",
            r["model"] or "", r["serial_number"] or "",
            *[r["specs"].get(label, "") for label in labels],
        ])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="specs-{equipment_type.value}.csv"'},
    )


def _field_labels(db: Session, organization_id: int, equipment_type: EquipmentType) -> list[str]:
    return [
        f.label for f in db.scalars(
            select(EquipmentSpecField).where(
                EquipmentSpecField.organization_id == organization_id,
                EquipmentSpecField.equipment_type == equipment_type.value,
            ).order_by(EquipmentSpecField.position, EquipmentSpecField.id)
        ).all()
    ]


@router.get("/import-template.csv")
def import_template(equipment_type: EquipmentType, db: Session = Depends(get_db),
                    user: User = Depends(require_staff)):
    """Download a blank CSV to bulk-load assets of this type (header only)."""
    labels = _field_labels(db, user.organization_id, equipment_type)
    buf = io.StringIO()
    csv.writer(buf).writerow(_BASE_COLUMNS + labels)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-{equipment_type.value}.csv"'},
    )


@router.post("/import")
async def import_equipment(
    equipment_type: EquipmentType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Bulk-create assets of one type from a CSV. Each row needs a Customer name
    that already exists; spec columns matching the type's template become
    nameplate_data. Returns a per-row summary."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames or "Customer" not in reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV must have a 'Customer' column header.")

    labels = _field_labels(db, user.organization_id, equipment_type)
    # Cache customers by lowercased name for this org.
    customers = {
        c.name.lower(): c.id
        for c in db.scalars(select(Customer).where(Customer.organization_id == user.organization_id)).all()
    }

    created, errors = 0, []
    to_add = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > MAX_IMPORT_ROWS:
            errors.append({"row": i, "error": f"File exceeds {MAX_IMPORT_ROWS} rows; split it."})
            break
        if not any((v or "").strip() for v in row.values()):
            continue  # skip blank lines
        name = (row.get("Customer") or "").strip()
        if not name:
            errors.append({"row": i, "error": "Missing Customer."})
            continue
        cust_id = customers.get(name.lower())
        if not cust_id:
            errors.append({"row": i, "error": f"Customer '{name}' not found."})
            continue
        specs = {label: row[label].strip() for label in labels if (row.get(label) or "").strip()}
        to_add.append(Equipment(
            organization_id=user.organization_id, customer_id=cust_id,
            equipment_type=equipment_type,
            tag=(row.get("Tag") or "").strip() or None,
            manufacturer=(row.get("Manufacturer") or "").strip() or None,
            model=(row.get("Model") or "").strip() or None,
            serial_number=(row.get("Serial") or "").strip() or None,
            nameplate_data=specs,
        ))
        created += 1

    if to_add:
        db.add_all(to_add)
        audit.record(db, organization_id=user.organization_id, actor=user, action="equipment.imported",
                     summary=f"Imported {created} {equipment_type.value}(s) via CSV",
                     entity_type="equipment", entity_id=None)
        db.commit()
    return {"created": created, "errors": errors}


@router.post("", response_model=SpecFieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: SpecFieldCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    field = EquipmentSpecField(
        organization_id=user.organization_id,
        equipment_type=payload.equipment_type.value,
        label=payload.label.strip(),
        unit=(payload.unit or None),
        position=payload.position,
    )
    db.add(field)
    audit.record(db, organization_id=user.organization_id, actor=user, action="spec_field.created",
                 summary=f"Added spec '{field.label}' for {field.equipment_type}",
                 entity_type="spec_field", entity_id=None)
    db.commit()
    db.refresh(field)
    return field


def _owned(db: Session, field_id: int, user: User) -> EquipmentSpecField:
    field = db.get(EquipmentSpecField, field_id)
    if not field or field.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Spec field not found.")
    return field


@router.patch("/{field_id}", response_model=SpecFieldOut)
def update_field(field_id: int, payload: SpecFieldUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require_manager)):
    field = _owned(db, field_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        field.label = data["label"].strip()
    if "unit" in data:
        field.unit = data["unit"] or None
    if "position" in data and data["position"] is not None:
        field.position = data["position"]
    db.commit()
    db.refresh(field)
    return field


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(field_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    field = _owned(db, field_id, user)
    db.delete(field)
    audit.record(db, organization_id=user.organization_id, actor=user, action="spec_field.deleted",
                 summary=f"Removed spec '{field.label}' for {field.equipment_type}",
                 entity_type="spec_field", entity_id=None)
    db.commit()
