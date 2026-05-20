"""Pydantic schemas for leave + notifications."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- Leave Types & Balances ----------------------------------------

class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    annual_quota: Optional[int] = None
    is_paid: bool = True
    applicable_gender: str = "all"


class LeaveBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    leave_type_id: str
    leave_type_name: Optional[str] = None
    year: int
    # Legacy fields (kept in sync with the new model for back-compat).
    opening_balance: int
    used: int
    reserved: int
    current_balance: int
    available: int = Field(0, description="allocated - reserved - pending (canonical)")
    # Phase 5A canonical model.
    allocated_balance: int = 0
    pending_balance: int = 0
    row_version: int = 0


# ---- Leave Requests ------------------------------------------------

class LeaveApplyIn(BaseModel):
    leave_type_id: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class RejectIn(BaseModel):
    reason: Optional[str] = None


class LeaveDraftIn(BaseModel):
    """Payload for creating a draft. Dates are required (matches the
    NOT NULL columns) but no validation is run, so past dates / overlaps
    are allowed at draft time. Validation fires only on submit."""
    leave_type_id: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class LeaveDraftUpdateIn(BaseModel):
    """Patch payload for editing a draft. All fields optional; only those
    present are updated."""
    leave_type_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None


class ApprovalStamp(BaseModel):
    by_id: Optional[int] = None
    by_name: Optional[str] = None
    at: Optional[datetime] = None


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: int
    employee_name: str
    employee_code: Optional[str] = None
    leave_type_id: str
    leave_type_name: str
    start_date: date
    end_date: date
    total_days: int
    reason: Optional[str] = None
    status: str
    next_approver_role: Optional[str] = None
    manager_approval: ApprovalStamp = ApprovalStamp()
    hr_approval: ApprovalStamp = ApprovalStamp()
    cancel_requested_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    # Phase 2 — SLA visibility
    sla_escalation_level: int = 0
    sla_last_alert_at: Optional[datetime] = None
    approver_override_id: Optional[int] = None
    # Phase 3 — payroll sync visibility
    payroll_sync_status: str = "na"
    payroll_synced_at: Optional[datetime] = None
    payroll_sync_attempts: int = 0
    payroll_last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class LeaveRequestDetailOut(LeaveRequestOut):
    audit: list[AuditEntryOut] = []


# ---- Notifications --------------------------------------------------

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recipient_id: int
    type: str
    title: str
    body: Optional[str] = None
    leave_request_id: Optional[str] = None
    reference_table: Optional[str] = None
    reference_id: Optional[str] = None
    action_url: Optional[str] = None
    meta_json: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    """Paginated envelope for the dedicated Notifications page."""
    items: list[NotificationOut]
    total: int
    unread: int
    limit: int
    offset: int


# ---- Comp-off + Attendance ----------------------------------------

class CompOffGrantIn(BaseModel):
    employee_id: int
    worked_on: date
    days: int = 1
    reason: Optional[str] = None
    proof_url: Optional[str] = None


class CompOffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    worked_on: date
    days: int
    reason: Optional[str] = None
    proof_url: Optional[str] = None
    status: str
    next_approver_role: Optional[str] = None
    manager_approved_at: Optional[datetime] = None
    hr_approved_at: Optional[datetime] = None
    expires_on: Optional[date] = None
    rejection_reason: Optional[str] = None
    created_at: datetime


class AttendanceMarkIn(BaseModel):
    employee_id: int
    date: date
    status: str = "present"
    note: Optional[str] = None


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    date: date
    status: str
    source: str
    note: Optional[str] = None
    created_at: datetime


class SchedulerRunOut(BaseModel):
    examined: int
    consumed: int
    reversed: int
    skipped_no_balance: int


# ---- Worked-on-Leave + Comp-off expiry ----------------------------

class WorkedOnLeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    leave_request_id: str
    employee_id: int
    employee_name: Optional[str] = None
    present_dates: list[str] = []
    status: str
    next_approver_role: Optional[str] = None
    manager_approved_at: Optional[datetime] = None
    hr_approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime


class CompOffExpiryRunOut(BaseModel):
    expired: int
    deducted_days: int


# ---- Delegate assignments (Phase 2) -------------------------------

class DelegateAssignmentIn(BaseModel):
    manager_id: int
    delegate_id: int
    start_date: date
    end_date: date
    reason: Optional[str] = None


class DelegateAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    manager_id: int
    manager_name: Optional[str] = None
    delegate_id: int
    delegate_name: Optional[str] = None
    start_date: date
    end_date: date
    reason: Optional[str] = None
    is_active: bool
    created_at: datetime


class SLASweepOut(BaseModel):
    examined: int
    reminded: int
    escalated: int
    hr_intervention: int


class PayrollRetryOut(BaseModel):
    examined: int
    synced: int
    failed: int
    skipped_max_attempts: int


class PayrollResetIn(BaseModel):
    """Admin payload to clear a stuck payroll row so retries can resume."""
    reset_attempts: bool = True
    new_status: str = "pending"   # 'pending' or 'na'


# ---- Documents (Phase 4) ------------------------------------------

class LeaveDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    leave_request_id: str
    original_filename: str
    content_type: Optional[str] = None
    size_bytes: int
    scan_status: str
    scan_engine: Optional[str] = None
    scan_detail: Optional[str] = None
    scanned_at: Optional[datetime] = None
    uploaded_by: int
    uploaded_at: datetime


# ---- Team capacity + blackout periods (Phase 4) -------------------

class TeamCapacityPolicyIn(BaseModel):
    manager_id: int
    max_concurrent_on_leave: int = 0
    # Phase 5C: % of the manager's active direct reports allowed on leave.
    # Effective cap is the LOWER of (max_concurrent_on_leave, ceil(team_size * pct / 100)).
    # Either knob alone is enforced; supplying both gives the tighter ceiling.
    max_concurrent_percent: Optional[int] = None


class TeamCapacityPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    manager_id: int
    max_concurrent_on_leave: int
    max_concurrent_percent: Optional[int] = None
    is_active: bool
    created_at: datetime


class BlackoutPeriodIn(BaseModel):
    scope_type: str    # 'global' | 'department' | 'manager'
    scope_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: Optional[str] = None


class BlackoutPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scope_type: str
    scope_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: Optional[str] = None
    is_active: bool
    created_at: datetime
