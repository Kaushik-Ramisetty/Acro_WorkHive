"""Salary Revision / Hike Request API.

Prefix : /finance
Auth   : admin/hr create, finance recommends, finance_head final-approves

Workflow
--------
1. HR/Admin creates request  → status: pending_finance_review
2. Finance reviews and recommends:
     /approve  → recommend_approval   → status: pending_finance_head_approval
     /reject   → recommend_rejection  → status: pending_finance_head_approval
   Finance CANNOT directly approve or reject. Both actions forward to Finance Head.
3. Finance Head makes final decision:
     /head-approve → applies salary revision → status: approved
     /head-reject  → status: rejected

Endpoints
---------
POST   /finance/hike-requests                    Create a salary revision request (HR/admin)
GET    /finance/hike-requests                    List requests
GET    /finance/hike-requests/pending-count      Count of pending requests
GET    /finance/hike-requests/{id}               Get single request
PUT    /finance/hike-requests/{id}               Edit a pending request (HR/admin only)
POST   /finance/hike-requests/{id}/cancel        Cancel a pending request (HR/admin only)
POST   /finance/hike-requests/{id}/approve       Finance recommends approval (→ Finance Head)
POST   /finance/hike-requests/{id}/reject        Finance recommends rejection (→ Finance Head)
POST   /finance/hike-requests/{id}/head-approve  Finance Head final approval (applies salary)
POST   /finance/hike-requests/{id}/head-reject   Finance Head final rejection
"""
from __future__ import annotations

import logging
from datetime import date, datetime
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
    dependencies=[Depends(role_required("admin", "hr", "finance", "finance_head"))],
)

_CreateActor = Depends(role_required("admin", "hr"))
_ReadActor = Depends(role_required("admin", "hr", "finance", "finance_head"))
_FinanceActor = Depends(role_required("finance"))
_FinanceHeadActor = Depends(role_required("finance_head"))

STATUS_PENDING_FINANCE = "pending_finance_review"
STATUS_PENDING_HEAD = "pending_finance_head_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

ALLOWED_REASONS = {
    "Annual Appraisal",
    "Promotion",
    "Confirmation",
    "Market Correction",
    "Retention Hike",
    "Other",
}


# ─── Request / Response Schemas ───────────────────────────────────────────────

class HikeRequestCreate(BaseModel):
    employee_id: int
    # New path: provide new_ctc directly (preferred for Salary Revision workflow)
    new_ctc: Optional[float] = Field(None, gt=0, description="New annual CTC in INR (direct input)")
    # Legacy path: provide hike_type + hike_value (kept for backward compat)
    hike_type: Optional[str] = Field(None, description="'percentage' or 'fixed'")
    hike_value: Optional[float] = Field(None, gt=0, description="Percentage or fixed amount")
    effective_from: date
    reason: Optional[str] = Field(None, description=f"One of: {', '.join(sorted(ALLOWED_REASONS))}")


