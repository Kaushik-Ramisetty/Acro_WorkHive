"""Encashment workflow.

Mirrors the manager-only approval model used by leave requests post-Phase-5A:
  - Employee creates a request: status='pending'.
  - Manager (or delegate, or admin override) approves or rejects.
  - On approval, a single ENCASHMENT ledger entry decrements
    `allocated_balance`. The ledger refuses (and the request stays
    'pending' with an error) if available has dropped below `days`
    between submission and approval — no race window.
  - HR is notified informationally on every transition.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Employee, EncashmentRequest, LeaveType, LedgerTxn, Notification,
)
from app.services.email_dispatcher import dispatch_for_recipient
from app.services.leave_ledger import LedgerError, get_available, post_ledger_entry
from utils.time_utils import now_utc


class EncashmentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _utcnow() -> datetime:
    return now_utc()


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u and u.role else None


def _notify(db: Session, recipient_id: int, type_: str, title: str,
            body: str) -> None:
    db.add(Notification(
        recipient_id=recipient_id, type=type_, title=title, body=body,
        leave_request_id=None,
    ))
    try:
        dispatch_for_recipient(db, recipient_id, title, body)
    except Exception:
        pass


def _hr_ids(db: Session) -> list[int]:
    # Mirror leave_engine._hr_user_ids without importing it (avoid cycle).
    from app.models import Role
    rows = (
        db.query(Employee.id)
        .join(Role)
        .filter(Role.name == "admin",
                Employee.is_deleted.is_(False),
                Employee.employment_status == "active")
        .all()
    )
    return [r.id for r in rows]


# ---------- public API ----------------------------------------------

def create_request(db: Session, actor: Employee, leave_type_id: str,
                   days: int, *, rate_per_day: Optional[float] = None,
                   reason: Optional[str] = None,
                   year: Optional[int] = None) -> EncashmentRequest:
    """Employee creates an encashment request. Pre-flight check ensures
    available balance covers the request at submission time — the
    authoritative re-check happens under row lock on approval."""
    if days <= 0:
        raise EncashmentError(400, "days must be at least 1.")

    lt = db.get(LeaveType, leave_type_id)
    if not lt:
        raise EncashmentError(400, f"Unknown leave type '{leave_type_id}'.")

    yr = year or _utcnow().year
    available = get_available(db, actor.id, leave_type_id, yr)
    if days > available:
        raise EncashmentError(
            400,
            f"Insufficient balance: available {available} day(s) of {lt.name}, "
            f"requested {days}.",
        )

    req = EncashmentRequest(
        employee_id=actor.id,
        leave_type_id=leave_type_id,
        year=yr,
        days=days,
        rate_per_day=rate_per_day,
        reason=reason,
        status="pending",
    )
    db.add(req)
    db.flush()

    # Notify manager (delegate-aware via the leave_engine helper).
    from app.services.leave_engine import _notify_manager_stage
    _notify_manager_stage(
        db,
        manager_id=actor.reporting_manager_id,
        type_="encashment_pending_your_approval",
        title="Encashment request awaiting your approval",
        body=f"{actor.full_name} requested encashment of {days} day(s) of {lt.name}.",
        leave_request_id=None,
    )
    _notify(
        db, actor.id, "encashment_submitted",
        title="Encashment request submitted",
        body=f"You requested encashment of {days} day(s) of {lt.name}.",
    )

    db.commit()
    db.refresh(req)
    return req


def approve_request(db: Session, actor: Employee, req: EncashmentRequest) -> EncashmentRequest:
    """Manager (or admin) approves. ENCASHMENT ledger entry posted under
    row lock — refuses with 409 if balance no longer covers it."""
    if req.status != "pending":
        raise EncashmentError(400, f"Cannot approve in status '{req.status}'.")

    actor_role = _role(actor)
    is_admin = actor_role == "admin"
    is_manager = (
        actor_role == "manager"
        and req.employee
        and req.employee.reporting_manager_id == actor.id
    )
    if not (is_admin or is_manager):
        raise EncashmentError(403, "Not authorized to approve this request.")

    try:
        post_ledger_entry(
            db,
            employee_id=req.employee_id,
            leave_type_id=req.leave_type_id,
            transaction_type=LedgerTxn.ENCASHMENT,
            days=req.days,
            reference_type="encashment_request",
            reference_id=str(req.id),
            actor=actor,
            note=f"Encashment of {req.days} day(s) approved by {actor.full_name}",
            year=req.year,
        )
    except LedgerError as exc:
        raise EncashmentError(409, f"Cannot encash: {exc}")

    req.status = "approved"
    req.approved_by = actor.id
    req.approved_at = _utcnow()
    # Hand off to payroll: the existing retry sweep tracks this field on
    # LeaveRequest; for encashment we only set the flag here. A future
    # payroll-bridge extension can pick these rows up via a single OR.
    req.payroll_sync_status = "pending"

    _notify(
        db, req.employee_id, "encashment_approved",
        title="Encashment request approved",
        body=f"Your encashment of {req.days} day(s) was approved by {actor.full_name}.",
    )
    # HR informational broadcast.
    for hr_id in _hr_ids(db):
        if hr_id == req.employee_id:
            continue
        _notify(
            db, hr_id, "encashment_approved_hr_info",
            title="Encashment approved (manager)",
            body=(
                f"{req.employee.full_name}: {req.days} day(s) of "
                f"{req.leave_type.name if req.leave_type else '?'} approved by "
                f"{actor.full_name}."
            ),
        )

    db.commit()
    db.refresh(req)
    return req


def reject_request(db: Session, actor: Employee, req: EncashmentRequest,
                   reason: Optional[str]) -> EncashmentRequest:
    if req.status != "pending":
        raise EncashmentError(400, f"Cannot reject in status '{req.status}'.")

    actor_role = _role(actor)
    is_admin = actor_role == "admin"
    is_manager = (
        actor_role == "manager"
        and req.employee
        and req.employee.reporting_manager_id == actor.id
    )
    if not (is_admin or is_manager):
        raise EncashmentError(403, "Not authorized.")

    req.status = "rejected"
    req.rejected_by = actor.id
    req.rejected_at = _utcnow()
    req.rejection_reason = reason

    _notify(
        db, req.employee_id, "encashment_rejected",
        title="Encashment request rejected",
        body=reason or "Your encashment request was rejected.",
    )

    db.commit()
    db.refresh(req)
    return req
