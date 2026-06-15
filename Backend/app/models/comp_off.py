"""Comp-off credit model.

Tracks earned compensatory-off days. Granted when an employee worked on a
holiday/weekend/leave day. Has an expiry per policy (default: 90 days from
the date worked).

Status values: 'pending' (awaiting approval), 'approved' (active credit),
'rejected', 'used' (consumed by a Compensatory_leave request), 'expired'.

The "use" side is handled by the existing Compensatory_leave LeaveType
through apply_leave -- the available comp-off balance simply augments
LeaveBalance.current_balance for that type when granted.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompOffCredit(Base):
    __tablename__ = "comp_off_credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    worked_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proof_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    next_approver_role: Mapped[str | None] = mapped_column(String(10), nullable=True)

    manager_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hr_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
