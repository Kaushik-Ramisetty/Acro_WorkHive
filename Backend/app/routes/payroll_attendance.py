"""Payroll Attendance Summary API — bridge endpoints.

╔══════════════════════════════════════════════════════════════════════════╗
║  TEMPORARY PAYROLL BRIDGE                                                 ║
║  These endpoints allow HR/Admin to manage the monthly attendance summary  ║
║  until the Attendance and Timesheet modules are ready to populate it      ║
║  automatically.  No Attendance/Timesheet module code was changed.        ║
╚══════════════════════════════════════════════════════════════════════════╝

Endpoints:
  GET  /payroll/attendance-summary             — readiness dashboard for HR
  POST /payroll/attendance-summary/manual      — upsert one employee's row (test)
  POST /payroll/attendance-summary/validate    — validate all rows for month/year
  POST /payroll/attendance-summary/freeze      — freeze & notify Finance
"""
from __future__ import annotations

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, role_required
from app.models.employee import Employee
from app.models.payroll import PayrollRun, PayrollRunEmployee
from app.services import payroll_attendance_bridge as _bridge

# ── Role guards ───────────────────────────────────────────────────────────────
# HR and Admin can read and write the attendance summary.
# Finance / Finance Head may read (they are consumers, not producers).
_READ_ROLES  = Depends(role_required("admin", "hr", "finance", "finance_head"))
_WRITE_ROLES = Depends(role_required("admin", "hr"))

router = APIRouter(prefix="/payroll", tags=["Payroll Attendance Bridge"])


# ── Request/Response schemas ──────────────────────────────────────────────────

class ManualSummaryIn(BaseModel):
    """Input for a single employee's manual monthly attendance summary.

    ── TEMPORARY PAYROLL BRIDGE ──
    Use this endpoint for testing until Attendance/Timesheet modules integrate.
    """
    employee_id: int
    month: int = Field(..., ge=1, le=12, description="Calendar month (1–12)")
    year: int = Field(..., ge=2020, le=2100)
    total_working_days: int = Field(..., ge=0, le=31)
    present_days: int = Field(..., ge=0, le=31)
    leave_days: int = Field(default=0, ge=0, le=31)
    payable_days: float = Field(..., ge=0.0, le=31.0)
    lop_days: Optional[int] = Field(
        default=None, ge=0, le=31,
        description=(
            "LOP (Loss of Pay) days. When provided, stored with lop_source='Manual Override' "
            "and protected from Leave Management sync overwrites. Omit to let LOP be "
            "computed automatically from approved unpaid leave requests."
        ),
    )
    approved_timesheet_hours: float = Field(default=0.0, ge=0.0)
    timesheet_status: str = Field(default="pending")


class FreezeIn(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2100)


class ValidateIn(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2100)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/attendance-summary/open-month",
    summary="[HR Payroll Dashboard] Auto-detect the current open payroll month",
    tags=["Payroll Attendance Bridge"],
)
def get_open_payroll_month(
    db: Session = Depends(get_db),
    _: Employee = _READ_ROLES,
):
    """Return the auto-detected open (non-frozen) payroll month.

    Used by the HR dashboard to auto-load the correct month on page load
    without requiring manual month selection or a payroll run ID.

    Logic:
    - Finds the latest month/year in monthly_attendance_summary where at
      least one row is not yet frozen (HR still needs to validate/freeze).
    - Falls back to the current calendar month when no data exists.

    Response also includes available_months (newest-first) listing every
    month that has at least one row in monthly_attendance_summary — used
    to populate the month/year selector dropdown on the HR dashboard.
    """
    return _bridge.get_open_month(db)


@router.get(
    "/attendance-summary",
    summary="[HR Payroll Dashboard] Monthly attendance readiness summary",
    tags=["Payroll Attendance Bridge"],
)
def get_attendance_summary(
    month: int = Query(..., ge=1, le=12, description="1–12"),
    year: int = Query(..., ge=2020, le=2100),
    db: Session = Depends(get_db),
    _: Employee = _READ_ROLES,
):
    """Return aggregated attendance readiness for HR payroll dashboard.

    Shows per-employee status, validation results, frozen count, and
    whether the attendance is ready for Finance to run payroll.

    ── TEMPORARY PAYROLL BRIDGE ──
    In production this data will be written by the Attendance/Timesheet modules.
    """
    return _bridge.get_summary(db, month=month, year=year)


