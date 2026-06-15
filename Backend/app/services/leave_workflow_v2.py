"""Hybrid Immediate Deduction + Reservation Tracking — v2 workflow engine.

Architectural shift from v1:
  v1: approval reserved days, scheduler consumed them.
      → Employee's "available" balance dropped only after the leave dates passed.
  v2: approval IMMEDIATELY deducts days from `used` AND records the reservation.
      → Employee's available balance drops the moment the manager approves.
      → Scheduler is now a lightweight "mark complete + clear reservation" sweep.

Public entry points
-------------------
    approve_hybrid(db, actor, req)
        Manager approval → atomic LEAVE_DEDUCTION ledger entry.
        Replaces the old `approve_leave()` reservation-only path.

    complete_in_scheduler(db, req)
        Called once a leave's dates have fully passed and attendance shows
        the employee was actually absent. Writes a LEAVE_COMPLETION ledger
        entry and flips status to COMPLETED. No balance change beyond
        clearing the reservation bookkeeping.

    cancel_full_future(db, actor, req)
        Manager-approved cancellation of a future-dated approved leave.
        Writes a LEAVE_CANCELLATION_REVERSAL → restores used and clears
        reservation in one atomic ledger row. Status → CANCELLED.

    cancel_partial(db, actor, req, *, attendance_consumed_days)
        Manager-approved cancellation of the *future tail* of a leave that
        has already begun. Restores only the un-consumed remainder.
        Status → PARTIALLY_CANCELLED.

Concurrency
-----------
Every function calls into `post_ledger_entry` which selects the balance
row `FOR UPDATE`. Combined with the surrounding request-scoped transaction
(`db.commit()` is the caller's responsibility), this gives us:
  - row-level locking on the balance during mutation
  - atomic ledger + balance writes (commit or rollback together)
  - prevention of double-approval / double-cancellation races at DB level

The state machine is consulted first; an InvalidTransition aborts before
any side effect lands.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import (
    Employee, LeaveAuditLog, LeaveRequest, LedgerTxn, Notification, Role,
)
from app.services.email_dispatcher import dispatch_for_recipient
from app.services.leave_ledger import LedgerError, post_ledger_entry, adjust_pending
from app.services.leave_state_machine import (
    InvalidTransition, LeaveStatus, transition,
)
from utils.time_utils import now_utc


logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Raised by v2 workflow functions. Carries a status code so the route
    layer can surface clean HTTP responses without bespoke mapping."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ──────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return now_utc()


def _audit(db: Session, req: LeaveRequest, action: str, actor: Optional[Employee],
           from_status: str, to_status: str, *, note: Optional[str] = None) -> None:
    db.add(LeaveAuditLog(
        leave_request_id=req.id,
        action=action,
        actor_id=(actor.id if actor else None),
        from_status=from_status,
        to_status=to_status,
        note=note,
    ))


def _notify(db: Session, *, recipient_id: int, type_: str, title: str,
            body: str, leave_request_id: Optional[str] = None) -> None:
    if not recipient_id:
        return
    db.add(Notification(
        recipient_id=recipient_id,
        type=type_,
        title=title[:160],
        body=(body or "")[:500] or None,
        leave_request_id=leave_request_id,
        reference_table="leave_requests",
        reference_id=leave_request_id,
    ))
    # Best-effort email — mirrors leave_engine._notify so v2 approvals
    # produce the same outbound mail as v1 apply/reject paths. Never raises.
    try:
        dispatch_for_recipient(db, recipient_id, title, body)
    except Exception:
        logger.exception("email dispatch failed for recipient=%s", recipient_id)


def _hr_user_ids(db: Session) -> list[int]:
    """All active admin/HR user ids — strictly notification recipients in v2."""
    rows = (
        db.query(Employee.id)
        .join(Role)
        .filter(
            Role.name.in_(["admin", "hr"]),
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )
    return [r[0] for r in rows]


def _broadcast_hr(db: Session, req: LeaveRequest, *,
                  type_: str, title: str, body: str) -> None:
    for hr_id in _hr_user_ids(db):
        if hr_id == req.employee_id:
            continue
        _notify(db, recipient_id=hr_id, type_=type_, title=title, body=body,
                leave_request_id=req.id)


def _payroll_locked(req: LeaveRequest) -> bool:
    """Has this leave already been pushed to payroll? If yes, balance-affecting
    cancellations require an HR override (caller checks the actor role)."""
    return (req.payroll_sync_status or "na").lower() == "synced"


# ──────────────────────────────────────────────────────────────────────────
# 1) Manager approval — Hybrid v2 immediate deduction
# ──────────────────────────────────────────────────────────────────────────
def approve_hybrid(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Manager approves a pending leave request under v2 semantics.

    Pipeline (all inside the caller's transaction):
      1. State machine: pending → approved.
      2. Stamp manager approval audit fields.
      3. Release any pending_balance reservation set at apply time.
      4. Atomic LEAVE_DEDUCTION ledger entry — moves reserved+ AND used+.
      5. Notify employee (approved); notify HR informationally.
    """
    if req.status != LeaveStatus.PENDING:
        raise WorkflowError(400, f"Cannot approve a request in status '{req.status}'.")

    role = (actor.role.name.lower() if actor.role else "")
    if role not in ("manager", "admin"):
        raise WorkflowError(403, "Only managers or admins can approve leave.")

    now = _utcnow()
    try:
        transition(req, "approve_manager", actor)
    except InvalidTransition as exc:
        raise WorkflowError(400, str(exc))

    req.manager_approved_by = actor.id
    req.manager_approved_at = now
    req.approved_by         = actor.id
    req.approved_at         = now
    # SLA bookkeeping belongs to the pending stage we just exited.
    req.sla_escalation_level = 0
    req.sla_last_alert_at    = None
    req.approver_override_id = None

    # 1) Drop the pending-balance reservation set when the request was
    #    submitted (so the available balance math is correct before we
    #    write the immediate deduction).
    adjust_pending(db, req.employee_id, req.leave_type_id,
                   -req.total_days, year=req.start_date.year)

    # 2) Atomic immediate deduction. Writes a single LEAVE_DEDUCTION row
    #    whose `before/after` snapshot reflects BOTH reserved+ and used+.
    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.LEAVE_DEDUCTION,
            days=req.total_days,
            reference_type="leave_request",
            reference_id=req.id,
            actor=actor,
            note=f"Hybrid v2 approval by {actor.full_name}: reserved+used incremented",
            year=req.start_date.year,
        )
    except LedgerError as exc:
        # Roll the pending decrement back so the row is consistent before we
        # bubble the failure up to the route layer.
        adjust_pending(db, req.employee_id, req.leave_type_id,
                       +req.total_days, year=req.start_date.year)
        raise WorkflowError(409, f"Cannot approve: {exc}")

    _audit(db, req, "approved_manager_v2", actor,
           LeaveStatus.PENDING, LeaveStatus.APPROVED,
           note=f"Immediate deduction by {actor.full_name}")

    _notify(db, recipient_id=req.employee_id, type_="leave_approved",
            title="Leave request approved",
            body=f"Your leave from {req.start_date} to {req.end_date} is approved.",
            leave_request_id=req.id)

    _broadcast_hr(
        db, req,
        type_="leave_approved_hr_info",
        title="Leave approved (HR info)",
        body=f"{req.employee.full_name}: {req.leave_type.name if req.leave_type else 'leave'} "
             f"({req.start_date} → {req.end_date}, {req.total_days} day(s)) approved by "
             f"{actor.full_name}.",
    )

    return req


