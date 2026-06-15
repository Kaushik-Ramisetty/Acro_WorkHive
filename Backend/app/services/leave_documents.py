"""Document upload + scan pipeline for leave requests.

Files are stored under LEAVE_UPLOAD_DIR (default: ./uploads/leave/).
On upload:
  1. Persist file to staging path
  2. Insert LeaveDocument row with scan_status='pending'
  3. Hand the path to the configured scanner (ClamAV / null)
  4. Update the row with the scan result
  5. On 'infected'/'scan_failed', move the file under a `quarantine/`
     subdirectory so it can't be served by accident.

The route layer treats only 'clean' documents as visible to non-admins.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.models import Employee, LeaveDocument, LeaveRequest, Notification
from app.services.email_dispatcher import dispatch_for_recipient
from app.services.malware_scanner import get_scanner
from utils.time_utils import now_utc


# Default storage root. Override with LEAVE_UPLOAD_DIR.
DEFAULT_UPLOAD_DIR = Path(os.getenv("LEAVE_UPLOAD_DIR") or "./uploads/leave").resolve()

MAX_FILE_BYTES = int(os.getenv("LEAVE_DOCUMENT_MAX_BYTES") or str(10 * 1024 * 1024))  # 10 MB
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".doc", ".docx",
    ".xls", ".xlsx", ".txt",
}


class DocumentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _safe_filename(name: str) -> str:
    # Strip directory components and replace whitespace.
    base = os.path.basename(name or "").strip().replace("\\", "_").replace("/", "_")
    base = base.replace("..", "_")
    return base[:200] or "file"


def _ext_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def _request_dir(req_id: str) -> Path:
    d = DEFAULT_UPLOAD_DIR / req_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _quarantine_dir(req_id: str) -> Path:
    d = DEFAULT_UPLOAD_DIR / "_quarantine" / req_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _notify_admins_infected(db: Session, req: LeaveRequest, doc: LeaveDocument) -> None:
    from app.services.leave_engine import _hr_user_ids
    title = "Infected file uploaded to a leave request"
    body = (
        f"LeaveDocument #{doc.id} ('{doc.original_filename}') attached to "
        f"leave {req.id} was flagged as INFECTED by {doc.scan_engine}: "
        f"{doc.scan_detail}"
    )
    for hr_id in _hr_user_ids(db):
        db.add(Notification(
            recipient_id=hr_id, type="leave_doc_infected",
            title=title, body=body, leave_request_id=req.id,
        ))
        try:
            dispatch_for_recipient(db, hr_id, title, body)
        except Exception:
            pass


def upload_document(db: Session, actor: Employee, req: LeaveRequest,
                    filename: str, content_type: str | None,
                    stream: BinaryIO) -> LeaveDocument:
    """Save + scan + persist. Caller commits the surrounding transaction."""
    # ---- authorization
    if req.status in ("rejected", "cancelled", "consumed"):
        raise DocumentError(400, f"Cannot attach to a request in status '{req.status}'.")
    role = (actor.role.name.lower() if actor.role else "")
    is_admin = role == "admin"
    if not is_admin and actor.id != req.employee_id:
        raise DocumentError(403, "Only the requester or an admin can attach a document.")

    # ---- filename / extension / size sanity
    safe_name = _safe_filename(filename)
    ext = _ext_of(safe_name)
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(400, f"File extension '{ext}' is not allowed.")

    # Write to a uuid-named path so concurrent uploads of the same filename
    # don't clobber each other.
    target_dir = _request_dir(req.id)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = target_dir / stored_name

    bytes_written = 0
    with open(stored_path, "wb") as out:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_FILE_BYTES:
                out.close()
                stored_path.unlink(missing_ok=True)
                raise DocumentError(
                    413, f"File exceeds {MAX_FILE_BYTES // (1024*1024)} MB limit.",
                )
            out.write(chunk)

    doc = LeaveDocument(
        leave_request_id=req.id,
        uploaded_by=actor.id,
        original_filename=safe_name,
        stored_path=str(stored_path),
        content_type=content_type,
        size_bytes=bytes_written,
        scan_status="pending",
    )
    db.add(doc)
    db.flush()  # need doc.id for any quarantine moves

    # ---- scan
    scanner = get_scanner()
    result = scanner.scan_path(str(stored_path))
    doc.scan_engine = result.engine
    doc.scan_detail = result.detail
    doc.scanned_at = now_utc()
    doc.scan_status = result.status

    if result.status != "clean":
        # Move out of the main path so a misconfigured download endpoint
        # can never serve it.
        q_dir = _quarantine_dir(req.id)
        q_path = q_dir / stored_name
        try:
            shutil.move(str(stored_path), str(q_path))
            doc.stored_path = str(q_path)
        except Exception:
            # Best-effort: if move fails, at least the row is marked.
            pass

    if result.status == "infected":
        _notify_admins_infected(db, req, doc)

    db.commit()
    db.refresh(doc)
    return doc


def list_documents(db: Session, actor: Employee, req: LeaveRequest) -> list[LeaveDocument]:
    role = (actor.role.name.lower() if actor.role else "")
    is_admin = role == "admin"
    can_view = (
        is_admin
        or actor.id == req.employee_id
        or (role == "manager" and req.employee and req.employee.reporting_manager_id == actor.id)
    )
    if not can_view:
        raise DocumentError(403, "Not allowed.")

    rows = (
        db.query(LeaveDocument)
        .filter(LeaveDocument.leave_request_id == req.id)
        .order_by(LeaveDocument.uploaded_at.asc())
        .all()
    )
    # Non-admins only see clean docs (others are quarantine artifacts).
    if not is_admin:
        rows = [r for r in rows if r.scan_status == "clean"]
    return rows


def delete_document(db: Session, actor: Employee, doc: LeaveDocument) -> None:
    role = (actor.role.name.lower() if actor.role else "")
    is_admin = role == "admin"
    if not is_admin and actor.id != doc.uploaded_by:
        raise DocumentError(403, "Only the uploader or an admin can remove this document.")
    # Best-effort filesystem cleanup.
    try:
        p = Path(doc.stored_path)
        if p.exists():
            p.unlink()
    except Exception:
        pass
    db.delete(doc)
    db.commit()


def resolve_for_download(actor: Employee, doc: LeaveDocument) -> Path:
    role = (actor.role.name.lower() if actor.role else "")
    is_admin = role == "admin"
    if doc.scan_status != "clean" and not is_admin:
        raise DocumentError(403, "This document is not available for download.")
    p = Path(doc.stored_path)
    if not p.exists():
        raise DocumentError(404, "File is missing from storage.")
    return p
