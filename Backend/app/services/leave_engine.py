"""Leave workflow engine.

All state transitions live here so the routes layer stays thin. Each
operation:
  1. validates inputs and authorization,
  2. updates the LeaveRequest + LeaveBalance,
  3. writes a LeaveAuditLog row,
  4. emits in-app Notifications.

Transitions implemented in Phase 1:
  apply              -> creates pending request
  approve            -> manager-stage or hr-stage approval (advances chain)
  reject             -> terminal rejection from any pending stage
  cancel             -> direct cancel (if pending) or open cancel-approval chain (if approved)
  approve_cancel     -> manager/hr approval of a cancel request
  reject_cancel      -> rejects the cancellation; leave stays approved

Draft workflow (added in enterprise refactor Phase 1):
  create_draft       -> persists a LeaveRequest with status="draft", no validation,
                        no notifications, no balance impact.
  update_draft       -> edit fields on a draft (owner only).
  submit_draft       -> runs the full validation pipeline and transitions
                        draft -> pending. Same notifications as apply_leave.
  discard_draft      -> hard-deletes a draft (owner only).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Attendance, CompOffCredit, DelegateAssignment, Employee, LeaveAuditLog,
    LeaveBalance, LeaveRequest, LeaveType, LedgerTxn, Notification, Role,
    WorkedOnLeaveRequest,
)
from app.services.leave_ledger import (
    LedgerError, adjust_pending, post_ledger_entry,
)
from app.services.leave_state_machine import (
    InvalidTransition, LeaveStatus, transition,
)
from app.services.email_dispatcher import dispatch_for_recipient
from utils.time_utils import now_utc


# ---------- helpers --------------------------------------------------

def _today() -> date:
    return now_utc().date()


def _utcnow() -> datetime:
    return now_utc()


def _next_request_id(db: Session) -> str:
    """Generate the next 'LR###' identifier."""
    last = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id.like("LR%"))
        .order_by(LeaveRequest.id.desc())
        .first()
    )
    n = 1
    if last and last.id and last.id.startswith("LR"):
        try:
            n = int(last.id[2:]) + 1
        except ValueError:
            pass
    return f"LR{n:03d}"


def _get_current_year_balance(db: Session, employee_id: int, leave_type_id: str) -> Optional[LeaveBalance]:
    year = _today().year
    return (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
        .first()
    )


def _audit(db: Session, req: LeaveRequest, action: str, actor: Optional[Employee],
           from_status: Optional[str], to_status: Optional[str], note: Optional[str] = None) -> None:
    db.add(LeaveAuditLog(
        leave_request_id=req.id,
        action=action,
        actor_id=actor.id if actor else None,
        from_status=from_status,
        to_status=to_status,
        note=note,
    ))


def _notify(db: Session, recipient_id: int, type_: str, title: str,
            body: Optional[str], leave_request_id: Optional[str]) -> None:
    db.add(Notification(
        recipient_id=recipient_id,
        type=type_,
        title=title,
        body=body,
        leave_request_id=leave_request_id,
    ))
    # Best-effort mock email — never crashes the caller.
    try:
        dispatch_for_recipient(db, recipient_id, title, body)
    except Exception:
        pass


def _hr_user_ids(db: Session) -> list[int]:
    """Return employee ids of all active admins (= HR approvers)."""
    return [
        e.id for e in (
            db.query(Employee)
            .join(Role)
            .filter(Role.name == "admin", Employee.is_deleted.is_(False), Employee.employment_status == "active")
            .all()
        )
    ]


def _initial_approver_role(employee: Employee) -> str:
    """Decide the first approver role for a fresh request.

    Phase 5A removes the HR approval stage. Every request that needs a
    human gate routes to 'manager' (a reporting manager, their active
    delegate, or — under SLA escalation — a skip-level manager). A leave
    where no manager can be identified is auto-approved by the system
    actor; see `_should_auto_approve()` below.

    The legacy 'hr' return value is preserved ONLY for one-off backfill
    of in-flight requests that pre-date the refactor; it is never
    produced from new applications.
    """
    return "manager"


def _should_auto_approve(employee: Employee) -> bool:
    """True when the applicant has no available approver (no reporting
    manager and not under any delegate chain). The engine fast-paths
    such requests directly to 'approved' under a synthetic system actor,
    so HR isn't left holding an approver role they no longer own."""
    return not bool(employee and employee.reporting_manager_id)


def _role_name(user: Employee) -> Optional[str]:
    return user.role.name.lower() if user and user.role else None


# ---------- authorization checks ------------------------------------

