"""utils/jwt_auth.py - Token-based auth for the WorkHive HRMS API."""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from utils.time_utils import now_utc

logger = logging.getLogger(__name__)


def _secret() -> str:
    """
    Read the JWT secret. Accept either SECRET_KEY (onboarding-style) or
    JWT_SECRET (core-style) so a single env value drives BOTH auth flows
    in the merged project.
    """
    s = (os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET") or "").strip()
    if not s:
        raise RuntimeError(
            "Neither SECRET_KEY nor JWT_SECRET is set in .env - JWT cannot operate."
        )
    if len(s) < 16:
        logger.warning(
            "JWT secret is shorter than 16 chars - use a stronger key in production."
        )
    return s


_ALGORITHM = (
    os.getenv("ALGORITHM")
    or os.getenv("JWT_ALGORITHM")
    or "HS256"
)
_DEFAULT_EXPIRE_MIN = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
    or os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    or "480"
)


class CurrentUser(BaseModel):
    """Resolved caller - what every protected endpoint receives via Depends."""
    sub: str
    role: str
    employee_id: Optional[int] = None
    candidate_id: Optional[int] = None
    employee_code: Optional[str] = None
    name: Optional[str] = None


def create_access_token(
    sub: str,
    role: str,
    *,
    expires_minutes: Optional[int] = None,
    **extra_claims,
) -> str:
    """Sign a JWT with standard fields plus any extra claims."""
    expires_in = timedelta(minutes=expires_minutes or _DEFAULT_EXPIRE_MIN)
    issued_at = now_utc()
    expires_at = issued_at + expires_in

    payload = {
        "sub":  str(sub),
        "role": (role or "").lower(),
        "iat":  int(issued_at.timestamp()),
        "exp":  int(expires_at.timestamp()),
        **{k: v for k, v in extra_claims.items() if v is not None},
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


_bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """Required-auth dependency. Returns CurrentUser or raises 401."""
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Send Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = _decode(creds.credentials)
    return CurrentUser(
        sub=claims.get("sub", ""),
        role=(claims.get("role") or "").lower(),
        employee_id=claims.get("employee_id"),
        candidate_id=claims.get("candidate_id"),
        employee_code=claims.get("employee_code"),
        name=claims.get("name"),
    )


def optional_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[CurrentUser]:
    """For routes that work with or without auth (returns None if absent)."""
    if creds is None:
        return None
    try:
        claims = _decode(creds.credentials)
    except HTTPException:
        return None
    return CurrentUser(
        sub=claims.get("sub", ""),
        role=(claims.get("role") or "").lower(),
        employee_id=claims.get("employee_id"),
        candidate_id=claims.get("candidate_id"),
        employee_code=claims.get("employee_code"),
        name=claims.get("name"),
    )


def requires_role(*allowed_roles: str):
    """Dependency factory: only allow calls whose JWT role is in allowed_roles."""
    allowed = {r.lower() for r in allowed_roles}

    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted on this endpoint.",
            )
        return user

    return _checker
