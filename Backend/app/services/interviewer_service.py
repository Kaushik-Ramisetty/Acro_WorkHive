"""
Interviewer service.

All queries are filtered by the logged-in employee's employee_code so that an
interviewer sees ONLY their own assigned rounds, slots, and feedback.

InterviewSlot.round_id is the integer PK of interview_rounds.id (r.id).
Legacy rows written before this fix used round_order text (e.g. "ROUN1"); all
read queries include a backward-compat OR clause to surface those rows too.

InterviewFeedback.round_id is also the integer PK of interview_rounds.id.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.recruitment import (
    CandidatePipeline,
    InterviewFeedback,
    InterviewRound,
    InterviewSlot,
    JobRequirement,
    RecruitmentCandidate,
)
from app.schemas.interviewer import (
    CalendarEvent,
    FeedbackHistoryItem,
    FeedbackSubmit,
    InterviewerAssignment,
    InterviewerStats,
    PreviousFeedbackOut,
    SlotOut,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_skills(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return []


def _exp_str(years) -> Optional[str]:
    if years is None:
        return None
    return f"{int(years)} yrs" if years == int(years) else f"{years} yrs"


def _initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    return name[:2].upper() if len(name) >= 2 else (name.upper() or "??")


def _format_time(time_str: Optional[str]) -> Optional[str]:
    """Convert "14:00" → "2:00 PM"."""
    if not time_str:
        return None
    try:
        t = datetime.strptime(time_str[:5], "%H:%M")
        return t.strftime("%I:%M %p").lstrip("0") or t.strftime("%I:%M %p")
    except Exception:
        return time_str


def _format_date_display(date_str: Optional[str]) -> Optional[str]:
    """Convert "2026-05-21" → "21 May 2026"."""
    if not date_str:
        return None
    try:
        d = date.fromisoformat(date_str)
        return f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        return date_str


def _get_slots(round_id: int, round_order: Optional[str], db: Session) -> list[SlotOut]:
    """Fetch slots for a round by its integer PK."""
    filter_clauses = [InterviewSlot.round_id == round_id]
    if round_order:
        filter_clauses.append(InterviewSlot.round_id == round_order)

    slots = (
        db.query(InterviewSlot)
        .filter(or_(*filter_clauses))
        .order_by(InterviewSlot.slot_date, InterviewSlot.slot_time)
        .all()
    )
    return [
        SlotOut(
            id=s.id,
            slot_date=s.slot_date,
            slot_time=s.slot_time,
            is_selected=bool(s.is_selected),
        )
        for s in slots
    ]


def _round_status(r: InterviewRound, db: Session) -> str:
    """Derive a human-readable status for the interviewer frontend."""
    if r.status == "completed":
        return "Completed"
    if r.status in ("scheduled", "in_progress"):
        return "Scheduled"
    filter_clauses = [InterviewSlot.round_id == r.id]
    if r.round_order:
        filter_clauses.append(InterviewSlot.round_id == r.round_order)
    slot_exists = (
        db.query(InterviewSlot)
        .filter(or_(*filter_clauses))
        .first()
    )
    if slot_exists:
        if r.email_sent_at:
            return "Candidate Notified"
        return "Slots Added"
    return "Awaiting Slot Selection"


def _previous_feedback(pipeline_id: int, current_round_id: int, db: Session) -> list[PreviousFeedbackOut]:
    """Feedback from other completed rounds in the same pipeline."""
    other_rounds = (
        db.query(InterviewRound)
        .filter(
            InterviewRound.pipeline_id == pipeline_id,
            InterviewRound.id != current_round_id,
            InterviewRound.status == "completed",
        )
        .all()
    )
    result = []
    for r in other_rounds:
        fb = (
            db.query(InterviewFeedback)
            .filter(InterviewFeedback.round_id == r.id)
            .first()
        )
        if fb:
            date_str = fb.submitted_at.strftime("%d %b %Y") if fb.submitted_at else ""
            result.append(
                PreviousFeedbackOut(
                    round=r.round_name,
                    date=date_str,
                    recommendation=fb.recommendation,
                    notes=fb.notes,
                )
            )
    return result


def _build_assignment(r: InterviewRound, db: Session) -> Optional[InterviewerAssignment]:
    """Build a full InterviewerAssignment from an InterviewRound row."""
    p = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
    if not p:
        return None
    cand = (
        db.query(RecruitmentCandidate)
        .filter(RecruitmentCandidate.candidate_id == p.candidate_id)
        .first()
    )
    if not cand:
        return None
    req = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

    full_name = f"{cand.first_name} {cand.last_name or ''}".strip()

    return InterviewerAssignment(
        round_id=r.id,
        pipeline_id=p.id,
        candidate_id=cand.candidate_id,
        candidate_name=full_name,
        initials=_initials(full_name),
        role=cand.current_job_title,
        req_id=req.req_id if req else "",
        req_db_id=p.requirement_id,
        round=r.round_name,
        exp=_exp_str(cand.experience_years),
        company=cand.current_employer,
        ctc=cand.current_ctc,
        exp_ctc=cand.expected_ctc,
        notice=cand.notice_period,
        source=cand.source,
        skills=_parse_skills(cand.skills),
        status=_round_status(r, db),
        date=_format_date_display(r.interview_date),
        time=r.interview_time,
        teams_link=r.meeting_link,
        manager_remark=p.manager_remark,
        recruiter_notes=cand.recruiter_notes,
        resume_url=cand.resume_url,
        previous_feedback=_previous_feedback(p.id, r.id, db),
        slots=_get_slots(r.id, r.round_order, db),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_interviewer_stats(db: Session, employee_code: str) -> InterviewerStats:
    today_str = date.today().isoformat()

    all_rounds = (
        db.query(InterviewRound)
        .filter(InterviewRound.interviewer_id == employee_code)
        .all()
    )
    assigned = len(all_rounds)

    today_count = (
        db.query(InterviewRound)
        .filter(
            InterviewRound.interviewer_id == employee_code,
            InterviewRound.interview_date == today_str,
            InterviewRound.status.in_(["scheduled", "in_progress"]),
        )
        .count()
    )

    scheduled_ids = [
        r.id
        for r in all_rounds
        if r.status in ("scheduled", "in_progress")
        and r.interview_date
        and r.interview_date <= today_str
    ]
    if scheduled_ids:
        submitted_ids = {
            fb.round_id
            for fb in db.query(InterviewFeedback)
            .filter(
                InterviewFeedback.round_id.in_(scheduled_ids),
                InterviewFeedback.submitted_at.isnot(None),
            )
            .all()
        }
        pending_feedback = len([rid for rid in scheduled_ids if rid not in submitted_ids])
    else:
        pending_feedback = 0

    completed = (
        db.query(InterviewFeedback)
        .join(InterviewRound, InterviewRound.id == InterviewFeedback.round_id)
        .filter(
            InterviewFeedback.interviewer_id == employee_code,
            InterviewFeedback.submitted_at.isnot(None),
            InterviewRound.interviewer_id == employee_code,
            InterviewRound.status == "completed",
        )
        .count()
    )

    return InterviewerStats(
        assigned=assigned,
        today=today_count,
        pending_feedback=pending_feedback,
        completed=completed,
    )


def get_interviewer_assignments(db: Session, employee_code: str) -> list[InterviewerAssignment]:
    rounds = (
        db.query(InterviewRound)
        .filter(InterviewRound.interviewer_id == employee_code)
        .order_by(InterviewRound.created_at.desc())
        .all()
    )
    result = []
    for r in rounds:
        assignment = _build_assignment(r, db)
        if assignment:
            result.append(assignment)
    return result


def get_interviewer_upcoming(db: Session, employee_code: str) -> list[InterviewerAssignment]:
    """Upcoming scheduled interviews (today onwards) for this interviewer."""
    today_str = date.today().isoformat()
    rounds = (
        db.query(InterviewRound)
        .filter(
            InterviewRound.interviewer_id == employee_code,
            InterviewRound.interview_date >= today_str,
            InterviewRound.status.in_(["scheduled", "in_progress"]),
        )
        .order_by(InterviewRound.interview_date)
        .all()
    )
    result = []
    for r in rounds:
        assignment = _build_assignment(r, db)
        if assignment:
            result.append(assignment)
    return result


def get_interviewer_calendar(db: Session, employee_code: str) -> list[CalendarEvent]:
    """All interview rounds with a date for this interviewer."""
    rounds = (
        db.query(InterviewRound)
        .filter(
            InterviewRound.interviewer_id == employee_code,
            InterviewRound.interview_date.isnot(None),
        )
        .order_by(InterviewRound.interview_date)
        .all()
    )

    result = []
    for r in rounds:
        p = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        if not p:
            continue
        cand = (
            db.query(RecruitmentCandidate)
            .filter(RecruitmentCandidate.candidate_id == p.candidate_id)
            .first()
        )
        if not cand:
            continue
        req = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

        try:
            d = date.fromisoformat(r.interview_date)
        except Exception:
            continue

        full_name = f"{cand.first_name} {cand.last_name or ''}".strip()

        result.append(
            CalendarEvent(
                round_id=r.id,
                candidate_name=full_name,
                date=r.interview_date,
                day=d.day,
                month=d.strftime("%b"),
                year=d.year,
                time=_format_time(r.interview_time),
                role=cand.current_job_title,
                req_id=req.req_id if req else "",
            )
        )
    return result


def get_interviewer_feedback_history(db: Session, employee_code: str) -> list[FeedbackHistoryItem]:
    feedbacks = (
        db.query(InterviewFeedback)
        .filter(
            InterviewFeedback.interviewer_id == employee_code,
            InterviewFeedback.submitted_at.isnot(None),
        )
        .order_by(InterviewFeedback.submitted_at.desc())
        .all()
    )

    result = []
    for fb in feedbacks:
        r = db.query(InterviewRound).filter(InterviewRound.id == fb.round_id).first()
        if not r:
            continue
        p = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        if not p:
            continue
        cand = (
            db.query(RecruitmentCandidate)
            .filter(RecruitmentCandidate.candidate_id == p.candidate_id)
            .first()
        )
        if not cand:
            continue

        full_name = f"{cand.first_name} {cand.last_name or ''}".strip()
        date_str = fb.submitted_at.strftime("%d %b %Y") if fb.submitted_at else ""

        result.append(
            FeedbackHistoryItem(
                id=fb.id,
                candidate_id=cand.candidate_id,
                candidate_name=full_name,
                initials=_initials(full_name),
                role=cand.current_job_title,
                round=r.round_name,
                date=date_str,
                recommendation=fb.recommendation,
                technical_rating=fb.technical_rating,
                comm_rating=fb.communication_rating,
                problem_rating=fb.problem_solving_rating,
                notes=fb.notes,
            )
        )
    return result


def submit_feedback(
    db: Session, round_id: int, payload: FeedbackSubmit, employee_code: str
) -> dict:
    r = db.query(InterviewRound).filter(InterviewRound.id == round_id).first()
    if not r:
        return {"error": "Interview round not found"}
    if r.interviewer_id != employee_code:
        return {"error": "You are not assigned to this interview round"}

    existing = (
        db.query(InterviewFeedback)
        .filter(InterviewFeedback.round_id == round_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    if existing:
        existing.technical_rating       = payload.technical_rating
        existing.communication_rating   = payload.comm_rating
        existing.problem_solving_rating = payload.problem_rating
        existing.recommendation         = payload.recommendation
        existing.notes                  = payload.notes
        existing.submitted_at           = now
    else:
        fb = InterviewFeedback(
            round_id               = round_id,
            interviewer_id         = employee_code,
            technical_rating       = payload.technical_rating,
            communication_rating   = payload.comm_rating,
            problem_solving_rating = payload.problem_rating,
            recommendation         = payload.recommendation,
            notes                  = payload.notes,
            submitted_at           = now,
        )
        db.add(fb)

    r.status     = "completed"
    r.updated_at = now
    db.commit()

    return {"message": "Feedback submitted successfully", "round_id": round_id}
