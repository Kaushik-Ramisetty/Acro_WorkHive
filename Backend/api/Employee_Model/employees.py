"""api/Employee_Model/employees.py — Employee CRUD router."""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from api.models import (
    Employee, Department, Designation,
    Candidate, CandidateStatus,
    OnboardedEmployee, OnboardedEmployeeStatus,
)
from api.Employee_Model.schemas import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    EmployeeListResponse, EmploymentStatus, FullEmployeeConvertRequest,
)
from utils.id_generator import generate_employee_code
from utils.response import ok, created
from utils.crypto import encrypt_pii_optional
from utils.jwt_auth import requires_role, get_current_user, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["HR — Employees"])

_ADMIN_HR = ("admin", "hr")
_INTERNAL_STAFF = ("admin", "hr", "manager", "employee")


def get_employee_or_404(employee_id: int, db: Session) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id, Employee.is_deleted == False
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.post("/", response_model=EmployeeResponse,
             dependencies=[Depends(requires_role(*_ADMIN_HR))])
def create_employee(employee: EmployeeCreate, db: Session = Depends(get_db)):
    from sqlalchemy import func as _func
    email_lower = (employee.email or "").strip().lower()
    if db.query(Employee).filter(_func.lower(Employee.email) == email_lower).first():
        raise HTTPException(400, "Email already exists")
    if db.query(Employee).filter(Employee.employee_code == employee.employee_code).first():
        raise HTTPException(400, "Employee code already exists")
    if not db.query(Department).filter(Department.id == employee.department_id).first():
        raise HTTPException(404, "Department not found")
    if not db.query(Designation).filter(Designation.id == employee.designation_id).first():
        raise HTTPException(404, "Designation not found")
    if employee.reporting_manager_id and not db.query(Employee).filter(
        Employee.id == employee.reporting_manager_id, Employee.is_deleted == False
    ).first():
        raise HTTPException(404, "Reporting manager not found")
    db_emp = Employee(**{
        k: v for k, v in employee.model_dump().items()
        if k not in ("employment_status", "gender")
    })
    db_emp.employment_status = employee.employment_status.value
    db_emp.gender            = employee.gender.value
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp


@router.get("/", response_model=List[EmployeeListResponse],
            dependencies=[Depends(requires_role(*_INTERNAL_STAFF))])
def get_all_employees(
    skip:              int                      = Query(0, ge=0),
    limit:             int                      = Query(20, ge=1, le=200),
    department_id:     str | None               = Query(None),
    designation_id:    str | None               = Query(None),
    employment_status: EmploymentStatus | None  = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Employee).filter(Employee.is_deleted == False)
    if department_id:    q = q.filter(Employee.department_id == department_id)
    if designation_id:   q = q.filter(Employee.designation_id == designation_id)
    if employment_status: q = q.filter(Employee.employment_status == employment_status.value)
    return q.order_by(Employee.employee_code.asc()).offset(skip).limit(limit).all()


@router.get("/search", response_model=List[EmployeeListResponse],
            dependencies=[Depends(requires_role(*_INTERNAL_STAFF))])
def search_employees(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    pattern = f"%{q}%"
    return db.query(Employee).filter(
        Employee.is_deleted == False,
        or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.email.ilike(pattern),
            Employee.employee_code.ilike(pattern),
        )
    ).all()


