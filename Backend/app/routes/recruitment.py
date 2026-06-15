"""
Recruitment routes — Manager & Recruiter endpoints.
Prefix: /recruitment
Auth:   Core HRMS JWT via role_required()
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee, Department
from app.schemas.recruitment import (
    ApprovalAction,
    CandidateOut,
    DashboardStats,
    RequirementCreate,
    RequirementOut,
    RequirementStatusUpdate,
    SkillRequestCreate,
    SkillRequestOut,
    SkillSearchResponse,
    SkillItem,
)
from app.services import recruitment_service as svc
from app.services import skill_service as skill_svc

router = APIRouter(prefix="/recruitment", tags=["recruitment"])


# ─────────────────────────────────────────────────────────────────────────────
# Departments (for dynamic dropdown in Create Requirement form)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/departments")
def list_departments_for_recruitment(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required("manager", "admin", "employee")),
):
    """
    Return all departments for the requirement form department dropdown.
    Returns id (value) and name (label) — same shape as the static list it replaces.
    """
    rows = (
        db.query(Department)
        .order_by(Department.name)
        .all()
    )
    return [{"id": r.id, "name": r.name} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Skills — master list + search + global request
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/skills", response_model=list[SkillItem])
def list_all_skills(
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required("manager", "admin", "employee")),
):
    """
    Return ALL active skills from skill_set master table.
    Used to populate the multi-select dropdown on initial load (no search term yet).
    """
    results = skill_svc.list_all_skills(db)
    return [SkillItem(name=r["name"]) for r in results]


@router.get("/skills/search", response_model=SkillSearchResponse)
def search_skills(
    q: str = Query(..., min_length=2, description="Minimum 2 characters required"),
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required("manager", "admin", "employee")),
):
    """
    Autocomplete skill search — case-insensitive partial match against skill_set DB table.
    Frontend calls this after the user types >= 2 characters.
    """
    results = skill_svc.search_skills(q, db=db, limit=limit)
    return SkillSearchResponse(
        results=[SkillItem(name=r["name"]) for r in results],
        query=q,
        total=len(results),
    )


@router.post("/skills/request-global", status_code=status.HTTP_201_CREATED)
def request_new_skill_global(
    payload: dict,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("employee", "manager", "admin")),
):
    """
    Recruiter or manager requests a NEW skill to be added to the master skill_set.
    The skill goes to HR Admin for approval — NOT inserted directly.
    Idempotent: returns existing pending request if one exists for this skill.
    """
    skill_name = (payload.get("skill_name") or "").strip()
    if not skill_name:
        raise HTTPException(status_code=422, detail="skill_name is required.")

    if skill_svc.skill_exists_in_master(skill_name, db=db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{skill_name}' already exists in the master skill list.",
        )

    req = skill_svc.create_global_skill_request(
        db=db, skill_name=skill_name, requested_by=current.id
    )
    return {
        "id": req.id,
        "skill_name": req.skill_name,
        "status": req.status,
        "requested_at": req.requested_at.isoformat(),
        "message": f"Skill '{skill_name}' request submitted — pending HR Admin approval.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Skills — per-requirement (backward-compatible, unchanged behaviour)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/skills/request", response_model=SkillRequestOut, status_code=status.HTTP_201_CREATED)
def request_new_skill(
    payload: SkillRequestCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("employee", "manager", "admin")),
):
    """
    Per-requirement skill request (recruiter workflow — unchanged).
    Creates a pending entry in requirement_skills tied to a specific requirement.
    """
    if skill_svc.skill_exists_in_master(payload.skill_name, db=db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill '{payload.skill_name}' already exists in the master list.",
        )
    row = skill_svc.create_skill_request(
        db=db,
        requirement_id=payload.requirement_id,
        skill_name=payload.skill_name,
        requested_by=current.id,
        is_primary=payload.is_primary,
    )
    return SkillRequestOut(
        id=row.id,
        skill_name=row.skill_name,
        requirement_id=row.requirement_id,
        status=row.status,
        requested_at=row.requested_at,
    )


@router.get("/skills/pending", response_model=list[SkillRequestOut])
def list_pending_skills(
    requirement_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _current: Employee = Depends(role_required("manager", "admin", "employee")),
):
    """List per-requirement pending skill requests (recruiter workflow)."""
    rows = skill_svc.get_pending_skill_requests(db, requirement_id=requirement_id)
    return [
        SkillRequestOut(
            id=r.id,
            skill_name=r.skill_name,
            requirement_id=r.requirement_id,
            status=r.status,
            requested_at=r.requested_at,
        )
        for r in rows
    ]


@router.post("/skills/approve/{skill_request_id}", response_model=SkillRequestOut)
def approve_requirement_skill(
    skill_request_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("admin", "employee")),
):
    """Recruiter approves a per-requirement pending skill (requirement_skills table)."""
    row = skill_svc.approve_skill_request_for_requirement(
        db, skill_request_id, approved_by=current.id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Skill request not found.")
    return SkillRequestOut(
        id=row.id,
        skill_name=row.skill_name,
        requirement_id=row.requirement_id,
        status=row.status,
        requested_at=row.requested_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """Recruitment dashboard stats scoped to this manager's requirements."""
    return svc.get_dashboard_stats(db, manager_id=current.id)


# ─────────────────────────────────────────────────────────────────────────────
# Requirements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/requirements", response_model=list[RequirementOut])
def list_requirements(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """List all requirements created by the current manager."""
    return svc.list_requirements(db, created_by=current.id, status=status_filter)


@router.post("/requirements", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def create_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """Create a new job requirement."""
    return svc.create_requirement(db, payload=payload, created_by=current.id)


@router.get("/requirements/{req_id}", response_model=RequirementOut)
def get_requirement(
    req_id: str,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin", "employee")),
):
    """Get a single requirement by its REQ-XXXX identifier."""
    result = svc.get_requirement(db, req_id=req_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Requirement {req_id} not found.")
    return result


@router.patch("/requirements/{req_id}/status", response_model=RequirementOut)
def update_requirement_status(
    req_id: str,
    payload: RequirementStatusUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """Update the status of a requirement."""
    result = svc.update_requirement_status(db, req_id=req_id, new_status=payload.status)
    if not result:
        raise HTTPException(status_code=404, detail=f"Requirement {req_id} not found.")
    return result

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline / Candidates
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/pipeline", response_model=list[CandidateOut])
def get_pipeline(
    req: Optional[str] = Query(None, description="Filter by REQ-XXXX string"),
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """Return all pipeline candidates across this manager's requirements."""
    return svc.list_pipeline(db, manager_id=current.id, req_id=req)


@router.post("/pipeline/{pipeline_id}/approve", response_model=CandidateOut)
def approve_candidate(
    pipeline_id: int,
    payload: ApprovalAction,
    db: Session = Depends(get_db),
    current: Employee = Depends(role_required("manager", "admin")),
):
    """Manager approve or reject a candidate at the Manager Approval stage."""
    if payload.action == "approve":
        result = svc.approve_candidate(
            db, pipeline_id=pipeline_id, manager_id=current.id, remark=payload.remark
        )
    else:
        result = svc.reject_candidate(
            db, pipeline_id=pipeline_id, manager_id=current.id, reason=payload.rejection_reason
        )
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline entry not found.")
    return result
