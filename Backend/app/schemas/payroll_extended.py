"""Pydantic schemas for the extended payroll tables."""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ─── Statutory Settings ───────────────────────────────────────────────────────

class StatutorySettingsBase(BaseModel):
    pf_employee_rate: float = 0.12
    pf_employer_rate: float = 0.12
    pf_wage_ceiling: float = 15000.0
    esi_employee_rate: float = 0.0075
    esi_employer_rate: float = 0.0325
    esi_wage_ceiling: float = 21000.0
    pt_slab_json: Optional[str] = None
    gratuity_rate: float = 0.0481
    gratuity_eligibility_years: float = 5.0
    bonus_min_rate: float = 0.0833
    bonus_max_rate: float = 0.20
    bonus_wage_ceiling: float = 21000.0
    basic_pct_of_ctc: float = 0.40
    hra_pct_of_basic: float = 0.50
    transport_allowance: float = 1600.0
    medical_allowance: float = 1250.0
    effective_from: date


class StatutorySettingsIn(StatutorySettingsBase):
    pass


class StatutorySettingsOut(StatutorySettingsBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Payroll Adjustment ───────────────────────────────────────────────────────

class PayrollAdjustmentIn(BaseModel):
    employee_id: int
    adjustment_type: str = Field(
        ..., description="bonus|arrears|advance_recovery|lta|variable_pay|other_addition|other_deduction"
    )
    direction: str = Field(..., description="addition | deduction")
    amount: float
    description: Optional[str] = None
    is_taxable: bool = True


class PayrollAdjustmentOut(PayrollAdjustmentIn):
    id: int
    run_id: int
    approved_by_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Payslip ──────────────────────────────────────────────────────────────────

class PayslipOut(BaseModel):
    id: int
    payslip_id: Optional[int] = None
    payroll_record_id: Optional[int] = None
    run_id: int
    payroll_run_id: Optional[int] = None
    employee_id: int
    employee_name: Optional[str] = None
    month_label: str
    month: Optional[int] = None
    year: Optional[int] = None
    payslip_number: Optional[str] = None
    pay_period_start: date
    pay_period_end: date
    gross_salary: float
    total_deductions: float
    net_salary: float
    pdf_path: Optional[str] = None
    file_url: Optional[str] = None
    payslip_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    status: str = "GENERATED"
    generated_by: Optional[int] = None
    generated_at: Optional[datetime] = None
    is_published: bool
    published_at: Optional[datetime] = None
    email_sent: bool = False
    emailed_at: Optional[datetime] = None
    download_count: int = 0
    created_at: datetime

    @model_validator(mode='after')
    def _derive_period_fields(self) -> 'PayslipOut':
        self.month_label = f"{calendar.month_name[self.pay_period_start.month]} {self.pay_period_start.year}"
        self.month = self.pay_period_start.month
        self.year = self.pay_period_start.year
        return self

    class Config:
        from_attributes = True


# ─── CTC Compute ─────────────────────────────────────────────────────────────

class CTCComputeIn(BaseModel):
    employee_id: int
    annual_ctc: float = Field(..., gt=0, description="Annual CTC in INR")
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    effective_from: Optional[date] = None
    revision_reason: Optional[str] = None


class CTCComputeOut(BaseModel):
    employee_id: int
    annual_ctc: float
    basic: float
    hra: float
    da: float = 0.0
    lta: float = 0.0
    special_allowance: float
    transport_allowance: float
    medical_allowance: float = 0.0
    gross_monthly: float
    pf_employee: float
    pf_employer: float
    esi_employee: float
    esi_employer: float
    professional_tax: float
    tds: float
    total_deductions: float
    net_monthly: float


# ─── Salary Component ─────────────────────────────────────────────────────────

class SalaryComponentBase(BaseModel):
    component_code: str
    component_name: str
    component_type: str
    calculation_type: str = "Fixed"
    default_value: float = 0.0
    is_taxable: bool = True
    pf_applicable: bool = False
    esi_applicable: bool = False
    display_order: int = 0
    is_active: bool = True
    remarks: Optional[str] = None


class SalaryComponentIn(SalaryComponentBase):
    pass


class SalaryComponentOut(SalaryComponentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Employee Salary ──────────────────────────────────────────────────────────

class EmployeeSalaryOut(BaseModel):
    id: int
    employee_id: int
    salary_structure_id: Optional[int] = None
    effective_from: date
    monthly_ctc: float
    basic: float
    hra: float
    da: float = 0.0
    special_allowance: float
    pf_employee: float
    pf_employer: float
    esi_employee: float
    professional_tax: float
    tds_estimated: float
    net_estimated: float
    status: str
    remarks: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Tax Deduction ────────────────────────────────────────────────────────────

class TaxDeductionOut(BaseModel):
    id: int
    employee_id: int
    run_id: int
    financial_year: str
    month: int
    year: int
    pf_employee: float
    esi_employee: float
    professional_tax: float
    tds: float
    total_tax_deductions: float
    remarks: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Reimbursement ────────────────────────────────────────────────────────────

class ReimbursementIn(BaseModel):
    employee_id: int
    claim_type: str = Field(..., description="Travel|Internet|Medical|Food|Equipment|Other")
    claim_amount: float = Field(..., gt=0)
    remarks: Optional[str] = None


class ReimbursementApproveIn(BaseModel):
    approved_amount: Optional[float] = None
    remarks: Optional[str] = None


class ReimbursementRejectIn(BaseModel):
    remarks: Optional[str] = None


class ReimbursementMarkPaidIn(BaseModel):
    payroll_run_id: Optional[int] = None


class ReimbursementOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    payroll_run_id: Optional[int] = None
    claim_type: str
    claim_amount: float
    approved_amount: float
    status: str
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
