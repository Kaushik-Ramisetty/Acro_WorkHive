"""Pydantic schemas for the timesheet flow."""

from datetime import date as date_t, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TimesheetEntryIn(BaseModel):
    entry_date: date_t
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    logged_hours: float
    description: Optional[str] = None
    is_manual_entry: bool = True
    attendance_record_id: Optional[str] = None


class TimesheetEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    timesheet_id: Optional[str] = None
    employee_id: Optional[int] = None
    entry_date: Optional[date_t] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    logged_hours: Optional[float] = None
    source: Optional[str] = None
    description: Optional[str] = None
    is_manual_entry: bool
    attendance_record_id: Optional[str] = None


class TimesheetCreateIn(BaseModel):
    period_type: str        # 'weekly' / 'monthly' / 'daily'
    period_start: date_t
    period_end: date_t
    entries: list[TimesheetEntryIn] = []


class TimesheetSubmitIn(BaseModel):
    pass


class TimesheetReviewIn(BaseModel):
    decision: str           # 'approve' or 'reject'
    review_comment: Optional[str] = None


class TimesheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    period_type: Optional[str] = None
    period_start: Optional[date_t] = None
    period_end: Optional[date_t] = None
    total_logged_hours: Optional[float] = None
    status: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_by: Optional[int] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    is_locked: bool
    locked_at: Optional[datetime] = None


class TimesheetDetailOut(TimesheetOut):
    entries: list[TimesheetEntryOut] = []


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_code: Optional[str] = None
    name: Optional[str] = None
    client_name: Optional[str] = None
    status: Optional[str] = None
    is_billable: bool


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None
