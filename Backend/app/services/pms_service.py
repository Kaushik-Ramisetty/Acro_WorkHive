"""PMS Phase-1 service: state machine, assignment generation, notifications, audit."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    GoalTemplate,
    TemplateKRA,
    TemplateKPI,
    TemplateCompetency,
    GoalAssignment,
    AssignedKRA,
    AssignedKPI,
    AssignedCompetency,
    GoalComment,
    Role,
)
from app.models.pms import (
    PMS_STATUS_DRAFT,
    PMS_STATUS_GOALS_SENT,
    PMS_STATUS_UNDER_DISCUSSION,
    PMS_STATUS_EMPLOYEE_CONFIRMED,
    PMS_STATUS_MANAGER_APPROVED,
    PMS_STATUS_HR_REVIEWED,
    PMS_STATUS_GOALS_LOCKED,
    LOCK_TYPE_MANUAL,
    LOCK_TYPE_AUTO,
)
from app.models.pms_settings import PMSPhaseSettings
from app.services.audit_service import write_audit
from app.services.notification_service import notify, notify_many
import app.services.pms_email_service as pms_email

_FALLBACK_DEADLINE_DAYS = 14


# ── Helpers ────────────────────────────────────────────────────────


def role_name(emp: Employee) -> str:
    return (emp.role.name.lower() if emp and emp.role else "") or ""


def full_name(emp: Optional[Employee]) -> str:
    if not emp:
        return ""
    fn = (emp.first_name or "").strip()
    ln = (emp.last_name or "").strip()
    return (fn + " " + ln).strip() or emp.email or f"Employee #{emp.id}"


def is_hr(emp: Employee) -> bool:
    return role_name(emp) in {"hr", "admin"}


def is_manager(emp: Employee) -> bool:
    return role_name(emp) == "manager"


def compute_deadline(phase_key: str, db: Session) -> datetime:
    """Return today + configured default_days for the given phase.  Falls back
    to _FALLBACK_DEADLINE_DAYS if the settings row doesn't exist yet."""
    setting = db.query(PMSPhaseSettings).filter(
        PMSPhaseSettings.phase_key == phase_key
    ).first()
    days = setting.default_days if setting else _FALLBACK_DEADLINE_DAYS
    return datetime.utcnow() + timedelta(days=days)


def _maybe_audit_deadline_override(
    db: Session,
    actor_id: int,
    action: str,
    entity_id: int,
    provided_deadline: Optional[datetime],
    computed_deadline: datetime,
) -> None:
    """If HR manually specified a deadline different from the auto-computed one,
    write an audit entry recording both values so the override is traceable."""
    if provided_deadline is None:
        return
    # Truncate to minute precision to avoid false positives from microseconds.
    p = provided_deadline.replace(second=0, microsecond=0)
    c = computed_deadline.replace(second=0, microsecond=0)
    if p != c:
        _audit(db, actor_id, f"{action}.deadline_override", entity_id, None, {
            "computed": computed_deadline.isoformat(),
            "provided": provided_deadline.isoformat(),
        })


def generate_template_code(db: Session) -> str:
    """Generate a short unique legacy code for pms_goal_templates.code."""
    prefix = "PMS"
    next_num = (db.query(GoalTemplate).count() or 0) + 1
    while True:
        code = f"{prefix}{next_num:05d}"
        exists = db.query(GoalTemplate.id).filter(GoalTemplate.code == code).first()
        if not exists:
            return code
        next_num += 1


