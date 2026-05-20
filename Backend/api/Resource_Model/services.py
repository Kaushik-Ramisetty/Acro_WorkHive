"""Business logic for resource management.

Capacity rules:
  - Managers (designation title contains 'manager', 'senior manager', or
    'engineering manager') may have up to 20 active allocations.
  - Everyone else may have up to 3 active allocations.

Project IDs are auto-generated as PRJ001, PRJ002, ... by querying the
current max ID with the PRJ prefix.

Skills are sync-replaced (delete-all + insert) on save — the FE always
submits the full intended set.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Designation, Employee, EmployeeSkill, Project, ResourceAllocation,
    ResourceAllocationAudit,
)
from utils.time_utils import now_utc


logger = logging.getLogger(__name__)


def _write_audit(db: Session, action: str, actor: Optional[Employee] = None,
                  *, employee_id: Optional[int] = None,
                  project_id: Optional[str] = None,
                  allocation_id: Optional[int] = None,
                  team_id: Optional[int] = None,
                  payload: Optional[dict] = None,
                  note: Optional[str] = None) -> None:
    """Append-only audit emit. Caller still owns commit — the audit row is
    flushed with the surrounding transaction so it lands or rolls back
    atomically with the underlying change."""
    db.add(ResourceAllocationAudit(
        action=action,
        employee_id=employee_id,
        project_id=project_id,
        allocation_id=allocation_id,
        team_id=team_id,
        actor_id=actor.id if actor else None,
        payload=(json.dumps(payload, default=str) if payload else None),
        note=note,
    ))


# Designations that get the elevated 20-allocation cap.
_MANAGER_PATTERN = re.compile(r"\b(senior manager|engineering manager|manager)\b", re.IGNORECASE)
MANAGER_CAP = 20
IC_CAP = 3


class ResourceError(Exception):
    """Bounded error raised by the service. Routes translate to HTTPException."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _safe_commit(db: Session, *, op: str) -> None:
    """Commit + translate IntegrityError/SQLAlchemyError to typed errors.

    Defends against races (concurrent assigns hitting the cap, duplicate
    project ids from concurrent _next_project_id races) without leaking
    a 500 to the caller.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("resource_model.%s: integrity error → %s", op, exc.orig)
        raise ResourceError(409, "Operation conflicts with existing data — please retry.")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("resource_model.%s: db error", op)
        raise ResourceError(500, "Database error.")


# ---------- helpers -------------------------------------------------

def _today() -> date:
    return now_utc().date()


def _designation_title(db: Session, employee: Employee) -> str:
    if not employee or not employee.designation_id:
        return ""
    desig = db.get(Designation, employee.designation_id)
    return (desig.title if desig else "") or ""


def _is_manager_role(title: str) -> bool:
    return bool(_MANAGER_PATTERN.search(title or ""))


def _active_alloc_count(db: Session, employee_id: int) -> int:
    return (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.employee_id == employee_id,
            ResourceAllocation.status == "active",
        )
        .count()
    )


def _cap_for(db: Session, employee: Employee) -> int:
    return MANAGER_CAP if _is_manager_role(_designation_title(db, employee)) else IC_CAP


def _next_project_id(db: Session) -> str:
    """Generate the next PRJ### identifier."""
    last = (
        db.query(Project)
        .filter(Project.id.like("PRJ%"))
        .order_by(Project.id.desc())
        .first()
    )
    n = 1
    if last and last.id and last.id.startswith("PRJ"):
        try:
            n = int(last.id[3:]) + 1
        except ValueError:
            pass
    return f"PRJ{n:03d}"


def _employee_skills(db: Session, employee_id: int) -> list[str]:
    return [
        r.skill for r in (
            db.query(EmployeeSkill)
            .filter(EmployeeSkill.employee_id == employee_id)
            .order_by(EmployeeSkill.skill.asc())
            .all()
        )
    ]


