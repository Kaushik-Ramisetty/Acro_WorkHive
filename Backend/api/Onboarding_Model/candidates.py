"""api/Onboarding_Model/candidates.py — Candidate CRUD router."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, created
from api.Onboarding_Model.schemas import CandidateCreate, CandidateUpdate
from api.Onboarding_Model.services import candidate_service as svc
from utils.jwt_auth import requires_role, get_current_user, CurrentUser

_HR_ROLES = ("admin", "hr")
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/candidates", tags=["Onboarding — Candidates"])


@router.post("", dependencies=[Depends(requires_role(*_HR_ROLES))])
@router.post("/", include_in_schema=False, dependencies=[Depends(requires_role(*_HR_ROLES))])
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    candidate = svc.create_candidate(payload, db)
    return created(data=_serialize(candidate),
        message=f"Candidate '{candidate.name}' created (ref: {candidate.candidate_ref})")


@router.get("", dependencies=[Depends(requires_role(*_HR_ROLES))])
@router.get("/", include_in_schema=False, dependencies=[Depends(requires_role(*_HR_ROLES))])
def list_candidates(status: Optional[str] = Query(None),
                     skip: int = Query(0, ge=0),
                     limit: int = Query(50, ge=1, le=200),
                     db: Session = Depends(get_db)):
    candidates = svc.list_candidates(db, status=status, skip=skip, limit=limit)
    return ok(data=[_serialize(c) for c in candidates],
              message=f"{len(candidates)} candidates found")


@router.get("/{candidate_id}")
def get_candidate(candidate_id: int,
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    # HR-equivalent roles see anyone; candidate may only see their own record.
    if user.role not in {"admin", "hr", "manager"}:
        if user.role != "candidate" or user.candidate_id != candidate_id:
            raise HTTPException(status_code=403, detail="Not permitted to view this candidate.")
    return _get_candidate_impl(candidate_id, db)


def _get_candidate_impl(candidate_id: int, db: Session):
    from api.models import Employee
    candidate = svc.get_candidate(candidate_id, db)
    linked_employee = db.query(Employee).filter(
        Employee.email == candidate.email.strip().lower(),
        Employee.is_deleted.is_(False),
    ).first()
    manager_name = None
    if linked_employee and linked_employee.reporting_manager_id:
        mgr = db.query(Employee).filter(
            Employee.id == linked_employee.reporting_manager_id,
            Employee.is_deleted.is_(False),
        ).first()
        if mgr:
            manager_name = f"{mgr.first_name} {mgr.last_name}".strip()
    return ok(data=_serialize_detail(candidate, linked_employee, manager_name))


@router.post("/{candidate_id}/not-joined",
             dependencies=[Depends(requires_role(*_HR_ROLES))])
def mark_not_joined(candidate_id: int, db: Session = Depends(get_db)):
    """Mark a candidate as NOT_JOINED. Soft-deletes the linked Employee."""
    from api.models import Employee, OnboardedEmployee, CandidateStatus
    from utils.time_utils import now_utc

    candidate = svc.get_candidate(candidate_id, db)
    candidate.status = CandidateStatus.NOT_JOINED.value
    linked_employee = db.query(Employee).filter(
        Employee.email == candidate.email.strip().lower(),
        Employee.is_deleted.is_(False),
    ).first()
    if linked_employee:
        linked_employee.is_deleted        = True
        linked_employee.employment_status = "exited"
        linked_employee.deleted_at        = now_utc()
    onboarded = db.query(OnboardedEmployee).filter(
        OnboardedEmployee.candidate_id == candidate_id
    ).first()
    if onboarded:
        onboarded.status = OnboardedEmployeeStatus_value("INACTIVE")
    db.commit()
    return ok(data={
        "candidate_id":     candidate_id,
        "status":           candidate.status,
        "employee_deleted": linked_employee is not None,
        "onboarded_updated":onboarded is not None,
    }, message="Candidate marked as Not Joined")


def OnboardedEmployeeStatus_value(name: str) -> str:
    """Tiny helper: avoids re-importing the enum each request."""
    from api.models import OnboardedEmployeeStatus
    return getattr(OnboardedEmployeeStatus, name).value


@router.patch("/{candidate_id}",
              dependencies=[Depends(requires_role(*_HR_ROLES))])
def update_candidate(candidate_id: int, payload: CandidateUpdate,
                      db: Session = Depends(get_db)):
    candidate = svc.update_candidate(candidate_id, payload, db)
    return ok(data=_serialize(candidate), message="Candidate updated")


# ─── serialisers ──────────────────────────────────────────────────────────────

def _serialize(c) -> dict:
    data = {
        "id":              c.id,
        "candidate_ref":   c.candidate_ref,
        "first_name":      getattr(c, "first_name", None),
        "last_name":       getattr(c, "last_name", None),
        "name":            c.name,
        "email":           c.email,
        "phone":           c.phone,
        "role":            c.role,
        "department":      c.department,
        "ctc":             getattr(c, "ctc", None),
        "status":          c.status,
        "is_offer_accepted": c.is_offer_accepted,
        "expected_joining_date": str(c.expected_joining_date) if c.expected_joining_date else None,
        "created_at":      c.created_at.isoformat() if c.created_at else None,
    }
    data.update(_serialize_admin_reflection(c))
    return data


def _serialize_admin_reflection(c) -> dict:
    from api.models import DocumentStatus as DS
    # Compute document_status summary and documents_verified flag for the admin UI.
    required_doc_types = {"bgv_form", "aadhar", "pan", "qualification", "address_proof", "cif"}
    verified_types = {
        d.doc_type for d in (c.documents or [])
        if d.status == DS.VERIFIED.value and d.doc_type in required_doc_types
    }
    uploaded_types = {
        d.doc_type for d in (c.documents or [])
        if d.status in (DS.UPLOADED.value, DS.VERIFIED.value) and d.doc_type in required_doc_types
    }
    documents_verified = verified_types >= required_doc_types
    return {
        "current_status": c.status,
        # documents_verified: True only when every required doc is in VERIFIED state.
        # This is the gate that controls whether HR can initiate BGV.
        "documents_verified": documents_verified,
        "bgv_initiable": documents_verified and c.bgv_check is None,
        "documents": [
            {
                "id":                d.id,
                "doc_type":          d.doc_type,
                "original_filename": d.original_filename,
                "file_url":          d.file_url,
                "file_size_kb":      getattr(d, "file_size_kb", None),
                "status":            d.status,
                "uploaded_at":       d.uploaded_at.isoformat() if d.uploaded_at else None,
                "verified_at":       d.verified_at.isoformat() if getattr(d, "verified_at", None) else None,
                "remarks":           getattr(d, "remarks", None),
            }
            for d in (c.documents or [])
        ],
        "bgv_check": (
            {
                "id":            c.bgv_check.id,
                "status":        c.bgv_check.status,
                "vendor_name":   c.bgv_check.vendor_name,
                "initiated_at":  c.bgv_check.initiated_at.isoformat() if c.bgv_check.initiated_at else None,
                "completed_at":  c.bgv_check.completed_at.isoformat() if c.bgv_check.completed_at else None,
                "remarks":       c.bgv_check.remarks,
            }
            if c.bgv_check else None
        ),
    }


def _serialize_detail(c, linked_employee=None, manager_name: str = None) -> dict:
    base = _serialize(c)
    emp_code_resolved = manager_resolved = None
    if linked_employee:
        emp_code_resolved = linked_employee.employee_code
        manager_resolved  = manager_name
    elif c.onboarded_employee:
        emp_code_resolved = c.onboarded_employee.employee_code
        manager_resolved  = c.onboarded_employee.manager_name or None
    base.update({
        "offer_letter_url":   c.offer_letter_url,
        "offer_sent_at":      c.offer_sent_at.isoformat() if c.offer_sent_at else None,
        "offer_accepted_at":  c.offer_accepted_at.isoformat() if c.offer_accepted_at else None,
        "is_offer_accepted":  c.is_offer_accepted,
        "credentials_sent":   c.credentials_sent,
        "updated_at":         c.updated_at.isoformat() if c.updated_at else None,
        "onboarded_employee": (
            {
                "id":            c.onboarded_employee.id,
                "employee_code": c.onboarded_employee.employee_code,
                "manager_name":  c.onboarded_employee.manager_name,
                "joining_date":  str(c.onboarded_employee.joining_date) if c.onboarded_employee.joining_date else None,
                "status":        c.onboarded_employee.status,
                "activated_at":  c.onboarded_employee.activated_at.isoformat() if c.onboarded_employee.activated_at else None,
            }
            if c.onboarded_employee else None
        ),
        "employee": (
            {
                "id":                     linked_employee.id,
                "employee_code":          linked_employee.employee_code,
                "first_name":             linked_employee.first_name,
                "last_name":              linked_employee.last_name,
                "email":                  linked_employee.email,
                "department_id":          linked_employee.department_id,
                "designation_id":         linked_employee.designation_id,
                "reporting_manager_id":   linked_employee.reporting_manager_id,
                "reporting_manager_name": manager_name,
                "employment_status":      linked_employee.employment_status,
                "date_of_joining":        str(linked_employee.date_of_joining) if linked_employee.date_of_joining else None,
                "location":               linked_employee.location,
                "time_zone":              linked_employee.time_zone,
            }
            if linked_employee else None
        ),
        "resolved_employee_code": emp_code_resolved,
        "resolved_manager_name":  manager_resolved,
    })
    return base