class HikeRequestUpdate(BaseModel):
    new_ctc: Optional[float] = Field(None, gt=0)
    effective_from: Optional[date] = None
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
    joining_date = None
    if emp:
        if emp.department:
            dept = emp.department.name
        if emp.designation:
            desig = emp.designation.title
        joining_date = str(emp.date_of_joining) if emp.date_of_joining else None

    old_ctc = req.old_ctc or 0.0
    new_ctc = req.new_ctc or 0.0
    change_amount = round(new_ctc - old_ctc, 2)
    change_pct = round((change_amount / old_ctc * 100), 2) if old_ctc else 0.0

    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": _fmt_name(emp),
        "employee_code": (emp.employee_code or f"EMP{emp.id:04d}") if emp else None,
        "department": dept,
        "designation": desig,
        "joining_date": joining_date,
        "old_ctc": old_ctc,
        "new_ctc": new_ctc,
        "change_amount": change_amount,
        "change_pct": change_pct,
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
        "approved_by_id": req.approved_by_id,
        "approved_by_name": _fmt_name(req.approved_by),
        "approved_at": req.approved_at.isoformat() if req.approved_at else None,
        "rejection_reason": req.rejection_reason,
        "finance_recommendation": req.finance_recommendation,
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
    actor: Employee = _CreateActor,
):
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # ── Reason validation ──
    if body.reason:
        if body.reason not in ALLOWED_REASONS:
            raise HTTPException(
                status_code=400,
                detail=f"reason must be one of: {', '.join(sorted(ALLOWED_REASONS))}",
            )

    # ── Joining date guard ──
    if emp.date_of_joining and body.effective_from < emp.date_of_joining:
        raise HTTPException(
            status_code=400,
            detail=(
                f"effective_from ({body.effective_from}) cannot be before "
                f"the employee's joining date ({emp.date_of_joining})."
            ),
        )

    # ── Duplicate pending guard ──
    duplicate = (
        db.query(SalaryHikeRequest)
        .filter(
            SalaryHikeRequest.employee_id == body.employee_id,
            SalaryHikeRequest.effective_from == body.effective_from,
            SalaryHikeRequest.status.in_([STATUS_PENDING_FINANCE, STATUS_PENDING_HEAD]),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A pending salary revision already exists for this employee "
                f"with effective date {body.effective_from} (request #{duplicate.id}). "
                "Cancel or edit the existing request first."
            ),
        )

    # ── Production guard: validate effective_from against closed months ──
    date_conflict = _validate_effective_date_vs_closed_months(db, body.effective_from)
    if date_conflict:
        raise HTTPException(status_code=400, detail=date_conflict)

    old_ctc = _get_active_ctc(db, body.employee_id)

    # ── Compute new CTC ──
    if body.new_ctc is not None:
        new_ctc = round(body.new_ctc, 2)
        hike_type = "fixed"
        hike_value = round(body.new_ctc - old_ctc, 2)
    elif body.hike_type and body.hike_value is not None:
        if body.hike_type not in ("percentage", "fixed"):
            raise HTTPException(status_code=400, detail="hike_type must be 'percentage' or 'fixed'")
        if body.hike_type == "percentage":
            new_ctc = old_ctc * (1 + body.hike_value / 100)
        else:
            new_ctc = old_ctc + body.hike_value
        new_ctc = round(new_ctc, 2)
        hike_type = body.hike_type
        hike_value = body.hike_value
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'new_ctc' (direct CTC) or both 'hike_type' and 'hike_value'.",
        )

    if new_ctc <= 0:
        raise HTTPException(status_code=400, detail="New CTC must be greater than zero.")

    req = SalaryHikeRequest(
        employee_id=body.employee_id,
        old_ctc=old_ctc,
        new_ctc=new_ctc,
        hike_type=hike_type,
        hike_value=hike_value,
        effective_from=body.effective_from,
        reason=body.reason,
        status=STATUS_PENDING_FINANCE,
        requested_by_id=actor.id,
        effective_date_validated=True,
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


# ─── POST /finance/hike-requests/{id}/head-approve ───────────────────────────

@router.post(
    "/hike-requests/{request_id}/head-approve",
    summary="Finance Head gives final approval and applies the salary revision",
)
def head_approve_hike_request(
    request_id: int,
    body: Optional[HikeReviewBody] = None,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceHeadActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != STATUS_PENDING_HEAD:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot final approve a request with status '{req.status}'",
        )

    # Validate new_ctc is present and positive before applying the salary revision
    if not req.new_ctc or req.new_ctc <= 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve: new CTC is missing or zero. The salary revision request must be updated with a valid new CTC before final approval.",
        )

    # Validate effective_from is present and not before the employee's joining date
    if not req.effective_from:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve: effective date is missing. Update the request with a valid effective date.",
        )
    employee = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if employee and employee.date_of_joining and req.effective_from < employee.date_of_joining:
        raise HTTPException(
            status_code=400,
            detail=f"Effective date {req.effective_from} cannot be before employee joining date {employee.date_of_joining}.",
        )

    date_conflict = _validate_effective_date_vs_closed_months(db, req.effective_from)
    if date_conflict:
        raise HTTPException(status_code=400, detail=date_conflict)

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
    req.status = STATUS_APPROVED
    req.approved_by_id = actor.id
    req.approved_at = datetime.utcnow()
    req.rejection_reason = None
    db.commit()
    db.refresh(req)

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
        logger.warning("[HIKE] Finance Head approval email failed: %s", exc)

    return _serialize(req)


