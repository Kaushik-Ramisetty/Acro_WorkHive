"""Attendance engine — validation + policy + exception detection.

Implements steps 3 - 7 of the HRMS Attendance Workflow diagram:

    3. Validation Layer            -> validate_punch()
    4. Store Raw Attendance Logs   -> create_punch()  (writes AttendanceLog)
    5. Apply Attendance Policies   -> compute_record_for_day()
    6. Generate Final Record       -> compute_record_for_day()  (writes AttendanceRecord)
    7. Exception / Anomaly Detect  -> detect_exceptions()       (writes AttendanceException)

System rules respected:
    - Raw AttendanceLog rows are never deleted; they're the source of truth.
    - AttendanceRecord is the *processed* data and can be re-derived at any
      time by re-running compute_record_for_day().
    - Approved leave on a date overrides attendance computation
      (-> status='on_leave').
    - Holidays from the holidays table mark days as 'holiday'.
"""
from __future__ import annotations

from datetime import date as date_t, datetime, time, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from utils.time_utils import now_utc

from app.models import (
    AttendanceException,
    AttendanceLog,
    AttendancePolicy,
    AttendanceRecord,
    Employee,
    EmployeeShift,
    Holiday,
    LeaveRequest,
    Shift,
    ValidationError,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _next_log_id(db: Session) -> str:
    n = db.query(AttendanceLog).count() + 1
    candidate = f"AL{n:06d}"
    while db.get(AttendanceLog, candidate) is not None:
        n += 1
        candidate = f"AL{n:06d}"
    return candidate


def _next_record_id(db: Session) -> str:
    n = db.query(AttendanceRecord).count() + 1
    candidate = f"AR{n:06d}"
    while db.get(AttendanceRecord, candidate) is not None:
        n += 1
        candidate = f"AR{n:06d}"
    return candidate


def _next_exception_id(db: Session) -> str:
    n = db.query(AttendanceException).count() + 1
    candidate = f"AE{n:04d}"
    while db.get(AttendanceException, candidate) is not None:
        n += 1
        candidate = f"AE{n:04d}"
    return candidate


def _next_validation_error_id(db: Session) -> str:
    n = db.query(ValidationError).count() + 1
    candidate = f"VE{n:04d}"
    while db.get(ValidationError, candidate) is not None:
        n += 1
        candidate = f"VE{n:04d}"
    return candidate


def _minutes_between(a: time, b: time) -> int:
    """Signed minute diff (b - a) using a date anchor of 1970-01-01."""
    da = datetime.combine(date_t(1970, 1, 1), a)
    db = datetime.combine(date_t(1970, 1, 1), b)
    return int((db - da).total_seconds() // 60)


def _hours_between(a: time, b: time) -> float:
    if a is None or b is None:
        return 0.0
    da = datetime.combine(date_t(1970, 1, 1), a)
    db_ = datetime.combine(date_t(1970, 1, 1), b)
    sec = (db_ - da).total_seconds()
    if sec < 0:
        sec += 24 * 3600  # night-shift wraparound
    return round(sec / 3600.0, 2)


def get_employee_shift(db: Session, employee_id: int, on: date_t) -> Optional[Shift]:
    """Return the Shift assigned to the employee on this date, or the first
    active shift as a fallback."""
    es = (
        db.query(EmployeeShift)
        .filter(
            EmployeeShift.employee_id == employee_id,
            EmployeeShift.effective_from <= on,
            or_(EmployeeShift.effective_to.is_(None), EmployeeShift.effective_to >= on),
        )
        .order_by(EmployeeShift.effective_from.desc())
        .first()
    )
    if es:
        return db.get(Shift, es.shift_id)
    return db.query(Shift).first()


def get_policy_for_shift(db: Session, shift_id: Optional[str]) -> Optional[AttendancePolicy]:
    if not shift_id:
        return db.query(AttendancePolicy).filter(AttendancePolicy.is_active.is_(True)).first()
    pol = (
        db.query(AttendancePolicy)
        .filter(AttendancePolicy.shift_id == shift_id, AttendancePolicy.is_active.is_(True))
        .first()
    )
    return pol or db.query(AttendancePolicy).filter(AttendancePolicy.is_active.is_(True)).first()


def is_weekly_off(shift: Optional[Shift], on: date_t) -> bool:
    if not shift or not shift.weekly_off_days:
        return on.weekday() >= 5  # default Sat/Sun
    days = {d.strip().lower() for d in shift.weekly_off_days.split(",") if d.strip()}
    return on.strftime("%A").lower() in days


def is_holiday(db: Session, on: date_t) -> Optional[Holiday]:
    return db.query(Holiday).filter(Holiday.date == on).first()


def approved_leave_for(db: Session, employee_id: int, on: date_t) -> Optional[LeaveRequest]:
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.start_date <= on,
            LeaveRequest.end_date >= on,
            LeaveRequest.status.in_(["approved", "consumed", "cancel_pending"]),
        )
        .first()
    )


