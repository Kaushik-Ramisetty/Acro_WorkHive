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

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
