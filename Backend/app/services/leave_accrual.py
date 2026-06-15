"""Leave accrual + carry-forward engine.

Two scheduled jobs live here:

  - `run_monthly_accrual(db, year, month)`
        Runs on day 1 of each month. For every active employee × leave-type
        with `accrual_frequency='monthly'`, posts an ACCRUAL ledger entry
        for `accrual_days_per_cycle` days. Idempotent — re-running the same
        (year, month) is a no-op because the reference_id 'ACC-YYYY-MM' is
        unique per balance row and the function checks before writing.

        Probation: an employee whose `date_of_joining` is less than
        `leave_type.probation_months` calendar months before the run date
        is skipped (no entitlement yet).

        Proration: if an employee joined in the same month the accrual is
        running for, they receive a fractional credit:
            days_credited = round(days_per_cycle * remaining_days_in_month / total_days_in_month)
        Result is at least 1 day to avoid silently zeroing-out edge cases
        where the joiner started on the very last day of the month.

  - `run_year_end(db, closing_year)`
        Runs once on Jan 1 (with closing_year = today.year - 1). Two passes:
        (1) **Yearly accrual** for leave types with `accrual_frequency='yearly'`
            — credit the full `annual_quota` to the new year's balance.
        (2) **Carry-forward** every leave type with `carry_forward_limit` > 0
            — remaining = allocated - used - reserved on the closing year;
            carry = min(remaining, carry_forward_limit). A CARRY_FORWARD
            ledger entry creates / tops-up the next year's balance row.
            Forfeiture (anything above the cap) is recorded as an ADJUSTMENT
            ledger entry on the closing year so the audit trail explains
            why the balance dropped to zero.

Both functions return summary dicts that the Celery tasks log.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Employee, LeaveAccrualBracket, LeaveBalance, LeaveBalanceLedger,
    LeaveType, LedgerTxn,
)
from app.services.leave_ledger import LedgerError, post_ledger_entry


logger = logging.getLogger(__name__)


# ---------- helpers --------------------------------------------------

def _months_between(start: date, end: date) -> int:
    """Whole calendar months elapsed (start inclusive, end exclusive at day)."""
    if not start or end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) - (1 if end.day < start.day else 0)


def _is_on_probation(employee: Employee, run_on: date, probation_months: int) -> bool:
    if probation_months <= 0:
        return False
    doj = employee.date_of_joining
    if not doj:
        return False  # missing DOJ — conservative: assume eligible
    return _months_between(doj, run_on) < probation_months


def _already_posted(db: Session, *, employee_id: int, leave_type_id: str,
                    year: int, reference_id: str) -> bool:
    return db.query(LeaveBalanceLedger.id).filter(
        LeaveBalanceLedger.employee_id == employee_id,
        LeaveBalanceLedger.leave_type_id == leave_type_id,
        LeaveBalanceLedger.year == year,
        LeaveBalanceLedger.reference_id == reference_id,
    ).first() is not None


def _tenure_years(doj: Optional[date], on: date) -> int:
    """Whole years since date_of_joining as of `on`. 0 if DOJ is missing."""
    if not doj:
        return 0
    years = on.year - doj.year
    if (on.month, on.day) < (doj.month, doj.day):
        years -= 1
    return max(0, years)


def _bracket_bonus(db: Session, leave_type_id: str, tenure_years: int) -> int:
    """Highest active bracket the employee qualifies for. 0 if none match."""
    row = (
        db.query(LeaveAccrualBracket)
        .filter(
            LeaveAccrualBracket.leave_type_id == leave_type_id,
            LeaveAccrualBracket.is_active.is_(True),
            LeaveAccrualBracket.min_years <= tenure_years,
        )
        .order_by(LeaveAccrualBracket.min_years.desc())
        .first()
    )
    return int(row.bonus_days_per_cycle) if row else 0


def _prorated_days(days_per_cycle: int, doj: date, run_on: date) -> int:
    """First-month proration. If the employee joined in the same month the
    accrual is for, scale by remaining-days-in-month / days-in-month."""
    if doj.year != run_on.year or doj.month != run_on.month:
        return days_per_cycle
    total_in_month = calendar.monthrange(doj.year, doj.month)[1]
    remaining = total_in_month - doj.day + 1
    fraction = remaining / total_in_month
    credited = round(days_per_cycle * fraction)
    return max(1, credited)  # never silently zero out


def _active_employees(db: Session):
    return (
        db.query(Employee)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )


# ---------- monthly accrual -----------------------------------------

def run_monthly_accrual(db: Session, year: int, month: int) -> dict:
    """Post one ACCRUAL ledger entry per (employee, leave_type) for the
    given month. Idempotent on `reference_id='ACC-{year}-{month:02d}'`."""
    summary = {"examined": 0, "credited": 0, "skipped_probation": 0,
               "skipped_already_posted": 0, "errors": 0}

    leave_types = (
        db.query(LeaveType)
        .filter(LeaveType.accrual_frequency == "monthly",
                LeaveType.accrual_days_per_cycle.is_not(None))
        .all()
    )
    if not leave_types:
        return summary

    employees = _active_employees(db)
    run_on = date(year, month, 1)
    ref_id = f"ACC-{year}-{month:02d}"

    for emp in employees:
        for lt in leave_types:
            summary["examined"] += 1
            if _is_on_probation(emp, run_on, int(lt.probation_months or 0)):
                summary["skipped_probation"] += 1
                continue
            if _already_posted(db, employee_id=emp.id, leave_type_id=lt.id,
                               year=year, reference_id=ref_id):
                summary["skipped_already_posted"] += 1
                continue

            days = int(lt.accrual_days_per_cycle or 0)
            if days <= 0:
                continue
            # Tenure bracket bonus (highest matching bracket). Applied BEFORE
            # proration so a fractional first month still scales the bonus.
            bonus = _bracket_bonus(db, lt.id, _tenure_years(emp.date_of_joining, run_on))
            if bonus:
                days += bonus
            if emp.date_of_joining:
                days = _prorated_days(days, emp.date_of_joining, run_on)

            try:
                post_ledger_entry(
                    db,
                    employee_id=emp.id,
                    leave_type_id=lt.id,
                    transaction_type=LedgerTxn.ACCRUAL,
                    days=days,
                    reference_type="accrual_run",
                    reference_id=ref_id,
                    actor=None,
                    note=f"Monthly accrual {year}-{month:02d}: {days} day(s) of {lt.name}",
                    year=year,
                )
                summary["credited"] += 1
            except LedgerError as exc:
                summary["errors"] += 1
                logger.warning("Accrual failed for emp=%s lt=%s: %s", emp.id, lt.id, exc)

    db.commit()
    logger.info("Monthly accrual %s-%02d: %s", year, month, summary)
    return summary


# ---------- year-end (yearly accrual + carry-forward) ---------------

def run_year_end(db: Session, closing_year: int) -> dict:
    """One-shot Jan-1 routine.

    Pass 1: credit the full annual_quota into year=`closing_year + 1` for
            leave types with accrual_frequency='yearly'.
    Pass 2: carry forward remaining balance from `closing_year` into
            `closing_year + 1`, capped by `carry_forward_limit`. The
            forfeited remainder is recorded as an ADJUSTMENT (negative
            via reference note) on the closing year so the ledger trail
            explains the balance hitting zero.
    """
    summary = {
        "yearly_credited": 0,
        "carry_forwarded": 0,
        "forfeited_days": 0,
        "skipped_already_posted": 0,
        "errors": 0,
    }
    new_year = closing_year + 1
    yearly_ref = f"ACC-{new_year}-00"
    carry_ref  = f"CF-{closing_year}->{new_year}"

    # ----- Pass 1: yearly lump-sum accrual -------------------------
    yearly_types = (
        db.query(LeaveType)
        .filter(LeaveType.accrual_frequency == "yearly",
                LeaveType.annual_quota.is_not(None))
        .all()
    )
    employees = _active_employees(db)
    new_year_start = date(new_year, 1, 1)

    for emp in employees:
        for lt in yearly_types:
            if _is_on_probation(emp, new_year_start, int(lt.probation_months or 0)):
                continue
            if _already_posted(db, employee_id=emp.id, leave_type_id=lt.id,
                               year=new_year, reference_id=yearly_ref):
                summary["skipped_already_posted"] += 1
                continue
            quota = int(lt.annual_quota or 0)
            if quota <= 0:
                continue
            try:
                post_ledger_entry(
                    db,
                    employee_id=emp.id,
                    leave_type_id=lt.id,
                    transaction_type=LedgerTxn.ACCRUAL,
                    days=quota,
                    reference_type="accrual_run",
                    reference_id=yearly_ref,
                    actor=None,
                    note=f"Yearly accrual for {new_year}: {quota} day(s) of {lt.name}",
                    year=new_year,
                )
                summary["yearly_credited"] += 1
            except LedgerError as exc:
                summary["errors"] += 1
                logger.warning("Yearly accrual failed emp=%s lt=%s: %s", emp.id, lt.id, exc)

    # ----- Pass 2: carry-forward + forfeiture ----------------------
    # Skim every closing-year balance row; for those with a positive
    # remainder, carry up to `carry_forward_limit` into the new year.
    closing_balances = (
        db.query(LeaveBalance)
        .filter(LeaveBalance.year == closing_year)
        .all()
    )
    for bal in closing_balances:
        lt = db.get(LeaveType, bal.leave_type_id)
        if not lt:
            continue
        cap = int(lt.carry_forward_limit or 0)
        remaining = max(
            0,
            int(bal.allocated_balance or bal.opening_balance or 0)
            - int(bal.used or 0)
            - int(bal.reserved or 0),
        )
        if remaining <= 0:
            continue

        carry = min(remaining, cap) if cap >= 0 else remaining
        forfeit = remaining - carry

        # Carry: positive credit on the new year.
        if carry > 0 and not _already_posted(
            db, employee_id=bal.employee_id, leave_type_id=bal.leave_type_id,
            year=new_year, reference_id=carry_ref,
        ):
            try:
                post_ledger_entry(
                    db,
                    employee_id=bal.employee_id,
                    leave_type_id=bal.leave_type_id,
                    transaction_type=LedgerTxn.CARRY_FORWARD,
                    days=carry,
                    reference_type="carry_forward_run",
                    reference_id=carry_ref,
                    actor=None,
                    note=(
                        f"Carry-forward {closing_year}->{new_year}: "
                        f"{carry} of {remaining} day(s) (cap={cap})"
                    ),
                    year=new_year,
                )
                summary["carry_forwarded"] += 1
            except LedgerError as exc:
                summary["errors"] += 1
                logger.warning("Carry-forward failed emp=%s lt=%s: %s",
                               bal.employee_id, bal.leave_type_id, exc)

        # Forfeit: zero the closing-year balance via an ENCASHMENT-like
        # ADJUSTMENT that decreases the allocated bucket. We use a unique
        # reference so re-running won't double-debit.
        forfeit_ref = f"FORFEIT-{closing_year}"
        if forfeit > 0 and not _already_posted(
            db, employee_id=bal.employee_id, leave_type_id=bal.leave_type_id,
            year=closing_year, reference_id=forfeit_ref,
        ):
            try:
                # ADJUSTMENT only supports +days; for forfeiture we need a
                # decrease, which the ledger expresses as ENCASHMENT (the
                # same sub-balance, negative sign).
                post_ledger_entry(
                    db,
                    employee_id=bal.employee_id,
                    leave_type_id=bal.leave_type_id,
                    transaction_type=LedgerTxn.ENCASHMENT,
                    days=forfeit,
                    reference_type="carry_forward_run",
                    reference_id=forfeit_ref,
                    actor=None,
                    note=(
                        f"Forfeiture {closing_year}: {forfeit} day(s) above "
                        f"carry_forward cap of {cap}"
                    ),
                    year=closing_year,
                )
                summary["forfeited_days"] += forfeit
            except LedgerError as exc:
                summary["errors"] += 1
                logger.warning("Forfeit failed emp=%s lt=%s: %s",
                               bal.employee_id, bal.leave_type_id, exc)

    db.commit()
    logger.info("Year-end %s -> %s: %s", closing_year, new_year, summary)
    return summary