# ── Step 3: VALIDATION LAYER ─────────────────────────────────────────

def validate_punch(
    db: Session,
    employee_id: int,
    punch_type: str,
    when: datetime,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Return (is_valid, validation_rule, error_message).

    Rules enforced:
      - punch_type must be 'check_in' or 'check_out'
      - no duplicate punches within 60s of an existing valid punch
      - check_out requires a prior valid check_in on the same day
      - check_in cannot follow another open check_in (must check_out first)
    """
    if punch_type not in {"check_in", "check_out"}:
        return False, "invalid_punch_type", "Punch type must be check_in or check_out."

    today = when.date()

    # Same-day valid logs ordered by time.
    day_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.is_valid.is_(True),
        )
        .all()
    )
    same_day = [l for l in day_logs if l.punch_timestamp and l.punch_timestamp.date() == today]
    same_day.sort(key=lambda l: l.punch_timestamp)

    # Duplicate detection: any same-type punch within 60s.
    for l in same_day:
        if l.punch_type == punch_type and abs((l.punch_timestamp - when).total_seconds()) < 60:
            return False, "duplicate_punch", "A punch of the same type was just recorded."

    last = same_day[-1] if same_day else None
    if punch_type == "check_in":
        if last and last.punch_type == "check_in":
            return False, "missing_previous_checkout", "You must check out before checking in again."
    else:  # check_out
        if not last or last.punch_type != "check_in":
            return False, "missing_checkin", "No open check-in found for today."

    return True, None, None


def _record_validation_error(
    db: Session,
    *,
    log_id: Optional[str],
    employee_id: int,
    when: datetime,
    rule: str,
    description: str,
    severity: str = "error",
) -> None:
    db.add(ValidationError(
        id=_next_validation_error_id(db),
        attendance_log_id=log_id,
        employee_id=employee_id,
        punch_timestamp=when,
        validation_rule=rule,
        rule_description=description,
        severity=severity,
    ))


# ── Step 4: STORE RAW LOG ────────────────────────────────────────────

def create_punch(
    db: Session,
    *,
    employee_id: int,
    punch_type: str,
    when: Optional[datetime] = None,
    device_info: Optional[str] = None,
    location_lat: Optional[float] = None,
    location_lng: Optional[float] = None,
    source: str = "web",
) -> AttendanceLog:
    """Validate then write an AttendanceLog. ALWAYS persists (raw logs are
    immutable evidence) — invalid punches are stored with is_valid=False
    plus a corresponding ValidationError row."""
    when = when or now_utc()
    is_valid, rule, msg = validate_punch(db, employee_id, punch_type, when)

    log = AttendanceLog(
        id=_next_log_id(db),
        employee_id=employee_id,
        punch_type=punch_type,
        punch_timestamp=when,
        device_info=device_info,
        location_lat=location_lat,
        location_lng=location_lng,
        source=source,
        is_valid=is_valid,
        validation_error=msg,
        validation_rule=rule,
    )
    db.add(log)
    db.flush()

    if not is_valid:
        _record_validation_error(
            db,
            log_id=log.id,
            employee_id=employee_id,
            when=when,
            rule=rule or "unknown",
            description=msg or "Punch failed validation",
            severity="error",
        )

    return log


# ── Steps 5+6: POLICY ENGINE → FINAL RECORD ──────────────────────────

def compute_record_for_day(
    db: Session, employee_id: int, on: date_t,
) -> Optional[AttendanceRecord]:
    """(Re)compute the AttendanceRecord for an employee + date.

    Order of precedence:
      1. Holiday on that date          -> status='holiday'
      2. Weekly off for that shift     -> status='holiday' (treated like holiday)
      3. Approved leave covers date    -> status='on_leave'
      4. No punches                    -> status='absent' (raises exception)
      5. Has punches                   -> compute hours, apply grace,
                                          status in {present, late, half_day}
    """
    emp = db.get(Employee, employee_id)
    if not emp:
        return None

    shift = get_employee_shift(db, employee_id, on)
    policy = get_policy_for_shift(db, shift.id if shift else None)

    # Pull any existing record (we update in place to keep id stable).
    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee_id, AttendanceRecord.date == on)
        .first()
    )
    if rec is None:
        rec = AttendanceRecord(
            id=_next_record_id(db),
            employee_id=employee_id,
            date=on,
        )
        db.add(rec)

    rec.shift_id = shift.id if shift else None

    # 1. Holiday
    hol = is_holiday(db, on)
    if hol:
        rec.status = "holiday"
        rec.check_in_time = None
        rec.check_out_time = None
        rec.working_hours = 0.0
        rec.late_minutes = 0
        rec.early_checkout_mins = 0
        rec.overtime_hours = 0.0
        rec.lop_applied = False
        return rec

    # 2. Weekly off
    if is_weekly_off(shift, on):
        rec.status = "holiday"
        rec.check_in_time = None
        rec.check_out_time = None
        rec.working_hours = 0.0
        rec.late_minutes = 0
        rec.early_checkout_mins = 0
        rec.overtime_hours = 0.0
        rec.lop_applied = False
        return rec

    # 3. Approved leave overlay
    leave = approved_leave_for(db, employee_id, on)
    if leave:
        rec.status = "on_leave"
        rec.leave_request_id = leave.id
        rec.lop_applied = False
        return rec

    # 4 + 5. Compute from raw logs.
    same_day_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.is_valid.is_(True),
        )
        .all()
    )
    same_day_logs = [l for l in same_day_logs if l.punch_timestamp and l.punch_timestamp.date() == on]
    same_day_logs.sort(key=lambda l: l.punch_timestamp)

    check_ins  = [l for l in same_day_logs if l.punch_type == "check_in"]
    check_outs = [l for l in same_day_logs if l.punch_type == "check_out"]

    if not check_ins:
        rec.status = "absent"
        rec.check_in_time = None
        rec.check_out_time = None
        rec.working_hours = 0.0
        rec.late_minutes = 0
        rec.early_checkout_mins = 0
        rec.overtime_hours = 0.0
        rec.lop_applied = True
        rec.lop_type = "absent_without_leave"
        return rec

    first_in = check_ins[0].punch_timestamp.time()
    last_out = check_outs[-1].punch_timestamp.time() if check_outs else None

    rec.check_in_time = first_in
    rec.check_out_time = last_out

    hours = _hours_between(first_in, last_out) if last_out else 0.0
    # Subtract policy break duration if it fits in the worked window.
    if shift and shift.break_duration_mins and hours > 0:
        hours = max(0.0, hours - (shift.break_duration_mins / 60.0))
    rec.working_hours = round(hours, 2)

    # Late minutes vs shift start + grace
    late_mins = 0
    if shift and shift.start_time:
        diff = _minutes_between(shift.start_time, first_in)
        grace = shift.grace_period_mins or 0
        late_mins = max(0, diff - grace)
    rec.late_minutes = late_mins

    # Early checkout vs shift end
    early_mins = 0
    if shift and shift.end_time and last_out:
        diff = _minutes_between(last_out, shift.end_time)
        early_mins = max(0, diff)
    rec.early_checkout_mins = early_mins

    # Overtime
    overtime = 0.0
    if policy and policy.overtime_threshold_hours and hours > policy.overtime_threshold_hours:
        overtime = round(hours - policy.overtime_threshold_hours, 2)
    rec.overtime_hours = overtime

    # Final status
    full_day = (policy.min_working_hours_full_day if policy else 8.0) or 8.0
    half_day = (policy.min_working_hours_half_day if policy else 4.0) or 4.0
    late_threshold = (policy.late_deduction_after_mins if policy else 30) or 30

    is_today = (on == date_t.today())
    has_checkout = last_out is not None

    if not has_checkout and is_today:
        # Open check-in earlier today, no check-out yet — show as PRESENT
        # (in-progress) not absent. The status will firm up once they punch out
        # or after the daily processing job re-runs at end of day.
        rec.status = "late" if late_mins > late_threshold else "present"
        rec.lop_applied = False
        rec.lop_type = None
    elif not has_checkout and not is_today:
        # Past day with check-in but no check-out — counts as missed checkout.
        rec.status = "absent"
        rec.lop_applied = True
        rec.lop_type = "no_checkout"
    elif hours < half_day:
        rec.status = "absent"
        rec.lop_applied = True
        rec.lop_type = "short_hours"
    elif hours < full_day:
        rec.status = "half_day"
        rec.lop_applied = True
        rec.lop_type = "half_day"
    elif late_mins > late_threshold:
        rec.status = "late"
        rec.lop_applied = False
    else:
        rec.status = "present"
        rec.lop_applied = False

    return rec


# ── Step 7: EXCEPTION DETECTION ──────────────────────────────────────

def detect_exceptions_for_record(
    db: Session, rec: AttendanceRecord,
) -> list[AttendanceException]:
    """Inspect a single record and write AttendanceException rows for any
    anomalies. Idempotent: deletes prior un-resolved exceptions for the
    same record before re-creating."""
    out: list[AttendanceException] = []
    if not rec or not rec.id:
        return out

    # Wipe prior open exceptions to avoid duplicates on re-runs.
    db.query(AttendanceException).filter(
        AttendanceException.attendance_record_id == rec.id,
        AttendanceException.is_resolved.is_(False),
    ).delete(synchronize_session=False)

    def _add(kind: str, desc: str):
        e = AttendanceException(
            id=_next_exception_id(db),
            attendance_record_id=rec.id,
            employee_id=rec.employee_id,
            date=rec.date,
            exception_type=kind,
            description=desc[:500],
            is_resolved=False,
        )
        db.add(e)
        out.append(e)

    if rec.status == "absent" and (rec.lop_type or "") == "no_checkout":
        _add("missing_checkout", "Check-in recorded but no check-out for the day.")
    if rec.status == "absent" and (rec.lop_type or "") == "absent_without_leave":
        _add("absent_without_leave", "No punches and no approved leave for the day.")
    if rec.status == "absent" and (rec.lop_type or "") == "short_hours":
        _add("short_hours", f"Worked only {rec.working_hours} h — below half-day threshold.")
    if rec.status in {"present", "late", "half_day"} and (rec.late_minutes or 0) > 0:
        _add("late_arrival", f"Late by {rec.late_minutes} mins.")
    if rec.status in {"present", "late", "half_day"} and (rec.early_checkout_mins or 0) > 30:
        _add("early_checkout", f"Left {rec.early_checkout_mins} mins before shift end.")

    return out


def process_day(
    db, employee_id: int, on,
    *, with_exceptions: bool = True,
):
    """One-call helper: compute the day's record AND its exceptions."""
    rec = compute_record_for_day(db, employee_id, on)
    db.flush()
    if with_exceptions and rec is not None:
        detect_exceptions_for_record(db, rec)
    return rec