# ──────────────────────────────────────────────────────────────────────────
# 2) Scheduler completion — no balance change, just clear reservation
# ──────────────────────────────────────────────────────────────────────────
def complete_in_scheduler(db: Session, req: LeaveRequest, *,
                          consumed_days: Optional[int] = None) -> LeaveRequest:
    """Called by the leave scheduler when a leave's dates have passed.

    v2 semantics: `used` was already incremented at approval time, so the
    scheduler ONLY clears the reservation and marks the row COMPLETED.

    If `consumed_days` is provided, store it on the request so partial-cancel
    math has a real value (defaults to `total_days` when fully attended).
    """
    if req.status not in (LeaveStatus.APPROVED, LeaveStatus.CANCEL_PENDING):
        raise WorkflowError(400, f"Cannot complete a request in status '{req.status}'.")

    try:
        transition(req, "complete")
    except InvalidTransition as exc:
        raise WorkflowError(400, str(exc))

    req.consumed_days = consumed_days if consumed_days is not None else req.total_days

    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.LEAVE_COMPLETION,
            days=req.total_days,
            reference_type="leave_request",
            reference_id=req.id,
            actor=None,
            note="Scheduler: reservation cleared; balance unchanged (already debited at approval).",
            year=req.start_date.year,
        )
    except LedgerError as exc:
        raise WorkflowError(409, f"Cannot complete: {exc}")

    _audit(db, req, "completed_v2", None,
           LeaveStatus.APPROVED, LeaveStatus.COMPLETED,
           note="Scheduler completion — reservation cleared.")

    _notify(db, recipient_id=req.employee_id, type_="leave_completed",
            title="Leave completed",
            body=f"Your leave from {req.start_date} to {req.end_date} is now closed.",
            leave_request_id=req.id)

    return req


