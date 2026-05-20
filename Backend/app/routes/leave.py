"""Leave management API.

Routes are role-aware; the engine in app.services.leave_engine owns the
business logic and side effects (notifications, audit, balance math).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    Employee, LeaveAuditLog, LeaveBalance, LeaveRequest, LeaveType, Role,
)
from app.schemas.leave import (
    ApprovalStamp, AuditEntryOut, LeaveApplyIn, LeaveBalanceOut,
    LeaveDraftIn, LeaveDraftUpdateIn, LeaveRequestDetailOut, LeaveRequestOut,
    LeaveTypeOut, RejectIn,
)
from app.services.leave_engine import (
    LeaveEngineError, apply_leave, approve_cancellation, approve_leave,
    cancel_leave, create_draft, discard_draft, reject_leave, submit_draft,
    update_draft,
)
from app.services.leave_validation import run_validation


router = APIRouter(prefix="/leave", tags=["leave"])


# ---- helpers --------------------------------------------------------

def _role_name(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _serialize(req: LeaveRequest) -> LeaveRequestOut:
    return LeaveRequestOut(
        id=req.id,
        employee_id=req.employee_id,
        employee_name=req.employee.full_name if req.employee else "",
        employee_code=req.employee.employee_code if req.employee else None,
        leave_type_id=req.leave_type_id,
        leave_type_name=req.leave_type.name if req.leave_type else "",
        start_date=req.start_date,
        end_date=req.end_date,
        total_days=req.total_days,
        reason=req.reason,
        status=req.status,
        next_approver_role=req.next_approver_role,
        manager_approval=ApprovalStamp(
            by_id=req.manager_approved_by,
            by_name=(_lookup_name(req, req.manager_approved_by)),
            at=req.manager_approved_at,
        ),
        hr_approval=ApprovalStamp(
            by_id=req.hr_approved_by,
            by_name=(_lookup_name(req, req.hr_approved_by)),
            at=req.hr_approved_at,
        ),
        cancel_requested_at=req.cancel_requested_at,
        rejection_reason=req.rejection_reason,
        sla_escalation_level=int(req.sla_escalation_level or 0),
        sla_last_alert_at=req.sla_last_alert_at,
        approver_override_id=req.approver_override_id,
        payroll_sync_status=req.payroll_sync_status or "na",
        payroll_synced_at=req.payroll_synced_at,
        payroll_sync_attempts=int(req.payroll_sync_attempts or 0),
        payroll_last_error=req.payroll_last_error,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def _lookup_name(req: LeaveRequest, eid: Optional[int]) -> Optional[str]:
    if not eid:
        return None
    if req.approver and req.approver.id == eid:
        return req.approver.full_name
    return None


def _ensure_can_view(user: Employee, req: LeaveRequest) -> None:
    role = _role_name(user)
    if role == "admin":
        return
    if user.id == req.employee_id:
        return
    if role == "manager" and req.employee.reporting_manager_id == user.id:
        return
    raise HTTPException(status_code=403, detail="You are not allowed to view this leave request.")


def _engine(call):
    """Translate LeaveEngineError into HTTPException."""
    try:
        return call()
    except LeaveEngineError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ---- Reference: leave types ----------------------------------------

@router.get("/types", response_model=list[LeaveTypeOut])
def list_leave_types(db: Session = Depends(get_db), _u: Employee = Depends(get_current_user)):
    rows = db.query(LeaveType).order_by(LeaveType.name).all()
    return [LeaveTypeOut.model_validate(r) for r in rows]


# ---- Apply / list / get --------------------------------------------

@router.post("/apply", response_model=LeaveRequestOut, status_code=201)
def apply(payload: LeaveApplyIn, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    req = _engine(lambda: apply_leave(
        db, user, payload.leave_type_id, payload.start_date, payload.end_date, payload.reason,
    ))
    return _serialize(req)


# ── Working-day apply variant ─────────────────────────────────────────────
# Client supplies start_date + requested_days; backend computes end_date
# by skipping weekends + location-scoped holidays. The legacy /apply
# remains for callers that still send explicit start+end.
from pydantic import BaseModel, Field as _PydField

class LeaveApplyByDaysIn(BaseModel):
    leave_type_id: str
    start_date: date
    requested_days: float = _PydField(..., gt=0, description="Working days the employee wants off")
    reason: Optional[str] = None
    half_day_start: bool = False
    half_day_end:   bool = False


@router.post("/apply-by-days", response_model=LeaveRequestOut, status_code=201)
def apply_by_days(payload: LeaveApplyByDaysIn,
                  db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    from app.services.leave_engine import apply_leave_by_days
    req = _engine(lambda: apply_leave_by_days(
        db, user,
        payload.leave_type_id, payload.start_date, payload.requested_days, payload.reason,
        half_day_start=payload.half_day_start, half_day_end=payload.half_day_end,
    ))
    return _serialize(req)


class LeavePreviewIn(BaseModel):
    start_date: date
    requested_days: float = _PydField(..., gt=0)
    half_day_start: bool = False
    half_day_end:   bool = False


@router.post("/preview")
def preview(payload: LeavePreviewIn,
            db: Session = Depends(get_db),
            user: Employee = Depends(get_current_user)):
    """Preview the working-day expansion of a leave request.

    Returns the calculated end_date and a day-by-day breakdown that the
    UI can render before the employee commits. Never mutates state.
    """
    from app.services.working_day_engine import preview_leave_span, SpanError
    try:
        return preview_leave_span(
            db, user, payload.start_date, payload.requested_days,
            half_day_start=payload.half_day_start,
            half_day_end=payload.half_day_end,
        )
    except SpanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---- Drafts --------------------------------------------------------

@router.post("/draft", response_model=LeaveRequestOut, status_code=201)
def draft_create(payload: LeaveDraftIn, db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_user)):
    req = _engine(lambda: create_draft(
        db, user, payload.leave_type_id, payload.start_date, payload.end_date, payload.reason,
    ))
    return _serialize(req)


@router.get("/drafts", response_model=list[LeaveRequestOut])
def draft_list(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    rows = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == user.id, LeaveRequest.status == "draft")
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )
    return [_serialize(r) for r in rows]


@router.put("/{request_id}/draft", response_model=LeaveRequestOut)
def draft_update(request_id: str, payload: LeaveDraftUpdateIn,
                 db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return _serialize(_engine(lambda: update_draft(
        db, user, req,
        leave_type_id=payload.leave_type_id,
        start=payload.start_date,
        end=payload.end_date,
        reason=payload.reason,
    )))


@router.post("/{request_id}/submit", response_model=LeaveRequestOut)
def draft_submit(request_id: str, db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return _serialize(_engine(lambda: submit_draft(db, user, req)))


@router.delete("/{request_id}/draft", status_code=204)
def draft_delete(request_id: str, db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    _engine(lambda: discard_draft(db, user, req))
    return None


@router.post("/validate")
def validate_preview(payload: LeaveApplyIn, db: Session = Depends(get_db),
                     user: Employee = Depends(get_current_user)):
    """Dry-run the validation pipeline so the frontend can show errors and
    warnings before the user submits a draft / applies for leave."""
    ctx = run_validation(
        db, user, payload.leave_type_id, payload.start_date, payload.end_date, payload.reason,
    )
    return {
        "ok": not ctx.errors,
        "errors": ctx.errors,
        "warnings": ctx.warnings,
        "days": ctx.days,
    }


@router.get("/list", response_model=list[LeaveRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = Query(None),
    pending_my_approval: bool = Query(False, description="Only requests waiting on the caller."),
):
    role = _role_name(user)
    q = db.query(LeaveRequest).join(Employee, LeaveRequest.employee_id == Employee.id)

    # Scope by role.
    if role == "admin":
        if employee_id is not None:
            q = q.filter(LeaveRequest.employee_id == employee_id)
    elif role == "manager":
        if employee_id is not None:
            # Manager can only fetch a specific employee from their team.
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not in your team.")
            q = q.filter(LeaveRequest.employee_id == employee_id)
        else:
            q = q.filter(Employee.reporting_manager_id == user.id)
    else:  # employee
        q = q.filter(LeaveRequest.employee_id == user.id)

    if status_filter:
        q = q.filter(LeaveRequest.status == status_filter.lower())

    if pending_my_approval:
        # Pending approvals waiting on this caller specifically.
        if role == "manager":
            q = q.filter(
                LeaveRequest.status.in_(["pending", "cancel_pending"]),
                LeaveRequest.next_approver_role == "manager",
                Employee.reporting_manager_id == user.id,
            )
        elif role == "admin":
            q = q.filter(
                LeaveRequest.status.in_(["pending", "cancel_pending"]),
                LeaveRequest.next_approver_role == "hr",
            )
        else:
            return []  # employees never have pending approvals queued for them

    rows = q.order_by(LeaveRequest.created_at.desc()).all()
    return [_serialize(r) for r in rows]


@router.get("/{request_id}", response_model=LeaveRequestDetailOut)
def get_request(request_id: str, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    _ensure_can_view(user, req)

    audits = (
        db.query(LeaveAuditLog)
        .filter(LeaveAuditLog.leave_request_id == request_id)
        .order_by(LeaveAuditLog.created_at.asc())
        .all()
    )
    audit_out = [
        AuditEntryOut(
            id=a.id,
            action=a.action,
            actor_id=a.actor_id,
            actor_name=(a.actor.full_name if a.actor else None),
            from_status=a.from_status,
            to_status=a.to_status,
            note=a.note,
            created_at=a.created_at,
        )
        for a in audits
    ]
    base = _serialize(req)
    return LeaveRequestDetailOut(**base.model_dump(), audit=audit_out)


# ---- Approve / reject / cancel --------------------------------------

@router.post("/{request_id}/approve", response_model=LeaveRequestOut)
def approve(request_id: str, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can approve leave.")
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if req.status == "cancel_pending":
        # Convenience: /approve on a cancellation routes to approve_cancellation.
        return _serialize(_engine(lambda: approve_cancellation(db, user, req)))
    return _serialize(_engine(lambda: approve_leave(db, user, req)))


@router.post("/{request_id}/reject", response_model=LeaveRequestOut)
def reject(
    request_id: str,
    payload: RejectIn = RejectIn(),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can reject leave.")
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return _serialize(_engine(lambda: reject_leave(db, user, req, payload.reason)))


@router.post("/{request_id}/cancel", response_model=LeaveRequestOut)
def cancel(request_id: str, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return _serialize(_engine(lambda: cancel_leave(db, user, req)))


@router.post("/{request_id}/approve-cancel", response_model=LeaveRequestOut)
def approve_cancel(request_id: str, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can approve cancellations.")
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return _serialize(_engine(lambda: approve_cancellation(db, user, req)))


# ---- Balances -------------------------------------------------------

@router.get("/balance/me", response_model=list[LeaveBalanceOut])
def my_balance(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    return _balance_for_employee(db, user.id)


@router.get("/balance/{employee_id}", response_model=list[LeaveBalanceOut])
def balance_for(employee_id: int, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    role = _role_name(user)
    if role != "admin":
        if user.id == employee_id:
            return _balance_for_employee(db, employee_id)
        if role == "manager":
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not in your team.")
        else:
            raise HTTPException(status_code=403, detail="Not allowed.")
    return _balance_for_employee(db, employee_id)


def _balance_for_employee(db: Session, employee_id: int) -> list[LeaveBalanceOut]:
    rows = (
        db.query(LeaveBalance)
        .filter(LeaveBalance.employee_id == employee_id)
        .order_by(LeaveBalance.year.desc(), LeaveBalance.leave_type_id)
        .all()
    )
    out = []
    for b in rows:
        allocated = int(b.allocated_balance or b.opening_balance or 0)
        reserved  = int(b.reserved or 0)
        pending   = int(b.pending_balance or 0)
        # Canonical formula from Phase 5A: available = allocated - reserved - pending.
        available = max(0, allocated - reserved - pending)
        out.append(LeaveBalanceOut(
            id=b.id,
            employee_id=b.employee_id,
            leave_type_id=b.leave_type_id,
            leave_type_name=(b.leave_type.name if b.leave_type else None),
            year=b.year,
            opening_balance=b.opening_balance,
            used=b.used,
            reserved=reserved,
            current_balance=b.current_balance,
            available=available,
            allocated_balance=allocated,
            pending_balance=pending,
            row_version=int(b.row_version or 0),
        ))
    return out


# ===================================================================
# Phase 2: comp-off + scheduler trigger
# ===================================================================
from app.models import CompOffCredit
from app.schemas.leave import CompOffGrantIn, CompOffOut, SchedulerRunOut
from app.services.leave_engine import (
    approve_comp_off, grant_comp_off, process_pending_consumption, reject_comp_off,
)


def _comp_off_serialize(c: CompOffCredit) -> CompOffOut:
    return CompOffOut(
        id=c.id,
        employee_id=c.employee_id,
        employee_name=(c.employee.full_name if c.employee else None),
        worked_on=c.worked_on,
        days=c.days,
        reason=c.reason,
        proof_url=c.proof_url,
        status=c.status,
        next_approver_role=c.next_approver_role,
        manager_approved_at=c.manager_approved_at,
        hr_approved_at=c.hr_approved_at,
        expires_on=c.expires_on,
        rejection_reason=c.rejection_reason,
        created_at=c.created_at,
    )


@router.post("/comp-off/grant", response_model=CompOffOut, status_code=201)
def comp_off_grant(payload: CompOffGrantIn, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    credit = _engine(lambda: grant_comp_off(
        db, user, payload.employee_id, payload.worked_on, payload.days, payload.reason, payload.proof_url,
    ))
    return _comp_off_serialize(credit)


@router.get("/comp-off/list", response_model=list[CompOffOut])
def comp_off_list(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = Query(None),
):
    role = _role_name(user)
    q = db.query(CompOffCredit).join(Employee, CompOffCredit.employee_id == Employee.id)
    if role == "admin":
        if employee_id is not None:
            q = q.filter(CompOffCredit.employee_id == employee_id)
    elif role == "manager":
        if employee_id is not None:
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not in your team.")
            q = q.filter(CompOffCredit.employee_id == employee_id)
        else:
            q = q.filter(Employee.reporting_manager_id == user.id)
    else:
        q = q.filter(CompOffCredit.employee_id == user.id)

    if status_filter:
        q = q.filter(CompOffCredit.status == status_filter.lower())

    return [_comp_off_serialize(c) for c in q.order_by(CompOffCredit.created_at.desc()).all()]


@router.post("/comp-off/{credit_id}/approve", response_model=CompOffOut)
def comp_off_approve(credit_id: int, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can approve.")
    credit = db.get(CompOffCredit, credit_id)
    if not credit:
        raise HTTPException(status_code=404, detail="Not found")
    return _comp_off_serialize(_engine(lambda: approve_comp_off(db, user, credit)))


@router.post("/comp-off/{credit_id}/reject", response_model=CompOffOut)
def comp_off_reject(credit_id: int, payload: dict = None, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can reject.")
    credit = db.get(CompOffCredit, credit_id)
    if not credit:
        raise HTTPException(status_code=404, detail="Not found")
    reason = (payload or {}).get("reason")
    return _comp_off_serialize(_engine(lambda: reject_comp_off(db, user, credit, reason)))


# Scheduler trigger — admin-only manual trigger of the negative-flow scan.
@router.post("/scheduler/run", response_model=SchedulerRunOut)
def scheduler_run(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    return process_pending_consumption(db)


# ===================================================================
# Phase 3: Worked-on-leave + comp-off expiry
# ===================================================================
from app.models import WorkedOnLeaveRequest
from app.schemas.leave import WorkedOnLeaveOut, CompOffExpiryRunOut
from app.services.leave_engine import (
    approve_worked_on_leave, reject_worked_on_leave, expire_comp_off_credits,
)


def _wol_serialize(w: WorkedOnLeaveRequest) -> WorkedOnLeaveOut:
    return WorkedOnLeaveOut(
        id=w.id,
        leave_request_id=w.leave_request_id,
        employee_id=w.employee_id,
        employee_name=(w.employee.full_name if w.employee else None),
        present_dates=[d for d in (w.present_dates or "").split(",") if d],
        status=w.status,
        next_approver_role=w.next_approver_role,
        manager_approved_at=w.manager_approved_at,
        hr_approved_at=w.hr_approved_at,
        rejection_reason=w.rejection_reason,
        created_at=w.created_at,
    )


@router.get("/worked-on-leave/list", response_model=list[WorkedOnLeaveOut])
def wol_list(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    role = _role_name(user)
    q = db.query(WorkedOnLeaveRequest).join(Employee, WorkedOnLeaveRequest.employee_id == Employee.id)
    if role == "admin":
        pass  # all
    elif role == "manager":
        q = q.filter(Employee.reporting_manager_id == user.id)
    else:
        q = q.filter(WorkedOnLeaveRequest.employee_id == user.id)

    if status_filter:
        q = q.filter(WorkedOnLeaveRequest.status == status_filter.lower())

    return [_wol_serialize(w) for w in q.order_by(WorkedOnLeaveRequest.created_at.desc()).all()]


@router.post("/worked-on-leave/{wol_id}/approve", response_model=WorkedOnLeaveOut)
def wol_approve(wol_id: int, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can approve.")
    wol = db.get(WorkedOnLeaveRequest, wol_id)
    if not wol:
        raise HTTPException(status_code=404, detail="Not found")
    return _wol_serialize(_engine(lambda: approve_worked_on_leave(db, user, wol)))


@router.post("/worked-on-leave/{wol_id}/reject", response_model=WorkedOnLeaveOut)
def wol_reject(wol_id: int, payload: dict = None, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Only managers or admins can reject.")
    wol = db.get(WorkedOnLeaveRequest, wol_id)
    if not wol:
        raise HTTPException(status_code=404, detail="Not found")
    reason = (payload or {}).get("reason")
    return _wol_serialize(_engine(lambda: reject_worked_on_leave(db, user, wol, reason)))


@router.post("/comp-off/expire", response_model=CompOffExpiryRunOut)
def comp_off_expire(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    return expire_comp_off_credits(db)


# ===================================================================
# Admin maintenance: wipe all leave activity (admin only)
# Mirrors cleanup_leaves.py — same operations, returns the counts.
# ===================================================================
from app.models import (
    LeaveAuditLog as _LeaveAuditLog,
    Notification as _Notification,
    CompOffCredit as _CompOffCredit,
    LeaveRequest as _LeaveRequest,
    LeaveBalance as _LeaveBalance,
    WorkedOnLeaveRequest as _WorkedOnLeaveRequest,
)


@router.post("/admin/cleanup")
def admin_cleanup(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role_name(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")

    n_audit = db.query(_LeaveAuditLog).delete()
    n_wol   = db.query(_WorkedOnLeaveRequest).delete()
    n_notif = (
        db.query(_Notification)
        .filter(_Notification.leave_request_id.is_not(None))
        .delete(synchronize_session=False)
    )
    n_co    = db.query(_CompOffCredit).delete()
    n_req   = db.query(_LeaveRequest).delete()

    # Comp-off balances are zeroed out entirely; non-comp-off types reset to opening.
    comp_type_ids = {
        t.id for t in db.query(LeaveType).filter(LeaveType.name.ilike("%comp%")).all()
    }
    n_bal_reset = 0
    n_bal_zeroed = 0
    for b in db.query(_LeaveBalance).all():
        if b.leave_type_id in comp_type_ids:
            b.opening_balance = 0
            b.used = 0
            b.reserved = 0
            b.current_balance = 0
            n_bal_zeroed += 1
        else:
            b.used = 0
            b.reserved = 0
            b.current_balance = b.opening_balance or 0
            n_bal_reset += 1

    db.commit()
    return {
        "leave_requests_deleted": n_req,
        "audit_deleted": n_audit,
        "worked_on_leave_deleted": n_wol,
        "notifications_deleted": n_notif,
        "comp_off_deleted": n_co,
        "balances_reset": n_bal_reset,
        "comp_off_balances_zeroed": n_bal_zeroed,
    }


# ===================================================================
# Phase 3: payroll sync queue (admin only)
# ===================================================================
from app.schemas.leave import PayrollRetryOut, PayrollResetIn
from app.services.payroll_bridge import retry_pending_syncs


@router.get("/payroll/pending", response_model=list[LeaveRequestOut])
def payroll_pending(db: Session = Depends(get_db),
                    user: Employee = Depends(get_current_user)):
    """All consumed leaves whose payroll sync hasn't succeeded yet."""
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    rows = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.payroll_sync_status.in_(("pending", "failed")))
        .order_by(LeaveRequest.updated_at.desc())
        .all()
    )
    return [_serialize(r) for r in rows]


