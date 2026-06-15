"""Utilization engine routes.

Utilization % = Billable Hours / Available Hours × 100
Available Hours = working_days × 8 (weekends excluded)

Endpoints:
  GET  /utilization/me           — own utilization summary (employee)
  GET  /utilization/team         — team utilization (manager/admin)
"""
from __future__ import annotations

from datetime import date as date_t, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AttendanceRecord, Department, Designation, Employee, Timesheet, TimesheetEntry
from app.schemas.timesheet import TeamUtilizationOut, UtilizationEmployeeOut


router = APIRouter(prefix="/utilization", tags=["utilization"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _working_days(start: date_t, end: date_t) -> int:
    """Count Mon–Fri days in [start, end] inclusive."""
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


def _compute_employee_utilization(
    db: Session,
    employee: Employee,
    start: date_t,
    end: date_t,
) -> UtilizationEmployeeOut:
    working_days   = _working_days(start, end)
    available_hours = working_days * 8.0

    # Aggregate timesheet entries in the period
    entries = (
        db.query(TimesheetEntry)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .filter(
            TimesheetEntry.employee_id == employee.id,
            TimesheetEntry.entry_date >= start,
            TimesheetEntry.entry_date <= end,
            Timesheet.status.in_(["approved", "manager_approved", "locked", "pending", "pending_review"]),
        )
        .all()
    )

    billable_hours     = sum(e.logged_hours or 0.0 for e in entries if e.is_billable)
    non_billable_hours = sum(e.logged_hours or 0.0 for e in entries if not e.is_billable)
    total_logged       = billable_hours + non_billable_hours

    # Overtime from attendance records
    att_recs = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.date >= start,
            AttendanceRecord.date <= end,
        )
        .all()
    )
    overtime_hours = sum(r.overtime_hours or 0.0 for r in att_recs)

    # Check if any submitted timesheet exists for this period
    ts_count = (
        db.query(Timesheet)
        .filter(
            Timesheet.employee_id == employee.id,
            Timesheet.period_start <= end,
            Timesheet.period_end >= start,
            Timesheet.status.notin_(["draft"]),
        )
        .count()
    )
    missing_timesheet = ts_count == 0

    util_pct = round(billable_hours / available_hours * 100, 1) if available_hours > 0 else 0.0
    billable_pct = round(billable_hours / total_logged * 100, 1) if total_logged > 0 else 0.0

    dept_name = employee.department.name if employee.department else None
    desig_name = employee.designation.title if employee.designation else None

    return UtilizationEmployeeOut(
        employee_id=employee.id,
        employee_name=employee.full_name,
        employee_code=employee.employee_code,
        department=dept_name,
        designation=desig_name,
        available_hours=available_hours,
        billable_hours=round(billable_hours, 2),
        non_billable_hours=round(non_billable_hours, 2),
        total_logged_hours=round(total_logged, 2),
        utilization_pct=util_pct,
        billable_pct=billable_pct,
        overtime_hours=round(overtime_hours, 2),
        missing_timesheet=missing_timesheet,
    )


@router.get("/me", response_model=UtilizationEmployeeOut)
def my_utilization(
    start: date_t = Query(..., description="Period start (YYYY-MM-DD)"),
    end: date_t   = Query(..., description="Period end (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if (end - start).days > 93:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 93 days.")
    return _compute_employee_utilization(db, user, start, end)


@router.get("/team", response_model=TeamUtilizationOut)
def team_utilization(
    start: date_t          = Query(..., description="Period start (YYYY-MM-DD)"),
    end: date_t            = Query(..., description="Period end (YYYY-MM-DD)"),
    department_id: Optional[str] = Query(None),
    employee_id: Optional[int]   = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = _role(user)
    if role not in {"manager", "admin", "finance"}:
        raise HTTPException(status_code=403, detail="Manager, admin, or finance access required.")
    if (end - start).days > 93:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 93 days.")

    q = db.query(Employee).filter(
        Employee.is_deleted.is_(False),
        Employee.employment_status == "active",
    )
    if role == "manager":
        q = q.filter(Employee.reporting_manager_id == user.id)
    if department_id:
        q = q.filter(Employee.department_id == department_id)
    if employee_id:
        q = q.filter(Employee.id == employee_id)

    employees = q.all()

    rows = [_compute_employee_utilization(db, emp, start, end) for emp in employees]

    total_available = sum(r.available_hours for r in rows)
    total_billable  = sum(r.billable_hours for r in rows)
    total_non_bill  = sum(r.non_billable_hours for r in rows)
    agg_util_pct    = round(total_billable / total_available * 100, 1) if total_available > 0 else 0.0

    return TeamUtilizationOut(
        period_start=start,
        period_end=end,
        total_employees=len(rows),
        available_hours=round(total_available, 2),
        billable_hours=round(total_billable, 2),
        non_billable_hours=round(total_non_bill, 2),
        utilization_pct=agg_util_pct,
        underutilized=sum(1 for r in rows if r.utilization_pct < 60),
        overallocated=sum(1 for r in rows if r.utilization_pct > 100),
        missing_submissions=sum(1 for r in rows if r.missing_timesheet),
        employees=rows,
    )
