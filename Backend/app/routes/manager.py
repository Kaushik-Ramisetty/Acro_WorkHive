"""Manager-scoped API routes.

All endpoints enforce manager isolation: only direct reports
(Employee.reporting_manager_id == current.id) are visible.
Admins may also call these routes and still receive only scoped data.

WFH rule (Part 6):
    WFH employees who check in count as BOTH present AND wfh in summary
    aggregations. A WFH employee who never checked in is absent, not wfh.
"""
from __future__ import annotations

import calendar
import csv
import io
import logging
from collections import defaultdict
from datetime import date as date_t, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from utils.time_utils import to_local

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import (
    AttendanceLog, AttendanceRecord, Employee, LeaveRequest,
)
from app.models.shift import EmployeeShift, Holiday, Shift
from app.services.comp_off_service import is_comp_off_eligible

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/manager",
    tags=["manager"],
    dependencies=[Depends(role_required("manager", "admin"))],
)


@router.get("/ping")
def ping():
    return {"ok": True, "scope": "manager"}


# ── Team listing ─────────────────────────────────────────────────────

@router.get("/team")
def my_team(
    current: Employee = Depends(role_required("manager", "admin")),
    db: Session = Depends(get_db),
):
    """Direct reports of the calling manager (active, non-deleted)."""
    members = (
        db.query(Employee)
        .filter(
            Employee.reporting_manager_id == current.id,
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )
    return [
        {
            "id": m.id,
            "full_name": m.full_name,
            "name": m.full_name,
            "employee_code": m.employee_code,
            "email": m.email,
            "designation_id": m.designation_id,
            "employee_type": m.employee_type,
            "employment_status": m.employment_status,
        }
        for m in members
    ]


# ── Attendance dashboard ──────────────────────────────────────────────

@router.get("/attendance-dashboard")
def attendance_dashboard(
    target_date: Optional[date_t] = Query(None, description="Date for daily stats (defaults to today)"),
    current: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Real-time attendance dashboard for the manager's direct reports.

    Returns:
      - summary: present / on_leave / wfh / absent / half_day for target_date
        WFH employees who checked in are counted in BOTH present AND wfh.
      - week_log: per-employee daily status grid for Mon–Sun of the target week
      - todays_checkins: employees who checked in today with their check-in time
      - weekly_trend: daily present count over the last 7 calendar days
        (includes wfh status as present)
    """
    today = target_date or date_t.today()

    team = (
        db.query(Employee)
        .filter(
            Employee.reporting_manager_id == current.id,
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )
    team_ids = [e.id for e in team]
    emp_by_id = {e.id: e for e in team}

    if not team_ids:
        return {
            "summary": {"present": 0, "on_leave": 0, "wfh": 0, "absent": 0, "half_day": 0, "team_size": 0},
            "week_log": [],
            "todays_checkins": [],
            "weekly_trend": [],
        }

    # ── Daily summary ────────────────────────────────────────────────
    today_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id.in_(team_ids),
            AttendanceRecord.date == today,
        )
        .all()
    )
    rec_by_emp = {r.employee_id: r for r in today_records}

    summary = {
        "present": 0, "on_leave": 0, "wfh": 0,
        "absent": 0, "half_day": 0, "team_size": len(team_ids),
    }
    for eid in team_ids:
        rec = rec_by_emp.get(eid)
        emp = emp_by_id[eid]
        status = (rec.status or "absent").lower() if rec else "absent"
        is_wfh_type = (emp.employee_type == "wfh")

        if status in ("wfh", "work_from_home"):
            # WFH check-in counts as present AND wfh
            summary["present"] += 1
            summary["wfh"] += 1
        elif status in ("present", "late"):
            summary["present"] += 1
            # WFH-type employee who got a present/late record still counted as wfh
            if is_wfh_type:
                summary["wfh"] += 1
        elif status == "on_leave":
            summary["on_leave"] += 1
        elif status == "half_day":
            summary["half_day"] += 1
        else:
            summary["absent"] += 1

    # ── Weekly attendance log (Mon–Sun containing today) ─────────────
    dow = today.weekday()           # Mon=0
    week_start = today - timedelta(days=dow)
    week_end   = week_start + timedelta(days=6)
    week_days  = [week_start + timedelta(days=i) for i in range(7)]

    week_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id.in_(team_ids),
            AttendanceRecord.date >= week_start,
            AttendanceRecord.date <= week_end,
        )
        .all()
    )
    week_idx: dict[tuple[int, date_t], AttendanceRecord] = {
        (r.employee_id, r.date): r for r in week_records
    }

    def _short_status(r: Optional[AttendanceRecord]) -> str:
        if r is None:
            return "absent"
        return (r.status or "absent").lower()

    week_log = []
    for emp in team:
        day_statuses = []
        total_hours = 0.0
        for d in week_days:
            r = week_idx.get((emp.id, d))
            s = _short_status(r)
            day_statuses.append({"date": d.isoformat(), "status": s})
            if r:
                total_hours += float(r.working_hours or 0)
        week_log.append({
            "employee_id": emp.id,
            "name": emp.full_name,
            "days": day_statuses,
            "total_hours": round(total_hours, 1),
        })

    # ── Today's check-ins ────────────────────────────────────────────
    today_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id.in_(team_ids),
            AttendanceLog.punch_type == "check_in",
            AttendanceLog.is_valid.is_(True),
        )
        .all()
    )
    checkin_by_emp: dict[int, AttendanceLog] = {}
    for log in today_logs:
        if log.punch_timestamp and log.punch_timestamp.date() == today:
            existing = checkin_by_emp.get(log.employee_id)
            if existing is None or log.punch_timestamp < existing.punch_timestamp:
                checkin_by_emp[log.employee_id] = log

    todays_checkins = [
        {
            "employee_id": eid,
            "name": emp_by_id[eid].full_name if eid in emp_by_id else f"#{eid}",
            "check_in_time": to_local(
                log.punch_timestamp,
                emp_by_id[eid].time_zone if eid in emp_by_id else None,
            ).strftime("%H:%M"),
            "status": _short_status(rec_by_emp.get(eid)),
            "is_wfh": emp_by_id[eid].employee_type == "wfh" if eid in emp_by_id else False,
        }
        for eid, log in sorted(checkin_by_emp.items(), key=lambda x: x[1].punch_timestamp)
    ]

    # ── 7-day present+wfh trend ──────────────────────────────────────
    trend_start = today - timedelta(days=6)
    trend_records = (
        db.query(
            AttendanceRecord.date,
            func.count(AttendanceRecord.id).label("count"),
        )
        .filter(
            AttendanceRecord.employee_id.in_(team_ids),
            AttendanceRecord.date >= trend_start,
            AttendanceRecord.date <= today,
            AttendanceRecord.status.in_(["present", "late", "wfh", "work_from_home"]),
        )
        .group_by(AttendanceRecord.date)
        .all()
    )
    count_by_date = {r.date: r.count for r in trend_records}
    weekly_trend = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "present": count_by_date.get(today - timedelta(days=i), 0),
        }
        for i in range(6, -1, -1)
    ]

    return {
        "summary": summary,
        "week_log": week_log,
        "todays_checkins": todays_checkins,
        "weekly_trend": weekly_trend,
    }


# ── Leave overview for manager's team ────────────────────────────────

@router.get("/leave-overview")
def leave_overview(
    current: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active/upcoming leaves for the manager's direct reports."""
    team_ids = [
        e.id for e in db.query(Employee).filter(
            Employee.reporting_manager_id == current.id,
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        ).all()
    ]
    if not team_ids:
        return []

    today = date_t.today()
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id.in_(team_ids),
            LeaveRequest.end_date >= today,
            LeaveRequest.status.in_(["approved", "pending", "cancel_pending"]),
        )
        .order_by(LeaveRequest.start_date)
        .limit(100)
        .all()
    )
    emp_map = {
        e.id: e.full_name
        for e in db.query(Employee).filter(Employee.id.in_(team_ids)).all()
    }
    return [
        {
            "id": lr.id,
            "employee_id": lr.employee_id,
            "employee_name": emp_map.get(lr.employee_id, f"#{lr.employee_id}"),
            "start_date": lr.start_date.isoformat() if lr.start_date else None,
            "end_date": lr.end_date.isoformat() if lr.end_date else None,
            "total_days": lr.total_days,
            "status": lr.status,
        }
        for lr in leaves
    ]


