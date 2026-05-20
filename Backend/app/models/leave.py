"""Leave-related models: types, balances, requests."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[str]                = mapped_column(String(20), primary_key=True)
    name: Mapped[str]              = mapped_column(String(80), nullable=False)
    annual_quota: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    carry_forward_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_paid: Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    applicable_gender: Mapped[str] = mapped_column(String(10), default="all", nullable=False)

    # ---- Phase 5B accrual policy (additive, all nullable) ----------
    # accrual_frequency: NULL = no accrual (lump-sum quota only),
    #                    'monthly' = days_per_cycle credited per calendar month,
    #                    'yearly'  = full annual_quota credited on Jan 1.
    accrual_frequency: Mapped[str | None]    = mapped_column(String(10), nullable=True)
    accrual_days_per_cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Block accrual until the employee has been with the company this many months.
    probation_months: Mapped[int]            = mapped_column(Integer, default=0, nullable=False)

    requests: Mapped[list["LeaveRequest"]] = relationship(back_populates="leave_type")
    balances: Mapped[list["LeaveBalance"]] = relationship(back_populates="leave_type")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    employee_id: Mapped[int]   = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[str] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    year: Mapped[int]          = mapped_column(Integer, nullable=False, index=True)

    opening_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used: Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    current_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Reserved = approved but not yet consumed (waiting for the leave date).
    # Available to apply = current_balance - reserved.
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- Phase 5A: additive balance fields -------------------------
    # `allocated_balance` is the canonical grant pool (opening + accruals +
    # comp-off + adjustments). The ledger writes into this column; the legacy
    # `opening_balance` column is kept in sync for backwards-compatible reads.
    allocated_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # `pending_balance` is the days currently locked by status='pending'
    # leave requests. Maintained by the engine on submit / approve / reject
    # so the availability formula doesn't require a SUM() at read time.
    pending_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Optimistic-concurrency token. Bumped on every successful write; the
    # ledger service uses it together with row-locking to detect concurrent
    # mutation under READ COMMITTED isolation on SQL Server.
    row_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    employee: Mapped["Employee"]     = relationship()                                       # type: ignore[name-defined]
    leave_type: Mapped["LeaveType"]  = relationship(back_populates="balances")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    employee_id: Mapped[int]   = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[str] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date]   = mapped_column(Date, nullable=False)
    total_days: Mapped[int]  = mapped_column(Integer, default=0, nullable=False)
    # Hybrid v2 — days actually consumed so far. Populated incrementally
    # by the scheduler as each leave date passes (or in one shot when the
    # leave ends without partial cancellation). Drives partial-cancel math:
    # `cancellable = total_days - consumed_days`.
    consumed_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Working-day refactor — half-day boundaries.
    # 'first'  → only the first half of start_date counts (afternoon off)
    # 'second' → only the second half of start_date counts (morning off)
    # null     → full day. Same vocabulary for end_date.
    start_half_day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_half_day:   Mapped[str | None] = mapped_column(String(10), nullable=True)

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Lifecycle:
    #   pending        -> awaiting next approval (see next_approver_role)
    #   approved       -> both manager + hr approved; balance reserved
    #   rejected       -> terminal
    #   cancel_pending -> approved request that the employee asked to cancel
    #   cancelled      -> terminal
    #   consumed       -> terminal (Phase 2 only, set by scheduler)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    # Drives the approval chain. Values: 'manager', 'hr', None (chain done).
    next_approver_role: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Per-stage stamps -- preserved even after rejection/cancellation for audit.
    manager_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hr_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Cancellation-specific fields.
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_manager_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    cancel_manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_hr_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    cancel_hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Legacy single-stage approver stamp (kept for backwards-compat with v1 seed).
    approved_by: Mapped[int | None]      = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ---- SLA escalation (Phase 2) -----------------------------------
    # Tracks how far the escalation ladder has climbed for the *current*
    # pending stage. Resets to 0 when the request advances stages.
    #   0 = nothing fired yet
    #   1 = 24h reminder sent
    #   2 = 48h skip-level escalation (approver_override_id set)
    #   3 = 72h HR intervention (next_approver_role forced to 'hr')
    sla_escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sla_last_alert_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # When non-null, this employee is an additional authorized approver for
    # the current stage (used by skip-level escalation + delegate cache).
    approver_override_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    # ---- Payroll sync (Phase 3) -------------------------------------
    # Lifecycle of the per-request payroll write into payroll_attendance_summary:
    #   na      = not applicable yet (still pending/approved, not consumed)
    #   pending = consumed; sync queued / in-flight
    #   synced  = successfully written
    #   failed  = last attempt errored; admin attention required after N tries
    payroll_sync_status: Mapped[str] = mapped_column(String(20), default="na", nullable=False, index=True)
    payroll_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payroll_sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payroll_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"]    = relationship(foreign_keys=[employee_id])              # type: ignore[name-defined]
    approver: Mapped["Employee | None"] = relationship(foreign_keys=[approved_by])          # type: ignore[name-defined]
    leave_type: Mapped["LeaveType"] = relationship(back_populates="requests")