# ─── POST /finance/hike-requests/{id}/head-reject ─────────────────────────────

@router.post(
    "/hike-requests/{request_id}/head-reject",
    summary="Finance Head rejects a salary hike request",
)
def head_reject_hike_request(
    request_id: int,
    body: HikeRejectBody,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceHeadActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != STATUS_PENDING_HEAD:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject a request with status '{req.status}'",
        )

    reason = (body.rejection_reason or body.comment or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required.")

    req.status = STATUS_REJECTED
    req.rejection_reason = reason
    db.commit()
    db.refresh(req)

    try:
        requester = req.requested_by
        to_email = _employee_email(requester)
        if to_email:
            send_hike_review_email(
                to_email=to_email,
                employee_name=_fmt_name(req.employee) or "—",
                decision="Rejected",
                reviewed_by=_fmt_name(actor) or "—",
                remarks=body.comment or reason,
                effective_from=str(req.effective_from),
                new_ctc=req.new_ctc,
            )
    except Exception as exc:
        logger.warning("[HIKE] Finance Head rejection email failed: %s", exc)

    return _serialize(req)


# ─── GET /finance/hike-requests/pending-count ─────────────────────────────────
@router.get(
    "/hike-requests/pending-count",
    summary="Count of pending salary hike requests",
)
def get_pending_hike_count(
    db: Session = Depends(get_db),
    actor: Employee = _ReadActor,
):
    finance_count = (
        db.query(SalaryHikeRequest)
        .filter(SalaryHikeRequest.status == STATUS_PENDING_FINANCE)
        .count()
    )
    head_count = (
        db.query(SalaryHikeRequest)
        .filter(SalaryHikeRequest.status == STATUS_PENDING_HEAD)
        .count()
    )
    actor_role = (actor.role.name.lower() if actor.role else "")
    count = head_count if actor_role == "finance_head" else finance_count
    return {
        "count": count,
        "pending_finance_review": finance_count,
        "pending_finance_head_approval": head_count,
    }


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
    _: Employee = _ReadActor,
):
    q = db.query(SalaryHikeRequest)
    if status_filter:
        q = q.filter(SalaryHikeRequest.status == status_filter)
    if employee_id:
        q = q.filter(SalaryHikeRequest.employee_id == employee_id)
    requests = q.order_by(SalaryHikeRequest.created_at.desc()).limit(limit).all()
    return [_serialize(r) for r in requests]


# ─── GET /finance/hike-requests/{id} ─────────────────────────────────────────

@router.get(
    "/hike-requests/{request_id}",
    summary="Get a single salary revision request",
)
def get_hike_request(
    request_id: int,
    db: Session = Depends(get_db),
    _: Employee = _ReadActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return _serialize(req)


# ─── PUT /finance/hike-requests/{id} ─────────────────────────────────────────

@router.put(
    "/hike-requests/{request_id}",
    summary="Edit a pending salary revision request (HR/admin only)",
)
def update_hike_request(
    request_id: int,
    body: HikeRequestUpdate,
    db: Session = Depends(get_db),
    actor: Employee = _CreateActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Only pending-finance-review requests can be edited (current status: '{req.status}').",
        )

    if body.reason is not None:
        if body.reason not in ALLOWED_REASONS:
            raise HTTPException(
                status_code=400,
                detail=f"reason must be one of: {', '.join(sorted(ALLOWED_REASONS))}",
            )
        req.reason = body.reason

    if body.effective_from is not None:
        emp = req.employee
        if emp and emp.date_of_joining and body.effective_from < emp.date_of_joining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"effective_from ({body.effective_from}) cannot be before "
                    f"the employee's joining date ({emp.date_of_joining})."
                ),
            )
        date_conflict = _validate_effective_date_vs_closed_months(db, body.effective_from)
        if date_conflict:
            raise HTTPException(status_code=400, detail=date_conflict)
        # Duplicate check (excluding self)
        duplicate = (
            db.query(SalaryHikeRequest)
            .filter(
                SalaryHikeRequest.employee_id == req.employee_id,
                SalaryHikeRequest.effective_from == body.effective_from,
                SalaryHikeRequest.status.in_([STATUS_PENDING_FINANCE, STATUS_PENDING_HEAD]),
                SalaryHikeRequest.id != request_id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Another pending revision exists for this employee with "
                    f"effective date {body.effective_from} (request #{duplicate.id})."
                ),
            )
        req.effective_from = body.effective_from

    if body.new_ctc is not None:
        old_ctc = req.old_ctc or 0.0
        req.new_ctc = round(body.new_ctc, 2)
        req.hike_type = "fixed"
        req.hike_value = round(body.new_ctc - old_ctc, 2)

    db.commit()
    db.refresh(req)
    return _serialize(req)


