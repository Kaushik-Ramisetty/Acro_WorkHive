"""Bonus Request model — one-time payment workflow.

Workflow
--------
pending_finance_review → pending_finance_head_approval → approved → applied | rejected

A BonusRequest is separate from SalaryRevision. It does NOT change annual CTC.
After Finance Head approval, a PayrollAdjustment is created for the target month's run.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BonusRequest(Base):
    __tablename__ = "bonus_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    payroll_month: Mapped[int] = mapped_column(Integer, nullable=False)   # 1–12
    payroll_year:  Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_type:    Mapped[str] = mapped_column(String(50), nullable=False)
    # Joining Bonus | Annual Bonus | Performance Bonus | Incentive
    # Arrears | Special Bonus | Other

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(40), default="pending_finance_review", nullable=False, index=True
    )
    # pending_finance_review | pending_finance_head_approval
    # approved | applied | rejected

    # Payment mode — determines how the bonus is disbursed after Finance Head approval
    # regular_payroll: added as PayrollAdjustment to current month's editable run
    # off_cycle: processed separately as a standalone bonus payment (run may be closed)
    payment_mode: Mapped[str] = mapped_column(
        String(20), default="regular_payroll", nullable=False
    )

    # Linked PayrollRun — set when bonus is materialised during payroll generation
    payroll_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"), nullable=True
    )

    # Linked PayrollAdjustment after Finance Head approval + run match
    payroll_adjustment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_adjustments.id", ondelete="SET NULL"), nullable=True
    )

    # Finance recommendation (both /approve and /reject forward to Finance Head)
    finance_recommendation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # approve | reject
    finance_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    reviewed_by_id:  Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_by_id:  Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee:     Mapped["Employee"] = relationship(foreign_keys=[employee_id])        # type: ignore[name-defined]
    requested_by: Mapped["Employee | None"] = relationship(foreign_keys=[requested_by_id])  # type: ignore[name-defined]
    reviewed_by:  Mapped["Employee | None"] = relationship(foreign_keys=[reviewed_by_id])   # type: ignore[name-defined]
    approved_by:  Mapped["Employee | None"] = relationship(foreign_keys=[approved_by_id])   # type: ignore[name-defined]
