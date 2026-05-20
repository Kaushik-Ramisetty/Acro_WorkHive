"""Business logic for team management.

Rules enforced here:
  - Unique team name per department (DB UniqueConstraint as belt-and-braces;
    the service translates that into a friendly 409).
  - Team lead must be an active, non-deleted employee.
  - Adding a member already on the team is a no-op (idempotent reactivation
    if the row was previously soft-removed).
  - Deletion is soft (`is_active=False`) so historical composition stays.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Department, Designation, Employee, Project, ResourceAllocation,
    ResourceAllocationAudit, Team, TeamMember,
)
from utils.time_utils import now_utc


logger = logging.getLogger(__name__)


class TeamError(Exception):
    """Bounded business-rule error. Router translates to HTTPException."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _safe_commit(db: Session, *, op: str) -> None:
    """Commit + translate IntegrityError to a friendly 409.

    Defends against races between the up-front uniqueness check and the
    actual INSERT (two admins creating the same team name concurrently).
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("team_model.%s: integrity error → %s", op, exc.orig)
        raise TeamError(409, "Operation conflicts with existing data — please retry.")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("team_model.%s: db error", op)
        raise TeamError(500, "Database error.")


# ---------- helpers -------------------------------------------------

def _full_name(emp: Optional[Employee]) -> Optional[str]:
    if not emp:
        return None
    return " ".join(filter(None, [emp.first_name, emp.last_name]))


def _audit(db: Session, action: str, actor: Optional[Employee] = None, *,
            team_id: Optional[int] = None,
            employee_id: Optional[int] = None,
            payload: Optional[dict] = None,
            note: Optional[str] = None) -> None:
    db.add(ResourceAllocationAudit(
        action=action,
        actor_id=actor.id if actor else None,
        team_id=team_id,
        employee_id=employee_id,
        payload=json.dumps(payload, default=str) if payload else None,
        note=note,
    ))


def _active_member_count(db: Session, team_id: int) -> int:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.is_active.is_(True))
        .count()
    )


def _active_project_ids(db: Session, team_id: int) -> list[str]:
    """Projects associated with any active member of the team via an
    active resource_allocation. Approximation: we don't have a direct
    team_id column on projects, so we treat the union of active
    allocations across active team members as the team's "active project
    set". This is the most useful definition without a separate join table.
    """
    rows = (
        db.query(ResourceAllocation.project_id)
        .join(TeamMember, TeamMember.employee_id == ResourceAllocation.employee_id)
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.is_active.is_(True),
            ResourceAllocation.status == "active",
        )
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows if r[0]})


def team_to_dict(db: Session, t: Team) -> dict:
    """Public serializer — returns the TeamOut-shaped dict for a Team row."""
    return _to_out(db, t)


def _to_out(db: Session, t: Team) -> dict:
    dept = db.get(Department, t.department_id) if t.department_id else None
    lead = db.get(Employee, t.lead_id) if t.lead_id else None
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "department_id": t.department_id,
        "department_name": dept.name if dept else None,
        "lead_id": t.lead_id,
        "lead_name": _full_name(lead),
        "is_active": t.is_active,
        "member_count": _active_member_count(db, t.id),
        "active_project_count": len(_active_project_ids(db, t.id)),
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def _member_to_out(db: Session, m: TeamMember) -> dict:
    emp = db.get(Employee, m.employee_id)
    desig = db.get(Designation, emp.designation_id) if (emp and emp.designation_id) else None
    return {
        "id": m.id,
        "employee_id": m.employee_id,
        "employee_name": _full_name(emp),
        "employee_email": emp.email if emp else None,
        "designation": desig.title if desig else None,
        "role_in_team": m.role_in_team,
        "is_active": m.is_active,
        "added_at": m.added_at,
    }


# ---------- public API ----------------------------------------------

def create_team(db: Session, actor: Employee, payload) -> dict:
    # Uniqueness check up-front for a friendlier error than the DB constraint.
    existing = (
        db.query(Team)
        .filter(Team.name == payload.name.strip(),
                Team.department_id == payload.department_id,
                Team.is_active.is_(True))
        .first()
    )
    if existing:
        raise TeamError(409, f"A team named '{payload.name}' already exists in this department.")

    # Department FK validation — fail with a 400 instead of letting the
    # INSERT trip the foreign-key constraint later.
    if payload.department_id and not db.get(Department, payload.department_id):
        raise TeamError(400, f"Department '{payload.department_id}' does not exist.")

    if payload.lead_id:
        lead = db.get(Employee, payload.lead_id)
        if not lead or lead.is_deleted:
            raise TeamError(400, "Lead must be an active employee.")

    t = Team(
        name=payload.name.strip(),
        description=payload.description,
        department_id=payload.department_id,
        lead_id=payload.lead_id,
        is_active=True,
        created_by=actor.id if actor else None,
    )
    db.add(t)
    db.flush()

    for emp_id in (payload.member_ids or []):
        emp = db.get(Employee, emp_id)
        if not emp or emp.is_deleted:
            continue
        db.add(TeamMember(team_id=t.id, employee_id=emp_id,
                          added_by=actor.id if actor else None))

    _audit(db, "team_created", actor, team_id=t.id,
           payload={"name": t.name, "lead_id": t.lead_id,
                    "members": payload.member_ids or []})
    _safe_commit(db, op="create_team")
    db.refresh(t)
    return _to_out(db, t)


def update_team(db: Session, actor: Employee, team_id: int, payload) -> dict:
    t = db.get(Team, team_id)
    if not t:
        raise TeamError(404, "Team not found")

    changes: dict = {}
    if payload.name is not None and payload.name.strip() != t.name:
        # Uniqueness check on rename.
        clash = (
            db.query(Team)
            .filter(Team.name == payload.name.strip(),
                    Team.department_id == (payload.department_id or t.department_id),
                    Team.id != t.id,
                    Team.is_active.is_(True))
            .first()
        )
        if clash:
            raise TeamError(409, "Another team with that name exists in this department.")
        changes["name"] = (t.name, payload.name.strip())
        t.name = payload.name.strip()

    if payload.description is not None and payload.description != t.description:
        changes["description"] = (t.description, payload.description)
        t.description = payload.description
    if payload.department_id is not None and payload.department_id != t.department_id:
        # FK validation — only when changing to a non-empty department id.
        if payload.department_id and not db.get(Department, payload.department_id):
            raise TeamError(400, f"Department '{payload.department_id}' does not exist.")
        changes["department_id"] = (t.department_id, payload.department_id)
        t.department_id = payload.department_id
    if payload.lead_id is not None and payload.lead_id != t.lead_id:
        if payload.lead_id:
            lead = db.get(Employee, payload.lead_id)
            if not lead or lead.is_deleted:
                raise TeamError(400, "Lead must be an active employee.")
        changes["lead_id"] = (t.lead_id, payload.lead_id)
        t.lead_id = payload.lead_id
        _audit(db, "team_lead_assigned", actor, team_id=t.id,
               payload={"lead_id": payload.lead_id})
    if payload.is_active is not None and payload.is_active != t.is_active:
        changes["is_active"] = (t.is_active, payload.is_active)
        t.is_active = payload.is_active

    if changes:
        _audit(db, "team_updated", actor, team_id=t.id, payload=changes)

    _safe_commit(db, op="update_team")
    db.refresh(t)
    return _to_out(db, t)


def delete_team(db: Session, actor: Employee, team_id: int) -> dict:
    """Soft-delete: flip is_active. Idempotent — re-deleting an already
    inactive team is a no-op (no audit row, no error)."""
    t = db.get(Team, team_id)
    if not t:
        raise TeamError(404, "Team not found")
    if not t.is_active:
        return {"id": team_id, "is_active": False, "already_inactive": True}
    t.is_active = False
    _audit(db, "team_deleted", actor, team_id=t.id)
    _safe_commit(db, op="delete_team")
    return {"id": team_id, "is_active": False, "already_inactive": False}


def list_teams(db: Session, *, include_inactive: bool = False) -> list[dict]:
    q = db.query(Team).order_by(Team.created_at.desc())
    if not include_inactive:
        q = q.filter(Team.is_active.is_(True))
    return [_to_out(db, t) for t in q.all()]


def get_team_detail(db: Session, team_id: int) -> dict:
    t = db.get(Team, team_id)
    if not t:
        raise TeamError(404, "Team not found")
    base = _to_out(db, t)
    members = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.is_active.is_(True))
        .order_by(TeamMember.added_at.asc())
        .all()
    )
    return {
        **base,
        "members": [_member_to_out(db, m) for m in members],
        "active_project_ids": _active_project_ids(db, team_id),
    }


def add_member(db: Session, actor: Employee, team_id: int, payload) -> dict:
    t = db.get(Team, team_id)
    if not t or not t.is_active:
        raise TeamError(404, "Team not found or inactive")
    emp = db.get(Employee, payload.employee_id)
    if not emp or emp.is_deleted:
        raise TeamError(400, "Employee must be active")

    # Reactivate a soft-removed membership if it exists; else create fresh.
    existing = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id,
                TeamMember.employee_id == payload.employee_id)
        .first()
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.removed_at = None
        if payload.role_in_team:
            existing.role_in_team = payload.role_in_team
        member = existing
    else:
        member = TeamMember(
            team_id=team_id,
            employee_id=payload.employee_id,
            role_in_team=payload.role_in_team,
            added_by=actor.id if actor else None,
        )
        db.add(member)

    _audit(db, "team_member_added", actor, team_id=team_id,
           employee_id=payload.employee_id,
           payload={"role_in_team": payload.role_in_team})
    _safe_commit(db, op="add_member")
    db.refresh(member)
    return _member_to_out(db, member)


def remove_member(db: Session, actor: Employee, team_id: int, employee_id: int) -> dict:
    m = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id,
                TeamMember.employee_id == employee_id,
                TeamMember.is_active.is_(True))
        .first()
    )
    if not m:
        raise TeamError(404, "Active membership not found")
    m.is_active = False
    m.removed_at = now_utc()
    _audit(db, "team_member_removed", actor, team_id=team_id,
           employee_id=employee_id)
    _safe_commit(db, op="remove_member")
    return {"team_id": team_id, "employee_id": employee_id, "is_active": False}


def transfer_member(db: Session, actor: Employee, from_team_id: int,
                     to_team_id: int, employee_id: int,
                     role_in_team: Optional[str] = None) -> dict:
    """Atomic move: remove from source team, add to destination team."""
    if from_team_id == to_team_id:
        raise TeamError(400, "Source and destination teams are the same.")
    src = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == from_team_id,
                TeamMember.employee_id == employee_id,
                TeamMember.is_active.is_(True))
        .first()
    )
    if not src:
        raise TeamError(404, "Membership in source team not found.")
    dest = db.get(Team, to_team_id)
    if not dest or not dest.is_active:
        raise TeamError(404, "Destination team not found.")

    src.is_active = False
    src.removed_at = now_utc()
    _audit(db, "team_member_removed", actor, team_id=from_team_id,
           employee_id=employee_id, note="transfer")

    # Reuse if employee was once on dest team.
    existing = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == to_team_id,
                TeamMember.employee_id == employee_id)
        .first()
    )
    if existing:
        existing.is_active = True
        existing.removed_at = None
        if role_in_team:
            existing.role_in_team = role_in_team
        member = existing
    else:
        member = TeamMember(
            team_id=to_team_id, employee_id=employee_id,
            role_in_team=role_in_team,
            added_by=actor.id if actor else None,
        )
        db.add(member)
    _audit(db, "team_member_added", actor, team_id=to_team_id,
           employee_id=employee_id, note="transfer",
           payload={"role_in_team": role_in_team})
    _safe_commit(db, op="transfer_member")
    return {"from_team_id": from_team_id, "to_team_id": to_team_id,
            "employee_id": employee_id}


def team_summary(db: Session) -> dict:
    total_teams = db.query(Team).filter(Team.is_active.is_(True)).count()
    total_members = db.query(TeamMember).filter(TeamMember.is_active.is_(True)).count()
    active_projects = (
        db.query(Project.id)
        .filter(Project.status == "active")
        .count()
    )
    departments_with_teams = (
        db.query(Team.department_id)
        .filter(Team.is_active.is_(True), Team.department_id.isnot(None))
        .distinct()
        .count()
    )
    return {
        "total_teams": total_teams,
        "total_members": total_members,
        "active_projects": active_projects,
        "departments_with_teams": departments_with_teams,
    }