@router.get("/me")
def get_my_profile(db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    """Return the full profile for the currently logged-in employee, identified by JWT subject."""
    email_lower = (user.sub or "").strip().lower()
    from sqlalchemy import func as _func
    emp = db.query(Employee).filter(
        _func.lower(Employee.official_email) == email_lower,
        Employee.is_deleted == False,
    ).first()
    if not emp:
        emp = db.query(Employee).filter(
            _func.lower(Employee.email) == email_lower,
            Employee.is_deleted == False,
        ).first()
    if not emp:
        raise HTTPException(status_code=404, detail=f"No employee profile found for '{email_lower}'.")
    dept  = db.query(Department).filter(Department.id == emp.department_id).first()
    desig = db.query(Designation).filter(Designation.id == emp.designation_id).first()
    manager_name = None
    if emp.reporting_manager_id:
        mgr = db.query(Employee).filter(
            Employee.id == emp.reporting_manager_id,
            Employee.is_deleted == False,
        ).first()
        if mgr:
            manager_name = f"{mgr.first_name} {mgr.last_name}".strip()
    return ok(data={
        "id":               emp.id,
        "employee_code":    emp.employee_code,
        "first_name":       emp.first_name,
        "last_name":        emp.last_name,
        "full_name":        f"{emp.first_name} {emp.last_name}".strip(),
        "email":            emp.email,
        "official_email":   emp.official_email,
        "work_email":       emp.official_email or emp.email,
        "phone":            emp.phone,
        "secondary_phone":  emp.secondary_phone,
        "date_of_birth":    str(emp.date_of_birth)    if emp.date_of_birth    else None,
        "date_of_joining":  str(emp.date_of_joining)  if emp.date_of_joining  else None,
        "gender":           emp.gender,
        "Nationality":      emp.Nationality,
        "Marital_status":   emp.Marital_status,
        "blood_group":      emp.blood_group,
        "department_id":    emp.department_id,
        "department_name":  dept.name  if dept  else None,
        "designation_id":   emp.designation_id,
        "designation_title":desig.title if desig else None,
        "employment_status":emp.employment_status,
        "reporting_manager_id":   emp.reporting_manager_id,
        "reporting_manager_name": manager_name,
        "location":         emp.location,
        "time_zone":        emp.time_zone,
        "emergency_contact_name":  emp.emergency_contact_name,
        "emergency_contact_phone": emp.emergency_contact_phone,
    }, message="Employee profile fetched")


@router.get("/{employee_id}", response_model=EmployeeResponse,
            dependencies=[Depends(requires_role(*_INTERNAL_STAFF))])
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    return get_employee_or_404(employee_id, db)


@router.put("/{employee_id}", response_model=EmployeeResponse,
            dependencies=[Depends(requires_role(*_ADMIN_HR))])
def update_employee(employee_id: int, data: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = get_employee_or_404(employee_id, db)
    if data.email and data.email != emp.email:
        if db.query(Employee).filter(Employee.email == data.email, Employee.id != employee_id).first():
            raise HTTPException(400, "Email already registered")
    for field in ("first_name", "last_name", "email", "phone", "date_of_exit",
                  "department_id", "designation_id", "reporting_manager_id",
                  "bank_ifsc", "profile_photo_url", "entra_object_id",
                  "blood_group", "emergency_contact_name", "emergency_contact_phone"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(emp, field, val)
    if data.employment_status:
        emp.employment_status = data.employment_status.value
    if data.gender:
        emp.gender = data.gender.value
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/{employee_id}",
               dependencies=[Depends(requires_role(*_ADMIN_HR))])
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = get_employee_or_404(employee_id, db)
    emp.is_deleted = True
    db.commit()
    return {"message": "Employee soft-deleted"}


@router.patch("/{employee_id}/status", response_model=EmployeeResponse,
              dependencies=[Depends(requires_role(*_ADMIN_HR))])
def change_status(employee_id: int,
                   new_status: EmploymentStatus = Query(...),
                   db: Session = Depends(get_db)):
    emp = get_employee_or_404(employee_id, db)
    emp.employment_status = new_status.value
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/{employee_id}/direct-reports", response_model=List[EmployeeListResponse],
            dependencies=[Depends(requires_role(*_INTERNAL_STAFF))])
def direct_reports(employee_id: int, db: Session = Depends(get_db)):
    get_employee_or_404(employee_id, db)
    return db.query(Employee).filter(
        Employee.reporting_manager_id == employee_id,
        Employee.is_deleted == False,
    ).all()


# ─── Candidate → Employee full conversion (legacy) ──────────────────────────
_CONVERTIBLE_STATUSES = {
    "OFFER_ACCEPTED", "DOCS_PENDING", "DOCS_SUBMITTED",
    "BGV_IN_PROGRESS", "BGV_CLEAR", "BGV_FAILED", "CONVERTED",
}


@router.post("/convert/{candidate_id}",
             dependencies=[Depends(requires_role(*_ADMIN_HR))])
def convert_candidate_to_employee(candidate_id: int,
                                   payload: FullEmployeeConvertRequest,
                                   db: Session = Depends(get_db)):
    """Convert a candidate into a full Employee record (legacy endpoint)."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")
    if candidate.status not in _CONVERTIBLE_STATUSES:
        raise HTTPException(status_code=409,
            detail=f"Cannot convert candidate with status '{candidate.status}'.")

    from sqlalchemy import func as _func
    candidate_email_lower = (candidate.email or "").strip().lower()
    existing_employee = db.query(Employee).filter(
        _func.lower(Employee.email) == candidate_email_lower,
        Employee.is_deleted == False,
    ).first()
    if existing_employee:
        raise HTTPException(status_code=409,
            detail=f"An active employee with email '{candidate.email}' already exists "
                   f"(employee_code: {existing_employee.employee_code}).")

    if not db.query(Department).filter(Department.id == payload.department_id).first():
        raise HTTPException(404, f"Department '{payload.department_id}' not found.")
    if not db.query(Designation).filter(Designation.id == payload.designation_id).first():
        raise HTTPException(404, f"Designation '{payload.designation_id}' not found.")
    if payload.reporting_manager_id:
        if not db.query(Employee).filter(
            Employee.id == payload.reporting_manager_id,
            Employee.is_deleted == False,
        ).first():
            raise HTTPException(404, "Reporting manager not found.")

    emp_code = generate_employee_code(db, Employee)
    aadhaar_bytes = encrypt_pii_optional(payload.aadhaar)

    employee = Employee(
        employee_code        = emp_code,
        entra_object_id      = str(candidate_id),
        first_name           = payload.first_name,
        last_name            = payload.last_name,
        email                = candidate.email,
        phone                = payload.phone,
        date_of_birth        = payload.date_of_birth,
        date_of_joining      = payload.date_of_joining,
        department_id        = payload.department_id,
        designation_id       = payload.designation_id,
        reporting_manager_id = payload.reporting_manager_id,
        employment_status    = "active",
        gender               = payload.gender.value,
        aadhaar_encrypted    = aadhaar_bytes,
        is_deleted           = False,
    )
    db.add(employee)

    existing_onboarded = db.query(OnboardedEmployee).filter(
        OnboardedEmployee.candidate_id == candidate_id
    ).first()
    if existing_onboarded:
        existing_onboarded.employee_code = emp_code
        existing_onboarded.manager_id    = payload.reporting_manager_id
        existing_onboarded.joining_date  = payload.date_of_joining
    else:
        db.add(OnboardedEmployee(
            candidate_id  = candidate_id,
            employee_code = emp_code,
            manager_id    = payload.reporting_manager_id,
            joining_date  = payload.date_of_joining,
            status        = OnboardedEmployeeStatus.INACTIVE.value,
        ))

    candidate.status = CandidateStatus.CONVERTED.value
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database commit failed: {exc}")
    db.refresh(employee)

    _trigger_it_email_after_conversion(employee, db)
    return created(data={
        "employee_id":       employee.id,
        "employee_code":     employee.employee_code,
        "first_name":        employee.first_name,
        "last_name":         employee.last_name,
        "email":             employee.email,
        "phone":             employee.phone,
        "department_id":     employee.department_id,
        "designation_id":    employee.designation_id,
        "date_of_joining":   str(employee.date_of_joining),
        "date_of_birth":     str(employee.date_of_birth) if employee.date_of_birth else None,
        "gender":            employee.gender,
        "employment_status": employee.employment_status,
        "candidate_id":      candidate_id,
        "candidate_status":  candidate.status,
        "it_request_sent":   True,
    }, message=f"Employee {emp_code} created. IT notified to create official credentials.")


def _trigger_it_email_after_conversion(employee, db) -> None:
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
    send_email_in_background(
        send_it_request_email, employee, manager_name, manager_email,
        label=f"IT-request-{employee.employee_code}",
    )