def assignment_view(db: Session, a: GoalAssignment) -> dict:
    """Hydrate an assignment row with employee/manager names for the API response."""
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    mgr = db.query(Employee).filter(Employee.id == a.manager_id).first() if a.manager_id else None
    d = {
        "id": a.id,
        "template_id": a.template_id,
        "employee_id": a.employee_id,
        "employee_name": full_name(emp),
        "manager_id": a.manager_id,
        "manager_name": full_name(mgr),
        "period": a.period,
        "deadline": a.deadline,  # CHANGE 3
        "status": a.status,
        "sent_at": a.sent_at,
        "discussed_at": a.discussed_at,
        "employee_confirmed_at": a.employee_confirmed_at,
        "manager_approved_at": a.manager_approved_at,
        "hr_reviewed_at": a.hr_reviewed_at,
        "locked_at": a.locked_at,
        "lock_type": getattr(a, 'lock_type', None),
        "employee_comments": a.employee_comments,
        "manager_comments": a.manager_comments,
        "hr_comments": a.hr_comments,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "kras": [
            {
                "id": k.id, "title": k.title, "description": k.description,
                "weightage": k.weightage, "sort_order": k.sort_order,
                "from_template": bool(getattr(k, 'from_template', False)),  # CHANGE 1
                "kpis": [
                    {
                        "id": p.id, "title": p.title, "description": p.description,
                        "target": p.target, "measurement_unit": p.measurement_unit,
                        "weightage": p.weightage,
                        "from_template": bool(getattr(p, 'from_template', False)),  # CHANGE 1
                    } for p in (k.kpis or [])
                ],
            } for k in sorted(a.kras or [], key=lambda x: (x.sort_order, x.id))
        ],
        "competencies": [
            {
                "id": c.id, "title": c.title, "description": c.description,
                "weightage": c.weightage,
                "from_template": bool(getattr(c, 'from_template', False)),  # CHANGE 1
            } for c in (a.competencies or [])
        ],
        "comments": [
            {
                "id": c.id, "author_id": c.author_id, "author_role": c.author_role,
                "body": c.body, "stage": c.stage, "created_at": c.created_at,
            } for c in sorted(a.comments or [], key=lambda x: x.created_at)
        ],
    }
    return d


def _audit(db: Session, actor_id: int, action: str, target_id: int, old: dict | None, new: dict | None) -> None:
    try:
        write_audit(
            db,
            actor_id=actor_id,
            action=action,
            target_table="pms_goal_assignments",
            target_id=str(target_id),
            old_value=old,
            new_value=new,
        )
    except Exception:
        pass


# ── Template authoring (HR) ────────────────────────────────────────


def create_template(db: Session, hr: Employee, payload) -> GoalTemplate:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    t = GoalTemplate(
        name=payload.name.strip(),
        description=payload.description,
        period=payload.period,
        department_id=payload.department_id,
        designation_id=payload.designation_id,
        role_id=payload.role_id,
        is_active=bool(payload.is_active),
        created_by=hr.id,
        # Legacy NOT NULL columns kept for backward compat with the original
        # pms_goal_templates DB schema (see app/models/pms.py comment).
        created_by_id=hr.id,
        code=generate_template_code(db),
        financial_year="",
        cycle="",
    )
    db.add(t)
    db.flush()
    for kra_in in payload.kras or []:
        kra = TemplateKRA(
            template_id=t.id,
            title=kra_in.title.strip(),
            description=kra_in.description,
            weightage=float(kra_in.weightage or 0.0),
            sort_order=int(kra_in.sort_order or 0),
        )
        db.add(kra)
        db.flush()
        for kpi_in in kra_in.kpis or []:
            db.add(TemplateKPI(
                kra_id=kra.id,
                title=kpi_in.title.strip(),
                description=kpi_in.description,
                weightage=float(kpi_in.weightage or 0.0),
            ))
    for comp_in in payload.competencies or []:
        db.add(TemplateCompetency(
            template_id=t.id,
            title=comp_in.title.strip(),
            description=comp_in.description,
            weightage=float(comp_in.weightage or 0.0),
        ))
    _audit(db, hr.id, "pms.template.create", t.id, None, {"name": t.name})
    db.commit()
    db.refresh(t)
    return t


