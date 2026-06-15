"""
Recruitment service - business logic layer.
Keeps routes thin; all DB logic lives here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.recruitment import (
    CandidatePipeline,
    InterviewRound,
    JobRequirement,
    RecruitmentCandidate,
    RequirementSkill,
)
from app.models import Department, Employee
from app.schemas.recruitment import (
    CandidateOut,
    DashboardStats,
    InterviewRoundOut,
    RequirementCreate,
    RequirementOut,
    RequirementUpdate,
)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_list(value) -> list:
    """Safely parse a TEXT JSON column into a Python list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _resolve_department_id(db: Session, raw: str | None) -> str | None:
    """Accept a DEP-style ID or department name; return matching department.id."""
    if not raw:
        return None
    if raw.upper().startswith("DEP"):
        return raw if db.get(Department, raw) else None
    row = db.query(Department).filter(Department.name.ilike(raw)).first()
    if row:
        return row.id
    row = db.query(Department).filter(Department.name.ilike(f"%{raw}%")).first()
    return row.id if row else None


def _next_req_id(db: Session) -> str:
    last = db.query(JobRequirement).order_by(JobRequirement.id.desc()).first()
    if not last:
        return "REQ-0001"
    try:
        num = int(last.req_id.split("-")[-1])
    except (ValueError, IndexError):
        num = last.id
    return f"REQ-{(num + 1):04d}"


def _req_to_out(req: JobRequirement, db: Session) -> RequirementOut:
    """Convert ORM JobRequirement to RequirementOut schema."""
    # department_id is TEXT (e.g. 'DEP001') — look up Department by PK
    dept = db.query(Department).filter(Department.id == req.department_id).first() \
           if req.department_id else None
    dept_name = dept.name if dept else None

    # skills_detail is a real FK relationship — safe to traverse
    approved = [rs.skill_name for rs in req.skills_detail if rs.status == "approved"]
    pending  = [rs.skill_name for rs in req.skills_detail if rs.status == "pending"]

    # Subquery: for each candidate, find the id of their most recently updated
    # pipeline entry.
    _latest = (
        db.query(
            CandidatePipeline.candidate_id.label("cid"),
            func.max(CandidatePipeline.updated_at).label("max_upd"),
        )
        .group_by(CandidatePipeline.candidate_id)
        .subquery()
    )
    pipeline_count = (
        db.query(CandidatePipeline)
        .join(
            RecruitmentCandidate,
            CandidatePipeline.candidate_id == RecruitmentCandidate.candidate_id,
        )
        .join(
            _latest,
            (CandidatePipeline.candidate_id == _latest.c.cid)
            & (CandidatePipeline.updated_at == _latest.c.max_upd),
        )
        .filter(
            CandidatePipeline.requirement_id == req.id,
            CandidatePipeline.pipeline_status == "active",
        )
        .count()
    )

    # created_by is INTEGER employee id — look up Employee by PK
    creator = db.query(Employee).filter(Employee.id == req.created_by).first() \
              if req.created_by else None
    creator_name = creator.full_name if creator else None

    # required_skills is TEXT JSON in DB
    raw_skills = _parse_json_list(req.required_skills)

    return RequirementOut(
        id=req.req_id,
        db_id=req.id,
        title=req.title,
        client_name=req.client_name,
        department=dept_name,
        department_id=req.department_id,
        employment_type=req.employment_type,
        work_mode=req.work_mode,
        location=req.location,
        min_exp=req.min_experience,
        max_exp=req.max_experience,
        openings=req.openings,
        priority=req.priority,
        skills=approved or raw_skills,
        pending_skills=pending,
        jd=req.job_description,
        preferred_qualification=req.qualification,
        target_joining=req.target_joining if req.target_joining else None,
        budget_range=req.budget_range,
        status=req.status,
        pipeline=pipeline_count,
        created=req.created_at.date().isoformat() if req.created_at else None,
        created_by_name=creator_name,
    )


