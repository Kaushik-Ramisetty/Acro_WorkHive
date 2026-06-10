"""HR-admin specific routes.

Endpoints:
  GET    /hr/timesheets              — list timesheets for client_site employees only
  GET    /hr/timesheets/summary      — count cards for HR dashboard
  GET    /hr/timesheets/export/csv   — export timesheet data as CSV
  GET    /hr/timesheets/{id}         — single timesheet detail (client_site only)
  GET    /hr/projects                — list active projects (for edit-timesheet dropdowns)
  GET    /hr/tasks                   — list tasks for a project (for edit-timesheet dropdowns)
  PUT    /hr/timesheets/{id}/entries — HR edits timesheet entries
  PATCH  /hr/employees/{id}/type     — Admin changes employee_type
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    AttendanceLog, AttendanceRecord, Department, Designation, Employee,
    Project, Task, Timesheet, TimesheetEntry, TimesheetPayrollSync,
)
from app.schemas.timesheet import HRTimesheetEntriesIn, HRTimesheetOut, ProjectOut, TaskOut, TimesheetDetailOut, TimesheetEntryOut
from app.services.audit_service import write_audit
from utils.time_utils import now_utc


router = APIRouter(prefix="/hr", tags=["hr"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _require_admin(user: Employee) -> None:
    if _role(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")


def _next_te_id(db: Session) -> str:
    n = db.query(TimesheetEntry).count() + 1
    cand = f"TE{n:07d}"
    while db.get(TimesheetEntry, cand) is not None:
        n += 1
        cand = f"TE{n:07d}"
    return cand


# ── GET /hr/timesheets ────────────────────────────────────────────────────────

@router.get("/timesheets", response_model=list[HRTimesheetOut])
def list_hr_timesheets(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List timesheets for client_site (T&M) employees only. Admin-only."""
    _require_admin(user)

    q = (
        db.query(Timesheet, Employee, Designation, Department)
        .join(Employee, Timesheet.employee_id == Employee.id)
        .outerjoin(Designation, Employee.designation_id == Designation.id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .filter(
            Employee.employee_type == "client_site",
            Employee.employment_status == "active",
            Employee.is_deleted.is_(False),
        )
    )
    if status:
        q = q.filter(Timesheet.status == status.lower())

    rows = q.order_by(Timesheet.updated_at.desc()).all()

    result = []
    for ts, emp, des, dep in rows:
        result.append(HRTimesheetOut(
            id=ts.id,
            employee_id=ts.employee_id,
            first_name=emp.first_name,
            last_name=emp.last_name,
            employee_code=emp.employee_code,
            designation_title=des.title if des else None,
            department_name=dep.name if dep else None,
            period_type=ts.period_type,
            period_start=ts.period_start,
            period_end=ts.period_end,
            total_logged_hours=ts.total_logged_hours,
            status=ts.status,
            submitted_at=ts.submitted_at,
            is_locked=ts.is_locked,
            has_mismatch=ts.has_mismatch,
            locked_at=ts.locked_at,
            client_approved_at=ts.client_approved_at,
            manager_approved_at=ts.reviewed_at,
        ))
    return result


# ── GET /hr/projects ──────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectOut])
def list_hr_projects(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List all active projects. Used by the HR timesheet edit drawer."""
    _require_admin(user)
    rows = (
        db.query(Project)
        .filter(Project.status == "active")
        .order_by(Project.name)
        .all()
    )
    return [ProjectOut.model_validate(p) for p in rows]


# ── GET /hr/tasks ─────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskOut])
def list_hr_tasks(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List tasks for a project. Used by the HR timesheet edit drawer."""
    _require_admin(user)
    q = db.query(Task)
    if project_id:
        q = q.filter(Task.project_id == project_id)
    # Filter active tasks: status not 'inactive' / 'closed'
    q = q.filter(Task.status.notin_(["inactive", "closed", "cancelled"]))
    rows = q.order_by(Task.name).all()
    return [TaskOut.model_validate(t) for t in rows]


# ── PUT /hr/timesheets/{ts_id}/entries ────────────────────────────────────────

@router.put("/timesheets/{ts_id}/entries")
def hr_edit_timesheet_entries(
    ts_id: str,
    payload: HRTimesheetEntriesIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """HR edits timesheet entries for a client_site employee timesheet.

    - 403 if the timesheet is locked.
    - Deletes, updates, and inserts entries in a single transaction.
    - Recalculates total_logged_hours and re-runs mismatch cross-check.
    - Writes audit log.
    """
    _require_admin(user)
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    owner = db.get(Employee, ts.employee_id)
    if not owner or getattr(owner, "employee_type", "wfh") != "client_site":
        raise HTTPException(status_code=403, detail="Timesheet access is only available for client-site employees.")
    if ts.locked_at is not None:
        raise HTTPException(status_code=403, detail="Timesheet is locked and cannot be modified.")

    # Capture old state for audit
    old_entries = [
        {"id": e.id, "entry_date": str(e.entry_date), "logged_hours": e.logged_hours}
        for e in db.query(TimesheetEntry).filter(TimesheetEntry.timesheet_id == ts_id).all()
    ]

    try:
        for row in payload.entries:
            if row.delete:
                if row.id:
                    entry = db.get(TimesheetEntry, row.id)
                    if entry and entry.timesheet_id == ts_id:
                        db.delete(entry)
            elif row.id:
                # Update existing entry
                entry = db.get(TimesheetEntry, row.id)
                if entry and entry.timesheet_id == ts_id:
                    if row.project_id is not None:
                        entry.project_id = row.project_id
                    entry.task_id = row.task_id
                    entry.logged_hours = row.logged_hours
                    entry.description = row.description
                    entry.source = "hr_edit"
                    entry.is_manual_entry = True
            else:
                # Insert new entry
                db.add(TimesheetEntry(
                    id=_next_te_id(db),
                    timesheet_id=ts_id,
                    employee_id=ts.employee_id,
                    entry_date=row.entry_date,
                    project_id=row.project_id,
                    task_id=row.task_id,
                    logged_hours=row.logged_hours,
                    description=row.description,
                    source="hr_edit",
                    is_manual_entry=True,
                ))

        db.flush()

        # Recalculate total
        total = db.query(func.sum(TimesheetEntry.logged_hours)).filter(
            TimesheetEntry.timesheet_id == ts_id
        ).scalar() or 0.0
        ts.total_logged_hours = round(float(total), 2)
        ts.updated_at = now_utc()

        db.flush()

        # Re-run mismatch cross-check if timesheet is past draft
        from app.routes.timesheet import _run_cross_check
        if (ts.status or "draft") not in {"draft", None}:
            _run_cross_check(db, ts, user.id)

        write_audit(
            db, actor_id=user.id, action="hr_edit_timesheet_entries",
            target_table="timesheets", target_id=ts_id,
            old_value={"entries": old_entries},
            new_value={"total_logged_hours": ts.total_logged_hours, "entry_count": len(payload.entries)},
            ip_address=request.client.host if request.client else None,
        )

        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    db.refresh(ts)
    return {
        "ok": True,
        "total_logged_hours": ts.total_logged_hours,
        "has_mismatch": bool(ts.has_mismatch),
    }


# ── GET /hr/timesheets/summary ────────────────────────────────────────────────

@router.get("/timesheets/summary")
def hr_timesheets_summary(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Count cards for the HR timesheets view. Admin-only."""
    _require_admin(user)

    base_q = (
        db.query(Timesheet)
        .join(Employee, Timesheet.employee_id == Employee.id)
        .filter(
            Employee.employee_type == "client_site",
            Employee.employment_status == "active",
            Employee.is_deleted.is_(False),
        )
    )

    total        = base_q.count()
    draft        = base_q.filter(Timesheet.status == "draft").count()
    pending      = base_q.filter(Timesheet.status.in_(["pending", "pending_internal", "pending_review"])).count()
    client_appr  = base_q.filter(Timesheet.status == "client_approved").count()
    mgr_appr     = base_q.filter(Timesheet.status == "manager_approved").count()
    locked       = base_q.filter(Timesheet.is_locked.is_(True)).count()
    rejected     = base_q.filter(Timesheet.status == "rejected").count()
    mismatched   = base_q.filter(Timesheet.has_mismatch.is_(True)).count()

    return {
        "total": total,
        "draft": draft,
        "pending": pending,
        "client_approved": client_appr,
        "manager_approved": mgr_appr,
        "locked": locked,
        "rejected": rejected,
        "mismatched": mismatched,
    }


# ── GET /hr/timesheets/export/csv ─────────────────────────────────────────────

_TS_CSV_HEADERS = [
    "employee_name",
    "employee_id",
    "project_client",
    "attendance_date",
    "worked_hours",
    "check_in",
    "check_out",
    "attendance_status",
    "approval_status",
    "manager",
    "remarks",
]


@router.get("/timesheets/export/csv")
def hr_timesheets_export_csv(
    start_date: date_t = Query(...),
    end_date: date_t = Query(...),
    employee_id: Optional[int] = Query(None),
    department_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Stream admin timesheets as CSV only.

    Each row is one timesheet entry.  Optional filters:
      start_date / end_date  — filter by period_start / period_end
      status                 — filter by timesheet.status
    """
    _require_admin(user)

    sd = start_date
    ed = end_date
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date.")

    # ── Fetch timesheets with employee/department joins ────────────────
    q = (
        db.query(Timesheet, Employee, Department)
        .join(Employee, Timesheet.employee_id == Employee.id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .filter(
            Employee.employee_type == "client_site",
            Employee.employment_status == "active",
            Employee.is_deleted.is_(False),
            Timesheet.period_start >= sd,
            Timesheet.period_end <= ed,
        )
    )
    if employee_id is not None:
        q = q.filter(Employee.id == employee_id)
    if department_id:
        q = q.filter(Employee.department_id == department_id)
    if status:
        q = q.filter(Timesheet.status == status.lower())

    ts_rows = q.order_by(Timesheet.period_start.asc(), Employee.id).all()

    if not ts_rows:
        # Return header-only CSV rather than an error
        buf = io.StringIO()
        csv.DictWriter(buf, fieldnames=_TS_CSV_HEADERS).writeheader()
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="timesheets_{start_date}_{end_date}.csv"'},
        )

    # ── Batch-load supporting data ─────────────────────────────────────
    ts_ids  = [ts.id  for ts, _, _ in ts_rows]
    emp_ids = [emp.id for _, emp, _ in ts_rows]

    entries = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.timesheet_id.in_(ts_ids))
        .all()
    )
    entries_by_ts: dict[str, list] = {}
    for e in entries:
        entries_by_ts.setdefault(e.timesheet_id, []).append(e)

    project_ids = {e.project_id for e in entries if e.project_id}
    project_map = {
        project.id: project
        for project in db.query(Project).filter(Project.id.in_(project_ids)).all()
    } if project_ids else {}

    # Manager names for employees
    mgr_ids = {emp.reporting_manager_id for _, emp, _ in ts_rows if emp.reporting_manager_id}
    mgr_map = {
        m.id: m.full_name or f"{m.first_name or ''} {m.last_name or ''}".strip()
        for m in db.query(Employee).filter(Employee.id.in_(mgr_ids)).all()
    } if mgr_ids else {}

    # Attendance records keyed by (employee_id, date)
    att_rec_ids = {e.attendance_record_id for e in entries if e.attendance_record_id}
    att_by_id: dict[str, AttendanceRecord] = {}
    if att_rec_ids:
        for ar in db.query(AttendanceRecord).filter(AttendanceRecord.id.in_(att_rec_ids)).all():
            att_by_id[ar.id] = ar

    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id.in_(emp_ids),
            AttendanceLog.punch_timestamp >= datetime.combine(sd, datetime.min.time()),
            AttendanceLog.punch_timestamp <= datetime.combine(ed, datetime.max.time()),
            AttendanceLog.is_valid.is_(True),
        )
        .all()
    )
    checkin_idx: dict[tuple[int, date_t], datetime] = {}
    checkout_idx: dict[tuple[int, date_t], datetime] = {}
    for log in logs:
        punch_date = log.punch_timestamp.date()
        key = (log.employee_id, punch_date)
        if log.punch_type == "check_in":
            if key not in checkin_idx or log.punch_timestamp < checkin_idx[key]:
                checkin_idx[key] = log.punch_timestamp
        elif log.punch_type == "check_out":
            if key not in checkout_idx or log.punch_timestamp > checkout_idx[key]:
                checkout_idx[key] = log.punch_timestamp

    # ── Build CSV ─────────────────────────────────────────────────────
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TS_CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()

    for ts, emp, _dep in ts_rows:
        employee_name = emp.full_name or f"{emp.first_name or ''} {emp.last_name or ''}".strip()
        manager_name = mgr_map.get(emp.reporting_manager_id, "") if emp.reporting_manager_id else ""
        for entry in entries_by_ts.get(ts.id, []):
            attendance_row = att_by_id.get(entry.attendance_record_id) if entry.attendance_record_id else None
            project = project_map.get(entry.project_id) if entry.project_id else None
            project_name = project.name if project and project.name else (entry.project_id or "")
            client_name = project.client_name if project and project.client_name else ""
            check_in = checkin_idx.get((emp.id, entry.entry_date)) if entry.entry_date else None
            check_out = checkout_idx.get((emp.id, entry.entry_date)) if entry.entry_date else None
            remarks = " | ".join(
                part.strip()
                for part in [entry.description or "", ts.review_comment or ""]
                if part and part.strip()
            )
            writer.writerow({
                "employee_name": employee_name,
                "employee_id": emp.employee_code or str(emp.id),
                "project_client": " / ".join(part for part in [project_name, client_name] if part),
                "attendance_date": str(entry.entry_date) if entry.entry_date else "",
                "worked_hours": f"{entry.logged_hours:.2f}" if entry.logged_hours is not None else "",
                "check_in": check_in.strftime("%H:%M:%S") if check_in else "",
                "check_out": check_out.strftime("%H:%M:%S") if check_out else "",
                "attendance_status": attendance_row.status if attendance_row else "",
                "approval_status": ts.status or "",
                "manager": manager_name,
                "remarks": remarks,
            })

    buf.seek(0)
    filename = f"timesheets_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /hr/timesheets/{ts_id} ────────────────────────────────────────────────

