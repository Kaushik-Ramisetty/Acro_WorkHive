"""
Recruiter service — complete workflow implementation.

Stage flow:
  Sourced → [Manager Review] → Technical Round → Awaiting Slot Selection
  → Interview Scheduled → [Additional Rounds] → HR Round → Selected → Onboarding

Key stage rules:
  - create_candidate:   current_stage = "Manager Approval"
  - manager approves:   current_stage = "Technical Round"  (set in recruitment_service.py)
  - assign_interviewer: current_stage = "Awaiting Slot Selection"
  - slot selected:      current_stage = "Interview Scheduled"
  - all rounds done:    current_stage = "HR Round"
  - selected:           current_stage = "Selected"
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.recruitment import (
    CandidatePipeline, InterviewFeedback, InterviewRound,
    InterviewSlot, JobRequirement, RecruitmentCandidate, RequirementSkill,
)
from app.models import Department, Employee
from app.services.email_dispatcher import _send_email, dispatch_for_recipient, send_html_email
from app.services import notification_service
from app.schemas.recruiter import (
    ActiveInterviewOut, CandidateDetailOut, CandidateListItem,
    CandidateDuplicateCheckOut, DuplicateCandidateInfo,
    InterviewListItem, PipelineCardOut, PipelineStage,
    RecruiterStats, RequirementListItem, UpcomingInterviewOut,
)

UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "./uploads")
APP_URL     = os.getenv("APP_URL", "http://localhost:8000")

# ── Ordered stages (for timeline and progression checks) ─────────────────────
STAGE_ORDER = [
    "Sourced",
    "Manager Approval",         # backward-compat alias kept in DB
    "Technical Round",
    "Awaiting Slot Selection",
    "Interview Scheduled",
    "HR Round",
    "Selected",
    "Onboarding",
]

def _stage_idx(stage: str) -> int:
    try: return STAGE_ORDER.index(stage)
    except ValueError: return 2   # unknown stages sit at Technical Round level


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_skills(raw) -> list:
    if isinstance(raw, list): return raw
    if isinstance(raw, str):
        try: return json.loads(raw)
        except Exception: return []
    return []

def _exp_str(years) -> Optional[str]:
    if years is None: return None
    return f"{int(years)} years" if years == int(years) else f"{years} years"

def _stage_type(stage: Optional[str]) -> str:
    m = {
        "Sourced":"teal","Manager Approval":"amber","Technical Round":"purple",
        "Awaiting Slot Selection":"blue","Interview Scheduled":"blue",
        "HR Round":"purple","Selected":"green","Onboarding":"teal",
        "Rejected":"red",
    }
    return m.get(stage or "", "gray")

def _status_type(status: str) -> str:
    m = {"scheduled":"blue","in_progress":"amber","completed":"green",
         "awaiting_slot":"red","pending":"gray"}
    return m.get(status, "gray")

def _status_label(status: str) -> str:
    return {"scheduled":"Interview Scheduled","in_progress":"In Progress",
            "completed":"Completed","awaiting_slot":"Slot Pending",
            "pending":"Pending"}.get(status, status.title())

def _interviewer_name(emp_code: Optional[str], db: Session) -> Optional[str]:
    if not emp_code: return None
    emp = db.query(Employee).filter(Employee.employee_code == emp_code).first()
    return emp.full_name if emp else emp_code

def _employee_id_from_identifier(db: Session, identifier) -> Optional[int]:
    if identifier is None:
        return None
    try:
        emp_id = int(identifier)
    except (TypeError, ValueError):
        emp_id = None
    if emp_id:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if emp:
            return emp.id

    ident = str(identifier).strip()
    if not ident:
        return None
    emp = db.query(Employee).filter(Employee.employee_code == ident).first()
    return emp.id if emp else None

def _resolve_recruiter_recipient_id(
    db: Session,
    *,
    req: Optional[JobRequirement] = None,
    round_: Optional[InterviewRound] = None,
    cand: Optional[RecruitmentCandidate] = None,
) -> Optional[int]:
    for identifier in (
        req.assigned_recruiter if req else None,
        round_.added_by if round_ else None,
        cand.added_by if cand else None,
        req.created_by if req else None,
    ):
        recipient_id = _employee_id_from_identifier(db, identifier)
        if recipient_id:
            return recipient_id
    return None

def _candidate_for_pipeline(p: CandidatePipeline, db: Session) -> Optional[RecruitmentCandidate]:
    return db.query(RecruitmentCandidate).filter(
        RecruitmentCandidate.candidate_id == p.candidate_id
    ).first()

def _next_candidate_id(db: Session) -> str:
    last = db.query(RecruitmentCandidate).order_by(RecruitmentCandidate.id.desc()).first()
    num = (last.id if last else 0) + 1
    return f"CAND{num:02d}"

def _next_round_order(pipeline_id: int, db: Session) -> str:
    count = db.query(InterviewRound).filter(InterviewRound.pipeline_id == pipeline_id).count()
    return f"ROUN{count + 1}"


def _normalize_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def _normalize_mobile(mobile: Optional[str | int]) -> Optional[str]:
    if mobile is None:
        return None
    digits = re.sub(r"\D+", "", str(mobile))
    if not digits:
        return None
    if len(digits) > 10:
        digits = digits[-10:]
    return digits or None


def _mobile_to_db_value(mobile: Optional[str | int]) -> Optional[int]:
    normalized = _normalize_mobile(mobile)
    return int(normalized) if normalized else None


def _format_mobile(mobile: Optional[str | int]) -> Optional[str]:
    normalized = _normalize_mobile(mobile)
    return normalized if normalized else None


def _build_duplicate_result(
    candidate: RecruitmentCandidate,
    matched_by: list[str],
) -> CandidateDuplicateCheckOut:
    return CandidateDuplicateCheckOut(
        duplicate_found=True,
        matched_candidate_id=candidate.candidate_id,
        matched_by=matched_by,
        matched_candidate=DuplicateCandidateInfo(
            candidate_id=candidate.candidate_id,
            candidate_name=f"{candidate.first_name} {candidate.last_name or ''}".strip(),
            email=_normalize_email(candidate.email),
            mobile=_format_mobile(candidate.mobile),
            created_date=candidate.created_at.isoformat() if candidate.created_at else None,
        ),
    )


def find_duplicate_candidate(
    db: Session,
    *,
    email: Optional[str] = None,
    mobile: Optional[str | int] = None,
) -> CandidateDuplicateCheckOut:
    normalized_email = _normalize_email(email)
    normalized_mobile = _normalize_mobile(mobile)

    if normalized_email:
        email_match = (
            db.query(RecruitmentCandidate)
            .filter(func.lower(func.trim(RecruitmentCandidate.email)) == normalized_email)
            .order_by(RecruitmentCandidate.created_at.asc(), RecruitmentCandidate.id.asc())
            .first()
        )
        if email_match:
            matched_by = ["email"]
            if normalized_mobile and _normalize_mobile(email_match.mobile) == normalized_mobile:
                matched_by.append("mobile")
            return _build_duplicate_result(email_match, matched_by)

    if normalized_mobile:
        mobile_db_value = _mobile_to_db_value(normalized_mobile)
        mobile_match = (
            db.query(RecruitmentCandidate)
            .filter(RecruitmentCandidate.mobile == mobile_db_value)
            .order_by(RecruitmentCandidate.created_at.asc(), RecruitmentCandidate.id.asc())
            .first()
        )
        if mobile_match:
            return _build_duplicate_result(mobile_match, ["mobile"])

    return CandidateDuplicateCheckOut(duplicate_found=False, matched_by=[])


# ── Pipeline stage timeline builder ──────────────────────────────────────────

def _build_pipeline_stages(p: CandidatePipeline, db: Session) -> list[PipelineStage]:
    """
    Build ordered interview timeline.
    Technical Round ALWAYS appears — even if no round record exists yet.
    """
    # When manager rejected, terminate pipeline at the Rejected node
    if p.pipeline_status == "rejected":
        return [
            PipelineStage(label="Sourced", status="done"),
            PipelineStage(label="Manager Review", status="done"),
            PipelineStage(
                label="Rejected",
                status="active",
                rejection_reason=p.rejection_reason or "",
            ),
        ]

    current = p.current_stage or "Sourced"
    cur_idx = _stage_idx(current)
    approved = p.mgr_approval_status == "approved"

    def stage_status_for(stage: str, idx: int) -> str:
        if idx < cur_idx: return "done"
        if idx == cur_idx: return "active"
        return ""

    rounds = (db.query(InterviewRound)
               .filter(InterviewRound.pipeline_id == p.id)
               .order_by(InterviewRound.round_order)
               .all())

    fb_map: dict[str, str] = {}
    for r in rounds:
        fb = db.query(InterviewFeedback).filter(
            InterviewFeedback.round_id == r.round_order
        ).first()
        fb_map[r.round_name] = fb.notes if fb else ""

    stages: list[PipelineStage] = []

    # 1. Sourced — always done once a candidate is in the pipeline
    stages.append(PipelineStage(label="Sourced", status="done"))

    # 2. Manager Review
    mgr_status = "done" if approved else ("active" if current in ["Sourced","Manager Approval"] else "done")
    stages.append(PipelineStage(
        label="Manager Review",
        status=mgr_status,
        managerRemark=p.manager_remark or "",
    ))

    # 3. Interview rounds (Technical Round always shown)
    base_rounds = [r for r in rounds if not r.is_additional and r.round_type not in ["HR"]]

    if not base_rounds:
        tech_idx  = _stage_idx("Technical Round")
        tech_s    = stage_status_for("Technical Round", tech_idx)
        if current in ["Technical Round", "Awaiting Slot Selection", "Interview Scheduled"]:
            tech_s = "active"
        elif _stage_idx(current) > _stage_idx("Interview Scheduled"):
            tech_s = "done"
        stages.append(PipelineStage(label="Technical Round", status=tech_s))
    else:
        for r in base_rounds:
            s = "done" if r.status == "completed" else (
                "active" if current in [r.round_name, "Awaiting Slot Selection", "Interview Scheduled"]
                else "")
            stages.append(PipelineStage(
                label=r.round_name, status=s,
                feedback=fb_map.get(r.round_name, ""),
                managerRemark=p.manager_remark or "" if s == "active" else "",
            ))

    # 4. Slot status sub-stages
    if current == "Awaiting Slot Selection":
        stages.append(PipelineStage(label="Awaiting Slot Selection", status="active"))
    elif current == "Interview Scheduled":
        sched = (
            db.query(InterviewRound)
            .filter(
                InterviewRound.pipeline_id == p.id,
                InterviewRound.status == "scheduled",
            )
            .order_by(InterviewRound.updated_at.desc())
            .first()
        )
        stages.append(PipelineStage(
            label="Interview Scheduled",
            status="active",
            interviewer=_interviewer_name(sched.interviewer_id, db) if sched else None,
            interview_date=sched.interview_date if sched else None,
            interview_time=sched.interview_time if sched else None,
        ))

    # 5. Additional rounds
    for r in [r for r in rounds if r.is_additional]:
        s = "done" if r.status == "completed" else ("active" if current == r.round_name else "")
        stages.append(PipelineStage(label=r.round_name, status=s,
                                    feedback=fb_map.get(r.round_name, "")))

    # 6. HR Round
    hr_rounds = [r for r in rounds if r.round_type == "HR"]
    if not hr_rounds:
        hr_idx = _stage_idx("HR Round")
        hr_s   = stage_status_for("HR Round", hr_idx)
        stages.append(PipelineStage(label="HR Round", status=hr_s))
    else:
        for r in hr_rounds:
            s = "done" if r.status == "completed" else ("active" if current == r.round_name else "")
            stages.append(PipelineStage(label=r.round_name, status=s,
                                        feedback=fb_map.get(r.round_name, "")))

    # 7. Selected / Onboarding
    sel_idx = _stage_idx("Selected")
    ob_idx  = _stage_idx("Onboarding")
    stages.append(PipelineStage(label="Selected",   status=stage_status_for("Selected",   sel_idx)))
    stages.append(PipelineStage(label="Onboarding", status=stage_status_for("Onboarding", ob_idx)))

    return stages


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_recruiter_stats(db: Session) -> RecruiterStats:
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)

    open_reqs        = db.query(JobRequirement).filter(JobRequirement.status.notin_(["Closed"])).count()
    total_candidates = db.query(RecruitmentCandidate).count()
    pending_review   = db.query(CandidatePipeline).filter(
        CandidatePipeline.pipeline_status == "active",
        CandidatePipeline.mgr_approval_status == "pending",
    ).count()
    interviews_this_week = db.query(InterviewRound).filter(
        InterviewRound.interview_date >= week_start.isoformat(),
        InterviewRound.interview_date <= week_end.isoformat(),
        InterviewRound.status.in_(["scheduled", "in_progress"]),
    ).count()
    offers_sent = db.query(CandidatePipeline).filter(
        CandidatePipeline.offer_status.isnot(None),
        CandidatePipeline.offer_status != "",
    ).count()

    return RecruiterStats(
        open_reqs=open_reqs, total_candidates=total_candidates,
        pending_review=pending_review, interviews_this_week=interviews_this_week,
        offers_sent=offers_sent,
    )


# ── Interview queries ─────────────────────────────────────────────────────────

def get_active_interviews(db: Session, limit: int = 10) -> list[ActiveInterviewOut]:
    rounds = (db.query(InterviewRound)
               .filter(InterviewRound.status.in_(["scheduled","in_progress","awaiting_slot"]))
               .limit(limit).all())
    result = []
    for r in rounds:
        p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        if not p: continue
        cand = _candidate_for_pipeline(p, db)
        if not cand: continue
        req  = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()
        iv_name = _interviewer_name(r.interviewer_id, db)
        date_label = None
        if r.interview_date and r.interview_time:
            try:
                d = date.fromisoformat(r.interview_date)
                date_label = f"{d.day} {d.strftime('%b')}, {r.interview_time[:5]}"
            except: date_label = f"{r.interview_date}, {r.interview_time}"
        elif r.interview_date:
            date_label = r.interview_date
        sl    = _status_label(r.status)
        sc    = "#16a34a" if r.status=="scheduled" else ("#d97706" if r.status=="awaiting_slot" else "#2563eb")
        rtype = "blue" if r.status=="scheduled" else "amber"
        result.append(ActiveInterviewOut(
            round_id=r.id, pipeline_id=p.id,
            candidate_id=cand.candidate_id,
            candidate_name=f"{cand.first_name} {cand.last_name or ''}".strip(),
            role=f"{cand.current_job_title} · {req.req_id}" if req else cand.current_job_title,
            req_id=req.req_id if req else "",
            round_name=r.round_name, round_type=rtype,
            interviewer_name=iv_name, date_label=date_label,
            interview_format=r.interview_format, meeting_link=r.meeting_link,
            status=r.status, status_label=sl, status_color=sc,
        ))
    return result


def get_upcoming_interviews(db: Session, limit: int = 6) -> list[UpcomingInterviewOut]:
    today    = date.today()
    week_end = today + timedelta(days=7)
    rounds   = (db.query(InterviewRound)
                 .filter(
                     InterviewRound.interview_date >= today.isoformat(),
                     InterviewRound.interview_date <= week_end.isoformat(),
                 ).order_by(InterviewRound.interview_date).limit(limit).all())
    result = []
    for r in rounds:
        p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        if not p: continue
        cand = _candidate_for_pipeline(p, db)
        if not cand: continue
        req  = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()
        iv_name = _interviewer_name(r.interviewer_id, db)
        day, month = None, None
        if r.interview_date:
            try:
                d = date.fromisoformat(r.interview_date)
                day, month = d.day, d.strftime("%b")
            except: pass
        time_label = r.interview_time[:5] if r.interview_time else "TBD"
        result.append(UpcomingInterviewOut(
            round_id=r.id, pipeline_id=p.id,
            candidate_id=cand.candidate_id,
            candidate_name=f"{cand.first_name} {cand.last_name or ''}".strip(),
            sub=f"{req.title if req else 'Unknown'} · {r.round_name}",
            day=day, month=month, time_label=time_label,
            interviewer_name=iv_name, interview_format=r.interview_format,
            pending=r.status == "awaiting_slot",
        ))
    return result


def get_all_interviews(db: Session, round_filter: Optional[str] = None) -> list[InterviewListItem]:
    q = db.query(InterviewRound)
    if round_filter and round_filter != "all":
        q = q.filter(InterviewRound.round_name.ilike(f"%{round_filter}%"))
    rounds = q.order_by(InterviewRound.created_at.desc()).all()
    result = []
    for r in rounds:
        p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        if not p: continue
        cand = _candidate_for_pipeline(p, db)
        if not cand: continue
        iv_name = _interviewer_name(r.interviewer_id, db)
        date_label = None
        if r.interview_date and r.interview_time:
            try:
                d = date.fromisoformat(r.interview_date)
                date_label = f"{d.day} {d.strftime('%b')} · {r.interview_time[:5]}"
            except: date_label = f"{r.interview_date} · {r.interview_time}"
        elif r.interview_date:
            date_label = r.interview_date
        actions = ["Reschedule"] if r.status in ["scheduled","awaiting_slot"] else []
        if r.status != "completed": actions.append("Feedback")
        result.append(InterviewListItem(
            round_id=r.id, round_order=r.round_order,
            pipeline_id=p.id, candidate_id=cand.candidate_id,
            candidate_name=f"{cand.first_name} {cand.last_name or ''}".strip(),
            role=cand.current_job_title,
            round_name=r.round_name, round_type=r.round_type,
            interviewer_name=iv_name, interviewer_code=r.interviewer_id,
            interview_date=date_label, interview_time=r.interview_time,
            interview_format=r.interview_format, meeting_link=r.meeting_link,
            status=r.status, status_type=_status_type(r.status), actions=actions,
        ))
    return result


def reschedule_interview(db: Session, round_id: int, payload, current_emp) -> dict:
    r = db.query(InterviewRound).filter(InterviewRound.id == round_id).first()
    if not r: return {"error": "Round not found"}
    r.interview_date   = payload.new_date
    r.interview_time   = payload.new_time
    if payload.interviewer_code: r.interviewer_id   = payload.interviewer_code
    if payload.interview_format: r.interview_format = payload.interview_format
    r.status     = "scheduled"
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Interview rescheduled", "round_id": round_id}


# ── Email date/time formatters ────────────────────────────────────────────────

def _fmt_date_val(date_str: Optional[str]) -> str:
    """'2026-06-01' → 'Mon, 01 Jun 2026'"""
    if not date_str:
        return "TBD"
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%a, %d %b %Y")
    except Exception:
        return date_str


def _fmt_time_val(time_str: Optional[str]) -> str:
    """'14:00' → '2:00 PM'"""
    if not time_str:
        return "TBD"
    try:
        t = datetime.strptime(time_str[:5], "%H:%M")
        return t.strftime("%I:%M %p").lstrip("0") or time_str
    except Exception:
        return time_str


# ── Interviewer assignment email ──────────────────────────────────────────────

def _send_interviewer_assignment_email(
    interviewer_email: str,
    interviewer_name: str,
    candidate_name: str,
    req_id: str,
    req_title: str,
    job_description: str,
    round_name: str,
    recruiter_name: str,
    token: str,
) -> None:
    """Send HTML email to the interviewer with a link to add their available slots."""
    slot_url = f"{APP_URL}/interviews/slot-selection/{token}"
    jd_excerpt = (job_description or "")[:500]
    if len(job_description or "") > 500:
        jd_excerpt += "…"

    plain = (
        f"Dear {interviewer_name},\n\n"
        f"You have been assigned to conduct an interview for the following candidate.\n\n"
        f"Candidate Name  : {candidate_name}\n"
        f"Requirement ID  : {req_id}\n"
        f"Position        : {req_title}\n"
        f"Interview Round : {round_name}\n"
        f"Assigned By     : {recruiter_name}\n\n"
        + (f"Job Description:\n{jd_excerpt}\n\n" if jd_excerpt else "")
        + f"Please add your available interview slots by clicking:\n{slot_url}\n\n"
        f"No login is required — the link is personalised for you.\n\n"
        f"Best regards,\nThe Recruitment Team\nWorkHive HRMS"
    )

    jd_html = (
        f'<p style="margin:0 0 20px;color:#475569;font-size:13px;line-height:1.6;">'
        f'<strong>Job Description:</strong><br/>{jd_excerpt}</p>'
        if jd_excerpt else ""
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="540" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.08);max-width:540px;">
        <tr><td style="background:#1e3a8a;border-radius:12px 12px 0 0;padding:24px 32px;">
          <p style="margin:0;color:#93c5fd;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">WorkHive HRMS</p>
          <p style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:700;">Interview Assignment</p>
        </td></tr>
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 16px;color:#1e293b;font-size:15px;">Dear <strong>{interviewer_name}</strong>,</p>
          <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
            You have been assigned to conduct an interview. Please review the details below and add your available slots.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;margin-bottom:20px;">
            <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;">
              <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;">Candidate</span><br/>
              <span style="font-size:14px;font-weight:600;color:#1e293b;">{candidate_name}</span>
            </td></tr>
            <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;">
              <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;">Requirement</span><br/>
              <span style="font-size:14px;font-weight:600;color:#1e293b;">{req_id} — {req_title}</span>
            </td></tr>
            <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;">
              <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;">Interview Round</span><br/>
              <span style="font-size:14px;font-weight:600;color:#1e293b;">{round_name}</span>
            </td></tr>
            <tr><td style="padding:12px 16px;">
              <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;">Assigned By (Recruiter)</span><br/>
              <span style="font-size:14px;font-weight:600;color:#1e293b;">{recruiter_name}</span>
            </td></tr>
          </table>
          {jd_html}
          <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
            Please add your available interview slots by clicking the button below.<br/>
            <strong>No login is required</strong> — this link is personalised for you.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
            <tr><td align="center">
              <a href="{slot_url}" style="display:inline-block;background:#2563eb;color:#fff;padding:14px 36px;border-radius:8px;text-decoration:none;font-size:15px;font-weight:700;font-family:Arial,sans-serif;">
                Add Interview Slots
              </a>
            </td></tr>
          </table>
          <p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.6;">
            If the button above doesn't work, copy this link into your browser:<br/>
            <span style="color:#2563eb;word-break:break-all;">{slot_url}</span>
          </p>
        </td></tr>
        <tr><td style="background:#f8fafc;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px;padding:16px 32px;text-align:center;">
          <p style="margin:0;color:#94a3b8;font-size:12px;">&copy; WorkHive HRMS &bull; Acronotics Internal System</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    send_html_email(
        interviewer_email,
        f"Interview Assignment — {candidate_name}",
        html,
        text_fallback=plain,
    )


# ── Step 6: Assign interviewer ────────────────────────────────────────────────

def assign_interviewer(db: Session, payload, current_emp) -> dict:
    cand = db.query(RecruitmentCandidate).filter(
        RecruitmentCandidate.candidate_id == payload.candidate_id
    ).first()
    if not cand:
        return {"error": f"Candidate '{payload.candidate_id}' not found"}

    p = (db.query(CandidatePipeline)
          .filter(
              CandidatePipeline.candidate_id == payload.candidate_id,
              CandidatePipeline.pipeline_status == "active",
              CandidatePipeline.mgr_approval_status == "approved",
          )
          .order_by(CandidatePipeline.updated_at.desc())
          .first())
    if not p:
        return {"error": (
            f"No approved pipeline entry for '{payload.candidate_id}'. "
            "Manager must approve the candidate first."
        )}

    now   = datetime.now(timezone.utc)
    order = _next_round_order(p.id, db)

    new_round = InterviewRound(
        pipeline_id      = p.id,
        round_name       = payload.round_name,
        round_type       = payload.round_type or "Technical",
        round_order      = order,
        interviewer_id   = payload.interviewer_code,
        status           = "awaiting_slot",
        interview_date   = payload.interview_date,
        interview_time   = payload.interview_time,
        interview_format = payload.interview_format or "Teams",
        meeting_link     = getattr(payload, "meeting_link", None),
        is_additional    = 0,
        added_by         = current_emp.employee_code or str(current_emp.id),
        added_reason     = "Initial interviewer assignment",
        created_at       = now,
        updated_at       = now,
    )
    db.add(new_round)

    p.current_stage = "Awaiting Slot Selection"
    p.updated_at    = now

    db.commit()
    db.refresh(new_round)

    slot_token = secrets.token_urlsafe(32)
    new_round.selection_token = slot_token
    new_round.token_used = 0
    db.commit()

    try:
        iv_emp = db.query(Employee).filter(
            Employee.employee_code == payload.interviewer_code
        ).first()
        req = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()
        cand_name = f"{cand.first_name} {cand.last_name or ''}".strip()
        recruiter_name = (
            getattr(current_emp, "full_name", None)
            or current_emp.employee_code
            or "Recruiter"
        )
        if iv_emp:
            iv_email = (
                getattr(iv_emp, "official_email", None)
                or getattr(iv_emp, "email", None)
            )
            if iv_email:
                _send_interviewer_assignment_email(
                    interviewer_email=iv_email,
                    interviewer_name=iv_emp.full_name or payload.interviewer_code,
                    candidate_name=cand_name,
                    req_id=req.req_id if req else "",
                    req_title=req.title if req else "the position",
                    job_description=(req.job_description or "") if req else "",
                    round_name=payload.round_name,
                    recruiter_name=recruiter_name,
                    token=slot_token,
                )
    except Exception:
        pass

    iv_name = _interviewer_name(payload.interviewer_code, db)
    return {
        "message":          "Interviewer assigned — candidate is now awaiting slot selection",
        "round_id":         new_round.id,
        "round_order":      order,
        "pipeline_id":      p.id,
        "candidate_id":     payload.candidate_id,
        "pipeline_stage":   "Awaiting Slot Selection",
        "interviewer_name": iv_name,
        "interviewer_code": payload.interviewer_code,
    }


# ── Step 7: Interviewer adds available slots ──────────────────────────────────

def _send_slot_selection_email(
    cand_email: str,
    cand_name: str,
    round_name: str,
    req_title: str,
    token: str,
    slots: list[dict],
) -> None:
    selection_url = f"{APP_URL}/candidate/select-slot/{token}"

    slot_rows_html = ""
    plain_lines: list[str] = []
    for s in slots:
        slot_id  = s.get("id")
        date_str = s.get("date", "")
        time_str = s.get("time", "")
        fmt_date = _fmt_date_val(date_str)
        fmt_time = _fmt_time_val(time_str)
        plain_lines.append(f"  • {fmt_date} at {fmt_time}")

        direct_url = (
            f"{APP_URL}/candidate/quick-select/{token}/{slot_id}"
            if slot_id else selection_url
        )
        slot_rows_html += f"""
        <tr>
          <td style="padding:6px 0;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border:1.5px solid #e5e7eb;border-radius:8px;background:#fff;">
              <tr>
                <td style="padding:12px 16px;">
                  <div style="font-size:14px;font-weight:700;color:#111827;">{fmt_date}</div>
                  <div style="font-size:13px;color:#6b7280;margin-top:2px;">{fmt_time}</div>
                </td>
                <td style="padding:12px 16px;text-align:right;">
                  <a href="{direct_url}"
                     style="display:inline-block;background:#2563eb;color:#fff;
                            padding:8px 18px;border-radius:6px;text-decoration:none;
                            font-size:12px;font-weight:700;white-space:nowrap;
                            font-family:Arial,sans-serif;">
                    Select This Slot
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    plain = (
        f"Dear {cand_name},\n\n"
        f"You have been shortlisted for the {round_name} for the position of {req_title}.\n\n"
        f"Available interview slots:\n"
        + "\n".join(plain_lines)
        + f"\n\nPlease select your preferred slot at:\n{selection_url}\n\n"
        f"Important: This link is unique to you. Do not share it.\n\n"
        f"Best regards,\nThe Recruitment Team\nWorkHive HRMS"
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="540" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.08);max-width:540px;">
        <tr><td style="background:#1e3a8a;border-radius:12px 12px 0 0;padding:24px 32px;">
          <p style="margin:0;color:#93c5fd;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">WorkHive HRMS</p>
          <p style="margin:4px 0 0;color:#fff;font-size:20px;font-weight:700;">Interview Slot Selection</p>
        </td></tr>
        <tr><td style="padding:28px 32px;">
          <p style="margin:0 0 16px;color:#1e293b;font-size:15px;">Dear <strong>{cand_name}</strong>,</p>
          <p style="margin:0 0 8px;color:#475569;font-size:14px;line-height:1.6;">
            You have been shortlisted for the <strong>{round_name}</strong> for the position of
            <strong>{req_title}</strong>.
          </p>
          <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
            Please click <strong>Select This Slot</strong> next to your preferred interview time.
          </p>
          <p style="margin:0 0 10px;font-size:12px;font-weight:700;color:#1e293b;text-transform:uppercase;letter-spacing:.06em;">Available Slots</p>
          <table width="100%" cellpadding="0" cellspacing="0">
            {slot_rows_html}
          </table>
          <p style="margin:20px 0 0;color:#94a3b8;font-size:12px;line-height:1.6;">
            If the buttons above don&rsquo;t work, you can
            <a href="{selection_url}" style="color:#2563eb;">view all slots here</a>.
            This link is unique to you &mdash; please do not share it.
          </p>
        </td></tr>
        <tr><td style="background:#f8fafc;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px;padding:16px 32px;text-align:center;">
          <p style="margin:0;color:#94a3b8;font-size:12px;">&copy; WorkHive HRMS &bull; Acronotics Internal System</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    send_html_email(
        cand_email,
        f"Select Your Interview Slot — {req_title}",
        html,
        text_fallback=plain,
    )


