"""
services/employee_service.py -- Candidate -> Employee conversion and lifecycle.
"""

import bcrypt as _bcrypt
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import (
    Candidate,
    CandidateStatus,
    OnboardedEmployee,
    OnboardedEmployeeStatus,
    User,
    UserRole,
)
from api.Onboarding_Model.schemas import (
    AssignManagerRequest,
    ConvertToEmployeeRequest,
)
from api.Onboarding_Model.services.candidate_service import get_candidate_or_404
from utils.id_generator import generate_employee_code
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)

EMAIL_SIMULATE = os.getenv("EMAIL_SIMULATE", "true").lower() == "true"
# Resolved via the central helper. Literal fallback "employee123" preserved.
from app.core.defaults import default_employee_password as _default_employee_password
DEFAULT_EMPLOYEE_PASSWORD = _default_employee_password()


def _hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt. Returns a UTF-8 string."""
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# Statuses from which a candidate CAN be converted (HR override for BGV_FAILED)
CONVERTIBLE_STATUSES = {
    CandidateStatus.OFFER_ACCEPTED.value,
    CandidateStatus.DOCS_PENDING.value,
    CandidateStatus.DOCS_SUBMITTED.value,
    CandidateStatus.BGV_IN_PROGRESS.value,
    CandidateStatus.BGV_CLEAR.value,
    CandidateStatus.BGV_FAILED.value,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_onboarded_employee_or_404(employee_id: int, db: Session) -> OnboardedEmployee:
    emp = db.query(OnboardedEmployee).filter(OnboardedEmployee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Onboarded employee {employee_id} not found.")
    return emp


def _send_credentials_email(candidate: Candidate, emp_code: str, password: str) -> None:
    """Send login credentials to the new employee. Always safe to call — never raises."""
    subject = "Your WorkHive account credentials"
    body = (
        f"Dear {candidate.name},\n\n"
        f"Congratulations! Your WorkHive employee account has been created.\n\n"
        f"Employee Code : {emp_code}\n"
        f"Login Email   : {candidate.email}\n"
        f"Password      : {password}\n\n"
        "Please log in and change your password immediately.\n\n"
        "Regards,\nHR Team -- WorkHive"
    )

    if EMAIL_SIMULATE:
        logger.info("[EMAIL SIMULATED] To=%s EMP=%s PWD=%s", candidate.email, emp_code, password)
        return

    try:
        msg = MIMEMultipart()
        msg["From"]    = os.getenv("EMAIL_USER", os.getenv("SMTP_USER", "noreply@workhive.com"))
        msg["To"]      = candidate.email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(
            os.getenv("EMAIL_HOST", os.getenv("SMTP_HOST", "smtp.gmail.com")),
            int(os.getenv("EMAIL_PORT", os.getenv("SMTP_PORT", "587"))),
        ) as server:
            server.starttls()
            user = os.getenv("EMAIL_USER", os.getenv("SMTP_USER", ""))
            pwd  = os.getenv("EMAIL_PASS", os.getenv("SMTP_PASSWORD", ""))
            server.login(user, pwd)
            server.send_message(msg)
        logger.info("Credentials email sent to %s", candidate.email)
    except Exception as exc:
        logger.error("Credentials email failed for %s (login still works): %s", candidate.email, exc)


def _upsert_user(candidate: Candidate, pwd_hash: str, db: Session) -> None:
    """
    Create or update the User row for a newly converted employee.
    Email is always stored lowercase so login (which normalises to lowercase)
    always finds the record regardless of how the candidate email was entered.
    """
    email_lower = candidate.email.strip().lower()   # normalise — KR@gmail.com -> kr@gmail.com

    # Check both the normalised address AND the original in case a row already
    # exists from a previous partial migration with mixed-case email.
    from sqlalchemy import func as _func
    existing = db.query(User).filter(
        _func.lower(User.email) == email_lower
    ).first()

    if existing:
        existing.email         = email_lower        # normalise stored email too
        existing.password_hash = pwd_hash
        existing.role          = UserRole.EMPLOYEE.value
        existing.is_active     = True
        existing.candidate_id  = candidate.id
        logger.info("User updated (promoted) for %s", email_lower)
    else:
        db.add(User(
            email=email_lower,
            password_hash=pwd_hash,
            role=UserRole.EMPLOYEE.value,
            is_active=True,
            candidate_id=candidate.id,
        ))
        logger.info("User created for %s", email_lower)


# ── Service functions ─────────────────────────────────────────────────────────

def convert_to_employee(
    candidate_id: int,
    payload: ConvertToEmployeeRequest,
    db: Session,
) -> OnboardedEmployee:
    """
    Convert an offer-accepted candidate to an onboarded employee.
    Commit order:
      1. OnboardedEmployee + User + candidate status  (critical — committed first)
      2. credentials_sent_at metadata                 (best-effort second commit)
    Email is sent AFTER the first commit so a network failure can never
    roll back the employee or user records.
    """
    candidate = get_candidate_or_404(candidate_id, db)

    if candidate.status not in CONVERTIBLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Candidate status is '{candidate.status}'. "
                f"Conversion requires one of: {sorted(CONVERTIBLE_STATUSES)}"
            ),
        )

    existing = db.query(OnboardedEmployee).filter(
        OnboardedEmployee.candidate_id == candidate_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Candidate {candidate_id} already converted (code: {existing.employee_code}).",
        )

    emp_code = generate_employee_code(db, OnboardedEmployee)
    pwd_hash = _hash_password(DEFAULT_EMPLOYEE_PASSWORD)

    # ── Step 1: stage OnboardedEmployee ──────────────────────────────────────
    emp = OnboardedEmployee(
        candidate_id=candidate_id,
        employee_code=emp_code,
        manager_id=payload.manager_id,
        manager_name=payload.manager_name,
        joining_date=payload.joining_date or candidate.expected_joining_date,
        status=OnboardedEmployeeStatus.INACTIVE.value,
        temp_password_hash=pwd_hash,
    )
    db.add(emp)

    # ── Step 2: stage User row (portal login) ────────────────────────────────
    _upsert_user(candidate, pwd_hash, db)

    # ── Step 3: advance candidate status ─────────────────────────────────────
    candidate.status = CandidateStatus.CONVERTED.value

    # ── Step 4: COMMIT everything critical BEFORE touching the network ────────
    db.commit()
    db.refresh(emp)
    logger.info(
        "Candidate %s -> employee %s | User record saved | password=employee123",
        candidate_id, emp_code,
    )

    # ── Step 5: send email (best-effort, after commit) ────────────────────────
    _send_credentials_email(candidate, emp_code, DEFAULT_EMPLOYEE_PASSWORD)

    # ── Step 6: record email-sent timestamp (best-effort second commit) ───────
    try:
        emp.credentials_sent_at   = now_utc()
        candidate.credentials_sent = True
        db.commit()
    except Exception as exc:
        logger.warning("Could not save credentials_sent_at: %s", exc)
        db.rollback()

    return emp


def assign_manager(employee_id: int, payload: AssignManagerRequest, db: Session) -> OnboardedEmployee:
    emp = get_onboarded_employee_or_404(employee_id, db)
    emp.manager_id   = payload.manager_id
    emp.manager_name = payload.manager_name
    db.commit()
    db.refresh(emp)
    logger.info("Manager '%s' assigned to employee %s", payload.manager_name, employee_id)
    return emp


def activate_employee(employee_id: int, db: Session) -> OnboardedEmployee:
    emp = get_onboarded_employee_or_404(employee_id, db)
    if emp.status == OnboardedEmployeeStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Employee is already active.")
    emp.status       = OnboardedEmployeeStatus.ACTIVE.value
    emp.activated_at = now_utc()
    db.commit()
    db.refresh(emp)
    logger.info("Employee %s activated", employee_id)
    return emp


def mark_joined(employee_id: int, db: Session) -> tuple:
    emp = get_onboarded_employee_or_404(employee_id, db)
    if emp.status != OnboardedEmployeeStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Employee must be activated before marking as joined.")
    candidate = get_candidate_or_404(emp.candidate_id, db)
    candidate.status = CandidateStatus.JOINED.value
    db.commit()
    db.refresh(emp)
    db.refresh(candidate)
    logger.info("Employee %s marked JOINED", employee_id)
    return emp, candidate


def mark_not_joined(employee_id: int, db: Session) -> tuple:
    emp = get_onboarded_employee_or_404(employee_id, db)
    candidate = get_candidate_or_404(emp.candidate_id, db)
    candidate.status = CandidateStatus.NOT_JOINED.value
    emp.status       = OnboardedEmployeeStatus.INACTIVE.value
    db.commit()
    db.refresh(emp)
    db.refresh(candidate)
    logger.info("Employee %s marked NOT JOINED", employee_id)
    return emp, candidate


def get_onboarded_employee_by_candidate(candidate_id: int, db: Session) -> Optional[OnboardedEmployee]:
    return db.query(OnboardedEmployee).filter(
        OnboardedEmployee.candidate_id == candidate_id
    ).first()