@router.post(
    "/attendance-summary/manual",
    status_code=status.HTTP_200_OK,
    summary="[Test Bridge] Manually upsert one employee's monthly attendance summary",
    tags=["Payroll Attendance Bridge"],
)
def upsert_manual_summary(
    payload: ManualSummaryIn,
    db: Session = Depends(get_db),
    actor: Employee = _WRITE_ROLES,
):
    """Create or update a monthly attendance summary row for one employee.

    ── TEMPORARY PAYROLL BRIDGE ──
    Only for testing until the Attendance/Timesheet modules are ready.
    Allowed roles: admin, hr.

    Notes:
    - Cannot update a frozen row.
    - Resets validation_status to 'pending' — re-validate after every edit.
    - lop_days: when provided, stored as a Manual Override — not overwritten by
      Leave Management syncs. When omitted, LOP is computed from approved unpaid leaves.
    - payable_days formula: caller supplies the value directly, or pass payable_days=0
      and lop_days to let the service recompute (working_days - lop_days).
    """
    # Verify the employee exists
    emp = db.query(Employee).filter(
        Employee.id == payload.employee_id,
        Employee.is_deleted.is_(False),
    ).first()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {payload.employee_id} not found.",
        )

    try:
        row = _bridge.upsert_manual_summary(
            db,
            employee_id=payload.employee_id,
            month=payload.month,
            year=payload.year,
            total_working_days=payload.total_working_days,
            present_days=payload.present_days,
            leave_days=payload.leave_days,
            payable_days=payload.payable_days,
            lop_days=payload.lop_days,
            approved_timesheet_hours=payload.approved_timesheet_hours,
            timesheet_status=payload.timesheet_status,
            actor=actor,
        )
        db.commit()
        db.refresh(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return {
        "ok": True,
        "id": row.id,
        "employee_id": row.employee_id,
        "month": row.month,
        "year": row.year,
        "attendance_status": row.attendance_status,
        "validation_status": row.validation_status,
        "is_ready_for_payroll": row.is_ready_for_payroll,
        "is_frozen": row.is_frozen,
        "message": "Attendance summary saved. Run validate to check before freezing.",
    }


@router.post(
    "/attendance-summary/seed-dummy",
    status_code=status.HTTP_410_GONE,
    summary="[Disabled] Dummy attendance summary seeding",
    tags=["Payroll Attendance Bridge"],
)
def seed_dummy_attendance_summary(
    month: int = Query(..., ge=1, le=12, description="Calendar month (1–12)"),
    year: int = Query(..., ge=2020, le=2100, description="Calendar year"),
    db: Session = Depends(get_db),
    actor: Employee = _WRITE_ROLES,
):
    """Dummy attendance seeding is disabled for production payroll inputs."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Dummy attendance summary seeding is disabled. Use the manual attendance "
            "summary endpoint or the Attendance module integration; LOP is supplied "
            "only by Leave Management."
        ),
    )


@router.post(
    "/attendance-summary/validate",
    status_code=status.HTTP_200_OK,
    summary="[HR] Validate monthly attendance summary for all employees",
    tags=["Payroll Attendance Bridge"],
)
def validate_attendance_summary(
    payload: ValidateIn,
    db: Session = Depends(get_db),
    actor: Employee = _WRITE_ROLES,
):
    """Validate all monthly attendance rows for a given month/year.

    Validation rules checked:
      V1  Missing summary for an active employee
      V2  Negative days (present/leave/lop/payable)
      V3  Day sum overflow (present + leave + lop > total_working_days)
      V4  Zero total_working_days
      V5  payable_days > total_working_days
      V6  Timesheet still pending (warning, non-blocking)

    After calling this endpoint:
      - Each row gets validation_status = 'passed' | 'failed'
      - is_ready_for_payroll = True only if issues_count = 0
      - can_freeze = True when ALL employees pass validation

    The Freeze endpoint will re-check readiness and block if any fail.
    """
    try:
        result = _bridge.validate_summary(
            db, month=payload.month, year=payload.year, actor=actor
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


@router.post(
    "/attendance-summary/freeze",
    status_code=status.HTTP_200_OK,
    summary="[HR] Freeze payroll input — unlocks payroll generation for Finance",
    tags=["Payroll Attendance Bridge"],
)
def freeze_attendance_summary(
    payload: FreezeIn,
    db: Session = Depends(get_db),
    actor: Employee = _WRITE_ROLES,
):
    """Freeze attendance for a month/year.

    Pre-conditions (enforced):
      - All active employees must have is_ready_for_payroll = True.
      - Rows must have been validated (validation_status = 'passed').
      - No employee may be missing a summary row.

    After freezing:
      - All rows are marked is_frozen = True.
      - attendance_status → 'finalized'.
      - Finance and Finance Head users receive an in-app notification:
        "Attendance finalized for <Month Year>. Payroll ready for processing."
      - Payroll generation unblocked (payroll_service.py check passes).

    ⚠ Freeze is irreversible via this API. Contact a developer to manually
    unfreeze a row for re-testing (set is_frozen=0, is_ready_for_payroll=0).
    """
    try:
        result = _bridge.freeze_attendance(
            db, month=payload.month, year=payload.year, actor=actor
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# DEV-ONLY — TEMPORARY FOR PAYROLL TESTING.
# REMOVE AFTER REAL ATTENDANCE/TIMESHEET INTEGRATION.
# ─────────────────────────────────────────────────────────────────────────────

class ResetFreezeIn(BaseModel):
    """Input for DEV-only attendance freeze reset.

    TEMPORARY FOR PAYROLL TESTING. REMOVE AFTER REAL ATTENDANCE/TIMESHEET INTEGRATION.
    """
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2100)


@router.post(
    "/attendance-summary/reset-freeze",
    status_code=status.HTTP_200_OK,
    summary="[DEV ONLY] Reset attendance freeze for re-testing — not for production use",
    tags=["Payroll Attendance Bridge"],
)
def reset_attendance_freeze(
    payload: ResetFreezeIn,
    db: Session = Depends(get_db),
    actor: Employee = Depends(role_required("admin", "hr")),
):
    """[DEV ONLY] Unfreeze attendance summary rows so the freeze flow can be re-tested.

    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  TEMPORARY FOR PAYROLL TESTING.                                          ║
    ║  REMOVE AFTER REAL ATTENDANCE/TIMESHEET INTEGRATION.                     ║
    ╚══════════════════════════════════════════════════════════════════════════╝

    Allowed roles: admin, hr.

    This endpoint ONLY updates monthly_attendance_summary rows:
      is_frozen=False, attendance_status='validated', timesheet_status='approved',
      validation_status='passed', issues_count=0, is_ready_for_payroll=True,
      finalized_by=NULL, finalized_at=NULL.

    It does NOT delete attendance rows, payroll records, notifications, salary
    structures, finance approvals, or any employee data.

    Audit log entry: ATTENDANCE_FREEZE_RESET
    """
    try:
        result = _bridge.reset_freeze_summary(
            db, month=payload.month, year=payload.year, actor=actor
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Read-only: per-employee payroll breakdown for a given payroll run.
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/employees",
    summary="Per-employee payroll breakdown for a payroll run",
    tags=["Payroll Attendance Bridge"],
)
def get_payroll_run_employees(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = _READ_ROLES,
):
    """Return per-employee payroll records for a given payroll_run_id.

    Read-only endpoint. Restricted to Finance, Finance Head, HR, and Admin
    roles — regular employees cannot access cross-employee salary data here.
    Employee self-service payslip access is handled via /employee/payroll/payslips.

    Column notes:
    - gross_earnings  is the canonical gross (gross_salary is kept in sync as a legacy alias).
    - employee_pf     is the canonical employee PF column (pf_employee is the legacy alias).
    - net_pay         is the canonical net (net_salary is the legacy alias).
    """
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")

    employees = (
        db.query(PayrollRunEmployee)
        .filter(PayrollRunEmployee.run_id == run_id)
        .order_by(PayrollRunEmployee.employee_id)
        .all()
    )

    result = []
    for rec in employees:
        emp = rec.employee
        dept = None
        if emp and emp.department_id:
            from app.models.department import Department
            d = db.query(Department).filter(Department.id == emp.department_id).first()
            dept = d.name if d else None
        result.append({
            "employee_id":       rec.employee_id,
            "employee_code":     emp.employee_code if emp else None,
            "employee_name":     ((emp.first_name or "") + " " + (emp.last_name or "")).strip() if emp else None,
            "department":        dept,
            "lop_days":          rec.lop_days,
            "gross_earnings":    rec.gross_earnings,
            "lop_deduction":     rec.lop_deduction,
            "employee_pf":       rec.employee_pf,
            "professional_tax":  rec.professional_tax,
            "tds":               rec.tds,
            "total_deductions":  rec.total_deductions,
            "net_pay":           rec.net_pay,
            "record_status":     rec.record_status,
        })
    return result
