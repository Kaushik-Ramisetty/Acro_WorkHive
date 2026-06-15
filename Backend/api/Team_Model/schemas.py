"""Pydantic schemas for the team-management endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Inputs --------------------------------------------------

class TeamCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    department_id: Optional[str] = None
    lead_id: Optional[int] = None
    # Optional initial roster — admin can omit and add members later.
    member_ids: List[int] = Field(default_factory=list)


class TeamUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    department_id: Optional[str] = None
    lead_id: Optional[int] = None
    is_active: Optional[bool] = None


class TeamMemberIn(BaseModel):
    employee_id: int
    role_in_team: Optional[str] = None


# ---------- Outputs -------------------------------------------------

class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    designation: Optional[str] = None
    role_in_team: Optional[str] = None
    is_active: bool
    added_at: datetime


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    lead_id: Optional[int] = None
    lead_name: Optional[str] = None
    is_active: bool
    member_count: int
    active_project_count: int
    created_at: datetime
    updated_at: datetime


class TeamDetailOut(TeamOut):
    members: List[TeamMemberOut] = Field(default_factory=list)
    active_project_ids: List[str] = Field(default_factory=list)


class TeamSummaryOut(BaseModel):
    """Dashboard top-of-page summary."""
    total_teams: int
    total_members: int
    active_projects: int
    departments_with_teams: int
