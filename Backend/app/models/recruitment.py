"""
Recruitment ORM models -- Acronotics WorkHive

KEY DESIGN:
  - interviewer_id, added_by, mgr_approval_by, shortlisted_by,
    requested_by, approved_by  -> TEXT (employee codes like AIN715)
  - assign_to_recruitment      -> TEXT (e.g. 'REQ-0041 . Backend Engineer')
  - candidate_pipeline.candidate_id -> TEXT (e.g. 'CAND01')
  Integer FKs:
    candidate_pipeline.requirement_id  -> job_requirements.id
    interview_rounds.pipeline_id       -> candidate_pipeline.id
    requirement_skills.requirement_id  -> job_requirements.id
    interview_slots.round_id           -> interview_rounds.id
    interview_feedback.round_id        -> interview_rounds.id
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobRequirement(Base):
    __tablename__ = "job_requirements"

    id:                  Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    req_id:              Mapped[str]        = mapped_column(String,  nullable=False, unique=True, index=True)
    title:               Mapped[str]        = mapped_column(String,  nullable=False)
    client_name:         Mapped[str | None] = mapped_column(String,  nullable=True)
    department_id:       Mapped[str | None] = mapped_column(String,  nullable=True)
    employment_type:     Mapped[str | None] = mapped_column(String,  nullable=True)
    work_mode:           Mapped[str | None] = mapped_column(String,  nullable=True)
    location:            Mapped[str | None] = mapped_column(String,  nullable=True)
    min_experience:      Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_experience:      Mapped[int | None] = mapped_column(Integer, nullable=True)
    openings:            Mapped[int]        = mapped_column(Integer, nullable=False, default=1)
    priority:            Mapped[str | None] = mapped_column(String,  nullable=True)
    required_skills:     Mapped[str | None] = mapped_column(Text,    nullable=True)
    job_description:     Mapped[str | None] = mapped_column(Text,    nullable=True)
    qualification:       Mapped[str | None] = mapped_column(String,  nullable=True)
    budget_range:        Mapped[str | None] = mapped_column(String,  nullable=True)
    target_joining:      Mapped[str | None] = mapped_column(String,  nullable=True)
    status:              Mapped[str]        = mapped_column(String,  nullable=False, default="Active")
    created_by:          Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_recruiter:  Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_by:         Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_at:         Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at:          Mapped[datetime]   = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at:          Mapped[datetime]   = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    pipeline_entries = relationship("CandidatePipeline", back_populates="requirement", cascade="all, delete-orphan")
    skills_detail    = relationship("RequirementSkill",  back_populates="requirement", cascade="all, delete-orphan")


class RecruitmentCandidate(Base):
    __tablename__ = "recruitment_candidates"

    id:                     Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id:           Mapped[str]          = mapped_column(String,  nullable=False, unique=True, index=True)
    first_name:             Mapped[str]          = mapped_column(String,  nullable=False)
    last_name:              Mapped[str | None]   = mapped_column(String,  nullable=True)
    email:                  Mapped[str]          = mapped_column(String,  nullable=False, unique=True)
    mobile:                 Mapped[int | None]   = mapped_column(Integer, nullable=True)
    experience_years:       Mapped[float | None] = mapped_column(Float,   nullable=True)
    current_job_title:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    current_employer:       Mapped[str | None]   = mapped_column(String,  nullable=True)
    current_ctc:            Mapped[int | None]   = mapped_column(Integer, nullable=True)
    expected_ctc:           Mapped[int | None]   = mapped_column(Integer, nullable=True)
    notice_period:          Mapped[str | None]   = mapped_column(String,  nullable=True)
    assign_to_recruitment:  Mapped[str | None]   = mapped_column(String,  nullable=True)
    source:                 Mapped[str | None]   = mapped_column(String,  nullable=True)
    skills:                 Mapped[str | None]   = mapped_column(Text,    nullable=True)
    curr_location:          Mapped[str | None]   = mapped_column(String,  nullable=True)
    resume_url:             Mapped[str | None]   = mapped_column(String,  nullable=True)
    cover_letter_url:       Mapped[str | None]   = mapped_column(String,  nullable=True)
    id_proof:               Mapped[str | None]   = mapped_column(String,  nullable=True)
    others:                 Mapped[str | None]   = mapped_column(String,  nullable=True)
    recruiter_notes:        Mapped[str | None]   = mapped_column(Text,    nullable=True)
    added_by:               Mapped[int | None]   = mapped_column(Integer, nullable=True)
    onboarded_at:           Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    onboarded_by:           Mapped[int | None]   = mapped_column(Integer, nullable=True)
    created_at:             Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at:             Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    requirement = relationship(
        "JobRequirement",
        primaryjoin="foreign(RecruitmentCandidate.assign_to_recruitment) == JobRequirement.req_id",
        uselist=False,
        viewonly=True,
    )
    pipeline_entries = relationship(
        "CandidatePipeline",
        primaryjoin="RecruitmentCandidate.candidate_id == foreign(CandidatePipeline.candidate_id)",
        viewonly=True,
    )


class CandidatePipeline(Base):
    __tablename__ = "candidate_pipeline"

    id:                  Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id:        Mapped[str]          = mapped_column(String,  nullable=False)
    requirement_id:      Mapped[int]          = mapped_column(ForeignKey("job_requirements.id"), nullable=False)
    current_stage:       Mapped[str]          = mapped_column(String,  nullable=False)
    pipeline_status:     Mapped[str]          = mapped_column(String,  nullable=False, default="active")
    mgr_approval_status: Mapped[str]          = mapped_column(String,  nullable=False, default="pending")
    mgr_approval_by:     Mapped[str | None]   = mapped_column(String,  nullable=True)
    mgr_approval_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manager_remark:      Mapped[str | None]   = mapped_column(Text,    nullable=True)
    rejection_reason:    Mapped[str | None]   = mapped_column(Text,    nullable=True)
    shortlisted_by:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    shortlisted_at:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    selected_at:         Mapped[str | None]   = mapped_column(String,  nullable=True)
    onboarding_date:     Mapped[str | None]   = mapped_column(String,  nullable=True)
    offer_status:        Mapped[str | None]   = mapped_column(String,  nullable=True)
    joining_date:        Mapped[str | None]   = mapped_column(String,  nullable=True)
    created_at:          Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at:          Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    requirement      = relationship("JobRequirement", back_populates="pipeline_entries")
    interview_rounds = relationship("InterviewRound", back_populates="pipeline", cascade="all, delete-orphan")
    candidate        = relationship(
        "RecruitmentCandidate",
        primaryjoin="foreign(CandidatePipeline.candidate_id) == RecruitmentCandidate.candidate_id",
        uselist=False,
        viewonly=True,
    )


class InterviewRound(Base):
    __tablename__ = "interview_rounds"

    id:               Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id:      Mapped[int]          = mapped_column(ForeignKey("candidate_pipeline.id"), nullable=False)
    round_name:       Mapped[str]          = mapped_column(String,  nullable=False)
    round_type:       Mapped[str | None]   = mapped_column(String,  nullable=True)
    round_order:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    interviewer_id:   Mapped[str | None]   = mapped_column(String,  nullable=True)
    status:           Mapped[str]          = mapped_column(String,  nullable=False, default="awaiting_slot")
    interview_date:   Mapped[str | None]   = mapped_column(String,  nullable=True)
    interview_time:   Mapped[str | None]   = mapped_column(String,  nullable=True)
    interview_format: Mapped[str | None]   = mapped_column(String,  nullable=True)
    meeting_link:     Mapped[str | None]   = mapped_column(String,  nullable=True)
    is_additional:    Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    added_by:         Mapped[str | None]   = mapped_column(String,  nullable=True)
    added_reason:     Mapped[str | None]   = mapped_column(Text,    nullable=True)
    selection_token:  Mapped[str | None]   = mapped_column(String,  nullable=True, unique=True)
    token_used:       Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    email_sent_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at:       Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at:       Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    pipeline = relationship("CandidatePipeline", back_populates="interview_rounds")
    slots    = relationship("InterviewSlot", back_populates="round", cascade="all, delete-orphan")
    feedback = relationship("InterviewFeedback", back_populates="round", uselist=False, cascade="all, delete-orphan")


class InterviewSlot(Base):
    __tablename__ = "interview_slots"

    id:             Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id:       Mapped[int]          = mapped_column(Integer, ForeignKey("interview_rounds.id"), nullable=False)
    slot_date:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    slot_time:      Mapped[str | None]   = mapped_column(String,  nullable=True)
    is_selected:    Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    selected_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    candidate_id:   Mapped[str | None]   = mapped_column(String,  nullable=True)
    interviewer_id: Mapped[str | None]   = mapped_column(String,  nullable=True)
    requirement_id: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, server_default=func.now(), nullable=False)

    round = relationship("InterviewRound", back_populates="slots")


class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"

    id:                     Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id:               Mapped[int]        = mapped_column(Integer, ForeignKey("interview_rounds.id"), nullable=False)
    interviewer_id:         Mapped[str | None] = mapped_column(String,  nullable=True)
    technical_rating:       Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_rating:   Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_solving_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation:         Mapped[str | None] = mapped_column(String,  nullable=True)
    notes:                  Mapped[str | None] = mapped_column(Text,    nullable=True)
    submitted_at:           Mapped[datetime]   = mapped_column(DateTime, server_default=func.now(), nullable=False)

    round = relationship("InterviewRound", back_populates="feedback", uselist=False)


class RequirementSkill(Base):
    __tablename__ = "requirement_skills"

    id:             Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int]        = mapped_column(Integer, ForeignKey("job_requirements.id"), nullable=False)
    skill_name:     Mapped[str]        = mapped_column(String,  nullable=False)
    is_primary:     Mapped[int]        = mapped_column(Integer, nullable=False, default=1)
    status:         Mapped[str]        = mapped_column(String,  nullable=False, default="approved")
    requested_by:   Mapped[str | None] = mapped_column(String,  nullable=True)
    requested_at:   Mapped[datetime]   = mapped_column(DateTime, server_default=func.now(), nullable=False)
    approved_by:    Mapped[str | None] = mapped_column(String,  nullable=True)
    approved_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    requirement = relationship("JobRequirement", back_populates="skills_detail")
