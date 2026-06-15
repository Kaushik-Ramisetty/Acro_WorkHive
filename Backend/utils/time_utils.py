"""
utils/time_utils.py — Project-wide datetime helpers.

Why this file exists
--------------------
`datetime.utcnow()` is deprecated in Python 3.12 (DeprecationWarning) and is
slated for removal in a future Python release. The recommended replacement
`datetime.now(timezone.utc)` returns a TIMEZONE-AWARE datetime, but the
SQLAlchemy columns in this project (DateTime without timezone=True) store
NAIVE datetimes. Mixing the two causes pain at comparison time.

`now_utc()` returns a NAIVE datetime that holds the current UTC wall-clock
time — semantically equivalent to the old `datetime.utcnow()` but produced
without the deprecation path.

Usage
-----
    from utils.time_utils import now_utc
    employee.updated_at = now_utc()
    if token.expires_at < now_utc():  ...
"""

import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Py < 3.9, never on this project
    ZoneInfo = None  # type: ignore[assignment]


# Default fallback when an Employee row has no time_zone set. The deployment
# is India-based (see seed data + Onboarding defaults), so Asia/Kolkata is
# the right floor. Override with HRMS_DEFAULT_TZ if you deploy elsewhere.
DEFAULT_TZ = os.environ.get("HRMS_DEFAULT_TZ", "Asia/Kolkata")


def now_utc() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime, tz_name: str | None = None) -> datetime:
    """Convert a naive-UTC datetime to a naive datetime in the named tz.

    The attendance engine stores `punch_timestamp` as naive UTC (per
    `now_utc()`). When we surface the time-of-day for display (e.g.
    `AttendanceRecord.check_in_time`), we have to convert into the user's
    local tz first — otherwise a 11:32 IST punch is rendered as 06:02 UTC
    on the dashboard.

    Falls back to `DEFAULT_TZ` if `tz_name` is empty or unknown.
    Returns a NAIVE datetime in the local zone (no tzinfo) so it composes
    cleanly with `.time()` / `.date()` and with naive-UTC columns elsewhere.
    """
    if dt is None or ZoneInfo is None:
        return dt
    aware_utc = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    target = (tz_name or "").strip() or DEFAULT_TZ
    try:
        zone = ZoneInfo(target)
    except Exception:
        zone = ZoneInfo(DEFAULT_TZ)
    return aware_utc.astimezone(zone).replace(tzinfo=None)
