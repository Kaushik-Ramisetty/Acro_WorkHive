import logging
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import OTP_TTL_SECONDS, otp_key, redis_client
from app.core.security import create_access_token, verify_password
from app.models import Employee, Role


logger = logging.getLogger(__name__)


# ---- Employee authentication (single-step credential check) -----------

def authenticate(db: Session, email: str, password: str) -> Optional[Employee]:
    """Locate an employee by personal email OR official email.

    Converted candidates receive credentials tied to their `official_email`
    after the onboarding/activate step. Matching either column lets them go
    through the standard 2FA flow instead of having to fall back to the
    legacy /api/v1/auth/login endpoint.
    """
    email_clean = (email or "").strip()
    user: Employee | None = (
        db.query(Employee)
        .filter(Employee.email.ilike(email_clean), Employee.is_deleted.is_(False))
        .first()
    )
    if not user:
        user = (
            db.query(Employee)
            .filter(Employee.official_email.ilike(email_clean), Employee.is_deleted.is_(False))
            .first()
        )
    if not user:
        return None
    if not user.password_hash or not verify_password(password, user.password_hash):
        return None
    # Progressive rehash: if the stored hash uses outdated parameters
    # (lower cost factor, deprecated scheme), upgrade it on this successful
    # login. Best-effort — any failure is swallowed because we already
    # accepted the credentials.
    try:
        from app.core.password_policy import needs_rehash
        from app.core.security import hash_password
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            db.commit()
            db.refresh(user)
            logger.info("Upgraded bcrypt hash on login for employee_id=%d", user.id)
    except Exception:
        db.rollback()
    # Self-heal: older converted employees may have role_id=NULL because the
    # conversion path didn't assign a default role. Without a role, /auth/me
    # returns role=null and the frontend can't pick a dashboard. Backfill the
    # "employee" role on the fly so the redirect works on this very login.
    if not user.role_id:
        default_role = db.query(Role).filter(Role.name == "employee").first()
        if default_role:
            user.role_id = default_role.id
            try:
                db.commit()
                db.refresh(user)
            except Exception:
                db.rollback()
    return user


def issue_token(user: Employee) -> dict:
    role_name = user.role.name if user.role else None
    token = create_access_token(
        subject=user.id,
        claims={"role": role_name, "email": user.email, "name": user.full_name},
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    }


# ---- 2FA OTP flow -----------------------------------------------------

def _generate_otp() -> str:
    """Cryptographically random 6-digit code."""
    return str(secrets.randbelow(900_000) + 100_000)


def _otp_recipient_email(user: Employee) -> str:
    """Return the address where the OTP should be delivered.

    For activated/converted employees we prefer their official (company-issued)
    email — that's the address tied to the credentials they were given. If the
    employee has not been activated or has no official email on file we fall
    back to the personal email so legacy users (seeded employees, demo
    accounts) keep working exactly as before.
    """
    official = (user.official_email or "").strip()
    if official and getattr(user, "is_activated", False):
        return official
    return user.email


def _set_otp_redis(user_id: int, otp_code: str) -> None:
    """Atomically replace any existing OTP entry: delete + hset + expire."""
    key = otp_key(user_id)
    pipe = redis_client.pipeline()
    pipe.delete(key)
    pipe.hset(key, "otp_code", otp_code)
    pipe.hset(key, "attempts", 0)
    pipe.expire(key, OTP_TTL_SECONDS)
    pipe.execute()




def _log_otp_dev(user_id: int, email: str, otp_code: str) -> None:
    """In dev mode, print the OTP so the developer can use it without SMTP/Celery."""
    if settings.APP_ENV.lower() not in ("production", "prod"):
        # Use a single, very visible line. Stdout, not just logger -- some
        # uvicorn setups buffer logger output but flush print() promptly.
        print(
            f"\n========================================================\n"
            f"  [DEV OTP]  user_id={user_id}  email={email}\n"
            f"  OTP CODE:  {otp_code}   (expires in {OTP_TTL_SECONDS}s)\n"
            f"========================================================\n",
            flush=True,
        )
        logger.info("[DEV] OTP for user_id=%d (%s) -> %s", user_id, email, otp_code)


