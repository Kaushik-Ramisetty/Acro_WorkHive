"""Timesheet routes — implements steps 12–16 of the workflow diagram.

Endpoints:

  GET    /timesheet/projects                — projects assigned via dept / manager
  GET    /timesheet/tasks                   — tasks for a project
  POST   /timesheet                         — create draft + initial entries
  PATCH  /timesheet/{id}                    — replace entries (only when draft)
  POST   /timesheet/{id}/submit             — employee submits (status=pending_review)
  GET    /timesheet                         — list (employee=mine, manager=team, admin=all)
  GET    /timesheet/{id}                    — detail (with entries)
  POST   /timesheet/{id}/review             — manager approve/reject; approve→lock
  POST   /timesheet/{id}/payroll-sync       — admin: sync to payroll_attendance_summary
"""
from __future__ import annotations

from datetime import date as date_t, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from utils.time_utils import now_utc
from app.db.session import get_db
from app.models import (
    AttendanceRecord, Employee, PayrollAttendanceSummary, Project, Task,
    Timesheet, TimesheetEntry, TimesheetPayrollSync,
)
from app.schemas.timesheet import (
    ProjectOut, TaskOut, TimesheetCreateIn, TimesheetDetailOut, TimesheetEntryIn,
    TimesheetEntryOut, TimesheetOut, TimesheetReviewIn,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify


router = APIRouter(prefix="/timesheet", tags=["timesheet"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _next_ts_id(db: Session) -> str:
    n = db.query(Timesheet).count() + 1
    cand = f"TS{n:06d}"
    while db.get(Timesheet, cand) is not None:
        n += 1
        cand = f"TS{n:06d}"
    return cand


def _next_te_id(db: Session) -> str:
    n = db.query(TimesheetEntry).count() + 1
    cand = f"TE{n:07d}"
    while db.get(TimesheetEntry, cand) is not None:
        n += 1
        cand = f"TE{n:07d}"
    return cand


def _can_manage(actor: Employee, employee_id: int, db: Session) -> bool:
    role = _role(actor)
    if role == "admin":
        return True
    if role == "manager":
        target = db.get(Employee, employee_id)
        return bool(target and target.reporting_manager_id == actor.id)
    return False


def _ensure_owner_or_manager(actor: Employee, ts: Timesheet, db: Session) -> None:
    if actor.id == ts.employee_id:
        return
    if _can_manage(actor, ts.employee_id, db):
        return
    raise HTTPException(status_code=403, detail="Not allowed.")


# ── Projects + tasks (read) ──────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List active projects available to the user. Admin sees all; others see
    projects in their department or where they're the project manager."""
    role = _role(user)
    q = db.query(Project)
    if role != "admin":
        q = q.filter(
            (Project.department_id == user.department_id) |
            (Project.project_manager_id == user.id)
        )
    rows = q.order_by(Project.name).all()
    return [ProjectOut.model_validate(p) for p in rows]


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    q = db.query(Task)
    if project_id:
        q = q.filter(Task.project_id == project_id)
    rows = q.order_by(Task.name).all()
    return [TaskOut.model_validate(t) for t in rows]


# ── Step 12: Timesheet creation + edit (draft) ───────────────────────

def _replace_entries(db: Session, ts: Timesheet, entries: list[TimesheetEntryIn], employee_id: int) -> float:
    """Wipe + re-insert entries. Returns the total hours."""
    db.query(TimesheetEntry).filter(TimesheetEntry.timesheet_id == ts.id).delete(synchronize_session=False)
    db.flush()  # ensure deletes hit before counting for the new IDs
    counter = [db.query(TimesheetEntry).count()]
    def _next():
        counter[0] += 1
        cand = f"TE{counter[0]:07d}"
        while db.get(TimesheetEntry, cand) is not None:
            counter[0] += 1
            cand = f"TE{counter[0]:07d}"
        return cand
    total = 0.0
    for e in entries:
        if e.logged_hours is None or e.logged_hours < 0:
            raise HTTPException(status_code=400, detail="logged_hours must be >= 0")
        if e.logged_hours > 24:
            raise HTTPException(status_code=400, detail="logged_hours cannot exceed 24 per entry")
        if not (ts.period_start <= e.entry_date <= ts.period_end):
            raise HTTPException(
                status_code=400,
                detail=f"Entry date {e.entry_date} is outside the timesheet period.",
            )
        db.add(TimesheetEntry(
            id=_next(),
            timesheet_id=ts.id,
            employee_id=employee_id,
            entry_date=e.entry_date,
            project_id=e.project_id,
            task_id=e.task_id,
            logged_hours=float(e.logged_hours),
            description=e.description,
            is_manual_entry=bool(e.is_manual_entry),
            source="manual" if e.is_manual_entry else "auto_fetch",
            attendance_record_id=e.attendance_record_id,
        ))
        total += float(e.logged_hours)
    return round(total, 2)


@router.post("", response_model=TimesheetDetailOut, status_code=201)
def create_timesheet(
    payload: TimesheetCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=400, detail="period_end must be >= period_start.")

    ts = Timesheet(
        id=_next_ts_id(db),
        employee_id=user.id,
        period_type=payload.period_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status="draft",
        is_locked=False,
    )
    db.add(ts)
    db.flush()
    total = _replace_entries(db, ts, payload.entries, user.id)
    ts.total_logged_hours = total

    write_audit(
        db, actor_id=user.id, action="timesheet_create",
        target_table="timesheets", target_id=ts.id,
        new_value={"period": [str(ts.period_start), str(ts.period_end)], "hours": total},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)
    out = TimesheetDetailOut.model_validate(ts)
    out.entries = [TimesheetEntryOut.model_validate(e) for e in ts.entries]
    return out


@router.patch("/{ts_id}", response_model=TimesheetDetailOut)
def edit_timesheet(
    ts_id: str,
    payload: TimesheetCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    if ts.employee_id != user.id and _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Not allowed.")
    if ts.is_locked:
        raise HTTPException(status_code=400, detail="Timesheet is locked.")
    if (ts.status or "").lower() not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit a {ts.status} timesheet.")

    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=400, detail="period_end must be >= period_start.")
    ts.period_type = payload.period_type
    ts.period_start = payload.period_start
    ts.period_end = payload.period_end
    if (ts.status or "").lower() == "rejected":
        ts.status = "draft"     # editing a rejected sheet returns it to draft
    total = _replace_entries(db, ts, payload.entries, ts.employee_id)
    ts.total_logged_hours = total

    write_audit(
        db, actor_id=user.id, action="timesheet_edit",
        target_table="timesheets", target_id=ts.id,
        new_value={"hours": total},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)
    out = TimesheetDetailOut.model_validate(ts)
    out.entries = [TimesheetEntryOut.model_validate(e) for e in ts.entries]
    return out


# ── Step 13: Submission ──────────────────────────────────────────────

@router.post("/{ts_id}/submit", response_model=TimesheetOut)
def submit_timesheet(
    ts_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    if ts.employee_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can submit.")
    if (ts.status or "").lower() not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Cannot submit a {ts.status} timesheet.")
    if not ts.entries:
        raise HTTPException(status_code=400, detail="Cannot submit an empty timesheet.")

    ts.status = "pending_review"
    ts.submitted_at = now_utc()

    # Notify the reporting manager.
    if user.reporting_manager_id:
        notify(
            db,
            recipient_id=user.reporting_manager_id,
            type_="timesheet_submitted",
            title=f"Timesheet from {user.full_name}",
            body=f"{ts.period_start} → {ts.period_end} ({ts.total_logged_hours or 0} h)",
            reference_table="timesheets", reference_id=ts.id,
        )

    write_audit(
        db, actor_id=user.id, action="timesheet_submit",
        target_table="timesheets", target_id=ts.id,
        old_value={"status": "draft"}, new_value={"status": "pending_review"},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(ts)
    return TimesheetOut.model_validate(ts)


# ── List + detail ────────────────────────────────────────────────────

@router.get("", response_model=list[TimesheetOut])
def list_timesheets(
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = _role(user)
    q = db.query(Timesheet)
    if role == "admin":
        if employee_id is not None:
            q = q.filter(Timesheet.employee_id == employee_id)
    elif role == "manager":
        sub = db.query(Employee.id).filter(Employee.reporting_manager_id == user.id)
        # Manager sees their reports + their own.
        if employee_id is not None:
            target = db.get(Employee, employee_id)
            if not target or (target.reporting_manager_id != user.id and target.id != user.id):
                raise HTTPException(status_code=403, detail="Not in your team.")
            q = q.filter(Timesheet.employee_id == employee_id)
        else:
            q = q.filter((Timesheet.employee_id.in_(sub)) | (Timesheet.employee_id == user.id))
    else:
        q = q.filter(Timesheet.employee_id == user.id)

    if status:
        q = q.filter(Timesheet.status == status.lower())
    rows = q.order_by(Timesheet.period_start.desc()).limit(200).all()
    return [TimesheetOut.model_validate(r) for r in rows]


@router.get("/{ts_id}", response_model=TimesheetDetailOut)
def get_timesheet(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    _ensure_owner_or_manager(user, ts, db)
    out = TimesheetDetailOut.model_validate(ts)
    out.entries = [TimesheetEntryOut.model_validate(e) for e in ts.entries]
    return out


# ── Step 14 + 15: Manager review + locking ───────────────────────────

@router.post("/{ts_id}/review", response_model=TimesheetOut)
def review_timesheet(
    ts_id: str,
    payload: TimesheetReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    role = _role(user)
    if role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager or admin only.")
    target = db.get(Employee, ts.employee_id)
    if role == "manager" and (not target or target.reporting_manager_id != user.id):
        raise HTTPException(status_code=403, detail="Not in your team.")
    if (ts.status or "").lower() != "pending_review":
        raise HTTPException(status_code=400, detail=f"Timesheet is in {ts.status} state.")

    decision = payload.decision.lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject.")

    old = {"status": ts.status}
    if decision == "approve":
        ts.status = "approved"
        ts.is_locked = True             # Step 15: lock on approval
        ts.locked_at = now_utc()
    else:
        ts.status = "rejected"
        ts.is_locked = False

    ts.reviewed_by = user.id
    ts.review_comment = payload.review_comment
    ts.reviewed_at = now_utc()

    notify(
        db,
        recipient_id=ts.employee_id,
        type_="timesheet_review",
        title=f"Timesheet {ts.status}",
        body=(payload.review_comment or "")[:480] or f"Your timesheet was {ts.status}.",
        reference_table="timesheets", reference_id=ts.id,
    )

    write_audit(
        db, actor_id=user.id, action=f"timesheet_{ts.status}",
        target_table="timesheets", target_id=ts.id,
        old_value=old, new_value={"status": ts.status, "comment": payload.review_comment},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(ts)
    return TimesheetOut.model_validate(ts)


# ── Step 16: Payroll sync ────────────────────────────────────────────

def _next_tps_id(db: Session) -> str:
    n = db.query(TimesheetPayrollSync).count() + 1
    cand = f"TPS{n:05d}"
    while db.get(TimesheetPayrollSync, cand) is not None:
        n += 1
        cand = f"TPS{n:05d}"
    return cand


@router.post("/{ts_id}/payroll-sync")
def payroll_sync(
    ts_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Compare timesheet hours to attendance hours for the same period and
    record a TimesheetPayrollSync row. Admin-only — final pre-payroll step."""
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    if (ts.status or "").lower() != "approved":
        raise HTTPException(status_code=400, detail="Only approved timesheets can be synced.")

    # Sum approved attendance working hours for the same period.
    att_total = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == ts.employee_id,
            AttendanceRecord.date >= ts.period_start,
            AttendanceRecord.date <= ts.period_end,
        )
        .all()
    )
    att_hours = round(sum((r.working_hours or 0.0) for r in att_total), 2)
    ts_hours = float(ts.total_logged_hours or 0.0)
    variance = round(ts_hours - att_hours, 2)
    has_mismatch = abs(variance) > 0.5

    # Find the matching payroll summary (best-effort).
    pas = (
        db.query(PayrollAttendanceSummary)
        .filter(
            PayrollAttendanceSummary.employee_id == ts.employee_id,
            PayrollAttendanceSummary.year == ts.period_start.year,
        )
        .first()
    )

    row = TimesheetPayrollSync(
        id=_next_tps_id(db),
        employee_id=ts.employee_id,
        month=ts.period_start.strftime("%B"),
        year=ts.period_start.year,
        timesheet_id=ts.id,
        payroll_summary_id=pas.id if pas else None,
        timesheet_hours=ts_hours,
        attendance_hours=att_hours,
        variance_hours=variance,
        has_mismatch=has_mismatch,
        mismatch_reason=(f"Variance {variance} h" if has_mismatch else None),
    )
    db.add(row)

    write_audit(
        db, actor_id=user.id, action="timesheet_payroll_sync",
        target_table="timesheet_payroll_sync", target_id=row.id,
        new_value={"variance": variance, "has_mismatch": has_mismatch},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(row)
    return {
        "id": row.id,
        "timesheet_hours": ts_hours,
        "attendance_hours": att_hours,
        "variance_hours": variance,
        "has_mismatch": has_mismatch,
    }
