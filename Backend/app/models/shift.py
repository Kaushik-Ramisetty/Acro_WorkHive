"""Shift / attendance-policy / overtime-rule / employee-shift / holiday models.

Mirrors the `shifts`, `attendance_policies`, `overtime_rules`,
`employee_shifts` and `holidays` sheets in hrms_schema_complete.xlsx.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. SH001
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None]   = mapped_column(Time, nullable=True)

    grace_period_mins: Mapped[int]    = mapped_column(Integer, default=0, nullable=False)
    break_duration_mins: Mapped[int]  = mapped_column(Integer, default=0, nullable=False)
    # Comma-separated weekday names: e.g. "Saturday,Sunday".
    weekly_off_days: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flexible: Mapped[bool]    = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AttendancePolicy(Base):
    __tablename__ = "attendance_policies"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. AP001
    shift_id: Mapped[str] = mapped_column(ForeignKey("shifts.id"), nullable=False, index=True)
    policy_name: Mapped[str] = mapped_column(String(120), nullable=False)

    min_working_hours_full_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_working_hours_half_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    overtime_threshold_hours: Mapped[float | None]   = mapped_column(Float, nullable=True)
    short_day_cutoff_hours: Mapped[float | None]     = mapped_column(Float, nullable=True)

    late_deduction_after_mins: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    absent_after_missing_mins: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    weekly_overtime_threshold: Mapped[float | None]  = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    shift: Mapped["Shift"] = relationship()


class OvertimeRule(Base):
    __tablename__ = "overtime_rules"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. OTR001
    policy_id: Mapped[str] = mapped_column(ForeignKey("attendance_policies.id"), nullable=False, index=True)

    # weekday / weekend / public_holiday
    day_type: Mapped[str] = mapped_column(String(30), nullable=False)
    rate_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    min_overtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_overtime_hours_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    comp_leave_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    policy: Mapped["AttendancePolicy"] = relationship()


class EmployeeShift(Base):
    __tablename__ = "employee_shifts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. ES001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    shift_id: Mapped[str]    = mapped_column(ForeignKey("shifts.id"),    nullable=False, index=True)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]
    shift: Mapped["Shift"]       = relationship()


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. HOL001
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    holiday_type: Mapped[str | None] = mapped_column(String(30), nullable=True)   # public / national
    applicable_locations: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Phase 5B: optional holidays are filtered out of the default list and
    # only surface to employees in `applicable_locations`. Counts against the
    # 'Optional Holiday' leave-type quota when consumed.
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
