"""
Recruiter routes — prefix /recruiter
All endpoints are accessible by employee, manager, and admin roles.
The RBAC gate (showing the tab only to authorised users) lives in the frontend.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee
from app.models.recruitment import JobRequirement
from app.schemas.recruiter import (
    AddRoundRequest, AssignInterviewerRequest, AssignRecruiterRequest,
    CandidateCreate, CandidateDetailOut,
    CandidateDuplicateCheckIn, CandidateDuplicateCheckOut, CandidateListItem, InterviewListItem, PipelineCardOut,
    RecruiterNotesUpdate, RecruiterStats, RescheduleRequest,
    RequirementListItem,
)
from app.schemas.recruitment import RequirementCreate, RequirementOut, RequirementUpdate
from app.services import recruiter_service as svc
from app.services import recruitment_service as req_svc

router = APIRouter(prefix="/recruiter", tags=["recruiter"])
ROLES = ("employee", "manager", "admin")
UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "./uploads")


def _save_upload(file: Optional[UploadFile], subfolder: str = "recruitment") -> Optional[str]:
    """Save an uploaded file and return its URL path."""
    if not file or not file.filename: return None
    ext = os.path.splitext(file.filename)[-1].lower()
    dest_dir = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    fname = f"{uuid.uuid4()}{ext}"
    fpath = os.path.join(dest_dir, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return f"uploads/{subfolder}/{fname}"


def _parse_ctc_amount(value: Optional[str], field_name: str) -> Optional[int]:
    """Accept common CTC input formats and store annual amount as an integer."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    lowered = raw.lower()
    normalized = raw.replace(",", "").replace("₹", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", normalized)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must contain a numeric amount.",
        )

    amount = float(match.group(0))
    if re.search(r"(lpa|lakh|lakhs|lac|lacs)", lowered):
        amount *= 100000
    return int(round(amount))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard stats
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=RecruiterStats)
def recruiter_stats(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Overview tab stat cards — all dynamic from DB."""
    return svc.get_recruiter_stats(db)


# ─────────────────────────────────────────────────────────────────────────────
# Interviews
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/interviews/active")
def active_interviews(
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Active interview schedule cards for the Overview tab."""
    return svc.get_active_interviews(db, limit=limit)


@router.get("/interviews/upcoming")
def upcoming_interviews(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Upcoming interview calendar entries for the Overview tab."""
    return svc.get_upcoming_interviews(db)


@router.get("/interviews", response_model=list[InterviewListItem])
def all_interviews(
    round_type: Optional[str] = Query(None, alias="round"),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Interviews tab — full list of all interview rounds."""
    return svc.get_all_interviews(db, round_filter=round_type)


@router.post("/interviews/assign")
def assign_interviewer(
    payload: AssignInterviewerRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """
    Step 6 — Recruiter assigns an interviewer to an Approved candidate.
    Creates the first interview round and advances pipeline stage to round_name.
    Candidate must have mgr_approval_status='approved' before this call.
    """
    result = svc.assign_interviewer(db, payload, current)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/interviews/{round_id}/reschedule")
def reschedule_interview(
    round_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Reschedule an interview round (updates date/time/interviewer/format)."""
    result = svc.reschedule_interview(db, round_id, payload, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/interviews/{round_id}/override")
def override_interview(
    round_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Override interview schedule — same as reschedule but labelled differently."""
    result = svc.reschedule_interview(db, round_id, payload, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"message": "Interview schedule overridden", **result}


@router.post("/pipeline/{pipeline_id}/add-round")
def add_round(
    pipeline_id: int,
    payload: AddRoundRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Add an additional interview round to a pipeline entry."""
    payload.pipeline_id = pipeline_id
    result = svc.add_interview_round(db, payload, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Candidates
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/candidates", response_model=list[CandidateListItem])
def list_candidates(
    q: Optional[str]      = Query(None, description="Search by name or email"),
    stage: Optional[str]  = Query(None),
    source: Optional[str] = Query(None),
    req_id: Optional[str] = Query(None),
    page: int             = Query(1, ge=1),
    per_page: int         = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Candidates tab — paginated, searchable, filterable list."""
    return svc.list_candidates(db, q=q, stage=stage, source=source,
                               req_id=req_id, page=page, per_page=per_page)


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailOut)
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Candidate detail slide-over panel."""
    result = svc.get_candidate_detail(db, candidate_id)
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return result


@router.post("/candidates/check-duplicate", response_model=CandidateDuplicateCheckOut)
def check_candidate_duplicate(
    payload: CandidateDuplicateCheckIn,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Check whether a candidate already exists by normalized email or mobile."""
    return svc.find_duplicate_candidate(db, email=payload.email, mobile=payload.mobile)


@router.post("/candidates", response_model=CandidateDetailOut, status_code=status.HTTP_201_CREATED)
async def add_candidate(
    # JSON fields sent as form fields (multipart)
    first_name: str         = Form(...),
    last_name: Optional[str]= Form(None),
    email: str              = Form(...),
    mobile: Optional[str]   = Form(None),
    current_job_title: Optional[str] = Form(None),
    current_employer: Optional[str]  = Form(None),
    current_ctc: Optional[str]       = Form(None),
    expected_ctc: Optional[str]      = Form(None),
    curr_location: Optional[str]     = Form(None),
    notice_period: Optional[str]     = Form(None),
    experience_years: Optional[float]= Form(None),
    source: Optional[str]            = Form(None),
    other_source: Optional[str]      = Form(None),
    requirement_id: Optional[int]    = Form(None),
    skills: Optional[str]            = Form(None),  # JSON array string
    # File uploads
    resume: Optional[UploadFile]       = File(None),
    cover_letter: Optional[UploadFile] = File(None),
    id_proof: Optional[UploadFile]     = File(None),
    others: Optional[UploadFile]       = File(None),
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Add a new candidate with optional file attachments."""
    # Parse skills JSON string from form
    parsed_skills: list = []
    if skills:
        try: parsed_skills = json.loads(skills)
        except Exception: parsed_skills = [s.strip() for s in skills.split(",") if s.strip()]

    payload = CandidateCreate(
        first_name=first_name, last_name=last_name, email=email, mobile=mobile,
        current_job_title=current_job_title, current_employer=current_employer,
        current_ctc=_parse_ctc_amount(current_ctc, "Current CTC"),
        expected_ctc=_parse_ctc_amount(expected_ctc, "Expected CTC"),
        curr_location=curr_location, notice_period=notice_period,
        experience_years=experience_years,
        source=source, other_source=other_source,
        requirement_id=requirement_id, skills=parsed_skills,
    )

    duplicate = svc.find_duplicate_candidate(db, email=payload.email, mobile=payload.mobile)
    if duplicate.duplicate_found:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=duplicate.model_dump())

    # Block assignment to closed requirements
    if requirement_id:
        req_row = db.query(JobRequirement).filter(JobRequirement.id == requirement_id).first()
        if req_row and req_row.status == "Closed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign candidate to a closed requirement.",
            )

    # Save files
    resume_url       = _save_upload(resume,       "recruitment/resumes")
    cover_letter_url = _save_upload(cover_letter, "recruitment/cover_letters")
    id_proof_url     = _save_upload(id_proof,     "recruitment/id_proofs")
    others_url       = _save_upload(others,        "recruitment/others")

    result = svc.create_candidate(
        db, payload, current,
        resume_url=resume_url, cover_letter_url=cover_letter_url,
        id_proof_url=id_proof_url, others_url=others_url,
    )
    if isinstance(result, CandidateDuplicateCheckOut) and result.duplicate_found:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())
    return result


@router.patch("/candidates/{candidate_id}/notes")
def update_notes(
    candidate_id: str,
    payload: RecruiterNotesUpdate,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Update recruiter notes for a candidate."""
    ok = svc.update_recruiter_notes(db, candidate_id, payload.notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"message": "Notes updated"}


# ─────────────────────────────────────────────────────────────────────────────
# Requirements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/requirements", response_model=list[RequirementListItem])
def list_requirements(
    exclude_closed: bool = Query(False, description="Set true to omit Closed requirements (use for dropdowns)"),
    recruiter_ids: Optional[str] = Query(None, description="Comma-separated recruiter employee IDs to filter by"),
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Requirements tab — with visibility rules and optional recruiter filter."""
    role_name = (current.role.name.lower() if current.role else "")
    parsed_ids: Optional[list] = None
    if recruiter_ids:
        try:
            parsed_ids = [int(x.strip()) for x in recruiter_ids.split(",") if x.strip()]
        except ValueError:
            parsed_ids = None
    return svc.list_requirements(
        db,
        exclude_closed=exclude_closed,
        viewer_role=role_name,
        viewer_id=current.id,
        recruiter_ids=parsed_ids,
    )


@router.post("/requirements", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def create_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """Create a new job requirement (recruiter workflow)."""
    return req_svc.create_requirement(db, payload=payload, created_by=current.id)


@router.get("/requirements/{req_id}", response_model=RequirementOut)
def get_requirement(
    req_id: str,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Get a single requirement by REQ-XXXX id."""
    result = req_svc.get_requirement(db, req_id=req_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Requirement {req_id} not found.")
    return result


@router.patch("/requirements/{req_id}", response_model=RequirementOut)
def update_requirement(
    req_id: str,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Update an existing requirement."""
    result = req_svc.update_requirement(db, req_id=req_id, payload=payload)
    if not result:
        raise HTTPException(status_code=404, detail=f"Requirement {req_id} not found.")
    return result


@router.patch("/requirements/{req_id}/close", response_model=RequirementOut)
def close_requirement(
    req_id: str,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Close a requirement (sets status=Closed)."""
    result = req_svc.update_requirement_status(db, req_id=req_id, new_status="Closed")
    if not result:
        raise HTTPException(status_code=404, detail=f"Requirement {req_id} not found.")
    return result


@router.post("/requirements/{req_id}/assign-recruiter")
def assign_recruiter(
    req_id: str,
    payload: AssignRecruiterRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("admin", "hr")),
):
    """Assign (or reassign) a recruiter to a requirement. Admin/HR only."""
    result = svc.assign_recruiter_to_requirement(db, req_id, payload.recruiter_id, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/recruiters")
def list_recruiters(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """List active employees available for recruiter assignment (dropdown)."""
    return svc.list_recruiters(db)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pipeline")
def get_pipeline(
    req: Optional[str] = Query(None, description="Filter by REQ-XXXX"),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Pipeline kanban — candidates grouped by stage."""
    return svc.get_pipeline(db, req_filter=req)


# ─────────────────────────────────────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/interviewers")
def list_interviewers(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """List of all employees available as interviewers (for dropdowns)."""
    return svc.list_interviewers(db)


# ─────────────────────────────────────────────────────────────────────────────
# Interview Slot Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/interviews/{round_id}/slots")
def get_slots(
    round_id: int,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """Return available slots for a round (shown to recruiter and candidate)."""
    return svc.get_interview_slots(db, round_id)


@router.post("/interviews/{round_id}/slots")
def add_slots(
    round_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required(*ROLES)),
):
    """
    Interviewer adds available time slots.
    payload: { slots: [{slot_date: "2026-06-01", slot_time: "14:00"}, ...] }
    """
    slots = (payload or {}).get("slots", [])
    if not slots:
        raise HTTPException(status_code=422, detail="slots array is required")
    result = svc.add_interview_slots(db, round_id, slots, current)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/slots/{slot_id}/select")
def select_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required(*ROLES)),
):
    """
    Recruiter selects an interview slot on behalf of a candidate.
    Marks slot as occupied, updates round to scheduled,
    advances pipeline stage to 'Interview Scheduled',
    and sends notifications to recruiter + interviewer.
    """
    result = svc.select_interview_slot(db, slot_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Close & Onboard — bridge recruitment → onboarding
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/candidates/{candidate_id}/close-and-onboard")
def close_and_onboard_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("admin", "hr")),
):
    """
    Close the recruitment process for a candidate and create an onboarding record.

    Steps:
      1. Validate the recruitment candidate exists and has required fields.
      2. Prevent duplicate — reject if the candidate's email is already in the
         onboarding candidates table.
      3. Create an onboarding Candidate record via the existing onboarding service
         (same logic HR uses when manually adding a candidate).
      4. Advance the candidate_pipeline stage to "Onboarding".
      5. Stamp onboarded_at / onboarded_by on the recruitment_candidates row
         (audit trail).
    """
    from datetime import datetime
    from sqlalchemy import func as _func

    from app.models.recruitment import CandidatePipeline, RecruitmentCandidate
    from api.models import Candidate as OnboardingCandidate
    from api.Onboarding_Model.schemas import CandidateCreate as OBCandidateCreate
    from api.Onboarding_Model.services import candidate_service as ob_svc

    # ── Step 1: load the recruitment candidate ───────────────────────────────
    rc = db.query(RecruitmentCandidate).filter(
        RecruitmentCandidate.candidate_id == candidate_id
    ).first()
    if not rc:
        raise HTTPException(status_code=404, detail="Recruitment candidate not found.")

    # ── Step 2: validate required fields ────────────────────────────────────
    missing = []
    full_name = f"{rc.first_name or ''} {rc.last_name or ''}".strip()
    if not full_name:
        missing.append("Full Name")
    if not rc.email:
        missing.append("Email")
    if not rc.mobile:
        missing.append("Phone")
    if not rc.skills:
        missing.append("Skills")
    if rc.experience_years is None:
        missing.append("Experience")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot onboard — missing required fields: {', '.join(missing)}.",
        )

    # ── Step 3: already onboarded check ─────────────────────────────────────
    if rc.onboarded_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Candidate already moved to onboarding.",
        )

    # ── Step 4: duplicate email in onboarding candidates table ───────────────
    email_lower = rc.email.strip().lower()
    if db.query(OnboardingCandidate).filter(
        _func.lower(OnboardingCandidate.email) == email_lower
    ).first():
        raise HTTPException(
            status_code=400,
            detail="Candidate already moved to onboarding.",
        )

    # ── Step 5: build the onboarding payload ────────────────────────────────
    # last_name is required (min_length=1) in CandidateCreate; use "-" if absent.
    last_name_clean = (rc.last_name or "").strip() or "-"

    # Format expected_ctc as "X LPA" string (onboarding stores CTC as string).
    ctc_str: Optional[str] = None
    if rc.expected_ctc is not None:
        lpa = rc.expected_ctc / 100_000
        ctc_str = f"{lpa:g} LPA"

    # Format mobile (10-digit integer) as E.164 phone.
    phone_str: Optional[str] = None
    if rc.mobile:
        raw = str(rc.mobile)
        if len(raw) == 10:
            phone_str = f"+91{raw}"

    # Role: prefer the current job title from recruitment.
    role = (rc.current_job_title or "").strip() or "Not Specified"

    ob_payload = OBCandidateCreate(
        first_name=rc.first_name.strip(),
        last_name=last_name_clean,
        email=rc.email,
        phone=phone_str,
        role=role,
        department=None,
        ctc=ctc_str,
        expected_joining_date=None,
    )

    # ── Step 6: create onboarding record (reuses the same service HR uses) ──
    ob_candidate = ob_svc.create_candidate(ob_payload, db)

    # ── Step 7: advance pipeline stage to "Onboarding" ──────────────────────
    pipeline = (
        db.query(CandidatePipeline)
        .filter(CandidatePipeline.candidate_id == candidate_id)
        .order_by(CandidatePipeline.id.desc())
        .first()
    )
    if pipeline:
        pipeline.current_stage = "Onboarding"

    # ── Step 8: stamp audit fields on the recruitment record ─────────────────
    rc.onboarded_at = datetime.utcnow()
    rc.onboarded_by = current.id

    db.commit()

    return {
        "message": f"Candidate '{full_name}' has been moved to onboarding.",
        "onboarding_candidate_id": ob_candidate.id,
        "onboarding_ref": ob_candidate.candidate_ref,
        "recruitment_candidate_id": candidate_id,
    }
