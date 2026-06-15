"""
api/Onboarding_Model/candidate_portal.py — Candidate self-service portal API.

Endpoints (prefix: /api/v1):
  GET  /api/v1/candidate/resolve                 → look up candidate by email
  GET  /api/v1/candidate/status/{candidate_id}   → progress for 5-step dashboard tracker
  POST /api/v1/candidate/documents/upload        → upload documents (PDF/JPG/PNG only)
  POST /api/v1/bgv/initiate                      → candidate initiates BGV
"""

import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, created, error
from api.models import (
    Candidate, CandidateDocument, CandidateStatus,
    BGVCheck, BGVStatus, BGVToken, DocumentStatus,
    OnboardedEmployeeStatus,
)
from api.Onboarding_Model.services.candidate_service import get_candidate_or_404

# Vendor link config
_FRONTEND_BASE    = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
_TOKEN_TTL_HOURS  = int(os.getenv("BGV_TOKEN_TTL_HOURS", "48"))
from api.Onboarding_Model.services.document_service import _save_file, UPLOAD_DIR
from utils.time_utils import now_utc
from utils.jwt_auth import CurrentUser, get_current_user, optional_current_user, requires_role


def _candidate_can_access(user: CurrentUser, candidate_id: int) -> bool:
    """A candidate may only see their own record; HR sees everyone."""
    if user.role in {"admin", "hr"}:
        return True
    if user.role == "candidate" and user.candidate_id == candidate_id:
        return True
    return False


def _ensure_candidate_self_or_hr(user: CurrentUser, candidate_id: int) -> None:
    if not _candidate_can_access(user, candidate_id):
        raise HTTPException(status_code=403, detail="Not permitted to access this candidate.")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Candidate Portal"])

# All document types accepted by the portal
ALLOWED_DOC_TYPES: set[str] = {
    "bgv_form", "aadhar", "pan", "qualification",
    "exp1", "exp2", "exp3",
    "address_proof", "cif",
}
# Mandatory to upload (BGV cannot start without all of these)
REQUIRED_DOC_TYPES: set[str] = {
    "bgv_form", "aadhar", "pan", "qualification", "address_proof", "cif",
}
# Optional — uploaded if available, not required to enable BGV button
OPTIONAL_DOC_TYPES: set[str] = {"exp1", "exp2", "exp3"}
# Alias kept for backward-compat with other modules that import this name
BGV_REQUIRED_DOC_TYPES = REQUIRED_DOC_TYPES

# Statuses that mean the offer has been accepted (and beyond)
_OFFER_ACCEPTED_ONWARDS = {
    CandidateStatus.OFFER_ACCEPTED.value,
    CandidateStatus.DOCS_PENDING.value,
    CandidateStatus.DOCS_SUBMITTED.value,
    CandidateStatus.BGV_IN_PROGRESS.value,
    CandidateStatus.BGV_CLEAR.value,
    CandidateStatus.BGV_FAILED.value,
    CandidateStatus.BGV_ON_HOLD.value,
    CandidateStatus.CONVERTED.value,
    CandidateStatus.JOINED.value,
}


# ── Resolve Candidate by Email ────────────────────────────────────────────────

@router.get("/candidate/resolve")
def resolve_candidate_by_email(email: str, db: Session = Depends(get_db)):
    """
    Look up a candidate record by email address.
    Used by the portal when candidateId is not available in the session.
    Returns { candidate_id, name, status }.
    """
    from sqlalchemy import func as _func
    candidate = (
        db.query(Candidate)
        .filter(_func.lower(Candidate.email) == email.strip().lower())
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail=f"No candidate found with email '{email}'")
    return ok(data={
        "candidate_id": candidate.id,
        "name":         candidate.name,
        "status":       candidate.status,
    })


# ── Status Tracker ────────────────────────────────────────────────────────────