class LeaveEngineError(Exception):
    """Raised by the engine for bounded errors (mapped to HTTP by the route)."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _can_view(viewer: Employee, req: LeaveRequest) -> bool:
    if _role_name(viewer) == "admin":
        return True
    if viewer.id == req.employee_id:
        return True
    if _role_name(viewer) == "manager":
        # Manager sees requests from their direct reports.
        return req.employee.reporting_manager_id == viewer.id
    return False


def _notify_manager_stage(db: Session, manager_id: Optional[int], type_: str,
                           title: str, body: str, leave_request_id: Optional[str]) -> None:
    """Notify the reporting manager and, if a delegate is currently active,
    also notify the delegate. Skips when manager_id is None."""
    if not manager_id:
        return
    _notify(db, recipient_id=manager_id, type_=type_, title=title, body=body,
            leave_request_id=leave_request_id)
    delegate_id = _active_delegate_id(db, manager_id)
    if delegate_id and delegate_id != manager_id:
        _notify(
            db,
            recipient_id=delegate_id,
            type_=type_,
            title=f"[Delegated] {title}",
            body=body,
            leave_request_id=leave_request_id,
        )


def _active_delegate_id(db: Session, manager_id: int) -> Optional[int]:
    """Return the delegate_id currently authorized for `manager_id`, or None."""
    if not manager_id:
        return None
    today = _today()
    row = (
        db.query(DelegateAssignment)
        .filter(
            DelegateAssignment.manager_id == manager_id,
            DelegateAssignment.is_active.is_(True),
            DelegateAssignment.start_date <= today,
            DelegateAssignment.end_date >= today,
        )
        .order_by(DelegateAssignment.created_at.desc())
        .first()
    )
    return row.delegate_id if row else None


def _can_approve_at_stage(actor: Employee, req: LeaveRequest, stage: str,
                          db: Optional[Session] = None) -> bool:
    """Stage is 'manager' or 'hr'. Admins can approve any stage.

    Phase 2 additions:
      - `approver_override_id` set (skip-level / delegate cache) — that
        specific employee is authorized regardless of role.
      - Active DelegateAssignment for the reporting manager — the delegate
        can approve the manager stage.
    """
    role = _role_name(actor)
    if role == "admin":
        # Admin retains override authority across all stages — Phase 5A
        # preserves this as the documented "HR override when authorized".
        return True
    # Explicit override (set by skip-level escalation, etc.)
    if req.approver_override_id and req.approver_override_id == actor.id:
        return True
    # The only human-gated stage post-Phase-5A is 'manager'. The legacy
    # 'hr' string is kept in the signature only for in-flight legacy rows.
    if stage in ("manager", "hr") and role == "manager":
        manager_id = req.employee.reporting_manager_id
        if manager_id == actor.id:
            return True
        if db is not None:
            delegate_id = _active_delegate_id(db, manager_id)
            if delegate_id and delegate_id == actor.id:
                return True
    return False


# ---------- validation -----------------------------------------------

def _validate_dates(start: date, end: date) -> int:
    if not start or not end:
        raise LeaveEngineError(400, "start_date and end_date are required.")
    if end < start:
        raise LeaveEngineError(400, "end_date cannot be before start_date.")
    today = _today()
    if start < today:
        raise LeaveEngineError(400, "Cannot apply for leave in the past.")
    return (end - start).days + 1


def _check_overlap(db: Session, employee_id: int, start: date, end: date) -> None:
    clashing = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(["pending", "approved", "cancel_pending"]),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
        .first()
    )
    if clashing:
        raise LeaveEngineError(
            409,
            f"Overlapping leave already exists ({clashing.id}: {clashing.start_date} -> {clashing.end_date}).",
        )


def _check_gender_rule(employee: Employee, lt: LeaveType) -> None:
    rule = (lt.applicable_gender or "all").lower()
    if rule == "all":
        return
    if not employee.gender or employee.gender.lower() != rule:
        raise LeaveEngineError(
            400,
            f"Leave type '{lt.name}' is restricted to {rule} employees.",
        )


# ---------- public API -----------------------------------------------

def apply_leave(db: Session, employee: Employee, leave_type_id: str,
                start: date, end: date, reason: Optional[str]) -> LeaveRequest:
    """Submit a leave request.

    Phase 5A flow:
      1. Centralized validation pipeline runs.
      2. Request is inserted with status='pending', next_approver_role='manager'.
      3. `pending_balance` is bumped on the relevant LeaveBalance row so
         concurrent applies can't oversubscribe.
      4. Manager (and any active delegate) is notified.
      5. If the employee has no reporting manager, the request is
         immediately approved by the system actor — HR is no longer an
         approver, so leaving the row in 'pending' would deadlock the
         workflow. HR is still notified informationally.
    """
    from app.services.leave_validation import run_validation
    vctx = run_validation(db, employee, leave_type_id, start, end, reason)
    if vctx.errors:
        raise LeaveEngineError(400, " | ".join(vctx.errors))

    lt = vctx.leave_type
    days = vctx.days

    req = LeaveRequest(
        id=_next_request_id(db),
        employee_id=employee.id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        total_days=days,
        reason=reason,
        status=LeaveStatus.PENDING,
        next_approver_role="manager",
    )
    db.add(req)
    db.flush()

    # Bump pending_balance under row lock so the availability formula
    # (allocated - reserved - pending) is correct for any concurrent applier.
    adjust_pending(db, employee.id, leave_type_id, +days, year=start.year)

    _audit(db, req, "created", employee, None, LeaveStatus.PENDING,
           note=f"{lt.name} for {days} day(s)")

    # Fast-path: no human approver available -> auto-approve via system.
    if _should_auto_approve(employee):
        _finalize_auto_approval(db, req, lt, reason="no reporting manager configured")
        db.commit()
        db.refresh(req)
        return req

    _notify_manager_stage(
        db,
        manager_id=employee.reporting_manager_id,
        type_="leave_pending_your_approval",
        title="Leave request awaiting your approval",
        body=f"{employee.full_name} requested {lt.name} from {start} to {end}.",
        leave_request_id=req.id,
    )

    _notify(
        db,
        recipient_id=employee.id,
        type_="leave_applied",
        title="Leave request submitted",
        body=f"Your {lt.name} request from {start} to {end} is pending approval.",
        leave_request_id=req.id,
    )

    db.commit()
    db.refresh(req)
    return req


def apply_lop_leave(
    db: Session, employee: Employee, start: date, end: date, reason: Optional[str],
    original_leave_type_id: Optional[str] = None,
) -> LeaveRequest:
    """Create a Loss-of-Pay leave request when paid leave balance is exhausted.

    Skips the balance check (LOP has no quota). Runs date, overlap,
    eligibility, blackout, and team-capacity validators. No ledger entry
    or pending_balance adjustment (nothing to deduct). Routes to manager
    → HR two-stage approval chain.
    """
    from app.services.leave_validation import (
        run_validation,
        date_validator,
        working_day_start_validator,
        eligibility_validator,
        overlap_validator,
        blackout_validator,
        team_capacity_validator,
    )

    # Validation: skip balance_validator and document_validator for LOP.
    lop_pipeline = [
        date_validator,
        working_day_start_validator,
        eligibility_validator,
        overlap_validator,
        blackout_validator,
        team_capacity_validator,
    ]
    vctx = run_validation(db, employee, "LT007", start, end, reason, pipeline=lop_pipeline)
    if vctx.errors:
        raise LeaveEngineError(400, " | ".join(vctx.errors))

    days = vctx.days

    req = LeaveRequest(
        id=_next_request_id(db),
        employee_id=employee.id,
        leave_type_id="LT007",
        start_date=start,
        end_date=end,
        total_days=days,
        reason=reason,
        status=LeaveStatus.PENDING,
        next_approver_role="manager",
        is_lop=True,
    )
    db.add(req)
    db.flush()

    # No adjust_pending / ledger entry — LOP has no balance pool.

    note = f"LOP requested for {days} day(s)"
    if original_leave_type_id:
        note += f" (converted from {original_leave_type_id})"
    _audit(db, req, "lop_requested", employee, None, LeaveStatus.PENDING, note=note)

    if _should_auto_approve(employee):
        # No manager — notify HR directly.
        _broadcast_hr(
            db, req,
            type_="lop_pending_hr_approval",
            title="LOP leave awaiting HR approval",
            body=(
                f"{employee.full_name} has no reporting manager. LOP request "
                f"({start} → {end}, {days} day(s)) requires HR approval."
            ),
        )
    else:
        _notify_manager_stage(
            db,
            manager_id=employee.reporting_manager_id,
            type_="lop_pending_manager_approval",
            title="LOP leave request awaiting your approval",
            body=(
                f"{employee.full_name} requested {days} LOP day(s) from {start} to {end}. "
                "Please review and approve or reject."
            ),
            leave_request_id=req.id,
        )

    _notify(
        db,
        recipient_id=employee.id,
        type_="lop_requested",
        title="LOP leave request submitted",
        body=(
            f"Your Loss-of-Pay request from {start} to {end} ({days} day(s)) "
            "has been submitted and is pending manager approval."
        ),
        leave_request_id=req.id,
    )

    db.commit()
    db.refresh(req)
    return req


def _approve_lop(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Two-stage LOP approval: manager stamps → pending HR; HR stamps → approved + payroll sync."""
    stage = req.next_approver_role or "manager"
    role = _role_name(actor)
    now = _utcnow()

    if stage == "manager":
        if not _can_approve_at_stage(actor, req, "manager", db):
            raise LeaveEngineError(403, "You are not authorized to approve this LOP request.")

        try:
            transition(req, "advance_to_hr", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))

        req.manager_approved_by = actor.id
        req.manager_approved_at = now
        req.sla_escalation_level = 0
        req.sla_last_alert_at = None
        req.approver_override_id = None

        _audit(
            db, req, "lop_manager_approved", actor,
            LeaveStatus.PENDING, LeaveStatus.PENDING,
            note=f"LOP manager approval by {actor.full_name}; routing to HR",
        )

        _notify(
            db,
            recipient_id=req.employee_id,
            type_="lop_manager_approved",
            title="LOP request: manager approved",
            body=(
                f"Your LOP request ({req.start_date} → {req.end_date}) was approved by your manager "
                "and is now pending HR review."
            ),
            leave_request_id=req.id,
        )

        _broadcast_hr(
            db, req,
            type_="lop_pending_hr_approval",
            title="LOP leave awaiting HR approval",
            body=(
                f"{req.employee.full_name} LOP request ({req.start_date} → {req.end_date}, "
                f"{req.total_days} day(s)) was manager-approved by {actor.full_name}. "
                "Please review."
            ),
        )

    elif stage == "hr":
        # Only admins may approve at the HR stage for LOP.
        if role != "admin":
            raise LeaveEngineError(403, "Only HR/admin can give final LOP approval.")

        try:
            transition(req, "approve_hr", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))

        req.hr_approved_by = actor.id
        req.hr_approved_at = now
        req.approved_by = actor.id
        req.approved_at = now

        _audit(
            db, req, "lop_hr_approved", actor,
            LeaveStatus.PENDING, LeaveStatus.APPROVED,
            note=f"LOP final HR approval by {actor.full_name}",
        )

        _notify(
            db,
            recipient_id=req.employee_id,
            type_="lop_approved",
            title="LOP leave fully approved",
            body=(
                f"Your LOP leave ({req.start_date} to {req.end_date}, {req.total_days} day(s)) "
                "has been approved by HR. It will be reflected in your payroll."
            ),
            leave_request_id=req.id,
        )

        # Sync to payroll immediately after HR approval.
        from app.services.payroll_bridge import sync_lop_to_payroll
        ok, err = sync_lop_to_payroll(db, req)
        if not ok:
            _audit(
                db, req, "lop_payroll_sync_failed", actor,
                LeaveStatus.APPROVED, LeaveStatus.APPROVED,
                note=err,
            )
            _broadcast_hr(
                db, req,
                type_="payroll_sync_failed",
                title="LOP payroll sync failed",
                body=f"LOP {req.id} approved but payroll sync failed: {err}. Manual update required.",
            )
        else:
            req.payroll_sync_status = "synced"
            _notify(
                db,
                recipient_id=req.employee_id,
                type_="lop_payroll_processed",
                title="LOP leave payroll updated",
                body=(
                    f"Your LOP leave ({req.start_date} to {req.end_date}) has been recorded "
                    "in payroll and will reflect in your next payslip."
                ),
                leave_request_id=req.id,
            )
            _broadcast_hr(
                db, req,
                type_="lop_approved_hr_info",
                title="LOP approved — payroll updated",
                body=(
                    f"{req.employee.full_name} LOP ({req.start_date} → {req.end_date}, "
                    f"{req.total_days} day(s)) fully approved and synced to payroll."
                ),
            )

    else:
        raise LeaveEngineError(400, f"Invalid LOP approval stage: '{stage}'.")

    db.commit()
    db.refresh(req)
    return req


