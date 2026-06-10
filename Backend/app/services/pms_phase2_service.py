"""PMS Phase 2 — Mid-Cycle Review service.

State machine:
  draft → in_progress → submitted → manager_reviewed → manager_approved
  → hr_reviewed → mid_cycle_locked

HR creates reviews. Employee updates progress and submits. Manager reviews,
provides feedback, and approves. HR reviews and locks. All transitions are
manual (no cron/scheduler). Designed so timeline automation can be added later
without schema changes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Employee, GoalAssignment, AssignedKPI
from app.models.pms import (
    MidCycleReview, KPIProgress, ReviewEvidence,
    MCR_STATUS_DRAFT, MCR_STATUS_IN_PROGRESS, MCR_STATUS_SUBMITTED,
    MCR_STATUS_MGR_REVIEWED, MCR_STATUS_MGR_APPROVED,
    MCR_STATUS_HR_REVIEWED, MCR_STATUS_LOCKED,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many
import app.services.pms_email_service as pms_email

# Reuse Phase 1 helpers.
from app.services.pms_service import (
    is_hr, is_manager, full_name, full_name_for_id, _hr_recipient_ids,
    get_assignment_for, compute_deadline, _maybe_audit_deadline_override,
)
from app.models.pms import LOCK_TYPE_MANUAL, LOCK_TYPE_AUTO


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit(db: Session, actor_id: int, action: str, review_id: int,
           old: dict | None, new: dict | None) -> None:
    try:
        write_audit(
            db, actor_id=actor_id, action=action,
            target_table="pms_mid_cycle_reviews", target_id=str(review_id),
            old_value=old, new_value=new,
        )
    except Exception:
        pass


# ── View helper ───────────────────────────────────────────────────────────────

def review_view(db: Session, r: MidCycleReview) -> dict:
    """Hydrate a MidCycleReview with assignment/employee/manager context."""
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    mgr = db.query(Employee).filter(Employee.id == a.manager_id).first() if (a and a.manager_id) else None

    return {
        "id": r.id,
        "assignment_id": r.assignment_id,
        "cycle_period": r.cycle_period,
        "status": r.status,
        "deadline": r.deadline,  # CHANGE 3
        "allow_goal_modification": r.allow_goal_modification,
        "employee_comments": r.employee_comments,
        "manager_comments": r.manager_comments,
        "hr_comments": r.hr_comments,
        "submitted_at": r.submitted_at,
        "manager_reviewed_at": r.manager_reviewed_at,
        "manager_approved_at": r.manager_approved_at,
        "hr_reviewed_at": r.hr_reviewed_at,
        "locked_at": r.locked_at,
        "lock_type": getattr(r, 'lock_type', None),
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "employee_name": full_name(emp),
        "manager_name": full_name(mgr),
        "period": a.period if a else None,
        "kpi_progress": [
            {
                "id": p.id,
                "assigned_kpi_id": p.assigned_kpi_id,
                "current_value": p.current_value,
                "progress_percent": p.progress_percent,
                "employee_notes": p.employee_notes,
                "manager_notes": p.manager_notes,
                "updated_at": p.updated_at,
            }
            for p in sorted(r.kpi_progress or [], key=lambda x: x.assigned_kpi_id)
        ],
        "evidences": [
            {
                "id": e.id,
                "review_id": e.review_id,
                "assigned_kpi_id": e.assigned_kpi_id,
                "title": e.title,
                "description": e.description,
                "evidence_url": e.evidence_url,
                "uploaded_by": e.uploaded_by,
                "created_at": e.created_at,
            }
            for e in sorted(r.evidences or [], key=lambda x: x.created_at)
        ],
    }


# ── Access guard ──────────────────────────────────────────────────────────────

def _get_review(db: Session, viewer: Employee, review_id: int) -> MidCycleReview:
    r = db.query(MidCycleReview).filter(MidCycleReview.id == review_id).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mid-cycle review not found.")
    if is_hr(viewer):
        return r
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if a.employee_id == viewer.id or a.manager_id == viewer.id:
        return r
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this review.")


def _require_not_locked(r: MidCycleReview) -> None:
    if r.status == MCR_STATUS_LOCKED:
        if getattr(r, 'lock_type', None) == LOCK_TYPE_AUTO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This phase has been automatically locked after the deadline and can no longer be modified.",
            )
        raise HTTPException(status.HTTP_409_CONFLICT, "Mid-cycle review is locked.")


# ── HR: create mid-cycle review ───────────────────────────────────────────────

def create_mid_cycle_review(db: Session, hr: Employee, payload) -> MidCycleReview:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    a = db.query(GoalAssignment).filter(GoalAssignment.id == payload.assignment_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal assignment not found.")

    # One active review per assignment + cycle_period.
    existing = db.query(MidCycleReview).filter(
        MidCycleReview.assignment_id == a.id,
        MidCycleReview.cycle_period == payload.cycle_period,
        MidCycleReview.status != MCR_STATUS_LOCKED,
    ).first()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An active mid-cycle review already exists for this assignment (id={existing.id}).",
        )

    # CHANGE 9: auto-compute deadline; use HR-provided value if supplied.
    computed_dl = compute_deadline("mid_cycle", db)
    provided_dl = getattr(payload, 'deadline', None)
    final_deadline = provided_dl if provided_dl is not None else computed_dl

    r = MidCycleReview(
        assignment_id=a.id,
        cycle_period=payload.cycle_period,
        status=MCR_STATUS_DRAFT,
        deadline=final_deadline,  # CHANGE 9: always set
        allow_goal_modification=bool(payload.allow_goal_modification),
        created_by=hr.id,
    )
    db.add(r)
    db.flush()

    # CHANGE 9: audit deadline override if HR provided a different value.
    _maybe_audit_deadline_override(db, hr.id, "pms.mid_cycle", r.id, provided_dl, computed_dl)

    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    dl_label = final_deadline.strftime("%d %b %Y") if final_deadline else ""
    notify(
        db, recipient_id=a.employee_id,
        type_="pms_mid_cycle_created",
        title=f"Mid Cycle Review — {payload.cycle_period or 'Review Opened'}",
        body=(
            f"Phase: Mid Cycle Review | Action: Update KPI progress and submit"
            + (f" | Due: {dl_label}" if dl_label else "")
        ),
        reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
    )
    pms_email.email_mid_cycle_created(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        period=a.period,
        cycle_period=payload.cycle_period,
        due_date=final_deadline,  # CHANGE 9
    )
    _audit(db, hr.id, "pms.mid_cycle.create", r.id, None,
           {"assignment_id": a.id, "cycle_period": r.cycle_period})
    db.commit()
    db.refresh(r)
    return r


# ── Listing ───────────────────────────────────────────────────────────────────

def list_mid_cycle_reviews(
    db: Session, viewer: Employee, scope: str = "auto",
    assignment_id: Optional[int] = None,
) -> List[MidCycleReview]:
    q = db.query(MidCycleReview)
    if assignment_id:
        q = q.filter(MidCycleReview.assignment_id == assignment_id)

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
        q = q.filter(MidCycleReview.assignment_id.in_(mgr_assignment_ids))
    else:
        emp_assignment_ids = [
            a.id for a in db.query(GoalAssignment).filter(
                GoalAssignment.employee_id == viewer.id
            ).all()
        ]
        q = q.filter(MidCycleReview.assignment_id.in_(emp_assignment_ids))

    return q.order_by(MidCycleReview.created_at.desc()).all()


def get_mid_cycle_review(db: Session, viewer: Employee, review_id: int) -> MidCycleReview:
    return _get_review(db, viewer, review_id)


# ── Employee: save/submit progress ───────────────────────────────────────────

def employee_save_progress(
    db: Session, employee: Employee, review_id: int, payload, submit: bool = False
) -> MidCycleReview:
    """Employee updates KPI progress. submit=True advances status to submitted."""
    r = _get_review(db, employee, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if a.employee_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assignee can update progress.")
    _require_not_locked(r)
    if r.status not in (MCR_STATUS_DRAFT, MCR_STATUS_IN_PROGRESS):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot update progress from status '{r.status}'. Contact HR to reset.",
        )

    # Upsert KPI progress rows.
    existing_progress = {p.assigned_kpi_id: p for p in r.kpi_progress}
    for kpi_in in payload.kpi_progress or []:
        kpi = db.query(AssignedKPI).filter(AssignedKPI.id == kpi_in.assigned_kpi_id).first()
        if not kpi:
            continue
        if kpi_in.assigned_kpi_id in existing_progress:
            p = existing_progress[kpi_in.assigned_kpi_id]
        else:
            p = KPIProgress(review_id=r.id, assigned_kpi_id=kpi_in.assigned_kpi_id)
            db.add(p)
        p.current_value = kpi_in.current_value
        p.progress_percent = float(kpi_in.progress_percent or 0.0)
        p.employee_notes = kpi_in.employee_notes

    if payload.employee_comments is not None:
        r.employee_comments = payload.employee_comments

    if submit:
        r.status = MCR_STATUS_SUBMITTED
        r.submitted_at = datetime.utcnow()
        if a.manager_id:
            notify(
                db, recipient_id=a.manager_id,
                type_="pms_progress_submitted",
                title=f"{full_name(employee)} submitted mid-cycle progress",
                body="Review their progress and provide feedback.",
                reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
            )
        pms_email.email_progress_submitted(
            db,
            manager_id=a.manager_id,
            employee_name=full_name(employee),
            period=a.period,
            cycle_period=r.cycle_period,
        )
        _audit(db, employee.id, "pms.mid_cycle.submit", r.id, None, {"status": r.status})
    else:
        if r.status == MCR_STATUS_DRAFT:
            r.status = MCR_STATUS_IN_PROGRESS
        _audit(db, employee.id, "pms.mid_cycle.save_progress", r.id, None, {"status": r.status})

    db.commit()
    db.refresh(r)
    return r


# ── Employee: add / remove evidence ──────────────────────────────────────────

def add_evidence(db: Session, employee: Employee, review_id: int, payload) -> ReviewEvidence:
    r = _get_review(db, employee, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if a.employee_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assignee can add evidence.")
    _require_not_locked(r)
    if r.status not in (MCR_STATUS_DRAFT, MCR_STATUS_IN_PROGRESS, MCR_STATUS_SUBMITTED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot add evidence in status '{r.status}'.")

    ev = ReviewEvidence(
        review_id=r.id,
        assigned_kpi_id=payload.assigned_kpi_id,
        title=payload.title.strip(),
        description=payload.description,
        evidence_url=payload.evidence_url,
        uploaded_by=employee.id,
    )
    db.add(ev)
    _audit(db, employee.id, "pms.mid_cycle.add_evidence", r.id, None, {"title": ev.title})
    db.commit()
    db.refresh(ev)
    return ev


def delete_evidence(db: Session, employee: Employee, review_id: int, evidence_id: int) -> None:
    r = _get_review(db, employee, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    # Employee can delete own evidence; HR can delete any.
    if a.employee_id != employee.id and not is_hr(employee):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied.")
    _require_not_locked(r)
    ev = db.query(ReviewEvidence).filter(
        ReviewEvidence.id == evidence_id, ReviewEvidence.review_id == r.id
    ).first()
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found.")
    db.delete(ev)
    _audit(db, employee.id, "pms.mid_cycle.delete_evidence", r.id, None, {"evidence_id": evidence_id})
    db.commit()


# ── Manager: review ───────────────────────────────────────────────────────────

def manager_review_progress(
    db: Session, manager: Employee, review_id: int, payload
) -> MidCycleReview:
    r = _get_review(db, manager, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may review.")
    _require_not_locked(r)
    if r.status != MCR_STATUS_SUBMITTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Employee must submit progress before manager review (current: '{r.status}').",
        )

    if payload.manager_comments is not None:
        r.manager_comments = payload.manager_comments

    # Apply per-KPI manager notes.
    kpi_map = {p.assigned_kpi_id: p for p in r.kpi_progress}
    for note_entry in (payload.kpi_notes or []):
        kid = note_entry.get("assigned_kpi_id")
        notes = note_entry.get("manager_notes")
        if kid and kid in kpi_map:
            kpi_map[kid].manager_notes = notes

    r.status = MCR_STATUS_MGR_REVIEWED
    r.manager_reviewed_at = datetime.utcnow()
    r.manager_reviewed_by = manager.id

    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    notify(
        db, recipient_id=a.employee_id,
        type_="pms_manager_reviewed_progress",
        title="Manager reviewed your mid-cycle progress",
        body="Check their feedback in the Performance section.",
        reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
    )
    pms_email.email_manager_reviewed_mid_cycle(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        manager_name=full_name(manager),
        period=a.period,
        cycle_period=r.cycle_period,
    )
    _audit(db, manager.id, "pms.mid_cycle.manager_review", r.id, None, {"status": r.status})
    db.commit()
    db.refresh(r)
    return r


# ── Manager: save notes (no state transition) ─────────────────────────────────

def manager_save_notes(
    db: Session, manager: Employee, review_id: int, payload
) -> MidCycleReview:
    """Manager saves per-KPI notes/ratings and overall comment without advancing state.

    Allowed during 'submitted' (pre-review) and 'manager_reviewed' (pre-approval).
    The manager may:
      • Set manager_notes on any KPI.
      • Override the employee-submitted current_value and progress_percent per KPI.
    Creates a KPIProgress row for any KPI that has no employee entry yet, so
    manager edits are never silently discarded.

    Audit-logged as ``pms.mid_cycle.manager_save_notes`` with before/after snapshots
    of every field that changed.
    """
    r = _get_review(db, manager, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the reporting manager (or HR) may edit progress or notes.",
        )
    _require_not_locked(r)
    if r.status not in (MCR_STATUS_SUBMITTED, MCR_STATUS_MGR_REVIEWED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Progress/notes can only be edited when the review is 'submitted' or "
            f"'manager_reviewed' (current: '{r.status}').",
        )

    # Snapshot old state for audit.
    old_state: dict = {
        "manager_comments": r.manager_comments,
        "kpi_progress": [
            {
                "assigned_kpi_id": p.assigned_kpi_id,
                "current_value":   p.current_value,
                "progress_percent": p.progress_percent,
                "manager_notes":   p.manager_notes,
            }
            for p in r.kpi_progress
        ],
    }

    if payload.manager_comments is not None:
        r.manager_comments = payload.manager_comments

    # Apply per-KPI edits.
    # Each entry (ManagerKPIEditIn) may carry: manager_notes, current_value,
    # progress_percent. None means "leave unchanged"; explicit value means "overwrite".
    kpi_map = {p.assigned_kpi_id: p for p in r.kpi_progress}
    kpi_changes: list = []
    for entry in (payload.kpi_notes or []):
        kid = entry.assigned_kpi_id

        if kid in kpi_map:
            row = kpi_map[kid]
            changed: dict = {"assigned_kpi_id": kid}
            if entry.manager_notes is not None:
                changed["manager_notes"] = entry.manager_notes
                row.manager_notes = entry.manager_notes
            if entry.current_value is not None:
                changed["current_value"] = entry.current_value
                row.current_value = entry.current_value
            if entry.progress_percent is not None:
                changed["progress_percent"] = entry.progress_percent
                row.progress_percent = float(entry.progress_percent)
            kpi_changes.append(changed)
        else:
            # No employee progress row yet — create one to preserve manager edits.
            new_row = KPIProgress(
                review_id=r.id,
                assigned_kpi_id=kid,
                manager_notes=entry.manager_notes,
                current_value=entry.current_value,
                progress_percent=float(entry.progress_percent) if entry.progress_percent is not None else 0.0,
            )
            db.add(new_row)
            kpi_changes.append({
                "assigned_kpi_id": kid,
                "created": True,
                "manager_notes": entry.manager_notes,
                "current_value": entry.current_value,
                "progress_percent": entry.progress_percent,
            })

    new_state: dict = {
        "manager_comments": r.manager_comments,
        "kpi_changes": kpi_changes,
    }

    _audit(
        db, manager.id, "pms.mid_cycle.manager_save_notes", r.id,
        old_state, new_state,
    )
    db.commit()
    db.refresh(r)
    return r


# ── Manager: approve ──────────────────────────────────────────────────────────

def manager_approve_review(
    db: Session, manager: Employee, review_id: int, payload
) -> MidCycleReview:
    r = _get_review(db, manager, review_id)
    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may approve.")
    _require_not_locked(r)
    if r.status != MCR_STATUS_MGR_REVIEWED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Manager must review before approving (current: '{r.status}').",
        )
    if payload and payload.comment:
        r.manager_comments = payload.comment

    r.status = MCR_STATUS_MGR_APPROVED
    r.manager_approved_at = datetime.utcnow()
    r.manager_approved_by = manager.id

    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    hr_ids = _hr_recipient_ids(db)
    notify(
        db, recipient_id=a.employee_id,
        type_="pms_mid_cycle_manager_approved",
        title="Manager approved your mid-cycle review",
        body="Your review is now with HR.",
        reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
    )
    if hr_ids:
        notify_many(
            db, hr_ids,
            type_="pms_mid_cycle_manager_approved",
            title=f"Mid-cycle review approved for {full_name(emp)}",
            body="Open HR review queue.",
            reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
        )
    pms_email.email_mid_cycle_manager_approved(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        manager_name=full_name(manager),
        period=a.period,
        cycle_period=r.cycle_period,
        hr_ids=hr_ids,
    )
    _audit(db, manager.id, "pms.mid_cycle.manager_approve", r.id, None, {"status": r.status})
    db.commit()
    db.refresh(r)
    return r


# ── HR: review ────────────────────────────────────────────────────────────────

def hr_review_mid_cycle(
    db: Session, hr: Employee, review_id: int, payload
) -> MidCycleReview:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    r = _get_review(db, hr, review_id)
    _require_not_locked(r)
    if r.status != MCR_STATUS_MGR_APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Manager must approve before HR review (current: '{r.status}').",
        )
    if payload and payload.comment:
        r.hr_comments = payload.comment

    r.status = MCR_STATUS_HR_REVIEWED
    r.hr_reviewed_at = datetime.utcnow()
    r.hr_reviewed_by = hr.id

    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    notify(
        db, recipient_id=a.employee_id if a else 0,
        type_="pms_mid_cycle_hr_reviewed",
        title="HR reviewed your mid-cycle progress",
        body="Review will be locked shortly.",
        reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
    )
    pms_email.email_mid_cycle_hr_reviewed(
        db,
        employee_id=a.employee_id if a else 0,
        employee_name=full_name(emp),
        period=a.period if a else None,
        cycle_period=r.cycle_period,
    )
    _audit(db, hr.id, "pms.mid_cycle.hr_review", r.id, None, {"status": r.status})
    db.commit()
    db.refresh(r)
    return r


# ── HR: lock ──────────────────────────────────────────────────────────────────

def hr_lock_mid_cycle(
    db: Session, hr: Employee, review_id: int, payload,
    lock_type: str = LOCK_TYPE_MANUAL,
) -> MidCycleReview:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    r = _get_review(db, hr, review_id)
    if r.status not in (MCR_STATUS_HR_REVIEWED, MCR_STATUS_MGR_APPROVED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Review must be HR-reviewed or manager-approved to lock (current: '{r.status}').",
        )
    if payload and payload.comment:
        r.hr_comments = payload.comment

    r.status = MCR_STATUS_LOCKED
    r.locked_at = datetime.utcnow()
    r.locked_by = hr.id
    r.lock_type = lock_type

    a = db.query(GoalAssignment).filter(GoalAssignment.id == r.assignment_id).first()
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first() if a else None
    recipients = [a.employee_id] if a else []
    if a and a.manager_id:
        recipients.append(a.manager_id)
    notify_many(
        db, recipients,
        type_="pms_mid_cycle_locked",
        title="Mid-cycle review locked",
        body="Progress records are now finalised.",
        reference_table="pms_mid_cycle_reviews", reference_id=str(r.id),
    )
    pms_email.email_mid_cycle_locked(
        db,
        employee_id=a.employee_id if a else 0,
        employee_name=full_name(emp),
        manager_id=a.manager_id if a else None,
        period=a.period if a else None,
        cycle_period=r.cycle_period,
    )
    _audit(db, hr.id, "pms.mid_cycle.lock", r.id, None, {"status": r.status})
    db.commit()
    db.refresh(r)
    return r


# ── HR: unlock ────────────────────────────────────────────────────────────────

def hr_unlock_mid_cycle(
    db: Session, hr: Employee, review_id: int, payload
) -> MidCycleReview:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    r = _get_review(db, hr, review_id)
    if r.status != MCR_STATUS_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only locked reviews can be unlocked.")
    if getattr(r, 'lock_type', None) == LOCK_TYPE_AUTO:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This phase has been automatically locked after the deadline and can no longer be modified.",
        )
    if payload and payload.comment:
        r.hr_comments = payload.comment
    r.status = MCR_STATUS_HR_REVIEWED
    r.locked_at = None
    r.locked_by = None
    r.lock_type = None
    _audit(db, hr.id, "pms.mid_cycle.unlock", r.id, None, {"status": r.status})
    db.commit()
    db.refresh(r)
    return r
