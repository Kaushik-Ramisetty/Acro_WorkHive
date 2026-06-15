"""Payroll Attendance Bridge service.

╔══════════════════════════════════════════════════════════════════════════╗
║  TEMPORARY PAYROLL BRIDGE                                                 ║
║  Source will be the Attendance/Timesheet modules after integration.       ║
║                                                                           ║
║  Payroll flow:                                                            ║
║    1. HR/Admin creates monthly summary (manual or from Attendance module) ║
║    2. HR validates the summary (checks completeness, day math)            ║
║    3. HR freezes the summary (locks it, notifies Finance)                 ║
║    4. Finance generates payroll (blocked until frozen)                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.monthly_attendance_summary import MonthlyAttendanceSummary
from app.models.employee import Employee
from app.services.payroll_bridge import aggregate_leave_days_for_payroll_month

log = logging.getLogger("hrms.payroll.attendance_bridge")
LOP_SOURCE = "Leave Management"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _role_name(emp: Employee) -> str:
    return (emp.role.name if emp.role else "unknown").lower()


def _month_label(month: int, year: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def _write_audit(
    db: Session,
    *,
    user_id: Optional[int],
    role: Optional[str],
    action: str,
    month: int,
    year: int,
    details: Optional[str] = None,
) -> None:
    """Write a payroll attendance audit entry. Never raises."""
    try:
        db.execute(
            text("""
                INSERT INTO payroll_attendance_audit
                    (user_id, role, action, month, year, details, created_at)
                VALUES
                    (:uid, :role, :action, :month, :year, :details, datetime('now'))
            """),
            {
                "uid": user_id,
                "role": role,
                "action": action,
                "month": month,
                "year": year,
                "details": details,
            },
        )
    except Exception as exc:
        log.warning("Payroll attendance audit write failed (non-fatal): %s", exc)


# ─── Active employees query ───────────────────────────────────────────────────

def _active_employees(db: Session) -> list[Employee]:
    return (
        db.query(Employee)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )


def _leave_payroll_days(db: Session, employee_id: int, month: int, year: int) -> dict[str, int]:
    return aggregate_leave_days_for_payroll_month(db, employee_id, month, year)


def _apply_leave_payroll_overlay(row: MonthlyAttendanceSummary, leave_days: dict[str, int]) -> None:
    row.leave_days = max(0, int(leave_days.get("paid_leave_days") or 0))
    row.lop_days = max(0, int(leave_days.get("lop_days") or 0))
    row.lop_source = LOP_SOURCE
    row.lop_status = "ready"
    row.lop_last_synced_at = datetime.utcnow()
    if row.total_working_days and row.total_working_days > 0:
        total_wd = int(row.total_working_days)
        row.payable_days = float(max(total_wd - row.lop_days, 0))
        # Ensure present_days + leave_days + lop_days <= total_working_days so the
        # payroll reconciliation check (present + leave + holidays + lop == working_days)
        # can balance. When the attendance row starts at full-present (e.g. demo seed or
        # no separate attendance records) the leave overlay must reduce present_days.
        total_absence = row.leave_days + row.lop_days
        if (row.present_days or 0) + total_absence > total_wd:
            row.present_days = max(0, total_wd - total_absence)


def _refresh_leave_lop_overlays(db: Session, month: int, year: int) -> None:
    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(month=month, year=year)
        .all()
    )
    for row in rows:
        if row.is_frozen:
            continue
        if row.lop_source == "Manual Override":
            continue  # Preserve manually set LOP — don't let leave-system sync overwrite it
        _apply_leave_payroll_overlay(row, _leave_payroll_days(db, row.employee_id, month, year))


# ─── Core service functions ───────────────────────────────────────────────────

def get_open_month(db: Session) -> dict:
    """Return the auto-detected open payroll month and available months list.

    The "open month" is the latest (year DESC, month DESC) month in
    monthly_attendance_summary that has at least one non-frozen row —
    i.e., HR still has work to do for that month.

    Falls back to the current calendar month when no attendance data exists.

    Returns
    -------
    {
      month: int, year: int, month_label: str,
      has_data: bool,
      available_months: [
        {month, year, month_label, is_fully_frozen}, ...
      ]   # newest-first; only months that have ≥1 row in the table
    }
    """
    # All distinct (year, month) pairs with any data — newest first
    all_pairs = (
        db.query(MonthlyAttendanceSummary.month, MonthlyAttendanceSummary.year)
        .distinct()
        .order_by(MonthlyAttendanceSummary.year.desc(), MonthlyAttendanceSummary.month.desc())
        .all()
    )

    # Pairs that still have at least one non-frozen row
    open_pairs: set[tuple[int, int]] = {
        (row.month, row.year)
        for row in db.query(
            MonthlyAttendanceSummary.month, MonthlyAttendanceSummary.year
        )
        .filter(MonthlyAttendanceSummary.is_frozen.is_(False))
        .distinct()
        .all()
    }

    from datetime import date as _date
    today = _date.today()

    available_months: list[dict] = []
    open_month: dict | None = None

    for pair in all_pairs:
        is_fully_frozen = (pair.month, pair.year) not in open_pairs
        label = _month_label(pair.month, pair.year)
        available_months.append({
            "month": pair.month,
            "year": pair.year,
            "month_label": label,
            "is_fully_frozen": is_fully_frozen,
        })
        if open_month is None and not is_fully_frozen:
            open_month = {"month": pair.month, "year": pair.year, "month_label": label}

    # Fall back to current calendar month when no data exists at all
    if open_month is None:
        fallback_label = _month_label(today.month, today.year)
        open_month = {"month": today.month, "year": today.year, "month_label": fallback_label}

    return {
        "month": open_month["month"],
        "year": open_month["year"],
        "month_label": open_month["month_label"],
        "has_data": len(all_pairs) > 0,
        "available_months": available_months,
    }


def get_summary(db: Session, month: int, year: int) -> dict:
    """Return aggregated readiness status for HR payroll dashboard.

    Fields returned:
      total_employees     – active head count
      with_summary        – employees that have a monthly_attendance_summary row
      missing_summary     – employees with no row yet
      frozen_count        – rows with is_frozen=True
      ready_count         – rows with is_ready_for_payroll=True
      issues_count        – sum of issues_count across all rows
      validation_passed   – rows where validation_status='passed'
      validation_failed   – rows where validation_status='failed'
      all_frozen          – True if every active employee has a frozen row
      attendance_overall  – pending | partial | ready | frozen
      rows                – per-employee detail list
    """
    active = _active_employees(db)
    emp_ids = [e.id for e in active]
    total = len(emp_ids)

    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter(
            MonthlyAttendanceSummary.month == month,
            MonthlyAttendanceSummary.year == year,
            MonthlyAttendanceSummary.employee_id.in_(emp_ids),
        )
        .all()
    ) if emp_ids else []

    row_map = {r.employee_id: r for r in rows}
    emp_map = {e.id: e for e in active}

    with_summary = len(rows)
    missing_ids = [eid for eid in emp_ids if eid not in row_map]
    frozen_count = sum(1 for r in rows if r.is_frozen)
    ready_count = sum(1 for r in rows if r.is_ready_for_payroll)
    total_issues = sum(r.issues_count for r in rows)
    val_passed = sum(1 for r in rows if r.validation_status == "passed")
    val_failed = sum(1 for r in rows if r.validation_status == "failed")
    all_frozen = (total > 0) and (frozen_count == total)

    if frozen_count == total and total > 0:
        overall = "frozen"
    elif ready_count == total and total > 0:
        overall = "ready"
    elif with_summary == 0:
        overall = "pending"
    else:
        overall = "partial"

    detail = []
    for eid in emp_ids:
        emp = emp_map[eid]
        r = row_map.get(eid)
        # blocked_lop_days is a runtime check for LOP that arrived after a freeze;
        # it drives the warning banner only and is not stored in the DB.
        leave_data = _leave_payroll_days(db, eid, month, year)
        blocked_lop_days = leave_data.get("blocked_lop_days", 0)
        detail.append({
            "employee_id": eid,
            "employee_code": emp.employee_code,
            "employee_name": emp.full_name,
            "department": emp.department.name if emp.department else None,
            "designation": emp.designation.title if emp.designation else None,
            "date_of_joining": str(emp.date_of_joining) if emp.date_of_joining else None,
            "has_summary": r is not None,
            "total_working_days": r.total_working_days if r else None,
            "present_days": r.present_days if r else None,
            # Read lop_days, leave_days, payable_days directly from DB.
            # get_summary() is read-only — no writes happen here.
            "leave_days": r.leave_days if r else None,
            "lop_days": r.lop_days if r else None,
            "lop_source": r.lop_source if r else None,
            "lop_status": (
                "reopen_required"
                if blocked_lop_days > 0
                else ("ready" if r else "pending")
            ),
            "lop_warning": (
                "Payroll input is frozen. Reopen payroll input to include this LOP."
                if blocked_lop_days > 0
                else None
            ),
            "lop_last_synced_at": r.lop_last_synced_at if r else None,
            "payable_days": r.payable_days if r else None,
            "approved_timesheet_hours": r.approved_timesheet_hours if r else None,
            "attendance_status": r.attendance_status if r else "missing",
            "timesheet_status": r.timesheet_status if r else "missing",
            "validation_status": (
                "failed" if blocked_lop_days > 0 else (r.validation_status if r else "missing")
            ),
            "is_ready_for_payroll": (
                False if blocked_lop_days > 0 else (r.is_ready_for_payroll if r else False)
            ),
            "is_frozen": r.is_frozen if r else False,
            "issues_count": r.issues_count if r else 0,
            "validation_notes": r.validation_notes if r else None,
        })

    return {
        "month": month,
        "year": year,
        "month_label": _month_label(month, year),
        "total_employees": total,
        "with_summary": with_summary,
        "missing_summary": len(missing_ids),
        "missing_employee_ids": missing_ids,
        "frozen_count": frozen_count,
        "ready_count": ready_count,
        "issues_count": total_issues,
        "validation_passed": val_passed,
        "validation_failed": val_failed,
        "all_frozen": all_frozen,
        "attendance_overall": overall,
        "rows": detail,
    }


def upsert_manual_summary(
    db: Session,
    *,
    employee_id: int,
    month: int,
    year: int,
    total_working_days: int,
    present_days: int,
    leave_days: int,
    payable_days: float,
    lop_days: Optional[int] = None,
    approved_timesheet_hours: float = 0.0,
    timesheet_status: str = "pending",
    actor: Employee,
) -> MonthlyAttendanceSummary:
    """Create or update a manual monthly attendance summary entry.

    ── TEMPORARY PAYROLL BRIDGE ──
    Allowed only when the row is NOT yet frozen. A frozen row can only be
    modified by unfreezing (currently not supported — freeze is final).

    Validation_status is reset to 'pending' on every upsert so the
    HR must re-validate after any manual edit.

    lop_days — when explicitly provided, stored as a "Manual Override" and
    protected from future Leave Management syncs. When omitted (None), LOP
    is computed from approved unpaid leave requests as usual.
    """
    existing = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(employee_id=employee_id, month=month, year=year)
        .first()
    )
    if existing and existing.is_frozen:
        raise ValueError(
            f"Attendance for this employee is already frozen for "
            f"{_month_label(month, year)}. Cannot modify a frozen record."
        )

    if existing:
        row = existing
    else:
        row = MonthlyAttendanceSummary(employee_id=employee_id, month=month, year=year)
        db.add(row)

    row.total_working_days = total_working_days
    row.present_days = present_days
    row.payable_days = payable_days
    if lop_days is not None:
        row.lop_days = max(0, lop_days)
        row.lop_source = "Manual Override"
        row.lop_status = "ready"
        row.lop_last_synced_at = datetime.utcnow()
        row.payable_days = float(max(total_working_days - row.lop_days, 0))
    else:
        _apply_leave_payroll_overlay(row, _leave_payroll_days(db, employee_id, month, year))
    row.approved_timesheet_hours = approved_timesheet_hours
    row.timesheet_status = timesheet_status
    # Reset validation state — any edit invalidates the previous validation
    row.validation_status = "pending"
    row.issues_count = 0
    row.validation_notes = None
    row.is_ready_for_payroll = False
    row.attendance_status = "submitted"

    db.flush()
    _write_audit(
        db,
        user_id=actor.id,
        role=_role_name(actor),
        action="MANUAL_ATTENDANCE_SUMMARY_CREATED",
        month=month,
        year=year,
        details=(
            f"employee_id={employee_id} total_working_days={total_working_days} "
            f"present={present_days} paid_leave={row.leave_days} "
            f"lop_source={row.lop_source} lop={row.lop_days} "
            f"payable={row.payable_days}"
        ),
    )
    log.info(
        "[ATT_BRIDGE] Manual summary upserted: employee_id=%d month=%d year=%d "
        "by actor_id=%d",
        employee_id, month, year, actor.id,
    )
    return row


def validate_summary(
    db: Session,
    *,
    month: int,
    year: int,
    actor: Employee,
) -> dict:
    """Validate all monthly attendance summary rows for a given month/year.

    Validation rules:
      V1  Missing summary — employee has no row at all
      V2  Negative days   — any of present/leave/lop/payable < 0
      V3  Attendance overflow — present_days > total_working_days
      V4  Zero working days — total_working_days = 0
      V5  Payable > total  — payable_days > total_working_days
      V6  Timesheet pending — timesheet_status = 'pending' (warning, not blocker)

    After validation:
      row.validation_status = 'passed' | 'failed'
      row.issues_count = number of hard errors
      row.is_ready_for_payroll = True only when issues_count = 0
    """
    active = _active_employees(db)
    emp_ids = [e.id for e in active]
    emp_map = {e.id: e for e in active}

    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(month=month, year=year)
        .all()
    )
    _refresh_leave_lop_overlays(db, month, year)
    row_map = {r.employee_id: r for r in rows}

    all_issues: list[dict] = []
    passed = 0
    failed = 0

    for eid in emp_ids:
        emp_name = emp_map[eid].full_name
        row = row_map.get(eid)

        if row is None:
            all_issues.append({
                "employee_id": eid,
                "employee_name": emp_name,
                "rule": "V1",
                "severity": "error",
                "message": "No attendance summary found for this employee.",
            })
            failed += 1
            continue

        if row.is_frozen:
            # Already frozen — skip re-validation
            passed += 1
            continue

        emp_issues: list[str] = []

        # V2 — negative days
        for field_name, val in [
            ("present_days", row.present_days),
            ("leave_days", row.leave_days),
            ("lop_days", row.lop_days),
            ("payable_days", row.payable_days),
        ]:
            if (val or 0) < 0:
                emp_issues.append(f"V2: {field_name} is negative ({val})")

        # V4 — zero working days
        if (row.total_working_days or 0) == 0:
            emp_issues.append("V4: total_working_days is 0")

        # V3 — attendance overflow. Leave/LOP are separate Leave Management
        # overlays, so full-present temporary attendance data must not block
        # approved paid leave or LOP visibility.
        if (row.total_working_days or 0) > 0 and (row.present_days or 0) > row.total_working_days:
            emp_issues.append(
                f"V3: present({row.present_days}) exceeds total_working_days({row.total_working_days})"
            )

        leave_total = (row.leave_days or 0) + (row.lop_days or 0)
        if (row.total_working_days or 0) > 0 and leave_total > row.total_working_days:
            emp_issues.append(
                f"V7: leave({row.leave_days}) + LOP({row.lop_days}) exceeds total_working_days({row.total_working_days})"
            )

        # V5 — payable overflow
        if (row.payable_days or 0) > (row.total_working_days or 0):
            emp_issues.append(
                f"V5: payable_days({row.payable_days}) > "
                f"total_working_days({row.total_working_days})"
            )

        # V6 — timesheet pending (warning only — does NOT block)
        warnings: list[str] = []
        if row.timesheet_status == "pending":
            warnings.append("V6: Timesheet not yet approved (warning only)")

        row.issues_count = len(emp_issues)
        if emp_issues:
            row.validation_status = "failed"
            row.is_ready_for_payroll = False
            row.validation_notes = "; ".join(emp_issues + warnings)
            failed += 1
            for msg in emp_issues:
                all_issues.append({
                    "employee_id": eid,
                    "employee_name": emp_name,
                    "rule": msg.split(":")[0],
                    "severity": "error",
                    "message": msg,
                })
        else:
            row.validation_status = "passed"
            row.is_ready_for_payroll = True
            row.validation_notes = "; ".join(warnings) if warnings else None
            row.attendance_status = "validated"
            passed += 1
            if warnings:
                all_issues.append({
                    "employee_id": eid,
                    "employee_name": emp_name,
                    "rule": "V6",
                    "severity": "warning",
                    "message": warnings[0],
                })

    db.flush()

    _write_audit(
        db,
        user_id=actor.id,
        role=_role_name(actor),
        action="ATTENDANCE_SUMMARY_VALIDATED",
        month=month,
        year=year,
        details=f"passed={passed} failed={failed} issues={len(all_issues)}",
    )

    return {
        "month": month,
        "year": year,
        "month_label": _month_label(month, year),
        "total_employees": len(emp_ids),
        "validation_passed": passed,
        "validation_failed": failed,
        "total_issues": len(all_issues),
        "issues": all_issues,
        "can_freeze": failed == 0 and passed == len(emp_ids),
    }


def freeze_attendance(
    db: Session,
    *,
    month: int,
    year: int,
    actor: Employee,
) -> dict:
    """Freeze monthly attendance — last step before Finance can run payroll.

    Rules:
    - All active employees must have a validated (passed) row.
    - Once frozen, rows cannot be edited.
    - Notifies all Finance and Finance Head users.
    - Writes payroll_attendance_audit entry.

    After freeze the PayrollRun's freeze_attendance action (existing flow)
    still works because that action operates on payroll_runs, not this table.
    Payroll generation is blocked unless at least one frozen row exists for
    the run's month/year — see payroll_service.py guard.
    """
    active = _active_employees(db)
    emp_ids = [e.id for e in active]
    total = len(emp_ids)

    if total == 0:
        raise ValueError("No active employees found.")

    _refresh_leave_lop_overlays(db, month, year)

    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(month=month, year=year)
        .all()
    )
    row_map = {r.employee_id: r for r in rows}

    # Guard: every active employee must have a passed row
    not_ready: list[int] = []
    for eid in emp_ids:
        r = row_map.get(eid)
        if r is None or not r.is_ready_for_payroll:
            not_ready.append(eid)

    if not_ready:
        raise ValueError(
            f"Cannot freeze: {len(not_ready)} employee(s) are not ready for payroll. "
            "Run validation first and resolve all issues."
        )

    now = datetime.utcnow()
    for r in rows:
        r.is_frozen = True
        r.finalized_by = actor.id
        r.finalized_at = now
        r.attendance_status = "finalized"

    db.flush()

    # Create or advance a PayrollRun to attendance_frozen so Finance can generate payroll
    _ensure_payroll_run_frozen(db, month=month, year=year, total_employees=total, actor=actor)

    # Notify Finance and Finance Head
    label = _month_label(month, year)
    _notify_finance(
        db,
        title=f"Attendance finalized — {label}",
        body=f"Attendance finalized for {label}. Payroll ready for processing.",
        month=month,
        year=year,
    )

    _write_audit(
        db,
        user_id=actor.id,
        role=_role_name(actor),
        action="ATTENDANCE_FROZEN_FOR_PAYROLL",
        month=month,
        year=year,
        details=f"frozen_count={total} by actor_id={actor.id}",
    )

    log.info(
        "[ATT_BRIDGE] Payroll input frozen for month=%d year=%d by actor_id=%d (%d employees)",
        month, year, actor.id, total,
    )

    return {
        "month": month,
        "year": year,
        "month_label": label,
        "frozen_count": total,
        "message": f"Attendance for {label} has been frozen. Finance has been notified.",
    }


def _ensure_payroll_run_frozen(
    db: Session,
    *,
    month: int,
    year: int,
    total_employees: int,
    actor: Employee,
) -> None:
    """Create or advance a PayrollRun to attendance_frozen status.

    After HR freezes attendance, Finance must be able to Generate Payroll.
    The payroll state machine requires status=attendance_frozen for that.
    This helper finds or creates the run and advances it to that status.
    """
    try:
        import calendar as _cal
        from app.models.payroll import PayrollRun

        _ADVANCEABLE = {"draft", "attendance_frozen"}

        # Find any non-cancelled run for this month/year
        run = (
            db.query(PayrollRun)
            .filter(
                PayrollRun.month == month,
                PayrollRun.year == year,
                PayrollRun.status.notin_(["cancelled"]),
            )
            .order_by(PayrollRun.id.desc())
            .first()
        )

        if run is None:
            # Create a fresh draft and immediately set to attendance_frozen
            import datetime as _dt
            first_day = _dt.date(year, month, 1)
            last_day = _dt.date(year, month, _cal.monthrange(year, month)[1])
            run = PayrollRun(
                pay_period_start=first_day,
                pay_period_end=last_day,
                month_label=f"{_cal.month_name[month]} {year}",
                month=month,
                year=year,
                status="attendance_frozen",
                total_employees=total_employees,
                attendance_locked=True,
                payroll_locked=False,
                initiated_by_id=actor.id,
                initiated_at=_dt.datetime.utcnow(),
            )
            db.add(run)
            db.flush()
            log.info(
                "[ATT_BRIDGE] Created PayrollRun id=%d for month=%d year=%d (attendance_frozen)",
                run.id, month, year,
            )
        elif run.status in _ADVANCEABLE:
            run.status = "attendance_frozen"
            run.total_employees = total_employees
            run.attendance_locked = True
            db.flush()
            log.info(
                "[ATT_BRIDGE] Advanced PayrollRun id=%d to attendance_frozen (month=%d year=%d)",
                run.id, month, year,
            )
        else:
            # Run already past attendance_frozen — just sync total_employees
            run.total_employees = total_employees
            db.flush()
            log.info(
                "[ATT_BRIDGE] PayrollRun id=%d already at status=%s for month=%d year=%d — skipped advance",
                run.id, run.status, month, year,
            )
    except Exception as exc:
        log.warning(
            "[ATT_BRIDGE] _ensure_payroll_run_frozen failed (non-fatal): %s", exc
        )


def _notify_finance(
    db: Session,
    *,
    title: str,
    body: str,
    month: int,
    year: int,
) -> None:
    """Notify all Finance and Finance Head users. Never raises."""
    try:
        from app.services.notification_service import notify
        from app.models.role import Role as _Role

        finance_roles = (
            db.query(_Role)
            .filter(_Role.name.in_(["finance", "finance_head"]))
            .all()
        )
        role_ids = [r.id for r in finance_roles]
        if not role_ids:
            return

        users = (
            db.query(Employee)
            .filter(
                Employee.role_id.in_(role_ids),
                Employee.is_deleted.is_(False),
                Employee.employment_status == "active",
            )
            .all()
        )
        for u in users:
            notify(
                db,
                recipient_id=u.id,
                type_="attendance_frozen",
                title=title,
                body=body,
                reference_table="monthly_attendance_summary",
                reference_id=f"{month}-{year}",
                autocommit=True,
            )
        log.info(
            "[ATT_BRIDGE] Notified %d finance user(s) for month=%d year=%d",
            len(users), month, year,
        )
    except Exception as exc:
        log.warning("Finance notification after freeze failed (non-fatal): %s", exc)


def reset_freeze_summary(
    db: Session,
    *,
    month: int,
    year: int,
    actor: Employee,
) -> dict:
    """[DEV ONLY] Unfreeze attendance summary rows for re-testing.

    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  TEMPORARY FOR PAYROLL TESTING.                                          ║
    ║  REMOVE AFTER REAL ATTENDANCE/TIMESHEET INTEGRATION.                     ║
    ║                                                                           ║
    ║  This function is intentionally NOT exposed to production users.          ║
    ║  It exists only to allow repeated testing of the freeze/validate flow     ║
    ║  without manually editing the database.                                   ║
    ╚══════════════════════════════════════════════════════════════════════════╝

    What this does (ONLY on monthly_attendance_summary rows):
      is_frozen            → False
      attendance_status    → 'validated'   (READY)
      timesheet_status     → 'approved'    (READY)
      validation_status    → 'passed'      (VALID)
      issues_count         → 0
      is_ready_for_payroll → True
      finalized_by         → NULL
      finalized_at         → NULL

    What this does NOT do:
      - Does NOT delete attendance rows
      - Does NOT delete payroll runs or payroll records
      - Does NOT delete notifications already sent
      - Does NOT affect salary structures
      - Does NOT affect finance approvals
      - Does NOT affect any employee data
    """
    # ── TEMPORARY FOR PAYROLL TESTING. REMOVE AFTER REAL ATT/TS INTEGRATION ──
    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter_by(month=month, year=year)
        .all()
    )

    if not rows:
        raise ValueError(
            f"No attendance summary rows found for {_month_label(month, year)}. "
            "Create or import attendance summary rows first."
        )

    reset_count = 0
    for row in rows:
        row.is_frozen            = False
        row.attendance_status    = "validated"   # READY
        row.timesheet_status     = "approved"    # READY
        row.validation_status    = "passed"      # VALID
        row.issues_count         = 0
        row.is_ready_for_payroll = True
        row.finalized_by         = None
        row.finalized_at         = None
        _apply_leave_payroll_overlay(row, _leave_payroll_days(db, row.employee_id, month, year))
        reset_count += 1

    db.flush()

    label = _month_label(month, year)
    _write_audit(
        db,
        user_id=actor.id,
        role=_role_name(actor),
        action="ATTENDANCE_FREEZE_RESET",
        month=month,
        year=year,
        details=(
            f"reset_count={reset_count} by actor_id={actor.id} "
            f"(DEV ONLY — testing reset)"
        ),
    )
    log.info(
        "[ATT_BRIDGE][DEV] Attendance freeze reset: month=%d year=%d by actor_id=%d "
        "(%d rows unfrozen) — TEMPORARY TESTING ONLY",
        month, year, actor.id, reset_count,
    )

    return {
        "month": month,
        "year": year,
        "month_label": label,
        "reset_count": reset_count,
        "message": (
            f"[DEV] Attendance freeze reset for {reset_count} employee(s) — {label}. "
            "You can now validate and freeze again."
        ),
    }


def check_frozen_for_payroll(db: Session, month: int, year: int) -> tuple[bool, str]:
    """Return (is_ok, error_message) — used by payroll_service to gate generation.

    Returns (True, '') when attendance is frozen for the given period.
    Returns (False, reason) otherwise.

    ── TEMPORARY PAYROLL BRIDGE ──
    Once Attendance/Timesheet modules integrate they will set is_frozen=True
    on this table and the gate will pass automatically.
    """
    active = _active_employees(db)
    if not active:
        # No employees — allow payroll to proceed (empty run)
        return True, ""

    total = len(active)
    emp_ids = [e.id for e in active]

    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter(
            MonthlyAttendanceSummary.month == month,
            MonthlyAttendanceSummary.year == year,
            MonthlyAttendanceSummary.employee_id.in_(emp_ids),
        )
        .all()
    )
    row_map = {r.employee_id: r for r in rows}
    frozen_count = sum(1 for r in rows if r.is_frozen)

    if frozen_count == 0:
        return (
            False,
            "Attendance and timesheet summary is not finalized. "
            "HR must freeze payroll inputs before payroll generation.",
        )

    if frozen_count < total:
        missing = total - frozen_count
        return (
            False,
            f"Attendance not frozen for {missing} employee(s). "
            "HR must freeze all employees before payroll generation.",
        )

    # C-3: verify is_ready_for_payroll flag — HR must mark records as ready
    not_ready_ids = [
        eid for eid in emp_ids
        if row_map.get(eid) and not row_map[eid].is_ready_for_payroll
    ]
    if not_ready_ids:
        return (
            False,
            f"Payroll input not ready for {len(not_ready_ids)} employee(s) "
            "(is_ready_for_payroll is False). "
            "HR must complete attendance review and mark inputs as ready before payroll generation.",
        )

    # C-3: block if attendance validation has explicitly failed
    failed_validation_ids = [
        eid for eid in emp_ids
        if row_map.get(eid) and row_map[eid].validation_status == "failed"
    ]
    if failed_validation_ids:
        return (
            False,
            f"Attendance validation failed for {len(failed_validation_ids)} employee(s). "
            "Resolve validation issues in the Attendance module before generating payroll.",
        )

    stale_lop_count = 0
    for eid in emp_ids:
        row = row_map.get(eid)
        leave_days = _leave_payroll_days(db, eid, month, year)
        if row is not None and int(row.lop_days or 0) != int(leave_days["lop_days"] or 0):
            stale_lop_count += 1

    if stale_lop_count:
        # Stale LOP is a data-quality warning, not a generation blocker.
        # Leave Management changes after the attendance freeze are common (e.g. late
        # leave approvals). Payroll generation will use the frozen lop_days; Finance
        # should review any LOP mismatch as a PayrollError warning.
        log.warning(
            "[check_frozen] %d employee(s) have stale LOP (frozen summary vs current "
            "Leave Management mismatch) for month=%d year=%d — allowing generation; "
            "Finance will see PayrollError warnings for these employees.",
            stale_lop_count, month, year,
        )

    return True, ""
