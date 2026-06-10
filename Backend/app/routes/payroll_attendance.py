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

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.services import payroll_attendance_bridge as _bridge

# ── Role guards ───────────────────────────────────────────────────────────────
# Admin and Finance can read the summary.
# Admin only may create manual entries and freeze (HR action).
# Finance may read but cannot write (they are consumers, not producers).
_READ_ROLES  = Depends(role_required("admin", "finance", "finance_head"))
_WRITE_ROLES = Depends(role_required("admin"))   # HR/Admin only

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
    lop_days: int = Field(default=0, ge=0, le=31)
    payable_days: float = Field(..., ge=0.0, le=31.0)
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
    Allowed roles: admin.

    Notes:
    - Cannot update a frozen row.
    - Resets validation_status to 'pending' — re-validate after every edit.
    - payable_days formula used here: caller supplies the value directly.
      Typical formula: present_days + approved_leave_days
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
            lop_days=payload.lop_days,
            payable_days=payload.payable_days,
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
    status_code=status.HTTP_200_OK,
    summary="[HR] Seed dummy attendance summary for all active employees",
    tags=["Payroll Attendance Bridge"],
)
def seed_dummy_attendance_summary(
    month: int = Query(..., ge=1, le=12, description="Calendar month (1–12)"),
    year: int = Query(..., ge=2020, le=2100, description="Calendar year"),
    db: Session = Depends(get_db),
    actor: Employee = _WRITE_ROLES,
):
    """Seed dummy attendance summary for all active employees (month/year via query params).

    ── TEMPORARY PAYROLL BRIDGE ──
    Creates/updates monthly_attendance_summary rows with pre-defined ready values.
    Does NOT create new employees, does NOT change salary structures, does NOT
    duplicate rows (upserts only).  Frozen rows are skipped.

    Allowed roles: admin.

    Seed values:
      total_working_days = 22, present_days = 22, leave_days = 0, lop_days = 0,
      payable_days = 22, approved_timesheet_hours = 176,
      attendance_status = 'validated' (READY), timesheet_status = 'approved' (READY),
      validation_status = 'passed' (VALID), issues_count = 0,
      is_ready_for_payroll = True, is_frozen = False.
    """
    try:
        result = _bridge.seed_dummy_summary(
            db, month=month, year=year, actor=actor
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


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
    summary="[HR] Freeze monthly attendance — unlocks payroll generation for Finance",
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
