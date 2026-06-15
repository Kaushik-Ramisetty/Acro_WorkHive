"""Team-management routers — admin (`/admin/teams*`) + manager (`/manager/teams*`).

Admin can full-CRUD. Managers can view +, for teams they lead, manage
members. Authorization is enforced at the route layer; non-admins are
filtered at the service layer where relevant.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee, Team

from api.Team_Model.schemas import (
    TeamCreateIn, TeamDetailOut, TeamMemberIn, TeamMemberOut, TeamOut,
    TeamSummaryOut, TeamUpdateIn,
)
from api.Team_Model.services import (
    TeamError, add_member, create_team, delete_team, get_team_detail,
    list_teams, remove_member, team_summary, team_to_dict, transfer_member,
    update_team,
)


admin_router = APIRouter(prefix="/admin", tags=["teams-admin"],
                          dependencies=[Depends(role_required("admin"))])
manager_router = APIRouter(prefix="/manager", tags=["teams-manager"],
                            dependencies=[Depends(role_required("manager", "admin"))])


def _wrap(call):
    try:
        return call()
    except TeamError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


def _is_lead_or_admin(user: Employee, team: Team) -> bool:
    role = (user.role.name.lower() if user.role else "")
    return role == "admin" or team.lead_id == user.id


# ===================================================================
# Admin
# ===================================================================

@admin_router.get("/teams/summary", response_model=TeamSummaryOut)
def admin_teams_summary(db: Session = Depends(get_db)):
    return team_summary(db)


@admin_router.get("/teams", response_model=list[TeamOut])
def admin_list_teams(
    db: Session = Depends(get_db),
    include_inactive: bool = Query(False),
):
    return list_teams(db, include_inactive=include_inactive)


@admin_router.get("/teams/{team_id}", response_model=TeamDetailOut)
def admin_get_team(team_id: int, db: Session = Depends(get_db)):
    return _wrap(lambda: get_team_detail(db, team_id))


@admin_router.post("/teams", response_model=TeamOut, status_code=201)
def admin_create_team(payload: TeamCreateIn,
                      db: Session = Depends(get_db),
                      user: Employee = Depends(get_current_user)):
    return _wrap(lambda: create_team(db, user, payload))


@admin_router.put("/teams/{team_id}", response_model=TeamOut)
def admin_update_team(team_id: int,
                      payload: TeamUpdateIn,
                      db: Session = Depends(get_db),
                      user: Employee = Depends(get_current_user)):
    return _wrap(lambda: update_team(db, user, team_id, payload))


@admin_router.delete("/teams/{team_id}")
def admin_delete_team(team_id: int,
                      db: Session = Depends(get_db),
                      user: Employee = Depends(get_current_user)):
    return _wrap(lambda: delete_team(db, user, team_id))


@admin_router.post("/teams/{team_id}/members", response_model=TeamMemberOut, status_code=201)
def admin_add_member(team_id: int,
                     payload: TeamMemberIn,
                     db: Session = Depends(get_db),
                     user: Employee = Depends(get_current_user)):
    return _wrap(lambda: add_member(db, user, team_id, payload))


@admin_router.delete("/teams/{team_id}/members/{employee_id}")
def admin_remove_member(team_id: int, employee_id: int,
                         db: Session = Depends(get_db),
                         user: Employee = Depends(get_current_user)):
    return _wrap(lambda: remove_member(db, user, team_id, employee_id))


@admin_router.post("/teams/{from_team_id}/members/{employee_id}/transfer-to/{to_team_id}")
def admin_transfer_member(from_team_id: int, employee_id: int, to_team_id: int,
                           role_in_team: str | None = Query(None),
                           db: Session = Depends(get_db),
                           user: Employee = Depends(get_current_user)):
    return _wrap(lambda: transfer_member(
        db, user, from_team_id, to_team_id, employee_id, role_in_team,
    ))


# ===================================================================
# Manager (team lead)
# ===================================================================

@manager_router.get("/teams", response_model=list[TeamOut])
def manager_list_teams(db: Session = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    """Lists teams the calling user leads (or all teams for admins)."""
    role = (user.role.name.lower() if user.role else "")
    if role == "admin":
        return list_teams(db)
    teams = (
        db.query(Team)
        .filter(Team.is_active.is_(True), Team.lead_id == user.id)
        .order_by(Team.created_at.desc())
        .all()
    )
    return [team_to_dict(db, t) for t in teams]


@manager_router.get("/teams/{team_id}", response_model=TeamDetailOut)
def manager_get_team(team_id: int,
                     db: Session = Depends(get_db),
                     user: Employee = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if not _is_lead_or_admin(user, team):
        raise HTTPException(403, "You are not the lead of this team.")
    return _wrap(lambda: get_team_detail(db, team_id))


@manager_router.post("/teams/{team_id}/members", response_model=TeamMemberOut, status_code=201)
def manager_add_member(team_id: int,
                       payload: TeamMemberIn,
                       db: Session = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if not _is_lead_or_admin(user, team):
        raise HTTPException(403, "Only the team lead or an admin can add members.")
    return _wrap(lambda: add_member(db, user, team_id, payload))


@manager_router.delete("/teams/{team_id}/members/{employee_id}")
def manager_remove_member(team_id: int, employee_id: int,
                           db: Session = Depends(get_db),
                           user: Employee = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if not _is_lead_or_admin(user, team):
        raise HTTPException(403, "Only the team lead or an admin can remove members.")
    return _wrap(lambda: remove_member(db, user, team_id, employee_id))
