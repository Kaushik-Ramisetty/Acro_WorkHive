"""Pydantic schemas for the Finance / Payroll module."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ─── Salary Structure ────────────────────────────────────────────────────────

class SalaryStructureBase(BaseModel):
    basic: float = 0.0
    hra: float = 0.0
    da: float = 0.0                   # Dearness Allowance (Excel schema field)
    special_allowance: float = 0.0
    transport_allowance: float = 0.0
    medical_allowance: float = 0.0
    other_allowances: float = 0.0
    pf_employee: float = 0.0
    pf_employer: float = 0.0
    esi_employee: float = 0.0
    esi_employer: float = 0.0
    professional_tax: float = 0.0
    tds: float = 0.0
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    effective_from: Optional[date] = None
    is_active: bool = True


class SalaryStructureIn(SalaryStructureBase):
    employee_id: int
    revision_reason: Optional[str] = None


class SalaryStructureOut(SalaryStructureBase):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    gross_monthly: float
    total_deductions: float
    net_monthly: float
    annual_ctc: float
    # LTA — exposed explicitly so Basic+HRA+LTA+Transport+Special == gross_monthly.
    # The SalaryStructure DB table has no dedicated lta column; LTA is stored in
    # other_allowances.  This field is populated by the validator below.
    lta: float = 0.0
    # Versioning fields
    is_active: bool = True
    effective_from: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode='after')
    def _expose_lta(self) -> 'SalaryStructureOut':
        """Expose lta as a named field for any consumer that reads it explicitly.

        For structures saved before the LTA-merge fix, other_allowances holds the
        LTA value.  We surface it as lta without zeroing other_allowances, because
        the salary-structure table computes combined allowances as
          special + transport + medical + other_allowances
        and must continue to include it.
        """
        if self.lta == 0.0:
            self.lta = self.other_allowances
        return self

    class Config:
        from_attributes = True


# ─── Payroll Run ─────────────────────────────────────────────────────────────

class PayrollRunCreate(BaseModel):
    pay_period_start: date
    pay_period_end: date
    month_label: str = Field(..., example="April 2025")
    month: Optional[int] = None
    year: Optional[int] = None
    notes: Optional[str] = None


class PayrollRunStatusUpdate(BaseModel):
    action: str = Field(
        ...,
        description=(
            "One of: freeze_attendance | generate | submit_review | "
            "recompute | approve | reject | finalize | generate_payslips | publish | disburse | cancel"
        ),
    )
    remarks: Optional[str] = None


class PayrollRunOut(BaseModel):
    id: int
    payroll_run_id: Optional[int] = None
    payroll_run_code: Optional[str] = None
    pay_period_start: date
    pay_period_end: date
    month_label: str
    month: Optional[int] = None
    year: Optional[int] = None
    status: str
    run_status: Optional[str] = None
    lifecycle_status: Optional[str] = None
    total_employees: int
    total_gross: float
    total_deductions: float
    total_net: float
    total_net_pay: Optional[float] = None
    total_pf: float
    total_esi: float
    total_tds: float
    total_pt: float
    attendance_locked: bool = False
    payroll_locked: bool = False
    initiated_at: Optional[datetime]
    processed_at: Optional[datetime]
    approved_at: Optional[datetime]
    finalized_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    disbursed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Payroll Run Employee ─────────────────────────────────────────────────────

class PayrollRunEmployeeOut(BaseModel):
    id: int
    payroll_record_id: Optional[int] = None
    run_id: int
    payroll_run_id: Optional[int] = None
    employee_id: int
    employee_name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    # Salary structure version that was used to generate this row.
    # Null only for rows generated before the versioning migration.
    salary_structure_id: Optional[int] = None
    salary_assignment_id: Optional[int] = None
    total_working_days: int = 0
    working_days: int
    payable_days: float = 0.0
    present_days: int
    leave_days: int
    lop_days: int
    gross_salary: float
    gross_earnings: float = 0.0
    basic: float
    basic_pay: float = 0.0
    hra: float
    da: float = 0.0
    special_allowance: float = 0.0
    lta: float = 0.0
    conveyance: float = 0.0
    bonus: float = 0.0
    variable_pay: float = 0.0
    overtime_amount: float = 0.0
    allowances: float
    employee_pf: float = 0.0
    pf_employee: float
    pf_employer: float = 0.0
    employer_pf: float = 0.0
    employee_esi: float = 0.0
    esi_employee: float
    esi_employer: float = 0.0
    employer_esi: float = 0.0
    professional_tax: float
    tds: float
    lop_deduction: float = 0.0
    other_deductions: float = 0.0
    total_deductions: float
    net_salary: float
    net_pay: float = 0.0
    # Adjustment breakdowns (computed from PayrollAdjustment table)
    bonus_total: float = 0.0
    variable_pay_total: float = 0.0
    arrears_total: float = 0.0
    has_error: bool
    is_locked: bool
    payslip_generated: bool
    record_status: str = "COMPUTED"
    variance_flag: bool = False
    variance_reason: Optional[str] = None
    payslip_url: Optional[str] = None
    migration_completed: bool = False

    class Config:
        from_attributes = True


# ─── Payroll Approval ────────────────────────────────────────────────────────

class PayrollApprovalOut(BaseModel):
    id: int
    payroll_approval_id: Optional[int] = None
    run_id: int
    payroll_run_id: Optional[int] = None
    actor_id: int
    actor_name: Optional[str] = None
    approval_level: Optional[str] = None
    approver_id: Optional[int] = None
    approval_status: str = "PENDING"
    comments: Optional[str] = None
    action: str
    from_status: Optional[str]
    to_status: Optional[str]
    remarks: Optional[str]
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Payroll Error ───────────────────────────────────────────────────────────

class PayrollErrorCreate(BaseModel):
    run_id: int
    employee_id: int
    error_type: str
    description: str
    severity: str = "warning"


class PayrollErrorResolve(BaseModel):
    resolution_note: Optional[str] = None


class PayrollErrorOut(BaseModel):
    id: int
    run_id: int
    employee_id: int
    employee_name: Optional[str] = None
    error_type: str
    description: str
    severity: str
    is_resolved: bool
    resolved_at: Optional[datetime]
    resolution_note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Dashboard / Summary ─────────────────────────────────────────────────────

class DepartmentPayrollSummary(BaseModel):
    department: str
    headcount: int
    gross: float
    deductions: float
    net: float
    variance_pct: float


class PayrollDashboardStats(BaseModel):
    current_run: Optional[PayrollRunOut]
    total_payroll_runs: int = 0
    pending_approval_count: int
    total_employees: int
    total_gross: float = 0.0
    total_deductions: float = 0.0
    total_net_pay: float = 0.0
    last_run_net: float
    open_error_count: int
    attendance_frozen: bool
    payroll_locked: bool = False
    is_finalized: bool = False
    is_published: bool = False
    approval_status: Optional[dict[str, str]] = None
    finance_review_status: Optional[str] = None
    payslip_generated_count: int = 0
    payslip_published_count: int = 0
    variance_count: int = 0
    payroll_completion_pct: float
    department_summary: list[DepartmentPayrollSummary]


# ─── Salary Revision ─────────────────────────────────────────────────────────

class SalaryRevisionCreate(BaseModel):
    """Request body for POST /payroll/salary-revisions."""
    employee_id: int
    new_ctc_annual: float = Field(..., gt=0, description="New annual CTC in INR")
    effective_from: date = Field(..., description="Date from which the hike is effective")
    revision_reason: Optional[str] = None


class SalaryRevisionOut(BaseModel):
    """Response for a salary revision — mirrors the SalaryRevisionLog row."""
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    old_annual_ctc: float = 0.0
    new_annual_ctc: float = 0.0
    ctc_difference: float = 0.0
    ctc_change_pct: float = 0.0
    old_gross_monthly: float = 0.0
    new_gross_monthly: float = 0.0
    old_net_monthly: float = 0.0
    new_net_monthly: float = 0.0
    effective_from: Optional[date] = None
    revision_reason: Optional[str] = None
    revised_by_id: Optional[int] = None
    revised_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
