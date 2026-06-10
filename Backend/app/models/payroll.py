"""Payroll domain models — PayrollRun, per-employee amounts, salary structure,
approval audit trail, and error/flag tracking.

These tables are additive: no existing table is altered here.

Versioning design (enterprise payroll):
  salary_structures supports multiple rows per employee.
  Each salary revision creates a NEW row with a new effective_from date.
  The previous active row is deactivated (is_active=False).
  Payroll generation selects the latest active row where effective_from <= pay_period_end.
  Closed payroll rows hold a salary_structure_id snapshot — they are never affected
  by future salary revisions.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, event, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SalaryStructure(Base):
    """Monthly salary component breakdown — one row per revision per employee.

    Versioning rules:
    - Each salary change creates a NEW row; the previous row is marked is_active=False.
    - Payroll generation always picks the latest row where:
        is_active=True AND effective_from <= pay_period_end
    - Existing payroll_run_employees rows hold salary_structure_id so historical
      payrolls are never affected by future salary revisions.
    - unique=True has been intentionally removed from employee_id to support versioning.
    """
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        # NOTE: unique=True intentionally removed — supports salary versioning.
        # A non-unique index is created via migration for query performance.
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Earnings (monthly, in INR)
    basic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    da: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)          # Dearness Allowance
    special_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    transport_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    medical_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    other_allowances: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Deductions (monthly, in INR)
    pf_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pf_employer: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employer: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Computed from above (denormalised for reporting speed)
    gross_monthly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_monthly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    annual_ctc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Bank details (for bank advice generation)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ifsc_code: Mapped[str | None] = mapped_column(String(15), nullable=True)

    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


class PayrollRun(Base):
    """One row per payroll cycle (e.g. April 2025).

    Status flow:
      draft → attendance_frozen → processing → under_review → approved → disbursed
    Finance can also push back to processing (recompute).
    """
    __tablename__ = "payroll_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_run_code: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True, index=True)

    # Period identification
    pay_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    pay_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    month_label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "April 2025"
    month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Workflow status
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    # draft | attendance_frozen | processing | under_review | approved | disbursed | cancelled

    # Aggregate totals (updated after processing)
    total_employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_gross: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_net: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_esi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pt: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    attendance_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payroll_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Workflow timestamps
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disbursed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Ownership
    initiated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    finalized_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    initiated_by: Mapped["Employee"] = relationship(foreign_keys=[initiated_by_id])  # type: ignore[name-defined]
    approved_by: Mapped["Employee"] = relationship(foreign_keys=[approved_by_id])   # type: ignore[name-defined]
    finalized_by: Mapped["Employee"] = relationship(foreign_keys=[finalized_by_id])  # type: ignore[name-defined]
    employees: Mapped[list["PayrollRunEmployee"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    approvals: Mapped[list["PayrollApproval"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    errors: Mapped[list["PayrollError"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    @property
    def payroll_run_id(self) -> int:
        return self.id

    @property
    def run_status(self) -> str:
        return self.status

    @property
    def total_net_pay(self) -> float:
        return self.total_net

    @property
    def lifecycle_status(self) -> str:
        if self.status == "approved" and self.payroll_locked:
            return "FINALIZED"
        mapping = {
            "draft": "DRAFT",
            "attendance_frozen": "DRAFT",
            "processing": "PROCESSING",
            "under_review": "PENDING_APPROVAL",
            "error_found": "PENDING_APPROVAL",
            "pending_head_approval": "PENDING_APPROVAL",
            "approved": "APPROVED",
            "payslip_generated": "FINALIZED",
            "disbursed": "FINALIZED",
            "published": "PUBLISHED",
            "closed": "PUBLISHED",
            "cancelled": "CANCELLED",
        }
        return mapping.get(self.status, self.status.upper())


class PayrollRunEmployee(Base):
    """Computed payroll amounts for one employee in one payroll run.

    salary_structure_id records EXACTLY which salary structure version was used
    to compute this row.  This is the audit anchor: even if the employee's salary
    is revised later, this row's reference to the original structure is immutable
    once the run moves past 'processing'.
    """
    __tablename__ = "payroll_run_employees"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_run_employee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    # Salary structure version used for this payroll row (audit anchor).
    # NULL only for rows generated before this column was added (legacy data).
    salary_structure_id: Mapped[int | None] = mapped_column(
        ForeignKey("salary_structures.id", ondelete="SET NULL"), nullable=True, index=True
    )
    salary_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_salary_assignments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Attendance data snapshot
    total_working_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    working_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payable_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    present_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lop_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    holiday_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Computed amounts (in INR)
    gross_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gross_earnings: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    basic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    basic_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    da: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    special_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    conveyance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    variable_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overtime_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    allowances: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employee_pf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pf_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pf_employer: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employer_pf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employee_esi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    esi_employer: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employer_esi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lop_deduction: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    other_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Flags
    has_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payslip_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    record_status: Mapped[str] = mapped_column(String(20), default="COMPUTED", nullable=False)
    variance_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    variance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payslip_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    migration_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped["PayrollRun"] = relationship(back_populates="employees")
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    salary_structure: Mapped["SalaryStructure | None"] = relationship(foreign_keys=[salary_structure_id])

    @property
    def payroll_record_id(self) -> int:
        return self.id

    @property
    def payroll_run_id(self) -> int:
        return self.run_id

    def sync_legacy_amount_columns(self) -> None:
        """Populate retired amount columns from the source-of-truth columns."""
        self.gross_salary = self.gross_earnings or 0.0
        self.basic = self.basic_pay or 0.0
        self.allowances = self.special_allowance or 0.0
        self.pf_employee = self.employee_pf or 0.0
        self.pf_employer = self.employer_pf or 0.0
        self.esi_employee = self.employee_esi or 0.0
        self.esi_employer = self.employer_esi or 0.0
        self.net_salary = self.net_pay or 0.0


@event.listens_for(PayrollRunEmployee, "before_insert")
@event.listens_for(PayrollRunEmployee, "before_update")
def _sync_payroll_run_employee_legacy_amounts(mapper, connection, target: PayrollRunEmployee) -> None:
    target.sync_legacy_amount_columns()


class PayrollApproval(Base):
    """Audit trail of every approval action on a payroll run."""
    __tablename__ = "payroll_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    approval_level: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # initiate | freeze_attendance | generate | submit_review | recompute |
    # approve | reject | disburse | cancel

    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped["PayrollRun"] = relationship(back_populates="approvals")
    actor: Mapped["Employee"] = relationship(foreign_keys=[actor_id])  # type: ignore[name-defined]
    approver: Mapped["Employee | None"] = relationship(foreign_keys=[approver_id])  # type: ignore[name-defined]

    @property
    def payroll_approval_id(self) -> int:
        return self.id

    @property
    def payroll_run_id(self) -> int:
        return self.run_id


class PayrollError(Base):
    """Flags/issues raised during finance review for a specific employee in a run."""
    __tablename__ = "payroll_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # salary_mismatch | missing_attendance | leave_inconsistency |
    # deduction_mismatch | lop_mismatch | manual_correction

    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)
    # warning | error | info

    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    run: Mapped["PayrollRun"] = relationship(back_populates="errors")
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    resolved_by: Mapped["Employee | None"] = relationship(foreign_keys=[resolved_by_id])  # type: ignore[name-defined]


class PayrollLockHistory(Base):
    """Lock/unlock audit trail for payroll-owned lock actions."""
    __tablename__ = "payroll_lock_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lock_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    action_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    action_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["PayrollRun"] = relationship(foreign_keys=[payroll_run_id])
    actor: Mapped["Employee | None"] = relationship(foreign_keys=[action_by])  # type: ignore[name-defined]

    @property
    def payroll_lock_history_id(self) -> int:
        return self.id