def update_template(db: Session, hr: Employee, template_id: int, payload) -> GoalTemplate:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    t = db.query(GoalTemplate).filter(GoalTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    t.name = payload.name.strip()
    t.description = payload.description
    t.period = payload.period
    t.department_id = payload.department_id
    t.designation_id = payload.designation_id
    t.role_id = payload.role_id
    t.is_active = bool(payload.is_active)

    # Wipe + re-create children for simplicity. Templates are not very large.
    for kra in list(t.kras):
        db.delete(kra)
    for comp in list(t.competencies):
        db.delete(comp)
    db.flush()

    for kra_in in payload.kras or []:
        kra = TemplateKRA(
            template_id=t.id,
            title=kra_in.title.strip(),
            description=kra_in.description,
            weightage=float(kra_in.weightage or 0.0),
            sort_order=int(kra_in.sort_order or 0),
        )
        db.add(kra)
        db.flush()
        for kpi_in in kra_in.kpis or []:
            db.add(TemplateKPI(
                kra_id=kra.id,
                title=kpi_in.title.strip(),
                description=kpi_in.description,
                weightage=float(kpi_in.weightage or 0.0),
            ))
    for comp_in in payload.competencies or []:
        db.add(TemplateCompetency(
            template_id=t.id,
            title=comp_in.title.strip(),
            description=comp_in.description,
            weightage=float(comp_in.weightage or 0.0),
        ))
    # Increment version on every successful update.
    t.template_version = (t.template_version or 1) + 1
    _audit(db, hr.id, "pms.template.update", t.id, None, {"name": t.name})
    db.commit()
    db.refresh(t)
    return t


def delete_template(db: Session, hr: Employee, template_id: int) -> None:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    t = db.query(GoalTemplate).filter(GoalTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    db.delete(t)
    _audit(db, hr.id, "pms.template.delete", template_id, {"name": t.name}, None)
    db.commit()


# ── Assignment generation (HR sends goals) ─────────────────────────


def _resolve_target_employees(
    db: Session,
    department_id: Optional[str],
    designation_id: Optional[str],
    role_id: Optional[int],
    employee_ids: Optional[Iterable[int]],
) -> List[Employee]:
    q = db.query(Employee).filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
    if employee_ids:
        ids = [int(x) for x in employee_ids if x]
        return q.filter(Employee.id.in_(ids)).all() if ids else []
    if department_id:
        q = q.filter(Employee.department_id == department_id)
    if designation_id:
        q = q.filter(Employee.designation_id == designation_id)
    if role_id:
        q = q.filter(Employee.role_id == role_id)
    return q.all()


def assign_template(db: Session, hr: Employee, payload) -> List[GoalAssignment]:
    """HR creates GoalAssignment rows for every targeted employee."""
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    t = db.query(GoalTemplate).filter(GoalTemplate.id == payload.template_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    targets = _resolve_target_employees(
        db,
        payload.department_id,
        payload.designation_id,
        payload.role_id,
        payload.employee_ids,
    )
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No employees matched the assignment criteria.")

    created: List[GoalAssignment] = []
    now = datetime.utcnow()
    period = payload.period or t.period

    # CHANGE 9: auto-compute deadline; use HR-provided value if supplied.
    computed_dl = compute_deadline("goal_setting", db)
    provided_dl = getattr(payload, 'deadline', None)
    final_deadline = provided_dl if provided_dl is not None else computed_dl

    for emp in targets:
        # Skip employees who already have an active (non-locked) assignment for this template + period.
        dup = db.query(GoalAssignment).filter(
            GoalAssignment.template_id == t.id,
            GoalAssignment.employee_id == emp.id,
            GoalAssignment.period == period,
        ).first()
        if dup:
            continue

        a = GoalAssignment(
            template_id=t.id,
            employee_id=emp.id,
            manager_id=emp.reporting_manager_id,
            period=period,
            deadline=final_deadline,  # CHANGE 9: always set (auto or HR-provided)
            status=PMS_STATUS_GOALS_SENT,
            sent_at=now,
            sent_by=hr.id,
            created_by=hr.id,
        )
        db.add(a)
        db.flush()

        # Defensive: purge any KRAs/competencies that exist for this assignment id.
        # In a clean DB this no-ops, but if a prior assignment was deleted without
        # SQLite CASCADE enforcement, orphaned rows may have inherited this id.
        for orphan in list(db.query(AssignedKRA).filter(AssignedKRA.assignment_id == a.id).all()):
            db.delete(orphan)
        for orphan in list(db.query(AssignedCompetency).filter(AssignedCompetency.assignment_id == a.id).all()):
            db.delete(orphan)
        db.flush()

        # Snapshot KRAs/KPIs/Competencies from the template.
        # CHANGE 1: mark all template-derived items as from_template=True
        for k in t.kras:
            ak = AssignedKRA(
                assignment_id=a.id,
                title=k.title,
                description=k.description,
                weightage=k.weightage,
                sort_order=k.sort_order,
                from_template=True,  # CHANGE 1
            )
            db.add(ak)
            db.flush()
            for p in k.kpis:
                db.add(AssignedKPI(
                    kra_id=ak.id,
                    title=p.title,
                    description=p.description,
                    weightage=p.weightage,
                    from_template=True,  # CHANGE 1
                ))
        for c in t.competencies:
            db.add(AssignedCompetency(
                assignment_id=a.id,
                title=c.title,
                description=c.description,
                weightage=c.weightage,
                from_template=True,  # CHANGE 1
            ))

        # CHANGE 9: audit deadline override if HR provided a different value.
        _maybe_audit_deadline_override(db, hr.id, "pms.assignment", a.id, provided_dl, computed_dl)

        dl_label = final_deadline.strftime("%d %b %Y") if final_deadline else ""
        # Notify the employee + their manager (CHANGE 9: include due date in body).
        notify(
            db, recipient_id=emp.id,
            type_="pms_goals_assigned",
            title="Goal Setting — Goals Assigned",
            body=(
                f"Phase: Goal Setting | Action: Review & discuss with manager"
                + (f" | Due: {dl_label}" if dl_label else "")
            ),
            reference_table="pms_goal_assignments",
            reference_id=str(a.id),
        )
        if emp.reporting_manager_id:
            notify(
                db, recipient_id=emp.reporting_manager_id,
                type_="pms_goals_assigned",
                title=f"Goal Setting — Goals assigned to {full_name(emp)}",
                body=(
                    f"Phase: Goal Setting | Action: Open the team-goals queue to start discussion"
                    + (f" | Due: {dl_label}" if dl_label else "")
                ),
                reference_table="pms_goal_assignments",
                reference_id=str(a.id),
            )

        # Email notifications (non-fatal — wrapped inside the service).
        pms_email.email_goals_assigned(
            db,
            employee_id=emp.id,
            employee_name=full_name(emp),
            manager_id=emp.reporting_manager_id,
            period=period,
            template_name=t.name,
            due_date=final_deadline,  # CHANGE 9
        )

        _audit(db, hr.id, "pms.assignment.create", a.id, None, {"employee_id": emp.id, "template_id": t.id})
        created.append(a)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


# ── Visibility helpers ─────────────────────────────────────────────


def list_assignments_for(db: Session, viewer: Employee, scope: str = "auto") -> List[GoalAssignment]:
    """`scope` ∈ {auto, hr, manager, employee}."""
    q = db.query(GoalAssignment)
    if scope == "auto":
        if is_hr(viewer):
            scope = "hr"
        elif is_manager(viewer):
            scope = "manager"
        else:
            scope = "employee"
    if scope == "hr":
        pass
    elif scope == "manager":
        q = q.filter(GoalAssignment.manager_id == viewer.id)
    else:
        q = q.filter(GoalAssignment.employee_id == viewer.id)
    return q.order_by(GoalAssignment.created_at.desc()).all()


def get_assignment_for(db: Session, viewer: Employee, assignment_id: int) -> GoalAssignment:
    a = db.query(GoalAssignment).filter(GoalAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if is_hr(viewer):
        return a
    if a.manager_id == viewer.id or a.employee_id == viewer.id:
        return a
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this assignment.")


# ── State transitions ──────────────────────────────────────────────


def _require_not_locked(a: GoalAssignment) -> None:
    if a.status == PMS_STATUS_GOALS_LOCKED:
        if getattr(a, 'lock_type', None) == LOCK_TYPE_AUTO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This phase has been automatically locked after the deadline and can no longer be modified.",
            )
        raise HTTPException(status.HTTP_409_CONFLICT, "Goals are locked. Ask HR to unlock before editing.")


def _apply_edits(db: Session, a: GoalAssignment, payload, actor: Optional[Employee] = None) -> None:
    """Merge editable KRA/KPI/Competency trees into the assignment in place.

    CHANGE 1: Template-derived KRAs/KPIs/competencies are read-only for
    employee and manager roles.  HR may still edit them (is_hr check).
    """
    actor_is_hr = is_hr(actor) if actor else False

    if payload.kras is not None:
        existing_kra = {k.id: k for k in a.kras}
        seen_kra_ids: set[int] = set()
        for kra_in in payload.kras:
            if kra_in.id and kra_in.id in existing_kra:
                kra = existing_kra[kra_in.id]
                # CHANGE 1: block edits on template-originated KRAs for non-HR
                if getattr(kra, 'from_template', False) and not actor_is_hr:
                    # preserve existing template KRA — just keep it in seen set
                    seen_kra_ids.add(kra.id)
                    # still process KPIs (they are guarded individually below)
                else:
                    kra.title = kra_in.title.strip()
                    kra.description = kra_in.description
                    kra.weightage = float(kra_in.weightage or 0.0)
                    kra.sort_order = int(kra_in.sort_order or 0)
                    seen_kra_ids.add(kra.id)
                # Merge KPIs under this KRA.
                existing_kpi = {p.id: p for p in (kra.kpis or [])}
                seen_kpi_ids: set[int] = set()
                for kpi_in in kra_in.kpis or []:
                    if kpi_in.id and kpi_in.id in existing_kpi:
                        p = existing_kpi[kpi_in.id]
                        # CHANGE 1: block edits on template KPIs for non-HR
                        if getattr(p, 'from_template', False) and not actor_is_hr:
                            seen_kpi_ids.add(p.id)
                        else:
                            p.title = kpi_in.title.strip()
                            p.description = kpi_in.description
                            p.weightage = float(kpi_in.weightage or 0.0)
                            seen_kpi_ids.add(p.id)
                    else:
                        # New KPI — always allowed
                        new_kpi = AssignedKPI(
                            kra_id=kra.id,
                            title=kpi_in.title.strip(),
                            description=kpi_in.description,
                            weightage=float(kpi_in.weightage or 0.0),
                            from_template=False,
                        )
                        db.add(new_kpi)
                # CHANGE 1: only delete non-template KPIs for non-HR actors
                for pid, p in existing_kpi.items():
                    if pid not in seen_kpi_ids:
                        if getattr(p, 'from_template', False) and not actor_is_hr:
                            pass  # preserve template KPIs
                        else:
                            db.delete(p)
            else:
                # New KRA — allowed for all roles
                kra = AssignedKRA(
                    assignment_id=a.id,
                    title=kra_in.title.strip(),
                    description=kra_in.description,
                    weightage=float(kra_in.weightage or 0.0),
                    sort_order=int(kra_in.sort_order or 0),
                    from_template=False,
                )
                db.add(kra)
                db.flush()
                seen_kra_ids.add(kra.id)
                for kpi_in in kra_in.kpis or []:
                    db.add(AssignedKPI(
                        kra_id=kra.id,
                        title=kpi_in.title.strip(),
                        description=kpi_in.description,
                        weightage=float(kpi_in.weightage or 0.0),
                        from_template=False,
                    ))
        # CHANGE 1: only delete non-template KRAs for non-HR actors
        for kid, kra in existing_kra.items():
            if kid not in seen_kra_ids:
                if getattr(kra, 'from_template', False) and not actor_is_hr:
                    pass  # preserve template KRAs — never delete them
                else:
                    db.delete(kra)

    if payload.competencies is not None:
        existing_c = {c.id: c for c in a.competencies}
        seen_c_ids: set[int] = set()
        for comp_in in payload.competencies:
            if comp_in.id and comp_in.id in existing_c:
                c = existing_c[comp_in.id]
                # CHANGE 1: block edits on template competencies for non-HR
                if getattr(c, 'from_template', False) and not actor_is_hr:
                    seen_c_ids.add(c.id)
                else:
                    c.title = comp_in.title.strip()
                    c.description = comp_in.description
                    c.weightage = float(comp_in.weightage or 0.0)
                    seen_c_ids.add(c.id)
            else:
                # New competency — always allowed (employee/manager can add their own)
                db.add(AssignedCompetency(
                    assignment_id=a.id,
                    title=comp_in.title.strip(),
                    description=comp_in.description,
                    weightage=float(comp_in.weightage or 0.0),
                    from_template=False,
                ))
        # CHANGE 1: preserve template competencies; only delete user-added ones
        for cid, c in existing_c.items():
            if cid not in seen_c_ids:
                if getattr(c, 'from_template', False) and not actor_is_hr:
                    pass  # preserve template competencies
                else:
                    db.delete(c)


def _stage_comment(db: Session, a: GoalAssignment, author: Employee, role: str, body: Optional[str]) -> None:
    if not body:
        return
    db.add(GoalComment(
        assignment_id=a.id,
        author_id=author.id,
        author_role=role,
        body=body.strip(),
        stage=a.status,
    ))


def manager_discuss(db: Session, manager: Employee, assignment_id: int, payload) -> GoalAssignment:
    a = get_assignment_for(db, manager, assignment_id)
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may open discussion.")
    _require_not_locked(a)
    if a.status not in (PMS_STATUS_GOALS_SENT, PMS_STATUS_UNDER_DISCUSSION):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot discuss from status '{a.status}'.")

    if payload is not None:
        _apply_edits(db, a, payload, actor=manager)
        if payload.comment:
            a.manager_comments = payload.comment
            _stage_comment(db, a, manager, "manager", payload.comment)

    a.status = PMS_STATUS_UNDER_DISCUSSION
    a.discussed_at = datetime.utcnow()

    notify(db, recipient_id=a.employee_id,
           type_="pms_goals_discussed",
           title="Your manager updated your goals",
           body="Open Performance to review and confirm.",
           reference_table="pms_goal_assignments", reference_id=str(a.id))
    emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
    pms_email.email_discussion_started(
        db,
        employee_id=a.employee_id,
        employee_name=full_name(emp),
        manager_name=full_name(manager),
        period=a.period,
    )
    _audit(db, manager.id, "pms.assignment.discuss", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def employee_confirm(db: Session, employee: Employee, assignment_id: int, payload) -> GoalAssignment:
    a = get_assignment_for(db, employee, assignment_id)
    if a.employee_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assignee can confirm these goals.")
    _require_not_locked(a)
    if a.status not in (PMS_STATUS_GOALS_SENT, PMS_STATUS_UNDER_DISCUSSION):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot confirm from status '{a.status}'.")

    if payload is not None:
        _apply_edits(db, a, payload, actor=employee)
        if payload.comment:
            a.employee_comments = payload.comment
            _stage_comment(db, a, employee, "employee", payload.comment)

    a.status = PMS_STATUS_EMPLOYEE_CONFIRMED
    a.employee_confirmed_at = datetime.utcnow()

    if a.manager_id:
        notify(db, recipient_id=a.manager_id,
               type_="pms_goals_discussed",
               title=f"{full_name(employee)} confirmed their goals",
               body="Awaiting your final approval.",
               reference_table="pms_goal_assignments", reference_id=str(a.id))
    pms_email.email_employee_confirmed(
        db,
        manager_id=a.manager_id,
        employee_name=full_name(employee),
        period=a.period,
    )
    _audit(db, employee.id, "pms.assignment.employee_confirm", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def manager_approve(db: Session, manager: Employee, assignment_id: int, payload) -> GoalAssignment:
    a = get_assignment_for(db, manager, assignment_id)
    if a.manager_id != manager.id and not is_hr(manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporting manager (or HR) may approve.")
    _require_not_locked(a)
    if a.status != PMS_STATUS_EMPLOYEE_CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee must confirm goals before manager approval.")

    # CHANGE 2: Manager can edit KPI details / descriptions / weightages during review
    # before final approval. Template-derived goals remain read-only via _apply_edits.
    old_kras = {k.id: {"title": k.title, "weightage": k.weightage} for k in a.kras}
    if payload and hasattr(payload, 'kras') and payload.kras is not None:
        _apply_edits(db, a, payload, actor=manager)
        new_kras = {k.id: {"title": k.title, "weightage": k.weightage} for k in a.kras}
        _audit(db, manager.id, "pms.assignment.manager_review_edit", a.id,
               {"kras": old_kras}, {"kras": new_kras})

    if payload and payload.comment:
        a.manager_comments = payload.comment
        _stage_comment(db, a, manager, "manager", payload.comment)

    a.status = PMS_STATUS_MANAGER_APPROVED
    a.manager_approved_at = datetime.utcnow()

    notify(db, recipient_id=a.employee_id,
           type_="pms_goals_approved",
           title="Manager approved your goals",
           body="Goals are now with HR for final review.",
           reference_table="pms_goal_assignments", reference_id=str(a.id))
    # Notify HR pool — best-effort: notify all employees with role 'hr' or 'admin'.
    hr_ids = _hr_recipient_ids(db)
    if hr_ids:
        notify_many(db, hr_ids,
                    type_="pms_goals_approved",
                    title=f"Manager approved goals for {full_name_for_id(db, a.employee_id)}",
                    body="Open the HR review queue.",
                    reference_table="pms_goal_assignments", reference_id=str(a.id))
    emp_name = full_name_for_id(db, a.employee_id)
    pms_email.email_manager_approved(
        db,
        employee_id=a.employee_id,
        employee_name=emp_name,
        manager_name=full_name(manager),
        period=a.period,
        hr_ids=hr_ids,
    )
    _audit(db, manager.id, "pms.assignment.manager_approve", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def hr_review(db: Session, hr: Employee, assignment_id: int, payload) -> GoalAssignment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    a = get_assignment_for(db, hr, assignment_id)
    _require_not_locked(a)
    if a.status != PMS_STATUS_MANAGER_APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Manager must approve before HR review.")
    if payload and payload.comment:
        a.hr_comments = payload.comment
        _stage_comment(db, a, hr, "hr", payload.comment)
    a.status = PMS_STATUS_HR_REVIEWED
    a.hr_reviewed_at = datetime.utcnow()
    a.hr_reviewed_by = hr.id

    notify(db, recipient_id=a.employee_id,
           type_="pms_goals_approved",
           title="HR reviewed your goals",
           body="Goals will be locked shortly.",
           reference_table="pms_goal_assignments", reference_id=str(a.id))
    pms_email.email_hr_reviewed(
        db,
        employee_id=a.employee_id,
        employee_name=full_name_for_id(db, a.employee_id),
        period=a.period,
    )
    _audit(db, hr.id, "pms.assignment.hr_review", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def hr_lock(db: Session, hr: Employee, assignment_id: int, payload,
            lock_type: str = LOCK_TYPE_MANUAL) -> GoalAssignment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    a = get_assignment_for(db, hr, assignment_id)
    if a.status not in (PMS_STATUS_HR_REVIEWED, PMS_STATUS_MANAGER_APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only HR-reviewed (or manager-approved) goals can be locked.")
    if payload and payload.comment:
        a.hr_comments = payload.comment
        _stage_comment(db, a, hr, "hr", payload.comment)
    a.status = PMS_STATUS_GOALS_LOCKED
    a.locked_at = datetime.utcnow()
    a.locked_by = hr.id
    a.lock_type = lock_type

    recipients = [a.employee_id]
    if a.manager_id:
        recipients.append(a.manager_id)
    notify_many(db, recipients,
                type_="pms_goals_locked",
                title="Goals locked",
                body="Goals are now locked and cannot be edited without HR unlock.",
                reference_table="pms_goal_assignments", reference_id=str(a.id))
    pms_email.email_goals_locked(
        db,
        employee_id=a.employee_id,
        employee_name=full_name_for_id(db, a.employee_id),
        manager_id=a.manager_id,
        period=a.period,
    )
    _audit(db, hr.id, "pms.assignment.lock", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def hr_unlock(db: Session, hr: Employee, assignment_id: int, payload) -> GoalAssignment:
    if not is_hr(hr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    a = get_assignment_for(db, hr, assignment_id)
    if a.status != PMS_STATUS_GOALS_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only locked goals can be unlocked.")
    if getattr(a, 'lock_type', None) == LOCK_TYPE_AUTO:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This phase has been automatically locked after the deadline and can no longer be modified.",
        )
    if payload and payload.comment:
        _stage_comment(db, a, hr, "hr", payload.comment)
    a.status = PMS_STATUS_HR_REVIEWED
    a.locked_at = None
    a.locked_by = None
    a.lock_type = None
    _audit(db, hr.id, "pms.assignment.unlock", a.id, None, {"status": a.status})
    db.commit()
    db.refresh(a)
    return a


def add_comment(db: Session, viewer: Employee, assignment_id: int, body: str) -> GoalComment:
    a = get_assignment_for(db, viewer, assignment_id)
    _require_not_locked(a)
    role = "hr" if is_hr(viewer) else ("manager" if a.manager_id == viewer.id else "employee")
    c = GoalComment(
        assignment_id=a.id,
        author_id=viewer.id,
        author_role=role,
        body=body.strip(),
        stage=a.status,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ── Tiny utilities ─────────────────────────────────────────────────


def _hr_recipient_ids(db: Session) -> List[int]:
    rows = (
        db.query(Employee.id)
        .join(Role, Role.id == Employee.role_id)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .filter(Role.name.in_(["hr", "admin"]))
        .all()
    )
    return [r[0] for r in rows]


def full_name_for_id(db: Session, eid: int) -> str:
    e = db.query(Employee).filter(Employee.id == eid).first()
    return full_name(e)
