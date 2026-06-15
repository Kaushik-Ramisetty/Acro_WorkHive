"""PMS Phase-1 API routes: HR template authoring → assignment → discussion → approval → locking."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    Employee,
    GoalTemplate,
    GoalAssignment,
    TemplateCompetency,
)
from app.models.pms_settings import PMSPhaseSettings
from app.schemas.pms import (
    ImportCommitIn,
    ImportPreviewOut,
    TemplateIn,
    TemplateOut,
    AssignTargetIn,
    AssignmentOut,
    AssignmentEdit,
    StageActionIn,
    CommentIn,
    BulkIdsIn,
    BulkActionOut,
    PMSPhaseSettingOut,
    PMSPhaseSettingUpdate,
    DeadlinePreviewOut,
)
from app.services import pms_service as svc
from app.services.audit_service import write_audit
from app.services import pms_excel_service as excel_svc


router = APIRouter(prefix="/pms", tags=["pms"])


def _bulk_error_reason(exc: Exception) -> str:
    """Return a plain-string reason from any exception, safely."""
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc)


# ── Templates (HR) ─────────────────────────────────────────────────


@router.get("/templates", response_model=List[TemplateOut])
def list_templates(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    q = db.query(GoalTemplate)
    if active_only:
        q = q.filter(GoalTemplate.is_active.is_(True))
    return q.order_by(GoalTemplate.created_at.desc()).all()


@router.get("/templates/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    t = db.query(GoalTemplate).filter(GoalTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    return t


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    return svc.create_template(db, me, payload)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    payload: TemplateIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    return svc.update_template(db, me, template_id, payload)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    svc.delete_template(db, me, template_id)
    return None


# ── Excel import / export ──────────────────────────────────────────


@router.post("/templates/import", response_model=ImportPreviewOut)
async def import_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Parse an uploaded Goals .xlsx and return a preview. Does NOT persist anything."""
    if not svc.is_hr(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    content = await file.read()
    filename = file.filename or "upload.xlsx"
    try:
        result = excel_svc.parse_goals_workbook(content, filename, db=db)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return result


@router.post("/templates/import/commit", response_model=List[TemplateOut], status_code=status.HTTP_201_CREATED)
def import_commit(
    payload: ImportCommitIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Persist parsed (and possibly client-edited) import preview as GoalTemplate rows."""
    if not svc.is_hr(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")

    from app.models import TemplateKRA, TemplateKPI

    created_templates = []
    now = datetime.utcnow()

    try:
        for desig in payload.designations:
            template_name = (desig.name or f"{_filename_base(payload.source_filename)} - {desig.designation_name}").strip()
            t = GoalTemplate(
                name=template_name[:200],
                description=desig.description,
                period=desig.period or payload.period,
                department_id=desig.department_id,
                designation_id=desig.designation_id,
                role_id=desig.role_id,
                is_active=bool(desig.is_active),
                created_by=me.id,
                created_by_id=me.id,
                code=svc.generate_template_code(db),
                financial_year="",
                cycle="",
                imported_from_excel=True,
                source_filename=(payload.source_filename or "")[:255] or None,
                template_version=1,
                imported_by=me.id,
                imported_at=now,
            )
            db.add(t)
            db.flush()

            for kra_in in desig.kras:
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

            for comp_in in desig.competencies or []:
                db.add(TemplateCompetency(
                    template_id=t.id,
                    title=comp_in.title.strip(),
                    description=comp_in.description,
                    weightage=float(comp_in.weightage or 0.0),
                ))

            write_audit(
                db,
                actor_id=me.id,
                action="pms.template.import",
                target_table="pms_goal_templates",
                target_id=str(t.id),
                old_value=None,
                new_value={"name": t.name, "source_filename": t.source_filename},
            )
            created_templates.append(t)

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        root = getattr(exc, "orig", None)
        detail = str(root or exc).strip() or exc.__class__.__name__
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while importing PMS template(s): {detail}",
        ) from exc

    for t in created_templates:
        db.refresh(t)
    return created_templates


@router.get("/templates/{template_id}/export")
def export_template(
    template_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Export a GoalTemplate as an .xlsx file."""
    if not svc.is_hr(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    t = db.query(GoalTemplate).filter(GoalTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")

    xlsx_bytes = excel_svc.build_workbook_for_template(t, db)
    fname = excel_svc.template_export_filename(t)

    t.last_exported_by = me.id
    t.last_exported_at = datetime.utcnow()
    write_audit(
        db,
        actor_id=me.id,
        action="pms.template.export",
        target_table="pms_goal_templates",
        target_id=str(t.id),
        old_value=None,
        new_value={"filename": fname},
    )
    db.commit()

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _filename_base(source_filename: str) -> str:
    """Strip extension and convert underscores/hyphens to spaces for a friendly template name."""
    import os
    base = os.path.splitext(source_filename)[0]
    return base.replace("_", " ").replace("-", " ").strip()


# ── HR: send goals (create assignments) ────────────────────────────


@router.post("/assignments", response_model=List[AssignmentOut], status_code=status.HTTP_201_CREATED)
def assign_template(
    payload: AssignTargetIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.assign_template(db, me, payload)
    return [svc.assignment_view(db, a) for a in rows]


# ── Assignment queries ─────────────────────────────────────────────


@router.get("/assignments", response_model=List[AssignmentOut])
def list_assignments(
    scope: str = Query("auto", pattern="^(auto|hr|manager|employee)$"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    rows = svc.list_assignments_for(db, me, scope=scope)
    if status_filter:
        rows = [a for a in rows if a.status == status_filter]
    return [svc.assignment_view(db, a) for a in rows]


# ── BULK Phase-1 actions (CHANGE 8) — must be before /{assignment_id} ──────────
#
# Session isolation strategy: each item is wrapped in a DB savepoint
# (db.begin_nested()).  On success the savepoint is released by the service's
# own db.commit(); on failure we roll back only that savepoint, leaving the
# session and all previously-successful items unaffected.  The outer
# transaction is committed once after the loop.
#
# This replaces the previous db.rollback() pattern, which reset the entire
# session identity map and caused DetachedInstanceError on subsequent items.

@router.post("/assignments/bulk/hr-review", response_model=BulkActionOut)
def bulk_hr_review_assignments(
    payload: BulkIdsIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for aid in payload.ids:
        sp = db.begin_nested()
        try:
            svc.hr_review(db, me, aid, StageActionIn(comment=payload.comment))
            results.append({"id": aid, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass  # savepoint already released by an internal commit
            results.append({"id": aid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()  # commit outer transaction (all released savepoints)
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.post("/assignments/bulk/lock", response_model=BulkActionOut)
def bulk_lock_assignments(
    payload: BulkIdsIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for aid in payload.ids:
        sp = db.begin_nested()
        try:
            svc.hr_lock(db, me, aid, StageActionIn(comment=payload.comment))
            results.append({"id": aid, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass
            results.append({"id": aid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.post("/assignments/bulk/unlock", response_model=BulkActionOut)
def bulk_unlock_assignments(
    payload: BulkIdsIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    results = []
    for aid in payload.ids:
        sp = db.begin_nested()
        try:
            svc.hr_unlock(db, me, aid, StageActionIn(comment=payload.comment))
            results.append({"id": aid, "success": True})
        except Exception as exc:
            try:
                sp.rollback()
            except Exception:
                pass
            results.append({"id": aid, "success": False, "reason": _bulk_error_reason(exc)})
    db.commit()
    sc = sum(1 for r in results if r["success"])
    return {"total": len(results), "success_count": sc, "failure_count": len(results) - sc, "results": results}


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.get_assignment_for(db, me, assignment_id)
    return svc.assignment_view(db, a)


# ── State-transition endpoints ─────────────────────────────────────


@router.post("/assignments/{assignment_id}/discuss", response_model=AssignmentOut)
def manager_discuss(
    assignment_id: int,
    payload: AssignmentEdit | None = None,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.manager_discuss(db, me, assignment_id, payload or AssignmentEdit())
    return svc.assignment_view(db, a)


@router.post("/assignments/{assignment_id}/employee-confirm", response_model=AssignmentOut)
def employee_confirm(
    assignment_id: int,
    payload: AssignmentEdit | None = None,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.employee_confirm(db, me, assignment_id, payload or AssignmentEdit())
    return svc.assignment_view(db, a)


@router.post("/assignments/{assignment_id}/manager-approve", response_model=AssignmentOut)
def manager_approve(
    assignment_id: int,
    payload: AssignmentEdit | None = None,  # CHANGE 2: manager can edit goals during approval
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.manager_approve(db, me, assignment_id, payload or AssignmentEdit())
    return svc.assignment_view(db, a)


@router.post("/assignments/{assignment_id}/hr-review", response_model=AssignmentOut)
def hr_review(
    assignment_id: int,
    payload: StageActionIn | None = None,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.hr_review(db, me, assignment_id, payload or StageActionIn())
    return svc.assignment_view(db, a)


@router.post("/assignments/{assignment_id}/lock", response_model=AssignmentOut)
def hr_lock(
    assignment_id: int,
    payload: StageActionIn | None = None,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.hr_lock(db, me, assignment_id, payload or StageActionIn())
    return svc.assignment_view(db, a)


@router.post("/assignments/{assignment_id}/unlock", response_model=AssignmentOut)
def hr_unlock(
    assignment_id: int,
    payload: StageActionIn | None = None,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    a = svc.hr_unlock(db, me, assignment_id, payload or StageActionIn())
    return svc.assignment_view(db, a)


# ── Comments thread ────────────────────────────────────────────────


@router.post("/assignments/{assignment_id}/comments", status_code=status.HTTP_201_CREATED)
def post_comment(
    assignment_id: int,
    payload: CommentIn,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    c = svc.add_comment(db, me, assignment_id, payload.body)
    return {
        "id": c.id,
        "author_id": c.author_id,
        "author_role": c.author_role,
        "body": c.body,
        "stage": c.stage,
        "created_at": c.created_at,
    }


# ── PMS Phase Settings (CHANGE 9) ──────────────────────────────────────────────


@router.get("/settings/phases", response_model=List[PMSPhaseSettingOut])
def list_phase_settings(
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Return all phase deadline settings. Accessible by any authenticated user."""
    return db.query(PMSPhaseSettings).order_by(PMSPhaseSettings.id).all()


@router.get("/settings/phases/{phase_key}", response_model=PMSPhaseSettingOut)
def get_phase_setting(
    phase_key: str,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    row = db.query(PMSPhaseSettings).filter(PMSPhaseSettings.phase_key == phase_key).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Phase setting '{phase_key}' not found.")
    return row


@router.put("/settings/phases/{phase_key}", response_model=PMSPhaseSettingOut)
def update_phase_setting(
    phase_key: str,
    payload: PMSPhaseSettingUpdate,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """HR / admin only — update the default deadline days for a phase."""
    if not svc.is_hr(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR / admin role required.")
    row = db.query(PMSPhaseSettings).filter(PMSPhaseSettings.phase_key == phase_key).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Phase setting '{phase_key}' not found.")
    old_days = row.default_days
    row.default_days = payload.default_days
    row.updated_by = me.id
    db.commit()
    db.refresh(row)
    write_audit(
        db, actor_id=me.id, action="pms.settings.update_phase_deadline",
        target_table="pms_phase_settings", target_id=str(row.id),
        old_value={"default_days": old_days},
        new_value={"default_days": payload.default_days, "phase_key": phase_key},
    )
    return row


@router.get("/settings/phases/{phase_key}/deadline", response_model=DeadlinePreviewOut)
def compute_phase_deadline(
    phase_key: str,
    db: Session = Depends(get_db),
    me: Employee = Depends(get_current_user),
):
    """Return the auto-computed deadline datetime for the given phase.
    The frontend pre-fills the deadline input with this value."""
    row = db.query(PMSPhaseSettings).filter(PMSPhaseSettings.phase_key == phase_key).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Phase setting '{phase_key}' not found.")
    return {
        "phase_key": row.phase_key,
        "default_days": row.default_days,
        "computed_deadline": svc.compute_deadline(phase_key, db),
    }
