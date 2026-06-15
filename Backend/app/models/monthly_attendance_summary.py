"""Monthly Attendance Summary — payroll integration bridge.

╔══════════════════════════════════════════════════════════════════════════╗
║  TEMPORARY PAYROLL BRIDGE                                                 ║
║  In production this table will be populated by the Attendance/Timesheet  ║
║  modules.  Until those modules are ready, HR/Admin can insert or update   ║
║  rows manually via the /payroll/attendance-summary/manual endpoint.       ║
║                                                                           ║
║  Integration contract (future):                                           ║
║    Attendance module → writes present_days, leave_days                   ║
║    Leave Management → writes payroll LOP days                            ║
║    Timesheet module  → writes approved_timesheet_hours, timesheet_status  ║
║    Payroll module    → reads this table; NEVER writes attendance data      ║
║                        except is_frozen / finalized_by / finalized_at     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MonthlyAttendanceSummary(Base):
    """One row per (employee, month, year) — the canonical payroll input snapshot.

    attendance_status values : pending | submitted | validated | finalized | issues
    timesheet_status values  : pending | submitted | approved
    validation_status values : pending | passed | failed
    """
    __tablename__ = "monthly_attendance_summary"
    __table_args__ = (
        UniqueConstraint("employee_id", "month", "year", name="uq_mas_emp_month_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)   # 1–12
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # ── Attendance fields (source: Attendance module, or manual bridge) ───────
    total_working_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    present_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lop_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payable_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lop_source: Mapped[str] = mapped_column(String(50), default="Leave Management", nullable=False)
    lop_status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    lop_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Timesheet fields (source: Timesheet module, or manual bridge) ─────────
    approved_timesheet_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # ── Status fields ─────────────────────────────────────────────────────────
    attendance_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    timesheet_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    validation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    issues_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Payroll readiness flags ───────────────────────────────────────────────
    is_ready_for_payroll: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # is_frozen = True → payroll generation allowed; HR cannot unfreeze after this
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    finalized_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    finalizer: Mapped["Employee | None"] = relationship(foreign_keys=[finalized_by])  # type: ignore[name-defined]
