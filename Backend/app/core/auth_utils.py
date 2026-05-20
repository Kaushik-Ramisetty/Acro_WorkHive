"""Shared auth primitives.

The codebase has two parallel auth surfaces:

  * Core 2FA flow (``/auth/login`` → ``/auth/verify-otp``) — uses
    :mod:`app.core.security` (passlib + python-jose).
  * Legacy onboarding flow (``/api/v1/auth/login``) — uses :mod:`utils.jwt_auth`
    plus ad-hoc ``bcrypt`` calls in :mod:`api.Onboarding_Model.auth`.

Both flows correctly verify bcrypt hashes today; passlib's bcrypt scheme
recognises any hash produced by the standalone ``bcrypt`` package and vice
versa. This module collects the small primitives both surfaces need, so a
future consolidation pass can adopt them gradually without forcing a
rewrite of either auth path.

Nothing here is wired into existing routes yet — adopting it is opt-in.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password as _core_hash, verify_password as _core_verify
from app.models import Employee


logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    """Single canonical bcrypt hasher. Delegates to passlib (CryptContext)
    so progressive rehash via :func:`app.core.password_policy.needs_rehash`
    keeps working."""
    return _core_hash(plain)


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    """Single canonical password verifier. Returns False (never raises) when
    the stored hash is missing or malformed — matches the existing safer
    behaviour of both auth flows."""
    if not hashed:
        return False
    try:
        return _core_verify(plain, hashed)
    except Exception:
        return False


def find_employee_by_login(db: Session, email: str) -> Optional[Employee]:
    """Resolve an Employee by personal *or* official email.

    Mirrors the lookup that :func:`app.services.auth_service.authenticate`
    performs. Extracted here so any future code that needs the same lookup
    can reuse it without duplicating the SQL.
    """
    email_clean = (email or "").strip()
    if not email_clean:
        return None
    user: Employee | None = (
        db.query(Employee)
        .filter(Employee.email.ilike(email_clean), Employee.is_deleted.is_(False))
        .first()
    )
    if user is None:
        user = (
            db.query(Employee)
            .filter(Employee.official_email.ilike(email_clean), Employee.is_deleted.is_(False))
            .first()
        )
    return user


__all__ = [
    "hash_password",
    "verify_password",
    "find_employee_by_login",
]
