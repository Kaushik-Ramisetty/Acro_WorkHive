"""Leave-encashment requests.

An employee converts unused (available) leave into cash. On approval:
  - The ledger posts an ENCASHMENT entry (allocated_balance -= days).
  - Optionally, payroll picks up `payroll_sync_status='pending'` on the
    next run and credits the cash amount into the employee's salary.

Workflow (Phase 5C):
  PENDING -> APPROVED (manager only; HR notification-only, mirrors leave)
  PENDING -> REJECTED

A request is rejected if available balance has dropped below the
requested days by the time the manager acts — the ledger refuses the
write under row lock, so no race can over-encash.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EncashmentRequest(Base):
    __tablename__ = "encashment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    leave_type_id: Mapped[str] = mapped_column(
        ForeignKey("leave_types.id"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional payroll hint — captured at request time so the rate the
    # employee saw is the rate they're paid even if payroll config moves.
    rate_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Workflow (mirrors LeaveRequest in spirit; status uses lowercase strings
    # so the existing notification + audit framework slots in.)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Payroll integration mirrors LeaveRequest.payroll_* so the existing
    # retry sweep can pick up encashments by widening one query later.
    payroll_sync_status: Mapped[str] = mapped_column(
        String(20), default="na", nullable=False, index=True
    )
    payroll_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    leave_type: Mapped["LeaveType"] = relationship()  # type: ignore[name-defined]