def _sync_skills(db: Session, employee_id: int, skills: Iterable[str]) -> None:
    """Replace the employee's skill rows with the supplied set. Caller commits."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in (skills or []):
        s = (s or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s[:80])

    db.query(EmployeeSkill).filter(EmployeeSkill.employee_id == employee_id).delete(
        synchronize_session=False
    )
    db.flush()
    for s in cleaned:
        db.add(EmployeeSkill(employee_id=employee_id, skill=s))
    db.flush()


def _full_name(emp: Optional[Employee]) -> Optional[str]:
    if not emp:
        return None
    return " ".join(filter(None, [emp.first_name, emp.last_name]))


def _latest_active_allocation(db: Session, employee_id: int) -> Optional[ResourceAllocation]:
    return (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.employee_id == employee_id,
            ResourceAllocation.status == "active",
        )
        .order_by(ResourceAllocation.start_date.desc(), ResourceAllocation.id.desc())
        .first()
    )


# ---------- list_employees_with_allocation -------------------------

def list_employees_with_allocation(db: Session) -> list[dict]:
    """Every active employee with a flag and convenience snapshot of their
    most-recent active allocation (used by the admin bench page)."""
    employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.first_name.asc())
        .all()
    )
    out: list[dict] = []
    for e in employees:
        active_count = _active_alloc_count(db, e.id)
        latest = _latest_active_allocation(db, e.id) if active_count else None
        project = db.get(Project, latest.project_id) if latest else None
        mgr = db.get(Employee, latest.manager_id) if (latest and latest.manager_id) else None
        out.append({
            "id": e.id,
            "name": _full_name(e) or e.email,
            "employee_code": e.employee_code,
            "email": e.email,
            "designation": _designation_title(db, e) or None,
            "department": (e.department.name if e.department else None),
            "has_active_allocation": active_count > 0,
            "active_allocation_count": active_count,
            "skills": _employee_skills(db, e.id),
            "experience_years": getattr(e, "experience_years", None),
            "certifications": getattr(e, "certifications", None),
            "latest_project_id": latest.project_id if latest else None,
            "latest_project_name": project.name if project else None,
            "latest_manager_id": latest.manager_id if latest else None,
            "latest_manager_name": _full_name(mgr),
            "latest_start_date": latest.start_date if latest else None,
            "latest_end_date": latest.end_date if latest else None,
        })
    return out


# ---------- list_bench_employees -----------------------------------

def list_bench_employees(db: Session) -> list[dict]:
    """Lightweight — used by dropdowns. No bench-duration math."""
    employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.first_name.asc())
        .all()
    )
    out: list[dict] = []
    for e in employees:
        if _active_alloc_count(db, e.id) > 0:
            continue
        out.append({
            "id": e.id,
            "name": _full_name(e) or e.email,
            "employee_code": e.employee_code,
            "email": e.email,
            "designation": _designation_title(db, e) or None,
        })
    return out


# ---------- list_bench_employees_detail ----------------------------

def list_bench_employees_detail(db: Session) -> list[dict]:
    """Bench employees + skills + days on bench since the most recent
    `actual_end_date` (or 0 if the employee has never been allocated)."""
    today = _today()
    employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.first_name.asc())
        .all()
    )
    out: list[dict] = []
    for e in employees:
        if _active_alloc_count(db, e.id) > 0:
            continue
        # Most recent completed allocation drives the bench-duration math.
        last_completed = (
            db.query(ResourceAllocation)
            .filter(
                ResourceAllocation.employee_id == e.id,
                ResourceAllocation.status == "completed",
            )
            .order_by(
                ResourceAllocation.actual_end_date.desc().nullslast(),
                ResourceAllocation.end_date.desc().nullslast(),
                ResourceAllocation.id.desc(),
            )
            .first()
        )
        if last_completed:
            ref = last_completed.actual_end_date or last_completed.end_date
            duration = max(0, (today - ref).days) if ref else 0
        else:
            duration = 0
        out.append({
            "id": e.id,
            "name": _full_name(e) or e.email,
            "employee_code": e.employee_code,
            "email": e.email,
            "designation": _designation_title(db, e) or None,
            "department": (e.department.name if e.department else None),
            "skills": _employee_skills(db, e.id),
            "experience_years": getattr(e, "experience_years", None),
            "certifications": getattr(e, "certifications", None),
            "bench_duration_days": int(duration),
        })
    return out


# ---------- get_employee_projects ----------------------------------

def get_employee_projects(db: Session, employee_id: int) -> list[dict]:
    """Project history for the admin History modal.

    Deduplicated by project name (case-insensitive); the most recent
    allocation wins. Sorted by start_date desc."""
    rows = (
        db.query(ResourceAllocation)
        .filter(ResourceAllocation.employee_id == employee_id)
        .order_by(ResourceAllocation.start_date.desc(), ResourceAllocation.id.desc())
        .all()
    )
    by_name: dict[str, dict] = {}
    for a in rows:
        proj = db.get(Project, a.project_id)
        name = (proj.name if proj else a.project_id) or a.project_id
        key = name.strip().lower()
        if key in by_name:
            continue  # already kept the most-recent
        mgr = db.get(Employee, a.manager_id) if a.manager_id else None
        by_name[key] = {
            "allocation_id": a.id,
            "project_id": a.project_id,
            "project_name": name,
            "manager_id": a.manager_id,
            "manager_name": _full_name(mgr),
            "start_date": a.start_date,
            "end_date": a.end_date,
            "actual_end_date": a.actual_end_date,
            "status": a.status,
        }
    return list(by_name.values())


# ---------- save_employee_resource_details -------------------------

def save_employee_resource_details(db: Session, employee_id: int, payload) -> dict:
    """Admin save from the Edit modal. Mutations are scoped:

      - If `skills` is given, the full set is replaced.
      - If `project_id` + `start_date` + allocation_status='active' are
        given, an ACTIVE allocation is created/updated for that project.
        (Existing active rows for the same project are extended; otherwise
        a new active row is inserted.)
      - `manager_id` updates the assigned manager on the latest active
        allocation, and the project's project_manager_id if it's null.

    Single transaction; commits at the end.
    """
    emp = db.get(Employee, employee_id)
    if not emp or emp.is_deleted:
        raise ResourceError(404, "Employee not found")

    if payload.skills is not None:
        _sync_skills(db, employee_id, payload.skills)
        _write_audit(db, "skills_synced",
                     employee_id=employee_id,
                     payload={"skills": list(payload.skills)})

    # Resource-profile fields (Phase 6). No allocation effect.
    profile_changes: dict = {}
    if payload.experience_years is not None and payload.experience_years != getattr(emp, "experience_years", None):
        profile_changes["experience_years"] = (getattr(emp, "experience_years", None), payload.experience_years)
        emp.experience_years = payload.experience_years
    if payload.certifications is not None and (payload.certifications or None) != getattr(emp, "certifications", None):
        profile_changes["certifications"] = (getattr(emp, "certifications", None), payload.certifications or None)
        emp.certifications = (payload.certifications or None)
    if profile_changes:
        _write_audit(db, "allocation_updated",
                     employee_id=employee_id,
                     payload=profile_changes,
                     note="employee profile fields updated")

    if payload.project_id:
        proj = db.get(Project, payload.project_id)
        if not proj:
            raise ResourceError(404, f"Project '{payload.project_id}' not found")

        # Look for an existing active allocation on this project. If found,
        # update its window + manager. If not, create one (subject to cap).
        existing = (
            db.query(ResourceAllocation)
            .filter(
                ResourceAllocation.employee_id == employee_id,
                ResourceAllocation.project_id == payload.project_id,
                ResourceAllocation.status == "active",
            )
            .first()
        )
        if existing:
            if payload.start_date:
                existing.start_date = payload.start_date
            if payload.end_date is not None:
                existing.end_date = payload.end_date
            if payload.manager_id is not None:
                existing.manager_id = payload.manager_id
        else:
            if (payload.allocation_status or "active").lower() == "active":
                cap = _cap_for(db, emp)
                if _active_alloc_count(db, employee_id) >= cap:
                    raise ResourceError(
                        409,
                        f"Cap reached: {cap} active allocation(s) for this employee.",
                    )
                if not payload.start_date:
                    raise ResourceError(400, "start_date is required for a new allocation.")
                db.add(ResourceAllocation(
                    employee_id=employee_id,
                    project_id=payload.project_id,
                    manager_id=payload.manager_id,
                    start_date=payload.start_date,
                    end_date=payload.end_date,
                    status="active",
                ))

        if payload.manager_id is not None and not proj.project_manager_id:
            proj.project_manager_id = payload.manager_id

    _safe_commit(db, op="save_employee_resource_details")
    return {"ok": True}


# ---------- create_project -----------------------------------------

def create_project(db: Session, payload, *, actor: Optional[Employee] = None) -> Project:
    proj = Project(
        id=_next_project_id(db),
        name=payload.name.strip(),
        project_manager_id=payload.manager_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        client_name=payload.client_name,
        department_id=payload.department_id,
        status="active",
    )
    db.add(proj)
    db.flush()
    _write_audit(db, "project_created", actor,
                 project_id=proj.id,
                 payload={"name": proj.name, "manager_id": proj.project_manager_id})
    _safe_commit(db, op="create_project")
    db.refresh(proj)
    return proj


def list_projects(db: Session, *, manager_id: Optional[int] = None) -> list[Project]:
    q = db.query(Project)
    if manager_id is not None:
        q = q.filter(Project.project_manager_id == manager_id)
    return q.order_by(Project.id.desc()).all()


# ---------- create_project_and_assign ------------------------------

def create_project_and_assign(db: Session, payload) -> dict:
    """Single transaction: create a new project, then allocate the employee."""
    emp = db.get(Employee, payload.employee_id)
    if not emp or emp.is_deleted:
        raise ResourceError(404, "Employee not found")

    cap = _cap_for(db, emp)
    if (payload.allocation_status or "active").lower() == "active" \
            and _active_alloc_count(db, payload.employee_id) >= cap:
        raise ResourceError(409, f"Cap reached: {cap} active allocation(s).")

    proj = Project(
        id=_next_project_id(db),
        name=payload.project_name.strip(),
        project_manager_id=payload.manager_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="active",
    )
    db.add(proj)
    db.flush()

    alloc = ResourceAllocation(
        employee_id=payload.employee_id,
        project_id=proj.id,
        manager_id=payload.manager_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=(payload.allocation_status or "active").lower(),
    )
    db.add(alloc)

    if payload.skills:
        _sync_skills(db, payload.employee_id, payload.skills)
        _write_audit(db, "skills_synced",
                     employee_id=payload.employee_id,
                     payload={"skills": list(payload.skills)})

    _write_audit(db, "project_created",
                 employee_id=payload.employee_id, project_id=proj.id,
                 payload={"name": proj.name})
    _write_audit(db, "allocation_created",
                 employee_id=payload.employee_id, project_id=proj.id,
                 allocation_id=alloc.id,
                 payload={
                     "start_date": str(payload.start_date),
                     "end_date": str(payload.end_date) if payload.end_date else None,
                     "manager_id": payload.manager_id,
                     "status": alloc.status,
                 })
    _safe_commit(db, op="create_project_and_assign")
    db.refresh(proj)
    db.refresh(alloc)
    return {"project_id": proj.id, "project_name": proj.name, "allocation_id": alloc.id}


# ---------- assign_employee ----------------------------------------

def assign_employee(db: Session, payload) -> dict:
    emp = db.get(Employee, payload.employee_id)
    if not emp or emp.is_deleted:
        raise ResourceError(404, "Employee not found")
    proj = db.get(Project, payload.project_id)
    if not proj:
        raise ResourceError(404, f"Project '{payload.project_id}' not found")

    is_active = (payload.allocation_status or "active").lower() == "active"
    if is_active:
        cap = _cap_for(db, emp)
        if _active_alloc_count(db, payload.employee_id) >= cap:
            raise ResourceError(409, f"Cap reached: {cap} active allocation(s).")

    # If a duplicate active allocation on this project already exists,
    # update it in place rather than creating a second row.
    existing = (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.employee_id == payload.employee_id,
            ResourceAllocation.project_id == payload.project_id,
            ResourceAllocation.status == "active",
        )
        .first()
    )
    if existing:
        existing.start_date = payload.start_date
        if payload.end_date is not None:
            existing.end_date = payload.end_date
        if payload.manager_id is not None:
            existing.manager_id = payload.manager_id
        alloc = existing
    else:
        alloc = ResourceAllocation(
            employee_id=payload.employee_id,
            project_id=payload.project_id,
            manager_id=payload.manager_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status="active" if is_active else "completed",
        )
        db.add(alloc)

    if payload.manager_id is not None and not proj.project_manager_id:
        proj.project_manager_id = payload.manager_id

    if payload.skills:
        _sync_skills(db, payload.employee_id, payload.skills)
        _write_audit(db, "skills_synced",
                     employee_id=payload.employee_id,
                     payload={"skills": list(payload.skills)})

    _write_audit(
        db,
        "allocation_updated" if existing else "allocation_created",
        employee_id=payload.employee_id,
        project_id=payload.project_id,
        allocation_id=alloc.id,
        payload={
            "start_date": str(payload.start_date),
            "end_date": str(payload.end_date) if payload.end_date else None,
            "manager_id": payload.manager_id,
            "status": alloc.status,
        },
    )
    _safe_commit(db, op="assign_employee")
    db.refresh(alloc)
    return {"allocation_id": alloc.id, "project_id": alloc.project_id}


# ---------- get_team (manager-facing) ------------------------------

def get_team(db: Session, manager_id: int) -> list[dict]:
    """My Team for a manager — union of THREE relationship sources:

    1. **Direct reports**:  Employee.reporting_manager_id = manager_id
    2. **Allocation manager**: an active ResourceAllocation where
       `allocation.manager_id = manager_id` (the admin assigned this
       employee to a project under this manager).
    3. **Project manager**: an active ResourceAllocation on a project
       where `project.project_manager_id = manager_id`.

    Why all three?
      - The reporting line (#1) is HR's source of truth for "who do you
        line-manage", and was the only thing the previous implementation
        consulted. That meant employees the admin **assigned** to a
        project under this manager from the Bench page (via
        /admin/assign-employee, /admin/reassign, or the Edit modal)
        never showed up in My Team — only their `allocation.manager_id`
        moved, not `Employee.reporting_manager_id`. That's the bug we
        fix here.
      - #2 and #3 surface employees the manager is currently
        responsible for delivery-wise even if their formal reporting
        line points elsewhere. RBAC for `release_employee` already uses
        the same union, so the team view now matches what the manager
        is actually empowered to act on.

    Row emission:
      - One row per **active allocation** under the manager, or one
        no-allocation row for direct reports without any allocation.
      - An employee with multiple active allocations under the same
        manager appears once per allocation (FE keys on
        `${employee_id}-${project_id}`).
      - Allocations under OTHER managers are NOT emitted (a direct
        report assigned to a different manager's project shows up
        only via their no-allocation row from this manager's
        perspective — the row they "owe" to the other manager
        belongs in that other manager's team view).
    """
    # ── Source 1: direct reports ────────────────────────────────────
    direct_report_ids = {
        e_id for (e_id,) in db.query(Employee.id)
        .filter(
            Employee.reporting_manager_id == manager_id,
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    }

    # ── Sources 2 & 3: active allocations under this manager ────────
    # We pull the (employee_id, allocation) tuples in one go so we can
    # emit them deterministically and also union the employee ids into
    # the direct-report set above.
    alloc_rows = (
        db.query(ResourceAllocation)
        .join(Employee, ResourceAllocation.employee_id == Employee.id)
        .outerjoin(Project, ResourceAllocation.project_id == Project.id)
        .filter(
            ResourceAllocation.status == "active",
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
            or_(
                ResourceAllocation.manager_id == manager_id,
                Project.project_manager_id == manager_id,
            ),
        )
        .order_by(ResourceAllocation.start_date.asc(), ResourceAllocation.id.asc())
        .all()
    )

    # Bucket allocations by employee id so we can pair them with the
    # employee row in one pass below.
    allocs_by_emp: dict[int, list[ResourceAllocation]] = {}
    for a in alloc_rows:
        allocs_by_emp.setdefault(a.employee_id, []).append(a)

    team_emp_ids = direct_report_ids | set(allocs_by_emp.keys())
    if not team_emp_ids:
        return []

    employees = (
        db.query(Employee)
        .filter(Employee.id.in_(team_emp_ids))
        .all()
    )

    out: list[dict] = []
    for emp in employees:
        emp_role = _designation_title(db, emp) or None
        emp_dept = (emp.department.name if emp.department else None)
        emp_allocs = allocs_by_emp.get(emp.id, [])

        if not emp_allocs:
            # Direct report with no allocation under this manager.
            # Surface them so they're visible on the team view; FE hides
            # Release/Extend buttons for `allocation_id=None` rows.
            out.append({
                "id": emp.id,
                "name": _full_name(emp) or emp.email,
                "role": emp_role,
                "dept": emp_dept,
                "email": emp.email,
                "employee_code": emp.employee_code,
                "allocation_id": None,
                "project_id": None,
                "project_name": None,
                "proj_start": None,
                "proj_end": None,
            })
            continue

        for a in emp_allocs:
            proj = db.get(Project, a.project_id)
            out.append({
                "id": emp.id,
                "name": _full_name(emp) or emp.email,
                "role": emp_role,
                "dept": emp_dept,
                "email": emp.email,
                "employee_code": emp.employee_code,
                "allocation_id": a.id,
                "project_id": a.project_id,
                "project_name": proj.name if proj else a.project_id,
                "proj_start": a.start_date,
                "proj_end": a.end_date,
            })

    # Sort by employee name then project_id for stable rendering.
    out.sort(key=lambda r: (
        (r["name"] or "").lower(),
        r["project_id"] is None,
        r["project_id"] or "",
    ))
    return out


# ---------- release_employee ---------------------------------------

def release_employee(db: Session, manager: Employee, employee_id: int,
                      project_id: str) -> dict:
    """Manager releases an employee from a specific project.

    Sets the allocation status to 'completed' and stamps actual_end_date
    to today. RBAC: the actor must be the allocation's `manager_id`, the
    project's `project_manager_id`, or an admin."""
    alloc = (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.employee_id == employee_id,
            ResourceAllocation.project_id == project_id,
            ResourceAllocation.status == "active",
        )
        .first()
    )
    if not alloc:
        raise ResourceError(404, "Active allocation not found for that employee + project.")

    proj = db.get(Project, project_id)
    is_admin = bool(manager.role and manager.role.name.lower() == "admin")
    # Build the authorized-manager set explicitly so we never accidentally
    # admit a caller because the membership-check membership happened to
    # contain None (e.g. when alloc.manager_id is NULL and manager.id was
    # also somehow None in tests). RBAC rule: actor must be the allocation
    # manager OR the project manager OR an admin.
    authorized_mgr_ids = {x for x in (alloc.manager_id, proj.project_manager_id if proj else None) if x is not None}
    if not is_admin and manager.id not in authorized_mgr_ids:
        raise ResourceError(403, "You are not the manager of this allocation.")

    alloc.status = "completed"
    alloc.actual_end_date = _today()
    _write_audit(db, "allocation_released", manager,
                 employee_id=employee_id, project_id=project_id,
                 allocation_id=alloc.id,
                 payload={"actual_end_date": str(alloc.actual_end_date)})
    _safe_commit(db, op="release_employee")
    return {"allocation_id": alloc.id, "released_on": alloc.actual_end_date}


# ---------- extend_project -----------------------------------------

def extend_project(db: Session, manager: Employee, project_id: str,
                    new_end_date: date) -> dict:
    """Extend a project's end_date and cascade to all its active
    allocations. Only the project manager or an admin may extend."""
    proj = db.get(Project, project_id)
    if not proj:
        raise ResourceError(404, "Project not found")

    is_admin = (manager.role and manager.role.name.lower() == "admin")
    if not is_admin and proj.project_manager_id != manager.id:
        raise ResourceError(403, "Only the project's manager (or an admin) can extend.")

    if proj.start_date and new_end_date < proj.start_date:
        raise ResourceError(400, "new_end_date is before the project's start_date.")

    proj.end_date = new_end_date
    updated = 0
    actives = (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.project_id == project_id,
            ResourceAllocation.status == "active",
        )
        .all()
    )
    for a in actives:
        a.end_date = new_end_date
        updated += 1
    _write_audit(db, "allocation_extended", manager,
                 project_id=project_id,
                 payload={"new_end_date": str(new_end_date),
                          "allocations_updated": updated})
    _safe_commit(db, op="extend_project")
    return {
        "project_id": proj.id,
        "new_end_date": new_end_date,
        "allocations_updated": updated,
    }