# ── CSV Export helpers ────────────────────────────────────────────────

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_CSV_HEADERS = [
    "employee_id", "employee_code", "employee_name", "manager_name",
    "department", "site",
    "attendance_date", "weekday_name",
    "check_in", "check_out", "worked_hours",
    "attendance_status", "attendance_state",
    "shift_name",
    "is_weekend", "is_holiday", "is_wfh",
    "comp_off_eligible", "comp_off_hours",
    "lop_applied", "remarks",
]


def _build_attendance_csv(
    db: Session,
    team: list,
    start: date_t,
    end: date_t,
    *,
    employee_id: Optional[int] = None,
    department_id: Optional[str] = None,
    attendance_status: Optional[str] = None,
) -> io.StringIO:
    """Build payroll-grade attendance CSV using batch queries (no N+1)."""
    if employee_id:
        team = [e for e in team if e.id == employee_id]
    if department_id:
        team = [e for e in team if str(e.department_id or "") == str(department_id)]

    team_ids = [e.id for e in team]
    emp_by_id = {e.id: e for e in team}

    if not team_ids:
        buf = io.StringIO()
        csv.DictWriter(buf, fieldnames=_CSV_HEADERS).writeheader()
        buf.seek(0)
        return buf

    # ── Batch: attendance records ────────────────────────────────────
    rec_query = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id.in_(team_ids),
            AttendanceRecord.date >= start,
            AttendanceRecord.date <= end,
        )
    )
    if attendance_status:
        rec_query = rec_query.filter(AttendanceRecord.status == attendance_status)
    records = rec_query.all()
    rec_idx: dict[tuple[int, date_t], AttendanceRecord] = {
        (r.employee_id, r.date): r for r in records
    }

    # ── Batch: first check-in / last check-out per employee per day ──
    ts_start = datetime.combine(start, datetime.min.time())
    ts_end   = datetime.combine(end,   datetime.max.time())
    logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id.in_(team_ids),
            AttendanceLog.punch_timestamp >= ts_start,
            AttendanceLog.punch_timestamp <= ts_end,
            AttendanceLog.is_valid.is_(True),
        )
        .all()
    )
    checkin_idx: dict[tuple[int, date_t], datetime] = {}
    checkout_idx: dict[tuple[int, date_t], datetime] = {}
    for log in logs:
        d   = log.punch_timestamp.date()
        key = (log.employee_id, d)
        if log.punch_type == "check_in":
            if key not in checkin_idx or log.punch_timestamp < checkin_idx[key]:
                checkin_idx[key] = log.punch_timestamp
        elif log.punch_type == "check_out":
            if key not in checkout_idx or log.punch_timestamp > checkout_idx[key]:
                checkout_idx[key] = log.punch_timestamp

    # ── Batch: holidays in range ─────────────────────────────────────
    holiday_dates = {
        h.date for h in
        db.query(Holiday.date).filter(Holiday.date >= start, Holiday.date <= end).all()
    }

    # ── Batch: shift assignments ─────────────────────────────────────
    shift_assignments = (
        db.query(EmployeeShift)
        .filter(
            EmployeeShift.employee_id.in_(team_ids),
            EmployeeShift.effective_from <= end,
        )
        .filter(
            (EmployeeShift.effective_to.is_(None)) | (EmployeeShift.effective_to >= start)
        )
        .all()
    )
    shift_ids = {es.shift_id for es in shift_assignments}
    shifts: dict[str, Shift] = (
        {s.id: s for s in db.query(Shift).filter(Shift.id.in_(shift_ids)).all()}
        if shift_ids else {}
    )
    emp_shifts: dict[int, list] = defaultdict(list)
    for es in shift_assignments:
        emp_shifts[es.employee_id].append(es)

    def _shift_name(emp_id: int, d: date_t) -> str:
        for es in sorted(emp_shifts[emp_id], key=lambda x: x.effective_from, reverse=True):
            if es.effective_from <= d and (es.effective_to is None or es.effective_to >= d):
                s = shifts.get(es.shift_id)
                return s.name if s else ""
        return ""

    # ── Batch: manager names ─────────────────────────────────────────
    mgr_ids = {e.reporting_manager_id for e in team if e.reporting_manager_id}
    mgr_map: dict[int, str] = (
        {m.id: m.full_name for m in db.query(Employee).filter(Employee.id.in_(mgr_ids)).all()}
        if mgr_ids else {}
    )

    # ── Batch: department names ──────────────────────────────────────
    dept_ids = {e.department_id for e in team if e.department_id}
    dept_map: dict[str, str] = {}
    if dept_ids:
        try:
            from app.models import Department
            dept_map = {
                d.id: d.name
                for d in db.query(Department).filter(Department.id.in_(dept_ids)).all()
            }
        except Exception:
            pass

    # ── Generate CSV ─────────────────────────────────────────────────
    delta      = (end - start).days + 1
    date_range = [start + timedelta(days=i) for i in range(delta)]

    buf    = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()

    for emp in sorted(team, key=lambda e: (e.last_name or "", e.first_name or "")):
        for d in date_range:
            rec = rec_idx.get((emp.id, d))
            if attendance_status and (rec is None or (rec.status or "").lower() != attendance_status.lower()):
                continue

            key        = (emp.id, d)
            is_weekend = d.weekday() in (5, 6)
            is_holiday = d in holiday_dates
            is_wfh     = (emp.employee_type == "wfh")
            status_str = (rec.status or "").lower() if rec else "not_marked"

            if rec is None:
                att_state = "absent"
            elif rec.check_in_time and not rec.check_out_time:
                att_state = "checked_in"
            elif rec.check_in_time and rec.check_out_time:
                att_state = "checked_out"
            else:
                att_state = "absent"

            comp_elig, comp_hrs = is_comp_off_eligible(
                is_tm=emp.is_tm,
                worked_on_date=d,
                worked_hours=float(rec.working_hours or 0) if rec else 0.0,
            )

            ci = checkin_idx.get(key)
            co = checkout_idx.get(key)

            writer.writerow({
                "employee_id":       emp.id,
                "employee_code":     emp.employee_code or "",
                "employee_name":     emp.full_name,
                "manager_name":      mgr_map.get(emp.reporting_manager_id, "") if emp.reporting_manager_id else "",
                "department":        dept_map.get(emp.department_id, "") if emp.department_id else "",
                "site":              emp.location or "",
                "attendance_date":   d.isoformat(),
                "weekday_name":      _WEEKDAY_NAMES[d.weekday()],
                "check_in":          ci.strftime("%H:%M:%S") if ci else "",
                "check_out":         co.strftime("%H:%M:%S") if co else "",
                "worked_hours":      f"{float(rec.working_hours or 0):.2f}" if rec else "0.00",
                "attendance_status": status_str or "not_marked",
                "attendance_state":  att_state,
                "shift_name":        _shift_name(emp.id, d),
                "is_weekend":        "Yes" if is_weekend else "No",
                "is_holiday":        "Yes" if is_holiday else "No",
                "is_wfh":            "Yes" if is_wfh else "No",
                "comp_off_eligible": "Yes" if comp_elig else "No",
                "comp_off_hours":    f"{comp_hrs:.2f}" if comp_elig else "0.00",
                "lop_applied":       "Yes" if (rec and rec.lop_applied) else "No",
                "remarks":           (rec.lop_type or "") if rec else "",
            })

    buf.seek(0)
    return buf


