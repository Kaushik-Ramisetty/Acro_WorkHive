"""Pydantic schemas for the Recruiter module.

All Optional fields explicitly default to None so Pydantic v2 treats them
as truly optional (no 'Field required' validation error when omitted).
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class RecruiterStats(BaseModel):
    open_reqs: int
    total_candidates: int
    pending_review: int
    interviews_this_week: int
    offers_sent: int


class PipelineStage(BaseModel):
    label: str
    status: str
    feedback: str = ""
    managerRemark: str = ""
    interviewer: Optional[str] = None
    interview_date: Optional[str] = None
    interview_time: Optional[str] = None
    rejection_reason: Optional[str] = None


class AssignRecruiterRequest(BaseModel):
    recruiter_id: int


class RecruiterItem(BaseModel):
    id: int
    name: str
    employee_code: Optional[str] = None


class CandidateDetailOut(BaseModel):
    candidate_id: str
    full_name: str
    role: Optional[str]         = None
    email: Optional[str]        = None
    phone: Optional[str]        = None
    exp: Optional[str]          = None
    employer: Optional[str]     = None
    ctc: Optional[int]          = None
    expCtc: Optional[int]       = None
    notice: Optional[str]       = None
    source: Optional[str]       = None
    curr_location: Optional[str] = None
    skills: List[str] = []
    notes: Optional[str]        = None
    resume_url: Optional[str]   = None
    cover_letter_url: Optional[str] = None
    pipeline_id: Optional[int]  = None
    pipeline: List[PipelineStage] = []
    mgr_approval_status: Optional[str] = None
    rejection_reason: Optional[str]    = None
    rejected_by: Optional[str]         = None
    rejected_at: Optional[str]         = None
    onboarded_at: Optional[datetime]   = None


class CandidateListItem(BaseModel):
    db_id: int
    candidate_id: str
    full_name: str
    email: Optional[str]       = None
    role: Optional[str]        = None
    source: Optional[str]      = None
    exp: Optional[str]         = None
    ctc: Optional[int]         = None
    stage: Optional[str]       = None
    stage_type: str = "gray"
    req_id: Optional[str]      = None
    pipeline_id: Optional[int] = None
    is_selected: bool = False
    onboarded_at: Optional[datetime] = None


class CandidateCreate(BaseModel):
    first_name: str         = Field(..., min_length=1)
    last_name: Optional[str]         = None
    email: str
    mobile: Optional[str]            = None
    current_job_title: Optional[str] = None
    current_employer: Optional[str]  = None
    current_ctc: Optional[int]       = None
    expected_ctc: Optional[int]      = None
    curr_location: Optional[str]     = None
    notice_period: Optional[str]     = None
    experience_years: Optional[float] = None
    source: Optional[str]            = None
    other_source: Optional[str]      = None
    requirement_id: Optional[int]    = None
    skills: Optional[List[str]]      = []


class RequirementListItem(BaseModel):
    db_id: int
    req_id: str
    title: str
    client_name: Optional[str]          = None
    department: Optional[str]             = None
    department_id: Optional[str]          = None
    priority: Optional[str]               = None
    priority_type: str                    = "gray"
    skills: List[str]                     = []
    candidate_count: int                  = 0
    openings: int                         = 0
    min_experience: Optional[int]         = None
    max_experience: Optional[int]         = None
    assigned_recruiter_name: Optional[str] = None
    assigned_recruiter_id: Optional[int]  = None
    assigned_by_name: Optional[str]       = None
    assigned_at: Optional[datetime]       = None
    location: Optional[str]              = None
    work_mode: Optional[str]             = None
    employment_type: Optional[str]       = None
    budget_range: Optional[str]          = None
    target_joining: Optional[str]        = None
    qualification: Optional[str]         = None
    created_by_name: Optional[str]       = None
    created_by_id: Optional[int]         = None
    status: str
    created_date: Optional[str]          = None
    job_description: Optional[str]       = None


class PipelineCardOut(BaseModel):
    pipeline_id: int
    candidate_id: str
    candidate_name: str
    role: Optional[str]          = None
    company: Optional[str]       = None
    exp: Optional[str]           = None
    ctc: Optional[int]           = None
    req_id: str
    stage: str
    interview_date: Optional[str] = None
    interviewer: Optional[str]   = None
    skills: List[str] = []
    is_special: bool = False
    pending_slots: bool = False
    rejection_reason: Optional[str] = None
    rejected_by: Optional[str]      = None
    rejected_at: Optional[str]      = None


class InterviewListItem(BaseModel):
    round_id: int
    round_order: Optional[str]   = None
    pipeline_id: int
    candidate_id: str
    candidate_name: str
    role: Optional[str]          = None
    round_name: str
    round_type: Optional[str]    = None
    interviewer_name: Optional[str]  = None
    interviewer_code: Optional[str]  = None
    interview_date: Optional[str]    = None
    interview_time: Optional[str]    = None
    interview_format: Optional[str]  = None
    meeting_link: Optional[str]      = None
    status: str
    status_type: str = "gray"
    actions: List[str] = []


class ActiveInterviewOut(BaseModel):
    round_id: int
    pipeline_id: int
    candidate_id: str
    candidate_name: str
    role: Optional[str]          = None
    req_id: str
    round_name: str
    round_type: str = "blue"
    interviewer_name: Optional[str]  = None
    date_label: Optional[str]        = None
    interview_format: Optional[str]  = None
    meeting_link: Optional[str]      = None
    status: str
    status_label: str
    status_color: str = "#16a34a"


class UpcomingInterviewOut(BaseModel):
    round_id: int
    pipeline_id: int
    candidate_id: str
    candidate_name: str
    sub: str
    day: Optional[int]           = None
    month: Optional[str]         = None
    time_label: str
    interviewer_name: Optional[str]  = None
    interview_format: Optional[str]  = None
    pending: bool = False


class RescheduleRequest(BaseModel):
    """Reschedule an existing interview. new_date + new_time are required."""
    new_date: str
    new_time: str
    interviewer_code: Optional[str] = None
    interview_format: Optional[str] = None
    reason: Optional[str]           = None


class AddRoundRequest(BaseModel):
    """Add an additional interview round mid-pipeline."""
    pipeline_id: int
    round_name: str             = Field(..., min_length=1)
    round_type: Optional[str]  = "Technical"
    interviewer_code: Optional[str]  = None
    interview_date: Optional[str]    = None
    interview_time: Optional[str]    = None
    interview_format: Optional[str]  = None
    reason: Optional[str]            = None


class AssignInterviewerRequest(BaseModel):
    """
    Step 6 of recruitment workflow:
    Recruiter assigns an interviewer to an Approved candidate.

    Creates the round assignment ONLY — no date/time/meeting link at this stage.
    Interviewer adds available slots later; candidate selects one slot.

    Required: candidate_id, interviewer_code
    Optional (all = None): interview_date, interview_time, meeting_link
    """
    candidate_id: str           = Field(..., min_length=1)
    round_name: str             = Field(default="Technical Round")
    round_type: Optional[str]  = "Technical"
    interviewer_code: str       = Field(..., min_length=1)
    # These are populated LATER when the candidate selects a slot — not at assignment time
    interview_date: Optional[str]    = None
    interview_time: Optional[str]    = None
    interview_format: Optional[str]  = "Teams"
    meeting_link: Optional[str]      = None


class RecruiterNotesUpdate(BaseModel):
    notes: str


class CandidateDuplicateCheckIn(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None


class DuplicateCandidateInfo(BaseModel):
    candidate_id: str
    candidate_name: str
    email: Optional[str] = None
    mobile: Optional[str] = None
    created_date: Optional[str] = None


class CandidateDuplicateCheckOut(BaseModel):
    duplicate_found: bool = False
    matched_candidate_id: Optional[str] = None
    matched_by: List[str] = []
    matched_candidate: Optional[DuplicateCandidateInfo] = None
