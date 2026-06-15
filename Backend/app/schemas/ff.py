"""Pydantic schemas for Final Settlement (Full & Final / FF)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class FinalSettlementCreate(BaseModel):
    """Payload to initiate a new FF record. Uses existing employee_id only."""
    employee_id: int = Field(..., description="Must be an existing employee — FF never creates a new employee")
    last_working_day: Optional[date] = None
    separation_type: Optional[str] = Field(
        None,
        description="resignation|termination|retirement|end_of_contract|deceased",
    )
    remarks: Optional[str] = None


class FinalSettlementCalculateIn(BaseModel):
    """Override inputs for FF calculation. Leave blank to auto-compute from records."""
    unpaid_salary: Optional[float] = None          # auto-computed if not supplied
    leave_encashment_days: Optional[float] = None  # auto-computed from leave balance
    bonus_pending: float = 0.0
    variable_pay_pending: float = 0.0
    other_earnings: float = 0.0
    notice_period_days: int = 0
    loan_recovery: float = 0.0
    advance_recovery: float = 0.0
    asset_recovery: float = 0.0
    other_deductions: float = 0.0
    tds_on_settlement: float = 0.0


class FinalSettlementOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    date_of_joining: Optional[date] = None
    last_working_day: Optional[date] = None
    separation_type: Optional[str] = None

    # Earnings
    unpaid_salary: float
    leave_encashment_days: float
    leave_encashment_amount: float
    bonus_pending: float
    variable_pay_pending: float
    gratuity_eligible: bool
    gratuity_amount: float
    other_earnings: float

    # Deductions
    notice_period_days: int
    notice_period_recovery: float
    loan_recovery: float
    advance_recovery: float
    asset_recovery: float = 0.0
    other_deductions: float
    tds_on_settlement: float
    pending_reimbursements_amount: float = 0.0

    # Totals
    gross_settlement: float
    total_deductions: float
    net_payable: float

    # Workflow
    status: str
    remarks: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    paid_date: Optional[date] = None
    payment_reference: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FinalSettlementApproveIn(BaseModel):
    remarks: Optional[str] = None


class FinalSettlementMarkPaidIn(BaseModel):
    paid_date: date
    payment_reference: Optional[str] = None
