"""
services/offer_service.py — Offer letter generation, email dispatch, and acceptance.

PDF generation uses ReportLab (installed via requirements.txt).
Email is simulated via logging in development; swap out for smtplib / SendGrid in production.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import Candidate, CandidateStatus
from api.Onboarding_Model.services.candidate_service import (
    get_candidate_or_404,
    assert_transition,
)
from utils.email_service import send_email
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


# ─── Offer letter (PDF) ────────────────────────────────────────────────────────

def _generate_offer_pdf(candidate: Candidate) -> str:
    """
    Generate a basic offer letter PDF and return its relative URL path.
    Falls back to a plain-text placeholder if ReportLab is not installed.
    """
    offers_dir = Path(UPLOAD_DIR) / "offers"
    offers_dir.mkdir(parents=True, exist_ok=True)

    filename = f"offer_{candidate.id}_{candidate.candidate_ref}.pdf"
    filepath = offers_dir / filename

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import cm

        doc = SimpleDocTemplate(str(filepath), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Acronotics", styles["Title"]))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("OFFER LETTER", styles["h2"]))
        story.append(Spacer(1, 0.5 * cm))

        joining = (
            candidate.expected_joining_date.strftime("%d %B %Y")
            if candidate.expected_joining_date else "As discussed"
        )
        ctc_line = f"<b>CTC (LPA in INR):</b> {candidate.ctc}<br/>" if candidate.ctc else ""

        body = f"""
        <para>
        Dear <b>{candidate.name}</b>,
        <br/><br/>
        We are pleased to offer you the position of <b>{candidate.role}</b>
        {f'in the <b>{candidate.department}</b> department' if candidate.department else ''}.
        <br/><br/>
        <b>Joining Date:</b> {joining}<br/>
        {ctc_line}
        <b>Reference No:</b> {candidate.candidate_ref}<br/>
        <br/>
        Please acknowledge your acceptance by responding to this letter within 7 days.
        <br/><br/>
        This offer is contingent upon successful completion of the background verification process.
        <br/><br/>
        We look forward to welcome you to the Acronotics team.
        <br/><br/>
        Regards,<br/>
        <b>Human Resources Team</b><br/>
        Acronotics
        </para>
        """
        story.append(Paragraph(body, styles["Normal"]))
        doc.build(story)
        logger.info("PDF offer letter generated: %s", filename)

    except ImportError:
        # ReportLab not available — write a text placeholder
        # Update filename/filepath BEFORE writing so the URL matches the file on disk
        filename = filename.replace(".pdf", ".txt")
        filepath = offers_dir / filename
        ctc_txt = f"\nCTC (Annual): {candidate.ctc}" if candidate.ctc else ""
        filepath.write_text(
            f"OFFER LETTER\n\nDear {candidate.name},\n\n"
            f"Role: {candidate.role}\nRef: {candidate.candidate_ref}{ctc_txt}\n\n"
            "Regards,\nHR Team"
        )
        logger.warning("ReportLab not installed — plain-text offer written: %s", filename)

    return f"/uploads/offers/{filename}"


# ─── Default email content builders ──────────────────────────────────────────

def _default_subject(candidate: Candidate) -> str:
    return f"Offer Letter - {candidate.name} | {candidate.role} at Acronotics"


def _default_body(candidate: Candidate) -> str:
    joining = (
        candidate.expected_joining_date.strftime("%d %B %Y")
        if candidate.expected_joining_date else "as discussed"
    )
    ctc_line = f"\nCTC (LPA in INR)    : {candidate.ctc}" if getattr(candidate, "ctc", None) else ""
    return (
        f"Dear {candidate.name},\n\n"
        f"We are pleased to extend this offer of employment for the position of "
        f"{candidate.role}"
        + (f" in the {candidate.department} department" if candidate.department else "")
        + f".\n\n"
        f"Offer Details\n"
        f"─────────────────────────────\n"
        f"Role            : {candidate.role}\n"
        f"Department      : {candidate.department or 'N/A'}\n"
        f"Expected Joining: {joining}"
        f"{ctc_line}\n"
        f"Reference No.   : {candidate.candidate_ref}\n"
        f"─────────────────────────────\n\n"
        f"Please find your offer letter attached to this email.\n\n"
        f"Kindly respond within 7 days to confirm your acceptance.\n\n"
        f"This offer is contingent upon successful completion of the "
        f"background verification process.\n\n"
        f"We look forward to welcoming you to the Acronotics team!\n\n"
        f"Warm regards,\n"
        f"HR Team — Acronotics"
    )


# ─── Service functions ────────────────────────────────────────────────────────

def generate_offer(candidate_id: int, db: Session) -> Candidate:
    """Generate offer PDF and mark status OFFER_GENERATED."""
    candidate = get_candidate_or_404(candidate_id, db)
    assert_transition(candidate, CandidateStatus.OFFER_GENERATED.value)

    offer_url = _generate_offer_pdf(candidate)
    candidate.offer_letter_url = offer_url
    candidate.status = CandidateStatus.OFFER_GENERATED.value
    db.commit()
    db.refresh(candidate)
    return candidate


def send_offer(
    candidate_id: int,
    db: Session,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> Candidate:
    """
    Email the offer letter to the candidate and advance status to OFFER_SENT.

    Parameters
    ----------
    to_email    Override recipient address (defaults to candidate.email).
    subject     Override email subject (defaults to built-in template).
    body        Override email body (defaults to built-in template).
    """
    candidate = get_candidate_or_404(candidate_id, db)

    if not candidate.offer_letter_url:
        raise HTTPException(
            status_code=400,
            detail="Offer letter has not been generated yet. Call /offer/generate first.",
        )

    assert_transition(candidate, CandidateStatus.OFFER_SENT.value)

    recipient = to_email or candidate.email
    email_subject = subject or _default_subject(candidate)
    email_body = body or _default_body(candidate)

    # Resolve absolute path for the attachment
    attachment_path: Optional[str] = None
    if candidate.offer_letter_url:
        # offer_letter_url is like "/uploads/offers/offer_1_CAND-ABC.pdf"
        # UPLOAD_DIR is like "./uploads" — strip the leading "/uploads" prefix
        rel = candidate.offer_letter_url.lstrip("/")   # "uploads/offers/offer_1_..."
        attachment_path = str(Path(UPLOAD_DIR).parent / rel)

    try:
        send_email(
            to=recipient,
            subject=email_subject,
            body=email_body,
            attachment_path=attachment_path,
        )
    except RuntimeError as exc:
        logger.error("Email send failed for candidate %s: %s", candidate_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    candidate.status = CandidateStatus.OFFER_SENT.value
    candidate.offer_sent_at = now_utc()
    db.commit()
    db.refresh(candidate)
    logger.info("Offer email dispatched → %s (candidate %s)", recipient, candidate_id)
    return candidate


def regenerate_offer(candidate_id: int, db: Session) -> Candidate:
    """
    Forcibly regenerate the offer PDF regardless of current status.
    Use this to fix candidates whose offer file is missing or is a text placeholder.
    Does not change candidate status.
    """
    candidate = get_candidate_or_404(candidate_id, db)

    if not candidate.offer_letter_url and candidate.status == CandidateStatus.CREATED.value:
        raise HTTPException(
            status_code=400,
            detail="No offer has been generated for this candidate yet. Use /offer/generate first.",
        )

    old_url = candidate.offer_letter_url
    new_url = _generate_offer_pdf(candidate)
    candidate.offer_letter_url = new_url
    db.commit()
    db.refresh(candidate)
    logger.info("Offer regenerated for candidate %s: %s → %s", candidate_id, old_url, new_url)
    return candidate


def accept_offer(candidate_id: int, db: Session) -> Candidate:
    """
    Record that the candidate accepted the offer.

    Side-effects (both best-effort — never fail the acceptance itself):
      1. Create a User record so the candidate can log in to the portal
         with email = candidate.email, password = "candidate123"
      2. Send onboarding email with portal credentials + document checklist
    """
    import bcrypt as _bcrypt
    from api.models import User, UserRole
    from app.core.defaults import default_candidate_password

    candidate = get_candidate_or_404(candidate_id, db)
    assert_transition(candidate, CandidateStatus.OFFER_ACCEPTED.value)

    candidate.status          = CandidateStatus.OFFER_ACCEPTED.value
    candidate.is_offer_accepted = True
    candidate.offer_accepted_at = now_utc()

    # ── Create / update candidate portal login ────────────────────────────────
    email_lower = candidate.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email_lower).first()
    if not existing_user:
        # Resolved via the central helper. Literal fallback "candidate123"
        # preserved so the onboarding email template + tests still match.
        _candidate_pwd = default_candidate_password()
        pwd_hash = _bcrypt.hashpw(_candidate_pwd.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
        db.add(User(
            email=email_lower,
            password_hash=pwd_hash,
            role=UserRole.CANDIDATE.value,
            is_active=True,
            candidate_id=candidate.id,
        ))
        logger.info("Portal login created for candidate %s (%s)", candidate_id, email_lower)
    else:
        # Always sync candidate_id — prevents stale references if the user row
        # was created by a backfill or a previous (different) candidate flow.
        if existing_user.candidate_id != candidate.id:
            logger.info(
                "Fixing stale candidate_id on User %s: %s → %s",
                email_lower, existing_user.candidate_id, candidate.id,
            )
            existing_user.candidate_id = candidate.id
        existing_user.role      = UserRole.CANDIDATE.value
        existing_user.is_active = True
        logger.info("Portal login updated for candidate %s (%s)", candidate_id, email_lower)

    db.commit()
    db.refresh(candidate)
    logger.info("Candidate %s accepted the offer", candidate_id)

    # ── Send onboarding email (best-effort) ───────────────────────────────────
    try:
        from utils.email_service import send_candidate_onboarding_email
        send_candidate_onboarding_email(candidate)
    except Exception as exc:
        logger.error(
            "[ONBOARDING EMAIL] Failed for candidate %s: %s. "
            "Check EMAIL_SIMULATE / SMTP settings.",
            candidate_id, exc,
        )

    return candidate


def reject_offer(candidate_id: int, db: Session) -> Candidate:
    """Record that the candidate rejected the offer."""
    candidate = get_candidate_or_404(candidate_id, db)
    assert_transition(candidate, CandidateStatus.OFFER_REJECTED.value)

    candidate.status = CandidateStatus.OFFER_REJECTED.value
    db.commit()
    db.refresh(candidate)
    logger.info("Candidate %s rejected the offer", candidate_id)
    return candidate
