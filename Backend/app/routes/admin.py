from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import role_required
from utils.time_utils import now_utc
from app.db.session import get_db
from app.models import Department, Designation, Employee, Role
from app.schemas.employee import (
    EmployeeUpdate, EmployeeListItem,
    ReferenceData, RefRole, RefDepartment, RefDesignation,
)
from app.utils.excel_sync import update_employee_row as xlsx_update


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(role_required("admin"))])


def _serialize(e: Employee) -> EmployeeListItem:
    return EmployeeListItem(
        id=e.id,
        employee_code=e.employee_code,
        full_name=e.full_name,
        first_name=e.first_name,
        last_name=e.last_name,
        email=e.email,
        phone=e.phone,
        role=e.role.name if e.role else None,
        role_id=e.role_id,
        designation=e.designation.title if e.designation else None,
        designation_id=e.designation_id,
        department=e.department.name if e.department else None,
        department_id=e.department_id,
        employment_status=e.employment_status,
        location=e.location,
        date_of_joining=e.date_of_joining,
        reporting_manager_id=e.reporting_manager_id,
        reporting_manager_name=(e.manager.full_name if e.manager else None),
    )


@router.get("/ping")
def ping():
    return {"ok": True, "scope": "admin"}


# Employees: read / update / delete
# NOTE: POST /employees (create) was intentionally removed.
# New employees are added via Employees-updated.xlsx + `python seed.py`.
# UI updates and soft-deletes are mirrored back into the xlsx (best-effort).
@router.get("/employees", response_model=list[EmployeeListItem])
def list_employees(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    department_id: Optional[str] = Query(None),
    designation_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    query = db.query(Employee).filter(Employee.is_deleted.is_(False))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            Employee.first_name.ilike(like),
            Employee.last_name.ilike(like),
            Employee.email.ilike(like),
        ))
    if role:
        query = query.join(Role).filter(Role.name == role.lower())
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if designation_id:
        query = query.filter(Employee.designation_id == designation_id)
    if status_filter:
        query = query.filter(Employee.employment_status == status_filter.lower())

    rows = query.order_by(Employee.id.desc()).all()
    return [_serialize(e) for e in rows]


@router.get("/employees/{employee_id}", response_model=EmployeeListItem)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e or e.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return _serialize(e)


