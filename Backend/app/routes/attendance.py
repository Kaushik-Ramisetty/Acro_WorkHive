"""Attendance routes - implements the workflow diagram end-to-end:

  /attendance/check-in            (employee)
  /attendance/check-out           (employee)
  /attendance/today               (employee - today's status)
  /attendance/logs                (employee/manager/admin - raw punches)
  /attendance/records             (employee/manager/admin - processed records)
  /attendance/process             (admin - re-run policy engine)
  /attendance/regularization      (employee - submit, list)
  /attendance/regularization/{id}/review  (admin - approve / reject)
  /attendance                     (admin/manager - legacy mark)
"""
from __future__ import annotations

import logging
from datetime import date as date_t, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from utils.time_utils import now_utc
from app.db.session import get_db
from app.models import (
    Attendance, AttendanceException, AttendanceLog, AttendanceRecord,
    CompOffCredit, Employee, OvertimeRecord, RegularizationRequest,
    Timesheet, TimesheetEntry,
)
from app.models.attendance_records import WeeklyOffChangeRequest
from app.schemas.attendance import (
    AdminAttOverrideIn, AttendanceExceptionOut, AttendanceLogOut,
    AttendanceRecordOut, CheckInResponse,
    CompOffRequestIn, CompOffRequestOut,
    OvertimeRequestIn, OvertimeRequestOut,
    PunchIn, RegularizationCreateIn, RegularizationOut,
    RegularizationReviewIn, TodayStatusOut,
    WeeklyOffChangeRequestIn, WeeklyOffChangeRequestOut,
)
from app.schemas.leave import AttendanceMarkIn, AttendanceOut
from app.services.attendance_engine import (
    create_punch, process_day, recompute_from_check_times,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many


router = APIRouter(prefix="/attendance", tags=["attendance"])

logger = logging.getLogger("hrms.attendance")


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _can_view_employee(actor: Employee, employee_id: int, db: Session) -> bool:
    role = _role(actor)
    if role == "admin":
        return True
    if role == "manager":
        target = db.get(Employee, employee_id)
        return bool(target and target.reporting_manager_id == actor.id)
    return actor.id == employee_id


def _next_reg_id(db: Session) -> str:
    n = db.query(RegularizationRequest).count() + 1
    candidate = f"RR{n:04d}"
    while db.get(RegularizationRequest, candidate) is not None:
        n += 1
        candidate = f"RR{n:04d}"
    return candidate


def _next_ts_id_att(db: Session) -> str:
    """Generate the next sequential Timesheet ID (TS000001 style)."""
    n = db.query(Timesheet).count() + 1
    candidate = f"TS{n:06d}"
    while db.get(Timesheet, candidate) is not None:
        n += 1
        candidate = f"TS{n:06d}"
    return candidate


def _next_te_id_att(db: Session) -> str:
    """Generate the next sequential TimesheetEntry ID (TE0000001 style)."""
    n = db.query(TimesheetEntry).count() + 1
    candidate = f"TE{n:07d}"
    while db.get(TimesheetEntry, candidate) is not None:
        n += 1
        candidate = f"TE{n:07d}"
    return candidate


def auto_create_timesheet_entry(db: Session, employee_id: int, entry_date) -> None:
    """Sync attendance hours into a timesheet entry for client_site employees.

    Called after every successful check-out and after regularization approval.

    Rules:
    - Only runs when employee.employee_type == 'client_site'.
    - Creates a weekly (Mon–Sun) draft timesheet if one does not exist yet.
    - Upserts a TimesheetEntry with working_hours from the AttendanceRecord.
    - Recalculates the timesheet's total_logged_hours.
    - Skips silently when the timesheet is locked or in a non-editable status.
    - All errors are caught and logged; never raises to the caller.
    """
    try:
        emp = db.get(Employee, employee_id)
        if not emp or (emp.employee_type or "").lower() != "client_site":
            return

        # Mon–Sun week bounds for the given date
        wd = entry_date.weekday()          # Monday = 0, Sunday = 6
        week_start = entry_date - timedelta(days=wd)
        week_end   = week_start + timedelta(days=6)

        # Fetch the attendance record to get working_hours
        rec = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date        == entry_date,
            )
            .first()
        )
        logged_hours = float(rec.working_hours or 0.0) if rec else 0.0
        if logged_hours <= 0:
            return

        # Find the draft timesheet for this week (with advisory lock), or create one
        try:
            ts = (
                db.query(Timesheet)
                .filter(
                    Timesheet.employee_id  == employee_id,
                    Timesheet.period_start == week_start,
                    Timesheet.period_end   == week_end,
                )
                .with_for_update()
                .first()
            )
        except Exception:
            # Fallback for dialects that don't support SELECT FOR UPDATE (e.g. SQLite in some modes)
            ts = (
                db.query(Timesheet)
                .filter(
                    Timesheet.employee_id  == employee_id,
                    Timesheet.period_start == week_start,
                    Timesheet.period_end   == week_end,
                )
                .first()
            )

        if ts is None:
            # Try to create; handle concurrent duplicate via savepoint
            try:
                sp = db.begin_nested()
                ts = Timesheet(
                    id=_next_ts_id_att(db),
                    employee_id=employee_id,
                    period_type="weekly",
                    period_start=week_start,
                    period_end=week_end,
                    status="draft",
                    is_locked=False,
                    total_logged_hours=0.0,
                )
                db.add(ts)
                sp.commit()
            except IntegrityError:
                sp.rollback()
                ts = (
                    db.query(Timesheet)
                    .filter(
                        Timesheet.employee_id  == employee_id,
                        Timesheet.period_start == week_start,
                        Timesheet.period_end   == week_end,
                    )
                    .first()
                )
                if ts is None:
                    logger.warning(
                        "auto_create_timesheet_entry: cannot find/create TS "
                        "for emp=%s week=%s", employee_id, week_start,
                    )
                    return

        # Only write to draft / rejected (unlocked) timesheets
        if ts.is_locked or (ts.status or "draft") not in {"draft", "rejected"}:
            logger.debug(
                "auto_create_timesheet_entry: skipping non-editable TS %s (status=%s) "
                "for emp=%s", ts.id, ts.status, employee_id,
            )
            return

        # Upsert the timesheet entry for this date
        te = (
            db.query(TimesheetEntry)
            .filter(
                TimesheetEntry.timesheet_id == ts.id,
                TimesheetEntry.employee_id  == employee_id,
                TimesheetEntry.entry_date   == entry_date,
            )
            .first()
        )
        if te is None:
            te = TimesheetEntry(
                id=_next_te_id_att(db),
                timesheet_id=ts.id,
                employee_id=employee_id,
                entry_date=entry_date,
                logged_hours=logged_hours,
                is_billable=True,
                source="attendance_sync",
                is_manual_entry=False,
                attendance_record_id=rec.id if rec else None,
            )
            db.add(te)
        else:
            te.logged_hours = logged_hours
            te.source = "attendance_sync"
            if rec:
                te.attendance_record_id = rec.id

        db.flush()

        # Recalculate total_logged_hours for the whole timesheet
        total = (
            db.query(func.sum(TimesheetEntry.logged_hours))
            .filter(TimesheetEntry.timesheet_id == ts.id)
            .scalar()
        ) or 0.0
        ts.total_logged_hours = float(total)
        db.flush()

        logger.info(
            "auto_create_timesheet_entry: synced %.2fh for emp=%s on %s → TS %s",
            logged_hours, employee_id, entry_date, ts.id,
        )
    except Exception as exc:
        logger.exception(
            "auto_create_timesheet_entry: unexpected error for emp=%s date=%s: %s",
            employee_id, entry_date, exc,
        )


