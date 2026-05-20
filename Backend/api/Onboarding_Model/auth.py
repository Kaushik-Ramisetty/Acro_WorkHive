"""
api/Onboarding_Model/auth.py -- Unified authentication endpoint.

Login priority:
  1. employees.Password  (new flow)
  2. users.password_hash (legacy flow)
"""

import bcrypt as _bcrypt
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import func as _func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from utils.response import ok, error
from api.models import Employee, User, OnboardedEmployee, Candidate
from utils.time_utils import now_utc
from utils.jwt_auth import create_access_token


logger = logging.getLogger(__name__)


def _stamp_employee_updated_at(employee_id: int) -> None:
    """Update employees.updated_at in a fresh session — runs in a BackgroundTask
    so it doesn't add latency to the login response. Best-effort: any error is
    swallowed because the user has already been authenticated."""
    db = SessionLocal()
    try:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if emp:
            emp.updated_at = now_utc()
            db.commit()
    except Exception as exc:
        logger.warning("BG: stamp employee updated_at failed (%s): %s", employee_id, exc)
        db.rollback()
    finally:
        db.close()


def _stamp_user_last_login(user_id: int) -> None:
    """Update users.last_login in a fresh session — runs as a BackgroundTask."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            u.last_login = now_utc()
            db.commit()
    except Exception as exc:
        logger.warning("BG: stamp user last_login failed (%s): %s", user_id, exc)
        db.rollback()
    finally:
        db.close()


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _verify(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(
    payload: LoginRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Authenticate any portal user. Issues a JWT bearer token."""
    email = (payload.email or "").strip().lower()

    # ── Path A: employees table — official_email login ──────────────────────
    employee: Employee | None = db.query(Employee).filter(
        _func.lower(Employee.official_email) == email,
        Employee.is_deleted.is_(False),
    ).first()
    if not employee:
        employee = db.query(Employee).filter(
            _func.lower(Employee.email) == email,
            Employee.is_deleted.is_(False),
        ).first()

    if employee and employee.Password and _verify(payload.password, employee.Password):
        # Block ONLY genuinely pending-activation employees. The
        # ``is_activated`` flag was added for the onboarding workflow and
        # defaults to False on every row, so a False value on its own is
        # NOT enough to lock someone out — pre-onboarding-system employees
        # (seeded from Excel, etc.) all have is_activated=False but a valid
        # password and are otherwise active. The activation gate fires
        # specifically when employment_status is "pending_activation",
        # which is the state new candidates land in after conversion.
        if employee.employment_status == "pending_activation":
            return error(
                "Your account is not yet activated. "
                "HR will send your official email and password once IT sets it up.",
                status_code=403,
            )
        if employee.is_deleted:
            return error("Your account has been deactivated. Please contact HR.", status_code=403)
        if employee.employment_status not in ("active", "on_notice"):
            return error(
                f"Login not permitted (account status: {employee.employment_status}). "
                "Please contact HR.",
                status_code=403,
            )

        # SECURITY: employees MUST go through 2FA. Previously this branch
        # issued a JWT directly, which let the frontend's fallback-to-legacy
        # path bypass the OTP step entirely. We now mint an OTP via the
        # shared 2FA pipeline and return ``requires_2fa: true`` instead of
        # an access token. The frontend recognises this shape and continues
        # to the OTP screen exactly as it does for the Core 2FA endpoint.
        #
        # Path B below (candidates from the legacy users table) is unchanged
        # — candidates still receive a direct token because they do not
        # have a 2FA flow.
        login_email = employee.official_email or employee.email
        emp_role = (employee.role.name.lower() if getattr(employee, "role", None) else "employee")
        try:
            from app.services.auth_service import issue_otp_for_user
            otp_result = issue_otp_for_user(employee)
        except ValueError as exc:
            return error(str(exc), status_code=403)
        background_tasks.add_task(_stamp_employee_updated_at, employee.id)
        logger.info("Login OK (employees, 2FA required): %s", email)
        # ``data`` keeps the same envelope shape — only the contents
        # change: no access_token until the user verifies OTP.
        return ok(
            data={
                "requires_2fa":  True,
                "user_id":       employee.id,
                "email":         login_email,
                "role":          emp_role,
                "name":          f"{employee.first_name} {employee.last_name}".strip(),
                "employeeCode":  employee.employee_code,
                "employeeId":    employee.id,
            },
            message="Verification code sent to your email.",
        )

    # ── Path B: users table (legacy) ────────────────────────────────────────
    user: User | None = db.query(User).filter(
        _func.lower(User.email) == email
    ).first()
    if user is None:
        return error("Invalid email or password.", status_code=401)
    if not user.is_active:
        return error("Account is deactivated. Please contact HR.", status_code=403)
    if not _verify(payload.password, user.password_hash):
        return error("Invalid email or password.", status_code=401)

    session: dict = {
        "email": user.email,
        "role":  user.role.lower(),
    }

    if user.role == "EMPLOYEE" and user.candidate_id:
        candidate = db.query(Candidate).filter(Candidate.id == user.candidate_id).first()
        onboarded = db.query(OnboardedEmployee).filter(OnboardedEmployee.candidate_id == user.candidate_id).first()
        session["name"]           = candidate.name        if candidate  else email
        session["candidateId"]    = user.candidate_id
        session["employeeCode"]   = onboarded.employee_code if onboarded else None
        session["employeeStatus"] = onboarded.status       if onboarded else None

    elif user.role == "CANDIDATE" and user.candidate_id:
        candidate = db.query(Candidate).filter(Candidate.id == user.candidate_id).first()
        if not candidate:
            candidate = db.query(Candidate).filter(_func.lower(Candidate.email) == email).first()
            if candidate:
                try:
                    user.candidate_id = candidate.id
                    db.commit()
                except Exception:
                    db.rollback()
        session["name"]        = candidate.name if candidate else email
        session["candidateId"] = candidate.id  if candidate else user.candidate_id

    else:
        session["name"] = email.split("@")[0].replace(".", " ").title()

    background_tasks.add_task(_stamp_user_last_login, user.id)

    session["access_token"] = create_access_token(
        sub=user.email, role=user.role.lower(),
        candidate_id=session.get("candidateId"),
        employee_code=session.get("employeeCode"),
        name=session.get("name"),
    )
    session["token_type"] = "bearer"

    logger.info("Login OK (users table): %s (role=%s)", email, user.role)
    return ok(data=session, message="Login successful")