# ──────────────────────────────────────────────────────────────────────────
# 3) Full future cancellation — manager approves; rollback in one shot
# ──────────────────────────────────────────────────────────────────────────
def cancel_full_future(db: Session, actor: Employee, req: LeaveRequest) -> LeaveRequest:
    """Manager approves an employee's cancellation request for a future-dated
    leave that hasn't started yet. Fully reverses the deduction.

    Required preconditions:
      - status is CANCEL_PENDING (employee already raised the request)
      - leave hasn't started yet (start_date > today)
      - if payroll has already synced this request, an HR override is required
    """
    today = _utcnow().date()
    if req.status != LeaveStatus.CANCEL_PENDING:
        raise WorkflowError(400, f"Cannot approve cancellation in status '{req.status}'.")
    if req.start_date <= today:
        raise WorkflowError(
            400,
            "This leave has already started — use cancel_partial() for the future tail.",
        )

    role = (actor.role.name.lower() if actor.role else "")
    if role not in ("manager", "admin"):
        raise WorkflowError(403, "Only managers or admins can approve cancellations.")

    # Payroll safety — if already synced, gate on HR override.
    if _payroll_locked(req) and role != "admin":
        raise WorkflowError(
            409,
            "This leave is already locked in payroll. HR override required.",
        )

    now = _utcnow()
    try:
        transition(req, "approve_cancel", actor)
    except InvalidTransition as exc:
        raise WorkflowError(400, str(exc))

    req.cancel_manager_approved_by = actor.id
    req.cancel_manager_approved_at = now

    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.LEAVE_CANCELLATION_REVERSAL,
            days=req.total_days,
            reference_type="leave_request",
            reference_id=req.id,
            actor=actor,
            note=f"Full future cancellation reversal by {actor.full_name}",
            year=req.start_date.year,
        )
    except LedgerError as exc:
        raise WorkflowError(409, f"Cannot reverse: {exc}")

    _audit(db, req, "cancelled_full_v2", actor,
           LeaveStatus.CANCEL_PENDING, LeaveStatus.CANCELLED,
           note=f"Full cancellation approved by {actor.full_name}")

    _notify(db, recipient_id=req.employee_id, type_="leave_cancelled",
            title="Leave cancellation approved",
            body=f"Your leave from {req.start_date} to {req.end_date} has been cancelled and your balance restored.",
            leave_request_id=req.id)

    _broadcast_hr(
        db, req,
        type_="leave_cancelled_hr_info",
        title="Leave cancelled (HR info)",
        body=f"{req.employee.full_name}: {req.total_days} day(s) cancellation approved by {actor.full_name}.",
    )

    return req


# ──────────────────────────────────────────────────────────────────────────
# 4) Partial cancellation — keep the consumed portion, refund the tail
# ──────────────────────────────────────────────────────────────────────────
def reconcile_attendance(
    db: Session, req: LeaveRequest, *, as_of: Optional[date] = None,
) -> Tuple[int, int]:
    """Compute (consumed_days, remaining_days) from attendance evidence.

    consumed_days = count of (start_date..min(end_date, as_of)) excluding
                    days the employee was *present* (biometric/regular
                    attendance/timesheet/remote-work evidence).
    remaining_days = total_days - consumed_days

    Caller passes `as_of` = today (default) or any reference date. Days
    in the future are treated as not-yet-consumed.
    """
    from app.models import Attendance
    today = as_of or _utcnow().date()
    # Window we evaluate: from start_date to whichever comes first of
    # end_date and today. Anything past today is, by definition, future
    # tail that hasn't been consumed yet.
    cutoff = min(req.end_date, today)
    if cutoff < req.start_date:
        return (0, req.total_days)

    # Days within the window that have an Attendance row with status in
    # ('present', 'wfh', 'late') count as 'worked', so they are NOT
    # consumed leave.
    worked_rows = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == req.employee_id,
            Attendance.date >= req.start_date,
            Attendance.date <= cutoff,
            Attendance.status.in_(["present", "wfh", "late"]),
        )
        .all()
    )
    window_days  = (cutoff - req.start_date).days + 1
    worked_days  = len(worked_rows)
    consumed     = max(0, window_days - worked_days)
    consumed     = min(consumed, req.total_days)
    remaining    = max(0, req.total_days - consumed)
    return (consumed, remaining)