def _do_punch(*, db: Session, request: Request, user: Employee, payload: PunchIn, punch_type: str) -> CheckInResponse:
    when = now_utc()
    log = create_punch(
        db,
        employee_id=user.id,
        punch_type=punch_type,
        when=when,
        device_info=payload.device_info,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        source=payload.source or "web",
    )
    rec = None
    if log.is_valid:
        rec = process_day(db, user.id, when.date(), with_exceptions=True)
        if punch_type == "check_in" and rec is not None and (rec.late_minutes or 0) > 0:
            notify(
                db, recipient_id=user.id, type_="late_arrival",
                title="Late arrival recorded",
                body=f"You checked in {rec.late_minutes} minutes after your shift start.",
                reference_table="attendance_records", reference_id=rec.id,
            )
        # Auto-sync hours into weekly timesheet for client_site employees
        if punch_type == "check_out":
            auto_create_timesheet_entry(db, user.id, when.date())
    write_audit(
        db, actor_id=user.id, action=punch_type,
        target_table="attendance_logs", target_id=log.id,
        new_value={"is_valid": log.is_valid, "rule": log.validation_rule},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(log)
    if rec is not None: db.refresh(rec)
    msg = (
        "Check-in recorded." if punch_type == "check_in" and log.is_valid else
        "Check-out recorded." if punch_type == "check_out" and log.is_valid else
        log.validation_error or "Punch rejected."
    )
    return CheckInResponse(
        log=AttendanceLogOut.model_validate(log),
        record=AttendanceRecordOut.model_validate(rec) if rec else None,
        message=msg,
    )


@router.post("/check-in", response_model=CheckInResponse, status_code=201)
def check_in(payload: PunchIn, request: Request, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)) -> CheckInResponse:
    return _do_punch(db=db, request=request, user=user, payload=payload, punch_type="check_in")


