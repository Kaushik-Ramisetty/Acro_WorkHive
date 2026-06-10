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

import logging
from datetime import date as date_t, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel as _PydanticBase
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from utils.time_utils import now_utc
from app.db.session import get_db
from app.models import (
    AttendanceRecord, Employee, PayrollAttendanceSummary, Project, Task,
    Timesheet, TimesheetEntry, TimesheetPayrollSync, TimesheetWorkflowStep,
)
from app.schemas.timesheet import (
    BulkReviewIn, BulkReviewOut,
    MonthlyDayOut, MonthlyReportDetailOut, MonthlyReportIn,
    ProjectOut, TaskOut, TimesheetCreateIn, TimesheetDetailOut, TimesheetEntryIn,
    TimesheetEntryOut, TimesheetOut, TimesheetReviewIn,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify
from app.services.timesheet_email import (
    html_approval_form, html_confirmation_page, html_rejection_form,
    send_client_approval_email,
)
from app.services.token_service import generate_client_token, verify_client_token

logger = logging.getLogger("hrms.timesheet")


router = APIRouter(prefix="/timesheet", tags=["timesheet"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


_PRESENT_STATUSES = {"present", "late", "half_day", "on_leave", "holiday"}


def _resolved_att_status(db: Session, employee_id: int, entry_date) -> str:
    """Return 'Present' or 'Absent' for a single employee+date pair.
    Any status other than 'absent' (or no record) maps to 'Absent'."""
    rec = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.date == entry_date,
        )
        .first()
    )
    if rec and (rec.status or "").lower() in _PRESENT_STATUSES:
        return "Present"
    return "Absent"


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


def _resolve_project_client(
    ts_ids: list[str], db: Session
) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Return {ts_id: (project_name, client_name)} for each timesheet.

    Uses one batched query against timesheet_entries + projects rather than
    per-row lookups, so it is safe even for lists of ~200 rows.
    """
    if not ts_ids:
        return {}
    # Join entries → projects and group by timesheet_id so we get one project
    # reference per timesheet regardless of how many entries it has.
    from sqlalchemy import func as _agg
    rows = (
        db.query(
            TimesheetEntry.timesheet_id,
            _agg.min(Project.name),
            _agg.min(Project.client_name),
        )
        .join(Project, Project.id == TimesheetEntry.project_id)
        .filter(
            TimesheetEntry.timesheet_id.in_(ts_ids),
            TimesheetEntry.project_id.isnot(None),
        )
        .group_by(TimesheetEntry.timesheet_id)
        .all()
    )
    return {r[0]: (r[1], r[2]) for r in rows}


def _enrich_ts_list(rows: list[Timesheet], db: Session) -> list:
    """Bulk-enrich a list of Timesheet ORM objects into TimesheetOut dicts
    that include employee_name, project_name, and client_name.

    Three queries total (employees, entries+projects, tasks) regardless of list length.
    """
    if not rows:
        return []

    # 1. Batch-fetch employees
    emp_ids  = list({r.employee_id for r in rows})
    emp_map  = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()}

    # 2. Resolve project + client per timesheet
    ts_ids       = [r.id for r in rows]
    proj_client  = _resolve_project_client(ts_ids, db)

    out = []
    for r in rows:
        obj = TimesheetOut.model_validate(r)
        emp = emp_map.get(r.employee_id)
        obj.employee_name = emp.full_name if emp else None
        pc = proj_client.get(r.id)
        if pc:
            obj.project_name, obj.client_name = pc
        out.append(obj)
    return out


def _enrich_ts_detail(ts: Timesheet, db: Session) -> TimesheetDetailOut:
    """Enrich a single Timesheet into a TimesheetDetailOut with:
    - employee_name
    - project_name / client_name (from entries)
    - entry-level client_name / project_name / task_name (batch-fetched)
    """
    out = TimesheetDetailOut.model_validate(ts)

    # Employee name
    emp = db.get(Employee, ts.employee_id)
    out.employee_name = emp.full_name if emp else None

    # Collect project/task IDs from entries once so detail views stay O(1) queries.
    proj_ids = list({e.project_id for e in ts.entries if e.project_id})
    task_ids = list({e.task_id for e in ts.entries if e.task_id})

    projs = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()} if proj_ids else {}
    tasks = {t.id: t for t in db.query(Task).filter(Task.id.in_(task_ids)).all()} if task_ids else {}

    # Set header-level project/client from first project found.
    for pid in proj_ids:
        proj = projs.get(pid)
        if proj:
            out.project_name = proj.name
            out.client_name = proj.client_name
            break

    enriched = []
    for e in ts.entries:
        entry_out = TimesheetEntryOut.model_validate(e)
        proj = projs.get(e.project_id) if e.project_id else None
        task = tasks.get(e.task_id) if e.task_id else None
        entry_out.project_name = proj.name if proj else None
        entry_out.client_name = proj.client_name if proj else None
        entry_out.task_name = task.name if task else None
        enriched.append(entry_out)
    out.entries = enriched

    return out


# ── Payroll cycle helper ─────────────────────────────────────────────

def _payroll_cycle_dates(today: date_t) -> tuple[date_t, date_t]:
    """Returns (period_start, period_end) for the current 26→25 billing cycle.

    If today ≤ 25: cycle is 26th of prev month → 25th of current month.
    If today > 25: cycle is 26th of current month → 25th of next month.
    """
    if today.day <= 25:
        first_of_month = today.replace(day=1)
        last_of_prev   = first_of_month - timedelta(days=1)
        start = last_of_prev.replace(day=26)
        end   = today.replace(day=25)
    else:
        start = today.replace(day=26)
        if today.month == 12:
            end = date_t(today.year + 1, 1, 25)
        else:
            end = date_t(today.year, today.month + 1, 25)
    return start, end


# ── Projects + tasks (read) ──────────────────────────────────────────

@router.get("/me")
def my_timesheets(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee's own timesheets. Returns access=false for non-client_site employees."""
    if getattr(user, "employee_type", "wfh") != "client_site":
        return {
            "access": False,
            "reason": "not_assigned",
            "message": "Timesheet access is only available for employees assigned to client-site projects.",
        }
    q = db.query(Timesheet).filter(Timesheet.employee_id == user.id)
    if status:
        q = q.filter(Timesheet.status == status.lower())
    rows = q.order_by(Timesheet.period_start.desc()).limit(200).all()
    return {"access": True, "timesheets": [TimesheetOut.model_validate(r) for r in rows]}


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


# ── Client-manager token actions (public — no auth required) ────────

@router.get("/client-action", response_class=HTMLResponse)
def client_token_action_get(
    token: str = Query(...),
    action: str = Query(...),
    db: Session = Depends(get_db),
):
    """External client manager approval/rejection via tokenized email link.

    GET  ?token=...&action=approve  → returns HTML approval form (optional remarks, POSTs back).
    GET  ?token=...&action=reject   → returns HTML rejection form (mandatory remarks, POSTs back).
    """
    payload = verify_client_token(token)
    if not payload:
        return HTMLResponse(
            content=html_confirmation_page(
                "error", "Invalid or Expired Link",
                "This approval link is invalid or has already expired. "
                "Please contact your HR team for a fresh link.",
            ),
            status_code=400,
        )

    ts_id = payload["ts_id"]
    ts    = db.get(Timesheet, ts_id)
    if not ts:
        return HTMLResponse(
            content=html_confirmation_page(
                "error", "Timesheet Not Found",
                f"Timesheet {ts_id} could not be found.",
            ),
            status_code=404,
        )

    # Single-use guard: token must still match the stored one
    if ts.client_token != token:
        return HTMLResponse(
            content=html_confirmation_page(
                "info", "Already Processed",
                "This timesheet has already been acted upon. No further action is required.",
            )
        )

    if action not in ("approve", "reject"):
        return HTMLResponse(
            content=html_confirmation_page("error", "Invalid Action",
                "The action must be 'approve' or 'reject'."),
            status_code=400,
        )

    allowed = {"pending_client_review", "pending"}  # "pending" kept for backward compat with old records
    if ts.status not in allowed:
        return HTMLResponse(
            content=html_confirmation_page(
                "info", "Already Processed",
                f"This timesheet (status: {ts.status}) has already moved past the client review stage.",
            )
        )

    if action == "reject":
        return HTMLResponse(content=html_rejection_form(token, ts_id))

    # ── Approve → show confirmation form (POST completes the action) ──
    employee = db.get(Employee, ts.employee_id)
    emp_name = employee.full_name if employee else f"Employee #{ts.employee_id}"
    period_str = f"{ts.period_start} → {ts.period_end}"
    return HTMLResponse(content=html_approval_form(token, ts_id, emp_name, period_str))


@router.post("/client-action", response_class=HTMLResponse)
def client_token_action_post(
    token: str = Form(...),
    action: str = Form(...),
    comments: str = Form(""),
    db: Session = Depends(get_db),
):
    """Handle approval/rejection form submission from client_token_action_get."""
    payload = verify_client_token(token)
    if not payload:
        return HTMLResponse(
            content=html_confirmation_page(
                "error", "Invalid or Expired Link",
                "This approval link is invalid or has expired. "
                "Please contact your HR team for a fresh link.",
            ),
            status_code=400,
        )

    ts_id = payload["ts_id"]
    ts    = db.get(Timesheet, ts_id)
    if not ts:
        return HTMLResponse(
            content=html_confirmation_page("error", "Timesheet Not Found",
                f"Timesheet {ts_id} could not be found."),
            status_code=404,
        )

    if ts.client_token != token:
        return HTMLResponse(
            content=html_confirmation_page("info", "Already Processed",
                "This timesheet has already been acted upon.")
        )

    allowed = {"pending_client_review", "pending"}  # "pending" kept for backward compat with old records
    if ts.status not in allowed:
        return HTMLResponse(
            content=html_confirmation_page("info", "Already Processed",
                f"Status is '{ts.status}' — past client review stage.")
        )

    if action not in ("approve", "reject"):
        return HTMLResponse(
            content=html_confirmation_page("error", "Invalid Action",
                "Only 'approve' or 'reject' is accepted via form POST."),
            status_code=400,
        )

    employee = db.get(Employee, ts.employee_id)
    emp_name = employee.full_name if employee else f"Employee #{ts.employee_id}"
    clean_comments = (comments or "").strip()

    # ── Approve ──────────────────────────────────────────────────────
    if action == "approve":
        ts.status                = "pending_reporting_manager_review"
        ts.client_approved_at    = now_utc()
        ts.client_token          = None   # invalidate — single use
        if clean_comments:
            ts.client_review_comment = clean_comments

        step_meta = _get_step_meta("client")
        _record_step(db, ts_id, "client", step_meta.get("sequence_order", 2),
                     "approved", None, clean_comments or "Approved via email link")

        notify(db, recipient_id=ts.employee_id, type_="timesheet_review",
               title="Timesheet Approved by Client Manager",
               body=f"Your timesheet ({ts.period_start} → {ts.period_end}) has been approved.",
               reference_table="timesheets", reference_id=ts.id)

        if employee and employee.reporting_manager_id:
            notify(db, recipient_id=employee.reporting_manager_id,
                   type_="timesheet_submitted",
                   title=f"Timesheet ready for review — {emp_name}",
                   body=f"Client has approved {ts.period_start} → {ts.period_end}.",
                   reference_table="timesheets", reference_id=ts.id)

        write_audit(db, actor_id=None, action="client_token_approve",
                    target_table="timesheets", target_id=ts.id,
                    new_value={"status": ts.status, "client_review_comment": clean_comments or None})
        db.commit()

        return HTMLResponse(
            content=html_confirmation_page(
                "success", "Timesheet Approved",
                f"You have successfully approved <strong>{emp_name}</strong>'s timesheet "
                f"for {ts.period_start} → {ts.period_end}. "
                "The timesheet has been forwarded to the reporting manager for further review.",
            )
        )

    # ── Reject ───────────────────────────────────────────────────────
    if not clean_comments:
        return HTMLResponse(
            content=html_rejection_form(token, ts_id,
                error="A rejection reason is required."),
            status_code=400,
        )

    ts.status                = "client_rejected"
    ts.is_locked             = False
    ts.client_token          = None   # invalidate
    ts.client_review_comment = clean_comments

    step_meta = _get_step_meta("client")
    _record_step(db, ts_id, "client", step_meta.get("sequence_order", 2),
                 "rejected", None, clean_comments)

    notify(db, recipient_id=ts.employee_id, type_="timesheet_review",
           title="Timesheet Rejected by Client Manager",
           body=f"Reason: {clean_comments[:200]}",
           reference_table="timesheets", reference_id=ts.id)

    if employee and employee.reporting_manager_id:
        notify(db, recipient_id=employee.reporting_manager_id,
               type_="timesheet_review",
               title=f"Timesheet Rejected by Client — {emp_name}",
               body=f"Client rejected {ts.period_start} → {ts.period_end}. Reason: {clean_comments[:200]}",
               reference_table="timesheets", reference_id=ts.id)

    write_audit(db, actor_id=None, action="client_token_reject",
                target_table="timesheets", target_id=ts.id,
                new_value={"status": "client_rejected", "comments": clean_comments})
    db.commit()

    return HTMLResponse(
        content=html_confirmation_page(
            "warning", "Timesheet Rejected",
            f"You have rejected <strong>{emp_name}</strong>'s timesheet "
            f"for {ts.period_start} → {ts.period_end}. "
            "The employee and their reporting manager have been notified.",
        )
    )


# ── Client-review JSON API (React approval page — no auth) ──────────

class _ClientReviewIn(_PydanticBase):
    token:   str
    action:  str             # "approve" | "reject"
    remarks: Optional[str] = None


@router.get("/client-review")
def client_review_info(token: str = Query(...), db: Session = Depends(get_db)):
    """JSON — no auth required — timesheet info for the React client approval page."""
    from app.services.timesheet_email import _CAL, _WEEKDAYS, _day_code, _fmt_date

    payload = verify_client_token(token)
    if not payload:
        return {"valid": False, "error": "expired"}

    ts_id = payload["ts_id"]
    ts    = db.get(Timesheet, ts_id)
    if not ts:
        return {"valid": False, "error": "not_found"}

    if ts.client_token != token:
        return {"valid": False, "error": "already_processed"}

    if ts.status not in {"pending_client_review", "pending"}:
        return {"valid": False, "error": "already_processed"}

    employee = db.get(Employee, ts.employee_id)
    emp_name = employee.full_name if employee else f"Employee #{ts.employee_id}"
    emp_code = (employee.employee_code or "—") if employee else "—"
    desig    = (
        getattr(employee.designation, "title", "N/A")
        if employee and employee.designation else "N/A"
    )

    calendar: list[dict] = []
    summary = {"present": 0, "absent": 0, "weekend_worked": 0, "holiday_worked": 0, "total_hours": 0.0}

    if ts.period_start and ts.period_end:
        att_records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == ts.employee_id,
                AttendanceRecord.date >= ts.period_start,
                AttendanceRecord.date <= ts.period_end,
            )
            .all()
        )
        att_map = {r.date: r for r in att_records}
        cur = ts.period_start
        while cur <= ts.period_end:
            wd    = cur.weekday()
            is_we = wd >= 5
            rec   = att_map.get(cur)
            s     = (rec.status if rec else "") or ""
            code  = _day_code(s, is_we, bool(rec and rec.check_in_time))
            hours = (rec.working_hours or 0.0) if rec else 0.0
            summary["total_hours"] += hours
            if code == "P":   summary["present"] += 1
            elif code == "A": summary["absent"] += 1
            elif code == "WW": summary["weekend_worked"] += 1
            elif code == "HW": summary["holiday_worked"] += 1
            calendar.append({
                "date":       cur.isoformat(),
                "day":        cur.day,
                "day_abbr":   _WEEKDAYS[wd][:3],
                "weekday":    wd,
                "code":       code,
                "is_weekend": is_we,
                "hours":      round(hours, 2),
                "bg":         _CAL[code][0],
                "fg":         _CAL[code][1],
            })
            cur += timedelta(days=1)

    project_name: Optional[str] = None
    entry = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.timesheet_id == ts_id, TimesheetEntry.project_id.isnot(None))
        .first()
    )
    if entry and entry.project_id:
        proj = db.get(Project, entry.project_id)
        project_name = proj.name if proj else None

    def _fmt_date_local(d) -> str:
        from app.services.timesheet_email import _fmt_date as _fe_fmt
        return _fe_fmt(d)

    period_label = (
        f"{_fmt_date_local(ts.period_start)} – {_fmt_date_local(ts.period_end)}"
        if ts.period_start and ts.period_end else ""
    )

    return {
        "valid":            True,
        "ts_id":            ts_id,
        "emp_name":         emp_name,
        "emp_code":         emp_code,
        "designation":      desig,
        "period_start":     ts.period_start.isoformat() if ts.period_start else None,
        "period_end":       ts.period_end.isoformat()   if ts.period_end   else None,
        "period_label":     period_label,
        "total_hours":      round(ts.total_logged_hours or 0.0, 2),
        "status":           ts.status,
        "submitted_at":     ts.submitted_at.isoformat() if ts.submitted_at else None,
        "project_name":     project_name,
        "employee_remarks": ts.review_comment or None,
        "calendar":         calendar,
        "summary":          {**summary, "total_hours": round(summary["total_hours"], 2)},
    }


