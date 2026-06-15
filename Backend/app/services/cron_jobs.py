"""Background cron job implementations.

Four jobs (all idempotent via jobs_log):

  1. end_of_day_attendance   — 11:59 PM daily
     - Recompute all attendance_records for today (active, non-deleted employees)
     - Detect missing checkouts + short hours → attendance_exceptions
     - Notify HR for each exception
     - Update payroll_attendance_summary

  2. leave_sync              — 12:05 AM daily
     - Cross-reference absent attendance_records with approved leave_requests
     - Update status, leave_request_id, lop_applied

  3. timesheet_reminders     — 9:00 AM daily
     - Find timesheets status='pending' submitted > 2 days ago, reminder_count < 5
     - Resend client approval notification, increment reminder_count

  4. attendance_digest       — 6:30 PM daily
     - Aggregate all unresolved attendance exceptions for today
     - Push one consolidated in-app notification to every admin/HR user

Isolation requirements:
  - All employee queries filter by is_deleted=False AND employment_status='active'.
  - Timesheet auto-generation is restricted to employee_type='client_site'.
  - Payroll summaries are per-employee with no cross-tenant bleed.
"""
from __future__ import annotations

import logging
from datetime import date as date_t, timedelta

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AttendanceException, AttendanceRecord, Employee, JobsLog,
    LeaveRequest, Notification, PayrollAttendanceSummary, Timesheet,
)
from app.services.attendance_digest import generate_attendance_digest
from app.services.attendance_engine import detect_exceptions_for_record, process_day
from app.services.notification_service import notify, notify_many
from utils.time_utils import now_utc

logger = logging.getLogger("hrms.cron")


# ── Idempotency helpers ───────────────────────────────────────────────

def _already_ran_today(db: Session, job_name: str) -> bool:
    today = date_t.today()
    row = (
        db.query(JobsLog)
        .filter(
            JobsLog.job_name == job_name,
            JobsLog.status == "success",
        )
        .order_by(JobsLog.ran_at.desc())
        .first()
    )
    return bool(row and row.ran_at.date() == today)


def _log_job(db: Session, job_name: str, status: str, notes: str | None = None) -> None:
    db.add(JobsLog(job_name=job_name, ran_at=now_utc(), status=status, notes=notes))
    db.commit()


# ── Shared employee query helper ─────────────────────────────────────

def _active_employees(db: Session) -> list[Employee]:
    """Return all active, non-deleted employees.

    This is the canonical filter used by all cron jobs — never query
    employees without these two guards to avoid processing terminated or
    deleted accounts.
    """
    return (
        db.query(Employee)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )


def _client_site_employees(db: Session) -> list[Employee]:
    """Return active employees assigned to client sites (timesheet-eligible)."""
    return (
        db.query(Employee)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
            Employee.employee_type == "client_site",
        )
        .all()
    )


def _hr_admin_ids(employees: list[Employee]) -> list[int]:
    """Extract HR/admin employee IDs from a pre-fetched list."""
    return [
        e.id for e in employees
        if e.role and e.role.name.lower() in {"admin", "hr"}
    ]


# ── Job 1: End-of-day attendance (11:59 PM) ──────────────────────────

def run_end_of_day_attendance() -> None:
    JOB = "end_of_day_attendance"
    with SessionLocal() as db:
        if _already_ran_today(db, JOB):
            logger.info("[%s] already ran today — skipping", JOB)
            return

        today = date_t.today()
        exceptions_raised = 0
        employees_processed = 0

        try:
            active_emps = _active_employees(db)
            hr_ids = _hr_admin_ids(active_emps)

            for emp in active_emps:
                try:
                    rec = process_day(db, emp.id, today, with_exceptions=True)
                    db.flush()
                    employees_processed += 1

                    new_exc = (
                        db.query(AttendanceException)
                        .filter(
                            AttendanceException.employee_id == emp.id,
                            AttendanceException.date == today,
                            AttendanceException.is_resolved.is_(False),
                        )
                        .count()
                    )
                    if new_exc and hr_ids:
                        exceptions_raised += new_exc
                        notify_many(
                            db, hr_ids,
                            type_="attendance_exception",
                            title=f"Attendance exception: {emp.full_name}",
                            body=f"{new_exc} exception(s) on {today}",
                            reference_table="attendance_records",
                            reference_id=rec.id if rec else "",
                        )
                except Exception as exc:
                    logger.warning("[%s] employee %s failed: %s", JOB, emp.id, exc)

            _update_payroll_summary(db, today, active_emps)

            db.commit()
            _log_job(db, JOB, "success",
                     f"processed={employees_processed} exceptions={exceptions_raised}")
            logger.info("[%s] done — %d employees, %d exceptions", JOB, employees_processed, exceptions_raised)

        except Exception as exc:
            db.rollback()
            _log_job(db, JOB, "failed", str(exc))
            logger.error("[%s] FAILED: %s", JOB, exc)
            raise


