"""Pydantic schemas for the PMS Phase-1 goal-setting flow."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Templates (HR-side authoring) ──────────────────────────────────


class KPIIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    weightage: float = 0.0


class KRAIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    weightage: float = 0.0
    sort_order: int = 0
    kpis: List[KPIIn] = []


class CompetencyIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    weightage: float = 0.0


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    period: Optional[str] = None
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool = True
    kras: List[KRAIn] = []
    competencies: List[CompetencyIn] = []


class KPIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    target: Optional[str] = None
    measurement_unit: Optional[str] = None
    weightage: float


class KRAOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    weightage: float
    sort_order: int
    kpis: List[KPIOut] = []


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    weightage: float


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    period: Optional[str] = None
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool
    created_by: Optional[int] = None
    created_at: datetime
    kras: List[KRAOut] = []
    competencies: List[CompetencyOut] = []


# ── Assignment (per-employee instance) ─────────────────────────────


class AssignTargetIn(BaseModel):
    """HR assigns a template to a cohort. Any combination of selectors."""
    template_id: int
    period: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3: goal-setting phase deadline
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    role_id: Optional[int] = None
    employee_ids: Optional[List[int]] = None


class AssignedKPIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    target: Optional[str] = None
    measurement_unit: Optional[str] = None
    weightage: float
    from_template: bool = False  # CHANGE 1: tells FE whether this KPI is template-locked


class AssignedKRAOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    weightage: float
    sort_order: int
    from_template: bool = False  # CHANGE 1: tells FE whether this KRA is template-locked
    kpis: List[AssignedKPIOut] = []


class AssignedCompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    weightage: float
    from_template: bool = False  # CHANGE 1: template competencies are read-only


class GoalCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: int
    author_role: str
    body: str
    stage: Optional[str] = None
    created_at: datetime


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: Optional[int] = None
    employee_id: int
    employee_name: Optional[str] = None
    manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    period: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3
    status: str
    sent_at: Optional[datetime] = None
    discussed_at: Optional[datetime] = None
    employee_confirmed_at: Optional[datetime] = None
    manager_approved_at: Optional[datetime] = None
    hr_reviewed_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    lock_type: Optional[str] = None   # 'manual' | 'auto'
    employee_comments: Optional[str] = None
    manager_comments: Optional[str] = None
    hr_comments: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    kras: List[AssignedKRAOut] = []
    competencies: List[AssignedCompetencyOut] = []
    comments: List[GoalCommentOut] = []


# ── Edit payloads ──────────────────────────────────────────────────


class KRAEdit(BaseModel):
    """Used by manager/employee to edit an assignment's KRA tree.
    `id` present → update; `id` null → create. KPIs follow the same rule."""
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    weightage: float = 0.0
    sort_order: int = 0
    kpis: List["KPIEdit"] = []


class KPIEdit(BaseModel):
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    weightage: float = 0.0


class CompetencyEdit(BaseModel):
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    weightage: float = 0.0


KRAEdit.model_rebuild()


class AssignmentEdit(BaseModel):
    kras: Optional[List[KRAEdit]] = None
    competencies: Optional[List[CompetencyEdit]] = None
    comment: Optional[str] = None


class CommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class StageActionIn(BaseModel):
    comment: Optional[str] = None


# ── Excel import preview schemas ───────────────────────────────────


class ImportPreviewDesignation(BaseModel):
    designation_name: str
    designation_id: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    period: Optional[str] = None
    department_id: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool = True
    kras: List[KRAIn]
    competencies: List[CompetencyIn] = []


class ImportPreviewOut(BaseModel):
    period: Optional[str] = None
    source_filename: str
    designations: List[ImportPreviewDesignation]
    warnings: List[str] = []


class ImportCommitIn(BaseModel):
    """Client sends back ImportPreviewOut (possibly edited) to persist."""
    period: Optional[str] = None
    source_filename: str
    designations: List[ImportPreviewDesignation]
    warnings: List[str] = []


# ── Bulk action schemas (CHANGE 8) ────────────────────────────────────────────


class BulkIdsIn(BaseModel):
    ids: List[int]
    comment: Optional[str] = None


class BulkMidCycleCreateIn(BaseModel):
    assignment_ids: List[int]
    cycle_period: Optional[str] = None
    deadline: Optional[datetime] = None
    allow_goal_modification: bool = False


class BulkECACreateIn(BaseModel):
    assignment_ids: List[int]
    cycle_period: Optional[str] = None
    deadline: Optional[datetime] = None


class BulkResultItem(BaseModel):
    id: int
    name: Optional[str] = None
    success: bool
    reason: Optional[str] = None


class BulkActionOut(BaseModel):
    total: int
    success_count: int
    failure_count: int
    results: List[BulkResultItem]


# ── PMS Phase Settings schemas (CHANGE 9) ────────────────────────────────────


class PMSPhaseSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phase_key: str
    label: str
    default_days: int
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None


class PMSPhaseSettingUpdate(BaseModel):
    default_days: int = Field(..., ge=1, le=365)


class DeadlinePreviewOut(BaseModel):
    phase_key: str
    default_days: int
    computed_deadline: datetime


# ── Phase 2: Mid-Cycle Review schemas ─────────────────────────────────────────


class MidCycleCreateIn(BaseModel):
    """HR creates a mid-cycle review for an assignment."""
    assignment_id: int
    cycle_period: Optional[str] = None          # e.g. "H1-2026"
    allow_goal_modification: bool = False
    deadline: Optional[datetime] = None          # CHANGE 3: mid-cycle deadline


class KPIProgressIn(BaseModel):
    """Employee updates progress on one KPI."""
    assigned_kpi_id: int
    current_value: Optional[str] = None
    progress_percent: float = Field(0.0, ge=0.0, le=100.0)
    employee_notes: Optional[str] = None


class ProgressSubmitIn(BaseModel):
    """Employee submits progress update (can be partial save or final submit)."""
    kpi_progress: List[KPIProgressIn] = []
    employee_comments: Optional[str] = None


class ManagerReviewIn(BaseModel):
    """Manager reviews and optionally annotates individual KPIs."""
    manager_comments: Optional[str] = None
    kpi_notes: Optional[List[dict]] = None    # [{assigned_kpi_id, manager_notes}, ...]


class ManagerKPIEditIn(BaseModel):
    """Per-KPI payload inside ManagerNotesIn.

    The manager may annotate any KPI with notes and may also override the
    employee-submitted progress values (current_value, progress_percent).
    Any field left as None is left unchanged on the existing KPIProgress row.
    """
    assigned_kpi_id: int
    manager_notes: Optional[str] = None
    # Progress value overrides — manager can correct employee-submitted values.
    current_value: Optional[str] = None       # None = do not change
    progress_percent: Optional[float] = None  # None = do not change


class ManagerNotesIn(BaseModel):
    """Manager saves per-KPI notes/ratings and overall comment WITHOUT advancing the state machine.

    Allowed when review status is 'submitted' (manager has not yet reviewed) or
    'manager_reviewed' (manager has reviewed but not yet approved).
    After 'manager_approved' the review is read-only for the manager.
    """
    manager_comments: Optional[str] = None
    kpi_notes: Optional[List[ManagerKPIEditIn]] = None


class MidCycleActionIn(BaseModel):
    """Simple action (approve / lock / review) with optional comment."""
    comment: Optional[str] = None


class EvidenceIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    evidence_url: Optional[str] = None
    assigned_kpi_id: Optional[int] = None


class KPIProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assigned_kpi_id: int
    current_value: Optional[str] = None
    progress_percent: float
    employee_notes: Optional[str] = None
    manager_notes: Optional[str] = None
    updated_at: Optional[datetime] = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    review_id: int
    assigned_kpi_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    evidence_url: Optional[str] = None
    uploaded_by: int
    created_at: datetime


class MidCycleReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assignment_id: int
    cycle_period: Optional[str] = None
    status: str
    deadline: Optional[datetime] = None  # CHANGE 3
    allow_goal_modification: bool
    employee_comments: Optional[str] = None
    manager_comments: Optional[str] = None
    hr_comments: Optional[str] = None
    submitted_at: Optional[datetime] = None
    manager_reviewed_at: Optional[datetime] = None
    manager_approved_at: Optional[datetime] = None
    hr_reviewed_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    lock_type: Optional[str] = None   # 'manual' | 'auto'
    created_at: datetime
    updated_at: Optional[datetime] = None
    kpi_progress: List[KPIProgressOut] = []
    evidences: List[EvidenceOut] = []
    # Hydrated fields (set by service layer).
    employee_name: Optional[str] = None
    manager_name: Optional[str] = None
    period: Optional[str] = None


# ── Phase 3: End Cycle Assessment schemas ─────────────────────────────────────


class ECACreateIn(BaseModel):
    """HR creates an end-cycle assessment for a locked assignment."""
    assignment_id: int
    cycle_period: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3: end-cycle deadline


class KRARatingIn(BaseModel):
    assigned_kra_id: int
    self_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    self_notes: Optional[str] = None


class CompetencyRatingIn(BaseModel):
    assigned_competency_id: int
    self_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    self_notes: Optional[str] = None


class SelfAssessIn(BaseModel):
    """Employee submits their self-assessment."""
    self_rating: float = Field(..., ge=1.0, le=5.0)
    self_comments: Optional[str] = None
    kra_ratings: List[KRARatingIn] = []
    competency_ratings: List[CompetencyRatingIn] = []


class KRARatingManagerIn(BaseModel):
    assigned_kra_id: int
    manager_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    manager_notes: Optional[str] = None


class CompetencyRatingManagerIn(BaseModel):
    assigned_competency_id: int
    manager_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    manager_notes: Optional[str] = None


class ManagerAssessIn(BaseModel):
    """Manager submits their assessment of an employee."""
    manager_rating: float = Field(..., ge=1.0, le=5.0)
    manager_comments: Optional[str] = None
    kra_ratings: List[KRARatingManagerIn] = []
    competency_ratings: List[CompetencyRatingManagerIn] = []


class ECAActionIn(BaseModel):
    """Simple action (submit to HR / receive / lock) with optional notes."""
    notes: Optional[str] = None


class HRNotesIn(BaseModel):
    """Standalone HR notes update — does not advance the state machine."""
    notes: str = Field("", max_length=5000)


class KRARatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assigned_kra_id: int
    self_rating: Optional[float] = None
    self_notes: Optional[str] = None
    manager_rating: Optional[float] = None
    manager_notes: Optional[str] = None


class CompetencyRatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assigned_competency_id: int
    self_rating: Optional[float] = None
    self_notes: Optional[str] = None
    manager_rating: Optional[float] = None
    manager_notes: Optional[str] = None


class MidCycleComparisonRow(BaseModel):
    """One row in the Mid-Cycle vs End-Cycle comparison panel.

    row_type distinguishes KRA summary rows, individual KPI rows, and
    competency rows.

    Achievement semantics
    ---------------------
    KPIProgress.progress_percent stores the ACHIEVED portion of the KPI's
    allocated weight (not a 0–100 completion %).  Correct achievement %:
        KPI: (progress_percent / kpi.weightage) × 100
        KRA: Σ(KPI progress_percent) / Σ(KPI weightage) × 100
    """
    row_type: str = "kra"                    # "kra" | "kpi" | "competency"
    kra_id: Optional[int] = None             # set for kra/kpi rows
    kpi_id: Optional[int] = None             # set for kpi rows only
    kra_title: str                           # KRA/parent-KRA/competency display name
    kpi_title: Optional[str] = None          # KPI title (kpi rows only)
    weightage: float                         # Assigned Weight (kra/kpi/comp)
    achieved_weight: Optional[float] = None  # Σ KPI progress (KRA) or individual progress (KPI)
    achievement_pct: Optional[float] = None  # achieved_weight / Σ(KPI weights) × 100
    derived_mid_rating: Optional[int] = None
    end_self_rating: Optional[float] = None
    end_manager_rating: Optional[float] = None
    variance: Optional[float] = None


class EndCycleAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assignment_id: int
    cycle_period: Optional[str] = None
    status: str
    deadline: Optional[datetime] = None  # CHANGE 3
    self_rating: Optional[float] = None
    self_comments: Optional[str] = None
    self_assessed_at: Optional[datetime] = None
    manager_rating: Optional[float] = None
    manager_comments: Optional[str] = None
    manager_assessed_at: Optional[datetime] = None
    hr_notes: Optional[str] = None
    hr_received_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    lock_type: Optional[str] = None   # 'manual' | 'auto'
    created_at: datetime
    updated_at: Optional[datetime] = None
    kra_ratings: List[KRARatingOut] = []
    competency_ratings: List[CompetencyRatingOut] = []
    # Hydrated.
    employee_name: Optional[str] = None
    employee_id: Optional[int] = None
    manager_name: Optional[str] = None
    period: Optional[str] = None
    # Mid vs End comparison rows (new — empty list when no mid-cycle data).
    mid_cycle_comparison: List[MidCycleComparisonRow] = []


# ── Phase 4: Normalization schemas ────────────────────────────────────────────


class NormSessionCreateIn(BaseModel):
    period: str = Field(..., min_length=1, max_length=40)
    notes: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3: normalization phase deadline


class NormSessionUpdateIn(BaseModel):
    period: Optional[str] = Field(None, min_length=1, max_length=40)
    notes: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3


class EligibleECAOut(BaseModel):
    """Locked end-cycle assessment available for inclusion in a normalization session."""
    model_config = ConfigDict(from_attributes=True)
    eca_id: int
    assignment_id: int
    employee_id: int
    employee_name: str
    manager_name: str
    period: str                         # assignment period (canonical label)
    cycle_period: Optional[str] = None  # ECA cycle_period (may differ)
    self_rating: Optional[float] = None
    manager_rating: Optional[float] = None
    locked_at: Optional[datetime] = None
    in_session_id: Optional[int] = None  # non-None → already in that session


class NormRecordUpdateIn(BaseModel):
    """HR updates a single normalization record (rating override / hike).

    All fields are optional:
    - override_rating: HR may override the auto-computed normalized rating. No
      longer mandatory to provide a reason when the value differs.
    - override_reason: Optional audit note explaining the override.
    - hike_percent: Manually entered by HR. Editable until the hike is approved
      (FROZEN and HIKE_GENERATED sessions both allow edits).
    """
    override_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    override_reason: Optional[str] = None
    hike_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    hike_notes: Optional[str] = None
    compensation_comments: Optional[str] = None


class NormActionIn(BaseModel):
    notes: Optional[str] = None


class NormRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    assessment_id: int
    employee_id: int
    raw_manager_rating: Optional[float] = None
    raw_self_rating: Optional[float] = None
    normalized_rating: Optional[float] = None
    override_rating: Optional[float] = None
    override_reason: Optional[str] = None
    final_rating: Optional[float] = None
    # CHANGE 4: override audit fields
    override_modified_by: Optional[int] = None
    override_modified_at: Optional[datetime] = None
    hike_percent: Optional[float] = None
    hike_notes: Optional[str] = None
    # CHANGE 5: manual hike audit fields
    hike_entered_by: Optional[int] = None
    hike_entered_at: Optional[datetime] = None
    compensation_comments: Optional[str] = None
    # Hydrated.
    employee_name: Optional[str] = None


class NormSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    period: str
    status: str
    notes: Optional[str] = None
    deadline: Optional[datetime] = None  # CHANGE 3
    normalized_at: Optional[datetime] = None
    frozen_at: Optional[datetime] = None
    hike_generated_at: Optional[datetime] = None
    hike_approved_at: Optional[datetime] = None
    created_at: datetime
    records: List[NormRecordOut] = []


# ── Phase 5: Compensation schemas ─────────────────────────────────────────────


class CompRevisionGenerateIn(BaseModel):
    """HR generates compensation revisions for a normalization session."""
    effective_from: str = Field(..., description="ISO date string e.g. 2026-07-01")
    notes: Optional[str] = None


class CompRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    normalization_record_id: int
    employee_id: int
    old_ctc: Optional[float] = None
    new_ctc: Optional[float] = None
    hike_percent: Optional[float] = None
    effective_from: Optional[datetime] = None
    letter_generated_at: Optional[datetime] = None
    employee_acknowledged_at: Optional[datetime] = None
    created_at: datetime
    # Hydrated.
    employee_name: Optional[str] = None


class PMSCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    period: str
    normalization_session_id: Optional[int] = None
    archived_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
