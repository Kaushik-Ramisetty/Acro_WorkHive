"""Password validation and progressive-rehash utilities.

Two concerns are addressed here:

1. **Policy validation** — applied to *new* passwords (signup, change-password,
   admin set-password). Existing passwords are not retroactively forced to
   meet the policy; they keep working until the user changes them.

2. **Progressive rehash** — when ``passlib`` reports that a stored hash uses
   outdated parameters (cost factor too low, deprecated scheme), the
   helper :func:`needs_rehash` returns ``True`` so callers can transparently
   re-hash on the next successful login. This requires no migration; users
   are upgraded one by one over time.

Neither helper raises at import time. All policies have sane defaults so
calling code does not need to read env vars.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Policy
# ─────────────────────────────────────────────────────────────────────────────

# Tunable via env so deployments can ratchet up the policy without code edits.
MIN_LENGTH       = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
REQUIRE_UPPER    = os.getenv("PASSWORD_REQUIRE_UPPER",   "true").lower() == "true"
REQUIRE_LOWER    = os.getenv("PASSWORD_REQUIRE_LOWER",   "true").lower() == "true"
REQUIRE_DIGIT    = os.getenv("PASSWORD_REQUIRE_DIGIT",   "true").lower() == "true"
REQUIRE_SYMBOL   = os.getenv("PASSWORD_REQUIRE_SYMBOL",  "false").lower() == "true"
MAX_LENGTH       = int(os.getenv("PASSWORD_MAX_LENGTH",  "128"))


@dataclass
class PolicyViolation:
    code: str       # e.g. "too_short"
    message: str    # human-readable


def _violations(password: str) -> List[PolicyViolation]:
    issues: List[PolicyViolation] = []
    if password is None:
        issues.append(PolicyViolation("missing", "Password is required."))
        return issues
    if len(password) < MIN_LENGTH:
        issues.append(PolicyViolation(
            "too_short", f"Password must be at least {MIN_LENGTH} characters.",
        ))
    if len(password) > MAX_LENGTH:
        issues.append(PolicyViolation(
            "too_long", f"Password must be at most {MAX_LENGTH} characters.",
        ))
    if REQUIRE_UPPER and not re.search(r"[A-Z]", password):
        issues.append(PolicyViolation(
            "needs_uppercase", "Password must contain at least one uppercase letter.",
        ))
    if REQUIRE_LOWER and not re.search(r"[a-z]", password):
        issues.append(PolicyViolation(
            "needs_lowercase", "Password must contain at least one lowercase letter.",
        ))
    if REQUIRE_DIGIT and not re.search(r"\d", password):
        issues.append(PolicyViolation(
            "needs_digit", "Password must contain at least one digit.",
        ))
    if REQUIRE_SYMBOL and not re.search(r"[^A-Za-z0-9]", password):
        issues.append(PolicyViolation(
            "needs_symbol", "Password must contain at least one symbol.",
        ))
    return issues


def validate(password: str) -> Tuple[bool, List[PolicyViolation]]:
    """Return ``(ok, violations)``. ``ok`` is True when the password meets
    the policy. Callers can surface each violation's ``message`` to users.
    """
    issues = _violations(password)
    return (len(issues) == 0, issues)


def first_error(password: str) -> Optional[str]:
    """Convenience: return the first human-readable error or ``None``."""
    issues = _violations(password)
    return issues[0].message if issues else None


# ─────────────────────────────────────────────────────────────────────────────
# Progressive rehash
# ─────────────────────────────────────────────────────────────────────────────

def needs_rehash(hashed: str) -> bool:
    """Does this stored hash need to be re-hashed with current parameters?

    Uses passlib's ``CryptContext.needs_update`` when available. Falls back
    to ``False`` if passlib is not importable, so callers can safely treat
    a False result as "no action needed".
    """
    if not hashed:
        return False
    try:
        from app.core.security import pwd_context
        return bool(pwd_context.needs_update(hashed))
    except Exception:
        return False


__all__ = [
    "PolicyViolation",
    "validate",
    "first_error",
    "needs_rehash",
]
