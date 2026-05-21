"""Rich attendance pipeline — raw punches, processed records, exceptions,
regularizations, overtime, payroll summary, and reports.

Mirrors the corresponding sheets in hrms_schema_complete.xlsx. The legacy
`attendance` table (app/models/attendance.py) is kept for the leave
negative-flow scheduler; this module adds the full schema model on top.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AttendanceLog(Base):
    """Raw punch event (mobile / biometric / web)."""
    __tablename__ = "attendance_logs"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. AL000001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    punch_type: Mapped[str] = mapped_column(String(20), nullable=False)   # check_in / check_out
    punch_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    device_info: Mapped[str | None]   = mapped_column(String(120), nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)  # mobile_app/biometric/web
    is_valid: Mapped[bool]     = mapped_column(Boolean, default=True, nullable=False)
    validation_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_rule: Mapped[str | None]  = mapped_column(String(60), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]


class ValidationError(Base):
    __tablename__ = "validation_errors"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. VE0001
    attendance_log_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_logs.id"), nullable=True, index=True)
    employee_id: Mapped[int | None]       = mapped_column(ForeignKey("employees.id"),      nullable=True, index=True)

    punch_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validation_rule: Mapped[str | None]      = mapped_column(String(60),  nullable=True)
    rule_description: Mapped[str | None]     = mapped_column(String(500), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)   # error / warning

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AttendanceRecord(Base):
    """Processed attendance row (one per employee + date)."""
    __tablename__ = "attendance_records"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. AR000001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    date: Mapped[date]       = mapped_column(Date, nullable=False, index=True)
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)

    check_in_time: Mapped[time | None]  = mapped_column(Time, nullable=True)
    check_out_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    working_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    late_minutes: Mapped[int | None]        = mapped_column(Integer, nullable=True)
    early_checkout_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overtime_hours: Mapped[float | None]    = mapped_column(Float, nullable=True)

    leave_request_id: Mapped[str | None] = mapped_column(ForeignKey("leave_requests.id"), nullable=True)
    is_regularized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    regularization_id: Mapped[str | None] = mapped_column(
        ForeignKey("regularization_requests.id", use_alter=True, name="fk_attrec_regrequest"),
        nullable=True,
    )
    lop_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lop_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship()  # type: ignore[name-defined]


class AttendanceException(Base):
    __tablename__ = "attendance_exceptions"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. AE0001
    attendance_record_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_records.id"), nullable=True, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)

    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None]    = mapped_column(String(500), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class RegularizationRequest(Base):
    __tablename__ = "regularization_requests"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. RR0001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    attendance_record_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_records.id"), nullable=True, index=True)

    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    regularization_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requested_check_in: Mapped[time | None]  = mapped_column(Time, nullable=True)
    requested_check_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attachment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # The list/review screens (admin + dashboard quick approvals) need the
    # employee's display name. Without this relationship the API surfaces only
    # `employee_id`, and the UI was falling back to "Employee #3" / initials
    # "E#". Pydantic's `from_attributes=True` picks up the @property below so
    # the schema gets `employee_name` for free.
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]

    @property
    def employee_name(self) -> str | None:
        return self.employee.full_name if self.employee else None


class RegularizationAttachment(Base):
    __tablename__ = "regularization_attachments"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. RA0001
    regularization_id: Mapped[str | None] = mapped_column(ForeignKey("regularization_requests.id"), nullable=True, index=True)
    employee_id: Mapped[int | None]       = mapped_column(ForeignKey("employees.id"),                nullable=True, index=True)

    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_url: Mapped[str | None]  = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(40),  nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OvertimeRecord(Base):
    __tablename__ = "overtime_records"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. OT0001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    attendance_record_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_records.id"), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    overtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    overtime_type: Mapped[str | None]    = mapped_column(String(40), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    comp_leave_request_id: Mapped[str | None] = mapped_column(ForeignKey("leave_requests.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AttendanceReport(Base):
    __tablename__ = "attendance_reports"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. RPT0001
    report_type: Mapped[str | None]  = mapped_column(String(60), nullable=True)
    report_scope: Mapped[str | None] = mapped_column(String(60), nullable=True)
    generated_for_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None]   = mapped_column(Date, nullable=True)

    generated_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    file_url: Mapped[str | None]    = mapped_column(String(500), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_frequency: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class PayrollAttendanceSummary(Base):
    __tablename__ = "payroll_attendance_summary"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. PAS00001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    month: Mapped[str | None] = mapped_column(String(20),  nullable=True)
    year: Mapped[int | None]  = mapped_column(Integer,     nullable=True, index=True)

    total_working_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    present_days: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    absent_days: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    half_days: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    late_days: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    leave_days: Mapped[int | None]     = mapped_column(Integer, nullable=True)
    holiday_count: Mapped[int | None]  = mapped_column(Integer, nullable=True)
    lop_days: Mapped[int | None]       = mapped_column(Integer, nullable=True)
    overtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class WeeklyOffChangeRequest(Base):
    """Employee request to change their weekly-off day(s).

    Workflow: pending → approved (takes effect on effective_from) or rejected.
    Approved requests trigger a shift update (weekly_off_days) for the employee.
    """
    __tablename__ = "weekly_off_change_requests"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. WO0001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    current_weekly_off: Mapped[str | None] = mapped_column(String(60), nullable=True)
    requested_weekly_off: Mapped[str] = mapped_column(String(60), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
