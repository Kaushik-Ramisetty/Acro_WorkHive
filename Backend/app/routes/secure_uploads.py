"""Centralized secure-upload routes — used by every module.

POST /secure-uploads
  multipart/form-data: file=<file>, module=<str>, reference_id=<str?>
  → validates + writes to temp + queues Celery scan
  → returns the new SecureUpload row (status='uploaded_temp' or 'scanning')

GET /secure-uploads/{id}
  → poll the status — frontends call this until status in
    ('safe','infected','scan_failed','rejected') to flip their UI.

GET /secure-uploads/mine
  → list the caller's recent uploads (optional filter by module).

GET /admin/secure-uploads
  → admin-only, with status/module filters. Drives the Quarantine view.

POST /admin/secure-uploads/{id}/rescan
  → admin re-triggers a scan on a scan_failed row.

DELETE /secure-uploads/{id}
  → uploader (only if not yet safe) or admin removes the row + file.

GET /secure-uploads/{id}/download
  → safe files only (non-admins). Admin can download quarantined files.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as PathParam, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee, SecureUpload
from app.services import secure_upload_service as svc


router = APIRouter(prefix="/secure-uploads", tags=["secure-uploads"])


class SecureUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    uploaded_by: int
    module: str
    reference_id: Optional[str] = None
    original_filename: str
    mime_type: Optional[str] = None
    size_bytes: int
    scan_status: str
    malware_detected: bool
    scan_engine: Optional[str] = None
    # `scan_signature` and `scan_error` carry sensitive engine detail. We do
    # NOT include them in the schema — the admin endpoint exposes them via
    # AdminSecureUploadOut below.
    created_at: Optional[str] = None  # ISO formatted by validator
    scan_completed_at: Optional[str] = None

    @classmethod
    def from_row(cls, r: SecureUpload) -> "SecureUploadOut":
        return cls(
            id=r.id,
            uploaded_by=r.uploaded_by,
            module=r.module,
            reference_id=r.reference_id,
            original_filename=r.original_filename,
            mime_type=r.mime_type,
            size_bytes=r.size_bytes,
            scan_status=r.scan_status,
            malware_detected=r.malware_detected,
            scan_engine=r.scan_engine,
            created_at=r.created_at.isoformat() if r.created_at else None,
            scan_completed_at=r.scan_completed_at.isoformat() if r.scan_completed_at else None,
        )


class AdminSecureUploadOut(SecureUploadOut):
    scan_signature: Optional[str] = None
    scan_error:     Optional[str] = None
    scan_attempts:  int = 0
    storage_path:   Optional[str] = None
    quarantine_path: Optional[str] = None

    @classmethod
    def from_row(cls, r: SecureUpload) -> "AdminSecureUploadOut":  # type: ignore[override]
        base = SecureUploadOut.from_row(r).model_dump()
        base.update(
            scan_signature=r.scan_signature,
            scan_error=r.scan_error,
            scan_attempts=r.scan_attempts or 0,
            storage_path=r.storage_path,
            quarantine_path=r.quarantine_path,
        )
        return cls(**base)


# ─── Upload ────────────────────────────────────────────────────────────────
@router.post("", response_model=SecureUploadOut, status_code=201)
async def upload(
    module: str = Form(..., description="leave | onboarding | regularization | profile | payroll | timesheet | …"),
    reference_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    row = svc.begin_upload(
        db,
        actor=user,
        module=module,
        reference_id=reference_id,
        filename=file.filename or "file",
        content_type=file.content_type,
        stream=file.file,
    )
    svc.dispatch_scan(row.id)
    db.refresh(row)
    return SecureUploadOut.from_row(row)


# ─── Status ────────────────────────────────────────────────────────────────
@router.get("/{upload_id}", response_model=SecureUploadOut)
def get_status(upload_id: int = PathParam(..., ge=1),
               db: Session = Depends(get_db),
               user: Employee = Depends(get_current_user)):
    row = db.get(SecureUpload, upload_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")
    is_admin = bool(user.role and user.role.name.lower() in ("admin", "hr"))
    if not is_admin and row.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    return SecureUploadOut.from_row(row)


@router.get("/mine/list", response_model=list[SecureUploadOut])
def list_mine(module: Optional[str] = Query(None),
              limit: int = Query(50, ge=1, le=200),
              db: Session = Depends(get_db),
              user: Employee = Depends(get_current_user)):
    q = db.query(SecureUpload).filter(SecureUpload.uploaded_by == user.id)
    if module:
        q = q.filter(SecureUpload.module == module)
    rows = q.order_by(SecureUpload.created_at.desc()).limit(limit).all()
    return [SecureUploadOut.from_row(r) for r in rows]


# ─── Download ──────────────────────────────────────────────────────────────
@router.get("/{upload_id}/download")
def download(upload_id: int = PathParam(..., ge=1),
             db: Session = Depends(get_db),
             user: Employee = Depends(get_current_user)):
    row = db.get(SecureUpload, upload_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")
    path = svc.resolve_for_download(user, row)
    return FileResponse(
        path=str(path),
        media_type=row.mime_type or "application/octet-stream",
        filename=row.original_filename,
    )


# ─── Delete ────────────────────────────────────────────────────────────────
@router.delete("/{upload_id}", status_code=204)
def delete_upload(upload_id: int = PathParam(..., ge=1),
                  db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    row = db.get(SecureUpload, upload_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")
    is_admin = bool(user.role and user.role.name.lower() in ("admin", "hr"))
    # Uploader can only delete their own non-finalized rows; admins always.
    if not is_admin:
        if row.uploaded_by != user.id:
            raise HTTPException(status_code=403, detail="Not allowed")
        if row.scan_status == "safe":
            # Once a file is linked into a workflow we don't want a random
            # uploader to nuke it — modules are responsible for their own
            # un-link semantics.
            raise HTTPException(status_code=409, detail="Cannot delete a finalized upload here; use the module endpoint.")
    # Best-effort filesystem cleanup.
    from pathlib import Path
    for p in (row.temp_path, row.storage_path, row.quarantine_path):
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
    db.delete(row)
    db.commit()
    return None


# ─── Admin: list / rescan ──────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin/secure-uploads", tags=["admin"])


def _require_admin(user: Employee) -> None:
    if not user.role or user.role.name.lower() not in ("admin", "hr"):
        raise HTTPException(status_code=403, detail="Admin only")


@admin_router.get("", response_model=list[AdminSecureUploadOut])
def admin_list(
    status: Optional[str] = Query(None, description="uploaded_temp|scanning|safe|infected|scan_failed|rejected"),
    module: Optional[str] = Query(None),
    infected_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    _require_admin(user)
    q = db.query(SecureUpload)
    if infected_only:
        q = q.filter(SecureUpload.malware_detected.is_(True))
    if status:
        q = q.filter(SecureUpload.scan_status == status)
    if module:
        q = q.filter(SecureUpload.module == module)
    rows = q.order_by(SecureUpload.created_at.desc()).offset(offset).limit(limit).all()
    return [AdminSecureUploadOut.from_row(r) for r in rows]


@admin_router.post("/{upload_id}/rescan", response_model=AdminSecureUploadOut)
def admin_rescan(upload_id: int,
                 db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_user)):
    _require_admin(user)
    row = db.get(SecureUpload, upload_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")
    if row.scan_status not in ("scan_failed", "infected"):
        raise HTTPException(status_code=400, detail=f"Cannot rescan a row in status '{row.scan_status}'.")
    # If the file currently lives in quarantine, move it back to temp so
    # the scanner picks it up again.
    from pathlib import Path
    if row.quarantine_path and Path(row.quarantine_path).exists():
        import shutil
        new_temp = svc._temp_dir() / row.stored_filename
        try:
            shutil.move(row.quarantine_path, str(new_temp))
            row.temp_path = str(new_temp)
            row.quarantine_path = None
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to stage file for rescan.")
    row.scan_status = "uploaded_temp"
    row.scan_error = None
    row.scan_signature = None
    db.commit()
    svc.dispatch_scan(row.id)
    db.refresh(row)
    return AdminSecureUploadOut.from_row(row)