def add_interview_slots(db: Session, round_id: int, slots: list[dict], current_emp) -> dict:
    r = db.query(InterviewRound).filter(InterviewRound.id == round_id).first()
    if not r:
        return {"error": "Round not found"}

    p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
    cand = _candidate_for_pipeline(p, db) if p else None
    req  = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first() if p else None

    now        = datetime.now(timezone.utc)
    added      = []
    added_objs: list[InterviewSlot] = []
    for s in slots:
        slot = InterviewSlot(
            round_id       = r.id,
            slot_date      = s.get("slot_date"),
            slot_time      = s.get("slot_time"),
            is_selected    = 0,
            candidate_id   = cand.candidate_id if cand else None,
            interviewer_id = r.interviewer_id,
            requirement_id = p.requirement_id if p else None,
            created_at     = now,
        )
        db.add(slot)
        added_objs.append(slot)
        added.append({"date": s.get("slot_date"), "time": s.get("slot_time")})

    if not r.selection_token:
        r.selection_token = secrets.token_urlsafe(32)
        r.token_used      = 0

    r.updated_at = now
    db.commit()

    slot_data_with_ids = [
        {"id": s.id, "date": s.slot_date, "time": s.slot_time}
        for s in added_objs
    ]

    _recruiter_id = _resolve_recruiter_recipient_id(db, req=req, round_=r, cand=cand)

    email_sent = False
    if cand and cand.email:
        cand_name = f"{cand.first_name} {cand.last_name or ''}".strip()
        req_title = req.title if req else "the position"
        try:
            _send_slot_selection_email(
                cand_email=cand.email,
                cand_name=cand_name,
                round_name=r.round_name,
                req_title=req_title,
                token=r.selection_token,
                slots=slot_data_with_ids,
            )
            r.email_sent_at = datetime.now(timezone.utc)
            db.commit()
            email_sent = True
        except Exception:
            pass

    if _recruiter_id and cand:
        try:
            cand_name = f"{cand.first_name} {cand.last_name or ''}".strip()
            iv_name = _interviewer_name(r.interviewer_id, db) or r.interviewer_id or "Interviewer"
            notification_service.notify(
                db,
                recipient_id=_recruiter_id,
                type_="recruitment",
                title=f"Slots Submitted — {cand_name}",
                body=(
                    f"Interviewer {iv_name} submitted interview slots for {cand_name}."
                ),
                reference_table="interview_rounds",
                reference_id=str(r.id),
                action_url="recruitment",
                autocommit=True,
            )
        except Exception:
            pass

    return {
        "message":        f"{len(added)} slot(s) added for round {r.round_name}",
        "round_id":       round_id,
        "slots":          added,
        "selection_token": r.selection_token,
        "email_sent":     email_sent,
    }


