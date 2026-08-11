"""Test / inspection reports: per-equipment-type test templates, and the
pass/fail results captured on a work order (e.g. a motor's megger test)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.core.database import get_db
from app.models import (
    Customer,
    Equipment,
    Organization,
    TestResult,
    TestTemplateItem,
    User,
    UserRole,
    WorkOrder,
)
from app.services.pdf import render_test_report_pdf
from app.schemas import (
    TestReportOut,
    TestResultOut,
    TestResultUpdate,
    TestTemplateItemCreate,
    TestTemplateItemOut,
    TestTemplateItemUpdate,
)
from app.services import audit

router = APIRouter(prefix="/api", tags=["tests"])

require_manager = require_roles(UserRole.owner, UserRole.manager)


def compute_overall(results: list[TestResult]) -> str:
    if not results:
        return "none"
    if any(r.result == "fail" for r in results):
        return "failed"
    if all(r.result in ("pass", "na") for r in results):
        return "passed"
    return "in_progress"


# ---------- Test templates (owner/manager to manage) ----------
@router.get("/test-templates", response_model=list[TestTemplateItemOut])
def list_items(equipment_type=None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    stmt = select(TestTemplateItem).where(TestTemplateItem.organization_id == user.organization_id)
    if equipment_type is not None:
        stmt = stmt.where(TestTemplateItem.equipment_type == equipment_type)
    return db.scalars(
        stmt.order_by(TestTemplateItem.equipment_type, TestTemplateItem.position, TestTemplateItem.id)
    ).all()


@router.post("/test-templates", response_model=TestTemplateItemOut, status_code=status.HTTP_201_CREATED)
def create_item(payload: TestTemplateItemCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    item = TestTemplateItem(
        organization_id=user.organization_id, equipment_type=payload.equipment_type.value,
        label=payload.label.strip(), unit=(payload.unit or None), position=payload.position,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _owned_item(db: Session, item_id: int, user: User) -> TestTemplateItem:
    item = db.get(TestTemplateItem, item_id)
    if not item or item.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test item not found.")
    return item


@router.patch("/test-templates/{item_id}", response_model=TestTemplateItemOut)
def update_item(item_id: int, payload: TestTemplateItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_manager)):
    item = _owned_item(db, item_id, user)
    data = payload.model_dump(exclude_unset=True)
    if data.get("label") is not None:
        item.label = data["label"].strip()
    if "unit" in data:
        item.unit = data["unit"] or None
    if data.get("position") is not None:
        item.position = data["position"]
    db.commit()
    db.refresh(item)
    return item


@router.delete("/test-templates/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    db.delete(_owned_item(db, item_id, user))
    db.commit()


# ---------- Work-order test report (staff) ----------
def _wo(db: Session, wo_id: int, user: User) -> WorkOrder:
    wo = db.scalar(select(WorkOrder).where(
        WorkOrder.id == wo_id, WorkOrder.organization_id == user.organization_id))
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    return wo


def _results(db: Session, wo_id: int) -> list[TestResult]:
    return db.scalars(
        select(TestResult).where(TestResult.work_order_id == wo_id)
        .order_by(TestResult.position, TestResult.id)
    ).all()


def _report(db: Session, wo_id: int) -> TestReportOut:
    results = _results(db, wo_id)
    return TestReportOut(overall=compute_overall(results),
                         items=[TestResultOut.model_validate(r) for r in results])


@router.get("/work-orders/{wo_id}/tests", response_model=TestReportOut)
def get_tests(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    _wo(db, wo_id, user)
    return _report(db, wo_id)


@router.get("/work-orders/{wo_id}/test-report.pdf")
def test_report_pdf(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Printable test/inspection report for a work order."""
    wo = _wo(db, wo_id, user)
    results = _results(db, wo_id)
    org = db.get(Organization, user.organization_id)
    customer = db.get(Customer, wo.customer_id)
    equipment = db.get(Equipment, wo.equipment_id) if wo.equipment_id else None
    pdf = render_test_report_pdf(
        org=org, work_order=wo, customer=customer, equipment=equipment,
        results=results, overall=compute_overall(results),
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{wo.number}-test-report.pdf"'})


@router.post("/work-orders/{wo_id}/tests/apply", response_model=TestReportOut, status_code=status.HTTP_201_CREATED)
def apply_template(wo_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Populate this work order's test report from its equipment type's template
    (adds any template items not already present; leaves existing results)."""
    wo = _wo(db, wo_id, user)
    if not wo.equipment_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Attach equipment before applying a test template.")
    equipment = db.get(Equipment, wo.equipment_id)
    template = db.scalars(
        select(TestTemplateItem).where(
            TestTemplateItem.organization_id == user.organization_id,
            TestTemplateItem.equipment_type == equipment.equipment_type.value,
        ).order_by(TestTemplateItem.position, TestTemplateItem.id)
    ).all()
    if not template:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No test template defined for this equipment type.")
    existing = {r.label for r in _results(db, wo_id)}
    for item in template:
        if item.label not in existing:
            db.add(TestResult(work_order_id=wo_id, label=item.label, unit=item.unit,
                              result="pending", position=item.position))
    audit.record(db, organization_id=user.organization_id, actor=user, action="test_report.applied",
                 summary=f"Applied {equipment.equipment_type.value} test template to {wo.number}",
                 entity_type="work_order", entity_id=wo.id)
    db.commit()
    return _report(db, wo_id)


@router.patch("/test-results/{result_id}", response_model=TestResultOut)
def update_result(result_id: int, payload: TestResultUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_staff)):
    result = db.get(TestResult, result_id)
    if result is not None:
        wo = db.get(WorkOrder, result.work_order_id)
        if wo is None or wo.organization_id != user.organization_id:
            result = None
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test result not found.")
    data = payload.model_dump(exclude_unset=True)
    if "value" in data:
        result.value = data["value"] or None
    if "notes" in data:
        result.notes = data["notes"] or None
    if data.get("result") is not None:
        result.result = data["result"]
    db.commit()
    db.refresh(result)
    return result