@router.post("/client-review")
def client_review_submit(body: _ClientReviewIn, db: Session = Depends(get_db)):
    """JSON — no auth required — process client approval/rejection from the React page."""
    payload = verify_client_token(body.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired approval link.")

    ts_id = payload["ts_id"]
    ts    = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")

    if ts.client_token != body.token:
        raise HTTPException(status_code=409, detail="This timesheet has already been reviewed.")

    if ts.status not in {"pending_client_review", "pending"}:
        raise HTTPException(status_code=409, detail=f"Already processed (status: {ts.status}).")

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'.")

    clean_remarks = (body.remarks or "").strip()
    if body.action == "reject" and not clean_remarks:
        raise HTTPException(status_code=422, detail="A rejection reason is required.")

    employee = db.get(Employee, ts.employee_id)
    emp_name = employee.full_name if employee else f"Employee #{ts.employee_id}"

    if body.action == "approve":
        ts.status                = "pending_reporting_manager_review"
        ts.client_approved_at    = now_utc()
        ts.client_token          = None
        if clean_remarks:
            ts.client_review_comment = clean_remarks

        step_meta = _get_step_meta("client")
        _record_step(db, ts_id, "client", step_meta.get("sequence_order", 2),
                     "approved", None, clean_remarks or "Approved via email link")

        notify(db, recipient_id=ts.employee_id, type_="timesheet_review",
               title="Timesheet Approved by Client Manager",
               body=f"Your timesheet ({ts.period_start} → {ts.period_end}) has been approved.",
               reference_table="timesheets", reference_id=ts.id)

        if employee and employee.reporting_manager_id:
            notify(db, recipient_id=employee.reporting_manager_id,
                   type_="timesheet_submitted",
                   title=f"Timesheet ready for review — {emp_name}",
                   body=f"Client approved {ts.period_start} → {ts.period_end}.",
                   reference_table="timesheets", reference_id=ts.id)

        write_audit(db, actor_id=None, action="client_json_approve",
                    target_table="timesheets", target_id=ts.id,
                    new_value={"status": ts.status, "client_review_comment": clean_remarks or None})
        db.commit()
        return {
            "success": True,
            "action":  "approve",
            "message": (
                f"Timesheet for {ts.period_start} → {ts.period_end} has been approved "
                "and forwarded to the Reporting Manager."
            ),
        }

    # ── Reject ────────────────────────────────────────────────────────
    ts.status                = "client_rejected"
    ts.is_locked             = False
    ts.client_token          = None
    ts.client_review_comment = clean_remarks

    step_meta = _get_step_meta("client")
    _record_step(db, ts_id, "client", step_meta.get("sequence_order", 2),
                 "rejected", None, clean_remarks)

    notify(db, recipient_id=ts.employee_id, type_="timesheet_review",
           title="Timesheet Rejected by Client Manager",
           body=f"Reason: {clean_remarks[:200]}",
           reference_table="timesheets", reference_id=ts.id)

    if employee and employee.reporting_manager_id:
        notify(db, recipient_id=employee.reporting_manager_id,
               type_="timesheet_review",
               title=f"Timesheet Rejected by Client — {emp_name}",
               body=f"Client rejected {ts.period_start} → {ts.period_end}. Reason: {clean_remarks[:200]}",
               reference_table="timesheets", reference_id=ts.id)

    write_audit(db, actor_id=None, action="client_json_reject",
                target_table="timesheets", target_id=ts.id,
                new_value={"status": "client_rejected", "client_review_comment": clean_remarks})
    db.commit()
    return {
        "success": True,
        "action":  "reject",
        "message": (
            f"Timesheet for {ts.period_start} → {ts.period_end} has been rejected. "
            "The employee has been notified."
        ),
    }


# ── Monthly T&M payroll-cycle report ─────────────────────────────────

@router.get("/monthly-report", response_model=TimesheetOut)
def get_monthly_report(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Return the current payroll-cycle (25→25) monthly report for the calling employee.
    Returns 404 if no report has been submitted yet for the current cycle."""
    if getattr(user, "employee_type", "wfh") != "client_site":
        raise HTTPException(
            status_code=403,
            detail="Monthly reports are only available for client-site employees.",
        )
    start, end = _payroll_cycle_dates(date_t.today())
    ts = (
        db.query(Timesheet)
        .filter(
            Timesheet.employee_id == user.id,
            Timesheet.period_start == start,
            Timesheet.period_end == end,
            Timesheet.period_type == "monthly",
        )
        .first()
    )
    if not ts:
        raise HTTPException(status_code=404, detail="No monthly report for the current cycle.")
    return TimesheetOut.model_validate(ts)


@router.post("/monthly-report", response_model=TimesheetOut, status_code=201)
def submit_monthly_report(
    payload: MonthlyReportIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Create and immediately submit a monthly payroll-cycle report.

    - Only available for client-site (is_tm or employee_type==client_site) employees.
    - Period is auto-calculated: 25th of prev month → 25th of current month.
    - Aggregates all attendance records in the period as timesheet entries.
    - Rejected reports can be resubmitted (same record updated).
    - Prevents duplicate submissions for the same cycle (409 if already pending/approved).
    """
    if getattr(user, "employee_type", "wfh") != "client_site":
        raise HTTPException(
            status_code=403,
            detail="Monthly reports are only available for client-site employees.",
        )

    start, end = _payroll_cycle_dates(date_t.today())

    # Prevent duplicate submission for non-rejected reports
    existing = (
        db.query(Timesheet)
        .filter(
            Timesheet.employee_id == user.id,
            Timesheet.period_start == start,
            Timesheet.period_end == end,
        )
        .first()
    )
    non_editable = {
        "pending_client_review", "pending",   # both old + new pending statuses
        "client_approved", "pending_reporting_manager_review",
        "reporting_manager_approved", "pending_hr_review",
        "hr_approved", "pending_finance_review",
        "finance_approved", "manager_approved", "approved", "locked", "processing", "completed",
    }
    if existing and (existing.status or "draft") in non_editable:
        raise HTTPException(
            status_code=409,
            detail=f"A monthly report for this cycle already exists (status: {existing.status}). "
                   "Wait for the current report to complete before resubmitting.",
        )

    # Fetch all attendance records for the period
    att_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == user.id,
            AttendanceRecord.date >= start,
            AttendanceRecord.date <= end,
        )
        .order_by(AttendanceRecord.date)
        .all()
    )

    total_hours = sum(r.working_hours or 0.0 for r in att_records)

    # Use employee's configured client manager as source of truth.
    # Payload fields are accepted as one-time overrides only.
    resolved_name: str | None = (
        (payload.client_manager_name or "").strip()
        or (getattr(user, "client_manager_name", None) or "").strip()
        or None
    )
    resolved_email: str | None = (
        (payload.client_manager_email or "").strip()
        or (getattr(user, "client_manager_email", None) or "").strip()
        or None
    )

    if existing and (existing.status or "draft") in {"draft", "rejected", "client_rejected"}:
        # Resubmit — update the existing record in-place
        ts = existing
        ts.status             = "pending_client_review"
        ts.submitted_at       = now_utc()
        ts.total_logged_hours = round(total_hours, 2)
        ts.review_comment     = payload.remarks
        ts.reviewed_by        = None
        ts.reviewed_at        = None
        ts.is_locked          = False
        if payload.client_manager_id:
            ts.client_manager_id = payload.client_manager_id
        if resolved_name:
            ts.client_manager_name = resolved_name
        if resolved_email:
            ts.client_manager_email = resolved_email
        # Refresh auto-synced entries from current attendance data
        db.query(TimesheetEntry).filter(
            TimesheetEntry.timesheet_id == ts.id,
            TimesheetEntry.is_manual_entry.is_(False),
        ).delete(synchronize_session=False)
    else:
        ts_id_new = _next_ts_id(db)
        ts = Timesheet(
            id=ts_id_new,
            employee_id=user.id,
            period_type="monthly",
            period_start=start,
            period_end=end,
            total_logged_hours=round(total_hours, 2),
            status="pending_client_review",
            submitted_at=now_utc(),
            client_manager_id=payload.client_manager_id or None,
            client_manager_name=resolved_name,
            client_manager_email=resolved_email,
            review_comment=payload.remarks,
            is_locked=False,
        )
        db.add(ts)
        db.flush()

    # (Re)generate the client approval token for each submission
    ts.client_token = generate_client_token(ts.id)

    # Upsert attendance-synced entries for every day with a record
    for rec in att_records:
        hours = round(rec.working_hours or 0.0, 2)
        if hours <= 0:
            continue
        existing_entry = (
            db.query(TimesheetEntry)
            .filter(
                TimesheetEntry.timesheet_id == ts.id,
                TimesheetEntry.entry_date == rec.date,
                TimesheetEntry.is_manual_entry.is_(False),
            )
            .first()
        )
        if existing_entry:
            existing_entry.logged_hours = hours
            existing_entry.attendance_record_id = rec.id
        else:
            db.add(TimesheetEntry(
                id=_next_te_id(db),
                timesheet_id=ts.id,
                employee_id=user.id,
                entry_date=rec.date,
                logged_hours=hours,
                source="attendance_sync",
                is_manual_entry=False,
                attendance_record_id=rec.id,
            ))

    # In-app notification to the reporting manager (if they have an account)
    if ts.client_manager_id:
        notify(
            db,
            recipient_id=ts.client_manager_id,
            type_="timesheet_submitted",
            title=f"Monthly Report from {user.full_name}",
            body=(
                f"Period: {start} → {end} | "
                f"{round(total_hours, 1)} hrs logged"
                + (f" | {payload.remarks[:100]}" if payload.remarks else "")
            ),
            reference_table="timesheets",
            reference_id=ts.id,
        )

    write_audit(
        db, actor_id=user.id, action="monthly_report_submit",
        target_table="timesheets", target_id=ts.id,
        old_value={},
        new_value={
            "status": "pending_client_review",
            "period": f"{start}→{end}",
            "hours": round(total_hours, 2),
            "client_manager_email": ts.client_manager_email,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)

    # Send HTML approval email — only when a direct email address is stored
    if ts.client_manager_email:
        try:
            send_client_approval_email(db, ts.id)
        except Exception as exc:
            logger.warning("Failed to send approval email for %s: %s", ts.id, exc)

    return TimesheetOut.model_validate(ts)


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

    # Idempotent create: return existing record if one already exists for this
    # period rather than crashing with IntegrityError on the UniqueConstraint.
    existing = (
        db.query(Timesheet)
        .filter(
            Timesheet.employee_id == user.id,
            Timesheet.period_start == payload.period_start,
            Timesheet.period_end == payload.period_end,
        )
        .first()
    )
    if existing:
        return _enrich_ts_detail(existing, db)

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
    return _enrich_ts_detail(ts, db)


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

    old_status = ts.status or "draft"   # capture before mutating
    ts.submitted_at = now_utc()
    is_client_site = (getattr(user, "employee_type", "") or "").lower() == "client_site"

    if is_client_site and (user.client_manager_email or "").strip():
        # ── Client-site billing flow ──────────────────────────────────────
        # Route directly to client manager for first-stage approval.
        ts.status               = "pending_client_review"
        ts.client_manager_name  = user.client_manager_name
        ts.client_manager_email = user.client_manager_email
        token                   = generate_client_token(ts.id, expires_hours=72)
        ts.client_token         = token
        ts.client_token_expires_at = now_utc() + timedelta(hours=72)
        new_status = "pending_client_review"
    else:
        # ── Standard flow (WFH / WFO, or client_site with no manager email) ──
        ts.status = "pending_review"
        # Notify the reporting manager
        if user.reporting_manager_id:
            notify(
                db,
                recipient_id=user.reporting_manager_id,
                type_="timesheet_submitted",
                title=f"Timesheet from {user.full_name}",
                body=f"{ts.period_start} → {ts.period_end} ({ts.total_logged_hours or 0} h)",
                reference_table="timesheets", reference_id=ts.id,
            )
        new_status = "pending_review"

    write_audit(
        db, actor_id=user.id, action="timesheet_submit",
        target_table="timesheets", target_id=ts.id,
        old_value={"status": old_status}, new_value={"status": new_status},
        ip_address=request.client.host if request.client else None,
    )
    db.commit(); db.refresh(ts)

    # Send client-approval email after the commit (token is now persisted)
    if is_client_site and ts.client_token:
        try:
            send_client_approval_email(db, ts.id)
        except Exception as exc:
            logger.exception(
                "submit_timesheet: failed to send client approval email for %s recipient=%s error=%s",
                ts.id,
                ts.client_manager_email,
                exc,
            )

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
        s = status.lower()
        if s == "pending_review":
            # "pending_review" is the manager's canonical pending status.
            # Client-site timesheets land in "pending_reporting_manager_review"
            # after the client email approval, which is functionally the same
            # queue for the reporting manager.
            q = q.filter(
                Timesheet.status.in_(["pending_review", "pending_reporting_manager_review"])
            )
        else:
            q = q.filter(Timesheet.status == s)
    rows = q.order_by(Timesheet.period_start.desc()).limit(200).all()
    return _enrich_ts_list(rows, db)


@router.get("/{ts_id}/monthly-detail", response_model=MonthlyReportDetailOut)
def get_monthly_detail(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Full daily breakdown for a monthly timesheet — used by the manager review modal.

    Returns every calendar day in the period with attendance status,
    check-in/out times, hours, and overtime. Aggregates summary counts.
    Accessible by the owning employee, their manager, or admin.
    """
    from datetime import timedelta

    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    _ensure_owner_or_manager(user, ts, db)

    if ts.period_type != "monthly":
        raise HTTPException(status_code=400, detail="This endpoint is for monthly timesheets only.")

    employee = db.get(Employee, ts.employee_id)

    # Build a lookup of AttendanceRecord keyed by date
    att_map: dict[date_t, AttendanceRecord] = {}
    if ts.period_start and ts.period_end:
        recs = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == ts.employee_id,
                AttendanceRecord.date >= ts.period_start,
                AttendanceRecord.date <= ts.period_end,
            )
            .all()
        )
        for r in recs:
            att_map[r.date] = r

    # Enumerate all calendar days in the period
    days: list[MonthlyDayOut] = []
    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    present_days = leave_days = half_days = holiday_days = 0
    total_ot = 0.0

    if ts.period_start and ts.period_end:
        cur = ts.period_start
        while cur <= ts.period_end:
            weekday_idx = (cur.weekday())  # 0=Mon
            is_weekend  = weekday_idx >= 5
            rec = att_map.get(cur)

            status       = None
            check_in     = None
            check_out    = None
            working_hrs  = None
            overtime_hrs = None

            if rec:
                status       = rec.status
                check_in     = str(rec.check_in_time)[:5]  if rec.check_in_time  else None
                check_out    = str(rec.check_out_time)[:5] if rec.check_out_time else None
                working_hrs  = round(rec.working_hours  or 0.0, 2) if rec.working_hours  is not None else None
                overtime_hrs = round(rec.overtime_hours or 0.0, 2) if rec.overtime_hours is not None else None

                # Aggregate counts
                s = (status or "").lower()
                if s in {"present", "late", "wfh"}:
                    present_days += 1
                elif s == "on_leave":
                    leave_days += 1
                elif s == "half_day":
                    half_days += 1
                elif s == "holiday":
                    holiday_days += 1
                total_ot += rec.overtime_hours or 0.0
            elif not is_weekend:
                status = "absent"

            days.append(MonthlyDayOut(
                date=cur,
                weekday=WEEKDAYS[weekday_idx],
                is_weekend=is_weekend,
                status=status,
                check_in_time=check_in,
                check_out_time=check_out,
                working_hours=working_hrs,
                overtime_hours=overtime_hrs,
            ))
            cur += timedelta(days=1)

    out = MonthlyReportDetailOut.model_validate(ts)
    out.employee_name        = employee.full_name if employee else None
    out.employee_code        = employee.employee_code if employee else None
    out.remarks              = ts.review_comment
    out.days                 = days
    out.total_present_days   = present_days
    out.total_leave_days     = leave_days
    out.total_half_days      = half_days
    out.total_holiday_days   = holiday_days
    out.total_overtime_hours = round(total_ot, 2)
    return out


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
    return _enrich_ts_detail(ts, db)


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
    cur_status = (ts.status or "").lower()
    # Accept both the standard pending status AND the client-site post-client-approval status.
    _MANAGER_REVIEWABLE = {"pending_review", "pending_reporting_manager_review"}
    if cur_status not in _MANAGER_REVIEWABLE:
        raise HTTPException(status_code=400, detail=f"Timesheet is in {ts.status} state.")

    decision = payload.decision.lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject.")

    old = {"status": ts.status}
    if decision == "approve":
        if cur_status == "pending_reporting_manager_review":
            # Client-site workflow: RM approval advances to reporting_manager_approved.
            # HR/Finance still need to process — do NOT lock yet.
            ts.status    = "reporting_manager_approved"
            ts.is_locked = False
            _record_step(db, ts.id, "rm", 3, "approved", user.id, payload.review_comment)
        else:
            # Standard (WFH / WFO) single-stage manager approval.
            ts.status    = "approved"
            ts.is_locked = True
            ts.locked_at = now_utc()
    else:
        ts.status    = "rejected"
        ts.is_locked = False

    ts.reviewed_by    = user.id
    ts.review_comment = payload.review_comment
    ts.reviewed_at    = now_utc()

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


# ── Attendance cross-check (runs inside manager approval transaction) ─

def _run_cross_check(db: Session, ts: Timesheet, reviewer_id: int) -> None:
    """Compare each timesheet entry against attendance_records.working_hours.

    Only flags genuine discrepancies:
      Condition A — source='hr_edit': variance > 0.5 h (HR manually changed hours)
      Condition B — source='attendance_sync', is_manual_entry=False: variance > 0.5 h
                    (attendance corrected via regularization after timesheet was synced)
    Auto-sync entries where hours already match are skipped entirely.
    has_mismatch is never set True without a mismatch_reason.

    Must be called inside an existing transaction — no commit here.
    """
    from app.services.notification_service import notify_many

    entries = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.timesheet_id == ts.id)
        .all()
    )

    tps_id_base = _next_tps_id(db)
    ts_total = 0.0
    att_total = 0.0
    # Each element: (date_str, ts_hours, att_hours, source)
    mismatch_entries: list[tuple[str, float, float, str]] = []

    for entry in entries:
        att_rec = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == ts.employee_id,
                AttendanceRecord.date == entry.entry_date,
            )
            .first()
        )
        att_h = att_rec.working_hours or 0.0 if att_rec else 0.0
        ts_h  = entry.logged_hours or 0.0
        ts_total  += ts_h
        att_total += att_h

        source    = (entry.source or "").lower()
        is_manual = bool(entry.is_manual_entry)

        # Condition A: HR-edited or manually-entered — flag if variance > 0.5 h
        if source == "hr_edit" or (source == "manual" and is_manual):
            if abs(ts_h - att_h) > 0.5:
                mismatch_entries.append((str(entry.entry_date), ts_h, att_h, source))
        # Condition B: auto-synced (includes legacy 'auto_fetch') — post-regularization drift
        elif source in ("attendance_sync", "auto_fetch") and not is_manual:
            if ts_h != att_h and abs(ts_h - att_h) > 0.5:
                mismatch_entries.append((str(entry.entry_date), ts_h, att_h, source))
        # All other cases (matching auto-sync entries) are skipped

    variance = round(ts_total - att_total, 2)
    has_mismatch = len(mismatch_entries) > 0

    def _reason_for(date_str: str, ts_h: float, att_h: float, source: str) -> str:
        if source == "hr_edit":
            return f"HR manually adjusted hours from {att_h:.1f}h to {ts_h:.1f}h on {date_str}"
        if source == "manual":
            diff = abs(ts_h - att_h)
            return f"Employee-entered hours ({ts_h:.1f}h) differ from attendance ({att_h:.1f}h) by {diff:.1f}h on {date_str}"
        diff = abs(ts_h - att_h)
        return (
            f"Attendance corrected via regularization after timesheet was submitted "
            f"— hours differ by {diff:.1f}h on {date_str}"
        )

    reason = (
        "; ".join(_reason_for(*m) for m in mismatch_entries)
        if mismatch_entries else None
    )

    # Safety: never persist has_mismatch=True with a null reason
    if has_mismatch and not reason:
        has_mismatch = False

    pas = (
        db.query(PayrollAttendanceSummary)
        .filter(
            PayrollAttendanceSummary.employee_id == ts.employee_id,
            PayrollAttendanceSummary.year == ts.period_start.year,
        )
        .first()
    )

    existing_sync = (
        db.query(TimesheetPayrollSync)
        .filter(TimesheetPayrollSync.timesheet_id == ts.id)
        .first()
    )
    if existing_sync:
        existing_sync.timesheet_hours  = round(ts_total, 2)
        existing_sync.attendance_hours = round(att_total, 2)
        existing_sync.variance_hours   = variance
        existing_sync.has_mismatch     = has_mismatch
        existing_sync.mismatch_reason  = reason
    else:
        db.add(TimesheetPayrollSync(
            id=tps_id_base,
            employee_id=ts.employee_id,
            month=ts.period_start.strftime("%B"),
            year=ts.period_start.year,
            timesheet_id=ts.id,
            payroll_summary_id=pas.id if pas else None,
            timesheet_hours=round(ts_total, 2),
            attendance_hours=round(att_total, 2),
            variance_hours=variance,
            has_mismatch=has_mismatch,
            mismatch_reason=reason,
        ))

    ts.has_mismatch = has_mismatch

    if has_mismatch:
        from app.models import Employee as Emp
        hr_emps = (
            db.query(Emp)
            .filter(Emp.is_deleted.is_(False), Emp.employment_status == "active")
            .all()
        )
        hr_ids = [e.id for e in hr_emps if e.role and e.role.name.lower() in {"admin", "hr"}]
        notify_many(
            db, hr_ids,
            type_="timesheet_mismatch",
            title=f"Timesheet mismatch: {ts.id}",
            body=f"Variance {variance} h across {len(mismatch_entries)} day(s).",
            reference_table="timesheets",
            reference_id=ts.id,
        )


@router.post("/bulk-review", response_model=BulkReviewOut)
def bulk_review_timesheets(
    payload: BulkReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Manager/admin bulk approve or reject multiple timesheets at once.

    Each timesheet is processed independently — failures are collected and
    returned without aborting the rest of the batch.
    """
    role = _role(user)
    if role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager or admin only.")

    decision = payload.decision.lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject.")

    succeeded: list[str] = []
    failed: list[dict] = []

    for ts_id in payload.timesheet_ids:
        try:
            ts = db.get(Timesheet, ts_id)
            if not ts:
                failed.append({"id": ts_id, "reason": "Not found."})
                continue
            target = db.get(Employee, ts.employee_id)
            if not target or getattr(target, "employee_type", "wfh") != "client_site":
                failed.append({"id": ts_id, "reason": "Not a client-site timesheet."})
                continue
            if role == "manager" and (not target or target.reporting_manager_id != user.id):
                failed.append({"id": ts_id, "reason": "Not in your team."})
                continue

            current_status = (ts.status or "").lower()
            if current_status not in {"pending", "pending_review", "client_approved"}:
                failed.append({"id": ts_id, "reason": f"Cannot review a {ts.status} timesheet."})
                continue

            if decision == "approve":
                _run_cross_check(db, ts, user.id)
                ts.status    = "manager_approved"
                ts.is_locked = True
                ts.locked_at = now_utc()
            else:
                ts.status    = "rejected"
                ts.is_locked = False

            ts.reviewed_by    = user.id
            ts.review_comment = payload.review_comment
            ts.reviewed_at    = now_utc()

            notify(
                db,
                recipient_id=ts.employee_id,
                type_="timesheet_review",
                title=f"Timesheet {ts.status}",
                body=(payload.review_comment or f"Your timesheet was {ts.status}."),
                reference_table="timesheets", reference_id=ts.id,
            )
            write_audit(
                db, actor_id=user.id, action=f"bulk_timesheet_{ts.status}",
                target_table="timesheets", target_id=ts.id,
                old_value={"status": current_status},
                new_value={"status": ts.status, "bulk": True},
                ip_address=request.client.host if request.client else None,
            )
            db.commit()
            succeeded.append(ts_id)
        except HTTPException as exc:
            db.rollback()
            failed.append({"id": ts_id, "reason": exc.detail})
        except Exception as exc:
            db.rollback()
            failed.append({"id": ts_id, "reason": str(exc)})

    return BulkReviewOut(succeeded=succeeded, failed=failed)


@router.get("/{ts_id}/mismatch-report")
def mismatch_report(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Returns the timesheet_payroll_sync record + day-by-day breakdown."""
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    _ensure_owner_or_manager(user, ts, db)

    sync = (
        db.query(TimesheetPayrollSync)
        .filter(TimesheetPayrollSync.timesheet_id == ts_id)
        .first()
    )

    entries = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.timesheet_id == ts_id)
        .order_by(TimesheetEntry.entry_date)
        .all()
    )

    breakdown = []
    for e in entries:
        att_rec = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == ts.employee_id,
                AttendanceRecord.date == e.entry_date,
            )
            .first()
        )
        att_h = att_rec.working_hours or 0.0 if att_rec else 0.0
        ts_h  = e.logged_hours or 0.0
        breakdown.append({
            "date":              str(e.entry_date),
            "timesheet_hours":   ts_h,
            "attendance_hours":  att_h,
            "variance":          round(ts_h - att_h, 2),
            "has_mismatch":      abs(ts_h - att_h) > 0.5,
        })

    return {
        "timesheet_id": ts_id,
        "sync": {
            "id":               sync.id if sync else None,
            "timesheet_hours":  sync.timesheet_hours if sync else None,
            "attendance_hours": sync.attendance_hours if sync else None,
            "variance_hours":   sync.variance_hours if sync else None,
            "has_mismatch":     sync.has_mismatch if sync else False,
            "mismatch_reason":  sync.mismatch_reason if sync else None,
        },
        "breakdown": breakdown,
    }


# ── Workflow engine ────────────────────────────────────────────────────────────
#
# Multi-stage approval pipeline:
#   Employee → Client Manager → Reporting Manager → HR → Finance → Payroll
#
# Status progression:
#   draft → pending_client_review → client_approved
#         → pending_reporting_manager_review → reporting_manager_approved
#         → pending_hr_review → hr_approved
#         → pending_finance_review → finance_approved
#         → processing → completed
#
# Rejection at any stage: status = 'client_rejected' (client) or 'rejected' (others).
# Employee edits and resubmits → restarts from pending_client_review.

# Step sequence metadata -------------------------------------------------------

_WORKFLOW_STEPS = [
    {"key": "employee", "sequence_order": 1, "advance_to": "pending_client_review"},
    {"key": "client",   "sequence_order": 2, "advance_to": "pending_reporting_manager_review",
     "done_status": "client_approved",   "reject_status": "client_rejected"},
    {"key": "rm",       "sequence_order": 3, "advance_to": "pending_hr_review",
     "done_status": "reporting_manager_approved", "reject_status": "rejected"},
    {"key": "hr",       "sequence_order": 4, "advance_to": "pending_finance_review",
     "done_status": "hr_approved",       "reject_status": "rejected"},
    {"key": "finance",  "sequence_order": 5, "advance_to": "processing",
     "done_status": "finance_approved",  "reject_status": "rejected"},
    {"key": "payroll",  "sequence_order": 6, "advance_to": "completed",
     "done_status": "completed",         "reject_status": "rejected"},
]

# Role → step key mapping for RBAC
_ROLE_TO_STEP: dict[str, str] = {
    "employee": "employee",
    "manager":  "rm",
    "admin":    "hr",
    # client_manager and finance roles are served via separate auth flows
}

# Billing/payroll-safe statuses (match frontend BILLING_SAFE / PAYROLL_SAFE)
_BILLING_SAFE  = {"finance_approved", "completed"}
_PAYROLL_SAFE  = {"completed"}


def _get_step_meta(step_key: str) -> dict:
    return next((s for s in _WORKFLOW_STEPS if s["key"] == step_key), {})


def _record_step(
    db: Session,
    timesheet_id: str,
    step_key: str,
    sequence_order: int,
    status: str,
    actor_id: int | None,
    comments: str | None,
) -> TimesheetWorkflowStep:
    row = TimesheetWorkflowStep(
        timesheet_id=timesheet_id,
        step_role=step_key,
        sequence_order=sequence_order,
        status=status,
        acted_by=actor_id,
        acted_at=now_utc(),
        comments=comments,
    )
    db.add(row)
    return row


# ── GET workflow steps ─────────────────────────────────────────────────────────

@router.get("/{ts_id}/workflow/steps")
def get_workflow_steps(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Return the full workflow audit history for a timesheet."""
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    _ensure_owner_or_manager(user, ts, db)

    rows = (
        db.query(TimesheetWorkflowStep)
        .filter(TimesheetWorkflowStep.timesheet_id == ts_id)
        .order_by(TimesheetWorkflowStep.sequence_order, TimesheetWorkflowStep.created_at)
        .all()
    )

    return [
        {
            "id":             r.id,
            "step_role":      r.step_role,
            "sequence_order": r.sequence_order,
            "status":         r.status,
            "acted_by":       r.acted_by,
            "actor_name":     r.actor.full_name if r.actor else None,
            "acted_at":       r.acted_at.isoformat() if r.acted_at else None,
            "comments":       r.comments,
        }
        for r in rows
    ]


# ── POST workflow/approve ─────────────────────────────────────────────────────

@router.post("/{ts_id}/workflow/approve")
def workflow_approve(
    ts_id: str,
    request: Request,
    comments: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Approve the current workflow step.

    The caller's role determines which step they are approving.
    Automatically advances the timesheet to the next status.

    Billing/payroll gate:
    - Billing calculations are only permitted on finance_approved / completed.
    - Payroll processing is only permitted on completed.
    """
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")

    role = _role(user) or ""

    # Determine which step this actor can approve
    step_key = _ROLE_TO_STEP.get(role)
    if not step_key:
        raise HTTPException(status_code=403, detail=f"Role '{role}' has no workflow approval action.")

    step_meta = _get_step_meta(step_key)
    if not step_meta:
        raise HTTPException(status_code=400, detail=f"Unknown workflow step for role '{role}'.")

    expected_active = {
        "rm":      "pending_reporting_manager_review",
        "hr":      "pending_hr_review",
        "finance": "pending_finance_review",
        "payroll": "processing",
    }.get(step_key)

    if expected_active and ts.status != expected_active:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: timesheet is '{ts.status}', expected '{expected_active}'.",
        )

    done_status = step_meta.get("done_status", "completed")
    ts.status = done_status

    # Lock on finance approval (billing/payroll gate)
    if done_status in _BILLING_SAFE and not ts.is_locked:
        ts.is_locked = True
        ts.locked_at = now_utc()

    _record_step(
        db, ts_id, step_key, step_meta["sequence_order"],
        "approved", user.id, comments,
    )

    # Notify employee
    notify(
        db, recipient_id=ts.employee_id,
        type_="timesheet_review",
        title=f"Timesheet {done_status.replace('_', ' ').title()}",
        body=f"Your timesheet ({ts.period_start} → {ts.period_end}) has been approved by {role}.",
        reference_table="timesheets", reference_id=ts.id,
    )

    write_audit(
        db, actor_id=user.id, action=f"workflow_approve_{step_key}",
        target_table="timesheets", target_id=ts.id,
        new_value={"status": done_status},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)
    return {"ok": True, "timesheet_id": ts_id, "new_status": ts.status}


# ── POST workflow/reject ──────────────────────────────────────────────────────

@router.post("/{ts_id}/workflow/reject")
def workflow_reject(
    ts_id: str,
    request: Request,
    comments: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Reject the current workflow step with a mandatory comment.

    Returns the timesheet to the employee for correction and resubmission.
    Rejection at the client stage sets status='client_rejected';
    rejection at any internal stage sets status='rejected'.
    """
    if not comments or not comments.strip():
        raise HTTPException(status_code=400, detail="Rejection comment is required.")

    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")

    role     = _role(user) or ""
    step_key = _ROLE_TO_STEP.get(role)
    if not step_key:
        raise HTTPException(status_code=403, detail=f"Role '{role}' has no workflow rejection action.")

    step_meta    = _get_step_meta(step_key)
    reject_status = step_meta.get("reject_status", "rejected")

    old_status  = ts.status
    ts.status   = reject_status
    ts.is_locked = False  # unlock so employee can edit

    _record_step(
        db, ts_id, step_key, step_meta.get("sequence_order", 0),
        "rejected", user.id, comments.strip(),
    )

    # Notify employee with rejection comment
    notify(
        db, recipient_id=ts.employee_id,
        type_="timesheet_review",
        title="Timesheet Rejected",
        body=f"Your timesheet was rejected by {user.full_name}: {comments.strip()[:200]}",
        reference_table="timesheets", reference_id=ts.id,
    )

    write_audit(
        db, actor_id=user.id, action=f"workflow_reject_{step_key}",
        target_table="timesheets", target_id=ts.id,
        old_value={"status": old_status},
        new_value={"status": reject_status, "comments": comments.strip()},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)
    return {"ok": True, "timesheet_id": ts_id, "new_status": ts.status}


# ── POST workflow/resubmit (employee resubmit after rejection) ────────────────

@router.post("/{ts_id}/workflow/resubmit")
def workflow_resubmit(
    ts_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Employee resubmits a rejected timesheet.

    Allowed from: client_rejected, rejected.
    Restarts the workflow from the client review stage.
    """
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    if ts.employee_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can resubmit.")
    if ts.status not in {"client_rejected", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resubmit a timesheet with status '{ts.status}'.",
        )

    ts.status       = "pending_client_review"
    ts.submitted_at = now_utc()
    ts.is_locked    = False
    ts.client_token = generate_client_token(ts_id)

    # Re-read client manager info from employee record so stale data is refreshed.
    if getattr(user, "client_manager_name", None):
        ts.client_manager_name = user.client_manager_name.strip()
    if getattr(user, "client_manager_email", None):
        ts.client_manager_email = user.client_manager_email.strip()

    _record_step(db, ts_id, "employee", 1, "approved", user.id, "Resubmitted after corrections")

    if user.reporting_manager_id:
        notify(
            db, recipient_id=user.reporting_manager_id,
            type_="timesheet_submitted",
            title=f"Timesheet resubmitted by {user.full_name}",
            body=f"{ts.period_start} → {ts.period_end} has been corrected and resubmitted.",
            reference_table="timesheets", reference_id=ts.id,
        )

    write_audit(
        db, actor_id=user.id, action="workflow_resubmit",
        target_table="timesheets", target_id=ts.id,
        new_value={"status": "pending_client_review"},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(ts)

    # Send fresh approval email — only when a direct email address is stored
    if ts.client_manager_email:
        try:
            send_client_approval_email(db, ts.id)
        except Exception as exc:
            logger.warning("Failed to send resubmission email for %s: %s", ts.id, exc)

    return {"ok": True, "timesheet_id": ts_id, "new_status": ts.status}


# ── GET billing/payroll readiness check ───────────────────────────────────────

@router.get("/{ts_id}/workflow/billing-check")
def billing_readiness_check(
    ts_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Returns whether a timesheet is cleared for billing and payroll processing.

    Billing: requires finance_approved or completed.
    Payroll: requires completed only.
    """
    ts = db.get(Timesheet, ts_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found.")
    _ensure_owner_or_manager(user, ts, db)

    billing_ok = ts.status in _BILLING_SAFE
    payroll_ok = ts.status in _PAYROLL_SAFE

    return {
        "timesheet_id":    ts_id,
        "current_status":  ts.status,
        "billing_ready":   billing_ok,
        "payroll_ready":   payroll_ok,
        "note": (
            "Cleared for billing and payroll." if payroll_ok else
            "Cleared for billing only — payroll requires completed status." if billing_ok else
            "Not yet cleared — workflow approval is still in progress."
        ),
    }
