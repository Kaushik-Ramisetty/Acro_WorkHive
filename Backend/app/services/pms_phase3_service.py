"""PMS Phase 3 — End Cycle Assessment service.

State machine:
  draft → self_assessed → manager_assessed → submitted_to_hr
  → hr_received → assessment_locked

HR creates assessments. Employee fills in self-assessment. Manager fills in
their assessment and submits to HR. HR receives and locks. All transitions
are manual — no automatic progression.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Employee, GoalAssignment, AssignedKRA, AssignedCompetency
from app.models.pms import (
    EndCycleAssessment, GoalRating, CompetencyRating,
    ECA_STATUS_DRAFT, ECA_STATUS_SELF_ASSESSED, ECA_STATUS_MGR_ASSESSED,
    ECA_STATUS_SUBMITTED_TO_HR, ECA_STATUS_HR_RECEIVED, ECA_STATUS_LOCKED,
    PMS_STATUS_GOALS_LOCKED,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many
import app.services.pms_email_service as pms_email
from app.services.pms_service import (
    is_hr, is_manager, full_name, full_name_for_id, _hr_recipient_ids,
    get_assignment_for, compute_deadline, _maybe_audit_deadline_override,
)
from app.models.pms import LOCK_TYPE_MANUAL, LOCK_TYPE_AUTO
from app.services.pms_comparison_service import build_comparison_rows


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit(db: Session, actor_id: int, action: str, eca_id: int,
           old: dict | None, new: dict | None) -> None:
    try:
        write_audit(
            db, actor_id=actor_id, action=action,
            target_table="pms_end_cycle_assessments", target_id=str(eca_id),
            old_value=old, new_value=new,
        )
    except Exception:
        pass


# ── View helper ───────────────────────────────────────────────────────────────

def assessment_view(db: Session, eca: EndCycleAssessment) -> dict:
    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    mgr = db.query(Employee).filter(Employee.id == a.manager_id).first() if (a and a.manager_id) else None

    # Build comparison rows safely — returns [] if no mid-cycle data exists.
    try:
        comparison_rows = build_comparison_rows(db, eca.assignment_id, eca)
    except Exception:
        comparison_rows = []

    return {
        "id": eca.id,
        "assignment_id": eca.assignment_id,
        "cycle_period": eca.cycle_period,
        "status": eca.status,
        "self_rating": eca.self_rating,
        "self_comments": eca.self_comments,
        "self_assessed_at": eca.self_assessed_at,
        "manager_rating": eca.manager_rating,
        "manager_comments": eca.manager_comments,
        "manager_assessed_at": eca.manager_assessed_at,
        "hr_notes": eca.hr_notes,
        "hr_received_at": eca.hr_received_at,
        "locked_at": eca.locked_at,
        "lock_type": getattr(eca, 'lock_type', None),
        "created_at": eca.created_at,
        "updated_at": eca.updated_at,
        "employee_name": full_name(emp),
        "employee_id": a.employee_id if a else None,
        "manager_name": full_name(mgr),
        "period": a.period if a else None,
        "kra_ratings": [
            {
                "id": r.id, "assigned_kra_id": r.assigned_kra_id,
                "self_rating": r.self_rating, "self_notes": r.self_notes,
                "manager_rating": r.manager_rating, "manager_notes": r.manager_notes,
            }
            for r in (eca.kra_ratings or [])
        ],
        "competency_ratings": [
            {
                "id": r.id, "assigned_competency_id": r.assigned_competency_id,
                "self_rating": r.self_rating, "self_notes": r.self_notes,
                "manager_rating": r.manager_rating, "manager_notes": r.manager_notes,
            }
            for r in (eca.competency_ratings or [])
        ],
        "mid_cycle_comparison": comparison_rows,
    }


# ── Access guard ──────────────────────────────────────────────────────────────

def _get_eca(db: Session, viewer: Employee, eca_id: int) -> EndCycleAssessment:
    eca = db.query(EndCycleAssessment).filter(EndCycleAssessment.id == eca_id).first()
    if not eca:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found.")
    if is_hr(viewer):
        return eca
    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if a.employee_id == viewer.id or a.manager_id == viewer.id:
        return eca
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this assessment.")


def _require_not_locked(eca: EndCycleAssessment) -> None:
    if eca.status == ECA_STATUS_LOCKED:
        if getattr(eca, 'lock_type', None) == LOCK_TYPE_AUTO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This phase has been automatically locked after the deadline and can no longer be modified.",
            )
        raise HTTPException(status.HTTP_409_CONFLICT, "Assessment is locked.")


# ── HR: create assessment ─────────────────────────────────────────────────────

def create_assessment(db: Session, hr: Employee, payload) -> EndCycleAssessment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    a = db.query(GoalAssignment).filter(GoalAssignment.id == payload.assignment_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal assignment not found.")
    if a.status != PMS_STATUS_GOALS_LOCKED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "End-cycle assessments can only be created for locked goal assignments.",
        )
    existing = db.query(EndCycleAssessment).filter(
        EndCycleAssessment.assignment_id == a.id,
        EndCycleAssessment.cycle_period == payload.cycle_period,
        EndCycleAssessment.status != ECA_STATUS_LOCKED,
    ).first()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An active end-cycle assessment already exists for this assignment (id={existing.id}).",
        )

    # CHANGE 9: auto-compute deadline; use HR-provided value if supplied.
    computed_dl = compute_deadline("end_cycle", db)
    provided_dl = getattr(payload, 'deadline', None)
    final_deadline = provided_dl if provided_dl is not None else computed_dl

    eca = EndCycleAssessment(
        assignment_id=a.id,
        cycle_period=payload.cycle_period,
        status=ECA_STATUS_DRAFT,
        deadline=final_deadline,  # CHANGE 9: always set
        created_by=hr.id,
    )
    db.add(eca)
    db.flush()

    # CHANGE 9: audit deadline override if HR provided a different value.
    _maybe_audit_deadline_override(db, hr.id, "pms.eca", eca.id, provided_dl, computed_dl)

    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    dl_label = final_deadline.strftime("%d %b %Y") if final_deadline else ""
    notify(
        db, recipient_id=a.employee_id,
        type_="pms_assessment_opened",
        title=f"End Cycle Assessment — {payload.cycle_period or a.period or 'Opened'}".strip(" —"),
        body=(
            f"Phase: End Cycle Assessment | Action: Complete your self-assessment"
            + (f" | Due: {dl_label}" if dl_label else "")
        ),
        reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
    )
    pms_email.email_assessment_opened(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        period=a.period,
        cycle_period=payload.cycle_period,
        due_date=final_deadline,  # CHANGE 9
    )
    _audit(db, hr.id, "pms.eca.create", eca.id, None,
           {"assignment_id": a.id, "cycle_period": eca.cycle_period})
    db.commit()
    db.refresh(eca)
    return eca


# ── Listing ───────────────────────────────────────────────────────────────────

def list_assessments(
    db: Session, viewer: Employee, scope: str = "auto",
    assignment_id: Optional[int] = None,
) -> List[EndCycleAssessment]:
    q = db.query(EndCycleAssessment)
    if assignment_id:
        q = q.filter(EndCycleAssessment.assignment_id == assignment_id)

    if scope == "auto":
        scope = "hr" if is_hr(viewer) else ("manager" if is_manager(viewer) else "employee")

    if scope == "hr":
        pass
    elif scope == "manager":
        mgr_assignment_ids = [
            a.id for a in db.query(GoalAssignment).filter(
                GoalAssignment.manager_id == viewer.id
            ).all()
        ]
        q = q.filter(EndCycleAssessment.assignment_id.in_(mgr_assignment_ids))
    else:
        emp_assignment_ids = [
            a.id for a in db.query(GoalAssignment).filter(
                GoalAssignment.employee_id == viewer.id
            ).all()
        ]
        q = q.filter(EndCycleAssessment.assignment_id.in_(emp_assignment_ids))

    return q.order_by(EndCycleAssessment.created_at.desc()).all()


def get_assessment(db: Session, viewer: Employee, eca_id: int) -> EndCycleAssessment:
    return _get_eca(db, viewer, eca_id)


# ── Employee: self-assessment ─────────────────────────────────────────────────

def employee_self_assess(
    db: Session, employee: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    eca = _get_eca(db, employee, eca_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    if a.employee_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assignee can submit self-assessment.")
    _require_not_locked(eca)
    if eca.status not in (ECA_STATUS_DRAFT, ECA_STATUS_SELF_ASSESSED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot submit self-assessment from status '{eca.status}'.",
        )

    eca.self_rating = payload.self_rating
    eca.self_comments = payload.self_comments
    eca.self_assessed_at = datetime.utcnow()
    eca.status = ECA_STATUS_SELF_ASSESSED

    # Upsert KRA ratings.
    kra_map = {r.assigned_kra_id: r for r in eca.kra_ratings}
    for kra_in in payload.kra_ratings or []:
        if kra_in.assigned_kra_id in kra_map:
            r = kra_map[kra_in.assigned_kra_id]
        else:
            r = GoalRating(assessment_id=eca.id, assigned_kra_id=kra_in.assigned_kra_id)
            db.add(r)
        r.self_rating = kra_in.self_rating
        r.self_notes = kra_in.self_notes

    # Upsert competency ratings.
    comp_map = {r.assigned_competency_id: r for r in eca.competency_ratings}
    for comp_in in payload.competency_ratings or []:
        if comp_in.assigned_competency_id in comp_map:
            r = comp_map[comp_in.assigned_competency_id]
        else:
            r = CompetencyRating(assessment_id=eca.id, assigned_competency_id=comp_in.assigned_competency_id)
            db.add(r)
        r.self_rating = comp_in.self_rating
        r.self_notes = comp_in.self_notes

    if a.manager_id:
        notify(
            db, recipient_id=a.manager_id,
            type_="pms_self_assessed",
            title=f"{full_name(employee)} submitted self-assessment",
            body="Please review and complete your manager assessment.",
            reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
        )
    pms_email.email_self_assessment_submitted(
        db,
        manager_id=a.manager_id,
        employee_name=full_name(employee),
        period=a.period,
        cycle_period=eca.cycle_period,
    )
    _audit(db, employee.id, "pms.eca.self_assess", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca


# ── Manager: assessment ───────────────────────────────────────────────────────

def manager_assess(
    db: Session, manager: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    eca = _get_eca(db, manager, eca_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may assess.")
    _require_not_locked(eca)
    if eca.status not in (ECA_STATUS_SELF_ASSESSED, ECA_STATUS_MGR_ASSESSED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Employee must complete self-assessment first (current: '{eca.status}').",
        )

    eca.manager_rating = payload.manager_rating
    eca.manager_comments = payload.manager_comments
    eca.manager_assessed_at = datetime.utcnow()
    eca.manager_assessed_by = manager.id
    eca.status = ECA_STATUS_MGR_ASSESSED

    # Upsert manager KRA ratings (preserve self ratings).
    kra_map = {r.assigned_kra_id: r for r in eca.kra_ratings}
    for kra_in in payload.kra_ratings or []:
        if kra_in.assigned_kra_id in kra_map:
            r = kra_map[kra_in.assigned_kra_id]
        else:
            r = GoalRating(assessment_id=eca.id, assigned_kra_id=kra_in.assigned_kra_id)
            db.add(r)
        r.manager_rating = kra_in.manager_rating
        r.manager_notes = kra_in.manager_notes

    comp_map = {r.assigned_competency_id: r for r in eca.competency_ratings}
    for comp_in in payload.competency_ratings or []:
        if comp_in.assigned_competency_id in comp_map:
            r = comp_map[comp_in.assigned_competency_id]
        else:
            r = CompetencyRating(assessment_id=eca.id, assigned_competency_id=comp_in.assigned_competency_id)
            db.add(r)
        r.manager_rating = comp_in.manager_rating
        r.manager_notes = comp_in.manager_notes

    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    notify(
        db, recipient_id=a.employee_id,
        type_="pms_manager_assessed",
        title="Manager completed your end-cycle assessment",
        body="View their ratings and feedback in Performance.",
        reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
    )
    pms_email.email_manager_assessment_submitted(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        manager_name=full_name(manager),
        period=a.period,
        cycle_period=eca.cycle_period,
    )
    _audit(db, manager.id, "pms.eca.manager_assess", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca


# ── Manager/HR: submit to HR ──────────────────────────────────────────────────

def submit_to_hr(
    db: Session, actor: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    eca = _get_eca(db, actor, eca_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    if a.manager_id != actor.id and not is_hr(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may submit.")
    _require_not_locked(eca)
    if eca.status != ECA_STATUS_MGR_ASSESSED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Manager must complete assessment before submitting to HR (current: '{eca.status}').",
        )

    eca.status = ECA_STATUS_SUBMITTED_TO_HR

    hr_ids = _hr_recipient_ids(db)
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    if hr_ids:
        notify_many(
            db, hr_ids,
            type_="pms_assessment_submitted_to_hr",
            title=f"End-cycle assessment submitted for {full_name(emp)}",
            body="Open the end-cycle review queue to receive and lock.",
            reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
        )
    pms_email.email_assessment_submitted_to_hr(
        db,
        employee_name=full_name(emp),
        period=a.period,
        cycle_period=eca.cycle_period,
        hr_ids=hr_ids,
    )
    _audit(db, actor.id, "pms.eca.submit_to_hr", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca


# ── HR: receive ───────────────────────────────────────────────────────────────

def hr_receive(
    db: Session, hr: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    eca = _get_eca(db, hr, eca_id)
    _require_not_locked(eca)
    if eca.status != ECA_STATUS_SUBMITTED_TO_HR:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Assessment must be submitted to HR first (current: '{eca.status}').",
        )

    if payload and payload.notes:
        eca.hr_notes = payload.notes
    eca.status = ECA_STATUS_HR_RECEIVED
    eca.hr_received_at = datetime.utcnow()
    eca.hr_received_by = hr.id

    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    recipients = [a.employee_id] if a else []
    if a and a.manager_id:
        recipients.append(a.manager_id)
    notify_many(
        db, recipients,
        type_="pms_assessment_hr_received",
        title="HR received your end-cycle assessment",
        body="Your assessment will be finalized shortly.",
        reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
    )
    pms_email.email_assessment_hr_received(
        db,
        employee_id=a.employee_id if a else 0,
        employee_name=full_name(emp),
        manager_id=a.manager_id if a else None,
        period=a.period if a else None,
        cycle_period=eca.cycle_period,
    )
    _audit(db, hr.id, "pms.eca.hr_receive", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca


# ── HR: lock ──────────────────────────────────────────────────────────────────

def hr_lock(
    db: Session, hr: Employee, eca_id: int, payload,
    lock_type: str = LOCK_TYPE_MANUAL,
) -> EndCycleAssessment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    eca = _get_eca(db, hr, eca_id)
    if eca.status not in (ECA_STATUS_HR_RECEIVED, ECA_STATUS_SUBMITTED_TO_HR):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Assessment must be HR-received to lock (current: '{eca.status}').",
        )
    if payload and payload.notes:
        eca.hr_notes = payload.notes
    eca.status = ECA_STATUS_LOCKED
    eca.locked_at = datetime.utcnow()
    eca.locked_by = hr.id
    eca.lock_type = lock_type

    a = db.query(GoalAssignment).filter(GoalAssignment.id == eca.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    recipients = [a.employee_id] if a else []
    if a and a.manager_id:
        recipients.append(a.manager_id)
    notify_many(
        db, recipients,
        type_="pms_assessment_locked",
        title="End-cycle assessment locked",
        body="Your performance assessment has been finalised by HR.",
        reference_table="pms_end_cycle_assessments", reference_id=str(eca.id),
    )
    pms_email.email_assessment_locked(
        db,
        employee_id=a.employee_id if a else 0,
        employee_name=full_name(emp),
        manager_id=a.manager_id if a else None,
        period=a.period if a else None,
        cycle_period=eca.cycle_period,
    )
    _audit(db, hr.id, "pms.eca.lock", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca


# ── HR: save notes (standalone — no state transition) ────────────────────────

def save_hr_notes(
    db: Session, hr: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    """HR can save notes at any point before the assessment is locked."""
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    eca = _get_eca(db, hr, eca_id)
    if eca.status == ECA_STATUS_LOCKED:
        if getattr(eca, 'lock_type', None) == LOCK_TYPE_AUTO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This phase has been automatically locked after the deadline and can no longer be modified.",
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Assessment is locked — notes can no longer be edited.",
        )
    old_notes = eca.hr_notes
    eca.hr_notes = payload.notes or None
    _audit(db, hr.id, "pms.eca.update_hr_notes", eca.id,
           {"hr_notes": old_notes}, {"hr_notes": eca.hr_notes})
    db.commit()
    db.refresh(eca)
    return eca


# ── HR: unlock ────────────────────────────────────────────────────────────────

def hr_unlock(
    db: Session, hr: Employee, eca_id: int, payload
) -> EndCycleAssessment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    eca = _get_eca(db, hr, eca_id)
    if eca.status != ECA_STATUS_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only locked assessments can be unlocked.")
    if getattr(eca, 'lock_type', None) == LOCK_TYPE_AUTO:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This phase has been automatically locked after the deadline and can no longer be modified.",
        )
    eca.status = ECA_STATUS_HR_RECEIVED
    eca.locked_at = None
    eca.locked_by = None
    eca.lock_type = None
    _audit(db, hr.id, "pms.eca.unlock", eca.id, None, {"status": eca.status})
    db.commit()
    db.refresh(eca)
    return eca
