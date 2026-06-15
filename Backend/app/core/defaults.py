"""Centralised defaults for the onboarding workflow.

Historically the candidate→employee conversion path hardcoded a literal
``"employee123"`` password (and ``"candidate123"`` for the candidate portal
account). Those literals are still honoured as a final fallback so existing
tests + flows keep working unchanged, but the actual values are now read
from the environment so production deployments can rotate them centrally
without code changes.

This module is import-safe: it has no SQLAlchemy / FastAPI dependencies and
can be pulled into any module without risk of circular imports.
"""
from __future__ import annotations

import logging
import os


logger = logging.getLogger(__name__)


# Literal fallbacks kept identical to the pre-refactor values so that any
# call site that previously imported these constants continues to receive
# the exact same string when no env var is set.
_FALLBACK_EMPLOYEE_PASSWORD = "employee123"
_FALLBACK_CANDIDATE_PASSWORD = "candidate123"


def default_employee_password() -> str:
    """Initial password assigned during candidate→employee conversion.

    Order of preference:
      1. ``DEFAULT_EMPLOYEE_PASSWORD`` env var.
      2. Hardcoded fallback (matches the legacy literal so behaviour is
         identical when the env var is unset).
    """
    val = (os.getenv("DEFAULT_EMPLOYEE_PASSWORD") or "").strip()
    return val or _FALLBACK_EMPLOYEE_PASSWORD


def default_candidate_password() -> str:
    """Initial password for the candidate-portal user that gets created
    when an offer is sent. Resolution order mirrors
    :func:`default_employee_password`."""
    val = (os.getenv("DEFAULT_CANDIDATE_PASSWORD") or "").strip()
    return val or _FALLBACK_CANDIDATE_PASSWORD


__all__ = [
    "default_employee_password",
    "default_candidate_password",
]
