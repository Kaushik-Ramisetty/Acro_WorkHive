"""Client approval token service.

Generates signed, time-limited tokens for external (unauthenticated) client
manager approval of timesheets via email link.

Token format:  base64url(payload_json).hmac_sha256_hex

Payload:  {"ts_id": "TS000001", "exp": <unix_timestamp>}

Security properties:
  - HMAC-SHA256 signed with the app's JWT_SECRET
  - Expires after expires_hours (default 72 h)
  - Single-use: callers must clear ts.client_token after consuming the token
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import get_settings


def _secret() -> bytes:
    return get_settings().JWT_SECRET.encode("utf-8")


def generate_client_token(timesheet_id: str, expires_hours: int = 72) -> str:
    """Return a URL-safe HMAC-signed token for external client approval."""
    payload = json.dumps(
        {"ts_id": timesheet_id, "exp": int(time.time()) + expires_hours * 3600},
        separators=(",", ":"),
    )
    b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_client_token(token: str) -> dict | None:
    """Return payload dict if the token is valid and unexpired, else None."""
    try:
        b64, sig = token.rsplit(".", 1)
        expected = hmac.new(_secret(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        # Restore base64 padding stripped during generation
        padded = b64 + "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
