"""Pydantic schemas for the Interviewer module."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class InterviewerStats(BaseModel):
    assigned: int
    today: int
    pending_feedback: int
    completed: int


class SlotOut(BaseModel):
    id: int
    slot_date: Optional[str] = None
    slot_time: Optional[str] = None
    is_selected: bool = False


class PreviousFeedbackOut(BaseModel):
    round: str
    date: str
    recommendation: Optional[str] = None
    notes: Optional[str] = None


class InterviewerAssignment(BaseModel):
    round_id: int
    pipeline_id: int
    candidate_id: str
    candidate_name: str
    initials: str
    role: Optional[str] = None
    req_id: str
    req_db_id: int
    round: str
    exp: Optional[str] = None
    company: Optional[str] = None
    ctc: Optional[str] = None
    exp_ctc: Optional[str] = None
    notice: Optional[str] = None
    source: Optional[str] = None
    skills: List[str] = []
    status: str
    date: Optional[str] = None
    time: Optional[str] = None
    teams_link: Optional[str] = None
    manager_remark: Optional[str] = None
    recruiter_notes: Optional[str] = None
    resume_url: Optional[str] = None
    previous_feedback: List[PreviousFeedbackOut] = []
    slots: List[SlotOut] = []


class CalendarEvent(BaseModel):
    round_id: int
    candidate_name: str
    date: str            # "YYYY-MM-DD"
    day: int
    month: str           # e.g. "May"
    year: int
    time: Optional[str] = None   # formatted for display e.g. "2:00 PM"
    role: Optional[str] = None
    req_id: str


class FeedbackHistoryItem(BaseModel):
    id: int
    candidate_id: str
    candidate_name: str
    initials: str
    role: Optional[str] = None
    round: str
    date: str
    recommendation: Optional[str] = None
    technical_rating: Optional[int] = None
    comm_rating: Optional[int] = None
    problem_rating: Optional[int] = None
    notes: Optional[str] = None


class FeedbackSubmit(BaseModel):
    technical_rating: int = Field(..., ge=0, le=5)
    comm_rating: int      = Field(..., ge=0, le=5)
    problem_rating: int   = Field(..., ge=0, le=5)
    recommendation: str
    notes: str            = Field(..., min_length=1)
