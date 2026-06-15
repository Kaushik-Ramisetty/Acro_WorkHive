"""
api/Onboarding_Model/bgv_vendor.py
Token-based BGV vendor portal endpoints.

Routes (prefix /api/v1/bgv):
  POST /api/v1/bgv/initiate/{candidate_id}   Admin triggers BGV, generates token, sends vendor email
  GET  /api/v1/bgv/vendor/{token}            Vendor loads review portal (validates token)
  POST /api/v1/bgv/vendor/{token}/submit     Vendor submits result (consumes token)

Security:
  - Token is a 32-byte cryptographically random hex string (64 chars)
  - Expires in TOKEN_TTL_HOURS (default 48h)
  - One-time-use: marked used=True on submit
  - Duplicate BGV prevention: checks for existing BGVCheck before creating
"""

import logging
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, created, error
from utils.time_utils import now_utc
from api.models import (
    BGVCheck, BGVStatus, BGVToken,
    Candidate, CandidateStatus, CandidateDocument, DocumentStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bgv", tags=["BGV — Vendor Portal"])

TOKEN_TTL_HOURS   = int(os.getenv("BGV_TOKEN_TTL_HOURS", "336"))  # default 2 weeks
REQUIRED_DOC_TYPES = {"aadhar", "pan", "degree", "exp", "photo", "bank"}
FRONTEND_BASE      = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")


# ── Schemas ───────────────────────────────────────────────────────────────────

class BGVInitiateRequest(BaseModel):
    vendor_name: str | None = None


class BGVSubmitRequest(BaseModel):
    status:  str          # "CLEAR" | "HOLD" | "FAILED"
    remarks: str          # MANDATORY for all decisions


# ── Helper: resolve token or 4xx ─────────────────────────────────────────────

def _resolve_token(token: str, db: Session) -> BGVToken:
    """Validate the token, returning the BGVToken ORM object on success."""
    record = db.query(BGVToken).filter(BGVToken.token == token).first()
    if not record:
        raise HTTPException(status_code=404, detail="Invalid or expired review link.")
    if record.expires_at < now_utc():
        raise HTTPException(status_code=410, detail="This review link has expired. Contact HR to resend.")
    if record.used:
        raise HTTPException(status_code=409, detail="This link has already been used and cannot be reused.")
    return record


# ── POST /api/v1/bgv/initiate/{candidate_id} ─────────────────────────────────

@router.post("/initiate/{candidate_id}")
def initiate_bgv(
    candidate_id: int,
    payload: BGVInitiateRequest = BGVInitiateRequest(),
    db: Session = Depends(get_db),
):
    """
    Admin triggers BGV for a candidate.

    Prerequisites:
      - Candidate must have at least OFFER_ACCEPTED status
      - At least one required document must be uploaded
      - BGV must not already be initiated

    Actions:
      1. Create BGVCheck record (status = IN_PROGRESS)
      2. Generate a secure, expiring, one-time token
      3. Send vendor link email (best-effort)
      4. Advance candidate status to BGV_IN_PROGRESS
    """
    # 1. Fetch candidate
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")

    early_statuses = {
        CandidateStatus.CREATED.value,
        CandidateStatus.OFFER_GENERATED.value,
        CandidateStatus.OFFER_SENT.value,
        CandidateStatus.OFFER_REJECTED.value,
    }
    if candidate.status in early_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"BGV requires OFFER_ACCEPTED or later status. Current: {candidate.status}",
        )

    # 2. Check docs
    uploaded_types = {
        d.doc_type for d in db.query(CandidateDocument).filter(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.status.in_([DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value]),
        ).all()
    }
    if not uploaded_types & REQUIRED_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="At least one required document must be uploaded before starting BGV.",
        )

    # ── New gate: every required document must be VERIFIED by HR ─────────────
    # Per the new BGV workflow, BGV cannot start until HR explicitly verifies
    # each required document via PATCH /documents/{id}/verify.
    from api.Onboarding_Model.services.bgv_service import assert_documents_verified
    assert_documents_verified(candidate, db)

    # 3. Prevent duplicate BGV
    existing_bgv = db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first()
    if existing_bgv:
        raise HTTPException(
            status_code=409,
            detail=f"BGV already initiated (status: {existing_bgv.status}). Cannot start again.",
        )

    # 4. Create BGVCheck
    bgv = BGVCheck(
        candidate_id=candidate_id,
        status=BGVStatus.IN_PROGRESS.value,
        vendor_name=payload.vendor_name,
        initiated_at=now_utc(),
    )
    db.add(bgv)

    # 5. Generate secure token
    raw_token = secrets.token_hex(32)          # 64-char hex string
    expires   = now_utc() + timedelta(hours=TOKEN_TTL_HOURS)
    token_rec = BGVToken(
        candidate_id=candidate_id,
        token=raw_token,
        expires_at=expires,
        used=False,
    )
    db.add(token_rec)

    # 6. Advance candidate status
    if candidate.status in (
        CandidateStatus.OFFER_ACCEPTED.value,
        CandidateStatus.DOCS_PENDING.value,
        CandidateStatus.DOCS_SUBMITTED.value,
    ):
        candidate.status = CandidateStatus.BGV_IN_PROGRESS.value

    db.flush()          # get token_rec.id before commit
    db.commit()

    # 7. Build vendor link and send email (best-effort — never fails the request)
    vendor_link = f"{FRONTEND_BASE}/vendor/bgv-review/{raw_token}"
    try:
        from utils.email_service import send_bgv_vendor_link_email
        send_bgv_vendor_link_email(candidate, vendor_link, expires)
        logger.info("BGV vendor link email sent for candidate %s", candidate_id)
    except Exception as exc:
        logger.error("BGV vendor link email failed (BGV still initiated): %s", exc)

    logger.info(
        "BGV initiated for candidate %s | token=%s...| expires=%s",
        candidate_id, raw_token[:8], expires.isoformat(),
    )

    return created(
        data={
            "candidate_id":   candidate_id,
            "bgv_status":     bgv.status,
            "vendor_link":    vendor_link,
            "expires_at":     expires.isoformat(),
            "docs_uploaded":  sorted(uploaded_types & REQUIRED_DOC_TYPES),
        },
        message=f"BGV initiated. Vendor link sent to {os.getenv('BGV_VENDOR_EMAIL', 'vendor')}.",
    )