def _pipeline_to_candidate_out(pipeline: CandidatePipeline, db: Session) -> CandidateOut:
    """Convert ORM CandidatePipeline + RecruitmentCandidate to CandidateOut."""
    cand = pipeline.candidate   # viewonly TEXT-join relationship
    req  = pipeline.requirement # real FK relationship

    if not cand or not req:
        missing = []
        if not cand:
            missing.append("candidate")
        if not req:
            missing.append("requirement")
        raise ValueError(
            f"Pipeline {pipeline.id} has missing related {' and '.join(missing)} record(s)."
        )

    exp_str = f"{cand.experience_years} yrs" if cand.experience_years else None

    rounds: list[InterviewRoundOut] = []
    for r in pipeline.interview_rounds:
        # interviewer_id is TEXT employee code (e.g. 'AIN715') — look up by employee_code
        iv_emp = db.query(Employee).filter(Employee.employee_code == r.interviewer_id).first() \
                 if r.interviewer_id else None
        iv_name = iv_emp.full_name if iv_emp else r.interviewer_id  # fallback to code

        # interview_date and interview_time are TEXT strings — concatenate directly
        date_str = None
        if r.interview_date and r.interview_time:
            date_str = f"{r.interview_date}, {r.interview_time}"
        elif r.interview_date:
            date_str = r.interview_date

        fb = r.feedback
        rounds.append(InterviewRoundOut(
            name=r.round_name,
            status=r.status,
            interviewer=iv_name,
            date=date_str,
            time=r.interview_time,
            format=r.interview_format,
            feedback=fb.notes if fb else "",
            manager_remark=pipeline.manager_remark or "",
        ))

    stage = pipeline.current_stage
    # Derive status from mgr_approval_status first
    if pipeline.mgr_approval_status == "pending":
        status = "awaiting"
    elif pipeline.mgr_approval_status == "rejected":
        status = "rejected"
    else:
        stage_status_map = {
            "Sourced":                  "active",
            "Manager Approval":         "approved",
            "Approved":                 "approved",
            "Technical Round":          "active",
            "Awaiting Slot Selection":  "active",
            "Interview Scheduled":      "active",
            "HR Round":                 "active",
            "Selected":                 "selected",
            "Onboarding":               "joining",
        }
        status = stage_status_map.get(stage, "active")

    return CandidateOut(
        id=cand.candidate_id,
        db_id=cand.id,
        pipeline_id=pipeline.id,
        name=f"{cand.first_name} {cand.last_name or ''}".strip(),
        req=req.req_id,
        req_db_id=req.id,
        role=cand.current_job_title,
        exp=exp_str,
        company=cand.current_employer,
        notice=cand.notice_period,
        ctc=cand.current_ctc,
        exp_ctc=cand.expected_ctc,
        skills=_parse_json_list(cand.skills),
        stage=stage,
        status=status,
        mgr_approval_status=pipeline.mgr_approval_status,
        manager_remark=pipeline.manager_remark,
        rejection_reason=pipeline.rejection_reason,
        interview_rounds=rounds,
        offer_status=pipeline.offer_status,
        onboarding_date=pipeline.onboarding_date if pipeline.onboarding_date else None,
        current_company=cand.current_employer,
        resume_url=cand.resume_url,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Requirements
# ─────────────────────────────────────────────────────────────────────────────

def list_requirements(
    db: Session,
    created_by: int,
    status: Optional[str] = None,
) -> list[RequirementOut]:
    q = (
        db.query(JobRequirement)
        .options(
            joinedload(JobRequirement.skills_detail),
        )
        .filter(JobRequirement.created_by == created_by)
        .order_by(JobRequirement.created_at.desc())
    )
    if status:
        q = q.filter(JobRequirement.status == status)
    return [_req_to_out(r, db) for r in q.all()]


def get_requirement(db: Session, req_id: str) -> Optional[RequirementOut]:
    row = (
        db.query(JobRequirement)
        .options(
            joinedload(JobRequirement.skills_detail),
        )
        .filter(JobRequirement.req_id == req_id)
        .first()
    )
    return _req_to_out(row, db) if row else None


def create_requirement(
    db: Session, payload: RequirementCreate, created_by: int
) -> RequirementOut:
    req_id  = _next_req_id(db)
    dept_id = _resolve_department_id(db, payload.department_id)

    # Store skills as JSON string (TEXT column)
    skills_json = json.dumps(payload.skills or [])

    req = JobRequirement(
        req_id=req_id,
        title=payload.title,
        client_name=payload.client_name,
        department_id=dept_id,
        employment_type=payload.employment_type,
        work_mode=payload.work_mode,
        location=payload.location,
        min_experience=payload.min_experience,
        max_experience=payload.max_experience,
        openings=payload.openings,
        priority=payload.priority,
        required_skills=skills_json,
        job_description=payload.job_description,
        qualification=payload.qualification,
        budget_range=payload.budget_range,
        target_joining=payload.target_joining.isoformat() if payload.target_joining else None,
        status="Active",
        created_by=created_by,
    )
    db.add(req)
    db.flush()

    now = datetime.now(timezone.utc)

    for skill_name in (payload.skills or []):
        db.add(RequirementSkill(
            requirement_id=req.id,
            skill_name=skill_name,
            is_primary=1,
            status="approved",
            requested_by=str(created_by),
            requested_at=now,
            approved_by=str(created_by),
            approved_at=now,
        ))

    for skill_name in (payload.pending_skills or []):
        db.add(RequirementSkill(
            requirement_id=req.id,
            skill_name=skill_name,
            is_primary=0,
            status="pending",
            requested_by=str(created_by),
            requested_at=now,
        ))

    db.commit()
    db.refresh(req)
    return _req_to_out(req, db)


def update_requirement_status(
    db: Session, req_id: str, new_status: str
) -> Optional[RequirementOut]:
    row = db.query(JobRequirement).filter(JobRequirement.req_id == req_id).first()
    if not row:
        return None
    row.status = new_status
    db.commit()
    db.refresh(row)
    return _req_to_out(row, db)


def update_requirement(
    db: Session, req_id: str, payload: RequirementUpdate
) -> Optional[RequirementOut]:
    row = db.query(JobRequirement).filter(JobRequirement.req_id == req_id).first()
    if not row:
        return None

    if payload.title is not None:
        row.title = payload.title
    if payload.client_name is not None:
        row.client_name = payload.client_name
    if payload.department_id is not None:
        row.department_id = _resolve_department_id(db, payload.department_id)
    if payload.employment_type is not None:
        row.employment_type = payload.employment_type
    if payload.work_mode is not None:
        row.work_mode = payload.work_mode
    if payload.location is not None:
        row.location = payload.location
    if payload.min_experience is not None:
        row.min_experience = payload.min_experience
    if payload.max_experience is not None:
        row.max_experience = payload.max_experience
    if payload.openings is not None:
        row.openings = payload.openings
    if payload.priority is not None:
        row.priority = payload.priority
    if payload.job_description is not None:
        row.job_description = payload.job_description
    if payload.qualification is not None:
        row.qualification = payload.qualification
    if payload.budget_range is not None:
        row.budget_range = payload.budget_range
    if payload.target_joining is not None:
        row.target_joining = payload.target_joining.isoformat()

    if payload.skills is not None:
        db.query(RequirementSkill).filter(
            RequirementSkill.requirement_id == row.id,
            RequirementSkill.status == "approved",
        ).delete(synchronize_session=False)
        row.required_skills = json.dumps(payload.skills)
        now = datetime.now(timezone.utc)
        for skill_name in payload.skills:
            db.add(RequirementSkill(
                requirement_id=row.id,
                skill_name=skill_name,
                is_primary=1,
                status="approved",
                requested_at=now,
            ))

    db.commit()
    db.refresh(row)
    return _req_to_out(row, db)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline / Candidates
# ─────────────────────────────────────────────────────────────────────────────

def list_pipeline(
    db: Session,
    manager_id: int,
    req_id: Optional[str] = None,
) -> list[CandidateOut]:
    mgr_req_ids = (
        db.query(JobRequirement.id)
        .filter(JobRequirement.created_by == manager_id)
        .subquery()
    )

    q = (
        db.query(CandidatePipeline)
        .options(
            joinedload(CandidatePipeline.candidate),
            joinedload(CandidatePipeline.requirement),
            joinedload(CandidatePipeline.interview_rounds)
                .joinedload(InterviewRound.feedback),
        )
        .filter(CandidatePipeline.requirement_id.in_(mgr_req_ids))
    )

    if req_id:
        req_row = db.query(JobRequirement).filter(JobRequirement.req_id == req_id).first()
        if req_row:
            q = q.filter(CandidatePipeline.requirement_id == req_row.id)

    results: list[CandidateOut] = []
    for pipeline in q.all():
        try:
            results.append(_pipeline_to_candidate_out(pipeline, db))
        except ValueError:
            continue
    return results


def approve_candidate(
    db: Session, pipeline_id: int, manager_id: int, remark: Optional[str] = None
) -> Optional[CandidateOut]:
    pipeline = db.query(CandidatePipeline).filter(CandidatePipeline.id == pipeline_id).first()
    if not pipeline:
        return None
    mgr_emp = db.query(Employee).filter(Employee.id == manager_id).first()
    pipeline.mgr_approval_status = "approved"
    pipeline.mgr_approval_by     = (mgr_emp.employee_code or str(manager_id)) if mgr_emp else str(manager_id)
    pipeline.mgr_approval_at     = datetime.now(timezone.utc)
    pipeline.manager_remark      = remark
    pipeline.current_stage       = "Technical Round"
    pipeline.updated_at          = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pipeline)
    return _pipeline_to_candidate_out(pipeline, db)


