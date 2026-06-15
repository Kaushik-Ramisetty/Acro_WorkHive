"""Leave-sourced LOP inputs consumed by payroll."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PayrollLopInput(Base):
    """One Leave Management LOP contribution for one employee/month."""

    __tablename__ = "payroll_lop_inputs"
    __table_args__ = (
        UniqueConstraint(
            "leave_request_id",
            "employee_id",
            "month",
            "year",
            name="uq_payroll_lop_leave_emp_month_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_request_id: Mapped[str] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    lop_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="Leave Management", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    leave_request: Mapped["LeaveRequest"] = relationship()  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]
