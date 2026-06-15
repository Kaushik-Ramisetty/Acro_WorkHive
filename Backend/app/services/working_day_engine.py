"""Centralized working-day engine.

Single source of truth for "is this date a working day for this employee?"
across leave application, validation, dashboards, attendance reconciliation,
and partial-cancellation refunds. ALL leave-day calculations route through
this module — never recompute weekend/holiday math anywhere else.

Public API
----------
    is_working_day(db, dt, location, *, year=None)
        bool — False on Sat/Sun OR a non-optional holiday in `location`.

    next_working_day(db, after, location, *, max_lookahead=30)
        date — the next working day strictly after `after`.

    count_working_days(db, start, end, location, *, half_day_start=False,
                       half_day_end=False)
        float — working days in the inclusive range, half-day aware.

    compute_leave_span(db, employee, start, requested_days, *,
                       half_day_start=False, half_day_end=False)
        SpanResult — calculated end_date + the day-by-day breakdown for
        UI preview and audit. Raises SpanError on bad input.

    preview_leave_span(db, employee, start, requested_days, ...) → dict
        Thin serializable wrapper around compute_leave_span for the
        POST /leave/preview API.

Holiday handling
----------------
- Non-optional holidays in the employee's location are SKIPPED unless
  explicitly opted in.
- Optional holidays are NEVER skipped automatically — they behave like
  normal working days. Employees can still take them by passing the
  optional holiday id in `selected_optional_holiday_ids` (forward-compat
  hook; not yet wired into apply_leave).
- Holidays where `applicable_locations IS NULL` are treated as global and
  skipped for everyone.

Half-day semantics
------------------
- `half_day_start=True` → start_date counts as 0.5 (employee works the
  first half).
- `half_day_end=True`   → end_date counts as 0.5.
- If start == end and either flag is set, the day is 0.5.

Performance
-----------
A per-process, per-(location, year) holiday cache (LRU, 64 buckets) keeps
the engine O(1) per date check after the first hit. The cache is bounded
so a multi-tenant deployment can run thousands of locations without
unbounded memory growth.

Backward compatibility
----------------------
- `count_working_days()` returns a float so half-day callers work, but
  whole-day callers can still rely on `int(result) == result`.
- The legacy `(end - start).days + 1` calculation is preserved by the
  apply_leave path that takes an explicit end date — only the new
  apply-by-days variant uses this engine end-to-end. Validators flip
  ctx.days to working-day units across the board so balance/overlap
  math is consistent everywhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Employee, Holiday


logger = logging.getLogger(__name__)


# Saturday=5, Sunday=6 in Python's weekday() encoding.
_WEEKEND_DAYS = frozenset({5, 6})

# Maximum forward window we'll scan looking for `requested_days` working
# days. 365 is enough for "30 working days starting in mid-December
# across two leave-year boundaries with 12 holidays" — a deliberately
# loose ceiling that still rejects nonsense input.
_MAX_SCAN_DAYS = 365


class SpanError(Exception):
    """Raised by the engine when inputs would produce an invalid span."""


# ── Public dataclasses ────────────────────────────────────────────────────
@dataclass
class DayKind:
    """One day in a computed leave span."""
    date: date
    kind: str       # 'working' | 'weekend' | 'holiday' | 'optional_holiday'
    fractional_days: float = 1.0  # 0.5 for half-day boundaries
    holiday_name: Optional[str] = None


@dataclass
class SpanResult:
    """Output of compute_leave_span — drives the UI preview + audit log."""
    start_date: date
    end_date: date
    requested_days: float
    counted_working_days: float
    days: list[DayKind] = field(default_factory=list)

    @property
    def skipped_weekends(self) -> list[date]:
        return [d.date for d in self.days if d.kind == "weekend"]

    @property
    def skipped_holidays(self) -> list[DayKind]:
        return [d for d in self.days if d.kind == "holiday"]

    def to_dict(self) -> dict:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date":   self.end_date.isoformat(),
            "requested_days":       self.requested_days,
            "counted_working_days": self.counted_working_days,
            "skipped_weekends":     [d.isoformat() for d in self.skipped_weekends],
            "skipped_holidays":     [
                {"date": h.date.isoformat(), "name": h.holiday_name}
                for h in self.skipped_holidays
            ],
            "days": [
                {
                    "date":             d.date.isoformat(),
                    "kind":             d.kind,
                    "fractional_days":  d.fractional_days,
                    "holiday_name":     d.holiday_name,
                }
                for d in self.days
            ],
        }


# ── Holiday cache ────────────────────────────────────────────────────────
# Per-process cache. Cleared by reset_cache() when admins seed/edit holidays
# so live updates take effect without a restart.
def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _holiday_matches_location(holiday: Holiday, location_norm: str) -> bool:
    raw = (holiday.applicable_locations or "").strip()
    if not raw:
        return True  # global → applies to everyone
    tokens = {_norm(t) for t in raw.split(",") if t.strip()}
    return bool(location_norm) and location_norm in tokens


_HOLIDAY_CACHE: dict[tuple[str, int], dict[date, Holiday]] = {}
_HOLIDAY_CACHE_MAX = 64  # bounded so a multi-tenant deployment stays sane


def _holiday_map(db: Session, location: str, year: int,
                 *, include_optional: bool = False) -> dict[date, Holiday]:
    """Return {date: Holiday} for the given location/year.

    Per spec, optional holidays are NOT skipped by default — they only
    appear when callers opt in. The cache key encodes the flag so both
    views stay correct simultaneously.
    """
    loc = _norm(location)
    key = (f"{loc}::{1 if include_optional else 0}", year)
    if key in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[key]

    q = db.query(Holiday).filter(Holiday.year == year)
    if not include_optional:
        q = q.filter(Holiday.is_optional.is_(False))
    rows = q.all()
    out: dict[date, Holiday] = {}
    for h in rows:
        if _holiday_matches_location(h, loc):
            out[h.date] = h

    # LRU eviction — drop oldest entry when over budget.
    if len(_HOLIDAY_CACHE) >= _HOLIDAY_CACHE_MAX:
        try:
            _HOLIDAY_CACHE.pop(next(iter(_HOLIDAY_CACHE)))
        except StopIteration:
            pass
    _HOLIDAY_CACHE[key] = out
    return out


def reset_cache() -> None:
    """Drop the entire holiday cache. Call after admin holiday edits."""
    _HOLIDAY_CACHE.clear()


# ── Primary primitives ───────────────────────────────────────────────────
def is_weekend(dt: date) -> bool:
    return dt.weekday() in _WEEKEND_DAYS


def is_working_day(db: Session, dt: date, location: Optional[str],
                   *, include_optional_as_holiday: bool = False) -> bool:
    """The central predicate. True when:
      - the date is Mon-Fri AND
      - the date is not a (location-scoped) non-optional holiday.

    Optional holidays default to working days. Pass
    `include_optional_as_holiday=True` to flip that for a specific check
    (e.g. an employee who opted in to an optional holiday)."""
    if is_weekend(dt):
        return False
    hmap = _holiday_map(
        db, location or "", dt.year,
        include_optional=include_optional_as_holiday,
    )
    return dt not in hmap


def next_working_day(db: Session, after: date, location: Optional[str],
                     *, max_lookahead: int = 30) -> date:
    """Return the next working day strictly after `after`. Raises
    SpanError if no working day is found within `max_lookahead` days."""
    cursor = after + timedelta(days=1)
    for _ in range(max_lookahead):
        if is_working_day(db, cursor, location):
            return cursor
        cursor += timedelta(days=1)
    raise SpanError(
        f"No working day within {max_lookahead} days after {after.isoformat()} "
        f"for location '{location}'."
    )


def count_working_days(db: Session, start: date, end: date,
                       location: Optional[str], *,
                       half_day_start: bool = False,
                       half_day_end: bool = False) -> float:
    """Inclusive count of working days between two dates."""
    if end < start:
        return 0.0
    total = 0.0
    cursor = start
    while cursor <= end:
        if is_working_day(db, cursor, location):
            total += 1.0
        cursor += timedelta(days=1)
    if half_day_start and is_working_day(db, start, location):
        total -= 0.5
    if half_day_end and end != start and is_working_day(db, end, location):
        total -= 0.5
    if half_day_start and half_day_end and start == end:
        # Single-day half-day: subtract only once (would be -1.0 otherwise).
        total += 0.5
    return max(0.0, total)


# ── Span calculator (the one apply_leave_by_days uses) ───────────────────
def compute_leave_span(
    db: Session,
    employee: Employee,
    start: date,
    requested_days: float,
    *,
    half_day_start: bool = False,
    half_day_end: bool = False,
) -> SpanResult:
    """Given a start date + a number of WORKING days to consume, return the
    full span: the auto-calculated end_date and a day-by-day breakdown.

    Hard rules:
      - `start` must be a working day for the employee's location. The
        validator layer prints the user-facing error; this function
        enforces it programmatically for any caller that bypasses
        validation (preview API, etc.).
      - `requested_days` must be > 0 and ≤ _MAX_SCAN_DAYS.

    Half-day handling:
      - `half_day_start` reduces start_date's contribution to 0.5.
      - `half_day_end` reduces the last working day's contribution to 0.5.
      - The function still walks the calendar one day at a time; the
        fractional adjustments are applied at the boundaries only.
    """
    if requested_days <= 0:
        raise SpanError("requested_days must be greater than zero.")
    if requested_days > _MAX_SCAN_DAYS:
        raise SpanError(f"requested_days exceeds the {_MAX_SCAN_DAYS} day ceiling.")

    location = employee.location if employee else None

    if not is_working_day(db, start, location):
        # Defence-in-depth: validator catches this earlier but we never
        # want a downstream caller to accidentally generate a leave
        # starting on a weekend / holiday.
        kind = "weekend" if is_weekend(start) else "holiday"
        raise SpanError(
            f"Cannot start leave on {start.isoformat()} — it is a {kind}."
        )

    # Walk forward, tagging every calendar day until we've accumulated
    # the requested working-day quota.
    days: list[DayKind] = []
    accumulated = 0.0
    cursor = start
    scan_count = 0
    last_working_date = start
    hmap_year_cache: dict[int, dict[date, Holiday]] = {}

    while accumulated < requested_days and scan_count < _MAX_SCAN_DAYS:
        # Look up the right year's holiday map (avoid recomputing the
        # cache for every day in a long span).
        hmap = hmap_year_cache.get(cursor.year)
        if hmap is None:
            hmap = _holiday_map(db, location or "", cursor.year)
            hmap_year_cache[cursor.year] = hmap

        if is_weekend(cursor):
            days.append(DayKind(date=cursor, kind="weekend", fractional_days=0.0))
        elif cursor in hmap:
            h = hmap[cursor]
            days.append(DayKind(
                date=cursor,
                kind="holiday",
                fractional_days=0.0,
                holiday_name=h.name,
            ))
        else:
            # Working day. Apply half-day adjustment ONLY on the first
            # date if half_day_start, never inside the span.
            fractional = 1.0
            is_first_working = (accumulated == 0.0)
            if is_first_working and half_day_start:
                fractional = 0.5
            days.append(DayKind(date=cursor, kind="working", fractional_days=fractional))
            accumulated += fractional
            last_working_date = cursor

        cursor += timedelta(days=1)
        scan_count += 1

    # half_day_end: nudge the last working day to 0.5 if asked (and we
    # still have ≥1 day to give back).
    if half_day_end and last_working_date != start:
        # Find the last 'working' DayKind and rebalance.
        for d in reversed(days):
            if d.kind == "working" and d.date == last_working_date:
                if d.fractional_days >= 0.5:
                    d.fractional_days -= 0.5
                    accumulated -= 0.5
                break

    if accumulated + 1e-9 < requested_days:
        raise SpanError(
            f"Could not accumulate {requested_days} working day(s) within the "
            f"{_MAX_SCAN_DAYS}-day scan window starting {start.isoformat()}."
        )

    end_date = last_working_date
    return SpanResult(
        start_date=start,
        end_date=end_date,
        requested_days=requested_days,
        counted_working_days=accumulated,
        days=days,
    )


def preview_leave_span(
    db: Session,
    employee: Employee,
    start: date,
    requested_days: float,
    *,
    half_day_start: bool = False,
    half_day_end: bool = False,
) -> dict:
    """Thin serializable wrapper for the preview API."""
    result = compute_leave_span(
        db, employee, start, requested_days,
        half_day_start=half_day_start,
        half_day_end=half_day_end,
    )
    return result.to_dict()
