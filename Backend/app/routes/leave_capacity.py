"""Phase 4 routes: leave document uploads + team capacity / blackout admin.

Kept in its own router so the existing leave.py stays readable. Mounted
under the same '/leave' prefix from main.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    BlackoutPeriod, Employee, LeaveDocument, LeaveRequest, TeamCapacityPolicy,
)
from app.schemas.leave import (
    BlackoutPeriodIn, BlackoutPeriodOut, LeaveDocumentOut,
    TeamCapacityPolicyIn, TeamCapacityPolicyOut,
)
from app.services.leave_documents import (
    DocumentError, delete_document, list_documents, resolve_for_download,
    upload_document,
)


router = APIRouter(prefix="/leave", tags=["leave"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _doc_out(d: LeaveDocument) -> LeaveDocumentOut:
    return LeaveDocumentOut(
        id=d.id,
        leave_request_id=d.leave_request_id,
        original_filename=d.original_filename,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        scan_status=d.scan_status,
        scan_engine=d.scan_engine,
        scan_detail=d.scan_detail,
        scanned_at=d.scanned_at,
        uploaded_by=d.uploaded_by,
        uploaded_at=d.uploaded_at,
    )


def _wrap(call):
    try:
        return call()
    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ---------- documents ------------------------------------------------

@router.post("/{request_id}/documents", response_model=LeaveDocumentOut, status_code=201)
async def upload_doc(request_id: str,
                     file: UploadFile = File(...),
                     db: Session = Depends(get_db),
                     user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(404, "Leave request not found.")
    # Stream the body to disk via the service helper.
    doc = _wrap(lambda: upload_document(
        db, user, req, file.filename or "file", file.content_type, file.file,
    ))
    return _doc_out(doc)


@router.get("/{request_id}/documents", response_model=list[LeaveDocumentOut])
def list_docs(request_id: str,
              db: Session = Depends(get_db),
              user: Employee = Depends(get_current_user)):
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(404, "Leave request not found.")
    return [_doc_out(d) for d in _wrap(lambda: list_documents(db, user, req))]


@router.delete("/documents/{doc_id}", status_code=204)
def delete_doc(doc_id: int,
               db: Session = Depends(get_db),
               user: Employee = Depends(get_current_user)):
    doc = db.get(LeaveDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    _wrap(lambda: delete_document(db, user, doc))
    return None


@router.get("/documents/{doc_id}/download")
def download_doc(doc_id: int,
                 db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_user)):
    doc = db.get(LeaveDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    path = _wrap(lambda: resolve_for_download(user, doc))
    return FileResponse(
        path=str(path),
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename,
    )


# ---------- team capacity (admin) -----------------------------------

@router.post("/policies/team-capacity", response_model=TeamCapacityPolicyOut, status_code=201)
def upsert_team_capacity(payload: TeamCapacityPolicyIn,
                         db: Session = Depends(get_db),
                         user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    if payload.max_concurrent_on_leave < 0:
        raise HTTPException(400, "max_concurrent_on_leave must be >= 0.")
    if payload.max_concurrent_percent is not None and not (1 <= payload.max_concurrent_percent <= 100):
        raise HTTPException(400, "max_concurrent_percent must be between 1 and 100.")
    if payload.max_concurrent_on_leave == 0 and not payload.max_concurrent_percent:
        raise HTTPException(400, "Provide at least one of max_concurrent_on_leave or max_concurrent_percent.")
    existing = (
        db.query(TeamCapacityPolicy)
        .filter(TeamCapacityPolicy.manager_id == payload.manager_id,
                TeamCapacityPolicy.is_active.is_(True))
        .first()
    )
    if existing:
        existing.max_concurrent_on_leave = payload.max_concurrent_on_leave
        existing.max_concurrent_percent = payload.max_concurrent_percent
        row = existing
    else:
        row = TeamCapacityPolicy(
            manager_id=payload.manager_id,
            max_concurrent_on_leave=payload.max_concurrent_on_leave,
            max_concurrent_percent=payload.max_concurrent_percent,
            created_by=user.id,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return TeamCapacityPolicyOut.model_validate(row)


@router.get("/policies/team-capacity", response_model=list[TeamCapacityPolicyOut])
def list_team_capacity(db: Session = Depends(get_db),
                       user: Employee = Depends(get_current_user),
                       manager_id: Optional[int] = Query(None)):
    q = db.query(TeamCapacityPolicy).filter(TeamCapacityPolicy.is_active.is_(True))
    if _role(user) != "admin":
        # Managers see their own.
        q = q.filter(TeamCapacityPolicy.manager_id == user.id)
    if manager_id is not None and _role(user) == "admin":
        q = q.filter(TeamCapacityPolicy.manager_id == manager_id)
    return [TeamCapacityPolicyOut.model_validate(r) for r in q.all()]


@router.delete("/policies/team-capacity/{policy_id}", status_code=204)
def delete_team_capacity(policy_id: int,
                         db: Session = Depends(get_db),
                         user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    row = db.get(TeamCapacityPolicy, policy_id)
    if not row:
        raise HTTPException(404, "Policy not found.")
    row.is_active = False
    db.commit()
    return None


# ---------- blackout periods (admin) --------------------------------

@router.post("/policies/blackout", response_model=BlackoutPeriodOut, status_code=201)
def create_blackout(payload: BlackoutPeriodIn,
                    db: Session = Depends(get_db),
                    user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    scope = payload.scope_type.lower()
    if scope not in ("global", "department", "manager"):
        raise HTTPException(400, "scope_type must be 'global', 'department', or 'manager'.")
    if scope != "global" and not payload.scope_id:
        raise HTTPException(400, f"scope_id is required for scope_type='{scope}'.")
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "end_date cannot be before start_date.")
    row = BlackoutPeriod(
        scope_type=scope,
        scope_id=payload.scope_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        is_active=True,
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return BlackoutPeriodOut.model_validate(row)


@router.get("/policies/blackout", response_model=list[BlackoutPeriodOut])
def list_blackouts(db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_user),
                   active_only: bool = Query(True)):
    q = db.query(BlackoutPeriod)
    if active_only:
        today = date.today()
        q = q.filter(
            BlackoutPeriod.is_active.is_(True),
            BlackoutPeriod.end_date >= today,
        )
    return [BlackoutPeriodOut.model_validate(r) for r in q.order_by(BlackoutPeriod.start_date.asc()).all()]


@router.delete("/policies/blackout/{blackout_id}", status_code=204)
def delete_blackout(blackout_id: int,
                    db: Session = Depends(get_db),
                    user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    row = db.get(BlackoutPeriod, blackout_id)
    if not row:
        raise HTTPException(404, "Blackout not found.")
    row.is_active = False
    db.commit()
    return None