@router.get("/candidate/status/{candidate_id}")
def get_candidate_progress(
    candidate_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _ensure_candidate_self_or_hr(user, candidate_id)
    """
    Returns candidate progress for the 5-step onboarding tracker.

    Steps:
      1. Profile Created      — always complete
      2. Offer Accepted       — status >= OFFER_ACCEPTED
      3. Documents Uploaded   — all 6 required doc types uploaded
      4. BGV Initiated        — bgv_check record exists
      5. Employee Activated   — onboarded_employee.status == ACTIVE
    """
    candidate = get_candidate_or_404(candidate_id, db)

    uploaded_types = {
        d.doc_type
        for d in candidate.documents
        if d.status in (DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value)
    }
    verified_types = {
        d.doc_type
        for d in candidate.documents
        if d.status == DocumentStatus.VERIFIED.value
    }
    rejected_types = {
        d.doc_type
        for d in candidate.documents
        if d.status == DocumentStatus.REJECTED.value
    }
    docs_done_count = len(uploaded_types & REQUIRED_DOC_TYPES)  # mandatory only
    all_docs_uploaded = docs_done_count >= len(REQUIRED_DOC_TYPES)
    # NEW: every required doc is in VERIFIED state — gates HR's "Initiate BGV"
    documents_verified = (verified_types & REQUIRED_DOC_TYPES) == REQUIRED_DOC_TYPES

    steps = [
        {
            "key":   "profile_created",
            "label": "Profile Created",
            "done":  True,
        },
        {
            "key":   "offer_accepted",
            "label": "Offer Accepted",
            "done":  candidate.status in _OFFER_ACCEPTED_ONWARDS,
        },
        {
            "key":   "documents_uploaded",
            "label": "Documents Uploaded",
            "done":  all_docs_uploaded,
        },
        {
            "key":   "bgv_initiated",
            "label": "BGV Initiated",
            "done":  candidate.bgv_check is not None,
        },
        {
            "key":   "employee_activated",
            "label": "Employee Activated",
            "done":  (
                candidate.onboarded_employee is not None
                and candidate.onboarded_employee.status == OnboardedEmployeeStatus.ACTIVE.value
            ),
        },
    ]

    return ok(
        data={
            "candidate_id":        candidate.id,
            "candidate_name":      candidate.name,
            "candidate_ref":       candidate.candidate_ref,
            "name":                candidate.name,
            "email":               candidate.email,
            "role":                candidate.role,
            "department":          candidate.department,
            "status":              candidate.status,
            "current_status":      candidate.status,
            "document_count":      docs_done_count,
            "total_required_documents": len(REQUIRED_DOC_TYPES),   # mandatory only
            "docs_uploaded_count": docs_done_count,
            "docs_required":       len(REQUIRED_DOC_TYPES),
            "uploaded_doc_types":  sorted(uploaded_types),
            "verified_doc_types":  sorted(verified_types & REQUIRED_DOC_TYPES),
            "rejected_doc_types":  sorted(rejected_types & REQUIRED_DOC_TYPES),
            "all_docs_uploaded":   all_docs_uploaded,
            # NEW: gates HR's Initiate-BGV button. True only when every required
            # document is in VERIFIED state.
            "documents_verified":  documents_verified,
            # Convenience: BGV is initiable iff docs are verified AND no BGV record yet.
            "bgv_initiable":       documents_verified and candidate.bgv_check is None,
            # Only expose real BGV status once offer is accepted.
            # For candidates still in early pipeline, always return None (= Not Initiated)
            # so stale bgv_check rows in the DB never pollute the display.
            # BGV status is only meaningful once BGV has been formally initiated.
            # DOCS_PENDING / DOCS_SUBMITTED = documents phase, BGV not yet started.
            # Stale bgv_check rows with CLEAR/FAILED must never show in these stages.
            "bgv_status": (
                candidate.bgv_check.status
                if candidate.bgv_check and candidate.status not in {
                    CandidateStatus.CREATED.value,
                    CandidateStatus.OFFER_GENERATED.value,
                    CandidateStatus.OFFER_SENT.value,
                    CandidateStatus.OFFER_REJECTED.value,
                    CandidateStatus.DOCS_PENDING.value,
                    CandidateStatus.DOCS_SUBMITTED.value,
                }
                else None
            ),
            "offer_accepted_at":   candidate.offer_accepted_at.isoformat() if candidate.offer_accepted_at else None,
            "joined_on":           (
                candidate.onboarded_employee.joining_date.isoformat()
                if candidate.onboarded_employee and candidate.onboarded_employee.joining_date
                else None
            ),
            "steps":               steps,
        },
        message="Candidate progress retrieved",
    )


# ── Document Upload ───────────────────────────────────────────────────────────

_PORTAL_ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}