def reject_candidate(
    db: Session, pipeline_id: int, manager_id: int, reason: Optional[str] = None
) -> Optional[CandidateOut]:
    pipeline = db.query(CandidatePipeline).filter(CandidatePipeline.id == pipeline_id).first()
    if not pipeline:
        return None
    mgr_emp = db.query(Employee).filter(Employee.id == manager_id).first()
    pipeline.mgr_approval_status = "rejected"
    pipeline.mgr_approval_by     = (mgr_emp.employee_code or str(manager_id)) if mgr_emp else str(manager_id)
    pipeline.mgr_approval_at     = datetime.now(timezone.utc)
    pipeline.rejection_reason    = reason
    pipeline.pipeline_status     = "rejected"
    pipeline.updated_at          = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pipeline)
    return _pipeline_to_candidate_out(pipeline, db)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def get_dashboard_stats(db: Session, manager_id: int) -> DashboardStats:
    mgr_req_ids = (
        db.query(JobRequirement.id)
        .filter(JobRequirement.created_by == manager_id)
        .subquery()
    )

    open_reqs = (
        db.query(JobRequirement)
        .filter(
            JobRequirement.created_by == manager_id,
            JobRequirement.status.notin_(["Closed"]),
        )
        .count()
    )

    in_pipeline = (
        db.query(CandidatePipeline)
        .filter(
            CandidatePipeline.requirement_id.in_(mgr_req_ids),
            CandidatePipeline.pipeline_status == "active",
        )
        .count()
    )

    awaiting_approval = (
        db.query(CandidatePipeline)
        .filter(
            CandidatePipeline.requirement_id.in_(mgr_req_ids),
            CandidatePipeline.pipeline_status == "active",
            CandidatePipeline.mgr_approval_status == "pending",
        )
        .count()
    )

    interviews_sched = (
        db.query(CandidatePipeline)
        .filter(
            CandidatePipeline.requirement_id.in_(mgr_req_ids),
            CandidatePipeline.current_stage.in_(["Technical Round", "HR Round"]),
            CandidatePipeline.pipeline_status == "active",
        )
        .count()
    )

    positions_closed = (
        db.query(JobRequirement)
        .filter(
            JobRequirement.created_by == manager_id,
            JobRequirement.status == "Closed",
        )
        .count()
    )

    return DashboardStats(
        open_reqs=open_reqs,
        in_pipeline=in_pipeline,
        awaiting_approval=awaiting_approval,
        interviews_sched=interviews_sched,
        positions_closed=positions_closed,
    )
