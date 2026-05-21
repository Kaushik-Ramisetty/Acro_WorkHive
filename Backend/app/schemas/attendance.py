"""Pydantic schemas for attendance, regularization, and exceptions."""

from datetime import date as date_t, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Punch (raw log) ───────────────────────────────────────────────────

class PunchIn(BaseModel):
    """Body for POST /attendance/check-in, /check-out, or /punch (unified)."""
    punch_type: Optional[str] = None    # required for /punch; ignored for /check-in|out
    device_info: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    source: str = "web"


class AttendanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    punch_type: str
    punch_timestamp: datetime
    device_info: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    source: Optional[str] = None
    is_valid: bool
    validation_error: Optional[str] = None
    validation_rule: Optional[str] = None


# ── Processed record (final) ──────────────────────────────────────────

class AttendanceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    date: date_t
    shift_id: Optional[str] = None
    check_in_time: Optional[time] = None
    check_out_time: Optional[time] = None
    working_hours: Optional[float] = None
    status: Optional[str] = None
    late_minutes: Optional[int] = None
    early_checkout_mins: Optional[int] = None
    overtime_hours: Optional[float] = None
    leave_request_id: Optional[str] = None
    is_regularized: bool
    regularization_id: Optional[str] = None
    lop_applied: bool
    lop_type: Optional[str] = None


class AttendanceExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    attendance_record_id: Optional[str] = None
    employee_id: Optional[int] = None
    date: Optional[date_t] = None
    exception_type: Optional[str] = None
    description: Optional[str] = None
    is_resolved: bool


class CheckInResponse(BaseModel):
    log: AttendanceLogOut
    record: Optional[AttendanceRecordOut] = None
    message: str


class TodayStatusOut(BaseModel):
    today: date_t
    has_checked_in: bool
    has_checked_out: bool
    last_punch: Optional[AttendanceLogOut] = None
    record: Optional[AttendanceRecordOut] = None


# ── Regularization ────────────────────────────────────────────────────

class RegularizationCreateIn(BaseModel):
    date: date_t
    regularization_type: str   # full_day / wrong_time / missed_checkout
    requested_check_in: Optional[time] = None
    requested_check_out: Optional[time] = None
    reason: Optional[str] = None
    attachment_url: Optional[str] = None


class RegularizationReviewIn(BaseModel):
    status: str               # 'approved' or 'rejected'
    review_comment: Optional[str] = None


class RegularizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    # Populated by the `employee_name` @property on RegularizationRequest
    # (picked up because from_attributes=True). Lets the admin Quick Approvals
    # widget + Regularizations table show the real name instead of "#3".
    employee_name: Optional[str] = None
    attendance_record_id: Optional[str] = None
    date: Optional[date_t] = None
    regularization_type: Optional[str] = None
    requested_check_in: Optional[time] = None
    requested_check_out: Optional[time] = None
    reason: Optional[str] = None
    attachment_url: Optional[str] = None
    status: str
    reviewed_by: Optional[int] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


# ── Admin override ────────────────────────────────────────────────────

class AdminAttOverrideIn(BaseModel):
    employee_id: int
    date: date_t
    status: Optional[str] = None  # None = clear (backend writes 'absent')


# ── Overtime request ──────────────────────────────────────────────────

class OvertimeRequestIn(BaseModel):
    date: date_t
    overtime_hours: float
    reason: Optional[str] = None
    notes: Optional[str] = None


class OvertimeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    date: Optional[date_t] = None
    overtime_hours: Optional[float] = None
    overtime_type: Optional[str] = None
    status: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


# ── Comp-off self-service ─────────────────────────────────────────────

class CompOffRequestIn(BaseModel):
    worked_on: date_t
    reason: Optional[str] = None


class CompOffRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    worked_on: date_t
    days: int
    reason: Optional[str] = None
    status: str
    next_approver_role: Optional[str] = None
    expires_on: Optional[date_t] = None
    rejection_reason: Optional[str] = None
    created_at: datetime


# ── Weekly-off change request ─────────────────────────────────────────

class WeeklyOffChangeRequestIn(BaseModel):
    requested_weekly_off: str   # e.g. "Sunday"
    effective_from: Optional[date_t] = None
    reason: Optional[str] = None


class WeeklyOffChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    current_weekly_off: Optional[str] = None
    requested_weekly_off: str
    effective_from: Optional[date_t] = None
    reason: Optional[str] = None
    status: str
    reviewed_by: Optional[int] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