# ─── POST /finance/hike-requests/{id}/cancel ─────────────────────────────────

@router.post(
    "/hike-requests/{request_id}/cancel",
    summary="Cancel a pending salary revision request (HR/admin only)",
)
def cancel_hike_request(
    request_id: int,
    db: Session = Depends(get_db),
    actor: Employee = _CreateActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Only pending-finance-review requests can be cancelled (current status: '{req.status}').",
        )
    db.delete(req)
    db.commit()
    return {"message": "Salary revision request cancelled.", "id": request_id}


# ─── POST /finance/hike-requests/{id}/approve ─────────────────────────────────

@router.post(
    "/hike-requests/{request_id}/approve",
    summary="Finance recommends approval and forwards to Finance Head for final decision",
)
def approve_hike_request(
    request_id: int,
    body: Optional[HikeReviewBody] = None,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot review a request with status '{req.status}'",
        )

    comment = body.comment if body else None
    req.status = STATUS_PENDING_HEAD
    req.reviewed_by_id = actor.id
    req.review_comment = comment
    req.finance_recommendation = "recommend_approval"
    req.approved_by_id = None
    req.approved_at = None
    req.rejection_reason = None
    db.commit()
    db.refresh(req)

    # Notify requester: Finance reviewed and recommended approval, pending Finance Head.
    try:
        requester = req.requested_by
        to_email = _employee_email(requester)
        if to_email:
            send_hike_review_email(
                to_email=to_email,
                employee_name=_fmt_name(req.employee) or "—",
                decision="Finance Recommends Approval — Pending Finance Head Final Decision",
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
    summary="Finance recommends rejection and forwards to Finance Head for final decision",
)
def reject_hike_request(
    request_id: int,
    body: HikeRejectBody,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceActor,
):
    req = db.query(SalaryHikeRequest).filter(SalaryHikeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Hike request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot review a request with status '{req.status}'",
        )

    reason = (body.rejection_reason or body.comment or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required.")

    # Finance cannot directly reject — it forwards to Finance Head with a
    # rejection recommendation. Only Finance Head gives the final rejection.
    req.status = STATUS_PENDING_HEAD
    req.reviewed_by_id = actor.id
    req.review_comment = body.comment or reason
    req.finance_recommendation = "recommend_rejection"
    # Store the reason for Finance Head to review and for compliance audit
    req.rejection_reason = reason
    req.approved_by_id = None
    req.approved_at = None
    db.commit()
    db.refresh(req)

    # Notify requester that Finance reviewed and recommends rejection (not final).
    try:
        requester = req.requested_by
        to_email = _employee_email(requester)
        if to_email:
            send_hike_review_email(
                to_email=to_email,
                employee_name=_fmt_name(req.employee) or "—",
                decision="Finance Recommends Rejection — Pending Finance Head Final Decision",
                reviewed_by=_fmt_name(actor) or "—",
                remarks=body.comment or reason,
                effective_from=str(req.effective_from),
                new_ctc=req.new_ctc,
            )
    except Exception as exc:
        logger.warning("[HIKE] Review email failed: %s", exc)

    return _serialize(req)
