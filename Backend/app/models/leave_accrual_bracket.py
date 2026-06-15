"""Tenure-bracket bonus accrual.

A row says: for `leave_type_id`, an employee with at least `min_years` of
tenure (measured from `Employee.date_of_joining`) earns an extra
`bonus_days_per_cycle` days on top of the base `LeaveType.accrual_days_per_cycle`.

Brackets stack additively per leave-type if multiple match (highest bracket
wins — service uses MAX). Inactive rows are ignored at run time so HR can
sunset a bracket without deleting historical config.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeaveAccrualBracket(Base):
    __tablename__ = "leave_accrual_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_type_id: Mapped[str] = mapped_column(
        ForeignKey("leave_types.id"), nullable=False, index=True
    )
    min_years: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_days_per_cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    leave_type: Mapped["LeaveType"] = relationship()  # type: ignore[name-defined]
