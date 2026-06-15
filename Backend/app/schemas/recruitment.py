"""
Pydantic schemas for the Recruitment module.
Request bodies and response shapes mirror exactly what the frontend expects.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Skill schemas
# ─────────────────────────────────────────────────────────────────────────────

class SkillItem(BaseModel):
    name: str
    category: Optional[str] = None


class SkillSearchResponse(BaseModel):
    results: List[SkillItem]
    query: str
    total: int


class SkillRequestCreate(BaseModel):
    skill_name: str    = Field(..., min_length=2, max_length=100)
    requirement_id: int
    is_primary: bool   = False


class SkillRequestOut(BaseModel):
    id: int
    skill_name: str
    requirement_id: int
    status: str
    requested_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Requirement schemas
# ─────────────────────────────────────────────────────────────────────────────

class RequirementCreate(BaseModel):
    title: str                              = Field(..., min_length=2, max_length=200)
    client_name: Optional[str]              = None
    department_id: Optional[str]            = None
    employment_type: Optional[str]          = None
    work_mode: Optional[str]               = None
    location: Optional[str]                = None
    min_experience: Optional[int]           = None
    max_experience: Optional[int]           = None
    openings: int                           = Field(1, ge=1)
    priority: Optional[str]                = "Normal"
    skills: Optional[List[str]]            = []      # approved skills
    pending_skills: Optional[List[str]]    = []      # skills awaiting recruiter approval
    job_description: Optional[str]         = None
    qualification: Optional[str]           = None
    budget_range: Optional[str]            = None
    target_joining: Optional[date]         = None


class RequirementStatusUpdate(BaseModel):
    status: str  # Active / In Review / Sourcing / Closed


class RequirementUpdate(BaseModel):
    title: Optional[str]               = None
    client_name: Optional[str]         = None
    department_id: Optional[str]       = None
    employment_type: Optional[str]     = None
    work_mode: Optional[str]           = None
    location: Optional[str]            = None
    min_experience: Optional[int]      = None
    max_experience: Optional[int]      = None
    openings: Optional[int]            = None
    priority: Optional[str]            = None
    skills: Optional[List[str]]        = None
    job_description: Optional[str]     = None
    qualification: Optional[str]       = None
    budget_range: Optional[str]        = None
    target_joining: Optional[date]     = None


class RequirementOut(BaseModel):
    """Shape returned to the frontend — matches mock REQUIREMENTS structure."""
    id: str                              # req_id string e.g. REQ-0841
    db_id: int                           # integer PK for FK operations
    title: str
    client_name: Optional[str] = None
    department: Optional[str]  = None   # department name (resolved)
    department_id: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str]       = None
    location: Optional[str]        = None
    min_exp: Optional[int]         = None
    max_exp: Optional[int]         = None
    openings: int
    priority: Optional[str]        = None
    skills: List[str]              = []
    pending_skills: List[str]      = []
    jd: Optional[str]              = None   # maps to job_description
    preferred_qualification: Optional[str] = None
    target_joining: Optional[str]  = None   # ISO date string
    budget_range: Optional[str]    = None
    status: str
    pipeline: int                  = 0      # count of active pipeline entries
    created: Optional[str]         = None   # YYYY-MM-DD
    created_by_name: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Candidate / pipeline schemas
# ─────────────────────────────────────────────────────────────────────────────

class InterviewRoundOut(BaseModel):
    name: str
    status: str
    interviewer: Optional[str] = None
    date: Optional[str]        = None
    time: Optional[str]        = None
    format: Optional[str]      = None
    feedback: Optional[str]    = None
    manager_remark: Optional[str] = None


class CandidateOut(BaseModel):
    """Matches mock CANDIDATES shape — each pipeline entry becomes one candidate card."""
    id: str                          # candidate_id e.g. CAND01
    db_id: int                       # recruitment_candidates.id
    pipeline_id: int                 # candidate_pipeline.id
    name: str
    req: str                         # req_id e.g. REQ-0841
    req_db_id: int                   # job_requirements.id
    role: Optional[str]    = None
    exp: Optional[str]     = None
    company: Optional[str] = None
    notice: Optional[str]  = None
    ctc: Optional[int]     = None
    exp_ctc: Optional[int] = None
    skills: List[str]      = []
    stage: str
    status: str                      # active / awaiting / approved / rejected / joining
    mgr_approval_status: str
    manager_remark: Optional[str]    = None
    rejection_reason: Optional[str]  = None
    interview_rounds: List[InterviewRoundOut] = []
    offer_status: Optional[str]      = None
    onboarding_date: Optional[str]   = None
    current_company: Optional[str]   = None
    resume_url: Optional[str]        = None   # relative path: uploads/recruitment/resumes/{uuid}.ext


class ApprovalAction(BaseModel):
    action: str                         = Field(..., pattern="^(approve|reject)$")
    remark: Optional[str]               = None
    rejection_reason: Optional[str]     = None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard schema
# ─────────────────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    open_reqs: int
    in_pipeline: int
    awaiting_approval: int
    interviews_sched: int
    positions_closed: int


# ─────────────────────────────────────────────────────────────────────────────
# Notification schema
# ─────────────────────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: str
    type: str
    message: str
    time: str
    read: bool
