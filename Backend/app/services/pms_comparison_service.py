"""PMS Mid-Cycle vs End-Cycle comparison helpers.

Pure utility — no state mutations, no commits.  Safe to call from any
assessment_view call without affecting existing PMS workflows.

All data is fetched via explicit db.query() calls — never via ORM lazy
relationships — so this is safe to call from list endpoints that process
many assessments in a single session.

Key semantic
------------
KPIProgress.progress_percent stores the ACHIEVED PORTION OF THE KPI'S
ALLOCATED WEIGHT, not a 0–100 completion percentage.

  Example: KPI weight = 9%.  Employee fully achieved → stores 9.
           Employee 50% achieved → stores 4.5.
  Display formula used by MidCycleReviewDrawer:
      displayPct = (rawProgress / kpi.weightage) * 100

Correct achievement formulas
----------------------------
    KPI achievement % = (progress_percent / kpi.weightage) × 100
    KRA achievement % = Σ(KPI progress_percent) / Σ(KPI weightage) × 100

The existing 1–5 rating bands (derive_mid_rating) are applied to these
correct achievement percentages — not to raw stored values.

Row types returned
------------------
  "kra"         — KRA summary row; achievement = Σ KPI progress / Σ KPI weight
  "kpi"         — Individual KPI sub-row; achievement = progress / kpi.weight
  "competency"  — Per-competency; no mid-cycle data (achievement fields = None)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import AssignedKRA, AssignedKPI, AssignedCompetency, MidCycleReview, KPIProgress
from app.models.pms import EndCycleAssessment, GoalRating, CompetencyRating


def derive_mid_rating(achievement_pct: Optional[float]) -> Optional[int]:
    """Map achievement % to the PMS 1–5 rating scale.

    Bands (same as end-cycle RATING_LABELS in pms.js):
      0–20%  → 1  Below Expectations
      21–40% → 2  Needs Improvement
      41–60% → 3  Meets Expectations
      61–80% → 4  Exceeds Expectations
      81–100%→ 5  Outstanding
    """
    if achievement_pct is None:
        return None
    p = float(achievement_pct)
    if p <= 20:
        return 1
    elif p <= 40:
        return 2
    elif p <= 60:
        return 3
    elif p <= 80:
        return 4
    else:
        return 5


def _find_mid_review(
    db: Session, assignment_id: int, cycle_period: Optional[str]
) -> Optional[MidCycleReview]:
    q = db.query(MidCycleReview).filter(
        MidCycleReview.assignment_id == assignment_id
    )
    if cycle_period:
        matched = (
            q.filter(MidCycleReview.cycle_period == cycle_period)
            .order_by(MidCycleReview.created_at.desc())
            .first()
        )
        if matched:
            return matched
    return q.order_by(MidCycleReview.created_at.desc()).first()


def build_comparison_rows(
    db: Session,
    assignment_id: int,
    eca: EndCycleAssessment,
) -> list[dict]:
    """Return comparison rows for the Mid vs End tab.

    Returned fields per row:
      row_type, kra_id, kpi_id, kra_title, kpi_title,
      weightage         — assigned weight (KRA / KPI / competency level)
      achieved_weight   — Σ KPI progress for KRA; individual KPI progress for KPI
      achievement_pct   — achieved_weight / Σ(KPI weights) × 100
      derived_mid_rating, end_self_rating, end_manager_rating, variance

    Mid-cycle columns are None for competency rows (competencies have no
    mid-cycle progress tracking) and also None when no mid-cycle review exists
    (end-cycle data is still shown in those cases).
    """
    # ── Mid-cycle data ────────────────────────────────────────────────────────
    mid_review = _find_mid_review(db, assignment_id, eca.cycle_period)

    # kpi_progress_map: assigned_kpi_id → achieved weight value (progress_percent)
    # Missing means no record yet; treat as 0 for KRA-level sum, None for KPI display.
    kpi_progress_map: dict[int, float] = {}
    if mid_review is not None:
        for p in (
            db.query(KPIProgress)
            .filter(KPIProgress.review_id == mid_review.id)
            .all()
        ):
            kpi_progress_map[p.assigned_kpi_id] = p.progress_percent

    # ── End-cycle KRA ratings (GoalRating) ───────────────────────────────────
    kra_rating_map: dict[int, GoalRating] = {
        r.assigned_kra_id: r
        for r in db.query(GoalRating)
        .filter(GoalRating.assessment_id == eca.id)
        .all()
    }

    # ── End-cycle competency ratings ─────────────────────────────────────────
    comp_rating_map: dict[int, CompetencyRating] = {
        r.assigned_competency_id: r
        for r in db.query(CompetencyRating)
        .filter(CompetencyRating.assessment_id == eca.id)
        .all()
    }

    # ── KRAs for this assignment ──────────────────────────────────────────────
    kras = (
        db.query(AssignedKRA)
        .filter(AssignedKRA.assignment_id == assignment_id)
        .order_by(AssignedKRA.sort_order)
        .all()
    )

    # ── Competencies for this assignment ─────────────────────────────────────
    comps = (
        db.query(AssignedCompetency)
        .filter(AssignedCompetency.assignment_id == assignment_id)
        .all()
    )

    rows: list[dict] = []

    for kra in kras:
        kpis = (
            db.query(AssignedKPI)
            .filter(AssignedKPI.kra_id == kra.id)
            .all()
        )

        kra_rating = kra_rating_map.get(kra.id)
        kra_self: Optional[float] = kra_rating.self_rating if kra_rating else None
        kra_mgr: Optional[float] = kra_rating.manager_rating if kra_rating else None

        # ── KRA achievement ───────────────────────────────────────────────────
        # Σ(KPI weightage) — denominator for achievement % (matches mid-cycle display)
        kpi_weight_total: float = sum(kpi.weightage for kpi in kpis)

        # Σ(KPI progress_percent) — treat unrecorded KPIs as 0 (not yet achieved)
        kra_achieved_weight: Optional[float] = None
        kra_achievement_pct: Optional[float] = None
        kra_derived: Optional[int] = None

        if mid_review is not None:
            kra_achieved_weight = sum(
                kpi_progress_map.get(kpi.id, 0.0) for kpi in kpis
            )
            if kpi_weight_total > 0:
                kra_achievement_pct = round(
                    kra_achieved_weight / kpi_weight_total * 100, 1
                )
            kra_derived = derive_mid_rating(kra_achievement_pct)

        kra_variance: Optional[float] = (
            round(float(kra_mgr) - float(kra_derived), 2)
            if kra_mgr is not None and kra_derived is not None
            else None
        )

        # ── KRA summary row ───────────────────────────────────────────────────
        rows.append({
            "row_type": "kra",
            "kra_id": kra.id,
            "kpi_id": None,
            "kra_title": kra.title,
            "kpi_title": None,
            "weightage": kra.weightage,
            "achieved_weight": kra_achieved_weight,
            "achievement_pct": kra_achievement_pct,
            "derived_mid_rating": kra_derived,
            "end_self_rating": kra_self,
            "end_manager_rating": kra_mgr,
            "variance": kra_variance,
        })

        # ── Individual KPI sub-rows ────────────────────────────────────────────
        for kpi in kpis:
            kpi_progress: Optional[float] = (
                kpi_progress_map.get(kpi.id) if mid_review is not None else None
            )

            kpi_achievement_pct: Optional[float] = None
            if kpi_progress is not None and kpi.weightage > 0:
                kpi_achievement_pct = round(kpi_progress / kpi.weightage * 100, 1)

            kpi_derived = derive_mid_rating(kpi_achievement_pct)

            kpi_variance: Optional[float] = (
                round(float(kra_mgr) - float(kpi_derived), 2)
                if kra_mgr is not None and kpi_derived is not None
                else None
            )

            rows.append({
                "row_type": "kpi",
                "kra_id": kra.id,
                "kpi_id": kpi.id,
                "kra_title": kra.title,      # parent KRA title (for frontend grouping)
                "kpi_title": kpi.title,
                "weightage": kpi.weightage,
                "achieved_weight": kpi_progress,
                "achievement_pct": kpi_achievement_pct,
                "derived_mid_rating": kpi_derived,
                "end_self_rating": kra_self,   # inherited from parent KRA rating
                "end_manager_rating": kra_mgr, # inherited from parent KRA rating
                "variance": kpi_variance,
            })

    # ── Competency rows ───────────────────────────────────────────────────────
    # Competencies have no mid-cycle progress tracking; variance = manager − self.
    for comp in comps:
        comp_rating = comp_rating_map.get(comp.id)
        comp_self: Optional[float] = comp_rating.self_rating if comp_rating else None
        comp_mgr: Optional[float] = comp_rating.manager_rating if comp_rating else None
        comp_variance: Optional[float] = (
            round(float(comp_mgr) - float(comp_self), 2)
            if comp_mgr is not None and comp_self is not None
            else None
        )
        rows.append({
            "row_type": "competency",
            "kra_id": None,
            "kpi_id": None,
            "kra_title": comp.title,   # reuse kra_title as display name
            "kpi_title": None,
            "weightage": comp.weightage,
            "achieved_weight": None,
            "achievement_pct": None,
            "derived_mid_rating": None,
            "end_self_rating": comp_self,
            "end_manager_rating": comp_mgr,
            "variance": comp_variance,
        })

    return rows
