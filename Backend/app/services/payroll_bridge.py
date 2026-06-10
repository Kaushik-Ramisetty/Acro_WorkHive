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
    MonthlyAttendanceSummary, PayrollLopInput,
)
from app.services.email_dispatcher import dispatch_for_recipient
from utils.time_utils import now_utc


MAX_RETRY_ATTEMPTS = 5
LOP_SOURCE = "Leave Management"
PAYROLL_ACTIVE_LEAVE_STATUSES = (
    "approved",
    "cancel_pending",
    "consumed",
    "completed",
    "partially_cancelled",
)


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


def _split_by_month_number(start: date, end: date) -> dict[tuple[int, int], int]:
    """Return {(year, month_number): day_count} for the inclusive range."""
    out: dict[tuple[int, int], int] = defaultdict(int)
    cur = start
    while cur <= end:
        out[(cur.year, cur.month)] += 1
        cur += timedelta(days=1)
    return out


def _split_request_days_by_month(req: LeaveRequest) -> dict[tuple[int, int], int]:
    """Split a leave request's approved day count across calendar months."""
    calendar_splits = _split_by_month_number(req.start_date, req.end_date)
    if not calendar_splits:
        return {}

    days = int(req.consumed_days or 0) if req.status == "partially_cancelled" else int(req.total_days or 0)
    if days <= 0:
        days = sum(calendar_splits.values())
    if len(calendar_splits) == 1:
        key = next(iter(calendar_splits))
        return {key: days}

    total_calendar_days = sum(calendar_splits.values())
    weighted: list[tuple[tuple[int, int], int, float]] = []
    assigned = 0
    for key, calendar_days in calendar_splits.items():
        raw = days * (calendar_days / total_calendar_days)
        whole = int(raw)
        weighted.append((key, whole, raw - whole))
        assigned += whole

    remainder = max(0, days - assigned)
    weighted.sort(key=lambda item: item[2], reverse=True)
    out = {key: whole for key, whole, _ in weighted}
    for idx in range(remainder):
        key = weighted[idx % len(weighted)][0]
        out[key] += 1
    return {key: value for key, value in out.items() if value > 0}


def aggregate_leave_days_for_payroll_month(
    db: Session,
    employee_id: int,
    month: int,
    year: int,
) -> dict[str, int]:
    """Approved Leave Management days for payroll display/calculation."""
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    paid_leave_days = 0
    lop_days = 0
    blocked_lop_days = 0

    rows = (
        db.query(LeaveRequest)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(PAYROLL_ACTIVE_LEAVE_STATUSES),
            LeaveRequest.approved_at.is_not(None),
            LeaveRequest.start_date <= month_end,
            LeaveRequest.end_date >= month_start,
        )
        .all()
    )
    for req in rows:
        days = _split_request_days_by_month(req).get((year, month), 0)
        if days <= 0:
            continue
        leave_type = req.leave_type or (db.get(LeaveType, req.leave_type_id) if req.leave_type_id else None)
        is_unpaid = bool(getattr(req, "is_lop", False)) or (leave_type is not None and not bool(leave_type.is_paid))
        if is_unpaid:
            lop_days += days
            err = (req.payroll_last_error or "").lower()
            if (req.payroll_sync_status or "").lower() == "failed" and "frozen" in err:
                blocked_lop_days += days
        else:
            paid_leave_days += days

    return {
        "paid_leave_days": paid_leave_days,
        "lop_days": lop_days,
        "blocked_lop_days": blocked_lop_days,
    }


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


def _get_or_create_monthly_summary(
    db: Session,
    employee_id: int,
    year: int,
    month: int,
) -> MonthlyAttendanceSummary:
    row = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(employee_id=employee_id, month=month, year=year)
        .first()
    )
    if row:
        return row

    row = MonthlyAttendanceSummary(
        employee_id=employee_id,
        month=month,
        year=year,
        lop_source=LOP_SOURCE,
        lop_status="ready",
    )
    db.add(row)
    db.flush()
    return row


def _frozen_month_error(db: Session, req: LeaveRequest, splits: dict[tuple[int, int], int]) -> Optional[str]:
    for (year, month), _ in splits.items():
        row = (
            db.query(MonthlyAttendanceSummary)
            .filter_by(employee_id=req.employee_id, month=month, year=year)
            .first()
        )
        if row and row.is_frozen:
            return "Payroll input is frozen. Reopen payroll input to include this LOP."
    return None