# ── GET /api/v1/bgv/vendor/{token} ───────────────────────────────────────────

@router.get("/vendor/{token}")
def vendor_get_review(token: str, db: Session = Depends(get_db)):
    """
    Vendor opens review portal using the secure link.
    Returns candidate info + uploaded documents.
    Token is validated (exists, not expired, not used) but NOT consumed here.
    """
    token_rec = _resolve_token(token, db)
    candidate = token_rec.candidate

    # Collect uploaded/verified documents
    docs = db.query(CandidateDocument).filter(
        CandidateDocument.candidate_id == token_rec.candidate_id,
        CandidateDocument.status.in_([DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value]),
    ).all()

    return ok(
        data={
            "candidate": {
                "id":            candidate.id,
                "name":          candidate.name,
                "candidate_ref": candidate.candidate_ref,
                "email":         candidate.email,
                "role":          candidate.role,
                "department":    candidate.department,
            },
            "documents": [
                {
                    "id":                d.id,
                    "doc_type":          d.doc_type,
                    "original_filename": d.original_filename,
                    "file_url":          d.file_url,
                    "status":            d.status,
                }
                for d in docs
            ],
            "token_expires_at": token_rec.expires_at.isoformat(),
        },
        message="BGV review data loaded",
    )


# ── POST /api/v1/bgv/vendor/{token}/submit ────────────────────────────────────

@router.post("/vendor/{token}/submit")
def vendor_submit_result(
    token: str,
    payload: BGVSubmitRequest,
    db: Session = Depends(get_db),
):
    """
    Vendor submits their BGV decision. Token is consumed (one-time-use).

    - Updates BGVCheck status to CLEAR or FAILED
    - Marks BGVToken as used
    - Updates candidate status to BGV_CLEAR or BGV_FAILED
    - Notifies admin via email (best-effort)
    """
    if payload.status not in ("CLEAR", "HOLD", "FAILED"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.status}'. Must be CLEAR, HOLD, or FAILED.",
        )
    if not payload.remarks or not payload.remarks.strip():
        raise HTTPException(
            status_code=422,
            detail="Remarks are mandatory. Please provide a remark for your decision.",
        )

    token_rec = _resolve_token(token, db)
    candidate = token_rec.candidate

    # Fetch BGVCheck — must exist
    bgv = db.query(BGVCheck).filter(BGVCheck.candidate_id == token_rec.candidate_id).first()
    if not bgv:
        raise HTTPException(status_code=404, detail="BGV record not found for this token.")

    if bgv.status in (BGVStatus.CLEAR.value, BGVStatus.FAILED.value, BGVStatus.ON_HOLD.value):
        raise HTTPException(
            status_code=409,
            detail=f"BGV already finalised with status '{bgv.status}'. Contact HR to reset.",
        )

    now = now_utc()

    # Update BGVCheck
    bgv.remarks      = payload.remarks
    bgv.completed_at = now

    # Consume token
    token_rec.used    = True
    token_rec.used_at = now

    # Mirror to candidate status
    _status_map = {
        "CLEAR":  CandidateStatus.BGV_CLEAR.value,
        "HOLD":   CandidateStatus.BGV_ON_HOLD.value,
        "FAILED": CandidateStatus.BGV_FAILED.value,
    }
    # Map vendor-submitted shortcode ("HOLD") to canonical BGVStatus enum
    # ("ON_HOLD"), so subsequent equality checks (e.g. duplicate-finalize
    # guard on line above) match what we store.
    _bgv_status_map = {
        "CLEAR":  BGVStatus.CLEAR.value,
        "HOLD":   BGVStatus.ON_HOLD.value,
        "FAILED": BGVStatus.FAILED.value,
    }
    candidate.status = _status_map[payload.status]
    bgv.status       = _bgv_status_map[payload.status]

    db.commit()

    logger.info(
        "BGV result submitted for candidate %s → %s (token=%s...)",
        token_rec.candidate_id, payload.status, token[:8],
    )

    # Notify admin (best-effort)
    try:
        from utils.email_service import send_bgv_result_admin_email
        send_bgv_result_admin_email(candidate, payload.status, payload.remarks, now)
    except Exception as exc:
        logger.error("Admin BGV result notification failed: %s", exc)

    status_labels = {"CLEAR": "BGV Cleared", "HOLD": "BGV On Hold", "FAILED": "BGV Rejected"}
    return ok(
        data={
            "bgv_status":       bgv.status,
            "remarks":          bgv.remarks,
            "completed_at":     bgv.completed_at.isoformat(),
            "candidate_status": candidate.status,
        },
        message=f"{status_labels.get(payload.status, payload.status)} recorded. Admin notified.",
    )