def get_interview_slots(db: Session, round_id: int) -> list[dict]:
    r = db.query(InterviewRound).filter(InterviewRound.id == round_id).first()
    if not r: return []
    slots = (
        db.query(InterviewSlot)
        .filter(
            or_(
                InterviewSlot.round_id == r.id,
                InterviewSlot.round_id == r.round_order,
            )
        )
        .order_by(InterviewSlot.slot_date, InterviewSlot.slot_time)
        .all()
    )
    return [
        {
            "id":          s.id,
            "slot_date":   s.slot_date,
            "slot_time":   s.slot_time,
            "is_selected": bool(s.is_selected),
            "selected_at": s.selected_at.isoformat() if s.selected_at else None,
        }
        for s in slots
    ]


# ── Step 8: Candidate selects a slot ─────────────────────────────────────────

def select_interview_slot(db: Session, slot_id: int, token: Optional[str] = None) -> dict:
    slot = db.query(InterviewSlot).filter(InterviewSlot.id == slot_id).first()
    if not slot:
        return {"error": "Slot not found"}
    if slot.is_selected:
        return {"error": "Slot already taken"}

    now = datetime.now(timezone.utc)
    slot.is_selected = 1
    slot.selected_at = now

    rid = slot.round_id
    r = None
    try:
        r = db.query(InterviewRound).filter(InterviewRound.id == int(rid)).first()
    except (TypeError, ValueError):
        pass
    if r is None and rid is not None and not str(rid).isdigit():
        r = db.query(InterviewRound).filter(
            InterviewRound.round_order == str(rid)
        ).first()

    p    = None
    cand = None
    req  = None

    if r:
        r.interview_date = slot.slot_date
        r.interview_time = slot.slot_time
        r.status         = "scheduled"
        r.token_used     = 1
        r.updated_at     = now

        p = db.query(CandidatePipeline).filter(
            CandidatePipeline.id == r.pipeline_id
        ).first()
        if p:
            p.current_stage = "Interview Scheduled"
            p.updated_at    = now

            cand = _candidate_for_pipeline(p, db)
            req  = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

    db.commit()

    if r and p and cand and req:
        cand_name = f"{cand.first_name} {cand.last_name or ''}".strip()
        req_title  = req.title if req else "the position"

        try:
            if slot.slot_date and slot.slot_time:
                from datetime import datetime as _dt2
                _d = date.fromisoformat(slot.slot_date)
                _t = _dt2.strptime(slot.slot_time[:5], "%H:%M")
                notif_date = f"{_d.day} {_d.strftime('%b %Y')} at {_t.strftime('%I:%M %p').lstrip('0')}"
            else:
                notif_date = "TBD"
        except Exception:
            notif_date = f"{slot.slot_date} at {slot.slot_time}" if slot.slot_date and slot.slot_time else "TBD"

        date_label = notif_date
        _rec_id = _resolve_recruiter_recipient_id(db, req=req, round_=r, cand=cand)

        if _rec_id:
            try:
                notification_service.notify(
                    db,
                    recipient_id=_rec_id,
                    type_="recruitment",
                    title=f"Slot Selected — {cand_name}",
                    body=f"Candidate {cand_name} selected interview slot on {notif_date}.",
                    reference_table="interview_rounds",
                    reference_id=str(r.id),
                    autocommit=True,
                )
            except Exception:
                pass

        if r.interviewer_id:
            try:
                iv_emp = db.query(Employee).filter(
                    Employee.employee_code == r.interviewer_id
                ).first()
                if iv_emp:
                    notification_service.notify(
                        db,
                        recipient_id=iv_emp.id,
                        type_="recruitment",
                        title=f"Interview Confirmed — {cand_name}",
                        body=f"Candidate {cand_name} confirmed interview slot on {notif_date}.",
                        reference_table="interview_rounds",
                        reference_id=str(r.id),
                        autocommit=True,
                    )
            except Exception:
                pass

        if _rec_id:
            try:
                dispatch_for_recipient(
                    db,
                    recipient_id=_rec_id,
                    subject=f"[HRMS] Interview Scheduled — {cand_name} for {req_title}",
                    body=(
                        f"{cand_name} has selected their interview slot.\n\n"
                        f"Round:     {r.round_name}\n"
                        f"Date/Time: {date_label}\n"
                        f"Position:  {req_title}\n\n"
                        f"Please confirm the meeting link and calendar invite."
                    ),
                )
            except Exception:
                pass

        if r.interviewer_id:
            try:
                iv_emp = db.query(Employee).filter(
                    Employee.employee_code == r.interviewer_id
                ).first()
                if iv_emp and iv_emp.id:
                    dispatch_for_recipient(
                        db,
                        recipient_id=iv_emp.id,
                        subject=f"[HRMS] Interview Confirmed — {cand_name}",
                        body=(
                            f"Your interview with {cand_name} has been confirmed.\n\n"
                            f"Round:     {r.round_name}\n"
                            f"Date/Time: {date_label}\n"
                            f"Position:  {req_title}\n\n"
                            f"Please prepare your interview questions accordingly."
                        ),
                    )
            except Exception:
                pass

        if cand.email:
            try:
                _send_email(
                    cand.email,
                    f"[HRMS] Interview Confirmed — {req_title}",
                    (
                        f"Dear {cand_name},\n\n"
                        f"Your interview slot has been confirmed.\n\n"
                        f"Round:     {r.round_name}\n"
                        f"Date/Time: {date_label}\n"
                        f"Position:  {req_title}\n\n"
                        f"You will receive a Teams meeting link shortly.\n\n"
                        f"Best regards,\nThe Recruitment Team"
                    ),
                )
            except Exception:
                pass

    return {
        "message":        "Slot selected — interview scheduled",
        "slot_id":        slot_id,
        "interview_date": slot.slot_date,
        "interview_time": slot.slot_time,
        "pipeline_stage": "Interview Scheduled",
    }