def apply_leave_by_days(
    db: Session,
    employee: Employee,
    leave_type_id: str,
    start: date,
    requested_days: float,
    reason: Optional[str],
    *,
    half_day_start: bool = False,
    half_day_end: bool = False,
) -> LeaveRequest:
    """Working-day apply variant.

    The user supplies a start date + a number of *working days* they want
    off. The engine computes the end_date by walking the calendar and
    skipping weekends + (location-scoped, non-optional) holidays. The
    audit note records the exact day-by-day breakdown so HR can verify
    later.

    Forwarded to the existing `apply_leave()` once the span is computed,
    so all downstream behaviour (validation, balance, notifications,
    auto-approve, ledger entries) is identical.
    """
    from app.services.working_day_engine import compute_leave_span, SpanError
    try:
        span = compute_leave_span(
            db, employee, start, requested_days,
            half_day_start=half_day_start,
            half_day_end=half_day_end,
        )
    except SpanError as exc:
        raise LeaveEngineError(400, str(exc))

    req = apply_leave(db, employee, leave_type_id, span.start_date, span.end_date, reason)
    # Stamp half-day markers + persist the computed span on the audit log.
    req.start_half_day = "first" if half_day_start else None
    req.end_half_day   = "first" if half_day_end   else None
    _audit(
        db, req, "span_computed", employee, None, req.status,
        note=(
            f"Working-day engine: requested={requested_days} -> "
            f"end={span.end_date.isoformat()} counted={span.counted_working_days} "
            f"skipped weekends={len(span.skipped_weekends)} "
            f"skipped holidays={len(span.skipped_holidays)}"
        ),
    )
    db.commit()
    db.refresh(req)
    return req


def _finalize_auto_approval(db: Session, req: LeaveRequest, lt: LeaveType,
                             reason: str) -> None:
    """System auto-approval for requests with no human approver.

    Releases pending_balance, reserves via ledger, audits, and broadcasts
    an informational notification to HR (admins) per the new policy."""
    now = _utcnow()
    # State machine: pending -> approved.
    transition(req, "approve_manager")
    req.manager_approved_by = None
    req.manager_approved_at = now
    req.approved_by = None
    req.approved_at = now

    adjust_pending(db, req.employee_id, req.leave_type_id, -req.total_days,
                   year=req.start_date.year)
    post_ledger_entry(
        db,
        employee_id=req.employee_id,
        leave_type_id=req.leave_type_id,
        transaction_type=LedgerTxn.RESERVE,
        days=req.total_days,
        reference_type="leave_request",
        reference_id=req.id,
        actor=None,
        note=f"System auto-approval: {reason}",
        year=req.start_date.year,
    )

    _audit(db, req, "auto_approved_system", None, LeaveStatus.PENDING, LeaveStatus.APPROVED,
           note=f"Auto-approved by system ({reason})")

    _notify(
        db,
        recipient_id=req.employee_id,
        type_="leave_approved",
        title="Leave request approved",
        body=f"Your {lt.name} ({req.start_date} -> {req.end_date}) was auto-approved.",
        leave_request_id=req.id,
    )
    # HR notification-only.
    _broadcast_hr(
        db, req,
        type_="leave_approved_hr_info",
        title="Leave approved (system auto)",
        body=f"{req.employee.full_name}: auto-approved {lt.name} ({req.start_date} -> {req.end_date}).",
    )


