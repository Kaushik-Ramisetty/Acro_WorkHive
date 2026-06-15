"""
Skill service backed by skill_set and skill_requests tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.recruitment import RequirementSkill
from app.models.skill_set import SkillRequest, SkillSet


def _next_skill_request_id(db: Session) -> int:
    last_id = (
        db.query(SkillRequest.id)
        .filter(SkillRequest.id.is_not(None))
        .order_by(SkillRequest.id.desc())
        .first()
    )
    return int(last_id[0]) + 1 if last_id and last_id[0] is not None else 1


def _ensure_global_skill_request_ids(db: Session) -> None:
    """Backfill missing IDs caused by legacy SQLite schema allowing NULL primary keys."""
    null_rows = db.execute(
        text("SELECT rowid FROM skill_requests WHERE id IS NULL ORDER BY rowid")
    ).fetchall()
    if not null_rows:
        return

    next_id = _next_skill_request_id(db)
    for (rowid,) in null_rows:
        db.execute(
            text("UPDATE skill_requests SET id = :id WHERE rowid = :rowid"),
            {"id": next_id, "rowid": rowid},
        )
        next_id += 1
    db.commit()


def ensure_skill_set_added_at(db: Session) -> None:
    """Backfill missing added_at timestamps for legacy skill_set rows."""
    null_rows = db.execute(
        text("SELECT rowid FROM skill_set WHERE added_at IS NULL ORDER BY rowid")
    ).fetchall()
    if not null_rows:
        return

    now = datetime.now(timezone.utc)
    for (rowid,) in null_rows:
        db.execute(
            text("UPDATE skill_set SET added_at = :added_at WHERE rowid = :rowid"),
            {"added_at": now, "rowid": rowid},
        )
    db.commit()


def search_skills(query: str, db: Session, limit: int = 10) -> list[dict]:
    """Case-insensitive partial match against skill_set."""
    ensure_skill_set_added_at(db)
    if not query or len(query.strip()) < 2:
        return []

    pattern = f"%{query.strip()}%"
    rows = (
        db.query(SkillSet)
        .filter(SkillSet.skill_name.ilike(pattern), SkillSet.is_active == 1)
        .order_by(SkillSet.skill_name)
        .limit(limit)
        .all()
    )
    return [{"id": r.id, "name": r.skill_name} for r in rows]


def list_all_skills(db: Session) -> list[dict]:
    """Return all active skills for the dropdown."""
    ensure_skill_set_added_at(db)
    rows = (
        db.query(SkillSet)
        .filter(SkillSet.is_active == 1)
        .order_by(SkillSet.skill_name)
        .all()
    )
    return [{"id": r.id, "name": r.skill_name} for r in rows]


def skill_exists_in_master(skill_name: str, db: Session) -> bool:
    """Case-insensitive exact match against skill_set."""
    ensure_skill_set_added_at(db)
    return (
        db.query(SkillSet)
        .filter(SkillSet.skill_name.ilike(skill_name.strip()), SkillSet.is_active == 1)
        .first()
    ) is not None


def add_skill_to_master(skill_name: str, db: Session, added_by: str = "system") -> SkillSet:
    """
    Insert a new skill into skill_set (idempotent).
    Called when HR Admin approves a skill_request.
    """
    ensure_skill_set_added_at(db)
    existing = (
        db.query(SkillSet)
        .filter(SkillSet.skill_name.ilike(skill_name.strip()))
        .first()
    )
    if existing:
        existing.is_active = 1
        if existing.added_at is None:
            existing.added_at = datetime.now(timezone.utc)
        db.commit()
        return existing

    last = db.query(SkillSet).order_by(SkillSet.id.desc()).first()
    try:
        last_num = int(last.id[3:]) if last else 0
    except (ValueError, TypeError):
        last_num = 0
    new_id = f"SKL{(last_num + 1):03d}"

    skill = SkillSet(
        id=new_id,
        skill_name=skill_name.strip(),
        is_active=1,
        added_by=added_by,
        added_at=datetime.now(timezone.utc),
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def create_global_skill_request(
    db: Session, skill_name: str, requested_by: int
) -> SkillRequest:
    """
    Create a global skill request.
    Idempotent: returns an existing pending request for the same skill.
    """
    _ensure_global_skill_request_ids(db)

    existing = (
        db.query(SkillRequest)
        .filter(
            SkillRequest.skill_name.ilike(skill_name.strip()),
            SkillRequest.status == "pending",
        )
        .first()
    )
    if existing:
        return existing

    req = SkillRequest(
        id=_next_skill_request_id(db),
        skill_name=skill_name.strip(),
        requested_by=requested_by,
        requested_at=datetime.now(timezone.utc),
        status="pending",
    )
    db.add(req)
    db.commit()
    return req


def list_skill_requests(db: Session, status: Optional[str] = None) -> list[SkillRequest]:
    """List global skill requests, optionally filtered by status."""
    _ensure_global_skill_request_ids(db)
    q = db.query(SkillRequest).order_by(SkillRequest.requested_at.desc())
    if status:
        q = q.filter(SkillRequest.status == status)
    return q.all()


def approve_skill_request(
    db: Session, request_id: int, approved_by: int
) -> Optional[SkillRequest]:
    """
    HR Admin approves a pending skill request.
    Inserts the skill into skill_set and marks request approved.
    """
    _ensure_global_skill_request_ids(db)
    req = db.query(SkillRequest).filter(SkillRequest.id == request_id).first()
    if not req:
        return None

    approver_emp = db.query(__import__("app.models", fromlist=["Employee"]).Employee).filter_by(id=approved_by).first()
    approver_code = approver_emp.employee_code if approver_emp else str(approved_by)
    add_skill_to_master(req.skill_name, db=db, added_by=approver_code)

    req.status = "approved"
    req.approved_by = approved_by
    req.approved_at = datetime.now(timezone.utc)
    db.commit()
    return req


def reject_skill_request(
    db: Session, request_id: int, approved_by: int, reason: Optional[str] = None
) -> Optional[SkillRequest]:
    """HR Admin rejects a pending skill request."""
    _ensure_global_skill_request_ids(db)
    req = db.query(SkillRequest).filter(SkillRequest.id == request_id).first()
    if not req:
        return None
    req.status = "rejected"
    req.approved_by = approved_by
    req.approved_at = datetime.now(timezone.utc)
    req.rejection_reason = reason
    db.commit()
    return req


def create_skill_request(
    db: Session,
    requirement_id: int,
    skill_name: str,
    requested_by: int,
    is_primary: bool = False,
) -> RequirementSkill:
    """
    Legacy: create a pending entry in requirement_skills for a specific requirement.
    """
    existing = (
        db.query(RequirementSkill)
        .filter(
            RequirementSkill.requirement_id == requirement_id,
            RequirementSkill.skill_name == skill_name.strip(),
        )
        .first()
    )
    if existing:
        return existing

    row = RequirementSkill(
        requirement_id=requirement_id,
        skill_name=skill_name.strip(),
        is_primary=is_primary,
        status="pending",
        requested_by=str(requested_by),
        requested_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_pending_skill_requests(
    db: Session, requirement_id: Optional[int] = None
) -> list[RequirementSkill]:
    """Pending entries in requirement_skills."""
    q = db.query(RequirementSkill).filter(RequirementSkill.status == "pending")
    if requirement_id:
        q = q.filter(RequirementSkill.requirement_id == requirement_id)
    return q.order_by(RequirementSkill.requested_at.desc()).all()


def approve_skill_request_for_requirement(
    db: Session, skill_request_id: int, approved_by: int
) -> Optional[RequirementSkill]:
    """Approve a per-requirement skill entry."""
    row = db.query(RequirementSkill).filter(RequirementSkill.id == skill_request_id).first()
    if not row:
        return None
    row.status = "approved"
    row.approved_by = str(approved_by)
    row.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
