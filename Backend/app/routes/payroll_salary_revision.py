"""Salary Revision API — additive endpoints for salary hike / revision flow.

Prefix : /payroll
Auth   : finance or admin role (same as finance.py)

Endpoints
---------
POST /payroll/salary-revisions
    Create a new salary revision (hike) for an employee.
    Deactivates the current active salary structure and assignment, then creates
    a new one.  Writes a SalaryRevisionLog audit entry.  Does NOT touch any
    existing payroll runs, payroll records, or payslips.

GET  /payroll/salary-revisions/{employee_id}
    Return the full salary revision history for an employee, newest first.

GET  /payroll/salary-revisions/{employee_id}/prorated/{month}/{year}
    Helper — returns a prorated-gross breakdown when a revision falls mid-month.
    Read-only / no side-effects.  Useful for Finance to preview impact before
    generating payroll.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.schemas.payroll import SalaryRevisionCreate, SalaryRevisionOut
from app.services import payroll_service

router = APIRouter(
    prefix="/payroll",
    tags=["Payroll - Salary Revisions"],
    dependencies=[Depends(role_required("finance", "admin"))],
)

_FinanceUser = Depends(role_required("finance", "admin"))

SALARY_REVISION_WORKFLOW_REQUIRED = (
    "Salary revisions must follow the HR request -> Finance review -> "
    "Finance Head approval workflow. Direct salary revision writes are not allowed."
)


# ─── POST /payroll/salary-revisions ──────────────────────────────────────────

@router.post(
    "/salary-revisions",
    response_model=SalaryRevisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a salary revision (hike) for an employee",
)
def create_salary_revision(
    body: SalaryRevisionCreate,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceUser,
):
    """
    Apply a salary hike for an employee effective from a given date.

    What happens internally:
    - Current active `salary_structures` row is deactivated (is_active=False).
    - New `salary_structures` row is created from the new annual CTC.
    - `employee_salary_assignments`:
        - Old ACTIVE assignment → effective_to = effective_from - 1 day,
                                   status = SUPERSEDED.
        - New ACTIVE assignment → effective_from = hike date, effective_to = NULL.
    - `salary_revision_logs` audit row is written.

    Old salary data, existing payroll runs, and existing payslips are NEVER
    modified.  Historical payroll for periods before the hike date continues to
    use the original salary via the effective_from date-range lookup.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=SALARY_REVISION_WORKFLOW_REQUIRED,
    )


# ─── GET /payroll/salary-revisions/{employee_id} ─────────────────────────────

@router.get(
    "/salary-revisions/{employee_id}",
    summary="List salary revision history for an employee",
)
def list_employee_salary_revisions(
    employee_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: Employee = _FinanceUser,
):
    """
    Return the salary revision history for an employee, newest first.

    Each entry shows the before/after CTC, component snapshots, effective date,
    and who made the revision.  Old payslips and payroll records are unaffected
    — they reference their original salary_structure_id permanently.
    """
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(
            status_code=404, detail=f"Employee {employee_id} not found"
        )

    revisions = payroll_service.list_salary_revisions(
        db, employee_id=employee_id, limit=limit, offset=offset
    )

    result = []
    for rev in revisions:
        revised_by = rev.revised_by
        result.append({
            "id": rev.id,
            "employee_id": rev.employee_id,
            "employee_name": (
                f"{emp.first_name} {emp.last_name or ''}".strip()
            ),
            "employee_code": (
                emp.employee_code or f"EMP{emp.id:04d}"
            ),
            "old_annual_ctc": rev.old_annual_ctc,
            "new_annual_ctc": rev.new_annual_ctc,
            "ctc_difference": rev.ctc_difference,
            "ctc_change_pct": rev.ctc_change_pct,
            "old_gross_monthly": rev.old_gross_monthly,
            "new_gross_monthly": rev.new_gross_monthly,
            "old_net_monthly": rev.old_net_monthly,
            "new_net_monthly": rev.new_net_monthly,
            "old_basic": rev.old_basic,
            "new_basic": rev.new_basic,
            "old_hra": rev.old_hra,
            "new_hra": rev.new_hra,
            "old_pf_employee": rev.old_pf_employee,
            "new_pf_employee": rev.new_pf_employee,
            "old_tds": rev.old_tds,
            "new_tds": rev.new_tds,
            "effective_from": (
                rev.effective_from.isoformat() if rev.effective_from else None
            ),
            "revision_reason": rev.revision_reason,
            "revised_by_id": rev.revised_by_id,
            "revised_by_name": (
                f"{revised_by.first_name} {revised_by.last_name or ''}".strip()
                if revised_by else "—"
            ),
            "old_salary_structure_id": rev.old_salary_structure_id,
            "new_salary_structure_id": rev.new_salary_structure_id,
            "created_at": (
                rev.created_at.isoformat() if rev.created_at else None
            ),
        })
    return result


# ─── GET /payroll/salary-revisions/{employee_id}/prorated/{month}/{year} ─────

@router.get(
    "/salary-revisions/{employee_id}/prorated/{month}/{year}",
    summary="Preview prorated salary breakdown if a revision falls mid-month",
)
def get_prorated_salary_preview(
    employee_id: int,
    month: int,
    year: int,
    db: Session = Depends(get_db),
    _: Employee = _FinanceUser,
):
    """
    Read-only helper: returns the prorated gross breakdown for a given month/year.

    Useful for Finance to preview the salary impact of a mid-month hike before
    payroll generation.  Does NOT modify any data.

    If no mid-month revision exists, is_prorated=False and prorated_gross equals
    the full-month gross under the current salary structure.

    NOTE: Prorated statutory deductions (PF, ESI, PT, TDS) are not included —
    see the TODO in calculate_prorated_salary_if_revision_mid_month for details.
    """
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="year out of valid range")

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(
            status_code=404, detail=f"Employee {employee_id} not found"
        )

    result = payroll_service.calculate_prorated_salary_if_revision_mid_month(
        db=db,
        employee_id=employee_id,
        payroll_month=month,
        payroll_year=year,
    )
    result["employee_id"] = employee_id
    result["employee_name"] = f"{emp.first_name} {emp.last_name or ''}".strip()
    result["month"] = month
    result["year"] = year
    return result
