"""Attendance model — minimal stub for the leave negative flow.

A row per (employee, date) records what the attendance system observed.
Status values: 'present', 'absent', 'wfh', 'leave', 'holiday'.

The negative-flow scheduler reads this table to decide whether an approved
leave should be CONSUMED (employee was absent) or REVERSED (employee
actually came in / worked).

Source values: 'manual', 'biometric', 'import' — whatever later integrations
populate this from. 'manual' for the seed.
"""
from datetime import date as date_t, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_attendance_emp_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    date: Mapped[date_t] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="present", index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]
