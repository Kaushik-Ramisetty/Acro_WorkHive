"""Holidays routes — strict location-aware filtering (Phase 5B).

Background: the previous implementation only filtered by location on
`/holidays/upcoming` and used substring matching, so Bangalore employees
saw Pune optional holidays leaking through. This module fixes both:

  - Token-level matching: `applicable_locations` is comma-separated; we
    normalize both sides (lowercase, strip whitespace) and require an
    exact token match, not a substring contain. "Bangalore" no longer
    matches "Bangalore-South" by accident.

  - Strict isolation: non-admin callers always see only their location's
    holidays plus global ones (`applicable_locations IS NULL or ''`).
    Admins can pass `?all=true` to see everything.

  - Optional holidays: `is_optional=True` rows are hidden from the
    default list and only surface when the caller explicitly requests
    them (`include_optional=true`). They still respect location matching.
"""
from datetime import date as date_t, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee, Holiday


router = APIRouter(prefix="/holidays", tags=["holidays"])


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    date: date_t
    holiday_type: Optional[str] = None
    applicable_locations: Optional[str] = None
    year: Optional[int] = None
    is_optional: bool = False


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _filter_by_location(rows: list[Holiday], location: str) -> list[Holiday]:
    """Exact-token match. A holiday is in scope when:
      - applicable_locations is NULL / empty (global), or
      - one of its comma-separated tokens (case-insensitive, trimmed)
        equals the caller's location.
    """
    loc = _norm(location)
    out = []
    for h in rows:
        raw = (h.applicable_locations or "").strip()
        if not raw:
            out.append(h)  # global
            continue
        tokens = {_norm(t) for t in raw.split(",") if t.strip()}
        if loc and loc in tokens:
            out.append(h)
    return out


def _is_admin(user: Employee) -> bool:
    return bool(user and user.role and user.role.name.lower() == "admin")


@router.get("/upcoming", response_model=list[HolidayOut])
def upcoming_holidays(
    days: int = Query(120, ge=1, le=730),
    location: Optional[str] = Query(None),
    include_optional: bool = Query(False),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Next `days` days of holidays. Defaults to the caller's location.
    Optional holidays are hidden unless `include_optional=true`."""
    today = date_t.today()
    until = today + timedelta(days=days)
    q = db.query(Holiday).filter(Holiday.date >= today, Holiday.date <= until)
    if not include_optional:
        q = q.filter(Holiday.is_optional.is_(False))
    rows = q.order_by(Holiday.date.asc()).all()

    where = location if location is not None else (user.location or "")
    rows = _filter_by_location(rows, where)
    return [HolidayOut.model_validate(h) for h in rows[:limit]]


@router.get("", response_model=list[HolidayOut])
def list_holidays(
    year: Optional[int] = Query(None),
    location: Optional[str] = Query(None),
    include_optional: bool = Query(False),
    all: bool = Query(False, description="Admin-only: bypass location filter."),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """All holidays for a year, location-filtered.

    Default behaviour for every caller (including admins, unless they pass
    `all=true`): only holidays in scope for the caller's `Employee.location`
    are returned. This is the fix for the Bangalore/Pune leak — the prior
    implementation returned everything.
    """
    yr = year or date_t.today().year
    q = db.query(Holiday).filter(Holiday.year == yr)
    if not include_optional:
        q = q.filter(Holiday.is_optional.is_(False))
    rows = q.order_by(Holiday.date.asc()).all()

    if all and _is_admin(user):
        return [HolidayOut.model_validate(h) for h in rows]

    where = location if location is not None else (user.location or "")
    rows = _filter_by_location(rows, where)
    return [HolidayOut.model_validate(h) for h in rows]


# ─── /holidays/me ──────────────────────────────────────────────────────────
# Convenience endpoint: returns the caller's location-scoped holidays for the
# requested year (defaults to current). Hides optional unless explicitly
# requested. This is what the frontend dashboard widgets should call when
# they want "holidays I, personally, will get this year" — no location query
# param needed.
@router.get("/me", response_model=list[HolidayOut])
def my_holidays(
    year: Optional[int] = Query(None),
    include_optional: bool = Query(False),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    yr = year or date_t.today().year
    q = db.query(Holiday).filter(Holiday.year == yr)
    if not include_optional:
        q = q.filter(Holiday.is_optional.is_(False))
    rows = q.order_by(Holiday.date.asc()).all()
    rows = _filter_by_location(rows, user.location or "")
    return [HolidayOut.model_validate(h) for h in rows]


# ─── /holidays/location/{location} ─────────────────────────────────────────
# Admin-only: inspect another office's holiday list without changing the
# caller's location. Mirrors the same `_filter_by_location` semantics used
# everywhere else so behaviour stays consistent.
@router.get("/location/{location}", response_model=list[HolidayOut])
def holidays_for_location(
    location: str = Path(..., min_length=1, max_length=100),
    year: Optional[int] = Query(None),
    include_optional: bool = Query(False),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin only")
    yr = year or date_t.today().year
    q = db.query(Holiday).filter(Holiday.year == yr)
    if not include_optional:
        q = q.filter(Holiday.is_optional.is_(False))
    rows = q.order_by(Holiday.date.asc()).all()
    rows = _filter_by_location(rows, location)
    return [HolidayOut.model_validate(h) for h in rows]
