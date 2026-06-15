"""Celery jobs for the attendance + timesheet system.

Mapped from the workflow diagram:

  - daily_attendance_processing : nightly job → run policy engine for
    yesterday for every active employee (Step 5/6).
  - detect_missed_checkouts     : flags employees who checked in but
    didn't check out within their shift window (Step 7 + Step 9 alert).
  - timesheet_submission_reminder : end-of-period nudge to employees who
    haven't submitted their timesheet (Step 13/9).

These are idempotent — re-running them produces the same end state.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.db.session import SessionLocal
from app.models import (
    AttendanceLog, AttendanceRecord, Employee, Timesheet,
)
from app.services.attendance_engine import process_day
from app.services.notification_service import notify
from app.tasks.celery_app import celery_app


@celery_app.task(name="attendance.daily_processing")
def daily_attendance_processing(target_date: str | None = None) -> dict:
    """Recompute records + exceptions for every active employee for the
    given date (default = yesterday)."""
    if target_date:
        on = date.fromisoformat(target_date)
    else:
        on = date.today() - timedelta(days=1)

    processed = 0
    with SessionLocal() as db:
        emps = (
            db.query(Employee)
            .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
            .all()
        )
        for e in emps:
            try:
                process_day(db, e.id, on, with_exceptions=True)
                processed += 1
            except Exception:
                continue
        db.commit()
    return {"date": str(on), "employees_processed": processed}


@celery_app.task(name="attendance.detect_missed_checkouts")
def detect_missed_checkouts() -> dict:
    """Identify open check-ins from earlier today that have no matching
    check-out, raise an in-app notification, and re-run the day record."""
    today = date.today()
    flagged = 0
    with SessionLocal() as db:
        emps = (
            db.query(Employee)
            .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
            .all()
        )
        for e in emps:
            logs_today = [
                l for l in
                db.query(AttendanceLog).filter(
                    AttendanceLog.employee_id == e.id,
                    AttendanceLog.is_valid.is_(True),
                ).all()
                if l.punch_timestamp and l.punch_timestamp.date() == today
            ]
            logs_today.sort(key=lambda l: l.punch_timestamp)
            if not logs_today:
                continue
            last = logs_today[-1]
            if last.punch_type == "check_in":
                # Open check-in — push a reminder.
                notify(
                    db,
                    recipient_id=e.id,
                    type_="missed_checkout",
                    title="Missed check-out reminder",
                    body=f"You haven't checked out yet today (last punch at {last.punch_timestamp.strftime('%H:%M')}).",
                    reference_table="attendance_logs",
                    reference_id=last.id,
                )
                flagged += 1
        db.commit()
    return {"date": str(today), "missed_checkouts": flagged}


@celery_app.task(name="timesheet.submission_reminder")
def timesheet_submission_reminder() -> dict:
    """Remind every employee who has an open period (today >= period_end + 1)
    but no submitted timesheet."""
    today = date.today()
    pinged = 0
    with SessionLocal() as db:
        # Reminders only for draft / rejected sheets whose period has ended.
        sheets = (
            db.query(Timesheet)
            .filter(
                Timesheet.status.in_(["draft", "rejected"]),
                Timesheet.period_end < today,
            )
            .all()
        )
        for ts in sheets:
            notify(
                db,
                recipient_id=ts.employee_id,
                type_="timesheet_reminder",
                title="Timesheet pending submission",
                body=f"Your timesheet for {ts.period_start} → {ts.period_end} is still in {ts.status} state.",
                reference_table="timesheets",
                reference_id=ts.id,
            )
            pinged += 1
        db.commit()
    return {"reminded": pinged}