def _broadcast_hr(db: Session, req: LeaveRequest, *,
                  type_: str, title: str, body: str) -> None:
    """Notify every active HR/admin user. HR is no longer in the approval
    chain so these are strictly informational."""
    for hr_id in _hr_user_ids(db):
        if hr_id == req.employee_id:
            continue
        _notify(
            db, recipient_id=hr_id, type_=type_, title=title, body=body,
            leave_request_id=req.id,
        )


def approve_leave(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Single-stage manager approval — now delegates to Hybrid v2.

    Phase 5A introduced the manager-only chain. Phase v2 (this refactor)
    shifts when `used` is incremented: at approval time rather than at
    scheduler-consumption time. The v2 engine performs:

      - state transition pending → approved
      - pending_balance release
      - atomic LEAVE_DEDUCTION ledger entry (reserved+ AND used+)
      - employee notification + HR informational broadcast

    The legacy authorization check (`_can_approve_at_stage`) is preserved
    so delegated/skip-level approvers still work the same way. We keep
    the wrapper so every router that currently calls `approve_leave()`
    automatically picks up v2 semantics without code changes.
    """
    if req.status != LeaveStatus.PENDING:
        raise LeaveEngineError(400, f"Cannot approve a request in status '{req.status}'.")

    # LOP requests use a two-stage manager → HR approval chain.
    if getattr(req, "is_lop", False):
        return _approve_lop(db, actor, req)

    # The only legal stage now is 'manager'; legacy 'hr' rows are picked
    # up by the startup backfill (see leave_ledger_backfill.py).
    stage = req.next_approver_role or "manager"
    if not _can_approve_at_stage(actor, req, stage, db):
        raise LeaveEngineError(403, "You are not authorized to approve this leave.")

    # Delegate to v2. approve_hybrid() documents that commit() is the
    # caller's responsibility — without these two lines every manager
    # approval is silently rolled back at request end.
    from app.services.leave_workflow_v2 import approve_hybrid, WorkflowError
    try:
        result = approve_hybrid(db, actor, req)
    except WorkflowError as exc:
        raise LeaveEngineError(exc.status_code, exc.detail)
    db.commit()
    db.refresh(result)
    return result
    # NOTE: the v1 body below is intentionally kept disabled so a quick
    # `git revert` of THIS edit returns the system to the prior behavior
    # without touching any callers.

    now = _utcnow()
    try:
        transition(req, "approve_manager", actor)
    except InvalidTransition as exc:
        raise LeaveEngineError(400, str(exc))

    # Manager stamps + legacy single-stage stamp (kept for backwards-compat
    # serializers that surface `approved_by` / `approved_at`).
    req.manager_approved_by = actor.id
    req.manager_approved_at = now
    req.approved_by = actor.id
    req.approved_at = now
    # SLA state belongs to the (now-terminated) pending stage.
    req.sla_escalation_level = 0
    req.sla_last_alert_at = None
    req.approver_override_id = None

    # Balance: release pending, then reserve through the ledger. The ledger
    # writes under row-lock and will refuse if available < total_days.
    adjust_pending(db, req.employee_id, req.leave_type_id, -req.total_days,
                   year=req.start_date.year)
    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.RESERVE,
            days=req.total_days,
            reference_type="leave_request",
            reference_id=req.id,
            actor=actor,
            note=f"Reserved on manager approval by {actor.full_name}",
            year=req.start_date.year,
        )
    except LedgerError as exc:
        # Roll back the pending decrement so the row is consistent.
        adjust_pending(db, req.employee_id, req.leave_type_id, +req.total_days,
                       year=req.start_date.year)
        raise LeaveEngineError(409, f"Cannot approve: {exc}")

    _audit(db, req, "approved_manager", actor, LeaveStatus.PENDING, LeaveStatus.APPROVED,
           note=f"Approved by manager {actor.full_name}")

    _notify(
        db,
        recipient_id=req.employee_id,
        type_="leave_approved",
        title="Leave request approved",
        body=f"Your leave from {req.start_date} to {req.end_date} is approved.",
        leave_request_id=req.id,
    )
    # HR notification-only — HR is no longer in the approval chain.
    _broadcast_hr(
        db, req,
        type_="leave_approved_hr_info",
        title="Leave approved (manager)",
        body=(
            f"{req.employee.full_name}: {req.leave_type.name if req.leave_type else 'leave'} "
            f"({req.start_date} -> {req.end_date}) approved by {actor.full_name}."
        ),
    )

    db.commit()
    db.refresh(req)
    return req


# ---------- Draft workflow ------------------------------------------

def _ensure_draft_owner(actor: Employee, req: LeaveRequest) -> None:
    if actor.id != req.employee_id and _role_name(actor) != "admin":
        raise LeaveEngineError(403, "Only the owner can modify this draft.")
    if req.status != "draft":
        raise LeaveEngineError(400, f"Request {req.id} is not a draft (status='{req.status}').")


def create_draft(db: Session, employee: Employee, leave_type_id: str,
                 start: date, end: date, reason: Optional[str]) -> LeaveRequest:
    """Persist a draft. No validation runs; no balance/notification side effects.

    The only sanity check is that the referenced leave type exists — drafts
    must still point at a real type so the UI can render them in the list.
    """
    if leave_type_id and not db.get(LeaveType, leave_type_id):
        raise LeaveEngineError(400, f"Unknown leave type '{leave_type_id}'.")

    # Drafts may have placeholder dates; if both provided, compute days.
    days = 0
    if start and end and end >= start:
        days = (end - start).days + 1

    req = LeaveRequest(
        id=_next_request_id(db),
        employee_id=employee.id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        total_days=days,
        reason=reason,
        status="draft",
        next_approver_role=None,
    )
    db.add(req)
    db.flush()
    _audit(db, req, "draft_created", employee, None, "draft",
           note="Draft saved (no approval triggered)")
    db.commit()
    db.refresh(req)
    return req


def update_draft(db: Session, actor: Employee, req: LeaveRequest, *,
                 leave_type_id: Optional[str] = None,
                 start: Optional[date] = None,
                 end: Optional[date] = None,
                 reason: Optional[str] = None) -> LeaveRequest:
    _ensure_draft_owner(actor, req)

    if leave_type_id is not None:
        if not db.get(LeaveType, leave_type_id):
            raise LeaveEngineError(400, f"Unknown leave type '{leave_type_id}'.")
        req.leave_type_id = leave_type_id
    if start is not None:
        req.start_date = start
    if end is not None:
        req.end_date = end
    if reason is not None:
        req.reason = reason

    if req.start_date and req.end_date and req.end_date >= req.start_date:
        req.total_days = (req.end_date - req.start_date).days + 1
    else:
        req.total_days = 0

    _audit(db, req, "draft_updated", actor, "draft", "draft", note=None)
    db.commit()
    db.refresh(req)
    return req


def submit_draft(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Run validation pipeline and transition draft -> pending.

    On success, same side effects as apply_leave (audit + notifications).
    On validation failure, the draft stays in 'draft' and the caller sees
    a 400 with all collected errors joined.
    """
    _ensure_draft_owner(actor, req)

    from app.services.leave_validation import run_validation
    vctx = run_validation(
        db, req.employee, req.leave_type_id, req.start_date, req.end_date, req.reason,
        leave_request_id=req.id,
    )
    if vctx.errors:
        raise LeaveEngineError(400, " | ".join(vctx.errors))

    lt = vctx.leave_type
    req.total_days = vctx.days

    # State machine: draft -> pending.
    try:
        transition(req, "submit", actor)
    except InvalidTransition as exc:
        raise LeaveEngineError(400, str(exc))
    req.next_approver_role = "manager"

    adjust_pending(db, req.employee_id, req.leave_type_id, +req.total_days,
                   year=req.start_date.year)

    _audit(db, req, "submitted", actor, LeaveStatus.DRAFT, LeaveStatus.PENDING,
           note=f"Draft submitted ({lt.name}, {vctx.days} day(s))")

    # Auto-approve if there's no manager — see apply_leave for the rationale.
    if _should_auto_approve(req.employee):
        _finalize_auto_approval(db, req, lt, reason="no reporting manager configured")
        db.commit()
        db.refresh(req)
        return req

    _notify_manager_stage(
        db,
        manager_id=req.employee.reporting_manager_id,
        type_="leave_pending_your_approval",
        title="Leave request awaiting your approval",
        body=f"{req.employee.full_name} requested {lt.name} from {req.start_date} to {req.end_date}.",
        leave_request_id=req.id,
    )

    _notify(
        db,
        recipient_id=req.employee_id,
        type_="leave_applied",
        title="Leave request submitted",
        body=f"Your {lt.name} request from {req.start_date} to {req.end_date} is pending approval.",
        leave_request_id=req.id,
    )

    db.commit()
    db.refresh(req)
    return req


def discard_draft(db: Session, actor: Employee, req: LeaveRequest) -> None:
    _ensure_draft_owner(actor, req)
    # Audit row references this request_id by FK with no cascade; clear those
    # first so the delete doesn't violate the constraint.
    db.query(LeaveAuditLog).filter(LeaveAuditLog.leave_request_id == req.id).delete(
        synchronize_session=False
    )
    db.delete(req)
    db.commit()


def reject_leave(db: Session, actor: Employee, req: LeaveRequest, reason: Optional[str]) -> LeaveRequest:
    """Manager rejects a pending request, or rejects a pending cancellation.

    Phase 5A:
      - pending -> rejected      : release pending_balance
      - cancel_pending -> approved (cancellation refused) : no balance move
    """
    if req.status not in {LeaveStatus.PENDING, LeaveStatus.CANCEL_PENDING}:
        raise LeaveEngineError(400, f"Cannot reject a request in status '{req.status}'.")

    stage = req.next_approver_role or "manager"
    if not _can_approve_at_stage(actor, req, stage, db):
        raise LeaveEngineError(403, "You are not authorized to reject this request.")

    now = _utcnow()
    prev = req.status

    if req.status == LeaveStatus.CANCEL_PENDING:
        try:
            transition(req, "reject_cancel", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        _audit(db, req, "cancel_rejected", actor, prev, LeaveStatus.APPROVED, note=reason)
        _notify(
            db,
            recipient_id=req.employee_id,
            type_="leave_cancel_rejected",
            title="Cancellation request rejected",
            body=reason or "Your cancellation was not approved; leave remains active.",
            leave_request_id=req.id,
        )
    else:
        try:
            transition(req, "reject", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        req.rejected_by = actor.id
        req.rejected_at = now
        req.rejection_reason = reason
        # Release pending_balance only for regular leaves; LOP has no balance row.
        if not getattr(req, "is_lop", False):
            adjust_pending(db, req.employee_id, req.leave_type_id, -req.total_days,
                           year=req.start_date.year)
        _audit(db, req, "rejected", actor, prev, LeaveStatus.REJECTED, note=reason)
        _notify(
            db,
            recipient_id=req.employee_id,
            type_="leave_rejected",
            title="Leave request rejected",
            body=reason or f"Your leave from {req.start_date} to {req.end_date} was rejected.",
            leave_request_id=req.id,
        )
        # HR informational broadcast — visibility for monitoring dashboards.
        _broadcast_hr(
            db, req, type_="leave_rejected_hr_info",
            title="Leave rejected (manager)",
            body=f"{req.employee.full_name}: leave rejected by {actor.full_name}.",
        )

    db.commit()
    db.refresh(req)
    return req


def cancel_leave(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Employee (or admin) cancels their own request.

    pending   -> cancelled              (release pending_balance, no approval chain)
    approved  -> cancel_pending         (manager approval required; reserved stays
                                         locked until approve_cancellation runs)
    """
    is_owner = actor.id == req.employee_id
    is_admin = _role_name(actor) == "admin"
    if not (is_owner or is_admin):
        raise LeaveEngineError(403, "Only the requester or an admin can cancel a leave.")

    if req.status == LeaveStatus.PENDING:
        try:
            transition(req, "cancel", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        if not getattr(req, "is_lop", False):
            adjust_pending(db, req.employee_id, req.leave_type_id, -req.total_days,
                           year=req.start_date.year)
        _audit(db, req, "cancelled", actor, LeaveStatus.PENDING, LeaveStatus.CANCELLED,
               note="Direct cancel (was pending)")
        _notify(
            db,
            recipient_id=req.employee_id,
            type_="leave_cancelled",
            title="Leave request cancelled",
            body=f"Your {req.leave_type.name} request was cancelled.",
            leave_request_id=req.id,
        )
    elif req.status == LeaveStatus.APPROVED:
        try:
            transition(req, "cancel", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        req.cancel_requested_at = _utcnow()
        req.next_approver_role = "manager"
        _audit(db, req, "cancel_requested", actor, LeaveStatus.APPROVED, LeaveStatus.CANCEL_PENDING)
        _notify_manager_stage(
            db,
            manager_id=req.employee.reporting_manager_id,
            type_="leave_cancel_pending_your_approval",
            title="Cancellation request awaiting your approval",
            body=f"{req.employee.full_name} wants to cancel their approved leave ({req.start_date} -> {req.end_date}).",
            leave_request_id=req.id,
        )
    else:
        raise LeaveEngineError(400, f"Cannot cancel a request in status '{req.status}'.")

    db.commit()
    db.refresh(req)
    return req


def approve_cancellation(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Single-stage manager approval of a cancellation request.

    Phase 5A: manager approval is final. Reserved balance is released
    through the ledger (RELEASE entry) and HR is notified informationally.
    """
    if req.status != LeaveStatus.CANCEL_PENDING:
        raise LeaveEngineError(400, f"No pending cancellation on request '{req.id}'.")

    stage = req.next_approver_role or "manager"
    if not _can_approve_at_stage(actor, req, stage, db):
        raise LeaveEngineError(403, "You are not authorized to approve this cancellation.")

    now = _utcnow()
    try:
        transition(req, "approve_cancel", actor)
    except InvalidTransition as exc:
        raise LeaveEngineError(400, str(exc))

    req.cancel_manager_approved_by = actor.id
    req.cancel_manager_approved_at = now
    # Also stamp the legacy 'cancel_hr_approved_*' fields so existing
    # serializers don't show a half-completed cancellation.
    req.cancel_hr_approved_by = actor.id
    req.cancel_hr_approved_at = now

    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.RELEASE,
            days=req.total_days,
            reference_type="leave_request",
            reference_id=req.id,
            actor=actor,
            note=f"Released on cancellation approval by {actor.full_name}",
            year=req.start_date.year,
        )
    except LedgerError as exc:
        raise LeaveEngineError(409, f"Cannot finalize cancellation: {exc}")

    _audit(db, req, "cancel_approved_manager", actor, LeaveStatus.CANCEL_PENDING,
           LeaveStatus.CANCELLED, note="Cancellation approved by manager")
    _notify(
        db,
        recipient_id=req.employee_id,
        type_="leave_cancelled",
        title="Leave cancellation approved",
        body=f"Your {req.leave_type.name} leave has been cancelled and balance restored.",
        leave_request_id=req.id,
    )
    _broadcast_hr(
        db, req, type_="leave_cancelled_hr_info",
        title="Leave cancellation approved (manager)",
        body=f"{req.employee.full_name}: cancellation approved by {actor.full_name}; balance released.",
    )

    db.commit()
    db.refresh(req)
    return req


# ===================================================================
# Phase 2: negative flow + comp-off
# ===================================================================

from datetime import timedelta  # noqa: E402  (intentionally local; small append)


def _next_comp_off_id_unused(db):  # placeholder for symmetry with _next_request_id
    return None


def _attendance_lookup(db: Session, employee_id: int, days: list) -> dict:
    """Return {date: status} for the given employee + dates."""
    if not days:
        return {}
    rows = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.date.in_(days))
        .all()
    )
    return {r.date: (r.status or "").lower() for r in rows}


def _date_range(start: date, end: date) -> list:
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def process_pending_consumption(db: Session) -> dict:
    """Negative-flow scheduler.

    Walks through every approved leave whose end_date is < today and decides:
      - All days marked absent / leave / wfh => CONSUMED (deduct balance,
        release reserved, notify employee, mock-notify payroll).
      - Any day shows present => REVERSE: restore reserved, mark cancelled
        with note 'reversed_worked_on_leave', notify employee + payroll.

    Returns a summary dict for the caller / scheduler logs.
    """
    today = _today()
    consumed = 0
    reversed_ = 0
    skipped = 0
    examined = 0

    pending = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "approved", LeaveRequest.end_date < today)
        .all()
    )

    for req in pending:
        examined += 1
        days = _date_range(req.start_date, req.end_date)
        attendance_map = _attendance_lookup(db, req.employee_id, days)

        present_days = [d for d in days if attendance_map.get(d) == "present"]
        bal = _get_current_year_balance(db, req.employee_id, req.leave_type_id)
        if not bal:
            skipped += 1
            continue

        if present_days:
            # Diagram panel 2: don't auto-reverse. Raise a "Worked on Leave"
            # validation request and route it through manager -> HR approval.
            # If a request already exists for this leave, skip.
            existing = (
                db.query(WorkedOnLeaveRequest)
                .filter(WorkedOnLeaveRequest.leave_request_id == req.id, WorkedOnLeaveRequest.status == "pending")
                .first()
            )
            if existing:
                continue
            wol = WorkedOnLeaveRequest(
                leave_request_id=req.id,
                employee_id=req.employee_id,
                present_dates=",".join(d.isoformat() for d in present_days),
                status="pending",
                next_approver_role=_initial_approver_role(req.employee),
            )
            db.add(wol)
            db.flush()
            _audit(db, req, "worked_on_leave_raised", None, req.status, req.status,
                   note=f"Validation needed for {len(present_days)} present day(s)")
            # Notify the approver
            if wol.next_approver_role == "manager" and req.employee.reporting_manager_id:
                _notify(
                    db,
                    recipient_id=req.employee.reporting_manager_id,
                    type_="worked_on_leave_pending_your_approval",
                    title="Worked-on-leave validation awaiting your approval",
                    body=f"{req.employee.full_name} was present on {len(present_days)} day(s) of leave {req.id}. Approve to reverse the leave; reject to consume.",
                    leave_request_id=req.id,
                )
            else:
                for hr_id in _hr_user_ids(db):
                    if hr_id == req.employee_id:
                        continue
                    _notify(
                        db,
                        recipient_id=hr_id,
                        type_="worked_on_leave_pending_your_approval",
                        title="Worked-on-leave validation awaiting HR approval",
                        body=f"{req.employee.full_name} was present on {len(present_days)} day(s) of leave {req.id}.",
                        leave_request_id=req.id,
                    )
            _notify(
                db,
                recipient_id=req.employee_id,
                type_="worked_on_leave_raised",
                title="Worked-on-leave validation raised",
                body=f"Attendance shows you worked on {len(present_days)} day(s) of your leave. Awaiting validation.",
                leave_request_id=req.id,
            )
            reversed_ += 1  # counted as "raised"; final outcome decided on approval
        else:
            # ── Hybrid v2 completion ─────────────────────────────────────
            # `used` was already incremented at approval time, so the
            # scheduler only needs to clear the reservation and mark the
            # request COMPLETED. One ledger entry (LEAVE_COMPLETION),
            # no balance arithmetic.
            from app.services.leave_workflow_v2 import (
                complete_in_scheduler, WorkflowError,
            )
            try:
                complete_in_scheduler(db, req, consumed_days=req.total_days)
            except WorkflowError as e:
                _audit(db, req, "completion_error_v2", None, "approved", "approved",
                       note=e.detail)
                skipped += 1
                continue
            # Payroll integration: write into payroll_attendance_summary
            # immediately. On failure the row is left in 'failed' state and
            # the retry sweep will pick it up later.
            from app.services.payroll_bridge import queue_for_payroll_sync, sync_leave_to_payroll
            queue_for_payroll_sync(req)
            ok, err = sync_leave_to_payroll(db, req)
            if not ok:
                _audit(db, req, "payroll_sync_failed", None, "consumed", "consumed",
                       note=err)
            consumed += 1

    db.commit()
    # Heartbeat — let the startup self-heal hook know consumption ran.
    try:
        from app.models import SchedulerHealth
        row = db.get(SchedulerHealth, "leave.process_pending_consumption")
        if not row:
            row = SchedulerHealth(task_name="leave.process_pending_consumption")
            db.add(row)
        row.last_run_at = _utcnow()
        row.last_status = "ok"
        row.last_summary = (
            f"examined={examined} consumed={consumed} reversed={reversed_} "
            f"skipped={skipped}"
        )
        row.run_count = int(row.run_count or 0) + 1
        db.commit()
    except Exception:
        logger.exception("Could not update scheduler_health heartbeat (ignoring)")

    return {"examined": examined, "consumed": consumed, "reversed": reversed_, "skipped_no_balance": skipped}


