"""Pydantic schemas for the resource-management endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Input payloads -----------------------------------------

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    manager_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    client_name: Optional[str] = None
    department_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_dates(self) -> "ProjectCreate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class AssignEmployeeIn(BaseModel):
    employee_id: int
    project_id: str
    start_date: date
    end_date: Optional[date] = None
    manager_id: Optional[int] = None
    skills: List[str] = Field(default_factory=list)
    allocation_status: str = "active"  # 'active' | 'inactive'

    @model_validator(mode="after")
    def _check_dates(self) -> "AssignEmployeeIn":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class CreateProjectAndAssignIn(BaseModel):
    employee_id: int
    project_name: str = Field(..., min_length=1, max_length=200)
    manager_id: Optional[int] = None
    skills: List[str] = Field(default_factory=list)
    allocation_status: str = "active"
    start_date: date
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def _check_dates(self) -> "CreateProjectAndAssignIn":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ReleaseEmployeeIn(BaseModel):
    employee_id: int
    project_id: str


class ExtendProjectIn(BaseModel):
    project_id: str
    new_end_date: date


class ReassignIn(BaseModel):
    employee_id: int
    from_project_id: str
    to_project_id: str
    new_start_date: date
    new_end_date: Optional[date] = None
    manager_id: Optional[int] = None


class EmployeeResourceDetailsIn(BaseModel):
    """Payload used by the admin "Edit" modal on the bench page.
    All fields optional — only what's present is updated."""
    skills: Optional[List[str]] = None
    project_id: Optional[str] = None
    manager_id: Optional[int] = None
    allocation_status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Phase 6: resource-profile updates (no allocation effect).
    experience_years: Optional[int] = None
    certifications: Optional[str] = None


# ---------- Output payloads ----------------------------------------

class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    project_id: str
    project_name: Optional[str] = None
    manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: str
    created_at: datetime


class TeamMemberOut(BaseModel):
    """One row per allocation. An employee on N projects appears N times.

    The FE keys table rows by `${employee_id}-${project_id || 'none'}` so
    both allocated and unallocated rows reconcile without React duplicate-key
    warnings. Unallocated direct reports come back with allocation_id=null
    and project_id=null so the FE can hide Release/Extend buttons for them.
    """
    id: int                              # employee_id
    name: str
    role: Optional[str] = None
    dept: Optional[str] = None
    email: Optional[str] = None
    employee_code: Optional[str] = None
    allocation_id: Optional[int] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    proj_start: Optional[date] = None
    proj_end: Optional[date] = None


class EmployeeWithAllocationOut(BaseModel):
    id: int
    name: str
    employee_code: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    has_active_allocation: bool
    active_allocation_count: int
    skills: List[str] = Field(default_factory=list)
    # Phase 6: resource-profile fields surfaced for the bench dashboard.
    experience_years: Optional[int] = None
    certifications: Optional[str] = None
    # Convenience block summarising the most recent active allocation.
    latest_project_id: Optional[str] = None
    latest_project_name: Optional[str] = None
    latest_manager_id: Optional[int] = None
    latest_manager_name: Optional[str] = None
    latest_start_date: Optional[date] = None
    latest_end_date: Optional[date] = None


class BenchEmployeeOut(BaseModel):
    id: int
    name: str
    employee_code: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience_years: Optional[int] = None
    certifications: Optional[str] = None
    bench_duration_days: int = 0  # 0 = never allocated; else days since last actual_end_date


class EmployeeProjectOut(BaseModel):
    """Project history row used by the History modal. Deduplicated by
    project_name (case-insensitive) keeping the most recent allocation."""
    allocation_id: int
    project_id: str
    project_name: Optional[str] = None
    manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    status: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: Optional[str] = None
    project_manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
