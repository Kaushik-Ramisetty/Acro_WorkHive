"""Bonus Request API.

Prefix : /finance
Auth   : admin/hr create, finance recommends, finance_head final-approves

Workflow
--------
1. HR/Admin creates  → status: pending_finance_review
2. Finance reviews (both actions forward to Finance Head):
     /approve  → recommend approval   → status: pending_finance_head_approval
     /reject   → recommend rejection  → status: pending_finance_head_approval
3. Finance Head decides:
     /head-approve → status: approved (auto-creates PayrollAdjustment if run exists)
     /head-reject  → status: rejected
4. For approved-but-not-applied:
     /apply-to-run → creates PayrollAdjustment → status: applied

Endpoints
---------
POST   /finance/bonus-requests                    Create (HR/admin)
GET    /finance/bonus-requests                    List
GET    /finance/bonus-requests/pending-count      Count awaiting action
GET    /finance/bonus-requests/{id}               Get single
PUT    /finance/bonus-requests/{id}               Edit pending (HR/admin)
POST   /finance/bonus-requests/{id}/cancel        Cancel pending (HR/admin)
POST   /finance/bonus-requests/{id}/approve       Finance recommends (→ Finance Head)
POST   /finance/bonus-requests/{id}/reject        Finance recommends rejection (→ Finance Head)
POST   /finance/bonus-requests/{id}/head-approve  Finance Head final approval
POST   /finance/bonus-requests/{id}/head-reject   Finance Head final rejection
POST   /finance/bonus-requests/{id}/apply-to-run  Apply approved bonus to a payroll run
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.bonus_request import BonusRequest
from app.models.employee import Employee
from app.models.payroll import PayrollRun
from app.models.payroll_extended import PayrollAdjustment

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/finance",
    tags=["Finance - Bonus Requests"],
    dependencies=[Depends(role_required("admin", "hr", "finance", "finance_head"))],
)

_CreateActor      = Depends(role_required("admin", "hr"))
_ReadActor        = Depends(role_required("admin", "hr", "finance", "finance_head"))
_FinanceActor     = Depends(role_required("finance"))
_FinanceHeadActor = Depends(role_required("finance_head"))
_FinanceOrHead    = Depends(role_required("finance", "finance_head"))

STATUS_PENDING_FINANCE = "pending_finance_review"
STATUS_PENDING_HEAD    = "pending_finance_head_approval"
STATUS_WAITING         = "waiting_for_payroll_application"
STATUS_APPROVED        = "approved"   # off_cycle only after head approval
STATUS_APPLIED         = "applied"
STATUS_REJECTED        = "rejected"

BONUS_TYPES = {
    "Joining Bonus",
    "Annual Bonus",
    "Performance Bonus",
    "Incentive",
    "Arrears",
    "Special Bonus",
    "Other",
}

BONUS_TYPE_TO_ADJ_TYPE: dict[str, str] = {
    "Joining Bonus":     "bonus",
    "Annual Bonus":      "bonus",
    "Performance Bonus": "bonus",
    "Incentive":         "bonus",
    "Arrears":           "arrears",
    "Special Bonus":     "bonus",
    "Other":             "other_addition",
}

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Payroll run statuses that still allow new adjustments
EDITABLE_RUN_STATUSES = {"draft", "attendance_frozen", "processing", "under_review"}


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

PAYMENT_MODES = {"regular_payroll", "off_cycle"}


class BonusRequestCreate(BaseModel):
    employee_id:   int
    payroll_month: int   = Field(..., ge=1, le=12)
    payroll_year:  int   = Field(..., ge=2000, le=2100)
    bonus_type:    str
    amount:        float = Field(..., gt=0)
    reason:        Optional[str] = None
    payment_mode:  str   = "regular_payroll"  # regular_payroll | off_cycle


class BonusRequestUpdate(BaseModel):
    payroll_month: Optional[int]   = Field(None, ge=1, le=12)
    payroll_year:  Optional[int]   = Field(None, ge=2000, le=2100)
    bonus_type:    Optional[str]   = None
    amount:        Optional[float] = Field(None, gt=0)
    reason:        Optional[str]   = None
    payment_mode:  Optional[str]   = None


class ActionPayload(BaseModel):
    comment:          Optional[str] = None
    rejection_reason: Optional[str] = None


class ApplyToRunPayload(BaseModel):
    run_id: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _name(emp: Employee) -> str:
    return f"{emp.first_name} {emp.last_name or ''}".strip()


def _serialize(req: BonusRequest) -> dict:
    emp = req.employee
    return {
        "id":             req.id,
        "employee_id":    req.employee_id,
        "employee_name":  _name(emp) if emp else str(req.employee_id),
        "employee_code":  (emp.employee_code or f"EMP{req.employee_id:04d}") if emp else "",
        "department":     (emp.department.name if emp and emp.department else "—"),
        "payroll_month":  req.payroll_month,
        "payroll_year":   req.payroll_year,
        "payroll_month_label": f"{MONTH_NAMES[req.payroll_month]} {req.payroll_year}",
        "bonus_type":     req.bonus_type,
        "amount":         req.amount,
        "reason":         req.reason,
        "status":         req.status,
        "payment_mode":   getattr(req, "payment_mode", "regular_payroll") or "regular_payroll",
        "finance_recommendation": req.finance_recommendation,
        "finance_comment":        req.finance_comment,
        "rejection_reason":       req.rejection_reason,
        "payroll_run_id":         getattr(req, "payroll_run_id", None),
        "payroll_adjustment_id":  req.payroll_adjustment_id,
        "requested_by_id":   req.requested_by_id,
        "requested_by_name": _name(req.requested_by) if req.requested_by else None,
        "reviewed_by_id":    req.reviewed_by_id,
        "reviewed_by_name":  _name(req.reviewed_by) if req.reviewed_by else None,
        "approved_by_id":    req.approved_by_id,
        "approved_by_name":  _name(req.approved_by) if req.approved_by else None,
        "approved_at":  req.approved_at.isoformat() if req.approved_at else None,
        "created_at":   req.created_at.isoformat() if req.created_at else None,
        "updated_at":   req.updated_at.isoformat() if req.updated_at else None,
    }


def _find_editable_run(db: Session, month: int, year: int) -> PayrollRun | None:
    return (
        db.query(PayrollRun)
        .filter(
            PayrollRun.month == month,
            PayrollRun.year  == year,
            PayrollRun.status.in_(EDITABLE_RUN_STATUSES),
        )
        .first()
    )


def _attach_adjustment(db: Session, req: BonusRequest, run: PayrollRun) -> None:
    adj = PayrollAdjustment(
        run_id=run.id,
        employee_id=req.employee_id,
        adjustment_type=BONUS_TYPE_TO_ADJ_TYPE.get(req.bonus_type, "bonus"),
        direction="addition",
        amount=req.amount,
        description=f"{req.bonus_type}" + (f": {req.reason}" if req.reason else ""),
        is_taxable=True,
        approved_by_id=req.approved_by_id,
    )
    db.add(adj)
    db.flush()
    req.payroll_adjustment_id = adj.id
    req.payroll_run_id = run.id
    req.status = STATUS_APPLIED


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/bonus-requests", status_code=201)
def create_bonus_request(
    body: BonusRequestCreate,
    db:    Session  = Depends(get_db),
    actor: Employee = _CreateActor,
):
    if body.bonus_type not in BONUS_TYPES:
        raise HTTPException(400, f"Invalid bonus_type. Allowed: {sorted(BONUS_TYPES)}")

    payment_mode = (body.payment_mode or "regular_payroll").strip().lower()
    if payment_mode not in PAYMENT_MODES:
        raise HTTPException(400, f"Invalid payment_mode. Allowed: {sorted(PAYMENT_MODES)}")

    emp = db.get(Employee, body.employee_id)
    if not emp or getattr(emp, "is_deleted", False):
        raise HTTPException(404, "Employee not found")

    # For regular_payroll mode: block creation if the target payroll month is already closed
    if payment_mode == "regular_payroll":
        _CLOSED_STATUSES = {"closed", "published", "bank_advice_generated", "payslip_generated", "approved", "disbursed", "completed"}
        closed_run = (
            db.query(PayrollRun)
            .filter(
                PayrollRun.month == body.payroll_month,
                PayrollRun.year  == body.payroll_year,
                PayrollRun.status.in_(_CLOSED_STATUSES),
            )
            .first()
        )
        if closed_run:
            raise HTTPException(
                400,
                f"Payroll for {MONTH_NAMES[body.payroll_month]} {body.payroll_year} is already closed "
                f"(status: {closed_run.status}). Select a future payroll month or choose Off-Cycle Payment.",
            )

    # Block duplicate approved/applied bonus for same employee + type + month
    dup = (
        db.query(BonusRequest)
        .filter(
            BonusRequest.employee_id   == body.employee_id,
            BonusRequest.bonus_type    == body.bonus_type,
            BonusRequest.payroll_month == body.payroll_month,
            BonusRequest.payroll_year  == body.payroll_year,
            BonusRequest.status.in_([STATUS_WAITING, STATUS_APPROVED, STATUS_APPLIED]),
        )
        .first()
    )
    if dup:
        raise HTTPException(
            400,
            f"An approved {body.bonus_type} bonus already exists for this employee "
            f"in {MONTH_NAMES[body.payroll_month]} {body.payroll_year}.",
        )

    req = BonusRequest(
        employee_id=body.employee_id,
        payroll_month=body.payroll_month,
        payroll_year=body.payroll_year,
        bonus_type=body.bonus_type,
        amount=body.amount,
        reason=body.reason,
        payment_mode=payment_mode,
        status=STATUS_PENDING_FINANCE,
        requested_by_id=actor.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.get("/bonus-requests/pending-count")
def bonus_pending_count(
    db:    Session  = Depends(get_db),
    actor: Employee = _ReadActor,
):
    role_name = actor.role.name if actor.role else ""
    if role_name == "finance":
        count = (
            db.query(BonusRequest)
            .filter(BonusRequest.status == STATUS_PENDING_FINANCE)
            .count()
        )
    elif role_name == "finance_head":
        count = (
            db.query(BonusRequest)
            .filter(BonusRequest.status == STATUS_PENDING_HEAD)
            .count()
        )
    else:
        count = (
            db.query(BonusRequest)
            .filter(BonusRequest.status.in_([STATUS_PENDING_FINANCE, STATUS_PENDING_HEAD]))
            .count()
        )
    return {"pending_count": count}


@router.get("/bonus-requests")
def list_bonus_requests(
    status_filter: Optional[str] = Query(None),
    employee_id:   Optional[int] = Query(None),
    month:         Optional[int] = Query(None, ge=1, le=12),
    year:          Optional[int] = Query(None),
    limit:         int           = Query(200, le=500),
    db:    Session  = Depends(get_db),
    _:     Employee = _ReadActor,
):
    q = db.query(BonusRequest)
    if status_filter:
        q = q.filter(BonusRequest.status == status_filter)
    if employee_id:
        q = q.filter(BonusRequest.employee_id == employee_id)
    if month:
        q = q.filter(BonusRequest.payroll_month == month)
    if year:
        q = q.filter(BonusRequest.payroll_year == year)
    return [_serialize(r) for r in q.order_by(BonusRequest.created_at.desc()).limit(limit)]


@router.get("/bonus-requests/{req_id}")
def get_bonus_request(
    req_id: int,
    db:     Session  = Depends(get_db),
    _:      Employee = _ReadActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    return _serialize(req)


@router.put("/bonus-requests/{req_id}")
def update_bonus_request(
    req_id: int,
    body:  BonusRequestUpdate,
    db:    Session  = Depends(get_db),
    actor: Employee = _CreateActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(400, "Only pending_finance_review requests can be edited")
    if body.bonus_type is not None and body.bonus_type not in BONUS_TYPES:
        raise HTTPException(400, f"Invalid bonus_type. Allowed: {sorted(BONUS_TYPES)}")

    if body.payment_mode is not None and body.payment_mode not in PAYMENT_MODES:
        raise HTTPException(400, f"Invalid payment_mode. Allowed: {sorted(PAYMENT_MODES)}")

    for field, val in {
        "payroll_month": body.payroll_month,
        "payroll_year":  body.payroll_year,
        "bonus_type":    body.bonus_type,
        "amount":        body.amount,
        "reason":        body.reason,
        "payment_mode":  body.payment_mode,
    }.items():
        if val is not None:
            setattr(req, field, val)

    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.post("/bonus-requests/{req_id}/cancel")
def cancel_bonus_request(
    req_id: int,
    db:    Session  = Depends(get_db),
    actor: Employee = _CreateActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(400, "Only pending_finance_review requests can be cancelled")
    db.delete(req)
    db.commit()
    return {"message": "Bonus request cancelled"}


@router.post("/bonus-requests/{req_id}/approve")
def finance_recommend_approve(
    req_id: int,
    body:  ActionPayload = ActionPayload(),
    db:    Session       = Depends(get_db),
    actor: Employee      = _FinanceActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(400, "Request is not pending Finance review")

    req.status                 = STATUS_PENDING_HEAD
    req.finance_recommendation = "approve"
    req.finance_comment        = body.comment
    req.reviewed_by_id         = actor.id
    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.post("/bonus-requests/{req_id}/reject")
def finance_recommend_reject(
    req_id: int,
    body:  ActionPayload = ActionPayload(),
    db:    Session       = Depends(get_db),
    actor: Employee      = _FinanceActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_FINANCE:
        raise HTTPException(400, "Request is not pending Finance review")

    req.status                 = STATUS_PENDING_HEAD
    req.finance_recommendation = "reject"
    req.finance_comment        = body.comment
    req.reviewed_by_id         = actor.id
    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.post("/bonus-requests/{req_id}/head-approve")
def head_final_approve(
    req_id: int,
    body:  ActionPayload = ActionPayload(),
    db:    Session       = Depends(get_db),
    actor: Employee      = _FinanceHeadActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_HEAD:
        raise HTTPException(400, "Request is not pending Finance Head approval")

    req.approved_by_id = actor.id
    req.approved_at    = datetime.utcnow()

    payment_mode = getattr(req, "payment_mode", "regular_payroll") or "regular_payroll"

    if payment_mode == "off_cycle":
        # Off-cycle: create an OffCyclePayment record immediately.
        # The bonus NEVER touches payroll_runs or payroll_adjustments.
        req.status = STATUS_APPROVED
        from app.routes.off_cycle_payment import create_off_cycle_payment_from_bonus
        create_off_cycle_payment_from_bonus(db, req, actor.id)
    else:
        # regular_payroll: ALWAYS transition to waiting_for_payroll_application.
        # The bonus will be materialised as a PayrollAdjustment by _generate_employee_rows
        # when payroll is processed/recomputed for the matching month and year.
        req.status = STATUS_WAITING

    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.post("/bonus-requests/{req_id}/head-reject")
def head_final_reject(
    req_id: int,
    body:  ActionPayload = ActionPayload(),
    db:    Session       = Depends(get_db),
    actor: Employee      = _FinanceHeadActor,
):
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status != STATUS_PENDING_HEAD:
        raise HTTPException(400, "Request is not pending Finance Head approval")

    req.status            = STATUS_REJECTED
    req.approved_by_id    = actor.id
    req.approved_at       = datetime.utcnow()
    req.rejection_reason  = body.rejection_reason or body.comment
    db.commit()
    db.refresh(req)
    return _serialize(req)


@router.post("/bonus-requests/{req_id}/apply-to-run")
def apply_bonus_to_run(
    req_id: int,
    body:  ApplyToRunPayload,
    db:    Session  = Depends(get_db),
    actor: Employee = _FinanceOrHead,
):
    """Manually link an approved (not-yet-applied) bonus to a payroll run."""
    req = db.get(BonusRequest, req_id)
    if not req:
        raise HTTPException(404, "Bonus request not found")
    if req.status not in (STATUS_APPROVED, STATUS_WAITING):
        raise HTTPException(400, "Only approved or waiting bonus requests can be manually applied to a run")

    run = db.get(PayrollRun, body.run_id)
    if not run:
        raise HTTPException(404, "Payroll run not found")
    if run.status not in EDITABLE_RUN_STATUSES:
        raise HTTPException(400, f"Payroll run is not editable (status: {run.status})")
    if run.month != req.payroll_month or run.year != req.payroll_year:
        raise HTTPException(400, "Payroll run month/year does not match the bonus request")

    if not req.approved_by_id:
        req.approved_by_id = actor.id
    _attach_adjustment(db, req, run)
    db.commit()
    db.refresh(req)
    return _serialize(req)