def cancel_partial(
    db: Session,
    actor: Employee,
    req: LeaveRequest,
    *,
    attendance_consumed_days: Optional[int] = None,
) -> LeaveRequest:
    """Approve a partial cancellation: keeps the consumed portion in
    `used` (payroll-safe), refunds only the future tail.

    If `attendance_consumed_days` is None, we run `reconcile_attendance`
    against the Attendance table to derive it. Callers (e.g. a strict
    admin flow) may pass the value explicitly when the reconciliation
    has already happened.
    """
    today = _utcnow().date()
    if req.status != LeaveStatus.CANCEL_PENDING:
        raise WorkflowError(400, f"Cannot partial-cancel in status '{req.status}'.")
    role = (actor.role.name.lower() if actor.role else "")
    if role not in ("manager", "admin"):
        raise WorkflowError(403, "Only managers or admins can approve cancellations.")

    if attendance_consumed_days is None:
        consumed, remaining = reconcile_attendance(db, req, as_of=today)
    else:
        consumed = max(0, min(int(attendance_consumed_days), req.total_days))
        remaining = req.total_days - consumed

    if remaining <= 0:
        raise WorkflowError(
            400,
            "Nothing to cancel — the leave has been fully consumed. Use the leave-reversal flow.",
        )
    if consumed <= 0:
        raise WorkflowError(
            400,
            "Nothing consumed yet — use cancel_full_future() instead of partial cancellation.",
        )

    # Payroll lock: refunding days that already synced needs HR override.
    if _payroll_locked(req) and role != "admin":
        raise WorkflowError(
            409,
            "This leave is already locked in payroll. HR override required.",
        )

    now = _utcnow()
    try:
        transition(req, "approve_partial_cancel", actor)
    except InvalidTransition as exc:
        raise WorkflowError(400, str(exc))

    req.cancel_manager_approved_by = actor.id
    req.cancel_manager_approved_at = now
    req.consumed_days              = consumed
    # `total_days` stays as the original ask so the audit trail still
    # tells you "5 day request, 2 consumed, 3 cancelled". Downstream
    # reports can use `consumed_days` as the source of truth for what
    # actually counted against the employee.

    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.PARTIAL_CANCELLATION,
            days=remaining,
            reference_type="leave_request",
            reference_id=req.id,
            actor=actor,
            note=(f"Partial cancellation by {actor.full_name}: "
                  f"{consumed} consumed, {remaining} refunded"),
            year=req.start_date.year,
        )
    except LedgerError as exc:
        raise WorkflowError(409, f"Cannot partial-cancel: {exc}")

    _audit(db, req, "partial_cancelled_v2", actor,
           LeaveStatus.CANCEL_PENDING, LeaveStatus.PARTIALLY_CANCELLED,
           note=f"Consumed {consumed}; refunded {remaining}")

    _notify(db, recipient_id=req.employee_id, type_="leave_partially_cancelled",
            title="Partial cancellation approved",
            body=(f"Your leave from {req.start_date} to {req.end_date} was partially cancelled: "
                  f"{consumed} day(s) kept, {remaining} day(s) restored to your balance."),
            leave_request_id=req.id)

    _broadcast_hr(
        db, req,
        type_="leave_partially_cancelled_hr_info",
        title="Partial cancellation (HR info)",
        body=(f"{req.employee.full_name}: partial cancellation approved by {actor.full_name}. "
              f"Consumed={consumed}, refunded={remaining}."),
    )

    return req
