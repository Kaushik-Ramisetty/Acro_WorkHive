"""Admin (/admin/*) and manager (/manager/*) resource-management routers.

These complement bench.py — separate so the file stays under 200 lines
and the bench/admin/manager surfaces are independently testable.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee

from api.Resource_Model.schemas import (
    AssignEmployeeIn, CreateProjectAndAssignIn, ExtendProjectIn,
    ProjectCreate, ProjectOut, ReleaseEmployeeIn, TeamMemberOut,
)
from api.Resource_Model.services import (
    ResourceError, assign_employee, create_project, create_project_and_assign,
    extend_project, get_team, list_bench_employees, list_projects,
    release_employee,
)


admin_router = APIRouter(prefix="/admin", tags=["resource-admin"],
                          dependencies=[Depends(role_required("admin"))])
manager_router = APIRouter(prefix="/manager", tags=["resource-manager"],
                            dependencies=[Depends(role_required("manager", "admin"))])


def _wrap(call):
    try:
        return call()
    except ResourceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


def _project_out(p) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        project_manager_id=p.project_manager_id,
        manager_name=(
            " ".join(filter(None, [p.manager.first_name, p.manager.last_name]))
            if p.manager else None
        ),
        start_date=p.start_date,
        end_date=p.end_date,
        status=p.status,
    )


# ===================================================================
# Admin endpoints
# ===================================================================

@admin_router.post("/projects", response_model=ProjectOut, status_code=201)
def admin_create_project(payload: ProjectCreate,
                         db: Session = Depends(get_db),
                         user: Employee = Depends(get_current_user)):
    # Pass `actor` so the project_created audit row records who did it.
    proj = _wrap(lambda: create_project(db, payload, actor=user))
    return _project_out(proj)


@admin_router.get("/projects", response_model=list[ProjectOut])
def admin_list_projects(
    db: Session = Depends(get_db),
    manager_id: Optional[int] = Query(None),
):
    return [_project_out(p) for p in list_projects(db, manager_id=manager_id)]


@admin_router.post("/create-and-assign")
def admin_create_and_assign(payload: CreateProjectAndAssignIn,
                             db: Session = Depends(get_db)):
    return _wrap(lambda: create_project_and_assign(db, payload))


@admin_router.post("/assign-employee")
def admin_assign_employee(payload: AssignEmployeeIn,
                           db: Session = Depends(get_db)):
    return _wrap(lambda: assign_employee(db, payload))


@admin_router.get("/bench-employees")
def admin_bench_lightweight(db: Session = Depends(get_db)):
    """Bench list used by dropdowns. Different from /admin/bench (which
    includes skills + bench_duration_days) — kept narrow on purpose."""
    return list_bench_employees(db)


# ===================================================================
# Manager endpoints
# ===================================================================

@manager_router.get("/team", response_model=list[TeamMemberOut])
def manager_team(db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    """Returns one row per active allocation. An employee on multiple
    projects appears multiple times — the FE uses `${id}-${project_id}` as
    the row key."""
    return get_team(db, user.id)


@manager_router.post("/release-employee")
def manager_release_employee(payload: ReleaseEmployeeIn,
                              db: Session = Depends(get_db),
                              user: Employee = Depends(get_current_user)):
    return _wrap(lambda: release_employee(
        db, user, payload.employee_id, payload.project_id,
    ))


@manager_router.put("/extend-project")
def manager_extend_project(payload: ExtendProjectIn,
                            db: Session = Depends(get_db),
                            user: Employee = Depends(get_current_user)):
    return _wrap(lambda: extend_project(
        db, user, payload.project_id, payload.new_end_date,
    ))
