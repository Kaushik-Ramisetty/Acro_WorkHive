"""
utils/phone_validator.py — E.164 phone number validation for WorkHive HRMS.

E.164 format:
  + <country-code (1-3 digits)> <subscriber-number>
  Total digits (after +): 8 to 15
  Examples: +919876543210  +14155552671  +447911123456

Validation is intentionally liberal about separators — spaces, dashes,
and parentheses are stripped before checking so that "+91 98765 43210"
normalises cleanly to "+919876543210" before storage.
"""

import re
from typing import Optional

# Compiled once at import — matches the canonical E.164 form AFTER normalisation
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# Characters that are stripped during normalisation (separators only)
_STRIP_RE = re.compile(r"[\s\-\(\)\. ]+")


def normalise_phone(raw: str) -> str:
    """
    Strip common separators from a phone string so "+91 98765 43210"
    becomes "+919876543210".  Does NOT validate — call validate_e164 for that.
    """
    return _STRIP_RE.sub("", raw.strip())


def validate_e164(phone: Optional[str]) -> Optional[str]:
    """
    Normalise and validate a phone number in E.164 format.

    - None / empty string → returns None (field is optional)
    - Strips spaces, dashes, parentheses before validating
    - Must start with +, followed by a non-zero country code digit
    - Digits after + must be 8–15 (ITU-T E.164 maximum is 15)
    - Returns the normalised E.164 string on success
    - Raises ValueError with a clear message on failure

    Suitable for use as a Pydantic field_validator.
    """
    if phone is None:
        return None

    # Normalise separators first
    normalised = normalise_phone(phone)

    if not normalised:          # empty after stripping
        return None

    if not normalised.startswith("+"):
        raise ValueError(
            f"Phone number must start with '+' and country code — "
            f"received '{phone}'. Example: +919876543210"
        )

    digits_after_plus = normalised[1:]

    if not digits_after_plus:
        raise ValueError("Phone number is missing the country code and subscriber number.")

    if not digits_after_plus.isdigit():
        raise ValueError(
            f"Phone number may only contain digits after '+' — received '{phone}'."
        )

    if not _E164_RE.match(normalised):
        total = len(digits_after_plus)
        if total < 8:
            raise ValueError(
                f"Phone number '{phone}' is too short ({total} digit(s) after '+'). "
                "Minimum is 8 digits including country code."
            )
        if total > 15:
            raise ValueError(
                f"Phone number '{phone}' is too long ({total} digit(s) after '+'). "
                "Maximum is 15 digits (ITU-T E.164)."
            )
        if digits_after_plus[0] == "0":
            raise ValueError(
                f"Country code cannot start with 0 — received '{phone}'."
            )
        raise ValueError(
            f"Invalid phone number format '{phone}'. "
            "Use E.164: +<country_code><number>, e.g. +919876543210"
        )

    return normalised