@router.post("/candidate/documents/upload")
async def candidate_upload_documents(
    candidate_id:  int        = Form(..., description="Candidate DB id"),
    document_type: str        = Form(..., description="bgv_form|aadhar|pan|qualification|exp1|exp2|exp3|address_proof|cif"),
    file:          UploadFile = File(..., description="PDF, JPG, or PNG file"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _ensure_candidate_self_or_hr(user, candidate_id)
    """
    Candidate uploads a single document for their onboarding.

    Rules:
      • Accepted formats: PDF, JPG, PNG
      • Max file size: 10 MB
      • document_type must be one of: bgv_form, aadhar, pan, qualification, exp1, exp2, exp3, address_proof, cif
    """
    if document_type not in ALLOWED_DOC_TYPES:
        return error(
            f"Invalid document_type '{document_type}'. "
            f"Accepted types: {', '.join(sorted(ALLOWED_DOC_TYPES))}",
            status_code=400,
        )

    # Extension pre-check (before touching disk)
    fname = file.filename or ""
    ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
    if ext not in _PORTAL_ALLOWED_EXTS:
        return error(
            f"'{fname}' has an unsupported format. Accepted: PDF, JPG, PNG",
            status_code=415,
        )

    candidate = get_candidate_or_404(candidate_id, db)

    # Block uploads once BGV has been initiated (status >= BGV_IN_PROGRESS)
    _bgv_locked_statuses = {
        CandidateStatus.BGV_IN_PROGRESS.value,
        CandidateStatus.BGV_CLEAR.value,
        CandidateStatus.BGV_FAILED.value,
        CandidateStatus.BGV_ON_HOLD.value,
        CandidateStatus.CONVERTED.value,
        CandidateStatus.JOINED.value,
    }
    if candidate.status in _bgv_locked_statuses:
        return error(
            "Document uploads are locked after BGV has been initiated. Contact HR to reset.",
            status_code=423,
        )

    # Replace any existing UPLOADED (not yet verified) record for this doc_type so
    # re-uploads don't stack duplicate rows. VERIFIED records are never touched.
    existing_unverified = (
        db.query(CandidateDocument)
        .filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.doc_type == document_type,
            CandidateDocument.status == DocumentStatus.UPLOADED.value,
        )
        .all()
    )
    for old_doc in existing_unverified:
        db.delete(old_doc)
    if existing_unverified:
        db.flush()

    # Save file to disk and create the DB record
    try:
        url, size_kb = _save_file(file, candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Upload failed for '%s': %s", file.filename, exc)
        return error(f"Could not save file: {exc}", status_code=500)

    doc = CandidateDocument(
        candidate_id=candidate_id,
        doc_type=document_type,
        original_filename=file.filename or "upload",
        file_url=url,
        file_size_kb=size_kb,
        status=DocumentStatus.UPLOADED.value,
    )
    db.add(doc)
    db.flush()

    # Advance status: any pre-docs status → DOCS_PENDING
    _pre_docs = {
        CandidateStatus.CREATED.value,
        CandidateStatus.OFFER_GENERATED.value,
        CandidateStatus.OFFER_SENT.value,
        CandidateStatus.OFFER_ACCEPTED.value,
    }
    if candidate.status in _pre_docs:
        candidate.status = CandidateStatus.DOCS_PENDING.value

    # Compute uploaded types for the response (status advancement to
    # DOCS_SUBMITTED is now done explicitly by POST /candidate/submit/{id}
    # so the candidate gets a clear submit step instead of a silent flip.)
    all_uploaded_types = {
        d.doc_type
        for d in db.query(CandidateDocument)
        .filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.status.in_(
                [DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value]
            ),
        )
        .all()
    }

    db.commit()
    db.refresh(doc)

    # Recompute count for the response
    uploaded_count = len(all_uploaded_types & REQUIRED_DOC_TYPES)

    return ok(
        data={
            "uploaded":            1,
            "docs_uploaded_count": uploaded_count,
            "all_docs_uploaded":   uploaded_count >= len(REQUIRED_DOC_TYPES),
            "document": {
                "id":                doc.id,
                "doc_type":          doc.doc_type,
                "original_filename": doc.original_filename,
                "file_url":          doc.file_url,
                "status":            doc.status,
                "uploaded_at":       doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            },
        },
        message=f"{document_type} uploaded successfully",
    )


# ── Document List ────────────────────────────────────────────────────────────

@router.get("/candidate/documents/{candidate_id}")
def list_candidate_documents(candidate_id: int, db: Session = Depends(get_db)):
    """
    Return all documents uploaded by a candidate, newest first.
    Only returns UPLOADED and VERIFIED records (not REJECTED).
    """
    get_candidate_or_404(candidate_id, db)
    docs = (
        db.query(CandidateDocument)
        .filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.status.in_([
                DocumentStatus.UPLOADED.value,
                DocumentStatus.VERIFIED.value,
            ]),
        )
        .order_by(CandidateDocument.uploaded_at.desc())
        .all()
    )
    return ok(
        data=[
            {
                "id":                d.id,
                "doc_type":          d.doc_type,
                "original_filename": d.original_filename,
                "file_url":          d.file_url,
                "file_size_kb":      d.file_size_kb,
                "status":            d.status,
                "uploaded_at":       d.uploaded_at.isoformat() if d.uploaded_at else None,
                "remarks":           d.remarks,
            }
            for d in docs
        ],
        message=f"{len(docs)} document(s) found",
    )


