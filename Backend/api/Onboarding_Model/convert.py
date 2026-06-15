"""api/Onboarding_Model/convert.py — Candidate → Employee conversion."""
import bcrypt as _bcrypt
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, created
from api.models import (
    Candidate, CandidateStatus, Employee, Department, Designation,
    LeaveType, LeaveBalance,
)
from app.models import Role
from utils.id_generator import generate_employee_code
from utils.time_utils import now_utc
from utils.crypto import encrypt_pii_optional
from utils.jwt_auth import requires_role
import re

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversion"])

# Sourced via the central helper so deployments can override without code
# edits. The literal fallback inside the helper matches the original value
# ("employee123"), so behaviour is identical when no env var is set.
from app.core.defaults import default_employee_password as _default_employee_password
DEFAULT_PASSWORD = _default_employee_password()


def _hash(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


CONVERTIBLE_STATUSES = {
    CandidateStatus.OFFER_ACCEPTED.value,
    CandidateStatus.DOCS_PENDING.value,
    CandidateStatus.DOCS_SUBMITTED.value,
    CandidateStatus.BGV_IN_PROGRESS.value,
    CandidateStatus.BGV_CLEAR.value,
    CandidateStatus.BGV_FAILED.value,
    CandidateStatus.CONVERTED.value,
    CandidateStatus.JOINED.value,
}


def _initialize_leave_balances(employee: Employee, db: Session) -> int:
    """Create LeaveBalance rows for the new employee. Returns count created."""
    current_year = now_utc().year
    emp_gender = (employee.gender or "").lower()
    leave_types = db.query(LeaveType).all()
    existing_type_ids = {
        row[0]
        for row in db.query(LeaveBalance.leave_type_id).filter(
            LeaveBalance.employee_id == employee.id,
            LeaveBalance.year == current_year,
        ).all()
    }
    created_count = 0
    for lt in leave_types:
        gender_restriction = (lt.applicable_gender or "all").lower()
        if gender_restriction != "all":
            if not emp_gender or gender_restriction != emp_gender:
                continue
        if lt.id in existing_type_ids:
            continue
        opening_balance = lt.annual_quota if lt.annual_quota is not None else 0
        # MERGE: aligned with the unified Core LeaveBalance schema
        # (opening_balance/current_balance/used/reserved). The original
        # onboarding fields (total_allocated/carried_forward/pending/remaining)
        # don't exist on the merged model.
        bal_id = f"LB-{employee.id}-{lt.id}-{current_year}"[:20]
        db.add(LeaveBalance(
            id=bal_id,
            employee_id=employee.id,
            leave_type_id=lt.id,
            year=current_year,
            opening_balance=opening_balance,
            used=0,
            current_balance=opening_balance,
            reserved=0,
        ))
        created_count += 1
    return created_count


class ConvertRequest(BaseModel):
    department_id:        str
    designation_id:       str
    reporting_manager_id: Optional[int]  = None
    employment_status:    str            = "active"
    date_of_joining:      Optional[date] = None
    location:             Optional[str]  = None
    time_zone:            Optional[str]  = None
    first_name:      Optional[str]  = None
    last_name:       Optional[str]  = None
    phone:           Optional[str]  = None
    secondary_phone: Optional[str]  = None
    date_of_birth:   Optional[date] = None
    gender:          Optional[str]  = None
    Nationality:     Optional[str]  = None
    Marital_status:  Optional[str]  = None
    blood_group:     Optional[str]  = None
    emergency_contact_name:  Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    aadhaar:      Optional[str] = None
    pan:          Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc:    Optional[str] = None
    password: str = DEFAULT_PASSWORD


@router.post("/convert/{candidate_id}",
             dependencies=[Depends(requires_role("admin", "hr"))])
def convert_candidate_to_employee(candidate_id: int, payload: ConvertRequest,
                                   db: Session = Depends(get_db)):
    """Convert a candidate to an employee record."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")

    if candidate.status not in CONVERTIBLE_STATUSES:
        raise HTTPException(status_code=409,
            detail=f"Candidate status '{candidate.status}' is not eligible for conversion.")

    if not db.query(Department).filter(Department.id == payload.department_id).first():
        raise HTTPException(status_code=400, detail=f"Department '{payload.department_id}' not found.")
    if not db.query(Designation).filter(Designation.id == payload.designation_id).first():
        raise HTTPException(status_code=400, detail=f"Designation '{payload.designation_id}' not found.")
    

    # Idempotent + revival check.
    email_lower = candidate.email.strip().lower()
    any_existing = db.query(Employee).filter(Employee.email == email_lower).first()
    if any_existing and not any_existing.is_deleted:
        return ok(
            data={**_serialize(any_existing), "leave_balances_created": 0},
            message=f"Employee already exists ({any_existing.employee_code})",
        )
    if any_existing and any_existing.is_deleted:
        # Revive the soft-deleted employee instead of hitting UNIQUE(email).
        any_existing.is_deleted = False
        any_existing.deleted_at = None
        # Preserve prior activation state when reviving. If the employee
        # had credentials (password_hash) the last time around, they were
        # previously activated by IT, so flipping them back to "active"
        # is safe. If they never received credentials, they re-enter the
        # pending_activation gate and must go through IT activation again.
        if any_existing.password_hash and any_existing.is_activated:
            any_existing.employment_status = payload.employment_status or "active"
        else:
            any_existing.employment_status = "pending_activation"
            any_existing.is_activated = False
        any_existing.department_id  = payload.department_id  or any_existing.department_id
        any_existing.designation_id = payload.designation_id or any_existing.designation_id
        if payload.reporting_manager_id is not None:
            any_existing.reporting_manager_id = payload.reporting_manager_id
        if payload.date_of_joining:
            any_existing.date_of_joining = payload.date_of_joining
        if not any_existing.role_id:
            _employee_role = db.query(Role).filter(Role.name == "employee").first()
            if _employee_role:
                any_existing.role_id = _employee_role.id
        candidate.status = CandidateStatus.CONVERTED.value
        balance_count = _initialize_leave_balances(any_existing, db)
        db.commit()
        db.refresh(any_existing)
        return ok(
            data={**_serialize(any_existing), "leave_balances_created": balance_count, "revived": True},
            message=f"Employee {any_existing.employee_code} revived from soft-delete",
        )

    # Derive names
    parts      = (candidate.name or "").strip().split(" ", 1)
    first_name = payload.first_name or candidate.first_name or parts[0] or "Unknown"
    last_name  = payload.last_name  or candidate.last_name  or (parts[1] if len(parts) > 1 else "")

    emp_code = generate_employee_code(db, Employee)
    # Conversion does NOT issue credentials. The freshly-created employee
    # lands in "pending_activation" with no password and is_activated=False;
    # IT is the single source of truth for credentials and runs the
    # /onboarding/activate/{id} endpoint afterwards, which is the *only*
    # place that sets official_email + Password + is_activated=True +
    # employment_status="active". The legacy ``payload.password`` field is
    # retained on the schema for backwards-compatible request shapes but is
    # intentionally ignored here.
    joining  = payload.date_of_joining or candidate.expected_joining_date or date.today()

    # Default every converted candidate to the "employee" role so that
    # downstream role-based UI (dashboard routing) + RBAC checks have a
    # value to read. Without this, /auth/me returns role=null and the
    # frontend can't pick a dashboard.
    employee_role = db.query(Role).filter(Role.name == "employee").first()

    employee = Employee(
        employee_code            = emp_code,
        first_name               = first_name,
        last_name                = last_name,
        email                    = email_lower,
        phone                    = payload.phone or candidate.phone,
        secondary_phone          = payload.secondary_phone,
        date_of_birth            = payload.date_of_birth,
        date_of_joining          = joining,
        department_id            = payload.department_id,
        designation_id           = payload.designation_id,
        reporting_manager_id     = payload.reporting_manager_id,
        # New converts land in pending_activation regardless of what the
        # caller passed — IT activation is the single gate that flips them
        # to "active". Existing clients that POSTed `employment_status:
        # "active"` continue to work; the field is just no longer the
        # source of truth here.
        employment_status        = "pending_activation",
        gender                   = payload.gender or None,
        Nationality              = payload.Nationality,
        Marital_status           = payload.Marital_status,
        blood_group              = payload.blood_group,
        bank_ifsc                = payload.bank_ifsc,
        emergency_contact_name   = payload.emergency_contact_name,
        emergency_contact_phone  = payload.emergency_contact_phone,
        location                 = payload.location,
        time_zone                = payload.time_zone,
        role_id                  = employee_role.id if employee_role else None,
        # No password is issued at conversion time. IT activation is the
        # sole place that sets a Password + official_email + is_activated.
        Password                 = None,
        is_activated             = False,
        # Fernet-encrypted PII (was raw bytes before — that's not encryption).
        aadhaar_encrypted        = encrypt_pii_optional(payload.aadhaar),
        pan_encrypted            = encrypt_pii_optional(payload.pan),
        bank_account_encrypted   = encrypt_pii_optional(payload.bank_account),
        is_deleted               = False,
    )
    db.add(employee)
    db.flush()
    balance_count = _initialize_leave_balances(employee, db)
    candidate.status = CandidateStatus.CONVERTED.value

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        racer = db.query(Employee).filter(Employee.email == email_lower).first()
        if racer:
            return ok(
                data={**_serialize(racer), "leave_balances_created": 0, "race_resolved": True},
                message=f"Employee already exists ({racer.employee_code}) — concurrent conversion resolved",
            )
        raise HTTPException(status_code=409,
            detail=f"Could not convert candidate {candidate_id} due to a uniqueness conflict.")
    db.refresh(employee)

    # Auto-trigger IT email in background
    manager_name = manager_email = None
    if employee.reporting_manager_id:
        mgr = db.query(Employee).filter(
            Employee.id == employee.reporting_manager_id,
            Employee.is_deleted.is_(False),
        ).first()
        if mgr:
            manager_name  = f"{mgr.first_name} {mgr.last_name}".strip()
            manager_email = mgr.official_email or mgr.email
    from utils.email_service import send_it_request_email, send_email_in_background
    send_email_in_background(send_it_request_email, employee, manager_name, manager_email,
                              label=f"IT-request-{emp_code}")

    return created(
        data={**_serialize(employee), "leave_balances_created": balance_count, "it_email_sent": True},
        message=f"Candidate converted to Employee {emp_code}. IT notified to create credentials.",
    )


@router.get("/employees/active",
            dependencies=[Depends(requires_role("admin", "hr", "manager", "employee"))])
def list_active_employees(q: Optional[str] = None, db: Session = Depends(get_db)):
    """Active employees list — powers the reporting-manager search dropdown."""
    query = db.query(Employee).filter(
        Employee.is_deleted.is_(False),
        Employee.employment_status == "active",
    )
    if q and len(q) >= 2:
        like = f"%{q}%"
        query = query.filter(or_(
            Employee.first_name.ilike(like),
            Employee.last_name.ilike(like),
            Employee.employee_code.ilike(like),
            Employee.email.ilike(like),
        ))
    employees = query.order_by(Employee.first_name).limit(50).all()
    return ok(data=[
        {"id": e.id, "employee_code": e.employee_code,
         "first_name": e.first_name, "last_name": e.last_name,
         "email": e.email, "department_id": e.department_id}
        for e in employees
    ], message=f"{len(employees)} employee(s) found")


@router.get("/employees/{employee_id}/leave-balances",
            dependencies=[Depends(requires_role("admin", "hr", "manager", "employee"))])
def get_employee_leave_balances(employee_id: int, db: Session = Depends(get_db)):
    """Return current-year leave balances for an employee."""
    year = now_utc().year
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_deleted.is_(False),
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found.")
    balances = db.query(LeaveBalance).filter(
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.year == year,
    ).all()
    return ok(data=[
        {
            "leave_type_id":   b.leave_type_id,
            # NOTE: LeaveType has no `code` column — `id` (e.g. "LT001") IS the code.
            "leave_type_code": b.leave_type.id   if b.leave_type else None,
            "leave_type_name": b.leave_type.name if b.leave_type else None,
            "year":            b.year,
            "total_allocated": b.total_allocated,
            "carried_forward": b.carried_forward,
            "used":            b.used,
            "pending":         b.pending,
            "remaining":       b.remaining,
            "is_paid":         b.leave_type.is_paid if b.leave_type else None,
        }
        for b in balances
    ], message=f"{len(balances)} leave balance(s) for year {year}")


def _serialize(e: Employee) -> dict:
    return {
        "id":                e.id,
        "employee_code":     e.employee_code,
        "first_name":        e.first_name,
        "last_name":         e.last_name,
        "email":             e.email,
        "phone":             e.phone,
        "date_of_joining":   str(e.date_of_joining) if e.date_of_joining else None,
        "department_id":     e.department_id,
        "designation_id":    e.designation_id,
        "employment_status": e.employment_status,
        "gender":            e.gender,
        "location":          e.location,
        "time_zone":         e.time_zone,
        "official_email":    e.official_email,
        "is_activated":      e.is_activated,
    }
