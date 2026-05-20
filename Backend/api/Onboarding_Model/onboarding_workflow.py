"""api/Onboarding_Model/onboarding_workflow.py — IT credential creation + activation."""
import bcrypt as _bcrypt
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, error
from api.models import Employee
from utils.time_utils import now_utc
from utils.jwt_auth import requires_role

logger = logging.getLogger(__name__)

# request-it and activate are HR-only operations.
router = APIRouter(
    prefix="/onboarding",
    tags=["Onboarding Workflow"],
    dependencies=[Depends(requires_role("admin", "hr"))],
)


def _hash(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _get_employee_or_404(employee_id: int, db: Session) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_deleted.is_(False),
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found.")
    return emp


@router.post("/request-it/{employee_id}")
def request_it_account(employee_id: int, db: Session = Depends(get_db)):
    """HR triggers IT to create an official email and temporary password."""
    emp = _get_employee_or_404(employee_id, db)
    if emp.is_activated:
        return error(
            f"Employee {emp.employee_code} is already activated with official email "
            f"{emp.official_email}. No new IT request needed.",
            status_code=409,
        )
    manager_name = manager_email = None
    if emp.reporting_manager_id:
        mgr = db.query(Employee).filter(
            Employee.id == emp.reporting_manager_id,
            Employee.is_deleted.is_(False),
        ).first()
        if mgr:
            manager_name  = f"{mgr.first_name} {mgr.last_name}".strip()
            manager_email = mgr.official_email or mgr.email
    from utils.email_service import send_it_request_email
    try:
        send_it_request_email(emp, manager_name, manager_email)
        email_sent, email_error = True, None
    except Exception as exc:
        email_sent, email_error = False, str(exc)
        logger.error("[IT EMAIL] failed for %s: %s", emp.employee_code, exc)
    it_addr = os.getenv("IT_EMAIL", "(not configured)")
    msg = (f"IT account request sent to {it_addr}." if email_sent
           else f"Email could not be sent: {email_error}.")
    return ok(data={
        "employee_id":   emp.id,
        "employee_code": emp.employee_code,
        "name":          f"{emp.first_name} {emp.last_name}".strip(),
        "is_activated":  emp.is_activated,
        "email_sent":    email_sent,
        "email_error":   email_error,
        "it_email":      it_addr,
        "manager_cc":    manager_email,
    }, message=msg)


class ActivateEmployeeRequest(BaseModel):
    official_email: str = Field(..., description="Official company email provided by IT")
    temp_password:  str = Field(..., min_length=6, description="Temporary password set by IT")


@router.put("/activate/{employee_id}")
def activate_employee(employee_id: int, payload: ActivateEmployeeRequest,
                       db: Session = Depends(get_db)):
    """HR activates the employee after receiving credentials from IT."""
    emp = _get_employee_or_404(employee_id, db)
    is_update = emp.is_activated
    official_email = payload.official_email.strip().lower()
    conflict = db.query(Employee).filter(
        Employee.official_email == official_email,
        Employee.id             != employee_id,
        Employee.is_deleted.is_(False),
    ).first()
    if conflict:
        raise HTTPException(status_code=400,
            detail=f"Official email '{official_email}' is already in use by another employee.")
    pwd_hash = _hash(payload.temp_password)
    emp.official_email         = official_email
    emp.Password               = pwd_hash
    emp.is_activated           = True
    emp.force_password_change  = True
    emp.employment_status      = "active"
    emp.updated_at             = now_utc()
    db.commit()
    db.refresh(emp)
    try:
        from utils.email_service import send_employee_welcome_email
        send_employee_welcome_email(emp, payload.temp_password)
    except Exception as exc:
        logger.error("Welcome email failed for %s: %s", emp.employee_code, exc)
    return ok(data={
        "employee_id":           emp.id,
        "employee_code":         emp.employee_code,
        "official_email":        emp.official_email,
        "is_activated":          emp.is_activated,
        "force_password_change": emp.force_password_change,
        "employment_status":     emp.employment_status,
    }, message=(f"Employee {emp.employee_code} {'credentials updated' if is_update else 'activated'}. "
                f"Welcome email sent to {official_email}."))


# ── /api/v1/auth/change-password — registered under auth prefix ───────────────
change_password_router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class ChangePasswordRequest(BaseModel):
    official_email:   str = Field(...)
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8)


@change_password_router.post("/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    """Employee changes their temporary password."""
    from sqlalchemy import func as _func
    official_email = payload.official_email.strip().lower()
    emp = db.query(Employee).filter(
        _func.lower(Employee.official_email) == official_email,
        Employee.is_deleted.is_(False),
    ).first()
    if not emp:
        return error("Invalid credentials.", status_code=401)
    if not emp.is_activated:
        return error("Account is not yet activated. Contact HR.", status_code=403)
    if not emp.Password or not _verify(payload.current_password, emp.Password):
        return error("Current password is incorrect.", status_code=401)
    if payload.new_password == payload.current_password:
        return error("New password must be different from the current password.", status_code=400)
    # Apply central password policy. Existing stored passwords are NOT
    # retroactively forced to meet the policy — this check only runs for
    # the new password the user is setting. Backwards compatible.
    try:
        from app.core.password_policy import first_error as _pwd_policy_error
        _msg = _pwd_policy_error(payload.new_password)
        if _msg:
            return error(_msg, status_code=400)
    except Exception:  # pragma: no cover — never block on policy import
        pass
    emp.Password              = _hash(payload.new_password)
    emp.force_password_change = False
    emp.updated_at            = now_utc()
    db.commit()
    return ok(data={
        "employee_id":           emp.id,
        "employee_code":         emp.employee_code,
        "force_password_change": emp.force_password_change,
    }, message="Password updated successfully.")


@router.get("/test-email")
def test_email_config(to: str = None):
    """Dev/HR diagnostic — sends a test email and returns SMTP config details."""
    from utils.email_service import send_email_with_cc
    recipient = to or os.getenv("IT_EMAIL", "")
    if not recipient:
        return error("Provide ?to=email or set IT_EMAIL in .env", status_code=400)
    cfg_info = {
        "EMAIL_HOST":     os.getenv("EMAIL_HOST", "smtp.gmail.com"),
        "EMAIL_PORT":     os.getenv("EMAIL_PORT", "587"),
        "EMAIL_USER":     os.getenv("EMAIL_USER", "(not set)"),
        "EMAIL_PASS_len": len(os.getenv("EMAIL_PASS", "").replace(" ", "")),
        "EMAIL_SIMULATE": os.getenv("EMAIL_SIMULATE", "true"),
        "IT_EMAIL":       os.getenv("IT_EMAIL", "(not set)"),
        "sending_to":     recipient,
    }
    try:
        send_email_with_cc(to=recipient, subject="Acronotics — SMTP Test",
                          body="Test email\n\nConfig:\n" + "\n".join(f"  {k}: {v}" for k, v in cfg_info.items()))
        return ok(data={**cfg_info, "status": "sent"},
                  message=f"Test email sent to {recipient}.")
    except Exception as exc:
        return ok(data={**cfg_info, "status": "failed", "error": str(exc)},
                  message=f"SMTP FAILED: {exc}")