# -------- Comp-off ------------------------------------------------

DEFAULT_COMP_OFF_EXPIRY_DAYS = 90


def grant_comp_off(db: Session, actor: Employee, employee_id: int, worked_on: date,
                   days: int, reason: Optional[str], proof_url: Optional[str]) -> CompOffCredit:
    """Open a comp-off credit request. Goes through manager -> HR approval chain."""
    target = db.get(Employee, employee_id)
    if not target or target.is_deleted:
        raise LeaveEngineError(404, "Employee not found")

    # Authorization: the employee themselves, their manager, or admin can initiate.
    role = _role_name(actor)
    if not (
        role == "admin"
        or actor.id == target.id
        or (role == "manager" and target.reporting_manager_id == actor.id)
    ):
        raise LeaveEngineError(403, "Not allowed to grant comp-off for this employee.")

    if days <= 0 or days > 5:
        raise LeaveEngineError(400, "Invalid number of comp-off days (1..5).")

    if worked_on > _today():
        raise LeaveEngineError(400, "worked_on must be in the past.")

    # Skip manager step if the granter IS the manager (or admin).
    if role == "manager" or role == "admin":
        # A manager/admin initiating their own grant for one of their reports
        # auto-clears the manager step, leaving only HR to approve.
        next_role = "hr"
        manager_by, manager_at = actor.id, _utcnow()
    else:
        next_role = "manager" if target.reporting_manager_id else "hr"
        manager_by, manager_at = None, None

    credit = CompOffCredit(
        employee_id=target.id,
        worked_on=worked_on,
        days=days,
        reason=reason,
        proof_url=proof_url,
        status="pending",
        next_approver_role=next_role,
        manager_approved_by=manager_by,
        manager_approved_at=manager_at,
        expires_on=worked_on + timedelta(days=DEFAULT_COMP_OFF_EXPIRY_DAYS),
    )
    db.add(credit)
    db.flush()

    # Notify the next approver
    if next_role == "manager" and target.reporting_manager_id:
        _notify(
            db,
            recipient_id=target.reporting_manager_id,
            type_="comp_off_pending_your_approval",
            title="Comp-off request awaiting your approval",
            body=f"{target.full_name} requested {days} comp-off day(s) for {worked_on}.",
            leave_request_id=None,
        )
    else:
        for hr_id in _hr_user_ids(db):
            if hr_id == target.id:
                continue
            _notify(
                db,
                recipient_id=hr_id,
                type_="comp_off_pending_your_approval",
                title="Comp-off request awaiting HR approval",
                body=f"{target.full_name} requested {days} comp-off day(s) for {worked_on}.",
                leave_request_id=None,
            )

    db.commit()
    db.refresh(credit)
    return credit


