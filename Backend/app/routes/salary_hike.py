"""Salary Hike Request API.

Prefix : /finance
Auth   : finance or admin role

Endpoints
---------
POST   /finance/hike-requests                   Create a hike request (admin)
GET    /finance/hike-requests                   List hike requests (admin + finance)
GET    /finance/hike-requests/pending-count     Count of pending requests
POST   /finance/hike-requests/{id}/approve      Finance approves → salary applied
POST   /finance/hike-requests/{id}/reject       Finance rejects with reason
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.models.payroll import SalaryStructure, PayrollRun
from app.models.role import Role
from app.models.salary_hike_request import SalaryHikeRequest
from app.services import payroll_service
from app.services.email_service import send_hike_request_email, send_hike_review_email

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/finance",
    tags=["Finance - Salary Hike Requests"],
    dependencies=[Depends(role_required("finance", "admin"))],
)

_Actor = Depends(role_required("finance", "admin"))


# ─── Request / Response Schemas ───────────────────────────────────────────────

class HikeRequestCreate(BaseModel):
    employee_id: int
    hike_type: str = Field(..., description="'percentage' or 'fixed'")
    hike_value: float = Field(..., gt=0, description="Percentage (e.g. 15) or fixed amount")
    effective_from: date
    reason: Optional[str] = None


class HikeReviewBody(BaseModel):
    comment: Optional[str] = None

class HikeRejectBody(BaseModel):
    comment: str = ""
    rejection_reason: Optional[str] = None   # If provided, stored separately for compliance audit


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_active_ctc(db: Session, employee_id: int) -> float:
    struct = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.is_active == True,
        )
        .order_by(SalaryStructure.effective_from.desc())
        .first()
    )
    return float(struct.annual_ctc) if struct and struct.annual_ctc else 0.0


def _validate_effective_date_vs_closed_months(
    db: Session, effective_from: date
) -> Optional[str]:
    """Check if effective_from falls within a closed/approved payroll month.

    Returns an error message string if blocked, or None if valid.

    Rules:
    - If the payroll run for the effective_from month is FINAL_APPROVED (closed/
      published/approved/payslip_generated), the hike CANNOT take effect from
      that month — it would require recomputing a locked run.
    - The hike is automatically pushed to the next OPEN month in that case.
    - This function returns a message describing the conflict so the caller
      can reject the request and suggest the next open month.
    """
    _LOCKED = ("closed", "published", "approved", "payslip_generated")
    # Find any run whose pay period overlaps with effective_from month
    blocked = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.month == effective_from.month,
            PayrollRun.year == effective_from.year,
            PayrollRun.status.in_(_LOCKED),
        )
        .first()
    )
    if blocked:
        import calendar as _cal
        # Suggest the first day of the next month as safe effective date
        next_month = effective_from.month % 12 + 1
        next_year  = effective_from.year + (1 if effective_from.month == 12 else 0)
        suggestion = date(next_year, next_month, 1)
        return (
            f"Cannot set effective_from={effective_from} — payroll for "
            f"{_cal.month_name[effective_from.month]} {effective_from.year} is already "
            f"'{blocked.status}' (locked/finalized). "
            f"Earliest safe effective date: {suggestion} (first of next open month)."
        )
    return None


def _fmt_name(emp: Optional[Employee]) -> Optional[str]:
    if not emp:
        return None
    return f"{emp.first_name} {emp.last_name or ''}".strip()


def _serialize(req: SalaryHikeRequest) -> dict:
    emp = req.employee
    dept = None
    desig = None
    if emp:
        if emp.department:
            dept = emp.department.name
        if emp.designation:
            desig = emp.designation.title
    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": _fmt_name(emp),
        "employee_code": (emp.employee_code or f"EMP{emp.id:04d}") if emp else None,
        "department": dept,
        "designation": desig,
        "old_ctc": req.old_ctc,
        "new_ctc": req.new_ctc,
        "hike_type": req.hike_type,
        "hike_value": req.hike_value,
        "effective_from": str(req.effective_from) if req.effective_from else None,
        "reason": req.reason,
        "status": req.status,
        "requested_by_id": req.requested_by_id,
        "requested_by_name": _fmt_name(req.requested_by),
        "reviewed_by_id": req.reviewed_by_id,
        "reviewed_by_name": _fmt_name(req.reviewed_by),
        "review_comment": req.review_comment,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }


def _employee_email(emp: Optional[Employee]) -> Optional[str]:
    if not emp:
        return None
    return emp.email or emp.official_email or None


# ─── POST /finance/hike-requests ─────────────────────────────────────────────

@router.post(
    "/hike-requests",
    status_code=status.HTTP_201_CREATED,
    summary="Create a salary hike request",
)
def create_hike_request(
    body: HikeRequestCreate,
    db: Session = Depends(get_db),
    actor: Employee = _Actor,
):
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.hike_type not in ("percentage", "fixed"):
        raise HTTPException(status_code=400, detail="hike_type must be 'percentage' or 'fixed'")

    # ── Production guard: validate effective_from against closed months ──
    date_conflict = _validate_effective_date_vs_closed_months(db, body.effective_from)
    if date_conflict:
        raise HTTPException(
            status_code=400,
            detail=date_conflict,
        )

    old_ctc = _get_active_ctc(db, body.employee_id)

    if body.hike_type == "percentage":
        new_ctc = old_ctc * (1 + body.hike_value / 100)
    else:
        new_ctc = old_ctc + body.hike_value

    new_ctc = round(new_ctc, 2)
    if new_ctc <= 0:
        raise HTTPException(status_code=400, detail="Computed new CTC must be positive")

    req = SalaryHikeRequest(
        employee_id=body.employee_id,
        old_ctc=old_ctc,
        new_ctc=new_ctc,
        hike_type=body.hike_type,
        hike_value=body.hike_value,
        effective_from=body.effective_from,
        reason=body.reason,
        status="pending_finance_review",
        requested_by_id=actor.id,
        effective_date_validated=True,  # Date validated against closed months
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Notify finance users via email
    try:
        finance_users = (
            db.query(Employee)
            .join(Employee.role)
            .filter(Role.name == "finance")
            .all()
        )
        emp_name = _fmt_name(emp)
        actor_name = _fmt_name(actor)
        for fu in finance_users:
            to_email = _employee_email(fu)
            if to_email:
                send_hike_request_email(
                    to_email=to_email,
                    employee_name=emp_name or "—",
                    employee_code=emp.employee_code or f"EMP{emp.id:04d}",
                    old_ctc=old_ctc,
                    new_ctc=new_ctc,
                    hike_type=body.hike_type,
                    hike_value=body.hike_value,
                    effective_from=str(body.effective_from),
                    reason=body.reason or "",
                    requested_by=actor_name or "—",
                )
    except Exception as exc:
        logger.warning("[HIKE] Notification email failed: %s", exc)

    return _serialize(req)


# ─── GET /finance/hike-requests/pending-count ─────────────────────────────────
# IMPORTANT: defined before /{id} routes so "pending-count" is not treated as id

@router.get(
    "/hike-requests/pending-count",
    summary="Count of pending salary hike requests",
)
def get_pending_hike_count(
    db: Session = Depends(get_db),
    _: Employee = _Actor,
):
    count = (
        db.query(SalaryHikeRequest)
        .filter(SalaryHikeRequest.status == "pending_finance_review")
        .count()
    )
    return {"count": count}


# ─── GET /finance/hike-requests ───────────────────────────────────────────────

@router.get(
    "/hike-requests",
    summary="List salary hike requests",
)
def list_hike_requests(
    status_filter: Optional[str] = None,
    employee_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: Employee = _Actor,
):
    q = db.query(SalaryHikeRequest)
    if status_filter:
        q = q.filter(SalaryHikeRequest.status == status_filter)
    if employee_id:
        q = q.filter(SalaryHikeRequest.employee_id == employee_id)
    requests = q.order_by(SalaryHikeRequest.created_at.desc()).limit(limit).all()
    return [_serialize(r) for r in requests]


# ─── POST /finance/hike-requests/{id}/approve ─────────────────────────────────

@router.post(
    "/hike-requests/{request_id}/approve",
    summary="Finance approves a salary hike request and applies the salary revision",
)
def approve_hike_request(
    request_id: int,
    body: Optional[HikeReviewBody] = None,
    db: Session = Depends(get_db),
    actor: Employee = _Actor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != "pending_finance_review":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve a request with status '{req.status}'",
        )

    # Apply the salary revision
    try:
        payroll_service.create_salary_revision(
            db=db,
            employee_id=req.employee_id,
            new_ctc_annual=req.new_ctc,
            effective_from=req.effective_from,
            assigned_by=actor,
            revision_reason=req.reason or "Salary hike approved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    comment = body.comment if body else None
    from datetime import datetime as _dt
    req.status = "approved"
    req.reviewed_by_id = actor.id
    req.review_comment = comment
    # Production fields (v15)
    req.approved_by_id = actor.id
    req.approved_at = _dt.utcnow()
    db.commit()
    db.refresh(req)

    # Notify requester
    try:
        requester = req.requested_by
        to_email = _employee_email(requester)
        if to_email:
            send_hike_review_email(
                to_email=to_email,
                employee_name=_fmt_name(req.employee) or "—",
                decision="Approved",
                reviewed_by=_fmt_name(actor) or "—",
                remarks=comment or "",
                effective_from=str(req.effective_from),
                new_ctc=req.new_ctc,
            )
    except Exception as exc:
        logger.warning("[HIKE] Review email failed: %s", exc)

    return _serialize(req)


# ─── POST /finance/hike-requests/{id}/reject ──────────────────────────────────

@router.post(
    "/hike-requests/{request_id}/reject",
    summary="Finance rejects a salary hike request",
)
def reject_hike_request(
    request_id: int,
    body: HikeRejectBody,
    db: Session = Depends(get_db),
    actor: Employee = _Actor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != "pending_finance_review":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject a request with status '{req.status}'",
        )

    reason = (body.rejection_reason or body.comment or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required.")

    req.status = "rejected"
    req.reviewed_by_id = actor.id
    req.review_comment = body.comment or reason
    # Store rejection_reason separately for compliance audit (v15)
    req.rejection_reason = reason
    db.commit()
    db.refresh(req)

    # Notify requester
    try:
        requester = req.requested_by
        to_email = _employee_email(requester)
        if to_email:
            send_hike_review_email(
                to_email=to_email,
                employee_name=_fmt_name(req.employee) or "—",
                decision="Rejected",
                reviewed_by=_fmt_name(actor) or "—",
                remarks=body.comment or "",
                effective_from=str(req.effective_from),
                new_ctc=req.new_ctc,
            )
    except Exception as exc:
        logger.warning("[HIKE] Review email failed: %s", exc)

    return _serialize(req)