@router.get("/timesheets/{ts_id}")
def hr_get_timesheet(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Single timesheet detail. Returns 404 for non-client_site owners. Admin-only."""
    _require_admin(user)
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    owner = db.get(Employee, ts.employee_id)
    if not owner or getattr(owner, "employee_type", "wfh") != "client_site":
        raise HTTPException(status_code=404, detail="Timesheet not found.")

    out = TimesheetDetailOut.model_validate(ts)
    entries = []
    for e in ts.entries:
        entry_out = TimesheetEntryOut.model_validate(e)
        # Resolve attendance status for each entry
        att_rec = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == ts.employee_id,
                AttendanceRecord.date == e.entry_date,
            )
            .first()
        )
        present_statuses = {"present", "late", "half_day", "on_leave", "holiday"}
        if att_rec and (att_rec.status or "").lower() in present_statuses:
            entry_out.attendance_status = "Present"
        else:
            entry_out.attendance_status = "Absent"
        entries.append(entry_out)
    out.entries = entries
    return out


# ── PATCH /hr/employees/{employee_id}/type ────────────────────────────────────

@router.patch("/employees/{employee_id}/type")
def update_employee_type(
    employee_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Admin-only: change employee_type and derive is_tm. Writes audit log."""
    _require_admin(user)
    emp = db.get(Employee, employee_id)
    if not emp or emp.is_deleted:
        raise HTTPException(status_code=404, detail="Employee not found.")

    new_type = payload.get("employee_type")
    if new_type not in ("wfh", "wfo", "client_site"):
        raise HTTPException(status_code=400, detail="employee_type must be wfh, wfo, or client_site.")

    old_value = {"employee_type": emp.employee_type, "is_tm": bool(emp.is_tm)}
    emp.employee_type = new_type
    emp.is_tm = (new_type == "client_site")
    new_value = {"employee_type": emp.employee_type, "is_tm": bool(emp.is_tm)}

    write_audit(
        db, actor_id=user.id, action="employee_type_updated",
        target_table="employees", target_id=str(employee_id),
        old_value=old_value, new_value=new_value,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(emp)
    return {
        "id":            emp.id,
        "employee_type": emp.employee_type,
        "is_tm":         bool(emp.is_tm),
    }