@router.post("/check-out", response_model=CheckInResponse, status_code=201)
def check_out(payload: PunchIn, request: Request, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)) -> CheckInResponse:
    return _do_punch(db=db, request=request, user=user, payload=payload, punch_type="check_out")


@router.get("/today", response_model=TodayStatusOut)
def my_today(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)) -> TodayStatusOut:
    today = now_utc().date()
    logs_today = db.query(AttendanceLog).filter(AttendanceLog.employee_id == user.id).all()
    same_day = [l for l in logs_today if l.punch_timestamp and l.punch_timestamp.date() == today]
    same_day.sort(key=lambda l: l.punch_timestamp)
    has_in  = any(l.punch_type == "check_in"  and l.is_valid for l in same_day)
    has_out = any(l.punch_type == "check_out" and l.is_valid for l in same_day)
    last = same_day[-1] if same_day else None
    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == user.id, AttendanceRecord.date == today)
        .first()
    )
    return TodayStatusOut(
        today=today,
        has_checked_in=has_in,
        has_checked_out=has_out,
        last_punch=AttendanceLogOut.model_validate(last) if last else None,
        record=AttendanceRecordOut.model_validate(rec) if rec else None,
    )


@router.get("/logs", response_model=list[AttendanceLogOut])
def list_logs(employee_id: Optional[int] = Query(None), start: Optional[date_t] = Query(None), end: Optional[date_t] = Query(None), db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    eid = employee_id if employee_id is not None else user.id
    if not _can_view_employee(user, eid, db):
        raise HTTPException(status_code=403, detail="Not allowed.")
    q = db.query(AttendanceLog).filter(AttendanceLog.employee_id == eid)
    if start: q = q.filter(AttendanceLog.punch_timestamp >= datetime.combine(start, datetime.min.time()))
    if end:   q = q.filter(AttendanceLog.punch_timestamp <= datetime.combine(end + timedelta(days=1), datetime.min.time()))
    rows = q.order_by(AttendanceLog.punch_timestamp.desc()).limit(500).all()
    return [AttendanceLogOut.model_validate(r) for r in rows]


@router.get("/records", response_model=list[AttendanceRecordOut])
def list_records(employee_id: Optional[int] = Query(None), start: Optional[date_t] = Query(None), end: Optional[date_t] = Query(None), db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    role = _role(user)
    q = db.query(AttendanceRecord)
    if role == "admin":
        if employee_id is not None: q = q.filter(AttendanceRecord.employee_id == employee_id)
    elif role == "manager":
        if employee_id is not None:
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not in your team.")
            q = q.filter(AttendanceRecord.employee_id == employee_id)
        else:
            sub = db.query(Employee.id).filter(Employee.reporting_manager_id == user.id)
            q = q.filter(AttendanceRecord.employee_id.in_(sub))
    else:
        q = q.filter(AttendanceRecord.employee_id == user.id)
    if start: q = q.filter(AttendanceRecord.date >= start)
    if end:   q = q.filter(AttendanceRecord.date <= end)
    rows = q.order_by(AttendanceRecord.date.desc()).limit(400).all()
    return [AttendanceRecordOut.model_validate(r) for r in rows]


@router.get("/exceptions", response_model=list[AttendanceExceptionOut])
def list_exceptions(employee_id: Optional[int] = Query(None), only_open: bool = Query(True), db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    role = _role(user)
    q = db.query(AttendanceException)
    if role == "admin":
        if employee_id is not None: q = q.filter(AttendanceException.employee_id == employee_id)
    elif role == "manager":
        sub = db.query(Employee.id).filter(Employee.reporting_manager_id == user.id)
        q = q.filter(AttendanceException.employee_id.in_(sub))
    else:
        q = q.filter(AttendanceException.employee_id == user.id)
    if only_open:
        q = q.filter(AttendanceException.is_resolved.is_(False))
    rows = q.order_by(AttendanceException.date.desc()).limit(300).all()
    return [AttendanceExceptionOut.model_validate(r) for r in rows]


@router.post("/process", response_model=AttendanceRecordOut)
def admin_process_day(employee_id: int, on: date_t, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    rec = process_day(db, employee_id, on, with_exceptions=True)
    if not rec:
        raise HTTPException(status_code=404, detail="Employee not found.")
    db.commit(); db.refresh(rec)
    return AttendanceRecordOut.model_validate(rec)


@router.post("/regularization", response_model=RegularizationOut, status_code=201)
def submit_regularization(payload: RegularizationCreateIn, request: Request, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == user.id, AttendanceRecord.date == payload.date)
        .first()
    )
    rr = RegularizationRequest(
        id=_next_reg_id(db),
        employee_id=user.id,
        attendance_record_id=rec.id if rec else None,
        date=payload.date,
        regularization_type=payload.regularization_type,
        requested_check_in=payload.requested_check_in,
        requested_check_out=payload.requested_check_out,
        reason=payload.reason,
        attachment_url=payload.attachment_url,
        status="pending",
    )
    db.add(rr)
    admins = db.query(Employee).join(Employee.role).filter(
        Employee.is_deleted.is_(False), Employee.employment_status == "active"
    ).all()
    admin_ids = [e.id for e in admins if e.role and e.role.name.lower() == "admin"]
    notify_many(
        db, admin_ids, type_="regularization_pending",
        title=f"Regularization request from {user.full_name}",
        body=f"Date {payload.date} - {payload.regularization_type}",
        reference_table="regularization_requests", reference_id=rr.id,
    )
    write_audit(
        db, actor_id=user.id, action="regularization_submit",
        target_table="regularization_requests", target_id=rr.id,
        new_value={"status": "pending", "type": payload.regularization_type, "date": str(payload.date)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(rr)
    return RegularizationOut.model_validate(rr)


@router.get("/regularization", response_model=list[RegularizationOut])
def list_regularizations(status: Optional[str] = Query(None), employee_id: Optional[int] = Query(None), db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    role = _role(user)
    q = db.query(RegularizationRequest)
    if role == "admin":
        if employee_id is not None: q = q.filter(RegularizationRequest.employee_id == employee_id)
    elif role == "manager":
        sub = db.query(Employee.id).filter(Employee.reporting_manager_id == user.id)
        q = q.filter(RegularizationRequest.employee_id.in_(sub))
    else:
        q = q.filter(RegularizationRequest.employee_id == user.id)
    if status:
        q = q.filter(RegularizationRequest.status == status.lower())
    rows = q.order_by(RegularizationRequest.created_at.desc()).limit(200).all()
    return [RegularizationOut.model_validate(r) for r in rows]


@router.post("/regularization/{rr_id}/review", response_model=RegularizationOut)
def review_regularization(rr_id: str, payload: RegularizationReviewIn, request: Request, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    rr = db.get(RegularizationRequest, rr_id)
    if not rr:
        raise HTTPException(status_code=404, detail="Regularization not found.")
    if rr.status != "pending":
        raise HTTPException(status_code=400, detail=f"Already {rr.status}.")
    new_status = payload.status.lower()
    if new_status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="status must be approved or rejected.")
    old_value = {"status": rr.status}
    rr.status = new_status
    rr.reviewed_by = user.id
    rr.review_comment = payload.review_comment
    rr.reviewed_at = now_utc()
    if new_status == "approved":
        rec = None
        if rr.attendance_record_id:
            rec = db.get(AttendanceRecord, rr.attendance_record_id)
        if rec is None and rr.date:
            rec = (
                db.query(AttendanceRecord)
                .filter(AttendanceRecord.employee_id == rr.employee_id, AttendanceRecord.date == rr.date)
                .first()
            )
        if rec is None and rr.date:
            from app.services.attendance_engine import _next_record_id
            rec = AttendanceRecord(id=_next_record_id(db), employee_id=rr.employee_id, date=rr.date)
            db.add(rec)
        if rec is not None:
            if rr.requested_check_in is not None:  rec.check_in_time = rr.requested_check_in
            if rr.requested_check_out is not None: rec.check_out_time = rr.requested_check_out
            rec.is_regularized = True
            rec.regularization_id = rr.id
            from app.services.attendance_engine import _hours_between
            if rec.check_in_time and rec.check_out_time:
                hrs = _hours_between(rec.check_in_time, rec.check_out_time)
                rec.working_hours = hrs
                if hrs >= 8.0:
                    rec.status = "present"; rec.lop_applied = False
                elif hrs >= 4.0:
                    rec.status = "half_day"; rec.lop_applied = True; rec.lop_type = "half_day"
                else:
                    rec.status = "absent"; rec.lop_applied = True; rec.lop_type = "short_hours"
            # Full policy engine recompute (derives status, working_hours, etc.)
            db.flush()
            recompute_from_check_times(db, rec)
            # Sync updated hours into the weekly timesheet for client_site employees
            auto_create_timesheet_entry(db, rr.employee_id, rr.date)
    notify(
        db, recipient_id=rr.employee_id, type_="regularization_update",
        title=f"Regularization {new_status}",
        body=f"Your regularization for {rr.date} was {new_status}.",
        reference_table="regularization_requests", reference_id=rr.id,
    )
    write_audit(
        db, actor_id=user.id, action=f"regularization_{new_status}",
        target_table="regularization_requests", target_id=rr.id,
        old_value=old_value, new_value={"status": new_status, "comment": payload.review_comment},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(rr)
    return RegularizationOut.model_validate(rr)


def _can_mark(actor: Employee, employee_id: int, db: Session) -> bool:
    role = _role(actor)
    if role == "admin":
        return True
    if role == "manager":
        target = db.get(Employee, employee_id)
        return bool(target and target.reporting_manager_id == actor.id)
    return False


@router.post("", response_model=AttendanceOut, status_code=201)
def mark_attendance(payload: AttendanceMarkIn, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    if not _can_mark(user, payload.employee_id, db):
        raise HTTPException(status_code=403, detail="Not allowed.")
    existing = (
        db.query(Attendance)
        .filter(Attendance.employee_id == payload.employee_id, Attendance.date == payload.date)
        .first()
    )
    if existing:
        existing.status = payload.status
        existing.note = payload.note
        existing.source = "manual"
        db.commit(); db.refresh(existing)
        return AttendanceOut.model_validate(existing)
    row = Attendance(
        employee_id=payload.employee_id, date=payload.date,
        status=payload.status, note=payload.note, source="manual",
    )
    db.add(row); db.commit(); db.refresh(row)
    return AttendanceOut.model_validate(row)


@router.get("", response_model=list[AttendanceOut])
def list_attendance(db: Session = Depends(get_db), user: Employee = Depends(get_current_user), employee_id: Optional[int] = Query(None), start: Optional[date_t] = Query(None), end: Optional[date_t] = Query(None)):
    role = _role(user)
    q = db.query(Attendance).join(Employee, Attendance.employee_id == Employee.id)
    if role == "admin":
        if employee_id is not None: q = q.filter(Attendance.employee_id == employee_id)
    elif role == "manager":
        if employee_id is not None:
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(status_code=403, detail="Not in your team.")
            q = q.filter(Attendance.employee_id == employee_id)
        else:
            q = q.filter(Employee.reporting_manager_id == user.id)
    else:
        q = q.filter(Attendance.employee_id == user.id)
    if start: q = q.filter(Attendance.date >= start)
    if end:   q = q.filter(Attendance.date <= end)
    rows = q.order_by(Attendance.date.desc(), Attendance.employee_id).all()
    return [AttendanceOut.model_validate(r) for r in rows]


# ─── Effective / weekly hours ─────────────────────────────────────────────────

def _build_effective_hours_payload(d: date_t, rec, placeholder_status=None) -> dict:
    """Build the effective-hours response dict for a single date + AttendanceRecord (or None)."""
    if rec is None:
        return {
            "date": str(d),
            "check_in": None,
            "check_out": None,
            "effective_hours": 0.0,
            "attendance_status": "NO_ATTENDANCE",
            "status": placeholder_status,
        }
    if rec.check_out_time is None:
        return {
            "date": str(d),
            "check_in": str(rec.check_in_time) if rec.check_in_time else None,
            "check_out": None,
            "effective_hours": 0.0,
            "attendance_status": "PENDING_CHECKOUT",
            "status": rec.status,
        }
    return {
        "date": str(d),
        "check_in": str(rec.check_in_time) if rec.check_in_time else None,
        "check_out": str(rec.check_out_time) if rec.check_out_time else None,
        "effective_hours": round(float(rec.working_hours or 0), 2),
        "attendance_status": "FINALIZED",
        "status": rec.status,
    }


@router.get("/effective-hours")
def effective_hours_for_date(
    date: date_t = Query(...),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Return effective working hours for a single date (logged-in employee).

    Response: { date, check_in, check_out, effective_hours, attendance_status }
    attendance_status: FINALIZED | PENDING_CHECKOUT | NO_ATTENDANCE
    """
    rec = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == user.id,
            AttendanceRecord.date == date,
        )
        .first()
    )
    return _build_effective_hours_payload(date, rec)


@router.get("/weekly-hours")
def weekly_effective_hours(
    week_start: date_t = Query(...),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Return effective working hours for all 7 days of the given week.

    week_start must be the Monday of the target week (ISO 8601 date string).
    Returns a list of 7 objects, one per day Mon-Sun.
    Each object: { date, check_in, check_out, effective_hours, attendance_status }
    """
    week_end = week_start + timedelta(days=6)
    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == user.id,
            AttendanceRecord.date >= week_start,
            AttendanceRecord.date <= week_end,
        )
        .all()
    )
    rec_map = {r.date: r for r in records}
    return [
        _build_effective_hours_payload(
            week_start + timedelta(days=i),
            rec_map.get(week_start + timedelta(days=i)),
        )
        for i in range(7)
    ]


# ─── Admin attendance override ────────────────────────────────────────────────

@router.patch("/admin/override")
def admin_override_attendance(
    payload: AdminAttOverrideIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Admin-only: set or clear an attendance_record status for a given employee + date.

    status=null -> Clear: sets DB status to 'absent' (removes any prior override).
    Writes to attendance_records only. Never touches attendance_logs.
    """
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")

    rec = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == payload.employee_id,
            AttendanceRecord.date == payload.date,
        )
        .first()
    )
    old_status = rec.status if rec else None

    if payload.status is None:
        if rec:
            rec.status = "absent"
    elif rec:
        rec.status = payload.status
    else:
        from app.services.attendance_engine import _next_record_id
        rec = AttendanceRecord(
            id=_next_record_id(db),
            employee_id=payload.employee_id,
            date=payload.date,
            status=payload.status,
            is_regularized=False,
            lop_applied=False,
        )
        db.add(rec)

    write_audit(
        db, actor_id=user.id, action="admin_override",
        target_table="attendance_records",
        target_id=rec.id if rec else "N/A",
        old_value={"status": old_status},
        new_value={"status": payload.status},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True, "employee_id": payload.employee_id,
            "date": str(payload.date), "status": payload.status}


# ─── Exception resolve ────────────────────────────────────────────────────────

@router.patch("/exceptions/{exc_id}/resolve")
def resolve_exception(
    exc_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Mark an attendance exception as resolved. Admin-only."""
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    exc = db.get(AttendanceException, exc_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found.")
    exc.is_resolved = True
    exc.resolved_at = now_utc()
    db.commit()
    return {"ok": True, "id": exc_id, "resolved_at": exc.resolved_at.isoformat()}


# ─── Regularization: employee's own view ─────────────────────────────────────

@router.get("/regularization/me", response_model=list[RegularizationOut])
def my_regularizations(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee's own regularization requests."""
    q = db.query(RegularizationRequest).filter(RegularizationRequest.employee_id == user.id)
    if status:
        q = q.filter(RegularizationRequest.status == status.lower())
    rows = q.order_by(RegularizationRequest.created_at.desc()).limit(200).all()
    return [RegularizationOut.model_validate(r) for r in rows]


# ─── ID helpers for new entities ─────────────────────────────────────────────

def _next_ot_id(db: Session) -> str:
    n = db.query(OvertimeRecord).count() + 1
    cand = f"OT{n:05d}"
    while db.query(OvertimeRecord).filter(OvertimeRecord.id == cand).first():
        n += 1; cand = f"OT{n:05d}"
    return cand


def _next_wo_id(db: Session) -> str:
    n = db.query(WeeklyOffChangeRequest).count() + 1
    cand = f"WO{n:05d}"
    while db.query(WeeklyOffChangeRequest).filter(WeeklyOffChangeRequest.id == cand).first():
        n += 1; cand = f"WO{n:05d}"
    return cand


# ─── Comp-Off self-service (employee) ────────────────────────────────────────

@router.post("/comp-off/request", response_model=CompOffRequestOut, status_code=201)
def request_comp_off(
    payload: CompOffRequestIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee requests comp-off for a weekend day they worked.

    Validates:
    - The date must be Saturday or Sunday.
    - An AttendanceRecord must exist with working_hours >= 4.
    - No existing pending/approved comp-off for the same day.
    """
    from app.services.comp_off_service import WEEKEND_COMP_OFF_MIN_HOURS
    worked_on = payload.worked_on
    if worked_on.weekday() not in (5, 6):
        raise HTTPException(status_code=400, detail="Comp-off is only available for weekend work (Saturday or Sunday).")

    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == user.id, AttendanceRecord.date == worked_on)
        .first()
    )
    if rec is None or (rec.working_hours or 0) < WEEKEND_COMP_OFF_MIN_HOURS:
        raise HTTPException(
            status_code=400,
            detail=f"No valid attendance record found for {worked_on} with at least {WEEKEND_COMP_OFF_MIN_HOURS}h worked.",
        )

    duplicate = (
        db.query(CompOffCredit)
        .filter(
            CompOffCredit.employee_id == user.id,
            CompOffCredit.worked_on == worked_on,
            CompOffCredit.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A comp-off request for this date already exists.")

    credit = CompOffCredit(
        employee_id=user.id,
        worked_on=worked_on,
        days=1,
        reason=payload.reason,
        status="pending",
        next_approver_role="manager",
        expires_on=worked_on + timedelta(days=90),
    )
    db.add(credit)
    db.commit()
    db.refresh(credit)

    admins = db.query(Employee).join(Employee.role).filter(
        Employee.is_deleted.is_(False), Employee.employment_status == "active"
    ).all()
    admin_ids = [e.id for e in admins if e.role and e.role.name.lower() == "admin"]
    notify_many(
        db, admin_ids, type_="comp_off_request",
        title="Comp-Off Request",
        body=f"Comp-off requested for {worked_on}.",
        reference_table="comp_off_credits",
        reference_id=str(credit.id),
    )
    db.commit()

    return CompOffRequestOut(
        id=credit.id,
        employee_id=credit.employee_id,
        worked_on=credit.worked_on,
        days=credit.days,
        reason=credit.reason,
        status=credit.status,
        next_approver_role=credit.next_approver_role,
        expires_on=credit.expires_on,
        rejection_reason=credit.rejection_reason,
        created_at=credit.created_at,
    )


@router.get("/comp-off", response_model=list[CompOffRequestOut])
def list_my_comp_off(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee's own comp-off credit history."""
    rows = (
        db.query(CompOffCredit)
        .filter(CompOffCredit.employee_id == user.id)
        .order_by(CompOffCredit.created_at.desc())
        .all()
    )
    return [
        CompOffRequestOut(
            id=r.id, employee_id=r.employee_id, worked_on=r.worked_on,
            days=r.days, reason=r.reason, status=r.status,
            next_approver_role=r.next_approver_role, expires_on=r.expires_on,
            rejection_reason=r.rejection_reason, created_at=r.created_at,
        )
        for r in rows
    ]


# ─── Overtime request (employee) ─────────────────────────────────────────────

@router.post("/overtime", response_model=OvertimeRequestOut, status_code=201)
def submit_overtime_request(
    payload: OvertimeRequestIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee submits an overtime approval request.

    Validates:
    - A valid AttendanceRecord must exist for the date.
    - No existing pending overtime request for the same date.
    """
    rec = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == user.id, AttendanceRecord.date == payload.date)
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=400, detail="No attendance record found for this date.")

    existing = (
        db.query(OvertimeRecord)
        .filter(
            OvertimeRecord.employee_id == user.id,
            OvertimeRecord.date == payload.date,
            OvertimeRecord.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="An overtime request for this date already exists.")

    ot = OvertimeRecord(
        id=_next_ot_id(db),
        employee_id=user.id,
        attendance_record_id=rec.id,
        date=payload.date,
        overtime_hours=payload.overtime_hours,
        overtime_type="daily",
        status="pending",
    )
    db.add(ot)
    db.commit()
    db.refresh(ot)

    admins2 = db.query(Employee).join(Employee.role).filter(
        Employee.is_deleted.is_(False), Employee.employment_status == "active"
    ).all()
    admin_ids2 = [e.id for e in admins2 if e.role and e.role.name.lower() == "admin"]
    notify_many(
        db, admin_ids2, type_="overtime_request",
        title="Overtime Request",
        body=f"Overtime approval requested for {payload.date} ({payload.overtime_hours}h).",
        reference_table="overtime_records",
        reference_id=ot.id,
    )
    db.commit()

    return OvertimeRequestOut.model_validate(ot)


@router.get("/overtime", response_model=list[OvertimeRequestOut])
def list_my_overtime(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee's own overtime records."""
    rows = (
        db.query(OvertimeRecord)
        .filter(OvertimeRecord.employee_id == user.id)
        .order_by(OvertimeRecord.date.desc())
        .all()
    )
    return [OvertimeRequestOut.model_validate(r) for r in rows]


# ─── Weekly-off change request (employee) ────────────────────────────────────

@router.post("/weekly-off-request", response_model=WeeklyOffChangeRequestOut, status_code=201)
def submit_weekly_off_request(
    payload: WeeklyOffChangeRequestIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee requests a change to their weekly-off day."""
    VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
    if payload.requested_weekly_off not in VALID_DAYS:
        raise HTTPException(status_code=400, detail=f"requested_weekly_off must be one of: {sorted(VALID_DAYS)}")

    existing_pending = (
        db.query(WeeklyOffChangeRequest)
        .filter(
            WeeklyOffChangeRequest.employee_id == user.id,
            WeeklyOffChangeRequest.status == "pending",
        )
        .first()
    )
    if existing_pending:
        raise HTTPException(status_code=409, detail="You already have a pending weekly-off change request.")

    from app.models.shift import EmployeeShift
    today = now_utc().date()
    emp_shift = (
        db.query(EmployeeShift)
        .filter(
            EmployeeShift.employee_id == user.id,
            EmployeeShift.effective_from <= today,
            or_(EmployeeShift.effective_to == None, EmployeeShift.effective_to >= today),  # noqa: E711
        )
        .order_by(EmployeeShift.effective_from.desc())
        .first()
    )
    current_off = None
    if emp_shift and emp_shift.shift_id:
        from app.models.shift import Shift
        shift = db.get(Shift, emp_shift.shift_id)
        if shift:
            current_off = shift.weekly_off_days

    req = WeeklyOffChangeRequest(
        id=_next_wo_id(db),
        employee_id=user.id,
        current_weekly_off=current_off,
        requested_weekly_off=payload.requested_weekly_off,
        effective_from=payload.effective_from,
        reason=payload.reason,
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    admins3 = db.query(Employee).join(Employee.role).filter(
        Employee.is_deleted.is_(False), Employee.employment_status == "active"
    ).all()
    admin_ids3 = [e.id for e in admins3 if e.role and e.role.name.lower() == "admin"]
    notify_many(
        db, admin_ids3, type_="weekly_off_request",
        title="Weekly-Off Change Request",
        body=f"Weekly-off change requested: {current_off or 'current'} -> {payload.requested_weekly_off}.",
        reference_table="weekly_off_change_requests",
        reference_id=req.id,
    )
    db.commit()

    return WeeklyOffChangeRequestOut.model_validate(req)


@router.get("/weekly-off-request", response_model=list[WeeklyOffChangeRequestOut])
def list_my_weekly_off_requests(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee's own weekly-off change requests."""
    rows = (
        db.query(WeeklyOffChangeRequest)
        .filter(WeeklyOffChangeRequest.employee_id == user.id)
        .order_by(WeeklyOffChangeRequest.created_at.desc())
        .all()
    )
    return [WeeklyOffChangeRequestOut.model_validate(r) for r in rows]
