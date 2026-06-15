"""WorkedOnLeaveRequest — validation sub-flow for the negative-flow scheduler.

When the scheduler detects an employee was present on a leave date, instead
of auto-reversing, it raises one of these requests. The employee's manager
or HR then approves (= reverse the leave, restore balance) or rejects
(= the employee took leave but worked anyway, so just consume the leave).
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkedOnLeaveRequest(Base):
    __tablename__ = "worked_on_leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_request_id: Mapped[str] = mapped_column(ForeignKey("leave_requests.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    # The dates within the leave range that attendance flagged as 'present'.
    # Stored as comma-separated ISO dates for portability with SQLite.
    present_dates: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    next_approver_role: Mapped[str | None] = mapped_column(String(10), nullable=True)

    manager_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hr_approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    leave_request: Mapped["LeaveRequest"] = relationship(foreign_keys=[leave_request_id])  # type: ignore[name-defined]
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