# ── Add additional round ──────────────────────────────────────────────────────

def add_interview_round(db: Session, payload, current_emp) -> dict:
    p = db.query(CandidatePipeline).filter(CandidatePipeline.id == payload.pipeline_id).first()
    if not p: return {"error": "Pipeline not found"}

    existing_count = db.query(InterviewRound).filter(
        InterviewRound.pipeline_id == payload.pipeline_id
    ).count()
    is_additional = 0 if existing_count == 0 else 1

    order = _next_round_order(payload.pipeline_id, db)
    now   = datetime.now(timezone.utc)

    new_round = InterviewRound(
        pipeline_id      = payload.pipeline_id,
        round_name       = payload.round_name,
        round_type       = payload.round_type or "Technical",
        round_order      = order,
        interviewer_id   = payload.interviewer_code,
        status           = "awaiting_slot",
        interview_date   = payload.interview_date,
        interview_time   = payload.interview_time,
        interview_format = getattr(payload, "interview_format", None) or "Teams",
        is_additional    = is_additional,
        added_by         = current_emp.employee_code if current_emp.employee_code else str(current_emp.id),
        added_reason     = payload.reason,
        created_at       = now,
        updated_at       = now,
    )
    db.add(new_round)
    p.current_stage = payload.round_name
    p.updated_at    = now
    db.commit()
    db.refresh(new_round)
    return {
        "message":                  f"Round '{payload.round_name}' added",
        "round_id":                 new_round.id,
        "round_order":              order,
        "pipeline_stage_updated_to": payload.round_name,
    }


