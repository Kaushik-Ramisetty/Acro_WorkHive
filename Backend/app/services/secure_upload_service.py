"""Centralized secure-upload pipeline used by every HRMS module.

Pipeline
--------
1. Frontend posts a file →
2. ``begin_upload()`` validates extension, MIME magic bytes, size, sanitizes
   the filename, writes the file to ``{root}/_temp/`` and inserts a
   ``SecureUpload`` row with ``scan_status='uploaded_temp'``.
3. The Celery task ``secure_upload.scan_file`` picks up the id and runs the
   configured ClamAV scanner.
4. ``finalize_scan()`` moves the file to ``{root}/{module}/`` on 'safe' or
   ``{root}/_quarantine/`` on 'infected' / 'scan_failed' and flips the row's
   ``scan_status``.

Hard rules
----------
- Only JPG / JPEG / PNG (per spec). Anything else → 400 *immediately*.
- 250 KB hard limit, enforced **after** reading the stream so callers can
  not lie about ``Content-Length``.
- Filename is sanitized; path traversal characters (``..``, ``/``, ``\\``)
  are stripped before persistence.
- The stored filename is a random UUID + the cleaned extension — the
  caller's filename is *never* used for the on-disk name.
- Files in the ``_quarantine`` tree are NOT served to non-admins.
- Scan must complete with ``scan_status='safe'`` before any module-specific
  workflow (e.g. attaching to a leave request) treats the file as usable.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Employee, SecureUpload
from app.services.malware_scanner import get_scanner
from utils.time_utils import now_utc


logger = logging.getLogger(__name__)


# ── Config (env-overridable) ───────────────────────────────────────────────
UPLOAD_ROOT = Path(os.getenv("SECURE_UPLOAD_ROOT") or "./uploads/secure").resolve()
MAX_BYTES   = int(os.getenv("SECURE_UPLOAD_MAX_BYTES") or "256000")  # 250 KB strict
CHUNK_SIZE  = 64 * 1024

# Extensions and the MIME types they should match (magic-byte verified).
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIMES      = {"image/jpeg", "image/png"}

# Explicit blocklist — caught by the extension whitelist already, but echoing
# the spec's named offenders gives nicer error messages and serves as a
# defence-in-depth check for any future "allow more types" change.
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".js", ".mjs", ".sh", ".ps1",
    ".dll", ".so", ".dylib",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".jar", ".msi", ".scr", ".vbs",
}


# ── Filename helpers ───────────────────────────────────────────────────────
def _sanitize_filename(raw: str) -> str:
    """Strip every path component, NUL bytes, and traversal sequences.

    The returned name is safe to log / display but is **never** used as the
    on-disk filename — see ``_stored_name()``.
    """
    name = (raw or "").strip()
    # Strip directory components (handles both \ and /)
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = name.replace("\x00", "")
    # Block ".." traversal even if it survived the rsplit.
    while ".." in name:
        name = name.replace("..", "_")
    return name[:200] or "file"


def _extension_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def _has_double_extension(name: str) -> bool:
    """Reject ``foo.png.exe`` style names. We look at every dot-suffix in
    the cleaned filename and bail if any non-final one is in the blocklist
    or outside the whitelist."""
    parts = name.lower().split(".")
    if len(parts) <= 2:
        return False
    interior = ["." + p for p in parts[1:-1]]
    bad = [e for e in interior if e in BLOCKED_EXTENSIONS or e not in ALLOWED_EXTENSIONS]
    return bool(bad)


def _stored_name(ext: str) -> str:
    return f"{uuid.uuid4().hex}{ext}"


# ── MIME (magic-byte) sniff ─────────────────────────────────────────────────
def _sniff_mime(blob: bytes) -> Optional[str]:
    """Cheap magic-byte check covering the two formats we allow.

    JPEG : starts with FF D8 FF
    PNG  : starts with 89 50 4E 47 0D 0A 1A 0A
    """
    if blob.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


# ── Filesystem layout ───────────────────────────────────────────────────────
def _temp_dir() -> Path:
    d = UPLOAD_ROOT / "_temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _module_dir(module: str) -> Path:
    safe = "".join(c for c in (module or "misc") if c.isalnum() or c in ("_", "-")).lower() or "misc"
    d = UPLOAD_ROOT / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _quarantine_dir() -> Path:
    d = UPLOAD_ROOT / "_quarantine"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Public API ─────────────────────────────────────────────────────────────
def begin_upload(
    db: Session,
    *,
    actor: Employee,
    module: str,
    reference_id: Optional[str],
    filename: str,
    content_type: Optional[str],
    stream: BinaryIO,
) -> SecureUpload:
    """Validate + write to temp + insert a SecureUpload row.

    Raises ``HTTPException`` on validation failures so callers don't need
    bespoke error mapping. Never returns an unscanned-yet-permanent row —
    the caller's contract is to call ``dispatch_scan(row.id)`` next.
    """
    if not module:
        raise HTTPException(status_code=400, detail="module is required.")

    # ── 1) Filename + extension ────────────────────────────────────────
    safe_name = _sanitize_filename(filename)
    ext = _extension_of(safe_name)
    if not ext:
        raise HTTPException(status_code=400, detail="File extension is missing.")
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension '{ext}' is not allowed.")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, and PNG files are allowed.",
        )
    if _has_double_extension(safe_name):
        raise HTTPException(status_code=400, detail="File has a suspicious double extension.")

    # ── 2) Content-Type header sanity (best-effort; we re-verify by magic
    #       bytes below). Treat missing header as 'application/octet-stream'.
    declared = (content_type or "").lower().split(";", 1)[0].strip()
    if declared and declared not in ALLOWED_MIMES and declared != "application/octet-stream":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported MIME type '{declared}'. Expected image/jpeg or image/png.",
        )

    # ── 3) Stream to temp file with hard 250 KB ceiling ────────────────
    tmp_dir = _temp_dir()
    stored_name = _stored_name(ext)
    temp_path = tmp_dir / stored_name

    first_chunk: Optional[bytes] = None
    bytes_written = 0
    try:
        with open(temp_path, "wb") as out:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                if first_chunk is None:
                    first_chunk = chunk[:16]
                bytes_written += len(chunk)
                if bytes_written > MAX_BYTES:
                    out.close()
                    temp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {MAX_BYTES // 1024} KB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        temp_path.unlink(missing_ok=True)
        logger.exception("secure_upload: temp write failed")
        raise HTTPException(status_code=500, detail="Failed to receive upload.") from exc

    if bytes_written == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File is empty.")

    # ── 4) Magic-byte verification (defends against ext-renamed payloads) ──
    sniffed = _sniff_mime(first_chunk or b"")
    if sniffed not in ALLOWED_MIMES:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="File contents do not match a valid JPG/PNG image.",
        )
    # Cross-check ext vs. magic bytes.
    if ext == ".png" and sniffed != "image/png":
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="PNG extension does not match PNG signature.")
    if ext in (".jpg", ".jpeg") and sniffed != "image/jpeg":
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="JPG extension does not match JPEG signature.")

    # ── 5) Persist the tracking row ────────────────────────────────────
    row = SecureUpload(
        uploaded_by=actor.id,
        module=module,
        reference_id=str(reference_id) if reference_id else None,
        original_filename=safe_name,
        stored_filename=stored_name,
        mime_type=sniffed,
        size_bytes=bytes_written,
        temp_path=str(temp_path),
        scan_status="uploaded_temp",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "secure_upload: uploaded_temp id=%s module=%s actor=%s size=%d",
        row.id, module, actor.id, bytes_written,
    )
    return row


def dispatch_scan(upload_id: int) -> None:
    """Queue the async scan. Falls back to synchronous scan when Celery is
    unavailable (dev or broker outage) so the workflow never strands rows
    in 'uploaded_temp' forever."""
    try:
        from app.tasks.scan_upload import scan_secure_upload
        scan_secure_upload.delay(upload_id)
        return
    except Exception as exc:  # broker down / celery import-time issue
        logger.warning("secure_upload: dispatch_scan fallback to inline (%s)", exc)
    # Inline fallback — runs in the request thread. Slow but safe.
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        scan_and_finalize(db, upload_id)


def scan_and_finalize(db: Session, upload_id: int) -> SecureUpload:
    """Run the scan + finalize step in-process. The Celery task is a thin
    wrapper around this so dev-without-broker and prod-with-broker share
    the exact same code path."""
    row: SecureUpload | None = db.get(SecureUpload, upload_id)
    if not row:
        raise RuntimeError(f"SecureUpload {upload_id} not found")
    if row.scan_status not in ("uploaded_temp", "scan_failed"):
        # Already finalized — idempotent no-op.
        return row

    row.scan_status = "scanning"
    row.scan_started_at = now_utc()
    row.scan_attempts = (row.scan_attempts or 0) + 1
    db.commit()

    if not row.temp_path or not Path(row.temp_path).exists():
        row.scan_status = "scan_failed"
        row.scan_error = "Temporary file missing on disk."
        row.scan_completed_at = now_utc()
        db.commit()
        db.refresh(row)
        return row

    result = get_scanner().scan_path(row.temp_path)
    row.scan_engine = result.engine
    row.scan_completed_at = now_utc()

    if result.status == "clean":
        # Move to permanent module storage.
        dest = _module_dir(row.module) / row.stored_filename
        try:
            shutil.move(row.temp_path, str(dest))
            row.storage_path = str(dest)
            row.temp_path = None
            row.scan_status = "safe"
            row.malware_detected = False
            row.scan_error = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("secure_upload: finalize move failed")
            row.scan_status = "scan_failed"
            row.scan_error = f"Storage move failed: {exc}"
    elif result.status == "infected":
        q = _quarantine_dir() / f"{row.id}_{row.stored_filename}"
        _move_to(row.temp_path, q, row)
        row.quarantine_path = str(q)
        row.scan_status = "infected"
        row.malware_detected = True
        row.scan_signature = (result.detail or "")[:120]
        row.scan_error = None
        logger.warning(
            "secure_upload: INFECTED id=%s module=%s engine=%s signature=%r",
            row.id, row.module, result.engine, result.detail,
        )
        _notify_admins_infected(db, row)
    else:  # 'scan_failed'
        # Keep the file in quarantine until an admin re-runs or deletes.
        q = _quarantine_dir() / f"{row.id}_{row.stored_filename}"
        _move_to(row.temp_path, q, row)
        row.quarantine_path = str(q)
        row.scan_status = "scan_failed"
        row.scan_error = (result.detail or "Unknown scan error")[:500]

    db.commit()
    db.refresh(row)
    return row


def _move_to(src: Optional[str], dest: Path, row: SecureUpload) -> None:
    if not src:
        return
    try:
        shutil.move(src, str(dest))
        row.temp_path = None
    except Exception:
        logger.exception("secure_upload: quarantine move failed")


def _notify_admins_infected(db: Session, row: SecureUpload) -> None:
    """Best-effort audit log + admin notification when malware is detected."""
    try:
        from app.models import Notification, Employee, Role
        admins = (
            db.query(Employee.id)
            .join(Role)
            .filter(Role.name.in_(["admin", "hr"]), Employee.is_deleted.is_(False))
            .all()
        )
        title = "Malware detected in uploaded file"
        body = (
            f"Upload #{row.id} ({row.original_filename}) from employee "
            f"#{row.uploaded_by} in module '{row.module}' was flagged "
            f"INFECTED by {row.scan_engine}: {row.scan_signature}"
        )
        for (aid,) in admins:
            db.add(Notification(
                recipient_id=aid,
                type="malware_detected",
                title=title,
                body=body,
                reference_table="secure_uploads",
                reference_id=str(row.id),
            ))
    except Exception:
        logger.exception("secure_upload: admin notify failed (non-fatal)")


# ── Cleanup helpers ────────────────────────────────────────────────────────
def cleanup_orphaned_temp(db: Session, *, older_than_minutes: int = 30) -> int:
    """Sweep abandoned uploads in `_temp/` whose row never moved past
    'uploaded_temp' or 'scanning'. Called by a Celery beat task."""
    from datetime import timedelta
    cutoff = now_utc() - timedelta(minutes=older_than_minutes)
    rows = (
        db.query(SecureUpload)
        .filter(
            SecureUpload.scan_status.in_(["uploaded_temp", "scanning"]),
            SecureUpload.created_at < cutoff,
        )
        .all()
    )
    n = 0
    for r in rows:
        if r.temp_path:
            try:
                Path(r.temp_path).unlink(missing_ok=True)
            except Exception:
                pass
        r.scan_status = "scan_failed"
        r.scan_error = "Scan timed out — temp file cleaned."
        r.temp_path = None
        n += 1
    if n:
        db.commit()
    return n


def resolve_for_download(actor: Employee, row: SecureUpload) -> Path:
    """Authorization + filesystem resolver for module-facing download
    endpoints. Non-admins can only download 'safe' files they uploaded."""
    is_admin = bool(actor.role and actor.role.name.lower() in ("admin", "hr"))
    if not is_admin:
        if row.scan_status != "safe":
            raise HTTPException(status_code=403, detail="File is not available.")
        if actor.id != row.uploaded_by:
            raise HTTPException(status_code=403, detail="Not allowed.")
    path = row.storage_path or row.quarantine_path
    if not path:
        raise HTTPException(status_code=404, detail="File is missing from storage.")
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File is missing from storage.")
    # Path-traversal guard: ensure the resolved path is still under our root.
    try:
        p.resolve().relative_to(UPLOAD_ROOT)
    except Exception:
        raise HTTPException(status_code=403, detail="Refusing to serve file outside upload root.")
    return p