@router.put("/employees/{employee_id}", response_model=EmployeeListItem)
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e or e.is_deleted:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Track which xlsx columns to patch alongside the DB update.
    xlsx_patch: dict = {}

    if payload.name is not None:
        parts = payload.name.strip().split(" ", 1)
        e.first_name = parts[0]
        e.last_name = parts[1] if len(parts) > 1 else None
        xlsx_patch["first_name"] = e.first_name
        xlsx_patch["last_name"] = e.last_name

    if payload.email is not None:
        new_email = payload.email.strip()
        if new_email.lower() != e.email.lower():
            clash = db.query(Employee).filter(
                Employee.email.ilike(new_email), Employee.id != e.id
            ).first()
            if clash:
                raise HTTPException(status_code=409, detail="Another employee already uses that email.")
            e.email = new_email
            xlsx_patch["email"] = e.email

    if payload.role is not None:
        # Note: there is no `role` column in the xlsx -- seed.py derives role
        # from designation/department. So role changes persist in the DB only.
        role = db.query(Role).filter(Role.name == payload.role.lower()).first()
        if not role:
            raise HTTPException(status_code=400, detail=f"Unknown role '{payload.role}'.")
        e.role_id = role.id

    if payload.department_id is not None:
        if payload.department_id and not db.get(Department, payload.department_id):
            raise HTTPException(status_code=400, detail=f"Unknown department '{payload.department_id}'.")
        e.department_id = payload.department_id or None
        xlsx_patch["department_id"] = e.department_id

    if payload.designation_id is not None:
        if payload.designation_id and not db.get(Designation, payload.designation_id):
            raise HTTPException(status_code=400, detail=f"Unknown designation '{payload.designation_id}'.")
        e.designation_id = payload.designation_id or None
        xlsx_patch["designation_id"] = e.designation_id

    if payload.phone is not None:
        e.phone = payload.phone or None
        xlsx_patch["phone"] = e.phone

    if payload.employment_status is not None:
        e.employment_status = payload.employment_status
        xlsx_patch["employment_status"] = e.employment_status

    if payload.employee_code is not None:
        e.employee_code = payload.employee_code or None
        xlsx_patch["employee_code"] = e.employee_code

    if payload.location is not None:
        e.location = payload.location or None
        xlsx_patch["location"] = e.location

    # Admin can re-assign the reporting manager. Three guardrails:
    #   1) the target must exist and not be soft-deleted
    #   2) an employee cannot report to themselves
    #   3) the assignment must not create a cycle (e.g. A → B → A)
    if "reporting_manager_id" in payload.model_fields_set:
        new_mgr_id = payload.reporting_manager_id
        if new_mgr_id in (None, 0):
            e.reporting_manager_id = None
            xlsx_patch["reporting_manager_id"] = None
        else:
            if new_mgr_id == e.id:
                raise HTTPException(status_code=400, detail="An employee cannot report to themselves.")
            mgr = db.get(Employee, new_mgr_id)
            if not mgr or mgr.is_deleted:
                raise HTTPException(status_code=400, detail=f"Unknown reporting manager '{new_mgr_id}'.")
            # Cycle check: walk up the chain from the proposed manager and
            # make sure we never reach `e.id`. Bounded by employee count.
            seen: set[int] = set()
            cursor = mgr
            while cursor and cursor.id not in seen:
                if cursor.id == e.id:
                    raise HTTPException(
                        status_code=400,
                        detail="Reporting-line cycle detected — chosen manager already reports to this employee (directly or indirectly).",
                    )
                seen.add(cursor.id)
                cursor = cursor.manager
            e.reporting_manager_id = new_mgr_id
            xlsx_patch["reporting_manager_id"] = new_mgr_id

    db.commit()
    db.refresh(e)

    # Best-effort: mirror the change back into the spreadsheet so re-running
    # `python seed.py` doesn't overwrite UI edits with stale Excel data.
    if xlsx_patch:
        xlsx_update(e.id, xlsx_patch)

    return _serialize(e)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    """Soft-delete: marks the row deleted and inactive but preserves history."""
    e = db.get(Employee, employee_id)
    if not e or e.is_deleted:
        raise HTTPException(status_code=404, detail="Employee not found")
    e.is_deleted = True
    e.deleted_at = now_utc()
    e.employment_status = "inactive"
    db.commit()

    # Mirror the soft-delete in the spreadsheet too, so a later `seed.py`
    # run doesn't resurrect the row.
    xlsx_update(e.id, {
        "is_deleted": True,
        "deleted_at": e.deleted_at,
        "employment_status": "inactive",
    })

    return None


# Reference data for dropdowns
@router.get("/reference", response_model=ReferenceData)
def reference_data(db: Session = Depends(get_db)):
    roles = [RefRole.model_validate(r) for r in db.query(Role).order_by(Role.name).all()]
    depts = [RefDepartment.model_validate(d) for d in db.query(Department).order_by(Department.name).all()]
    desigs = [RefDesignation.model_validate(d) for d in db.query(Designation).order_by(Designation.title).all()]
    return ReferenceData(roles=roles, departments=depts, designations=desigs)


# ── Hybrid v2 leave migration ────────────────────────────────────────────
# Admin-only trigger for the v1→v2 ledger migration. The same routine runs
# automatically on startup; this endpoint exists for ops to dry-run or
# re-trigger after a manual data fix. Idempotent.
@router.post("/leave/migrate-v2")
def trigger_leave_v2_migration(
    dry_run: bool = Query(False, description="When true, log what would change but don't write."),
    db: Session = Depends(get_db),
):
    from app.services.leave_v2_migration import migrate_to_v2
    summary = migrate_to_v2(db, dry_run=dry_run)
    return {"dry_run": dry_run, **summary}


# Candidate-manager list for the "Reporting Manager" dropdown on the admin
# Edit Employee form. Includes anyone with role=manager or role=admin so
# admins (who may themselves be reporting managers) are pickable too.
@router.get("/managers")
def managers_for_picker(db: Session = Depends(get_db)):
    rows = (
        db.query(Employee)
        .join(Role)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
            Role.name.in_(["manager", "admin"]),
        )
        .order_by(Employee.first_name.asc())
        .all()
    )
    return [
        {
            "id": e.id,
            "full_name": e.full_name,
            "email": e.email,
            "role": e.role.name if e.role else None,
            "designation": e.designation.title if e.designation else None,
            "department": e.department.name if e.department else None,
        }
        for e in rows
    ]