def _update_payroll_summary(db: Session, today: date_t, active_emps: list) -> None:
    """Refresh payroll_attendance_summary for each employee for the current month.

    Each employee's summary is strictly isolated — we only aggregate that
    employee's own attendance_records, never a cross-employee join.
    """
    month_name = today.strftime("%B")
    year = today.year
    month_start = today.replace(day=1)
    month_end = today

    for emp in active_emps:
        records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.date >= month_start,
                AttendanceRecord.date <= month_end,
            )
            .all()
        )

        statuses = [r.status or "" for r in records]
        present   = sum(1 for s in statuses if s in ("present", "late"))
        absent    = sum(1 for s in statuses if s == "absent")
        half_days = sum(1 for s in statuses if s == "half_day")
        late_days = sum(1 for s in statuses if s == "late")
        leave_days = sum(1 for s in statuses if s == "on_leave")
        holidays  = sum(1 for s in statuses if s == "holiday")
        lop_days  = sum(1 for r in records if r.lop_applied)
        ot_hours  = round(sum(r.overtime_hours or 0.0 for r in records), 2)

        existing = (
            db.query(PayrollAttendanceSummary)
            .filter(
                PayrollAttendanceSummary.employee_id == emp.id,
                PayrollAttendanceSummary.month == month_name,
                PayrollAttendanceSummary.year == year,
            )
            .first()
        )
        if existing:
            existing.total_working_days = len(records)
            existing.present_days   = present
            existing.absent_days    = absent
            existing.half_days      = half_days
            existing.late_days      = late_days
            existing.leave_days     = leave_days
            existing.holiday_count  = holidays
            existing.lop_days       = lop_days
            existing.overtime_hours = ot_hours
        else:
            n = db.query(PayrollAttendanceSummary).count() + 1
            pas_id = f"PAS{n:05d}"
            db.add(PayrollAttendanceSummary(
                id=pas_id,
                employee_id=emp.id,
                month=month_name,
                year=year,
                total_working_days=len(records),
                present_days=present,
                absent_days=absent,
                half_days=half_days,
                late_days=late_days,
                leave_days=leave_days,
                holiday_count=holidays,
                lop_days=lop_days,
                overtime_hours=ot_hours,
            ))


# ── Job 2: Leave sync (12:05 AM) ────────────────────────────────────

def run_leave_sync() -> None:
    """Cross-reference absent attendance records with approved leave requests.

    Scoped strictly per-employee — no cross-tenant queries.
    """
    JOB = "leave_sync"
    with SessionLocal() as db:
        if _already_ran_today(db, JOB):
            logger.info("[%s] already ran today — skipping", JOB)
            return

        updated = 0
        try:
            # Only process absent records for active employees.
            active_emp_ids = {
                e.id for e in _active_employees(db)
            }

            absent_records = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.status == "absent",
                    AttendanceRecord.employee_id.in_(active_emp_ids),
                )
                .all()
            )

            for rec in absent_records:
                if not rec.date:
                    continue
                leave = (
                    db.query(LeaveRequest)
                    .filter(
                        LeaveRequest.employee_id == rec.employee_id,
                        LeaveRequest.start_date <= rec.date,
                        LeaveRequest.end_date >= rec.date,
                        LeaveRequest.status.in_(["approved", "consumed"]),
                    )
                    .first()
                )
                if leave:
                    rec.status = "on_leave"
                    rec.leave_request_id = str(leave.id)
                    rec.lop_applied = False
                    rec.lop_type = None
                    updated += 1
                else:
                    if not rec.lop_applied:
                        rec.lop_applied = True
                        rec.lop_type = "absent_without_leave"

            db.commit()
            _log_job(db, JOB, "success", f"synced={updated} absent→on_leave")
            logger.info("[%s] done — %d records updated", JOB, updated)

        except Exception as exc:
            db.rollback()
            _log_job(db, JOB, "failed", str(exc))
            logger.error("[%s] FAILED: %s", JOB, exc)
            raise


