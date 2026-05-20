"""Pydantic schemas for attendance, regularization, and exceptions."""

from datetime import date as date_t, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Punch (raw log) ───────────────────────────────────────────────────

class PunchIn(BaseModel):
    """Body for POST /attendance/check-in or /attendance/check-out."""
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
