"""PMS Phase 2 — Mid-Cycle Review API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee
from app.schemas.pms import (
    MidCycleCreateIn,
    ProgressSubmitIn,
    ManagerReviewIn,
    ManagerNotesIn,
    MidCycleActionIn,
    EvidenceIn,
    MidCycleReviewOut,
    EvidenceOut,
    BulkIdsIn,
    BulkMidCycleCreateIn,
    BulkActionOut,
)
from app.services import pms_phase2_service as svc

router = APIRouter(prefix="/pms/mid-cycle", tags=["pms-phase2"])


def _bulk_error_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc)


# ── HR: create a mid-cycle review ─────────────────────────────────────────────

@router.post("", response_model=MidCycleReviewOut, status_code=status.HTTP_201_CREATED)
def create_mid_cycle_review(
    payload: MidCycleCreateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.create_mid_cycle_review(db, me, payload)
    return svc.review_view(db, r)


# ── BULK Phase-2 actions (CHANGE 8) — must be before /{review_id} ─────────────
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
def bulk_create_mid_cycle(
    payload: BulkMidCycleCreateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for aid in payload.assignment_ids:
        sp = db.begin_nested()
        try:
            r = svc.create_mid_cycle_review(db, me, MidCycleCreateIn(
                assignment_id=aid,
                cycle_period=payload.cycle_period,
                deadline=payload.deadline,
                allow_goal_modification=payload.allow_goal_modification,
            ))
            # svc.create_mid_cycle_review() calls db.commit() internally, which
            # releases the savepoint.  No explicit sp.commit() needed.
            results.append({"id": r.id, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass  # savepoint already released by an internal commit
            results.append({"id": aid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()  # commit outer transaction (all released savepoints)
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.post("/bulk/hr-lock", response_model=BulkActionOut)
def bulk_lock_mid_cycle(
    payload: BulkIdsIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for rid in payload.ids:
        sp = db.begin_nested()
        try:
            svc.hr_lock_mid_cycle(db, me, rid, MidCycleActionIn(comment=payload.comment))
            results.append({"id": rid, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass
            results.append({"id": rid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


# ── List / Get ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[MidCycleReviewOut])
def list_mid_cycle_reviews(
    scope: str = Query("auto", pattern="^(auto|hr|manager|employee)$"),
    assignment_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.list_mid_cycle_reviews(db, me, scope=scope, assignment_id=assignment_id)
    if status_filter:
        rows = [r for r in rows if r.status == status_filter]
    return [svc.review_view(db, r) for r in rows]


@router.get("/{review_id}", response_model=MidCycleReviewOut)
def get_mid_cycle_review(
    review_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.get_mid_cycle_review(db, me, review_id)
    return svc.review_view(db, r)


# ── Employee: save progress (draft / in-progress) ─────────────────────────────

@router.put("/{review_id}/progress", response_model=MidCycleReviewOut)
def save_progress(
    review_id: int,
    payload: ProgressSubmitIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.employee_save_progress(db, me, review_id, payload, submit=False)
    return svc.review_view(db, r)


# ── Employee: submit progress (advances to 'submitted') ───────────────────────

@router.post("/{review_id}/submit", response_model=MidCycleReviewOut)
def submit_progress(
    review_id: int,
    payload: ProgressSubmitIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.employee_save_progress(db, me, review_id, payload, submit=True)
    return svc.review_view(db, r)


# ── Manager: save notes (no state transition) ─────────────────────────────────

@router.put("/{review_id}/manager-notes", response_model=MidCycleReviewOut)
def manager_save_notes(
    review_id: int,
    payload: ManagerNotesIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Manager saves draft KPI notes and overall comment without advancing the state machine.

    Allowed when review status is ``submitted`` or ``manager_reviewed``.
    After ``manager_approved`` the review is read-only for the manager.
    """
    r = svc.manager_save_notes(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── Manager: review ───────────────────────────────────────────────────────────

@router.post("/{review_id}/manager-review", response_model=MidCycleReviewOut)
def manager_review(
    review_id: int,
    payload: ManagerReviewIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.manager_review_progress(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── Manager: approve ──────────────────────────────────────────────────────────

@router.post("/{review_id}/manager-approve", response_model=MidCycleReviewOut)
def manager_approve(
    review_id: int,
    payload: MidCycleActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.manager_approve_review(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── HR: review ────────────────────────────────────────────────────────────────

@router.post("/{review_id}/hr-review", response_model=MidCycleReviewOut)
def hr_review(
    review_id: int,
    payload: MidCycleActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.hr_review_mid_cycle(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── HR: lock ──────────────────────────────────────────────────────────────────

@router.post("/{review_id}/lock", response_model=MidCycleReviewOut)
def lock_mid_cycle(
    review_id: int,
    payload: MidCycleActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.hr_lock_mid_cycle(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── HR: unlock ────────────────────────────────────────────────────────────────

@router.post("/{review_id}/unlock", response_model=MidCycleReviewOut)
def unlock_mid_cycle(
    review_id: int,
    payload: MidCycleActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    r = svc.hr_unlock_mid_cycle(db, me, review_id, payload)
    return svc.review_view(db, r)


# ── Evidence ──────────────────────────────────────────────────────────────────

@router.post("/{review_id}/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def add_evidence(
    review_id: int,
    payload: EvidenceIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    ev = svc.add_evidence(db, me, review_id, payload)
    return {
        "id": ev.id, "review_id": ev.review_id, "assigned_kpi_id": ev.assigned_kpi_id,
        "title": ev.title, "description": ev.description, "evidence_url": ev.evidence_url,
        "uploaded_by": ev.uploaded_by, "created_at": ev.created_at,
    }


@router.delete("/{review_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    review_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    svc.delete_evidence(db, me, review_id, evidence_id)
    return None
