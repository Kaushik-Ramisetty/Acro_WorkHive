"""PMS Phase 4 — HR Normalization service.

State machine (NormalizationSession):
  draft → normalized → frozen → hike_generated → hike_approved

HR creates a session for a period, pulling in all locked end-cycle assessments.
HR normalizes ratings (computed or manual overrides). HR freezes the ratings,
generates hike recommendations, then gets management approval.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Employee, GoalAssignment
from app.models.pms import (
    EndCycleAssessment, NormalizationSession, NormalizationRecord,
    ECA_STATUS_LOCKED,
    NORM_STATUS_DRAFT, NORM_STATUS_NORMALIZED, NORM_STATUS_FROZEN,
    NORM_STATUS_HIKE_GENERATED, NORM_STATUS_HIKE_APPROVED,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify_many
import app.services.pms_email_service as pms_email
from app.services.pms_service import (
    is_hr, full_name, _hr_recipient_ids,
    compute_deadline, _maybe_audit_deadline_override,
)


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit(db: Session, actor_id: int, action: str, session_id: int,
           old: dict | None, new: dict | None) -> None:
    try:
        write_audit(
            db, actor_id=actor_id, action=action,
            target_table="pms_normalization_sessions", target_id=str(session_id),
            old_value=old, new_value=new,
        )
    except Exception:
        pass


# ── View helper ───────────────────────────────────────────────────────────────

def _record_view(db: Session, rec: NormalizationRecord) -> dict:
    emp = db.query(Employee).filter(Employee.id == rec.employee_id).first()
    return {
        "id": rec.id,
        "session_id": rec.session_id,
        "assessment_id": rec.assessment_id,
        "employee_id": rec.employee_id,
        "employee_name": full_name(emp),
        "raw_manager_rating": rec.raw_manager_rating,
        "raw_self_rating": rec.raw_self_rating,
        "normalized_rating": rec.normalized_rating,
        "override_rating": rec.override_rating,
        "override_reason": rec.override_reason,
        "final_rating": rec.final_rating,
        # CHANGE 4: override audit fields
        "override_modified_by": rec.override_modified_by,
        "override_modified_at": rec.override_modified_at,
        "hike_percent": rec.hike_percent,
        "hike_notes": rec.hike_notes,
        # CHANGE 5: manual hike audit fields
        "hike_entered_by": rec.hike_entered_by,
        "hike_entered_at": rec.hike_entered_at,
        "compensation_comments": rec.compensation_comments,
    }


def session_view(db: Session, sess: NormalizationSession) -> dict:
    return {
        "id": sess.id,
        "period": sess.period,
        "status": sess.status,
        "notes": sess.notes,
        "deadline": sess.deadline,  # CHANGE 3
        "normalized_at": sess.normalized_at,
        "frozen_at": sess.frozen_at,
        "hike_generated_at": sess.hike_generated_at,
        "hike_approved_at": sess.hike_approved_at,
        "created_at": sess.created_at,
        "records": [_record_view(db, r) for r in (sess.records or [])],
    }


def _require_hr(actor: Employee) -> None:
    if not is_hr(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")


def _require_not_frozen(sess: NormalizationSession) -> None:
    """Ratings (override_rating) are locked once the session is frozen."""
    if sess.status in (NORM_STATUS_FROZEN, NORM_STATUS_HIKE_GENERATED, NORM_STATUS_HIKE_APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is frozen — ratings cannot be modified.")


def _require_hike_editable(sess: NormalizationSession) -> None:
    """Hike % can be edited until the hike is approved (FROZEN and HIKE_GENERATED are both allowed)."""
    if sess.status == NORM_STATUS_HIKE_APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Hike has already been approved — hike % can no longer be changed.",
        )


# ── HR: create normalization session ─────────────────────────────────────────

def create_session(db: Session, hr: Employee, payload) -> NormalizationSession:
    _require_hr(hr)

    # Use the shared helper so the query is consistent with list_eligible_ecas().
    locked_ecas = _locked_ecas_for_period(db, payload.period)

    # CHANGE 9: auto-compute deadline; use HR-provided value if supplied.
    computed_dl = compute_deadline("normalization", db)
    provided_dl = getattr(payload, 'deadline', None)
    final_deadline = provided_dl if provided_dl is not None else computed_dl

    sess = NormalizationSession(
        period=payload.period,
        status=NORM_STATUS_DRAFT,
        notes=payload.notes,
        deadline=final_deadline,  # CHANGE 9: always set
        created_by=hr.id,
    )
    db.add(sess)
    db.flush()

    # CHANGE 9: audit deadline override if HR provided a different value.
    _maybe_audit_deadline_override(db, hr.id, "pms.norm", sess.id, provided_dl, computed_dl)

    eca_count = 0
    for eca in locked_ecas:
        a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
        if not a:
            continue
        # Skip ECAs already assigned to any other normalization session.
        existing = db.query(NormalizationRecord).filter(
            NormalizationRecord.assessment_id == eca.id,
            NormalizationRecord.session_id != sess.id,
        ).first()
        if existing:
            continue
        rec = NormalizationRecord(
            session_id=sess.id,
            assessment_id=eca.id,
            employee_id=a.employee_id,
            raw_manager_rating=eca.manager_rating,
            raw_self_rating=eca.self_rating,
            normalized_rating=eca.manager_rating,
            final_rating=eca.manager_rating,
        )
        db.add(rec)
        eca_count += 1

    _audit(db, hr.id, "pms.norm.create", sess.id, None,
           {"period": sess.period, "eca_count": eca_count})
    db.commit()
    db.refresh(sess)
    return sess


# ── Eligible ECA query (used by both listing & session creation) ──────────────

def _locked_ecas_for_period(db: Session, period: Optional[str]) -> List[EndCycleAssessment]:
    """Return all locked ECAs where either ECA.cycle_period OR Assignment.period matches."""
    q = (
        db.query(EndCycleAssessment)
        .join(GoalAssignment, GoalAssignment.id == EndCycleAssessment.assignment_id)
        .filter(EndCycleAssessment.status == ECA_STATUS_LOCKED)
    )
    if period:
        q = q.filter(
            or_(
                EndCycleAssessment.cycle_period == period,
                GoalAssignment.period == period,
            )
        )
    return q.order_by(EndCycleAssessment.id).all()


def list_eligible_ecas(db: Session, hr: Employee, period: Optional[str] = None) -> List[dict]:
    """
    Return all locked ECAs available for normalization (optionally filtered by period).

    Each entry includes employee info, ratings, the effective period label, and whether
    the ECA is already assigned to an active (non-deleted) normalization session so the
    frontend can clearly flag duplicates.
    """
    _require_hr(hr)
    ecas = _locked_ecas_for_period(db, period)

    # Build a lookup: eca_id → session_id for ECAs already assigned.
    assigned_eca_ids: dict[int, int] = {}
    for rec in db.query(NormalizationRecord).all():
        assigned_eca_ids[rec.assessment_id] = rec.session_id

    results = []
    for eca in ecas:
        a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
        if not a:
            continue
        emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
        mgr = db.query(Employee).filter(Employee.id == a.manager_id).first() if a.manager_id else None

        # Effective period: prefer Assignment.period so it matches NormalizationSession creation.
        effective_period = a.period or eca.cycle_period or ""

        results.append({
            "eca_id":          eca.id,
            "assignment_id":   eca.assignment_id,
            "employee_id":     a.employee_id,
            "employee_name":   full_name(emp),
            "manager_name":    full_name(mgr),
            "period":          effective_period,
            "cycle_period":    eca.cycle_period,
            "self_rating":     eca.self_rating,
            "manager_rating":  eca.manager_rating,
            "locked_at":       eca.locked_at,
            "in_session_id":   assigned_eca_ids.get(eca.id),  # None → available
        })

    return results


def distinct_eligible_periods(db: Session, hr: Employee) -> List[str]:
    """Return sorted distinct period labels from all locked ECAs (assignment period OR cycle_period)."""
    _require_hr(hr)
    periods: set[str] = set()

    # Assignment periods for locked ECAs.
    rows = (
        db.query(GoalAssignment.period)
        .join(EndCycleAssessment, EndCycleAssessment.assignment_id == GoalAssignment.id)
        .filter(
            EndCycleAssessment.status == ECA_STATUS_LOCKED,
            GoalAssignment.period.isnot(None),
        )
        .distinct()
        .all()
    )
    for (p,) in rows:
        if p:
            periods.add(p.strip())

    # ECA cycle_periods.
    rows2 = (
        db.query(EndCycleAssessment.cycle_period)
        .filter(
            EndCycleAssessment.status == ECA_STATUS_LOCKED,
            EndCycleAssessment.cycle_period.isnot(None),
        )
        .distinct()
        .all()
    )
    for (p,) in rows2:
        if p:
            periods.add(p.strip())

    return sorted(periods)


# ── Listing ───────────────────────────────────────────────────────────────────

def list_sessions(db: Session, hr: Employee) -> List[NormalizationSession]:
    _require_hr(hr)
    return db.query(NormalizationSession).order_by(NormalizationSession.created_at.desc()).all()


def get_session(db: Session, hr: Employee, session_id: int) -> NormalizationSession:
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Normalization session not found.")
    return sess


# ── HR: add records to an existing session ────────────────────────────────────

def add_records_to_session(
    db: Session, hr: Employee, session_id: int
) -> NormalizationSession:
    """
    Re-scan locked ECAs for the session's period and add any that are not yet
    in THIS session.  Idempotent — calling it twice is safe.
    """
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    _require_not_frozen(sess)

    ecas = _locked_ecas_for_period(db, sess.period)

    # Only skip ECAs already in THIS session (not in other sessions).
    existing_eca_ids_in_this_session: set[int] = {
        r.assessment_id for r in sess.records
    }

    added = 0
    for eca in ecas:
        if eca.id in existing_eca_ids_in_this_session:
            continue
        a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
        if not a:
            continue
        # Check if this ECA is already in a DIFFERENT session — log a warning but still skip.
        other = db.query(NormalizationRecord).filter(
            NormalizationRecord.assessment_id == eca.id,
            NormalizationRecord.session_id != session_id,
        ).first()
        if other:
            continue  # Already normalised in another session — skip to prevent duplicates.

        rec = NormalizationRecord(
            session_id=sess.id,
            assessment_id=eca.id,
            employee_id=a.employee_id,
            raw_manager_rating=eca.manager_rating,
            raw_self_rating=eca.self_rating,
            normalized_rating=eca.manager_rating,
            final_rating=eca.manager_rating,
        )
        db.add(rec)
        added += 1

    _audit(db, hr.id, "pms.norm.add_records", sess.id, None, {"added": added})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: update a single record ────────────────────────────────────────────────

def update_record(
    db: Session, hr: Employee, session_id: int, record_id: int, payload
) -> NormalizationRecord:
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")

    rec = db.query(NormalizationRecord).filter(
        NormalizationRecord.id == record_id,
        NormalizationRecord.session_id == session_id,
    ).first()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found.")

    now = datetime.utcnow()

    # ── Override rating ────────────────────────────────────────────────────────
    # Blocked once the session is frozen.  Override reason is OPTIONAL — HR may
    # provide it as an audit note but it is no longer enforced.
    rating_touched = payload.override_rating is not None or (
        payload.override_rating is None and rec.override_rating is not None
        and hasattr(payload, '__fields_set__') and 'override_rating' in payload.__fields_set__
    )
    if payload.override_rating is not None:
        _require_not_frozen(sess)
        rec.override_rating = payload.override_rating
        rec.override_reason = (payload.override_reason or "").strip() or None
        rec.final_rating = payload.override_rating
        rec.override_modified_by = hr.id
        rec.override_modified_at = now
    elif hasattr(payload, '__fields_set__') and 'override_rating' in payload.__fields_set__ and payload.override_rating is None:
        # Explicit None = clear override
        _require_not_frozen(sess)
        rec.override_rating = None
        rec.override_reason = None
        rec.override_modified_by = None
        rec.override_modified_at = None
    elif payload.override_reason is not None:
        # Updating reason without changing the rating — still needs unfrozen session
        _require_not_frozen(sess)
        rec.override_reason = payload.override_reason.strip() or None

    # If no override, final = normalized.
    if rec.override_rating is None and rec.normalized_rating is not None:
        rec.final_rating = rec.normalized_rating

    # ── Hike % ────────────────────────────────────────────────────────────────
    # Editable until the hike is approved.  FROZEN and HIKE_GENERATED are both
    # allowed so HR can correct hike % after freezing ratings.
    if payload.hike_percent is not None:
        _require_hike_editable(sess)
        rec.hike_percent = payload.hike_percent
        rec.hike_entered_by = hr.id
        rec.hike_entered_at = now
    if payload.hike_notes is not None:
        _require_hike_editable(sess)
        rec.hike_notes = payload.hike_notes
    if payload.compensation_comments is not None:
        rec.compensation_comments = payload.compensation_comments

    _audit(db, hr.id, "pms.norm.update_record", session_id,
           None, {"record_id": record_id, "final_rating": rec.final_rating,
                  "override_rating": rec.override_rating, "hike_percent": rec.hike_percent})
    db.commit()
    db.refresh(rec)
    return rec


# ── HR: normalize ─────────────────────────────────────────────────────────────

def normalize_session(
    db: Session, hr: Employee, session_id: int, payload
) -> NormalizationSession:
    """Compute normalized ratings for all records (simple mean of self + manager)."""
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    _require_not_frozen(sess)
    if sess.status not in (NORM_STATUS_DRAFT, NORM_STATUS_NORMALIZED):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Cannot normalize from status '{sess.status}'.")

    for rec in sess.records:
        # Compute weighted mean: 30% self + 70% manager (industry standard).
        s = rec.raw_self_rating or 0.0
        m = rec.raw_manager_rating or 0.0
        if rec.raw_self_rating and rec.raw_manager_rating:
            rec.normalized_rating = round(0.3 * s + 0.7 * m, 2)
        elif rec.raw_manager_rating:
            rec.normalized_rating = rec.raw_manager_rating
        elif rec.raw_self_rating:
            rec.normalized_rating = rec.raw_self_rating
        # Apply override if present, else use normalized.
        rec.final_rating = rec.override_rating if rec.override_rating is not None else rec.normalized_rating

    if payload and payload.notes:
        sess.notes = payload.notes
    sess.status = NORM_STATUS_NORMALIZED
    sess.normalized_at = datetime.utcnow()
    sess.normalized_by = hr.id

    _audit(db, hr.id, "pms.norm.normalize", sess.id, None, {"status": sess.status})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: freeze ratings ────────────────────────────────────────────────────────

def freeze_session(
    db: Session, hr: Employee, session_id: int, payload
) -> NormalizationSession:
    """Freeze ratings.

    The "Normalize Ratings" step is now optional — if the session is still in
    DRAFT status when HR clicks Freeze, normalization is run automatically before
    freezing so HR can skip the separate Normalize action.

    Override reasons are no longer mandatory (the check has been removed).
    """
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.status not in (NORM_STATUS_DRAFT, NORM_STATUS_NORMALIZED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot freeze from status '{sess.status}'. Session must be in draft or normalized.",
        )

    # Auto-normalize if HR skipped the explicit Normalize step.
    if sess.status == NORM_STATUS_DRAFT:
        for rec in sess.records:
            s = rec.raw_self_rating or 0.0
            m = rec.raw_manager_rating or 0.0
            if rec.raw_self_rating and rec.raw_manager_rating:
                rec.normalized_rating = round(0.3 * s + 0.7 * m, 2)
            elif rec.raw_manager_rating:
                rec.normalized_rating = rec.raw_manager_rating
            elif rec.raw_self_rating:
                rec.normalized_rating = rec.raw_self_rating
            rec.final_rating = rec.override_rating if rec.override_rating is not None else rec.normalized_rating
        sess.status = NORM_STATUS_NORMALIZED
        sess.normalized_at = datetime.utcnow()
        sess.normalized_by = hr.id

    sess.status = NORM_STATUS_FROZEN
    sess.frozen_at = datetime.utcnow()
    sess.frozen_by = hr.id

    # Notify all affected employees.
    employee_ids = [r.employee_id for r in sess.records]
    if employee_ids:
        notify_many(
            db, employee_ids,
            type_="pms_rating_frozen",
            title="Your performance rating has been frozen",
            body="HR has finalised the rating normalization for this cycle.",
            reference_table="pms_normalization_sessions", reference_id=str(sess.id),
        )
    pms_email.email_rating_frozen(db, period=sess.period, employee_ids=employee_ids)
    _audit(db, hr.id, "pms.norm.freeze", sess.id, None, {"status": sess.status})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: submit hike % (manual only — CHANGE 5) ───────────────────────────────

def generate_hike(
    db: Session, hr: Employee, session_id: int, payload
) -> NormalizationSession:
    """CHANGE 5: Removed automatic hike generation.
    HR must have manually entered hike_percent for every record before calling this.
    This function validates completeness and advances the session status."""
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.status != NORM_STATUS_FROZEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session must be frozen before submitting hikes.")

    # CHANGE 5: validate all records have manually-entered hike_percent
    missing = []
    for rec in sess.records:
        if rec.hike_percent is None:
            emp = db.query(Employee).filter(Employee.id == rec.employee_id).first()
            missing.append(full_name(emp) if emp else f"Employee #{rec.employee_id}")
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Hike % must be manually entered for all employees before submitting. "
            f"Missing for: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
        )

    sess.status = NORM_STATUS_HIKE_GENERATED
    sess.hike_generated_at = datetime.utcnow()
    sess.hike_generated_by = hr.id

    hr_ids = _hr_recipient_ids(db)
    if hr_ids:
        notify_many(
            db, hr_ids,
            type_="pms_hike_generated",
            title=f"Hike % submitted for approval — {sess.period}",
            body="Review and approve the manually-entered hike recommendations.",
            reference_table="pms_normalization_sessions", reference_id=str(sess.id),
        )
    pms_email.email_hike_generated(db, period=sess.period, hr_ids=hr_ids)
    _audit(db, hr.id, "pms.norm.submit_hike", sess.id, None, {"status": sess.status})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: approve hikes ─────────────────────────────────────────────────────────

def approve_hike(
    db: Session, hr: Employee, session_id: int, payload
) -> NormalizationSession:
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.status != NORM_STATUS_HIKE_GENERATED:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Hikes must be generated before approval.")

    sess.status = NORM_STATUS_HIKE_APPROVED
    sess.hike_approved_at = datetime.utcnow()
    sess.hike_approved_by = hr.id

    # Notify all affected employees.
    employee_ids = [r.employee_id for r in sess.records]
    if employee_ids:
        notify_many(
            db, employee_ids,
            type_="pms_hike_approved",
            title="Your hike recommendation has been approved",
            body="HR will communicate your revised compensation shortly.",
            reference_table="pms_normalization_sessions", reference_id=str(sess.id),
        )
    pms_email.email_hike_approved(db, period=sess.period, employee_ids=employee_ids)
    _audit(db, hr.id, "pms.norm.approve_hike", sess.id, None, {"status": sess.status})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: update session (Issue 4) ──────────────────────────────────────────────

def update_session(
    db: Session, hr: Employee, session_id: int, payload
) -> NormalizationSession:
    """HR may update period / notes only while the session is still editable (draft / normalized)."""
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    _require_not_frozen(sess)
    if sess.status not in (NORM_STATUS_DRAFT, NORM_STATUS_NORMALIZED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Session cannot be edited in status '{sess.status}'.",
        )

    old_period = sess.period
    if payload.period:
        sess.period = payload.period.strip()
    if payload.notes is not None:
        sess.notes = payload.notes
    if hasattr(payload, 'deadline'):
        sess.deadline = payload.deadline  # CHANGE 3

    _audit(db, hr.id, "pms.norm.update", sess.id,
           {"period": old_period, "notes": sess.notes},
           {"period": sess.period, "notes": sess.notes})
    db.commit()
    db.refresh(sess)
    return sess


# ── HR: delete session (Issue 4) ──────────────────────────────────────────────

def delete_session(
    db: Session, hr: Employee, session_id: int
) -> None:
    """HR may delete a session only while it is in draft status (no records frozen / approved)."""
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.status != NORM_STATUS_DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only draft sessions can be deleted (current: '{sess.status}'). "
            "Freeze / approved sessions are protected.",
        )
    _audit(db, hr.id, "pms.norm.delete", sess.id, {"period": sess.period}, None)
    db.delete(sess)
    db.commit()
