"""Pydantic schemas for the timesheet flow."""

from datetime import date as date_t, datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class TimesheetEntryIn(BaseModel):
    entry_date: date_t
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    logged_hours: float = 0.0
    is_billable: bool = True
    description: Optional[str] = None
    is_manual_entry: bool = True
    attendance_record_id: Optional[str] = None
    source: Optional[str] = None   # 'manual' | 'attendance_sync'


class TimesheetEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    timesheet_id: Optional[str] = None
    employee_id: Optional[int] = None
    entry_date: Optional[date_t] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None          # resolved from Project.name — populated by get_timesheet
    client_name: Optional[str] = None           # resolved from Project.client_name — populated by get_timesheet
    task_id: Optional[str] = None
    task_name: Optional[str] = None             # resolved from Task.name — populated by get_timesheet
    logged_hours: Optional[float] = None
    is_billable: bool = True
    source: Optional[str] = None
    description: Optional[str] = None
    is_manual_entry: bool
    attendance_record_id: Optional[str] = None
    attendance_status: Optional[str] = None  # "Present" or "Absent" — populated by manager view only


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
    # Monthly T&M report fields
    client_manager_id: Optional[int] = None
    client_manager_name: Optional[str] = None
    client_manager_email: Optional[str] = None
    client_token_expires_at: Optional[datetime] = None
    client_email_sent_at: Optional[datetime] = None
    client_email_status: Optional[str] = None
    client_approved_at: Optional[datetime] = None
    client_rejected_at: Optional[datetime] = None
    client_review_comment: Optional[str] = None
    has_mismatch: bool = False
    # Derived / joined fields — not ORM columns; populated by route handlers
    employee_name: Optional[str] = None
    project_name: Optional[str] = None
    client_name: Optional[str] = None


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


class TimesheetEntryEditRow(BaseModel):
    """One row in a HR PUT /hr/timesheets/{id}/entries payload."""
    id: Optional[str] = None            # None → new entry
    entry_date: Optional[date_t] = None # required for new entries
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    logged_hours: float = 0.0
    description: Optional[str] = None
    delete: bool = False                # True → delete this entry


class HRTimesheetEntriesIn(BaseModel):
    entries: list[TimesheetEntryEditRow] = []


class HRTimesheetOut(BaseModel):
    """Timesheet row returned by GET /hr/timesheets (client_site employees only)."""
    id: str
    employee_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_code: Optional[str] = None
    designation_title: Optional[str] = None
    department_name: Optional[str] = None
    period_type: Optional[str] = None
    period_start: Optional[date_t] = None
    period_end: Optional[date_t] = None
    total_logged_hours: Optional[float] = None
    status: Optional[str] = None
    submitted_at: Optional[datetime] = None
    is_locked: bool = False
    has_mismatch: bool = False
    locked_at: Optional[datetime] = None
    client_manager_name: Optional[str] = None
    client_manager_email: Optional[str] = None
    client_email_sent_at: Optional[datetime] = None
    client_email_status: Optional[str] = None
    client_approved_at: Optional[datetime] = None
    client_rejected_at: Optional[datetime] = None
    client_review_comment: Optional[str] = None
    manager_approved_at: Optional[datetime] = None


# ── Monthly T&M report schemas ────────────────────────────────────────────────

class MonthlyReportIn(BaseModel):
    """Payload for POST /timesheet/monthly-report (employee submits monthly report)."""
    client_manager_id: Optional[int] = None        # legacy FK — kept for compatibility only
    client_manager_name: Optional[str] = None      # override employee.client_manager_name for this submission
    client_manager_email: Optional[str] = None     # override employee.client_manager_email for this submission
    remarks: Optional[str] = None


class MonthlyDayOut(BaseModel):
    """One calendar day in a monthly report detail view."""
    date: date_t
    weekday: str                              # Mon, Tue, …
    is_weekend: bool
    status: Optional[str] = None             # present / absent / on_leave / holiday / half_day / late
    check_in_time: Optional[str] = None      # HH:MM
    check_out_time: Optional[str] = None     # HH:MM
    working_hours: Optional[float] = None
    overtime_hours: Optional[float] = None


class MonthlyReportDetailOut(TimesheetOut):
    """Full daily breakdown returned by GET /timesheet/{id}/monthly-detail."""
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    remarks: Optional[str] = None
    days: list[MonthlyDayOut] = []
    total_present_days: int = 0
    total_leave_days: int = 0
    total_half_days: int = 0
    total_holiday_days: int = 0
    total_overtime_hours: float = 0.0


# ── Bulk review ───────────────────────────────────────────────────────────────

class BulkReviewIn(BaseModel):
    timesheet_ids: List[str]
    decision: str           # 'approve' or 'reject'
    review_comment: Optional[str] = None


class BulkReviewOut(BaseModel):
    succeeded: List[str] = []
    failed: List[dict] = []    # [{"id": ..., "reason": ...}]


# ── Utilization schemas ───────────────────────────────────────────────────────

class UtilizationEmployeeOut(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    available_hours: float
    billable_hours: float
    non_billable_hours: float
    total_logged_hours: float
    utilization_pct: float      # billable / available * 100
    billable_pct: float         # billable / total_logged * 100 (0 if no hours)
    overtime_hours: float
    missing_timesheet: bool


class TeamUtilizationOut(BaseModel):
    period_start: date_t
    period_end: date_t
    total_employees: int
    available_hours: float
    billable_hours: float
    non_billable_hours: float
    utilization_pct: float
    underutilized: int          # utilization_pct < 60
    overallocated: int          # utilization_pct > 100
    missing_submissions: int
    employees: List[UtilizationEmployeeOut] = []


# ── Billing schemas ───────────────────────────────────────────────────────────

class ProjectCostRow(BaseModel):
    project_id: str
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    is_billable: bool
    billing_rate: Optional[float] = None
    total_hours: float
    billable_hours: float
    non_billable_hours: float
    revenue: float              # billable_hours × billing_rate
    headcount: int              # distinct employees who logged time


class BillingSummaryOut(BaseModel):
    period_start: date_t
    period_end: date_t
    total_billable_hours: float
    total_non_billable_hours: float
    total_revenue: float
    project_count: int
    projects: List[ProjectCostRow] = []


class ResourceCostRow(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    hourly_cost_rate: float
    total_hours: float
    billable_hours: float
    non_billable_hours: float
    total_cost: float           # total_hours × hourly_cost_rate
    billable_cost: float        # billable_hours × hourly_cost_rate
    utilization_pct: float


class ProjectCostingOut(BaseModel):
    period_start: date_t
    period_end: date_t
    total_cost: float
    total_billable_cost: float
    total_revenue: float
    profit_margin_pct: float    # (revenue - billable_cost) / revenue * 100
    resources: List[ResourceCostRow] = []