def _refresh_monthly_lop_overlay(
    db: Session,
    employee_id: int,
    year: int,
    month: int,
    *,
    create: bool = True,
) -> None:
    leave_days = aggregate_leave_days_for_payroll_month(db, employee_id, month, year)
    total = leave_days["lop_days"]

    row = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(employee_id=employee_id, month=month, year=year)
        .first()
    )
    if not row and (create or total > 0):
        row = _get_or_create_monthly_summary(db, employee_id, year, month)
    if not row:
        return
    if row.is_frozen:
        raise ValueError(
            f"Payroll input for {calendar.month_name[month]} {year} is frozen."
        )

    lop_days = int(total)
    row.leave_days = int(leave_days["paid_leave_days"])
    row.lop_days = lop_days
    row.lop_source = LOP_SOURCE
    row.lop_status = "ready"
    row.lop_last_synced_at = _utcnow()
    if row.total_working_days and row.total_working_days > 0:
        row.payable_days = float(max(int(row.total_working_days) - lop_days, 0))


def _upsert_leave_lop_inputs(
    db: Session,
    req: LeaveRequest,
    splits: dict[tuple[int, int], int],
) -> None:
    for (year, month), days in splits.items():
        row = (
            db.query(PayrollLopInput)
            .filter_by(
                leave_request_id=req.id,
                employee_id=req.employee_id,
                month=month,
                year=year,
            )
            .first()
        )
        if not row:
            row = PayrollLopInput(
                leave_request_id=req.id,
                employee_id=req.employee_id,
                month=month,
                year=year,
            )
            db.add(row)
        row.lop_days = float(days)
        row.source = LOP_SOURCE
        row.status = "ready"
        _refresh_monthly_lop_overlay(db, req.employee_id, year, month)


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
    lop_splits = _split_by_month_number(req.start_date, req.end_date)

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

    if is_unpaid:
        msg = _frozen_month_error(db, req, lop_splits)
        if msg:
            req.payroll_sync_status = "failed"
            req.payroll_last_error = msg
            return False, msg

    # Second pass — apply the increments.
    for (year, month_label), days in splits.items():
        row = _get_or_create_summary(db, req.employee_id, year, month_label)
        row.leave_days = int(row.leave_days or 0) + days

    if is_unpaid:
        try:
            _upsert_leave_lop_inputs(db, req, lop_splits)
        except ValueError as exc:
            msg = str(exc)
            req.payroll_sync_status = "failed"
            req.payroll_last_error = msg
            return False, msg

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
    lop_splits = _split_by_month_number(start, end)
    if is_unpaid:
        msg = _frozen_month_error(db, req, lop_splits)
        if msg:
            req.payroll_last_error = msg
            return False, msg

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
        for (year, month), _ in lop_splits.items():
            (
                db.query(PayrollLopInput)
                .filter_by(
                    leave_request_id=req.id,
                    employee_id=req.employee_id,
                    month=month,
                    year=year,
                )
                .delete(synchronize_session=False)
            )
            _refresh_monthly_lop_overlay(db, req.employee_id, year, month, create=False)
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
        lt = db.get(LeaveType, req.leave_type_id) if req.leave_type_id else None
        if req.status == "approved" and lt and not bool(lt.is_paid):
            ok, err = sync_lop_to_payroll(db, req)
        else:
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


def sync_lop_to_payroll(db: Session, req: LeaveRequest) -> tuple[bool, Optional[str]]:
    """Sync an HR-approved LOP leave to monthly payroll inputs immediately.

    Called right after HR approval (not waiting for scheduler consumption).
    Upserts idempotent Leave Management LOP rows and overlays the aggregate
    into monthly_attendance_summary.lop_days for each month spanned.
    Returns (success, error_message).
    """
    req.payroll_sync_attempts = int(req.payroll_sync_attempts or 0) + 1

    lt = db.get(LeaveType, req.leave_type_id) if req.leave_type_id else None
    is_lop_type = lt and not bool(lt.is_paid)
    if not is_lop_type:
        msg = f"sync_lop_to_payroll called for non-LOP type '{req.leave_type_id}'."
        return False, msg

    splits = _split_by_month_number(req.start_date, req.end_date)
    msg = _frozen_month_error(db, req, splits)
    if msg:
        req.payroll_sync_status = "failed"
        req.payroll_last_error = msg
        return False, msg

    try:
        _upsert_leave_lop_inputs(db, req, splits)
    except ValueError as exc:
        msg = str(exc)
        req.payroll_sync_status = "failed"
        req.payroll_last_error = msg
        return False, msg

    req.payroll_sync_status = "synced"
    req.payroll_synced_at = _utcnow()
    req.payroll_last_error = None
    return True, None