@router.post("/payroll/retry", response_model=PayrollRetryOut)
def payroll_retry(db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    """Trigger the payroll retry sweep on demand."""
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    return retry_pending_syncs(db)


# ===================================================================
# Phase 5B: accrual / carry-forward admin triggers + ledger inspection
# ===================================================================
from datetime import date as _date
from app.models import LeaveBalanceLedger
from app.services.leave_accrual import run_monthly_accrual, run_year_end


@router.post("/admin/accrual/run-monthly")
def admin_run_monthly_accrual(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Manual trigger. Defaults to the current calendar month. Idempotent —
    re-running for the same (year, month) skips already-posted entries."""
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    today = _date.today()
    return run_monthly_accrual(db, year or today.year, month or today.month)


@router.post("/admin/year-end/run")
def admin_run_year_end(
    closing_year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Manual trigger. Defaults to previous calendar year. Carry-forward +
    yearly-accrual passes are both idempotent on their reference ids."""
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    cy = closing_year if closing_year is not None else (_date.today().year - 1)
    return run_year_end(db, cy)


@router.get("/{request_id}/ledger")
def request_ledger(request_id: str,
                   db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_user)):
    """Every ledger entry whose reference points at this leave request.
    Visible to admin, manager-of-the-employee, and the employee themselves."""
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(404, "Leave request not found.")
    _ensure_can_view(user, req)
    rows = (
        db.query(LeaveBalanceLedger)
        .filter(
            LeaveBalanceLedger.reference_type == "leave_request",
            LeaveBalanceLedger.reference_id == request_id,
        )
        .order_by(LeaveBalanceLedger.created_at.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "transaction_type": r.transaction_type,
            "bucket": r.bucket,
            "days": r.days,
            "before_allocated": r.before_allocated,
            "before_reserved": r.before_reserved,
            "before_used": r.before_used,
            "after_allocated": r.after_allocated,
            "after_reserved": r.after_reserved,
            "after_used": r.after_used,
            "actor_id": r.actor_id,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/balance/{employee_id}/ledger")
def employee_balance_ledger(
    employee_id: int,
    leave_type_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Full ledger history for an employee's balance (one leave type or all).
    RBAC: admin sees any; manager sees their team; employee sees their own."""
    role = _role_name(user)
    if role != "admin":
        if user.id == employee_id:
            pass
        elif role == "manager":
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(403, "Not in your team.")
        else:
            raise HTTPException(403, "Not allowed.")

    q = db.query(LeaveBalanceLedger).filter(LeaveBalanceLedger.employee_id == employee_id)
    if leave_type_id:
        q = q.filter(LeaveBalanceLedger.leave_type_id == leave_type_id)
    if year:
        q = q.filter(LeaveBalanceLedger.year == year)
    rows = q.order_by(LeaveBalanceLedger.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "leave_type_id": r.leave_type_id,
            "year": r.year,
            "transaction_type": r.transaction_type,
            "bucket": r.bucket,
            "days": r.days,
            "before_allocated": r.before_allocated,
            "before_reserved": r.before_reserved,
            "before_used": r.before_used,
            "after_allocated": r.after_allocated,
            "after_reserved": r.after_reserved,
            "after_used": r.after_used,
            "reference_type": r.reference_type,
            "reference_id": r.reference_id,
            "actor_id": r.actor_id,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/{request_id}/payroll/reset", response_model=LeaveRequestOut)
def payroll_reset(request_id: str,
                  payload: PayrollResetIn = PayrollResetIn(),
                  db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    """Admin escape hatch: clear a row's attempt counter / status so the
    next retry sweep treats it as fresh. Use after fixing the underlying
    cause (e.g. reopening a finalized payroll period)."""
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    if payload.new_status not in ("pending", "na"):
        raise HTTPException(400, "new_status must be 'pending' or 'na'.")
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(404, "Leave request not found.")
    if payload.reset_attempts:
        req.payroll_sync_attempts = 0
    req.payroll_sync_status = payload.new_status
    req.payroll_last_error = None
    db.commit()
    db.refresh(req)
    return _serialize(req)


# ===================================================================
# Phase 5D: balance reconciliation (admin only).
#
# Replays the immutable leave_balance_ledger to compute expected
# allocated/reserved/used per LeaveBalance row and reports drift.
# Heals legacy rows broken by the historical comp-off bypass bug.
# ===================================================================
from app.services.leave_reconcile import reconcile as _reconcile_balances


@router.post("/admin/reconcile-balances")
def admin_reconcile_balances(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    employee_id: Optional[int] = Query(None, description="Limit to one employee."),
    leave_type_id: Optional[str] = Query(None, description="Limit to one leave type."),
    year: Optional[int] = Query(None, description="Limit to one year."),
    apply: bool = Query(False, description="If true, write corrections; otherwise dry-run."),
):
    """Replay the ledger and report (or correct) balance drift.

    `apply=false` (default) returns a structured drift report without
    touching the DB; safe to run any time. `apply=true` writes the
    corrected (allocated, reserved, used, opening, current) values and
    bumps row_version on each modified row.
    """
    if _role_name(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    return _reconcile_balances(
        db,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=year,
        dry_run=not apply,
    )