def approve_comp_off(db: Session, actor: Employee, credit: CompOffCredit) -> CompOffCredit:
    if credit.status != "pending":
        raise LeaveEngineError(400, f"Cannot approve a comp-off credit in status '{credit.status}'.")

    stage = credit.next_approver_role
    role = _role_name(actor)
    if stage == "manager":
        if role != "admin" and not (role == "manager" and credit.employee.reporting_manager_id == actor.id):
            raise LeaveEngineError(403, "Not authorized at manager stage.")
        credit.manager_approved_by = actor.id
        credit.manager_approved_at = _utcnow()
        credit.next_approver_role = "hr"
        for hr_id in _hr_user_ids(db):
            if hr_id == credit.employee_id:
                continue
            _notify(
                db,
                recipient_id=hr_id,
                type_="comp_off_pending_your_approval",
                title="Comp-off awaiting HR approval",
                body=f"Manager approved {credit.employee.full_name}'s comp-off; awaiting HR.",
                leave_request_id=None,
            )
    elif stage == "hr":
        if role != "admin":
            raise LeaveEngineError(403, "Only admin/HR can grant final approval.")
        credit.hr_approved_by = actor.id
        credit.hr_approved_at = _utcnow()
        credit.status = "approved"
        credit.next_approver_role = None

        # Top up the Compensatory_leave balance for the employee in the current year.
        comp_lt = (
            db.query(LeaveType)
            .filter(LeaveType.name.ilike("%comp%"))
            .first()
        )
        if comp_lt:
            # Phase 5D fix: route the credit through the ledger so
            # allocated_balance / opening_balance / current_balance and the
            # audit trail all stay consistent. The previous direct mutation
            # of opening_balance + current_balance left allocated_balance
            # untouched, breaking the canonical available formula
            # (allocated - reserved - pending) and silently making the
            # comp-off credit unusable in the leave-apply flow.
            try:
                post_ledger_entry(
                    db,
                    employee_id=credit.employee_id,
                    leave_type_id=comp_lt.id,
                    transaction_type=LedgerTxn.ACCRUAL,
                    days=int(credit.days or 0),
                    reference_type="comp_off_credit",
                    reference_id=str(credit.id),
                    actor=actor,
                    note=(
                        f"Comp-off credit #{credit.id}: +{credit.days} day(s) "
                        f"for {credit.worked_on}"
                    ),
                    year=_today().year,
                )
            except LedgerError as exc:
                # Should not happen for ACCRUAL (no underflow possible), but
                # surface clearly if it does so the failure isn't silent.
                raise LeaveEngineError(
                    500, f"Comp-off ledger write failed: {exc}",
                )

        _notify(
            db,
            recipient_id=credit.employee_id,
            type_="comp_off_approved",
            title="Comp-off approved",
            body=f"{credit.days} day(s) of comp-off credited (expires {credit.expires_on}).",
            leave_request_id=None,
        )
    else:
        raise LeaveEngineError(400, "Comp-off has no pending approval stage.")

    db.commit()
    db.refresh(credit)
    return credit