def issue_otp_for_user(user: Employee) -> dict:
    """Mint + persist + dispatch an OTP for an already-authenticated user.

    Extracted from ``login_service`` so that *any* code path that has
    already verified credentials can put the user through the same 2FA
    pipeline — without duplicating the OTP generation, Redis persistence,
    and email/Celery dispatch logic.

    Specifically, this lets the legacy ``/api/v1/auth/login`` endpoint
    require 2FA for employees while keeping its existing direct-token
    behaviour for candidates (which Path B handles separately).
    """
    # Pending-activation employees haven't been issued credentials yet.
    if user.employment_status == "pending_activation":
        raise ValueError(
            "Your account is not yet activated. You'll receive an email "
            "with your official credentials once IT sets it up."
        )
    if user.employment_status != "active":
        raise ValueError("This account has been deactivated.")

    otp_code = _generate_otp()
    _set_otp_redis(user.id, otp_code)
    delivery_email = _otp_recipient_email(user)
    _log_otp_dev(user.id, delivery_email, otp_code)

    _is_prod = settings.APP_ENV.lower() in ("production", "prod")
    if _is_prod:
        try:
            from app.tasks.otp_tasks import send_otp_task
            send_otp_task.delay(user.id, otp_code)
            logger.info("OTP task dispatched via Celery: user_id=%d", user.id)
            return {"success": True, "requires_2fa": True, "user_id": user.id}
        except Exception as e:
            logger.warning("Celery dispatch failed (%s); sending OTP synchronously", e)

    try:
        from app.services.email_service import send_otp_email
        ok = send_otp_email(to_email=delivery_email, otp=otp_code, full_name=user.full_name or "")
        if ok:
            logger.info("OTP emailed synchronously to %s", delivery_email)
        else:
            logger.error(
                "send_otp_email returned False for %s. "
                "Most common cause: SMTP_USERNAME/SMTP_PASSWORD missing or Gmail App Password revoked. "
                "Use the [DEV OTP] code printed above to log in.",
                delivery_email,
            )
    except Exception as send_exc:
        logger.exception(
            "send_otp_email raised for %s: %s. "
            "Use the [DEV OTP] code printed above to log in.",
            delivery_email, send_exc,
        )

    return {"success": True, "requires_2fa": True, "user_id": user.id}


def login_service(email: str, password: str, db: Session) -> dict:
    """Step 1 of 2FA: validate credentials, mint OTP, queue email send.
    Raises ValueError on credential / account problems (route maps to 401)."""
    user = authenticate(db, email, password)
    if not user:
        raise ValueError("Invalid email or password.")
    return issue_otp_for_user(user)


def resend_otp_service(user_id: int, db: Session) -> dict:
    """Re-mint OTP and re-dispatch. Same atomic-replace semantics as login_service."""
    user = (
        db.query(Employee)
        .filter(Employee.id == user_id, Employee.is_deleted.is_(False))
        .first()
    )
    if not user or user.employment_status != "active":
        raise ValueError("User not found or account has been deactivated.")

    otp_code = _generate_otp()
    _set_otp_redis(user_id, otp_code)
    delivery_email = _otp_recipient_email(user)
    _log_otp_dev(user_id, delivery_email, otp_code)

    _is_prod = settings.APP_ENV.lower() in ("production", "prod")
    if _is_prod:
        try:
            from app.tasks.otp_tasks import send_otp_task
            send_otp_task.delay(user_id, otp_code)
            logger.info("OTP task re-dispatched via Celery: user_id=%d", user_id)
            return {"success": True, "message": "OTP resent"}
        except Exception as e:
            logger.warning("Celery dispatch failed (%s); sending OTP synchronously", e)

    try:
        from app.services.email_service import send_otp_email
        ok = send_otp_email(to_email=delivery_email, otp=otp_code, full_name=user.full_name or "")
        logger.info("OTP resend %s for %s", "succeeded" if ok else "FAILED", delivery_email)
    except Exception as send_exc:
        logger.exception("send_otp_email raised on resend: %s", send_exc)

    return {"success": True, "message": "OTP resent"}
