"""PMS Phase 5 — Compensation & Communication service.

HR generates compensation revisions from approved hike recommendations,
applies salary changes via the existing payroll engine, employees acknowledge,
and HR archives the cycle.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Employee
from app.models.payroll import SalaryStructure
from app.models.pms import (
    NormalizationSession, NormalizationRecord, CompensationRevision, PMSCycle,
    NORM_STATUS_HIKE_APPROVED,
)
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many
import app.services.pms_email_service as pms_email
from app.services.pms_service import is_hr, full_name, _hr_recipient_ids
from app.services import payroll_service


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit(db: Session, actor_id: int, action: str, target_id: int,
           target_table: str, old: dict | None, new: dict | None) -> None:
    try:
        write_audit(
            db, actor_id=actor_id, action=action,
            target_table=target_table, target_id=str(target_id),
            old_value=old, new_value=new,
        )
    except Exception:
        pass


def _require_hr(actor: Employee) -> None:
    if not is_hr(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")


# ── View helper ───────────────────────────────────────────────────────────────

def revision_view(db: Session, rev: CompensationRevision) -> dict:
    # Use normalization_record.employee_id as the authoritative source.  If
    # the FK on CompensationRevision was ever mis-set, this cross-reference
    # ensures the correct employee name is always displayed.
    authoritative_employee_id = rev.employee_id
    norm_rec = db.query(NormalizationRecord).filter(
        NormalizationRecord.id == rev.normalization_record_id
    ).first()
    if norm_rec and norm_rec.employee_id:
        authoritative_employee_id = norm_rec.employee_id
        if rev.employee_id != norm_rec.employee_id:
            # Silently correct the denormalised employee_id in place.
            rev.employee_id = norm_rec.employee_id
            try:
                db.commit()
            except Exception:
                db.rollback()

    emp = db.query(Employee).filter(Employee.id == authoritative_employee_id).first()
    return {
        "id": rev.id,
        "normalization_record_id": rev.normalization_record_id,
        "employee_id": rev.employee_id,
        "employee_name": full_name(emp),
        "old_ctc": rev.old_ctc,
        "new_ctc": rev.new_ctc,
        "hike_percent": rev.hike_percent,
        "effective_from": rev.effective_from,
        "letter_generated_at": rev.letter_generated_at,
        "employee_acknowledged_at": rev.employee_acknowledged_at,
        "created_at": rev.created_at,
    }


# ── HR: generate compensation revisions ──────────────────────────────────────

def generate_revisions(
    db: Session, hr: Employee, session_id: int, payload
) -> List[CompensationRevision]:
    """
    For each NormalizationRecord in the approved session:
      1. Compute new CTC from current CTC + hike_percent.
      2. Call payroll_service.upsert_salary_structure_from_ctc() to apply salary.
      3. Create / update a CompensationRevision record.
      4. Mark letter_generated_at = now.
    """
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Normalization session not found.")
    if sess.status != NORM_STATUS_HIKE_APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Hikes must be approved before generating compensation revisions.",
        )

    # Parse effective_from.
    try:
        eff_from = date.fromisoformat(payload.effective_from)
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "effective_from must be a valid ISO date string (e.g. 2026-07-01).")

    now = datetime.utcnow()
    created: List[CompensationRevision] = []

    for rec in sess.records:
        if not rec.hike_percent:
            continue  # Skip records with no hike.

        # Get current active salary structure for the employee.
        current_struct: SalaryStructure | None = (
            db.query(SalaryStructure)
            .filter(
                SalaryStructure.employee_id == rec.employee_id,
                SalaryStructure.is_active.is_(True),
            )
            .order_by(SalaryStructure.effective_from.desc())
            .first()
        )
        old_ctc = float(current_struct.annual_ctc or 0.0) if current_struct else 0.0
        new_ctc = round(old_ctc * (1 + rec.hike_percent / 100), 2)

        # Check for existing revision (idempotent).
        existing_rev = db.query(CompensationRevision).filter(
            CompensationRevision.normalization_record_id == rec.id
        ).first()

        if existing_rev:
            rev = existing_rev
            # Always sync employee_id from the normalization record — source of truth.
            rev.employee_id = rec.employee_id
        else:
            rev = CompensationRevision(
                normalization_record_id=rec.id,
                employee_id=rec.employee_id,
            )
            db.add(rev)

        rev.old_ctc = old_ctc
        rev.new_ctc = new_ctc
        rev.hike_percent = rec.hike_percent
        rev.effective_from = datetime.combine(eff_from, datetime.min.time())
        rev.letter_generated_at = now
        rev.letter_generated_by = hr.id

        # Apply salary revision via payroll engine (non-fatal — log if it fails).
        if new_ctc > 0:
            try:
                emp_obj = db.query(Employee).filter(Employee.id == rec.employee_id).first()
                payroll_service.upsert_salary_structure_from_ctc(
                    db=db,
                    employee_id=rec.employee_id,
                    annual_ctc=new_ctc,
                    actor=hr,
                    effective_from=eff_from,
                    revision_reason=f"PMS {sess.period} annual hike {rec.hike_percent:.1f}%",
                )
            except Exception as exc:
                import logging
                logging.getLogger("hrms.pms_phase5").warning(
                    "Salary upsert failed for employee #%d: %s", rec.employee_id, exc
                )

        db.flush()

        # Notify employee.
        emp = db.query(Employee).filter(Employee.id == rec.employee_id).first()
        notify(
            db, recipient_id=rec.employee_id,
            type_="pms_revision_letter_ready",
            title="Your compensation revision letter is ready",
            body="Log in to Performance → Compensation to view and acknowledge your revised CTC.",
            reference_table="pms_compensation_revisions", reference_id=str(rev.id),
        )
        pms_email.email_revision_letter_ready(
            db,
            employee_id=rec.employee_id,
            employee_name=full_name(emp),
            period=sess.period,
            old_ctc=old_ctc,
            new_ctc=new_ctc,
            hike_percent=rec.hike_percent,
            effective_from=eff_from.isoformat(),
        )

        _audit(db, hr.id, "pms.comp.generate_revision", rev.id,
               "pms_compensation_revisions", None, {"employee_id": rec.employee_id, "new_ctc": new_ctc})
        created.append(rev)

    db.commit()
    for rev in created:
        db.refresh(rev)
    return created


# ── Listing ───────────────────────────────────────────────────────────────────

def list_revisions(
    db: Session, viewer: Employee, session_id: Optional[int] = None
) -> List[CompensationRevision]:
    q = db.query(CompensationRevision)
    if session_id:
        record_ids = [
            r.id for r in db.query(NormalizationRecord).filter(
                NormalizationRecord.session_id == session_id
            ).all()
        ]
        q = q.filter(CompensationRevision.normalization_record_id.in_(record_ids))

    # Employees can only see their own revisions.
    if not is_hr(viewer):
        q = q.filter(CompensationRevision.employee_id == viewer.id)

    return q.order_by(CompensationRevision.created_at.desc()).all()


def get_revision(db: Session, viewer: Employee, revision_id: int) -> CompensationRevision:
    rev = db.query(CompensationRevision).filter(CompensationRevision.id == revision_id).first()
    if not rev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revision not found.")
    if not is_hr(viewer) and rev.employee_id != viewer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied.")
    return rev


# ── Employee: acknowledge revision ────────────────────────────────────────────

def employee_acknowledge(
    db: Session, employee: Employee, revision_id: int
) -> CompensationRevision:
    rev = get_revision(db, employee, revision_id)
    if rev.employee_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the employee can acknowledge their revision.")
    if rev.employee_acknowledged_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Revision already acknowledged.")
    if not rev.letter_generated_at:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Revision letter has not been generated yet.")

    rev.employee_acknowledged_at = datetime.utcnow()

    # Notify HR pool.
    hr_ids = _hr_recipient_ids(db)
    emp = db.query(Employee).filter(Employee.id == employee.id).first()
    if hr_ids:
        notify_many(
            db, hr_ids,
            type_="pms_revision_acknowledged",
            title=f"{full_name(emp)} acknowledged their compensation revision",
            body="Employee has accepted the revised CTC.",
            reference_table="pms_compensation_revisions", reference_id=str(rev.id),
        )
    pms_email.email_revision_acknowledged(
        db,
        employee_name=full_name(emp),
        hr_ids=hr_ids,
    )
    _audit(db, employee.id, "pms.comp.acknowledge", rev.id,
           "pms_compensation_revisions", None, {"acknowledged_at": str(rev.employee_acknowledged_at)})
    db.commit()
    db.refresh(rev)
    return rev


# ── HR: archive cycle ─────────────────────────────────────────────────────────

def archive_cycle(
    db: Session, hr: Employee, session_id: int, payload
) -> PMSCycle:
    _require_hr(hr)
    sess = db.query(NormalizationSession).filter(NormalizationSession.id == session_id).first()
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Normalization session not found.")
    if sess.status != NORM_STATUS_HIKE_APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Session must be hike-approved before archiving the cycle.")

    # Idempotent — return existing cycle record if already archived.
    existing = db.query(PMSCycle).filter(
        PMSCycle.normalization_session_id == session_id
    ).first()
    if existing:
        return existing

    cycle = PMSCycle(
        period=sess.period,
        normalization_session_id=sess.id,
        archived_at=datetime.utcnow(),
        archived_by=hr.id,
        notes=payload.notes if payload else None,
    )
    db.add(cycle)

    # Notify HR team.
    hr_ids = _hr_recipient_ids(db)
    if hr_ids:
        notify_many(
            db, hr_ids,
            type_="pms_cycle_archived",
            title=f"PMS cycle {sess.period} archived",
            body="The full performance management cycle has been archived.",
            reference_table="pms_cycles", reference_id=None,
        )
    pms_email.email_cycle_archived(db, period=sess.period, hr_ids=hr_ids)

    _audit(db, hr.id, "pms.comp.archive_cycle", sess.id,
           "pms_normalization_sessions", None, {"period": sess.period})
    db.commit()
    db.refresh(cycle)
    return cycle
