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

from datetime import date as date_t, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from utils.time_utils import now_utc
from app.db.session import get_db
from app.models import (
    Attendance, AttendanceException, AttendanceLog, AttendanceRecord,
    Employee, RegularizationRequest,
)
from app.schemas.attendance import (
    AttendanceExceptionOut, AttendanceLogOut, AttendanceRecordOut,
    CheckInResponse, PunchIn, RegularizationCreateIn, RegularizationOut,
    RegularizationReviewIn, TodayStatusOut,
)
from app.schemas.leave import AttendanceMarkIn, AttendanceOut
from app.services.attendance_engine import (
    create_punch, process_day,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many


router = APIRouter(prefix="/attendance", tags=["attendance"])


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
