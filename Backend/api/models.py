"""api/models.py — compatibility shim re-exporting from app.models.*"""

from app.models import (  # noqa: F401
    Department, Designation, Employee, Role,
    LeaveType, LeaveBalance, LeaveRequest,
    Candidate, CandidateDocument, DocumentStatus,
    CandidateStatus, CANDIDATE_TRANSITIONS,
    BGVCheck, BGVStatus, BGVToken,
    OnboardedEmployee, OnboardedEmployeeStatus,
    User, UserRole,
)

import enum


class EmploymentStatus(str, enum.Enum):
    active    = "active"
    on_notice = "on_notice"
    exited    = "exited"
    suspended = "suspended"


class Gender(str, enum.Enum):
    male   = "male"
    female = "female"
    other  = "other"


class LeaveRequestStatus(str, enum.Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    CANCELLED = "CANCELLED"
    WITHDRAWN = "WITHDRAWN"


__all__ = [
    "Department", "Designation", "Employee", "Role",
    "LeaveType", "LeaveBalance", "LeaveRequest", "LeaveRequestStatus",
    "Candidate", "CandidateDocument", "DocumentStatus",
    "CandidateStatus", "CANDIDATE_TRANSITIONS",
    "BGVCheck", "BGVStatus", "BGVToken",
    "OnboardedEmployee", "OnboardedEmployeeStatus",
    "User", "UserRole",
    "EmploymentStatus", "Gender",
]
