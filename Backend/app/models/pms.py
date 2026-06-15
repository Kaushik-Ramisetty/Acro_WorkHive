"""Performance Management (PMS) — Phase 1 models.

Goal-setting workflow: HR defines templates → assigns to employees →
manager + employee discuss → manager approves → HR reviews → HR locks.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# Canonical status strings for a GoalAssignment.
PMS_STATUS_DRAFT              = "draft"
PMS_STATUS_GOALS_SENT         = "goals_sent"
PMS_STATUS_UNDER_DISCUSSION   = "under_discussion"
PMS_STATUS_EMPLOYEE_CONFIRMED = "employee_confirmed"
PMS_STATUS_MANAGER_APPROVED   = "manager_approved"
PMS_STATUS_HR_REVIEWED        = "hr_reviewed"
PMS_STATUS_GOALS_LOCKED       = "goals_locked"

PMS_STATUSES = (
    PMS_STATUS_DRAFT, PMS_STATUS_GOALS_SENT, PMS_STATUS_UNDER_DISCUSSION,
    PMS_STATUS_EMPLOYEE_CONFIRMED, PMS_STATUS_MANAGER_APPROVED,
    PMS_STATUS_HR_REVIEWED, PMS_STATUS_GOALS_LOCKED,
)

# Lock source discriminator — stored in lock_type column.
LOCK_TYPE_MANUAL = "manual"   # HR initiated via UI
LOCK_TYPE_AUTO   = "auto"     # System initiated after phase deadline


class GoalTemplate(Base):
    __tablename__ = "pms_goal_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)  # e.g. "FY2026-Q1", "2026"

    # Default targeting (optional — used as suggestion at assignment time).
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    designation_id: Mapped[str | None] = mapped_column(ForeignKey("designations.id"), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    # ── Excel import / export tracking ────────────────────────────
    imported_from_excel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    template_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    imported_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_exported_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    last_exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Legacy DB columns ───────────────────────────────────────────
    # The original pms_goal_templates table was created by a prior
    # implementation with these NOT NULL columns.  We keep them mapped so
    # SQLAlchemy includes them in INSERT statements (otherwise the DB rejects
    # the insert due to the NOT NULL constraint).  On a fresh DB these are
    # created as nullable by Base.metadata.create_all(); on an existing DB the
    # Python default="" / created_by satisfies the NOT NULL constraint at
    # runtime.  These columns are not exposed through the API.
    code: Mapped[str] = mapped_column(String(20), default="", nullable=True)
    financial_year: Mapped[str] = mapped_column(String(10), default="", nullable=True)
    cycle: Mapped[str] = mapped_column(String(20), default="", nullable=True)
    # created_by_id mirrors created_by; populated by the service layer.
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    kras: Mapped[list["TemplateKRA"]] = relationship(back_populates="template", cascade="all, delete-orphan")
    competencies: Mapped[list["TemplateCompetency"]] = relationship(back_populates="template", cascade="all, delete-orphan")


class TemplateKRA(Base):
    __tablename__ = "pms_template_kras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("pms_goal_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    template: Mapped["GoalTemplate"] = relationship(back_populates="kras")
    kpis: Mapped[list["TemplateKPI"]] = relationship(back_populates="kra", cascade="all, delete-orphan")


class TemplateKPI(Base):
    __tablename__ = "pms_template_kpis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kra_id: Mapped[int] = mapped_column(ForeignKey("pms_template_kras.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(60), nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    kra: Mapped["TemplateKRA"] = relationship(back_populates="kpis")


class TemplateCompetency(Base):
    __tablename__ = "pms_template_competencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("pms_goal_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    template: Mapped["GoalTemplate"] = relationship(back_populates="competencies")


class GoalAssignment(Base):
    """A template instance assigned to a single employee for a review period."""
    __tablename__ = "pms_goal_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("pms_goal_templates.id"), nullable=True, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)

    status: Mapped[str] = mapped_column(String(40), nullable=False, default=PMS_STATUS_GOALS_SENT, index=True)

    # CHANGE 3: goal-setting phase deadline
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Stage-stamps
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    discussed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    employee_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hr_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hr_reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    # 'manual' = HR-initiated lock; 'auto' = system auto-lock after deadline.
    lock_type: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Stage-level comments (free text, last-write-wins per stage).
    employee_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    hr_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    kras: Mapped[list["AssignedKRA"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")
    competencies: Mapped[list["AssignedCompetency"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")
    comments: Mapped[list["GoalComment"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    manager: Mapped["Employee | None"] = relationship(foreign_keys=[manager_id])  # type: ignore[name-defined]


class AssignedKRA(Base):
    __tablename__ = "pms_assigned_kras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("pms_goal_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # CHANGE 1: marks KRAs that originated from a template (read-only for employee/manager)
    from_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assignment: Mapped["GoalAssignment"] = relationship(back_populates="kras")
    kpis: Mapped[list["AssignedKPI"]] = relationship(back_populates="kra", cascade="all, delete-orphan")


class AssignedKPI(Base):
    __tablename__ = "pms_assigned_kpis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kra_id: Mapped[int] = mapped_column(ForeignKey("pms_assigned_kras.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(60), nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # CHANGE 1: marks KPIs that originated from a template (read-only for employee/manager)
    from_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    kra: Mapped["AssignedKRA"] = relationship(back_populates="kpis")


class AssignedCompetency(Base):
    __tablename__ = "pms_assigned_competencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("pms_goal_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weightage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # CHANGE 1: template competencies are read-only; employee/manager can add their own
    from_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assignment: Mapped["GoalAssignment"] = relationship(back_populates="competencies")


class GoalComment(Base):
    """Thread of stage comments on an assignment (HR / manager / employee)."""
    __tablename__ = "pms_goal_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("pms_goal_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'hr' | 'manager' | 'employee'
    body: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)  # status snapshot at time of comment
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    assignment: Mapped["GoalAssignment"] = relationship(back_populates="comments")
    author: Mapped["Employee"] = relationship(foreign_keys=[author_id])  # type: ignore[name-defined]


# ── Phase 2 — Mid-Cycle Review ─────────────────────────────────────────────────

MCR_STATUS_DRAFT          = "draft"
MCR_STATUS_IN_PROGRESS    = "in_progress"
MCR_STATUS_SUBMITTED      = "submitted"
MCR_STATUS_MGR_REVIEWED   = "manager_reviewed"
MCR_STATUS_MGR_APPROVED   = "manager_approved"
MCR_STATUS_HR_REVIEWED    = "hr_reviewed"
MCR_STATUS_LOCKED         = "mid_cycle_locked"

MCR_STATUSES = (
    MCR_STATUS_DRAFT, MCR_STATUS_IN_PROGRESS, MCR_STATUS_SUBMITTED,
    MCR_STATUS_MGR_REVIEWED, MCR_STATUS_MGR_APPROVED,
    MCR_STATUS_HR_REVIEWED, MCR_STATUS_LOCKED,
)


class MidCycleReview(Base):
    """Mid-cycle progress review for a single GoalAssignment."""
    __tablename__ = "pms_mid_cycle_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("pms_goal_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cycle_period: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)  # e.g. "H1-2026"

    status: Mapped[str] = mapped_column(String(40), nullable=False, default=MCR_STATUS_DRAFT, index=True)

    # CHANGE 3: mid-cycle review deadline
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # HR flag: allow manager to modify goals during this review.
    allow_goal_modification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Stage-level comments (last-write-wins per stage).
    employee_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hr_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stage timestamps.
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    manager_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    manager_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    hr_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 'manual' = HR-initiated lock; 'auto' = system auto-lock after deadline.
    lock_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Stage actors.
    manager_reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    manager_approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hr_reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    locked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    # Relationships.
    assignment: Mapped["GoalAssignment"] = relationship(foreign_keys=[assignment_id])
    kpi_progress: Mapped[list["KPIProgress"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    evidences: Mapped[list["ReviewEvidence"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class KPIProgress(Base):
    """Employee progress on a single KPI within a MidCycleReview."""
    __tablename__ = "pms_kpi_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("pms_mid_cycle_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_kpi_id: Mapped[int] = mapped_column(
        ForeignKey("pms_assigned_kpis.id", ondelete="CASCADE"), nullable=False, index=True
    )

    current_value: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    employee_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    review: Mapped["MidCycleReview"] = relationship(back_populates="kpi_progress")
    assigned_kpi: Mapped["AssignedKPI"] = relationship()


class ReviewEvidence(Base):
    """Evidence (text/URL) attached to a MidCycleReview, optionally linked to a KPI."""
    __tablename__ = "pms_review_evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("pms_mid_cycle_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_kpi_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pms_assigned_kpis.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    review: Mapped["MidCycleReview"] = relationship(back_populates="evidences")
    uploader: Mapped["Employee"] = relationship(foreign_keys=[uploaded_by])  # type: ignore[name-defined]


# ── Phase 3 — End Cycle Assessment ────────────────────────────────────────────

ECA_STATUS_DRAFT           = "draft"
ECA_STATUS_SELF_ASSESSED   = "self_assessed"
ECA_STATUS_MGR_ASSESSED    = "manager_assessed"
ECA_STATUS_SUBMITTED_TO_HR = "submitted_to_hr"
ECA_STATUS_HR_RECEIVED     = "hr_received"
ECA_STATUS_LOCKED          = "assessment_locked"

ECA_STATUSES = (
    ECA_STATUS_DRAFT, ECA_STATUS_SELF_ASSESSED, ECA_STATUS_MGR_ASSESSED,
    ECA_STATUS_SUBMITTED_TO_HR, ECA_STATUS_HR_RECEIVED, ECA_STATUS_LOCKED,
)


class EndCycleAssessment(Base):
    """End-of-cycle performance assessment for a single GoalAssignment."""
    __tablename__ = "pms_end_cycle_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("pms_goal_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cycle_period: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    status: Mapped[str] = mapped_column(String(40), nullable=False, default=ECA_STATUS_DRAFT, index=True)

    # CHANGE 3: end-cycle assessment deadline
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Employee self-assessment (overall).
    self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # 1.0–5.0
    self_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    self_assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Manager assessment (overall).
    manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manager_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    manager_assessed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)

    # HR.
    hr_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hr_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    hr_received_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    # 'manual' = HR-initiated lock; 'auto' = system auto-lock after deadline.
    lock_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    assignment: Mapped["GoalAssignment"] = relationship(foreign_keys=[assignment_id])
    kra_ratings: Mapped[list["GoalRating"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    competency_ratings: Mapped[list["CompetencyRating"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class GoalRating(Base):
    """Employee self + manager rating per KRA within an EndCycleAssessment."""
    __tablename__ = "pms_goal_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("pms_end_cycle_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_kra_id: Mapped[int] = mapped_column(
        ForeignKey("pms_assigned_kras.id", ondelete="CASCADE"), nullable=False
    )

    self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    self_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manager_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    assessment: Mapped["EndCycleAssessment"] = relationship(back_populates="kra_ratings")
    assigned_kra: Mapped["AssignedKRA"] = relationship()


class CompetencyRating(Base):
    """Employee self + manager rating per competency within an EndCycleAssessment."""
    __tablename__ = "pms_competency_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("pms_end_cycle_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_competency_id: Mapped[int] = mapped_column(
        ForeignKey("pms_assigned_competencies.id", ondelete="CASCADE"), nullable=False
    )

    self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    self_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manager_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    assessment: Mapped["EndCycleAssessment"] = relationship(back_populates="competency_ratings")
    assigned_competency: Mapped["AssignedCompetency"] = relationship()


# ── Phase 4 — HR Normalization ─────────────────────────────────────────────────

NORM_STATUS_DRAFT          = "draft"
NORM_STATUS_NORMALIZED     = "normalized"
NORM_STATUS_FROZEN         = "frozen"
NORM_STATUS_HIKE_GENERATED = "hike_generated"
NORM_STATUS_HIKE_APPROVED  = "hike_approved"

NORM_STATUSES = (
    NORM_STATUS_DRAFT, NORM_STATUS_NORMALIZED, NORM_STATUS_FROZEN,
    NORM_STATUS_HIKE_GENERATED, NORM_STATUS_HIKE_APPROVED,
)


class NormalizationSession(Base):
    """A batch normalization exercise covering a set of end-cycle assessments."""
    __tablename__ = "pms_normalization_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=NORM_STATUS_DRAFT, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CHANGE 3: normalization phase deadline
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    normalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    normalized_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    frozen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    frozen_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hike_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    hike_generated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hike_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    hike_approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    records: Mapped[list["NormalizationRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class NormalizationRecord(Base):
    """Per-employee record within a NormalizationSession."""
    __tablename__ = "pms_normalization_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("pms_normalization_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("pms_end_cycle_assessments.id"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    raw_manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    normalized_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # computed
    override_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # HR override
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # override ?? normalized

    # CHANGE 4: audit trail for override — who changed it and when
    override_modified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    override_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    hike_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hike_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CHANGE 5: track who manually entered the hike %
    hike_entered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hike_entered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    compensation_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    session: Mapped["NormalizationSession"] = relationship(back_populates="records")
    assessment: Mapped["EndCycleAssessment"] = relationship()
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


# ── Phase 5 — Compensation & Communication ─────────────────────────────────────

class CompensationRevision(Base):
    """Salary revision generated from a NormalizationRecord (one per employee per session)."""
    __tablename__ = "pms_compensation_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalization_record_id: Mapped[int] = mapped_column(
        ForeignKey("pms_normalization_records.id"), nullable=False, unique=True, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    old_ctc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_ctc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hike_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Letter lifecycle.
    letter_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    letter_generated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    employee_acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    normalization_record: Mapped["NormalizationRecord"] = relationship()
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]


class PMSCycle(Base):
    """Archive record for a completed PMS cycle."""
    __tablename__ = "pms_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    normalization_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pms_normalization_sessions.id"), nullable=True
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archived_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    normalization_session: Mapped[Optional["NormalizationSession"]] = relationship()