# ── CSV Export Endpoints ──────────────────────────────────────────────

@router.get("/attendance/export/weekly")
def export_weekly_attendance(
    start_date: Optional[date_t] = Query(None, description="Start of export range (default: current week Mon)"),
    end_date:   Optional[date_t] = Query(None, description="End of export range   (default: current week Sun)"),
    employee_id:       Optional[int] = Query(None),
    department_id:     Optional[str] = Query(None),
    attendance_status: Optional[str] = Query(None, description="Filter: present|absent|wfh|on_leave|half_day|holiday"),
    current: Employee = Depends(role_required("manager", "admin")),
    db: Session = Depends(get_db),
):
    """Download weekly attendance CSV. Admin gets all employees; manager gets direct reports."""
    today = date_t.today()
    if start_date is None:
        start_date = today - timedelta(days=today.weekday())   # Monday
    if end_date is None:
        end_date = start_date + timedelta(days=6)              # Sunday

    q = db.query(Employee).filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
    if current.role and current.role.name != "admin":
        q = q.filter(Employee.reporting_manager_id == current.id)
    team = q.all()
    buf  = _build_attendance_csv(
        db, team, start_date, end_date,
        employee_id=employee_id,
        department_id=department_id,
        attendance_status=attendance_status,
    )
    fname = f"attendance_weekly_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/attendance/export/monthly")
def export_monthly_attendance(
    year:  Optional[int] = Query(None, description="Year  (default: current year)"),
    month: Optional[int] = Query(None, description="Month 1–12 (default: current month)"),
    employee_id:       Optional[int] = Query(None),
    department_id:     Optional[str] = Query(None),
    attendance_status: Optional[str] = Query(None),
    current: Employee = Depends(role_required("manager", "admin")),
    db: Session = Depends(get_db),
):
    """Download monthly attendance CSV. Admin gets all employees; manager gets direct reports."""
    today = date_t.today()
    y = year  or today.year
    m = month or today.month
    _, last_day = calendar.monthrange(y, m)
    start_date  = date_t(y, m, 1)
    end_date    = date_t(y, m, last_day)

    q = db.query(Employee).filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
    if current.role and current.role.name != "admin":
        q = q.filter(Employee.reporting_manager_id == current.id)
    team = q.all()
    buf  = _build_attendance_csv(
        db, team, start_date, end_date,
        employee_id=employee_id,
        department_id=department_id,
        attendance_status=attendance_status,
    )
    fname = f"attendance_{y}_{m:02d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
