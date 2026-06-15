"""PMS Phase 3 — End Cycle Assessment API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee
from app.schemas.pms import (
    ECACreateIn, SelfAssessIn, ManagerAssessIn, ECAActionIn, HRNotesIn,
    EndCycleAssessmentOut,
    BulkIdsIn, BulkECACreateIn, BulkActionOut,
)
from app.services import pms_phase3_service as svc

router = APIRouter(prefix="/pms/end-cycle", tags=["pms-phase3"])


def _bulk_error_reason(exc: Exception) -> str:
    """Return a plain-string reason from any exception, safely."""
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc)


# ── BULK Phase-3 actions (CHANGE 8) — must be before /{eca_id} ─────────────────
#
# Session isolation strategy: each item is wrapped in a DB savepoint
# (db.begin_nested()).  On success the savepoint is released by the service's
# own db.commit(); on failure we roll back only that savepoint, leaving the
# session and all previously-successful items unaffected.  The outer
# transaction is committed once after the loop.
#
# This replaces the previous db.rollback() pattern, which reset the entire
# session identity map and caused DetachedInstanceError on subsequent items.


@router.post("/bulk/create", response_model=BulkActionOut, status_code=status.HTTP_201_CREATED)
def bulk_create_assessments(
    payload: BulkECACreateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for aid in payload.assignment_ids:
        sp = db.begin_nested()
        try:
            eca = svc.create_assessment(db, me, ECACreateIn(
                assignment_id=aid,
                cycle_period=payload.cycle_period,
                deadline=payload.deadline,
            ))
            # svc.create_assessment() calls db.commit() internally, which
            # releases the savepoint.  No explicit sp.commit() needed.
            results.append({"id": eca.id, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass  # savepoint already released by an internal commit
            results.append({"id": aid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()  # commit outer transaction (all released savepoints)
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.post("/bulk/lock", response_model=BulkActionOut)
def bulk_lock_assessments(
    payload: BulkIdsIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for eca_id in payload.ids:
        sp = db.begin_nested()
        try:
            svc.hr_lock(db, me, eca_id, ECAActionIn(comment=payload.comment))
            results.append({"id": eca_id, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass
            results.append({"id": eca_id, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.post("", response_model=EndCycleAssessmentOut, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: ECACreateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.create_assessment(db, me, payload)
    return svc.assessment_view(db, eca)


@router.get("", response_model=List[EndCycleAssessmentOut])
def list_assessments(
    scope: str = Query("auto", pattern="^(auto|hr|manager|employee)$"),
    assignment_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.list_assessments(db, me, scope=scope, assignment_id=assignment_id)
    if status_filter:
        rows = [r for r in rows if r.status == status_filter]
    return [svc.assessment_view(db, r) for r in rows]


@router.get("/{eca_id}", response_model=EndCycleAssessmentOut)
def get_assessment(
    eca_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.get_assessment(db, me, eca_id)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/self-assess", response_model=EndCycleAssessmentOut)
def self_assess(
    eca_id: int,
    payload: SelfAssessIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.employee_self_assess(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/manager-assess", response_model=EndCycleAssessmentOut)
def manager_assess(
    eca_id: int,
    payload: ManagerAssessIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.manager_assess(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/submit-to-hr", response_model=EndCycleAssessmentOut)
def submit_to_hr(
    eca_id: int,
    payload: ECAActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.submit_to_hr(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/hr-receive", response_model=EndCycleAssessmentOut)
def hr_receive(
    eca_id: int,
    payload: ECAActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.hr_receive(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/lock", response_model=EndCycleAssessmentOut)
def lock_assessment(
    eca_id: int,
    payload: ECAActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.hr_lock(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.patch("/{eca_id}/hr-notes", response_model=EndCycleAssessmentOut)
def update_hr_notes(
    eca_id: int,
    payload: HRNotesIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """HR saves notes without advancing the state machine. Available until the assessment is locked."""
    eca = svc.save_hr_notes(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)


@router.post("/{eca_id}/unlock", response_model=EndCycleAssessmentOut)
def unlock_assessment(
    eca_id: int,
    payload: ECAActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    eca = svc.hr_unlock(db, me, eca_id, payload)
    return svc.assessment_view(db, eca)
