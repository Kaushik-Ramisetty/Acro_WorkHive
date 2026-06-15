"""PMS Phase 4 — HR Normalization API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee
from app.schemas.pms import (
    NormSessionCreateIn, NormSessionUpdateIn, NormRecordUpdateIn, NormActionIn,
    NormSessionOut, NormRecordOut, EligibleECAOut,
)
from app.services import pms_phase4_service as svc

router = APIRouter(prefix="/pms/normalization", tags=["pms-phase4"])


# ── Eligible employees — must be declared BEFORE /{session_id} routes ─────────
# (FastAPI resolves path params left-to-right; a literal segment beats a param)

@router.get("/eligible-employees", response_model=List[EligibleECAOut])
def list_eligible_employees(
    period: Optional[str] = Query(None, description="Filter by period; omit to return all locked ECAs"),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """
    Return all locked end-cycle assessments available for normalization.
    Each row includes employee info, ratings, the effective period, and whether
    it is already in an active normalization session (in_session_id non-null).
    HR-only endpoint.
    """
    return svc.list_eligible_ecas(db, me, period=period)


@router.get("/eligible-periods", response_model=List[str])
def list_eligible_periods(
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """
    Return a sorted list of distinct period labels from all locked ECAs.
    Used to populate the period dropdown in the create-session form.
    HR-only endpoint.
    """
    return svc.distinct_eligible_periods(db, me)


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=NormSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: NormSessionCreateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.create_session(db, me, payload)
    return svc.session_view(db, sess)


@router.get("", response_model=List[NormSessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.list_sessions(db, me)
    return [svc.session_view(db, s) for s in rows]


@router.get("/{session_id}", response_model=NormSessionOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.get_session(db, me, session_id)
    return svc.session_view(db, sess)


@router.put("/{session_id}", response_model=NormSessionOut)
def update_session(
    session_id: int,
    payload: NormSessionUpdateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.update_session(db, me, session_id, payload)
    return svc.session_view(db, sess)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    svc.delete_session(db, me, session_id)
    return None


# ── Records ───────────────────────────────────────────────────────────────────

@router.put("/{session_id}/records/{record_id}", response_model=NormRecordOut)
def update_record(
    session_id: int,
    record_id: int,
    payload: NormRecordUpdateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rec = svc.update_record(db, me, session_id, record_id, payload)
    full = svc.session_view(db, rec.session)
    matched = next((r for r in full["records"] if r["id"] == record_id), None)
    return matched or {}


@router.post("/{session_id}/add-records", response_model=NormSessionOut)
def add_records(
    session_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """
    Re-scan locked ECAs for the session's period and add any newly-locked or
    previously-missed employees.  Idempotent — safe to call multiple times.
    """
    sess = svc.add_records_to_session(db, me, session_id)
    return svc.session_view(db, sess)


# ── Workflow transitions ───────────────────────────────────────────────────────

@router.post("/{session_id}/normalize", response_model=NormSessionOut)
def normalize(
    session_id: int,
    payload: NormActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.normalize_session(db, me, session_id, payload)
    return svc.session_view(db, sess)


@router.post("/{session_id}/freeze", response_model=NormSessionOut)
def freeze(
    session_id: int,
    payload: NormActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.freeze_session(db, me, session_id, payload)
    return svc.session_view(db, sess)


@router.post("/{session_id}/generate-hike", response_model=NormSessionOut)
def generate_hike(
    session_id: int,
    payload: NormActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.generate_hike(db, me, session_id, payload)
    return svc.session_view(db, sess)


@router.post("/{session_id}/approve-hike", response_model=NormSessionOut)
def approve_hike(
    session_id: int,
    payload: NormActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    sess = svc.approve_hike(db, me, session_id, payload)
    return svc.session_view(db, sess)
