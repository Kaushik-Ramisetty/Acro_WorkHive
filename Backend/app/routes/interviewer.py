"""
Interviewer routes — prefix /interviewer

All endpoints require a valid JWT. RBAC is wide enough (employee/manager/admin)
because the data is already scoped to the logged-in user's employee_code — only
rounds/feedback belonging to that user are returned.

Slot-adding reuses the existing /recruiter/interviews/{round_id}/slots route
so we delegate to the same recruiter_service function to avoid duplicating logic.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee
from app.schemas.interviewer import FeedbackSubmit
from app.services import interviewer_service as svc

router = APIRouter(prefix="/interviewer", tags=["interviewer"])
ROLES = ("employee", "manager", "admin")


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Stat cards for the interviewer dashboard — scoped to current user."""
    return svc.get_interviewer_stats(db, current.employee_code)


# ── Assignments ───────────────────────────────────────────────────────────────

@router.get("/assignments")
def get_assignments(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """All interview rounds assigned to the logged-in interviewer."""
    return svc.get_interviewer_assignments(db, current.employee_code)


# ── Upcoming ──────────────────────────────────────────────────────────────────

@router.get("/upcoming")
def get_upcoming(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Upcoming scheduled interviews (today onwards) for the logged-in interviewer."""
    return svc.get_interviewer_upcoming(db, current.employee_code)


# ── Calendar ──────────────────────────────────────────────────────────────────

@router.get("/calendar")
def get_calendar(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Calendar events for the logged-in interviewer (rounds with a scheduled date)."""
    return svc.get_interviewer_calendar(db, current.employee_code)


# ── Feedback history ──────────────────────────────────────────────────────────

@router.get("/feedback-history")
def get_feedback_history(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """All feedback records submitted by the logged-in interviewer."""
    return svc.get_interviewer_feedback_history(db, current.employee_code)


# ── Slot submission ───────────────────────────────────────────────────────────

@router.post("/rounds/{round_id}/slots")
def add_slots(
    round_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """
    Interviewer adds available time slots for a round.
    payload: { "slots": [{"slot_date": "2026-06-01", "slot_time": "14:00"}, ...] }

    Delegates to recruiter_service.add_interview_slots to stay DRY.
    """
    from app.services import recruiter_service as rec_svc

    slots = (payload or {}).get("slots", [])
    if not slots:
        raise HTTPException(status_code=422, detail="slots array is required")
    result = rec_svc.add_interview_slots(db, round_id, slots, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Feedback submission ───────────────────────────────────────────────────────

@router.post("/rounds/{round_id}/feedback")
def submit_feedback(
    round_id: int,
    payload: FeedbackSubmit,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Submit (or update) interview feedback for a round. Marks round as completed."""
    result = svc.submit_feedback(db, round_id, payload, current.employee_code)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