def reject_comp_off(db: Session, actor: Employee, credit: CompOffCredit, reason: Optional[str]) -> CompOffCredit:
    if credit.status != "pending":
        raise LeaveEngineError(400, f"Cannot reject in status '{credit.status}'.")
    role = _role_name(actor)
    stage = credit.next_approver_role or "hr"
    if stage == "manager":
        if role != "admin" and not (role == "manager" and credit.employee.reporting_manager_id == actor.id):
            raise LeaveEngineError(403, "Not authorized.")
    elif role != "admin":
        raise LeaveEngineError(403, "Not authorized.")

    credit.status = "rejected"
    credit.rejection_reason = reason
    credit.next_approver_role = None
    _notify(
        db,
        recipient_id=credit.employee_id,
        type_="comp_off_rejected",
        title="Comp-off rejected",
        body=reason or "Your comp-off request was not approved.",
        leave_request_id=None,
    )
    db.commit()
    db.refresh(credit)
    return credit


# ===================================================================
# Phase 3: Worked-on-leave validation + comp-off expiry
# ===================================================================

def approve_worked_on_leave(db: Session, actor: Employee, wol: WorkedOnLeaveRequest) -> WorkedOnLeaveRequest:
    """Manager-only approval (Phase 5A).

    Approving = the employee genuinely worked on the leave dates ->
    REVERSE the leave: ledger RELEASE of the reserved days, leave row
    moves to 'cancelled'. HR is notified informationally.
    """
    if wol.status != "pending":
        raise LeaveEngineError(400, f"Cannot approve in status '{wol.status}'.")

    role = _role_name(actor)
    if role != "admin" and not (
        role == "manager"
        and wol.employee
        and wol.employee.reporting_manager_id == actor.id
    ):
        raise LeaveEngineError(403, "Not authorized to approve this validation.")

    now = _utcnow()
    wol.manager_approved_by = actor.id
    wol.manager_approved_at = now
    # Keep legacy HR-stamp fields populated for back-compat readers.
    wol.hr_approved_by = actor.id
    wol.hr_approved_at = now
    wol.status = "approved"
    wol.next_approver_role = None

    req = db.get(LeaveRequest, wol.leave_request_id)
    if req:
        try:
            transition(req, "reverse", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        try:
            post_ledger_entry(
                db,
                employee_id=req.employee_id,
                leave_type_id=req.leave_type_id,
                transaction_type=LedgerTxn.RELEASE,
                days=req.total_days,
                reference_type="leave_request",
                reference_id=req.id,
                actor=actor,
                note=f"Reversed via WoL #{wol.id}",
                year=req.start_date.year,
            )
        except LedgerError as exc:
            raise LeaveEngineError(409, f"Cannot reverse: {exc}")

        _audit(db, req, "reversed_worked_on_leave", actor, LeaveStatus.APPROVED,
               LeaveStatus.CANCELLED, note=f"Reversed via WoL request #{wol.id}")
        _notify(
            db,
            recipient_id=req.employee_id,
            type_="leave_reversed",
            title="Leave reversed (worked-on-leave validated)",
            body=f"Your {req.leave_type.name} ({req.start_date} to {req.end_date}) is reversed and balance restored.",
            leave_request_id=req.id,
        )
        _broadcast_hr(
            db, req, type_="payroll_adjustment_needed",
            title="Payroll: leave reversed",
            body=f"{req.employee.full_name}'s leave {req.id} was reversed via worked-on-leave validation.",
        )

    db.commit()
    db.refresh(wol)
    return wol


def reject_worked_on_leave(db: Session, actor: Employee, wol: WorkedOnLeaveRequest, reason: Optional[str]) -> WorkedOnLeaveRequest:
    """Manager-only rejection (Phase 5A).

    Rejecting = approver decided the employee was NOT genuinely working ->
    consume the original leave normally (ledger RELEASE + DEBIT).
    """
    if wol.status != "pending":
        raise LeaveEngineError(400, f"Cannot reject in status '{wol.status}'.")

    role = _role_name(actor)
    if role != "admin" and not (
        role == "manager"
        and wol.employee
        and wol.employee.reporting_manager_id == actor.id
    ):
        raise LeaveEngineError(403, "Not authorized to reject this validation.")

    wol.status = "rejected"
    wol.rejection_reason = reason
    wol.next_approver_role = None

    req = db.get(LeaveRequest, wol.leave_request_id)
    if req and req.status == LeaveStatus.APPROVED:
        try:
            transition(req, "consume", actor)
        except InvalidTransition as exc:
            raise LeaveEngineError(400, str(exc))
        try:
            post_ledger_entry(
                db,
                employee_id=req.employee_id,
                leave_type_id=req.leave_type_id,
                transaction_type=LedgerTxn.RELEASE,
                days=req.total_days,
                reference_type="leave_request",
                reference_id=req.id,
                actor=actor,
                note=f"Pre-consumption release via WoL rejection #{wol.id}",
                year=req.start_date.year,
            )
            post_ledger_entry(
                db,
                employee_id=req.employee_id,
                leave_type_id=req.leave_type_id,
                transaction_type=LedgerTxn.DEBIT,
                days=req.total_days,
                reference_type="leave_request",
                reference_id=req.id,
                actor=actor,
                note=f"Consumed after WoL rejection #{wol.id}",
                year=req.start_date.year,
            )
        except LedgerError as exc:
            raise LeaveEngineError(409, f"Cannot consume: {exc}")
        _audit(db, req, "consumed", actor, LeaveStatus.APPROVED, LeaveStatus.CONSUMED,
               note=f"Consumed after WoL rejection #{wol.id}")
        from app.services.payroll_bridge import queue_for_payroll_sync, sync_leave_to_payroll
        queue_for_payroll_sync(req)
        ok, err = sync_leave_to_payroll(db, req)
        if not ok:
            _audit(db, req, "payroll_sync_failed", actor, "consumed", "consumed", note=err)
        _notify(
            db,
            recipient_id=req.employee_id,
            type_="leave_consumed",
            title="Leave consumed",
            body=f"Worked-on-leave validation was rejected; {req.leave_type.name} ({req.start_date} to {req.end_date}) is now consumed.",
            leave_request_id=req.id,
        )

    db.commit()
    db.refresh(wol)
    return wol


def expire_comp_off_credits(db: Session) -> dict:
    """Daily task: expire approved comp-off credits whose expires_on has passed.

    For each expiring credit, the employee's Compensatory_leave LeaveBalance
    is decremented (opening + current) by the credit's days. If those balances
    are already at zero (the days were used), no decrement happens.
    """
    today = _today()
    expired = 0
    deducted_days = 0

    rows = (
        db.query(CompOffCredit)
        .filter(CompOffCredit.status == "approved", CompOffCredit.expires_on < today)
        .all()
    )
    if not rows:
        return {"expired": 0, "deducted_days": 0}

    comp_lt = (
        db.query(LeaveType)
        .filter(LeaveType.name.ilike("%comp%"))
        .first()
    )

    for c in rows:
        c.status = "expired"
        if comp_lt:
            year = c.expires_on.year
            expire_days = c.days or 1
            # Phase 5C: route the decrement through the ledger so expiry is
            # auditable. ENCASHMENT is the bucket-aligned txn for shrinking
            # `allocated`; the note distinguishes it from real cash-outs.
            try:
                post_ledger_entry(
                    db,
                    employee_id=c.employee_id,
                    leave_type_id=comp_lt.id,
                    transaction_type=LedgerTxn.ENCASHMENT,
                    days=expire_days,
                    reference_type="comp_off_credit",
                    reference_id=str(c.id),
                    actor=None,
                    note=f"Comp-off credit #{c.id} expired ({expire_days} day(s))",
                    year=year,
                )
                deducted_days += expire_days
            except LedgerError as exc:
                # Likely zero allocated remaining (credit already used) — that's
                # the expected silent no-op the original implementation aimed for.
                logger.debug("Comp-off expiry skipped for credit %s: %s", c.id, exc)
        expired += 1
        # Notify employee
        _notify(
            db,
            recipient_id=c.employee_id,
            type_="comp_off_expired",
            title="Comp-off credit expired",
            body=f"Your comp-off credit ({c.days or 1} day) earned on {c.worked_on} expired on {c.expires_on}.",
            leave_request_id=None,
        )

    db.commit()
    return {"expired": expired, "deducted_days": deducted_days}
