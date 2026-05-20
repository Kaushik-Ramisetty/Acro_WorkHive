"""Response-shape helpers used **only when explicitly opted into**.

The codebase currently emits two response styles:
  * Core HRMS → raw JSON payloads (e.g. ``LeaveRequestOut``).
  * Onboarding → envelope ``{"success": bool, "message": str, "data": ...}``
    via ``utils/response.py``.

We do **not** force a unified style. Existing routes keep their existing
shape, and the frontend continues to read both formats. These helpers exist
so that new endpoints, or future refactors that the team explicitly opts
into, can choose a style and stick to it without re-implementing the
boilerplate.

Anything in this module is safe to import — it has no SQLAlchemy or
FastAPI dependency at module load time.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def ok_envelope(data: Any = None, message: str = "OK") -> Dict[str, Any]:
    """Build a success envelope identical to ``utils/response.ok()``.

    Provided as a typed, dependency-free alternative for code that doesn't
    want to import from ``utils/``.
    """
    return {"success": True, "message": message, "data": data}


def error_envelope(message: str, *, code: Optional[str] = None,
                   data: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": False, "message": message, "data": data}
    if code:
        payload["code"] = code
    return payload


__all__ = ["ok_envelope", "error_envelope"]
