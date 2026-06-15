"""
services/document_service.py — Candidate document upload and retrieval.

Files are saved to UPLOAD_DIR/documents/{candidate_id}/ on the local filesystem.
Swap out for S3/Azure Blob in production by replacing _save_file().
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from api.models import Candidate, CandidateDocument, CandidateStatus, DocumentStatus
from api.Onboarding_Model.services.candidate_service import get_candidate_or_404
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)

UPLOAD_DIR   = os.getenv("UPLOAD_DIR", "./uploads")
MAX_SIZE_MB  = int(os.getenv("MAX_UPLOAD_SIZE_MB", 10))
ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}


def _save_file(file: UploadFile, candidate_id: int) -> Tuple[str, int]:
    """
    Persist an UploadFile to disk.
    Returns (relative_url, size_kb).
    """
    doc_dir = Path(UPLOAD_DIR) / "documents" / str(candidate_id)
    doc_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTS)}",
        )

    safe_name = Path(file.filename or "upload").name
    dest = doc_dir / safe_name

    # Handle filename collisions
    counter = 1
    while dest.exists():
        dest = doc_dir / f"{dest.stem}_{counter}{ext}"
        counter += 1

    content = file.file.read()
    size_kb = len(content) // 1024

    if size_kb > MAX_SIZE_MB * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File '{file.filename}' exceeds the {MAX_SIZE_MB} MB limit.",
        )

    dest.write_bytes(content)
    relative_url = f"/uploads/documents/{candidate_id}/{dest.name}"
    logger.info("Saved document: %s (%d KB)", relative_url, size_kb)
    return relative_url, size_kb


def upload_documents(
    candidate_id: int,
    doc_type: str,
    files: List[UploadFile],
    db: Session,
) -> Tuple[List[CandidateDocument], int]:
    """
    Save one or more files for a candidate and create DB records.
    Returns (list_of_saved_docs, failure_count).
    """
    candidate = get_candidate_or_404(candidate_id, db)

    saved: List[CandidateDocument] = []
    failures = 0

    for file in files:
        try:
            url, size_kb = _save_file(file, candidate_id)
            doc = CandidateDocument(
                candidate_id=candidate_id,
                doc_type=doc_type,
                original_filename=file.filename or "unknown",
                file_url=url,
                file_size_kb=size_kb,
                status=DocumentStatus.UPLOADED.value,
            )
            db.add(doc)
            saved.append(doc)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to save file '%s': %s", file.filename, exc)
            failures += 1

    if saved:
        db.flush()  # get IDs before commit

        # After first upload, advance candidate status to DOCS_PENDING (if still at OFFER_ACCEPTED)
        if candidate.status == CandidateStatus.OFFER_ACCEPTED.value:
            candidate.status = CandidateStatus.DOCS_PENDING.value

        # If ALL required docs uploaded, move to DOCS_SUBMITTED
        # (business rule: at least 1 doc = submitted; adjust threshold as needed)
        if candidate.status in (
            CandidateStatus.DOCS_PENDING.value,
            CandidateStatus.OFFER_ACCEPTED.value,
        ):
            candidate.status = CandidateStatus.DOCS_SUBMITTED.value

        db.commit()
        for doc in saved:
            db.refresh(doc)

    return saved, failures


def get_candidate_documents(candidate_id: int, db: Session) -> List[CandidateDocument]:
    get_candidate_or_404(candidate_id, db)  # ensure candidate exists
    return (
        db.query(CandidateDocument)
        .filter(CandidateDocument.candidate_id == candidate_id)
        .order_by(CandidateDocument.uploaded_at.desc())
        .all()
    )


def verify_document(doc_id: int, approved: bool, remarks: str | None, db: Session, actor_employee_id: int | None = None) -> CandidateDocument:
    doc = db.query(CandidateDocument).filter(CandidateDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    from datetime import datetime
    doc.status = DocumentStatus.VERIFIED.value if approved else DocumentStatus.REJECTED.value
    doc.verified_at = now_utc()
    doc.remarks = remarks
    db.commit()
    db.refresh(doc)
    # Audit log: who verified/rejected what.
    try:
        from api.Onboarding_Model.services.bgv_service import write_bgv_audit
        write_bgv_audit(
            db, actor_employee_id,
            f"document.{'verify' if approved else 'reject'}",
            candidate_id=doc.candidate_id,
            old_value=str(doc_id),
            new_value=DocumentStatus.VERIFIED.value if approved else DocumentStatus.REJECTED.value,
        )
        db.commit()
    except Exception as exc:
        logger.warning("Document audit write failed (doc_id=%s): %s", doc_id, exc)
    return doc