# ── Candidates ────────────────────────────────────────────────────────────────

def list_candidates(db: Session, q: Optional[str] = None, stage: Optional[str] = None,
                    source: Optional[str] = None, req_id: Optional[str] = None,
                    page: int = 1, per_page: int = 50) -> list[CandidateListItem]:
    query = db.query(RecruitmentCandidate)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            RecruitmentCandidate.first_name.ilike(pattern)
            | RecruitmentCandidate.last_name.ilike(pattern)
            | RecruitmentCandidate.email.ilike(pattern)
        )
    if source:
        query = query.filter(RecruitmentCandidate.source.ilike(source))
    cands = query.order_by(RecruitmentCandidate.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    result = []
    for c in cands:
        p = (db.query(CandidatePipeline)
              .filter(CandidatePipeline.candidate_id == c.candidate_id)
              .order_by(CandidatePipeline.updated_at.desc()).first())
        current_stage = "Rejected" if (p and p.pipeline_status == "rejected") else (p.current_stage if p else "Sourced")
        if stage and current_stage.lower() != stage.lower(): continue
        req_obj = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first() if p else None
        if req_id and req_obj and req_obj.req_id != req_id: continue
        is_selected = p and p.offer_status and p.offer_status.strip() != ""
        result.append(CandidateListItem(
            db_id=c.id, candidate_id=c.candidate_id,
            full_name=f"{c.first_name} {c.last_name or ''}".strip(),
            email=c.email, role=c.current_job_title, source=c.source,
            exp=_exp_str(c.experience_years),
            ctc=c.expected_ctc, stage=current_stage,
            stage_type=_stage_type(current_stage),
            req_id=req_obj.req_id if req_obj else None,
            pipeline_id=p.id if p else None,
            is_selected=bool(is_selected),
            onboarded_at=c.onboarded_at,
        ))
    return result


def get_candidate_detail(db: Session, candidate_id: str) -> Optional[CandidateDetailOut]:
    c = db.query(RecruitmentCandidate).filter(
        RecruitmentCandidate.candidate_id == candidate_id
    ).first()
    if not c: return None
    p = (db.query(CandidatePipeline)
          .filter(CandidatePipeline.candidate_id == candidate_id)
          .order_by(CandidatePipeline.updated_at.desc()).first())
    stages = _build_pipeline_stages(p, db) if p else []

    mgr_approval_status = p.mgr_approval_status if p else None
    rejection_reason    = p.rejection_reason if p else None
    rejected_by         = None
    rejected_at         = None
    if p and p.pipeline_status == "rejected":
        if p.mgr_approval_by:
            mgr_emp = db.query(Employee).filter(Employee.employee_code == p.mgr_approval_by).first()
            rejected_by = mgr_emp.full_name if mgr_emp else p.mgr_approval_by
        if p.mgr_approval_at:
            try:
                rejected_at = p.mgr_approval_at.strftime("%d %b %Y, %I:%M %p")
            except Exception:
                rejected_at = str(p.mgr_approval_at)

    return CandidateDetailOut(
        candidate_id=c.candidate_id,
        full_name=f"{c.first_name} {c.last_name or ''}".strip(),
        role=c.current_job_title, email=c.email, phone=_format_mobile(c.mobile),
        exp=_exp_str(c.experience_years), employer=c.current_employer,
        ctc=c.current_ctc, expCtc=c.expected_ctc,
        notice=c.notice_period, source=c.source,
        curr_location=c.curr_location,
        skills=_parse_skills(c.skills),
        notes=c.recruiter_notes,
        resume_url=c.resume_url, cover_letter_url=c.cover_letter_url,
        pipeline_id=p.id if p else None,
        pipeline=stages,
        mgr_approval_status=mgr_approval_status,
        rejection_reason=rejection_reason,
        rejected_by=rejected_by,
        rejected_at=rejected_at,
        onboarded_at=c.onboarded_at,
    )


def create_candidate(db: Session, payload, current_emp: Employee,
                     resume_url=None, cover_letter_url=None,
                     id_proof_url=None, others_url=None) -> CandidateDetailOut:
    import json as _json
    duplicate = find_duplicate_candidate(db, email=payload.email, mobile=payload.mobile)
    if duplicate.duplicate_found:
        return duplicate

    cand_id     = _next_candidate_id(db)
    skills_json = _json.dumps(payload.skills or [])
    now         = datetime.now(timezone.utc)
    normalized_email = _normalize_email(payload.email)
    normalized_mobile = _mobile_to_db_value(payload.mobile)

    cand = RecruitmentCandidate(
        candidate_id=cand_id, first_name=payload.first_name,
        last_name=payload.last_name, email=normalized_email, mobile=normalized_mobile,
        experience_years=payload.experience_years,
        current_job_title=payload.current_job_title,
        current_employer=payload.current_employer,
        current_ctc=payload.current_ctc, expected_ctc=payload.expected_ctc,
        curr_location=payload.curr_location, notice_period=payload.notice_period,
        source=payload.other_source if payload.source == "Others" else payload.source,
        skills=skills_json, assign_to_recruitment=None,
        resume_url=resume_url, cover_letter_url=cover_letter_url,
        id_proof=id_proof_url, others=others_url,
        added_by=current_emp.id, created_at=now, updated_at=now,
    )
    db.add(cand)
    db.flush()

    if payload.requirement_id:
        req = db.query(JobRequirement).filter(JobRequirement.id == payload.requirement_id).first()
        if req:
            cand.assign_to_recruitment = f"{req.req_id} . {req.title}"
            pipeline = CandidatePipeline(
                candidate_id=cand_id,
                requirement_id=payload.requirement_id,
                current_stage="Manager Approval",
                pipeline_status="active",
                mgr_approval_status="pending",
                shortlisted_by=(current_emp.employee_code or str(current_emp.id)),
                shortlisted_at=now.isoformat(),
                created_at=now, updated_at=now,
            )
            db.add(pipeline)

    db.commit()
    db.refresh(cand)
    return get_candidate_detail(db, cand_id)


def update_recruiter_notes(db: Session, candidate_id: str, notes: str) -> bool:
    c = db.query(RecruitmentCandidate).filter(
        RecruitmentCandidate.candidate_id == candidate_id
    ).first()
    if not c: return False
    c.recruiter_notes = notes
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


# ── Requirements ─────────────────────────────────────────────────────────────

def list_requirements(
    db: Session,
    exclude_closed: bool = False,
    viewer_role: str = "",
    viewer_id: Optional[int] = None,
    recruiter_ids: Optional[List[int]] = None,
) -> list[RequirementListItem]:
    q = db.query(JobRequirement).order_by(JobRequirement.created_at.desc())
    if exclude_closed:
        q = q.filter(JobRequirement.status != "Closed")
    # Manager visibility: only requirements they created
    if viewer_role == "manager" and viewer_id:
        q = q.filter(JobRequirement.created_by == viewer_id)
    # Recruiter filter
    if recruiter_ids:
        q = q.filter(JobRequirement.assigned_recruiter.in_(recruiter_ids))
    reqs = q.all()
    result = []
    priority_map = {"Urgent":"red","High":"amber","Medium":"blue",
                    "Normal":"gray","Low":"gray","Filled":"green","Sourcing":"teal"}
    for r in reqs:
        dept  = db.query(Department).filter(Department.id == r.department_id).first()
        skills = _parse_skills(r.required_skills)
        if not skills:
            skill_rows = (db.query(RequirementSkill)
                           .filter(RequirementSkill.requirement_id == r.id,
                                   RequirementSkill.status == "approved").all())
            skills = [s.skill_name for s in skill_rows]
        _latest = (
            db.query(
                CandidatePipeline.candidate_id.label("cid"),
                func.max(CandidatePipeline.updated_at).label("max_upd"),
            )
            .group_by(CandidatePipeline.candidate_id)
            .subquery()
        )
        cnt = (db.query(CandidatePipeline)
                .join(
                    RecruitmentCandidate,
                    CandidatePipeline.candidate_id == RecruitmentCandidate.candidate_id,
                )
                .join(
                    _latest,
                    (CandidatePipeline.candidate_id == _latest.c.cid)
                    & (CandidatePipeline.updated_at == _latest.c.max_upd),
                )
                .filter(CandidatePipeline.requirement_id == r.id,
                        CandidatePipeline.pipeline_status == "active")
                .count())
        recruiter_name = None
        if r.assigned_recruiter:
            rec_emp = db.query(Employee).filter(Employee.id == r.assigned_recruiter).first()
            recruiter_name = rec_emp.full_name if rec_emp else None
        creator_name = None
        if r.created_by:
            creator_emp = db.query(Employee).filter(Employee.id == r.created_by).first()
            creator_name = creator_emp.full_name if creator_emp else None
        assigned_by_name = None
        if r.assigned_by:
            assigner_emp = db.query(Employee).filter(Employee.id == r.assigned_by).first()
            assigned_by_name = assigner_emp.full_name if assigner_emp else None
        result.append(RequirementListItem(
            db_id=r.id, req_id=r.req_id, title=r.title,
            client_name=r.client_name,
            department=dept.name if dept else None,
            department_id=r.department_id,
            priority=r.priority,
            priority_type=priority_map.get(r.priority or "", "gray"),
            skills=skills[:4], candidate_count=cnt,
            openings=r.openings or 0,
            min_experience=r.min_experience,
            max_experience=r.max_experience,
            assigned_recruiter_name=recruiter_name,
            assigned_recruiter_id=r.assigned_recruiter,
            assigned_by_name=assigned_by_name,
            assigned_at=r.assigned_at,
            location=r.location,
            work_mode=r.work_mode,
            employment_type=r.employment_type,
            budget_range=r.budget_range,
            target_joining=r.target_joining,
            qualification=r.qualification,
            created_by_name=creator_name,
            created_by_id=r.created_by,
            status=r.status,
            created_date=r.created_at.date().isoformat() if r.created_at else None,
            job_description=r.job_description,
        ))
    return result


# ── Pipeline ─────────────────────────────────────────────────────────────────

PIPELINE_STAGES_DISPLAY = [
    "Sourced","Manager Approval","Technical Round","Awaiting Slot Selection",
    "Interview Scheduled","HR Round","Selected","Onboarding",
]

def get_pipeline(db: Session, req_filter: Optional[str] = None) -> dict:
    q = db.query(CandidatePipeline).filter(CandidatePipeline.pipeline_status != "rejected")
    if req_filter and req_filter != "All":
        req = db.query(JobRequirement).filter(JobRequirement.req_id == req_filter).first()
        if req: q = q.filter(CandidatePipeline.requirement_id == req.id)

    pipelines = q.all()
    grouped: dict[str, list] = {}
    for p in pipelines:
        cand = _candidate_for_pipeline(p, db)
        if not cand: continue
        req   = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

        is_rejected = p.pipeline_status == "rejected"
        stage = "Rejected" if is_rejected else (p.current_stage or "Sourced")

        rejection_reason = None
        rejected_by      = None
        rejected_at      = None
        if is_rejected:
            rejection_reason = p.rejection_reason
            if p.mgr_approval_by:
                mgr_emp = db.query(Employee).filter(Employee.employee_code == p.mgr_approval_by).first()
                rejected_by = mgr_emp.full_name if mgr_emp else p.mgr_approval_by
            if p.mgr_approval_at:
                try:
                    rejected_at = p.mgr_approval_at.strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    rejected_at = str(p.mgr_approval_at)

        latest_round = None
        if not is_rejected:
            latest_round = (db.query(InterviewRound)
                             .filter(InterviewRound.pipeline_id == p.id,
                                     InterviewRound.status.in_(["scheduled","awaiting_slot"]))
                             .order_by(InterviewRound.round_order.desc()).first())
        iv_name  = _interviewer_name(latest_round.interviewer_id, db) if latest_round else None
        iv_date  = None
        if latest_round and latest_round.interview_date:
            try:
                d = date.fromisoformat(latest_round.interview_date)
                iv_date = f"{d.day} {d.strftime('%b')}, {latest_round.interview_time[:5] if latest_round.interview_time else 'TBD'}"
            except: iv_date = latest_round.interview_date
        elif latest_round and latest_round.status == "awaiting_slot":
            iv_date = "Slot pending"

        is_special = bool(p.offer_status and p.offer_status.strip()) and not is_rejected
        pending    = bool(latest_round and latest_round.status == "awaiting_slot")

        card = PipelineCardOut(
            pipeline_id=p.id, candidate_id=cand.candidate_id,
            candidate_name=f"{cand.first_name} {cand.last_name or ''}".strip(),
            role=cand.current_job_title, company=cand.current_employer,
            exp=_exp_str(cand.experience_years), ctc=cand.current_ctc,
            req_id=req.req_id if req else "",
            stage=stage, interview_date=iv_date,
            interviewer=iv_name, skills=_parse_skills(cand.skills)[:3],
            is_special=is_special, pending_slots=pending,
            rejection_reason=rejection_reason,
            rejected_by=rejected_by,
            rejected_at=rejected_at,
        )
        grouped.setdefault(stage, []).append(card)

    ordered = {}
    for s in PIPELINE_STAGES_DISPLAY:
        if s in grouped: ordered[s] = grouped[s]
    for s in grouped:
        if s not in ordered: ordered[s] = grouped[s]
    return ordered


# ── Interviewers list ─────────────────────────────────────────────────────────

def list_interviewers(db: Session) -> list[dict]:
    emps = db.query(Employee).filter(
        Employee.is_deleted.is_(False),
        Employee.employment_status == "active",
    ).order_by(Employee.first_name).all()
    return [
        {"id": e.id, "employee_code": e.employee_code,
         "full_name": e.full_name,
         "designation": e.designation.title if e.designation else None}
        for e in emps
    ]


# ── Recruiters list (for assign-recruiter dropdown) ───────────────────────────

def list_recruiters(db: Session) -> list[dict]:
    emps = db.query(Employee).filter(
        Employee.is_deleted.is_(False),
        Employee.employment_status == "active",
    ).order_by(Employee.first_name).all()
    return [
        {"id": e.id, "name": e.full_name, "employee_code": e.employee_code or ""}
        for e in emps
    ]


# ── Assign recruiter to requirement ──────────────────────────────────────────

def assign_recruiter_to_requirement(
    db: Session,
    req_id: str,
    recruiter_id: int,
    assigner: Employee,
) -> dict:
    from datetime import timezone as _tz
    req = db.query(JobRequirement).filter(JobRequirement.req_id == req_id).first()
    if not req:
        return {"error": "Requirement not found"}
    recruiter = db.query(Employee).filter(
        Employee.id == recruiter_id,
        Employee.is_deleted.is_(False),
        Employee.employment_status == "active",
    ).first()
    if not recruiter:
        return {"error": "Recruiter not found or inactive"}
    req.assigned_recruiter = recruiter_id
    req.assigned_by = assigner.id
    req.assigned_at = datetime.now(_tz.utc)
    notification_service.notify(
        db,
        recipient_id=recruiter_id,
        type_="recruitment",
        title=f"You have been assigned Requirement {req.req_id}",
        body=f"You have been assigned to work on: {req.title}.",
        reference_table="job_requirements",
        reference_id=str(req.id),
        action_url="recruitment",
        autocommit=False,
    )
    db.commit()
    return {"message": "Recruiter assigned", "req_id": req.req_id, "recruiter_id": recruiter_id}
