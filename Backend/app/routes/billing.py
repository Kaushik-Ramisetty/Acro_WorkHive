"""Billing + Project Costing routes (PMO / Finance).

Revenue   = billable_hours × project.billing_rate
Cost      = total_hours × employee.hourly_cost_rate  (fallback 0)
Profit %  = (revenue − billable_cost) / revenue × 100

Endpoints:
  GET  /billing/summary        — project billing summary for a date range
  GET  /billing/export         — CSV export of billing data
  GET  /billing/project-costing — per-employee cost breakdown for a date range
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Department, Designation, Employee, Project, Task, Timesheet, TimesheetEntry
from app.schemas.timesheet import BillingSummaryOut, ProjectCostRow, ProjectCostingOut, ResourceCostRow


router = APIRouter(prefix="/billing", tags=["billing"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _require_finance_access(user: Employee) -> None:
    if _role(user) not in {"admin", "finance"}:
        raise HTTPException(status_code=403, detail="Finance or admin access required.")


def _get_approved_entries(db: Session, start: date_t, end: date_t):
    """Return all timesheet entries in the period from approved/locked timesheets."""
    return (
        db.query(TimesheetEntry)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .filter(
            TimesheetEntry.entry_date >= start,
            TimesheetEntry.entry_date <= end,
            Timesheet.status.in_(["approved", "manager_approved", "locked"]),
        )
        .all()
    )


@router.get("/summary", response_model=BillingSummaryOut)
def billing_summary(
    start: date_t = Query(..., description="Period start (YYYY-MM-DD)"),
    end: date_t   = Query(..., description="Period end (YYYY-MM-DD)"),
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    _require_finance_access(user)
    if (end - start).days > 366:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 366 days.")

    entries = _get_approved_entries(db, start, end)

    # Group by project
    proj_map: dict[str, list[TimesheetEntry]] = {}
    no_project_entries: list[TimesheetEntry] = []
    for e in entries:
        if e.project_id:
            proj_map.setdefault(e.project_id, []).append(e)
        else:
            no_project_entries.append(e)

    if project_id:
        proj_map = {k: v for k, v in proj_map.items() if k == project_id}

    rows: list[ProjectCostRow] = []
    total_billable     = 0.0
    total_non_billable = 0.0
    total_revenue      = 0.0

    for pid, ents in proj_map.items():
        proj = db.get(Project, pid)
        if not proj:
            continue
        bill_h  = sum(e.logged_hours or 0.0 for e in ents if e.is_billable)
        nbill_h = sum(e.logged_hours or 0.0 for e in ents if not e.is_billable)
        rate     = proj.billing_rate or 0.0
        revenue  = round(bill_h * rate, 2)
        headcount = len({e.employee_id for e in ents if e.employee_id})

        total_billable     += bill_h
        total_non_billable += nbill_h
        total_revenue      += revenue

        rows.append(ProjectCostRow(
            project_id=pid,
            project_name=proj.name,
            client_name=proj.client_name,
            is_billable=proj.is_billable,
            billing_rate=proj.billing_rate,
            total_hours=round(bill_h + nbill_h, 2),
            billable_hours=round(bill_h, 2),
            non_billable_hours=round(nbill_h, 2),
            revenue=revenue,
            headcount=headcount,
        ))

    rows.sort(key=lambda r: r.revenue, reverse=True)

    return BillingSummaryOut(
        period_start=start,
        period_end=end,
        total_billable_hours=round(total_billable, 2),
        total_non_billable_hours=round(total_non_billable, 2),
        total_revenue=round(total_revenue, 2),
        project_count=len(rows),
        projects=rows,
    )


@router.get("/export")
def billing_export(
    start: date_t = Query(..., description="Period start (YYYY-MM-DD)"),
    end: date_t   = Query(..., description="Period end (YYYY-MM-DD)"),
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    _require_finance_access(user)

    entries = _get_approved_entries(db, start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Employee ID", "Employee Name", "Employee Code",
        "Department", "Designation",
        "Project ID", "Project Name", "Client", "Task",
        "Logged Hours", "Is Billable", "Billing Rate", "Revenue",
        "Timesheet ID", "Timesheet Status",
    ])

    for e in entries:
        emp  = db.get(Employee, e.employee_id) if e.employee_id else None
        proj = db.get(Project, e.project_id)   if e.project_id   else None
        task = db.get(Task, e.task_id)         if e.task_id      else None
        ts   = db.get(Timesheet, e.timesheet_id) if e.timesheet_id else None
        dept_name  = emp.department.name    if emp and emp.department  else ""
        desig_name = emp.designation.title  if emp and emp.designation else ""
        rate       = proj.billing_rate or 0.0 if proj else 0.0
        revenue    = round((e.logged_hours or 0.0) * rate, 2) if e.is_billable else 0.0
        writer.writerow([
            str(e.entry_date),
            emp.id          if emp  else "",
            emp.full_name   if emp  else "",
            emp.employee_code if emp else "",
            dept_name,
            desig_name,
            proj.id         if proj else "",
            proj.name       if proj else "",
            proj.client_name if proj else "",
            task.name       if task else "",
            e.logged_hours or 0.0,
            "Yes" if e.is_billable else "No",
            rate,
            revenue,
            e.timesheet_id or "",
            ts.status if ts else "",
        ])

    output.seek(0)
    filename = f"billing_{start}_{end}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/project-costing", response_model=ProjectCostingOut)
def project_costing(
    start: date_t = Query(..., description="Period start (YYYY-MM-DD)"),
    end: date_t   = Query(..., description="Period end (YYYY-MM-DD)"),
    project_id: Optional[str]    = Query(None),
    department_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    _require_finance_access(user)
    if (end - start).days > 366:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 366 days.")

    entries = _get_approved_entries(db, start, end)

    if project_id:
        entries = [e for e in entries if e.project_id == project_id]

    # Group by employee
    emp_map: dict[int, list[TimesheetEntry]] = {}
    for e in entries:
        if e.employee_id:
            emp_map.setdefault(e.employee_id, []).append(e)

    resource_rows: list[ResourceCostRow] = []
    total_cost         = 0.0
    total_billable_cost = 0.0
    total_revenue      = 0.0

    for eid, ents in emp_map.items():
        emp = db.get(Employee, eid)
        if not emp:
            continue
        if department_id and emp.department_id != department_id:
            continue

        # hourly_cost_rate stored on employee — fallback 0
        cost_rate = float(getattr(emp, "hourly_cost_rate", None) or 0.0)
        bill_h    = sum(e.logged_hours or 0.0 for e in ents if e.is_billable)
        nbill_h   = sum(e.logged_hours or 0.0 for e in ents if not e.is_billable)
        total_h   = bill_h + nbill_h

        emp_cost      = round(total_h   * cost_rate, 2)
        bill_cost     = round(bill_h    * cost_rate, 2)

        # Revenue: sum across each entry's project billing_rate
        revenue = 0.0
        for e in ents:
            if e.is_billable and e.project_id:
                proj = db.get(Project, e.project_id)
                if proj and proj.billing_rate:
                    revenue += (e.logged_hours or 0.0) * proj.billing_rate
        revenue = round(revenue, 2)

        total_cost         += emp_cost
        total_billable_cost += bill_cost
        total_revenue      += revenue

        # available hours for utilization
        from datetime import timedelta as td
        avail = 0
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                avail += 8
            cur += td(days=1)

        util_pct = round(bill_h / avail * 100, 1) if avail > 0 else 0.0
        dept_name  = emp.department.name   if emp.department   else None
        desig_name = emp.designation.title if emp.designation  else None

        resource_rows.append(ResourceCostRow(
            employee_id=eid,
            employee_name=emp.full_name,
            employee_code=emp.employee_code,
            department=dept_name,
            designation=desig_name,
            hourly_cost_rate=cost_rate,
            total_hours=round(total_h, 2),
            billable_hours=round(bill_h, 2),
            non_billable_hours=round(nbill_h, 2),
            total_cost=emp_cost,
            billable_cost=bill_cost,
            utilization_pct=util_pct,
        ))

    resource_rows.sort(key=lambda r: r.total_cost, reverse=True)

    margin_pct = 0.0
    if total_revenue > 0:
        margin_pct = round((total_revenue - total_billable_cost) / total_revenue * 100, 1)

    return ProjectCostingOut(
        period_start=start,
        period_end=end,
        total_cost=round(total_cost, 2),
        total_billable_cost=round(total_billable_cost, 2),
        total_revenue=round(total_revenue, 2),
        profit_margin_pct=margin_pct,
        resources=resource_rows,
    )