# ---------- reassign_employee --------------------------------------

def reassign_employee(db: Session, actor: Employee, payload) -> dict:
    """Atomic move: complete the active allocation on from_project and
    open a new active allocation on to_project. Single transaction."""
    emp = db.get(Employee, payload.employee_id)
    if not emp or emp.is_deleted:
        raise ResourceError(404, "Employee not found")

    src = (
        db.query(ResourceAllocation)
        .filter(
            ResourceAllocation.employee_id == payload.employee_id,
            ResourceAllocation.project_id == payload.from_project_id,
            ResourceAllocation.status == "active",
        )
        .first()
    )
    if not src:
        raise ResourceError(404, "Active allocation on source project not found.")

    dest_project = db.get(Project, payload.to_project_id)
    if not dest_project:
        raise ResourceError(404, f"Target project '{payload.to_project_id}' not found.")

    # Cap math: closing src + opening dest is net-zero, so we don't need a
    # second cap check unless we're moving onto an additional project while
    # the source is from a non-existent allocation — handled by the check above.
    src.status = "completed"
    src.actual_end_date = _today()

    new_alloc = ResourceAllocation(
        employee_id=payload.employee_id,
        project_id=payload.to_project_id,
        manager_id=payload.manager_id if payload.manager_id is not None else dest_project.project_manager_id,
        start_date=payload.new_start_date,
        end_date=payload.new_end_date,
        status="active",
    )
    db.add(new_alloc)
    db.flush()
    _write_audit(db, "allocation_reassigned", actor,
                 employee_id=payload.employee_id,
                 project_id=payload.to_project_id,
                 allocation_id=new_alloc.id,
                 payload={
                     "from_project_id": payload.from_project_id,
                     "from_allocation_id": src.id,
                     "new_start_date": str(payload.new_start_date),
                     "new_end_date": str(payload.new_end_date) if payload.new_end_date else None,
                 })
    _safe_commit(db, op="reassign_employee")
    db.refresh(new_alloc)
    return {
        "released_allocation_id": src.id,
        "new_allocation_id": new_alloc.id,
        "to_project_id": payload.to_project_id,
    }