# ── Job 3: Timesheet reminders (9:00 AM) ────────────────────────────

def run_timesheet_reminders() -> None:
    """Find pending timesheets older than 2 days, resend client notification,
    increment reminder_count (max 5).

    Only processes timesheets belonging to active client_site employees.
    """
    JOB = "timesheet_reminders"
    with SessionLocal() as db:
        if _already_ran_today(db, JOB):
            logger.info("[%s] already ran today — skipping", JOB)
            return

        reminded = 0
        cutoff = now_utc() - timedelta(days=2)

        try:
            # Restrict to active client_site employees — no orphaned timesheets.
            eligible_ids = {e.id for e in _client_site_employees(db)}

            pending = (
                db.query(Timesheet)
                .filter(
                    # Accept both statuses: "pending_client_review" (new) and
                    # "pending" (legacy records created before the status rename)
                    Timesheet.status.in_(["pending_client_review", "pending"]),
                    Timesheet.submitted_at <= cutoff,
                    Timesheet.reminder_count < 5,
                    Timesheet.employee_id.in_(eligible_ids),
                )
                .all()
            )

            # Pre-fetch HR ids once (avoid N+1 in the loop).
            active_emps = _active_employees(db)
            hr_ids = _hr_admin_ids(active_emps)

            for ts in pending:
                emp = db.get(Employee, ts.employee_id)
                emp_name = emp.full_name if emp else f"Employee #{ts.employee_id}"

                if ts.client_manager_id:
                    notify(
                        db,
                        recipient_id=ts.client_manager_id,
                        type_="timesheet_approval_reminder",
                        title="Reminder: Timesheet awaiting your approval",
                        body=f"{emp_name} — {ts.period_start} to {ts.period_end}",
                        reference_table="timesheets",
                        reference_id=ts.id,
                    )

                if not ts.client_manager_id and hr_ids:
                    notify_many(
                        db, hr_ids,
                        type_="timesheet_approval_reminder",
                        title=f"Reminder: Timesheet pending — {emp_name}",
                        body=f"{ts.period_start} to {ts.period_end} ({ts.total_logged_hours or 0} h)",
                        reference_table="timesheets",
                        reference_id=ts.id,
                    )

                ts.reminder_count = (ts.reminder_count or 0) + 1
                reminded += 1

            db.commit()
            _log_job(db, JOB, "success", f"reminded={reminded}")
            logger.info("[%s] done — %d timesheets reminded", JOB, reminded)

        except Exception as exc:
            db.rollback()
            _log_job(db, JOB, "failed", str(exc))
            logger.error("[%s] FAILED: %s", JOB, exc)
            raise


# ── Job 4: Daily attendance digest (6:30 PM) ─────────────────────────

def run_attendance_digest() -> None:
    """Aggregate today's unresolved attendance exceptions and push one
    consolidated in-app notification to every admin/HR user.

    Idempotent — skips if already ran successfully today.
    No notification is sent when there are zero exceptions (clean day).
    """
    JOB = "attendance_digest"
    with SessionLocal() as db:
        if _already_ran_today(db, JOB):
            logger.info("[%s] already ran today — skipping", JOB)
            return

        today = date_t.today()

        try:
            active_emps = _active_employees(db)
            hr_ids = _hr_admin_ids(active_emps)

            if not hr_ids:
                logger.info("[%s] no admin/HR recipients — skipping", JOB)
                _log_job(db, JOB, "success", "no_recipients")
                return

            result = generate_attendance_digest(db, today, hr_ids)
            db.commit()

            _log_job(
                db, JOB, "success",
                f"total_exceptions={result.total} "
                f"notifications_sent={result.notifications_sent} "
                f"recipients={len(hr_ids)}",
            )
            logger.info(
                "[%s] done — %d exceptions, %d notifications sent to %d recipients",
                JOB, result.total, result.notifications_sent, len(hr_ids),
            )

        except Exception as exc:
            db.rollback()
            _log_job(db, JOB, "failed", str(exc))
            logger.error("[%s] FAILED: %s", JOB, exc)
            raise
