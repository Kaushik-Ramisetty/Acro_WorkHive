"""Extended payroll domain models — additive tables only.

No existing table is altered. These tables extend the payroll module with:
- StatutorySettings      : configurable PF/ESI/PT/TDS rates
- PayrollAdjustment      : one-time bonus, arrears, deductions per employee per run
- EmployeeTaxDeclaration : 80C / HRA / NPS declarations for TDS
- Payslip                : generated payslip record with PDF path + publish state
- PayrollAuditLog        : computation audit trail per employee per run
- FinalSettlement        : Full & Final settlement (FF)
- SalaryComponent        : reference table of salary component definitions (Excel schema)
- EmployeeSalary         : per-employee salary record with revision history (Excel schema)
- TaxDeduction           : per-employee per-month tax ledger for compliance (Excel schema)
- Reimbursement          : expense reimbursement claims management (Excel schema)
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ─── Statutory Settings ───────────────────────────────────────────────────────

class StatutorySettings(Base):
    """Configurable PF / ESI / PT / TDS rate table.

    One active row at a time (use effective_from to version).
    """
    __tablename__ = "statutory_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # PF
    pf_employee_rate: Mapped[float] = mapped_column(Float, default=0.12, nullable=False)   # 12%
    pf_employer_rate: Mapped[float] = mapped_column(Float, default=0.12, nullable=False)   # 12%
    pf_wage_ceiling: Mapped[float] = mapped_column(Float, default=15000.0, nullable=False) # ₹15,000

    # ESI
    esi_employee_rate: Mapped[float] = mapped_column(Float, default=0.0075, nullable=False)  # 0.75%
    esi_employer_rate: Mapped[float] = mapped_column(Float, default=0.0325, nullable=False)  # 3.25%
    esi_wage_ceiling: Mapped[float] = mapped_column(Float, default=21000.0, nullable=False)  # ₹21,000

    # Professional Tax (monthly, INR) — India standard slab
    pt_slab_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        # JSON array: [{"min": 0, "max": 10000, "pt": 0}, {"min": 10001, "max": 15000, "pt": 110},
        #              {"min": 15001, "max": 999999, "pt": 200}]
        # Default PT is for Maharashtra. Finance can customise per state.
        default='[{"min":0,"max":10000,"pt":0},{"min":10001,"max":15000,"pt":110},{"min":15001,"max":999999,"pt":200}]'
    )

    # Gratuity
    gratuity_rate: Mapped[float] = mapped_column(Float, default=0.0481, nullable=False)  # 4.81% of basic p.a.
    gratuity_eligibility_years: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    # Bonus Act
    bonus_min_rate: Mapped[float] = mapped_column(Float, default=0.0833, nullable=False)  # 8.33%
    bonus_max_rate: Mapped[float] = mapped_column(Float, default=0.20, nullable=False)    # 20%
    bonus_wage_ceiling: Mapped[float] = mapped_column(Float, default=21000.0, nullable=False)

    # CTC split ratios
    basic_pct_of_ctc: Mapped[float] = mapped_column(Float, default=0.40, nullable=False)    # 40% of annual CTC
    hra_pct_of_basic: Mapped[float] = mapped_column(Float, default=0.50, nullable=False)    # 50% of basic (metro)
    transport_allowance: Mapped[float] = mapped_column(Float, default=1600.0, nullable=False)  # ₹1,600 / month
    medical_allowance: Mapped[float] = mapped_column(Float, default=1250.0, nullable=False)    # ₹1,250 / month

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ─── Payroll Adjustments ──────────────────────────────────────────────────────

class PayrollAdjustment(Base):
    """One-time additions or deductions for a specific employee in a payroll run.

    Examples: performance bonus, arrears, advance recovery, LTA payout.
    """
    __tablename__ = "payroll_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    adjustment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # bonus | arrears | advance_recovery | lta | variable_pay | overtime_pay
    # loan_recovery | other_addition | other_deduction

    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # addition | deduction
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped["PayrollRun"] = relationship(foreign_keys=[run_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    approved_by: Mapped["Employee | None"] = relationship(foreign_keys=[approved_by_id])  # type: ignore[name-defined]


# ─── Employee Tax Declarations ────────────────────────────────────────────────

class EmployeeTaxDeclaration(Base):
    """Investment declarations submitted by employee for TDS computation.

    One row per employee per financial year.
    """
    __tablename__ = "employee_tax_declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    financial_year: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "2025-26"

    # Section 80C (max ₹1,50,000)
    sec_80c: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Section 80D — health insurance (max ₹25,000 self; ₹50,000 senior parents)
    sec_80d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # NPS 80CCD(1B) — additional ₹50,000
    sec_80ccd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # HRA exemption (computed by system from rent receipts; stored here)
    hra_exemption: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Home loan interest 24(b)
    sec_24b: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Other declared deductions
    other_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # New Tax Regime flag
    opted_new_regime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Proof submission status
    proof_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proof_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    # ── Declaration approval workflow (v17) ───────────────────────────────
    # Status flow: draft → submitted → approved | rejected
    # Only APPROVED declarations affect OLD regime TDS.
    # DRAFT declarations are not used in payroll TDS computation.
    declaration_status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True
    )
    # draft | submitted | approved | rejected

    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Locked after cutoff date — employee cannot change unless admin reopens
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lock_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    verified_by: Mapped["Employee | None"] = relationship(foreign_keys=[verified_by_id])  # type: ignore[name-defined]
    reviewed_by: Mapped["Employee | None"] = relationship(foreign_keys=[reviewed_by_id])  # type: ignore[name-defined]

    @property
    def is_effective_for_tds(self) -> bool:
        """Return True only when this declaration can affect TDS computation.

        New Regime (opted_new_regime=True): always effective (no declarations needed).
        Old Regime (opted_new_regime=False): ONLY effective when status='approved'.
        """
        if self.opted_new_regime:
            return True   # New regime: declarations irrelevant, TDS from slabs only
        return self.declaration_status == "approved"


# ─── Payslip ──────────────────────────────────────────────────────────────────

class Payslip(Base):
    """Generated payslip record — links run, employee, PDF path, publish state."""
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payslip_run_employee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    month_label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "April 2025"
    month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    pay_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    pay_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payslip_number: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True, index=True)

    # Snapshot of amounts at time of generation
    gross_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # PDF
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # server file path
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generated_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ESS publish state
    status: Mapped[str] = mapped_column(String(20), default="GENERATED", nullable=False, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped["PayrollRun"] = relationship(foreign_keys=[run_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    payroll_record: Mapped["PayrollRunEmployee | None"] = relationship(foreign_keys=[payroll_record_id])  # type: ignore[name-defined]
    generated_by: Mapped["Employee | None"] = relationship(foreign_keys=[generated_by_id])  # type: ignore[name-defined]

    @property
    def payslip_id(self) -> int:
        return self.id

    @property
    def payroll_run_id(self) -> int:
        return self.run_id

    @property
    def payslip_url(self) -> str | None:
        return self.file_url or self.pdf_path


# ─── Payroll Audit Log ────────────────────────────────────────────────────────

class PayrollAuditLog(Base):
    """Computation audit trail — records every calculation step for an employee in a run."""
    __tablename__ = "payroll_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    event: Mapped[str] = mapped_column(String(60), nullable=False)
    # computed | lop_applied | adjustment_applied | recomputed | locked | payslip_generated | published

    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot of calc inputs/outputs
    performed_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    run: Mapped["PayrollRun"] = relationship(foreign_keys=[run_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    performed_by: Mapped["Employee | None"] = relationship(foreign_keys=[performed_by_id])  # type: ignore[name-defined]


# ─── Final Settlement ─────────────────────────────────────────────────────────

class FinalSettlement(Base):
    """Full & Final settlement record for an exiting employee.

    Uses existing employee_id — does NOT create new employee records.

    Status flow:
        draft → calculated → under_review → approved → paid | cancelled
    """
    __tablename__ = "final_settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    # Separation details
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    separation_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # resignation | termination | retirement | end_of_contract | deceased

    # Earnings
    unpaid_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    leave_encashment_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    leave_encashment_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bonus_pending: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    variable_pay_pending: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gratuity_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gratuity_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    other_earnings: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Deductions / Recoveries
    notice_period_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notice_period_recovery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    loan_recovery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    advance_recovery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    asset_recovery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    other_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tds_on_settlement: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Auto-pulled pending reimbursements at settlement time
    pending_reimbursements_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Computed totals
    gross_settlement: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_payable: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Workflow
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    # draft | calculated | under_review | approved | paid | cancelled

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Approval
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Payment
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    approved_by: Mapped["Employee | None"] = relationship(foreign_keys=[approved_by_id])  # type: ignore[name-defined]
    paid_by: Mapped["Employee | None"] = relationship(foreign_keys=[paid_by_id])  # type: ignore[name-defined]
    created_by: Mapped["Employee | None"] = relationship(foreign_keys=[created_by_id])  # type: ignore[name-defined]


# ─── Salary Component (Excel schema) ─────────────────────────────────────────

class SalaryComponent(Base):
    """Reference table of configurable salary component definitions.

    Matches the Excel schema salary_components table.
    Finance can add/deactivate components (Basic, HRA, DA, Special Allow., etc.)
    """
    __tablename__ = "salary_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    component_name: Mapped[str] = mapped_column(String(100), nullable=False)
    component_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Earning | Deduction | Employer_Contribution

    calculation_type: Mapped[str] = mapped_column(String(30), nullable=False, default="Fixed")
    # Fixed | Percent_of_Basic | Percent_of_Gross | Residual

    default_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # For percent types: store as percentage (e.g., 40 for 40%).

    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pf_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    esi_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ─── Employee Salary (Excel schema) ──────────────────────────────────────────

class EmployeeSalary(Base):
    """Per-employee salary record with revision history.

    Matches the Excel schema employee_salary table.
    Each row represents one salary revision for an employee.
    Links to salary_structures via salary_structure_id.
    """
    __tablename__ = "employee_salary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salary_structure_id: Mapped[int | None] = mapped_column(
        ForeignKey("salary_structures.id", ondelete="SET NULL"), nullable=True, index=True
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_ctc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Snapshot of component values at time of this revision
    basic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    da: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    special_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Deductions snapshot
    pf_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pf_employer: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tds_estimated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_estimated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="Active", nullable=False)
    # Active | Superseded | Cancelled

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


# ─── Tax Deduction (Excel schema) ─────────────────────────────────────────────

class TaxDeduction(Base):
    """Per-employee per-month statutory tax ledger.

    Matches the Excel schema tax_deductions table.
    Auto-populated when a payroll run is finalised.
    Used for compliance reporting (Form 16, annual PT returns).
    """
    __tablename__ = "tax_deductions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_run_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    financial_year: Mapped[str] = mapped_column(String(10), nullable=False)   # e.g. "2025-2026"
    month: Mapped[int] = mapped_column(Integer, nullable=False)               # 1–12
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Statutory deductions
    pf_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tax_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


# ─── Statutory Deductions (per payroll record) ────────────────────────────────

class StatutoryDeduction(Base):
    """Per-record statutory deduction snapshot for payroll compliance audit."""
    __tablename__ = "statutory_deductions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_record_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    deduction_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    employee_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employer_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    wage_base: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    calculation_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    payroll_record: Mapped["PayrollRunEmployee"] = relationship(foreign_keys=[payroll_record_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]

    @property
    def statutory_deduction_id(self) -> int:
        return self.id


# ─── Salary Assignment / Versioning ───────────────────────────────────────────

class EmployeeSalaryAssignment(Base):
    """Employee salary assignment revision that points at salary_structures."""
    __tablename__ = "employee_salary_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salary_structure_id: Mapped[int] = mapped_column(
        ForeignKey("salary_structures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    ctc_annual: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    monthly_ctc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False, index=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    salary_structure: Mapped["SalaryStructure"] = relationship(foreign_keys=[salary_structure_id])  # type: ignore[name-defined]
    assigned_by_employee: Mapped["Employee | None"] = relationship(foreign_keys=[assigned_by_id])  # type: ignore[name-defined]

    @property
    def employee_salary_assignment_id(self) -> int:
        return self.id

    @property
    def assigned_by(self) -> int | None:
        return self.assigned_by_id


# ─── Reimbursement (Excel schema) ─────────────────────────────────────────────

class Reimbursement(Base):
    """Expense reimbursement claim per employee.

    Matches the Excel schema reimbursements table.
    Status flow: pending → approved → paid | rejected | cancelled
    Paid claims are linked to the payroll run in which they are disbursed.
    """
    __tablename__ = "reimbursements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    # Optionally attached to a payroll run for disbursement
    payroll_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    claim_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Travel | Internet | Medical | Food | Equipment | Other

    claim_amount: Mapped[float] = mapped_column(Float, nullable=False)
    approved_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    # pending | approved | paid | rejected | cancelled

    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # FK to payroll_run_employees row where this was paid out
    paid_in_payroll_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="SET NULL"), nullable=True
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Manager pre-approval (before Finance final approval)
    manager_approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manager_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Taxability flag & supporting info
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    approved_by: Mapped["Employee | None"] = relationship(foreign_keys=[approved_by_id])  # type: ignore[name-defined]
    manager_approved_by: Mapped["Employee | None"] = relationship(foreign_keys=[manager_approved_by_id])  # type: ignore[name-defined]


# ─── Payslip Download Audit ───────────────────────────────────────────────────

class PayslipDownloadAudit(Base):
    """Immutable audit log of every payslip download.

    Created every time an employee, Finance, or Admin downloads a payslip PDF.
    Records who downloaded, from where (IP/user-agent), and when.
    Never deleted — forms part of the compliance audit trail.
    """
    __tablename__ = "payslip_download_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payslip_id: Mapped[int] = mapped_column(
        ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    downloaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    download_source: Mapped[str] = mapped_column(String(30), default="web", nullable=False)

    payslip: Mapped["Payslip"] = relationship(foreign_keys=[payslip_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    downloaded_by: Mapped["Employee | None"] = relationship(foreign_keys=[downloaded_by_id])  # type: ignore[name-defined]


# ─── TDS Annual Summary (Form 16 Readiness) ───────────────────────────────────

class TdsAnnualSummary(Base):
    """Annual TDS summary per employee per financial year.

    Stores the data required to generate Form 16 without recalculating
    old payroll records.  Updated each time a payroll run is finalized
    for that employee in the financial year.  Immutable once is_finalized=True.

    One row per (employee_id, financial_year).
    """
    __tablename__ = "tds_annual_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    financial_year: Mapped[str] = mapped_column(String(10), nullable=False)   # e.g. "2025-26"

    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tax_regime: Mapped[str] = mapped_column(String(20), default="new", nullable=False)

    # Annualized income components
    gross_annual_income: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    standard_deduction: Mapped[float] = mapped_column(Float, default=75000.0, nullable=False)

    # Declared deductions
    sec_80c_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sec_80d_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hra_exemption_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sec_24b_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sec_80ccd_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    other_deductions_claimed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Tax computation
    taxable_income: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    annual_tax_before_cess: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cess_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    annual_tax_with_cess: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rebate_87a: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tds_deducted: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Employer details for Form 16 Part A
    employer_tan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("employee_id", "financial_year", name="uq_tds_annual_emp_fy"),
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


# ─── TDS Monthly Breakup (Form 16 Part B readiness) ──────────────────────────

class TdsMonthlyBreakup(Base):
    """Per-employee per-payroll-run monthly TDS breakup for Form 16 Part B.

    Stored at payroll finalization time.  Immutable — never re-computed
    after the payroll run reaches 'closed' status.

    One row per (employee_id, run_id).
    """
    __tablename__ = "tds_monthly_breakup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    financial_year: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    gross_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    monthly_tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pf_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    regime_used: Mapped[str] = mapped_column(String(20), default="new", nullable=False)

    # Point-in-time snapshot for audit
    annual_taxable_at_time: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remaining_months_at_time: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    tds_debug_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "run_id", name="uq_tds_monthly_emp_run"),
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    run: Mapped["PayrollRun"] = relationship(foreign_keys=[run_id])  # type: ignore[name-defined]


# ─── Payroll Variance Log ─────────────────────────────────────────────────────

class PayrollVarianceLog(Base):
    """Payroll variance comparison between current run and previous month.

    Finance must acknowledge flagged variances before submitting to Finance Head.
    Finance Head sees the variance summary before final approval.

    One row per employee per run — created during payroll generation.
    """
    __tablename__ = "payroll_variance_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    prev_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"), nullable=True
    )

    # Gross pay comparison
    prev_gross_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    curr_gross_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gross_variance_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Net pay comparison
    prev_net_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    curr_net_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_variance_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # TDS comparison
    prev_tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    curr_tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # LOP comparison
    prev_lop_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    curr_lop_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    variance_flags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Acknowledgement (Finance must acknowledge before sending to Finance Head)
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    run: Mapped["PayrollRun"] = relationship(foreign_keys=[run_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    acknowledged_by: Mapped["Employee | None"] = relationship(foreign_keys=[acknowledged_by_id])  # type: ignore[name-defined]


# ─── Declaration Audit Log ─────────────────────────────────────────────────────

class DeclarationAuditLog(Base):
    """Full audit trail for every tax declaration status change.

    Immutable — one row appended per action, never updated/deleted.
    """
    __tablename__ = "declaration_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    declaration_id: Mapped[int] = mapped_column(
        ForeignKey("employee_tax_declarations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # submit | approve | reject | lock | unlock | reopen
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    performed_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    declaration: Mapped["EmployeeTaxDeclaration"] = relationship(foreign_keys=[declaration_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    performed_by: Mapped["Employee | None"] = relationship(foreign_keys=[performed_by_id])  # type: ignore[name-defined]
