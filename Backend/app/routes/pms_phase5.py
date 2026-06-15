"""PMS Phase 5 — Compensation & Communication API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee
from app.schemas.pms import (
    CompRevisionGenerateIn, NormActionIn,
    CompRevisionOut, PMSCycleOut,
)
from app.services import pms_phase5_service as svc

router = APIRouter(prefix="/pms/compensation", tags=["pms-phase5"])


@router.post("/{session_id}/generate", response_model=List[CompRevisionOut],
             status_code=status.HTTP_201_CREATED)
def generate_revisions(
    session_id: int,
    payload: CompRevisionGenerateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    revisions = svc.generate_revisions(db, me, session_id, payload)
    return [svc.revision_view(db, r) for r in revisions]


@router.get("", response_model=List[CompRevisionOut])
def list_revisions(
    session_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.list_revisions(db, me, session_id=session_id)
    return [svc.revision_view(db, r) for r in rows]


@router.get("/{revision_id}", response_model=CompRevisionOut)
def get_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rev = svc.get_revision(db, me, revision_id)
    return svc.revision_view(db, rev)


@router.post("/{revision_id}/acknowledge", response_model=CompRevisionOut)
def acknowledge(
    revision_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rev = svc.employee_acknowledge(db, me, revision_id)
    return svc.revision_view(db, rev)


@router.post("/{session_id}/archive", response_model=PMSCycleOut,
             status_code=status.HTTP_201_CREATED)
def archive_cycle(
    session_id: int,
    payload: NormActionIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    cycle = svc.archive_cycle(db, me, session_id, payload)
    return {
        "id": cycle.id,
        "period": cycle.period,
        "normalization_session_id": cycle.normalization_session_id,
        "archived_at": cycle.archived_at,
        "notes": cycle.notes,
        "created_at": cycle.created_at,
    }
