"""
services/candidate_service.py — CRUD for Candidate records.

Enforces the state-machine transition rules defined in api/models.py.
"""

import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import Candidate, CandidateStatus, CANDIDATE_TRANSITIONS
from api.Onboarding_Model.schemas import CandidateCreate, CandidateUpdate
from utils.id_generator import generate_candidate_ref

logger = logging.getLogger(__name__)


# ─── helpers ──────────────────────────────────────────────────────────────────

def get_candidate_or_404(candidate_id: int, db: Session) -> Candidate:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return candidate


def assert_transition(candidate: Candidate, target_status: str) -> None:
    """
    Validate that moving `candidate` to `target_status` is an allowed transition.
    Raises HTTP 409 if not.
    """
    allowed = CANDIDATE_TRANSITIONS.get(candidate.status, [])
    if target_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition '{candidate.status}' → '{target_status}'. "
                f"Allowed next states: {allowed or ['none']}"
            ),
        )


def advance_status(candidate: Candidate, new_status: str, db: Session) -> Candidate:
    assert_transition(candidate, new_status)
    candidate.status = new_status
    db.commit()
    db.refresh(candidate)
    logger.info("Candidate %s → status %s", candidate.id, new_status)
    return candidate


# ─── service functions ────────────────────────────────────────────────────────

def create_candidate(data: CandidateCreate, db: Session) -> Candidate:
    # Case-insensitive duplicate check — emails are not case-sensitive in
    # practice, and we don't want "Foo@x.com" and "foo@x.com" to be two
    # separate candidate rows.
    from sqlalchemy import func as _func
    email_lower = (data.email or "").strip().lower()
    if db.query(Candidate).filter(_func.lower(Candidate.email) == email_lower).first():
        raise HTTPException(status_code=400, detail="A candidate with this email already exists.")

    ref = generate_candidate_ref()
    # Regenerate until unique (extremely unlikely collision)
    while db.query(Candidate).filter(Candidate.candidate_ref == ref).first():
        ref = generate_candidate_ref()

    full_name = f"{data.first_name.strip()} {data.last_name.strip()}".strip()

    candidate = Candidate(
        candidate_ref=ref,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        name=full_name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        department=data.department,
        ctc=data.ctc,
        expected_joining_date=data.expected_joining_date,
        status=CandidateStatus.CREATED.value,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    logger.info("Created candidate %s (ref=%s)", candidate.id, ref)
    return candidate


def list_candidates(
    db: Session,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Candidate]:
    q = db.query(Candidate)
    if status:
        q = q.filter(Candidate.status == status)
    return q.order_by(Candidate.id.desc()).offset(skip).limit(limit).all()


def get_candidate(candidate_id: int, db: Session) -> Candidate:
    return get_candidate_or_404(candidate_id, db)


def update_candidate(candidate_id: int, data: CandidateUpdate, db: Session) -> Candidate:
    candidate = get_candidate_or_404(candidate_id, db)
    if data.first_name is not None:
        candidate.first_name = data.first_name.strip()
    if data.last_name is not None:
        candidate.last_name = data.last_name.strip()
    # Keep the denormalised `name` column in sync
    if data.first_name is not None or data.last_name is not None:
        fn = candidate.first_name or ""
        ln = candidate.last_name or ""
        candidate.name = f"{fn} {ln}".strip()
    if data.phone is not None:
        candidate.phone = data.phone
    if data.role is not None:
        candidate.role = data.role
    if data.department is not None:
        candidate.department = data.department
    if data.ctc is not None:
        candidate.ctc = data.ctc
    if data.expected_joining_date is not None:
        candidate.expected_joining_date = data.expected_joining_date
    db.commit()
    db.refresh(candidate)
    return candidate