# ── Candidate explicit Submit ────────────────────────────────────────────────

@router.post("/candidate/submit/{candidate_id}")
def candidate_submit_documents(
    candidate_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Candidate (or HR on their behalf) finalizes the document upload step.

    Pre-conditions:
      • All mandatory document types uploaded (UPLOADED or VERIFIED).
      • Candidate not yet past the documents stage.

    Effect:
      • Advances candidate.status to DOCS_SUBMITTED. Idempotent: if the
        candidate is already DOCS_SUBMITTED, this returns the current state
        without raising.
    """
    _ensure_candidate_self_or_hr(user, candidate_id)
    candidate = get_candidate_or_404(candidate_id, db)

    # Block if BGV has already started or beyond.
    _post_submit_statuses = {
        CandidateStatus.BGV_IN_PROGRESS.value,
        CandidateStatus.BGV_CLEAR.value,
        CandidateStatus.BGV_FAILED.value,
        CandidateStatus.BGV_ON_HOLD.value,
        CandidateStatus.CONVERTED.value,
        CandidateStatus.JOINED.value,
    }
    if candidate.status in _post_submit_statuses:
        return error(
            f"Documents have already been submitted and processed "
            f"(current status: {candidate.status}).",
            status_code=409,
        )

    # Block if offer was rejected or never accepted.
    _ineligible_statuses = {
        CandidateStatus.CREATED.value,
        CandidateStatus.OFFER_GENERATED.value,
        CandidateStatus.OFFER_SENT.value,
        CandidateStatus.OFFER_REJECTED.value,
    }
    if candidate.status in _ineligible_statuses:
        return error(
            "You can only submit documents after the offer has been accepted.",
            status_code=409,
        )

    # Verify all required docs are present.
    uploaded_types = {
        d.doc_type
        for d in candidate.documents
        if d.status in (DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value)
    }
    missing = sorted(REQUIRED_DOC_TYPES - uploaded_types)
    if missing:
        return error(
            "Cannot submit yet. Missing required document(s): "
            + ", ".join(missing),
            status_code=409,
            data={"missing": missing},
        )

    # Idempotent: if already submitted, just return the current state.
    if candidate.status == CandidateStatus.DOCS_SUBMITTED.value:
        return ok(
            data={
                "candidate_id": candidate.id,
                "status":       candidate.status,
                "submitted":    True,
                "already_submitted": True,
            },
            message="Documents were already submitted.",
        )

    candidate.status = CandidateStatus.DOCS_SUBMITTED.value
    db.commit()
    db.refresh(candidate)

    logger.info(
        "Candidate %s submitted documents (status -> DOCS_SUBMITTED)",
        candidate_id,
    )

    return ok(
        data={
            "candidate_id": candidate.id,
            "status":       candidate.status,
            "submitted":    True,
            "already_submitted": False,
        },
        message="Documents submitted successfully. HR will review and start verification.",
    )


# ── Document Delete ──────────────────────────────────────────────────────────

_DOC_TYPE_LABELS: dict[str, str] = {
    "bgv_form":      "Updated BGV Form",
    "aadhar":        "Aadhaar Card",
    "pan":           "PAN Card",
    "qualification": "Highest Qualification",
    "exp1":          "Experience Letter 1",
    "exp2":          "Experience Letter 2",
    "exp3":          "Experience Letter 3",
    "address_proof": "Address Proof",
    "cif":           "CIF Document",
    "bank":   "Bank Account Proof",
}

_REVERT_ON_DELETE = {
    CandidateStatus.DOCS_SUBMITTED.value,
    CandidateStatus.DOCS_PENDING.value,
    CandidateStatus.BGV_IN_PROGRESS.value,
    CandidateStatus.BGV_CLEAR.value,
    CandidateStatus.BGV_FAILED.value,
}


@router.delete("/documents/{candidate_id}/{document_type}")
def delete_candidate_document(
    candidate_id: int,
    document_type: str,
    db: Session = Depends(get_db),
):
    """
    Delete a candidate's uploaded document (UPLOADED status only).

    Rules:
      • Only removes UPLOADED records — VERIFIED documents require admin action.
      • Deletes the file from disk if it exists.
      • If all 6 docs are no longer present and candidate is DOCS_SUBMITTED,
        reverts candidate status to DOCS_PENDING.
    """
    if document_type not in REQUIRED_DOC_TYPES:
        return error(
            f"Invalid document_type '{document_type}'. "
            f"Accepted types: {', '.join(sorted(REQUIRED_DOC_TYPES))}",
            status_code=400,
        )

    candidate = get_candidate_or_404(candidate_id, db)

    docs_to_delete = (
        db.query(CandidateDocument)
        .filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.doc_type == document_type,
            CandidateDocument.status == DocumentStatus.UPLOADED.value,
        )
        .all()
    )

    if not docs_to_delete:
        raise HTTPException(
            status_code=404,
            detail=f"No uploaded document of type '{document_type}' found for this candidate.",
        )

    # Delete each matching file from disk
    for doc in docs_to_delete:
        if doc.file_url:
            filename = Path(doc.file_url).name
            file_path = Path(UPLOAD_DIR) / "documents" / str(candidate_id) / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info("Deleted document file: %s", file_path)
                except Exception as exc:
                    logger.warning("Could not delete file %s: %s", file_path, exc)
        db.delete(doc)

    db.flush()

    # Recompute how many required docs remain
    remaining_types = {
        d.doc_type
        for d in db.query(CandidateDocument)
        .filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.status.in_(
                [DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value]
            ),
        )
        .all()
    }
    docs_count = len(remaining_types & REQUIRED_DOC_TYPES)
    all_uploaded = docs_count >= len(REQUIRED_DOC_TYPES)

    # ── Reset BGV record unconditionally (any status) ────────────────────────
    # Deleting a required document invalidates any in-flight or completed BGV.
    # The candidate must re-upload all docs and re-initiate to trigger a fresh
    # vendor email.
    bgv_record = db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first()
    if bgv_record:
        db.delete(bgv_record)
        logger.info("BGV record reset for candidate %s due to document deletion", candidate_id)

    # ── Revert candidate status ───────────────────────────────────────────────
    if candidate.status in _REVERT_ON_DELETE:
        candidate.status = (
            CandidateStatus.DOCS_SUBMITTED.value if all_uploaded
            else CandidateStatus.DOCS_PENDING.value
        )

    db.commit()

    label = _DOC_TYPE_LABELS.get(document_type, document_type)
    logger.info("Candidate %s deleted document '%s'", candidate_id, document_type)

    return ok(
        data={
            "document_type":       document_type,
            "document_label":      label,
            "docs_uploaded_count": docs_count,
            "all_docs_uploaded":   all_uploaded,
            "bgv_status":          None,
        },
        message="Document deleted successfully",
    )


# ── BGV Status ───────────────────────────────────────────────────────────────

@router.get("/bgv/{candidate_id}")
def get_bgv_status(candidate_id: int, db: Session = Depends(get_db)):
    """
    Return the current BGV status for a candidate.

    Response shape:
      initiated   = false  →  no BGV record yet ("Not Initiated")
      initiated   = true   →  BGV record exists; status is PENDING / IN_PROGRESS / CLEAR / FAILED / REVIEW
    """
    get_candidate_or_404(candidate_id, db)

    bgv = (
        db.query(BGVCheck)
        .filter(BGVCheck.candidate_id == candidate_id)
        .first()
    )

    if bgv is None:
        return ok(
            data={
                "initiated":    False,
                "status":       None,
                "initiated_at": None,
                "completed_at": None,
                "remarks":      None,
            },
            message="BGV not initiated",
        )

    return ok(
        data={
            "initiated":    True,
            "status":       bgv.status,
            "initiated_at": bgv.initiated_at.isoformat() if bgv.initiated_at else None,
            "completed_at": bgv.completed_at.isoformat() if bgv.completed_at else None,
            "remarks":      bgv.remarks,
        },
        message="BGV status retrieved",
    )


# ── BGV Initiation ────────────────────────────────────────────────────────────

def _send_bgv_vendor_link_safe(candidate, vendor_link: str, expires_at: datetime) -> None:
    """
    Send the secure BGV vendor review link email.
    Best-effort — logs errors but never raises so the API response is unaffected.
    Uses send_bgv_vendor_link_email (link-based, no attachments) instead of the
    old send_bgv_email (attachment-based, no link).
    """
    logger.info(
        "[BGV EMAIL] Sending vendor link to %s for candidate %s | link=%s | expires=%s",
        os.getenv("BGV_VENDOR_EMAIL", "(not set)"),
        candidate.id,
        vendor_link,
        expires_at.isoformat(),
    )
    try:
        from utils.email_service import send_bgv_vendor_link_email
        send_bgv_vendor_link_email(candidate, vendor_link, expires_at)
        logger.info(
            "[BGV EMAIL] ✅ Vendor link email dispatched for candidate %s (%s)",
            candidate.id, candidate.candidate_ref,
        )
    except Exception as exc:
        # Log the full error — do NOT silently swallow it
        logger.error(
            "[BGV EMAIL] ❌ Vendor link email FAILED for candidate %s: %s. "
            "Check EMAIL_SIMULATE, BGV_VENDOR_EMAIL, SMTP credentials in .env.",
            candidate.id, exc,
        )


class BGVInitiateRequest(BaseModel):
    candidate_id: int


@router.post("/bgv/initiate")
def initiate_bgv(
    payload: BGVInitiateRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(requires_role("admin", "hr")),
):
    """
    Candidate self-initiates their background verification.

    Pre-conditions:
      • All 6 required documents must be uploaded.
      • No existing BGV record for this candidate.

    Creates a BGVCheck with status=PENDING and updates candidate status to BGV_IN_PROGRESS.
    HR will later advance the BGV to IN_PROGRESS / CLEAR / FAILED.
    """
    candidate = get_candidate_or_404(payload.candidate_id, db)

    # NEW workflow: HR must mark each required document VERIFIED before BGV
    # can be initiated. The shared helper raises 409 with the list of doc
    # types still pending verification.
    from api.Onboarding_Model.services.bgv_service import assert_documents_verified
    assert_documents_verified(candidate, db)

    existing = (
        db.query(BGVCheck)
        .filter(BGVCheck.candidate_id == payload.candidate_id)
        .first()
    )
    if existing:
        # BGV already exists — regenerate token and resend vendor link
        logger.info(
            "[BGV INITIATE] BGV already exists for candidate %s (status=%s). "
            "Regenerating vendor link.",
            payload.candidate_id, existing.status,
        )
        existing.status       = BGVStatus.IN_PROGRESS.value
        existing.initiated_at = existing.initiated_at or now_utc()
        candidate.status      = CandidateStatus.BGV_IN_PROGRESS.value

        # Revoke any previous unused tokens and issue a fresh one
        for old in db.query(BGVToken).filter(
            BGVToken.candidate_id == payload.candidate_id,
            BGVToken.used.is_(False),
        ).all():
            db.delete(old)

        raw_token = secrets.token_hex(32)
        expires   = now_utc() + timedelta(hours=_TOKEN_TTL_HOURS)
        db.add(BGVToken(
            candidate_id=payload.candidate_id,
            token=raw_token,
            expires_at=expires,
            used=False,
        ))
        db.commit()
        db.refresh(existing)

        vendor_link = f"{_FRONTEND_BASE}/vendor/bgv-review/{raw_token}"
        logger.info("[BGV INITIATE] New vendor link: %s", vendor_link)
        _send_bgv_vendor_link_safe(candidate, vendor_link, expires)

        try:
            from api.Onboarding_Model.services.bgv_service import write_bgv_audit
            write_bgv_audit(
                db, actor.employee_id, "bgv.reinitiate",
                candidate_id=payload.candidate_id,
                new_value=f"token_issued={raw_token[:8]}...",
            )
            db.commit()
        except Exception as exc:
            logger.warning("BGV audit write failed: %s", exc)

        return ok(
            data={
                "id":           existing.id,
                "candidate_id": existing.candidate_id,
                "status":       existing.status,
                "initiated_at": existing.initiated_at.isoformat() if existing.initiated_at else None,
                "vendor_link":  vendor_link,
                "expires_at":   expires.isoformat(),
            },
            message="BGV re-initiated. New vendor link email sent.",
        )

    # Status gate — any status before BGV_IN_PROGRESS is eligible
    # Block BGV initiation for statuses that haven't even accepted the offer yet,
    # AND for statuses where BGV has already been completed/converted.
    _ineligible = {
        # Too early — offer not accepted yet
        CandidateStatus.CREATED.value,
        CandidateStatus.OFFER_GENERATED.value,
        CandidateStatus.OFFER_SENT.value,
        CandidateStatus.OFFER_REJECTED.value,
        # Already completed
        CandidateStatus.BGV_CLEAR.value,
        CandidateStatus.BGV_FAILED.value,
        CandidateStatus.BGV_ON_HOLD.value,
        CandidateStatus.CONVERTED.value,
        CandidateStatus.JOINED.value,
    }
    if candidate.status in _ineligible:
        return error(
            f"BGV has already been processed for this candidate "
            f"(current status: {candidate.status}).",
            status_code=400,
        )

    logger.info("[BGV INITIATE] Creating BGVCheck for candidate %s", payload.candidate_id)

    bgv = BGVCheck(
        candidate_id=payload.candidate_id,
        status=BGVStatus.IN_PROGRESS.value,
        initiated_at=now_utc(),
    )
    db.add(bgv)
    candidate.status = CandidateStatus.BGV_IN_PROGRESS.value

    # ── Generate secure vendor token ──────────────────────────────────────────
    # 32-byte cryptographically random hex string (64 chars), expiring in TTL hours.
    raw_token = secrets.token_hex(32)
    expires   = now_utc() + timedelta(hours=_TOKEN_TTL_HOURS)

    # Remove any previous (unused) token for this candidate before creating a new one
    old_tokens = db.query(BGVToken).filter(
        BGVToken.candidate_id == payload.candidate_id,
        BGVToken.used.is_(False),
    ).all()
    for old in old_tokens:
        db.delete(old)

    token_rec = BGVToken(
        candidate_id=payload.candidate_id,
        token=raw_token,
        expires_at=expires,
        used=False,
    )
    db.add(token_rec)

    # ── Commit BEFORE sending email — DB is the source of truth ──────────────
    db.commit()
    db.refresh(bgv)

    logger.info(
        "[BGV INITIATE] ✅ BGVCheck + BGVToken committed | "
        "candidate=%s | status=%s | token=%s... | expires=%s",
        payload.candidate_id, bgv.status, raw_token[:8], expires.isoformat(),
    )

    # ── Build vendor link and send email (best-effort) ────────────────────────
    vendor_link = f"{_FRONTEND_BASE}/vendor/bgv-review/{raw_token}"
    logger.info("[BGV INITIATE] Vendor link: %s", vendor_link)

    _send_bgv_vendor_link_safe(candidate, vendor_link, expires)

    # ── Audit log: who, when, target ──────────────────────────────────────
    try:
        from api.Onboarding_Model.services.bgv_service import write_bgv_audit
        write_bgv_audit(
            db, actor.employee_id, "bgv.initiate",
            candidate_id=payload.candidate_id,
            new_value=f"token_issued={raw_token[:8]}...",
        )
        db.commit()
    except Exception as exc:
        logger.warning("BGV audit write failed: %s", exc)

    return created(
        data={
            "id":           bgv.id,
            "candidate_id": bgv.candidate_id,
            "status":       bgv.status,
            "initiated_at": bgv.initiated_at.isoformat() if bgv.initiated_at else None,
            "vendor_link":  vendor_link,        # returned for debugging/admin display
            "expires_at":   expires.isoformat(),
        },
        message="BGV initiated. Vendor link email sent.",
    )


# ── Admin: Update BGV Status ──────────────────────────────────────────────────

_UPDATABLE_BGV_STATUSES = {
    BGVStatus.IN_PROGRESS.value,
    BGVStatus.REVIEW.value,
    BGVStatus.CLEAR.value,
    BGVStatus.FAILED.value,
    BGVStatus.ON_HOLD.value,
}

_BGV_TO_CANDIDATE_STATUS = {
    BGVStatus.IN_PROGRESS.value: CandidateStatus.BGV_IN_PROGRESS.value,
    BGVStatus.REVIEW.value:      CandidateStatus.BGV_IN_PROGRESS.value,
    BGVStatus.CLEAR.value:       CandidateStatus.BGV_CLEAR.value,
    BGVStatus.FAILED.value:      CandidateStatus.BGV_FAILED.value,
    BGVStatus.ON_HOLD.value:     CandidateStatus.BGV_ON_HOLD.value,
}


class BGVAdminUpdateRequest(BaseModel):
    status: str
    remarks: Optional[str] = None


@router.patch("/bgv/{candidate_id}")
def admin_update_bgv_status(
    candidate_id: int,
    payload: BGVAdminUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Admin updates BGV status for a candidate.

    Allowed statuses: IN_PROGRESS, REVIEW, CLEAR, FAILED
    Special value  : NOT_STARTED — deletes the BGV record (reset)

    Also updates candidate.status to mirror the BGV result.
    """
    from api.models import DocumentStatus as DS  # local import to avoid name clash

    candidate = get_candidate_or_404(candidate_id, db)

    # ── Reset path: delete BGV record ────────────────────────────────────────
    if payload.status == "NOT_STARTED":
        bgv = db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first()
        if bgv:
            db.delete(bgv)
        # Revert candidate status based on docs state
        uploaded_types = {
            d.doc_type for d in candidate.documents
            if d.status in (DS.UPLOADED.value, DS.VERIFIED.value)
        }
        if uploaded_types >= REQUIRED_DOC_TYPES:
            candidate.status = CandidateStatus.DOCS_SUBMITTED.value
        else:
            candidate.status = CandidateStatus.OFFER_ACCEPTED.value
        db.commit()
        logger.info("Admin reset BGV for candidate %s -> NOT_STARTED", candidate_id)
        # Must return here — otherwise we fall through to the validation
        # below, which rejects "NOT_STARTED" and discards the reset.
        return ok(
            data={
                "candidate_id":   candidate_id,
                "bgv_status":     None,
                "candidate_status": candidate.status,
            },
            message="BGV reset to NOT_STARTED",
        )

    # ── Validate and update BGV record ───────────────────────────────────────
    if payload.status not in _UPDATABLE_BGV_STATUSES:
        from utils.response import error as _error
        return _error(
            f"Invalid status '{payload.status}'. "
            f"Allowed: {', '.join(sorted(v for v in _UPDATABLE_BGV_STATUSES))} or NOT_STARTED",
            status_code=400,
        )

    bgv = db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first()

    # Guard: terminal statuses (CLEAR/FAILED/ON_HOLD) must NOT be set from scratch.
    # BGV must have been formally initiated first. This is the root cause that allowed
    # a new candidate to show "BGV Cleared" without any actual verification.
    _TERMINAL = {BGVStatus.CLEAR.value, BGVStatus.FAILED.value, BGVStatus.ON_HOLD.value}
    if bgv is None and payload.status in _TERMINAL:
        from utils.response import error as _error
        return _error(
            f"Cannot mark BGV as \'{payload.status}\' before BGV is initiated. "
            "Use IN_PROGRESS to start, then update to a terminal status.",
            status_code=400,
        )

    if bgv is None:
        bgv = BGVCheck(
            candidate_id=candidate_id,
            status=payload.status,
            initiated_at=now_utc(),
            remarks=payload.remarks,
        )
        db.add(bgv)
    else:
        bgv.status  = payload.status
        bgv.remarks = payload.remarks
        if payload.status in _TERMINAL:
            bgv.completed_at = bgv.completed_at or now_utc()

    # Mirror BGV result to candidate status
    new_cand_status = _BGV_TO_CANDIDATE_STATUS.get(payload.status)
    if new_cand_status:
        candidate.status = new_cand_status

    db.commit()
    db.refresh(bgv)

    logger.info("Admin updated BGV for candidate %s -> %s", candidate_id, payload.status)

    return ok(
        data={
            "id":            bgv.id,
            "candidate_id":  bgv.candidate_id,
            "status":        bgv.status,
            "initiated_at":  bgv.initiated_at.isoformat() if bgv.initiated_at else None,
            "completed_at":  bgv.completed_at.isoformat() if bgv.completed_at else None,
            "remarks":       bgv.remarks,
        },
        message=f"BGV status updated to '{payload.status}'",
    )