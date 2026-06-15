"""Comp-off eligibility calculation service.

Determines whether a worked day qualifies for compensatory-off credit.

Policy rules:
- Employee must be T&M / fixed-bid (is_tm=True)
- Work must occur on Saturday (weekday=5) or Sunday (weekday=6)
- Worked hours must meet WEEKEND_COMP_OFF_MIN_HOURS threshold (default 4.0)

The CompOffCredit model (app/models/comp_off.py) handles the approval workflow
once eligibility is confirmed.
"""
from __future__ import annotations

from datetime import date as date_t

WEEKEND_COMP_OFF_MIN_HOURS: float = 4.0

_WEEKDAY_SAT = 5
_WEEKDAY_SUN = 6


def is_comp_off_eligible(
    *,
    is_tm: bool,
    worked_on_date: date_t,
    worked_hours: float,
    min_hours: float = WEEKEND_COMP_OFF_MIN_HOURS,
) -> tuple[bool, float]:
    """Return ``(eligible, comp_off_hours)``.

    Eligibility requires all three conditions:
    1. ``is_tm=True``  — T&M / fixed-bid employee
    2. ``worked_on_date`` falls on Saturday or Sunday
    3. ``worked_hours >= min_hours``

    Returns (False, 0.0) when any condition is not met.
    """
    if not is_tm:
        return False, 0.0
    if worked_on_date.weekday() not in (_WEEKDAY_SAT, _WEEKDAY_SUN):
        return False, 0.0
    hours = float(worked_hours or 0)
    if hours < min_hours:
        return False, 0.0
    return True, hours
