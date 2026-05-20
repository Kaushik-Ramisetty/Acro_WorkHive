"""Payroll integration for the leave engine.

When a leave request transitions to `consumed`, this module upserts its
days into the `payroll_attendance_summary` row for that employee + month.
Failures are tracked on the LeaveRequest itself (`payroll_sync_status`,
`payroll_sync_attempts`, `payroll_last_error`) so the retry task can
sweep them later.

Why we upsert into `payroll_attendance_summary` rather than a separate
queue table:
  - There's already exactly one row per (employee, month, year) used
    downstream by payroll reports.
  - "Leave days" and "LOP days" columns already exist on that row, so
    leave-driven payroll math just needs to bump those counters.
  - One source of truth means no reconciliation step.

Sync rules:
  - Paid leave types (`LeaveType.is_paid == True`): +N to `leave_days`.
  - Unpaid types (`is_paid == False`): +N to `leave_days` AND +N to
    `lop_days`. (lop_days is the column payroll runs use to deduct salary.)
  - If the target month's summary `is_finalized == True`, the sync fails
    — payroll is closed for that period; HR must reopen or backdate by hand.
  - When a leave spans two months, the days are split month-by-month.

The bridge is intentionally synchronous + transactional. The caller
(leave_engine.process_pending_consumption) commits the LeaveRequest +
payroll row in the same transaction so we never end up with a consumed
leave that was never reflected anywhere.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Employee, LeaveRequest, LeaveType, Notification, PayrollAttendanceSummary,
)
from app.services.email_dispatcher import dispatch_for_recipient
from utils.time_utils import now_utc


MAX_RETRY_ATTEMPTS = 5


# ---------- helpers --------------------------------------------------

def _utcnow() -> datetime:
    return now_utc()


def _month_label(d: date) -> str:
    return d.strftime("%B")


def _split_by_month(start: date, end: date) -> dict[tuple[int, str], int]:
    """Return {(year, month_name): day_count} for the inclusive range."""
    out: dict[tuple[int, str], int] = defaultdict(int)
    cur = start
    while cur <= end:
        out[(cur.year, _month_label(cur))] += 1
        cur += timedelta(days=1)
    return out


def _next_summary_id(db: Session) -> str:
    """Generate the next 'PAS#####' identifier."""
    last = (
        db.query(PayrollAttendanceSummary)
        .filter(PayrollAttendanceSummary.id.like("PAS%"))
        .order_by(PayrollAttendanceSummary.id.desc())
        .first()
    )
    n = 1
    if last and last.id and last.id.startswith("PAS"):
        try:
            n = int(last.id[3:]) + 1
        except ValueError:
            pass
    return f"PAS{n:05d}"


def _get_or_create_summary(db: Session, employee_id: int, year: int,
                           month_label: str) -> PayrollAttendanceSummary:
    row = (
        db.query(PayrollAttendanceSummary)
        .filter(
            PayrollAttendanceSummary.employee_id == employee_id,
            PayrollAttendanceSummary.year == year,
            PayrollAttendanceSummary.month == month_label,
        )
        .first()
    )
    if row:
        return row
    row = PayrollAttendanceSummary(
        id=_next_summary_id(db),
        employee_id=employee_id,
        year=year,
        month=month_label,
        total_working_days=0,
        present_days=0,
        absent_days=0,
        half_days=0,
        late_days=0,
        leave_days=0,
        holiday_count=0,
        lop_days=0,
        overtime_hours=0.0,
        is_finalized=False,
    )
    db.add(row)
    db.flush()
    return row


def _notify_admins(db: Session, type_: str, title: str, body: str,
                   leave_request_id: Optional[str]) -> None:
    # Local import to dodge circular: leave_engine also imports this module.
    from app.services.leave_engine import _hr_user_ids
    for hr_id in _hr_user_ids(db):
        db.add(Notification(
            recipient_id=hr_id, type=type_, title=title, body=body,
            leave_request_id=leave_request_id,
        ))
        try:
            dispatch_for_recipient(db, hr_id, title, body)
        except Exception:
            pass


# ---------- public API ----------------------------------------------

def sync_leave_to_payroll(db: Session, req: LeaveRequest) -> tuple[bool, Optional[str]]:
    """Upsert a single consumed leave into payroll_attendance_summary.

    Returns (success, error_message). Mutates `req.payroll_*` fields but
    does NOT commit — the caller decides transaction boundaries.
    """
    req.payroll_sync_attempts = int(req.payroll_sync_attempts or 0) + 1

    if req.status != "consumed":
        msg = f"Cannot sync to payroll: status is '{req.status}', expected 'consumed'."
        req.payroll_sync_status = "failed"
        req.payroll_last_error = msg
        return False, msg

    lt = db.get(LeaveType, req.leave_type_id) if req.leave_type_id else None
    if not lt:
        msg = f"Unknown leave type '{req.leave_type_id}'."
        req.payroll_sync_status = "failed"
        req.payroll_last_error = msg
        return False, msg

    is_unpaid = not bool(lt.is_paid)
    splits = _split_by_month(req.start_date, req.end_date)

    # First pass — detect any finalized month so the whole write is atomic
    # (we don't want to partially write the unfinalized months and then
    # fail on the finalized one; the caller would have a dangling state).
    for (year, month_label), _ in splits.items():
        existing = (
            db.query(PayrollAttendanceSummary)
            .filter(
                PayrollAttendanceSummary.employee_id == req.employee_id,
                PayrollAttendanceSummary.year == year,
                PayrollAttendanceSummary.month == month_label,
            )
            .first()
        )
        if existing and existing.is_finalized:
            msg = (
                f"Payroll for {month_label} {year} is finalized; "
                f"manual reopen needed for leave {req.id}."
            )
            req.payroll_sync_status = "failed"
            req.payroll_last_error = msg
            return False, msg

    # Second pass — apply the increments.
    for (year, month_label), days in splits.items():
        row = _get_or_create_summary(db, req.employee_id, year, month_label)
        row.leave_days = int(row.leave_days or 0) + days
        if is_unpaid:
            row.lop_days = int(row.lop_days or 0) + days

    req.payroll_sync_status = "synced"
    req.payroll_synced_at = _utcnow()
    req.payroll_last_error = None
    return True, None


def reverse_leave_from_payroll(db: Session, req: LeaveRequest, days: int,
                                start: date, end: date,
                                is_unpaid: bool) -> tuple[bool, Optional[str]]:
    """Subtract a previously-synced leave (used when WoL validation reverses
    a consumed leave). No-op if no summary rows exist for the months."""
    splits = _split_by_month(start, end)
    for (year, month_label), d in splits.items():
        row = (
            db.query(PayrollAttendanceSummary)
            .filter(
                PayrollAttendanceSummary.employee_id == req.employee_id,
                PayrollAttendanceSummary.year == year,
                PayrollAttendanceSummary.month == month_label,
            )
            .first()
        )
        if not row:
            continue
        if row.is_finalized:
            msg = (
                f"Cannot reverse: payroll for {month_label} {year} is finalized."
            )
            req.payroll_last_error = msg
            return False, msg
        row.leave_days = max(0, int(row.leave_days or 0) - d)
        if is_unpaid:
            row.lop_days = max(0, int(row.lop_days or 0) - d)
    req.payroll_last_error = None
    return True, None


def queue_for_payroll_sync(req: LeaveRequest) -> None:
    """Mark a freshly-consumed request as needing payroll sync. Called by
    the engine immediately after `req.status = 'consumed'`."""
    req.payroll_sync_status = "pending"
    req.payroll_synced_at = None
    req.payroll_sync_attempts = 0
    req.payroll_last_error = None


def retry_pending_syncs(db: Session) -> dict:
    """Retry sweep: scans every leave with payroll_sync_status in
    ('pending', 'failed') and attempts `sync_leave_to_payroll` on it.

    Failures past `MAX_RETRY_ATTEMPTS` trigger an admin notification once,
    then stop retrying until an admin intervenes (resets attempts or
    finalizes the month). The status stays 'failed' so the row remains
    visible in the admin queue.
    """
    summary = {"examined": 0, "synced": 0, "failed": 0, "skipped_max_attempts": 0}
    rows = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.payroll_sync_status.in_(("pending", "failed")))
        .all()
    )
    for req in rows:
        summary["examined"] += 1
        if int(req.payroll_sync_attempts or 0) >= MAX_RETRY_ATTEMPTS and req.payroll_sync_status == "failed":
            summary["skipped_max_attempts"] += 1
            continue
        ok, err = sync_leave_to_payroll(db, req)
        if ok:
            summary["synced"] += 1
        else:
            summary["failed"] += 1
            if int(req.payroll_sync_attempts or 0) == MAX_RETRY_ATTEMPTS:
                # First time we cross the threshold — alert admins once.
                _notify_admins(
                    db,
                    type_="payroll_sync_max_retries",
                    title="Payroll sync stuck: manual review required",
                    body=(
                        f"Leave {req.id} for employee #{req.employee_id} failed payroll "
                        f"sync {MAX_RETRY_ATTEMPTS} times. Last error: {err}"
                    ),
                    leave_request_id=req.id,
                )
    db.commit()
    return summary
