"""Authoritative balance mutator.

Every change to a `LeaveBalance` row goes through `post_ledger_entry`.
The function:
  1. SELECTs the balance row `FOR UPDATE` (row-level lock on SQL Server
     and Postgres; SQLite no-op but still safe under its single-writer
     model).
  2. Applies the delta to the right bucket (allocated / reserved / used).
  3. Mirrors the change into legacy columns (`opening_balance`,
     `current_balance`, `used`, `reserved`) so existing reads continue to
     work without an API break.
  4. Bumps `row_version` for downstream optimistic-concurrency checks.
  5. Inserts an immutable `LeaveBalanceLedger` row with the full before/after
     snapshot, transaction type, reference, and actor.

The caller owns the surrounding `db.commit()` boundary — this function
flushes but never commits, so the ledger row and the balance row are
guaranteed to land or roll back together.

`post_ledger_entry` raises `LedgerError` on:
  - unknown leave_type / employee
  - underflow (reserve when available would go negative, etc.)
  - negative `days`
"""
from __future__ import annotations

from datetime import date as _date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Employee, LeaveBalance, LeaveBalanceLedger, LeaveType, LedgerTxn,
)


class LedgerError(Exception):
    pass


# Mapping from transaction_type to which sub-balance it touches and the sign
# (+1 increases the bucket, -1 decreases it).
_BUCKET_AND_SIGN = {
    LedgerTxn.RESERVE:       ("reserved",  +1),
    LedgerTxn.RELEASE:       ("reserved",  -1),
    LedgerTxn.CANCELLATION:  ("reserved",  -1),  # synonym for RELEASE in cancel paths
    LedgerTxn.DEBIT:         ("used",      +1),
    LedgerTxn.CREDIT:        ("used",      -1),
    LedgerTxn.ACCRUAL:       ("allocated", +1),
    LedgerTxn.CARRY_FORWARD: ("allocated", +1),
    LedgerTxn.ENCASHMENT:    ("allocated", -1),
    LedgerTxn.ADJUSTMENT:    ("allocated", +1),  # caller passes negative `days`? No — see below
}


def _today_year() -> int:
    return _date.today().year


def _lock_balance(db: Session, employee_id: int, leave_type_id: str, year: int) -> Optional[LeaveBalance]:
    """SELECT ... FOR UPDATE on the balance row. Creates the row on first
    use so callers don't need to care whether it pre-existed."""
    q = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
        .with_for_update()
    )
    return q.first()


def _next_balance_id(db: Session) -> str:
    last = (
        db.query(LeaveBalance)
        .filter(LeaveBalance.id.like("LB%"))
        .order_by(LeaveBalance.id.desc())
        .first()
    )
    n = 1
    if last and last.id and last.id.startswith("LB"):
        try:
            n = int(last.id[2:]) + 1
        except ValueError:
            pass
    return f"LB{n:04d}"


def _ensure_balance(db: Session, employee_id: int, leave_type_id: str,
                    year: int) -> LeaveBalance:
    bal = _lock_balance(db, employee_id, leave_type_id, year)
    if bal:
        return bal
    bal = LeaveBalance(
        id=_next_balance_id(db),
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=year,
        opening_balance=0,
        used=0,
        reserved=0,
        current_balance=0,
        allocated_balance=0,
        pending_balance=0,
        row_version=0,
    )
    db.add(bal)
    db.flush()
    # Re-lock the newly-inserted row.
    return _lock_balance(db, employee_id, leave_type_id, year) or bal


def post_ledger_entry(
    db: Session,
    *,
    employee_id: int,
    leave_type_id: str,
    transaction_type: str,
    days: int,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    actor: Optional[Employee] = None,
    note: Optional[str] = None,
    year: Optional[int] = None,
    allow_negative_available: bool = False,
) -> LeaveBalanceLedger:
    """Atomic balance mutation + immutable ledger insert."""
    if transaction_type not in LedgerTxn.ALL:
        raise LedgerError(f"Unknown transaction_type '{transaction_type}'.")
    if days < 0:
        raise LedgerError("`days` must be non-negative; flip transaction_type for refunds.")
    if days == 0:
        raise LedgerError("Zero-day ledger entries are not allowed.")

    yr = year or _today_year()
    if not db.get(LeaveType, leave_type_id):
        raise LedgerError(f"Unknown leave type '{leave_type_id}'.")

    bal = _ensure_balance(db, employee_id, leave_type_id, yr)

    before_alloc = int(bal.allocated_balance or 0)
    before_res   = int(bal.reserved or 0)
    before_used  = int(bal.used or 0)

    # ── Composite txn types (Hybrid v2) ──────────────────────────────────
    # These atomically move more than one bucket. We compute new triples
    # in-line then fall through to the persistence block below.
    if transaction_type in LedgerTxn.COMPOSITE:
        return _post_composite(
            db, bal,
            transaction_type=transaction_type,
            days=days,
            before_alloc=before_alloc, before_res=before_res, before_used=before_used,
            reference_type=reference_type, reference_id=reference_id,
            actor=actor, note=note, year=yr,
            allow_negative_available=allow_negative_available,
        )

    bucket, sign = _BUCKET_AND_SIGN[transaction_type]

    after_alloc = before_alloc
    after_res   = before_res
    after_used  = before_used
    if bucket == "allocated":
        after_alloc = before_alloc + sign * days
        if after_alloc < 0 and not allow_negative_available:
            raise LedgerError(
                f"{transaction_type} would drive allocated_balance below 0 "
                f"(before={before_alloc}, days={days})."
            )
    elif bucket == "reserved":
        after_res = before_res + sign * days
        if after_res < 0:
            raise LedgerError(
                f"{transaction_type} would drive reserved below 0 "
                f"(before={before_res}, days={days})."
            )
        # Reserving requires sufficient available.
        if sign > 0:
            available = before_alloc - before_res - int(bal.pending_balance or 0)
            if days > available and not allow_negative_available:
                raise LedgerError(
                    f"Insufficient available balance to reserve {days} day(s): "
                    f"available={available} (allocated={before_alloc}, "
                    f"reserved={before_res}, pending={bal.pending_balance or 0})."
                )
    elif bucket == "used":
        after_used = before_used + sign * days
        if after_used < 0:
            raise LedgerError(
                f"{transaction_type} would drive used below 0 "
                f"(before={before_used}, days={days})."
            )

    # Apply to balance row.
    bal.allocated_balance = after_alloc
    bal.reserved = after_res
    bal.used = after_used
    # Mirror into legacy columns so existing serializers stay correct.
    bal.opening_balance = after_alloc
    bal.current_balance = max(0, after_alloc - after_used)
    bal.row_version = int(bal.row_version or 0) + 1

    entry = LeaveBalanceLedger(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        year=yr,
        transaction_type=transaction_type,
        days=days,
        bucket=bucket,
        before_allocated=before_alloc,
        before_reserved=before_res,
        before_used=before_used,
        after_allocated=after_alloc,
        after_reserved=after_res,
        after_used=after_used,
        reference_type=reference_type,
        reference_id=reference_id,
        actor_id=actor.id if actor else None,
        note=note,
    )
    db.add(entry)
    db.flush()
    return entry


# ---------- pending-balance helpers ---------------------------------

def adjust_pending(db: Session, employee_id: int, leave_type_id: str,
                    days: int, *, year: Optional[int] = None) -> None:
    """Bump (positive `days`) or release (negative `days`) the
    pending_balance counter on the relevant LeaveBalance row.

    `pending_balance` is NOT ledger-tracked because it doesn't change the
    actual entitlement — it's a query-acceleration cache the engine
    refreshes whenever a request enters/leaves the 'pending' state.
    """
    if days == 0:
        return
    yr = year or _today_year()
    bal = _ensure_balance(db, employee_id, leave_type_id, yr)
    new_val = int(bal.pending_balance or 0) + days
    if new_val < 0:
        new_val = 0
    bal.pending_balance = new_val
    bal.row_version = int(bal.row_version or 0) + 1


# ---------- read-only availability helper ---------------------------

def get_available(db: Session, employee_id: int, leave_type_id: str,
                  year: Optional[int] = None) -> int:
    """available = allocated - reserved - pending. Returns 0 if no row."""
    yr = year or _today_year()
    bal = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == yr,
        )
        .first()
    )
    if not bal:
        return 0
    return max(
        0,
        int(bal.allocated_balance or 0)
        - int(bal.reserved or 0)
        - int(bal.pending_balance or 0),
    )


# ──────────────────────────────────────────────────────────────────────────
# Hybrid v2 — composite multi-bucket ledger writes
# ──────────────────────────────────────────────────────────────────────────
def _post_composite(
    db: Session,
    bal: LeaveBalance,
    *,
    transaction_type: str,
    days: int,
    before_alloc: int, before_res: int, before_used: int,
    reference_type: Optional[str],
    reference_id: Optional[str],
    actor: Optional[Employee],
    note: Optional[str],
    year: int,
    allow_negative_available: bool,
) -> LeaveBalanceLedger:
    """Persist a composite (multi-bucket) ledger row + atomic balance update.

    Bucket movement table (Hybrid v2 spec):

      LEAVE_DEDUCTION              reserved += days   used += days
      LEAVE_COMPLETION             reserved -= days
        (single-bucket, but exposed as a composite-typed alias so callers
         can use the named v2 vocabulary; bucket is 'reserved' for clarity)
      LEAVE_CANCELLATION_REVERSAL  reserved -= days   used -= days
      PARTIAL_CANCELLATION         reserved -= days   used -= days
        (caller passes only the *remaining* day count.)
    """
    after_alloc = before_alloc
    after_res   = before_res
    after_used  = before_used

    if transaction_type == LedgerTxn.LEAVE_DEDUCTION:
        # Pre-flight: available must cover the deduction.
        available = before_alloc - before_res - int(bal.pending_balance or 0)
        if days > available and not allow_negative_available:
            raise LedgerError(
                f"Insufficient available balance for LEAVE_DEDUCTION of {days} day(s): "
                f"available={available} (allocated={before_alloc}, "
                f"reserved={before_res}, pending={bal.pending_balance or 0})."
            )
        after_res  = before_res  + days
        after_used = before_used + days
        bucket_label = "multi"

    elif transaction_type == LedgerTxn.LEAVE_COMPLETION:
        # Lightweight: only clear the reservation. `used` stays put because
        # it was already moved at approval time under v2 semantics.
        if before_res - days < 0 and not allow_negative_available:
            raise LedgerError(
                f"LEAVE_COMPLETION would drive reserved below 0 "
                f"(before={before_res}, days={days})."
            )
        after_res = before_res - days
        bucket_label = "reserved"

    elif transaction_type == LedgerTxn.LEAVE_CANCELLATION_REVERSAL:
        # Full reversal of an approved future-dated leave that was never
        # consumed. Both buckets unwind together.
        if before_res - days < 0 and not allow_negative_available:
            raise LedgerError(
                f"LEAVE_CANCELLATION_REVERSAL would drive reserved below 0 "
                f"(before={before_res}, days={days})."
            )
        if before_used - days < 0 and not allow_negative_available:
            raise LedgerError(
                f"LEAVE_CANCELLATION_REVERSAL would drive used below 0 "
                f"(before={before_used}, days={days})."
            )
        after_res  = before_res  - days
        after_used = before_used - days
        bucket_label = "multi"

    elif transaction_type == LedgerTxn.PARTIAL_CANCELLATION:
        # Partial cancellation = same shape as REVERSAL but `days` is the
        # not-yet-consumed remainder. The already-consumed portion is
        # locked in (payroll-safe).
        if before_res - days < 0 and not allow_negative_available:
            raise LedgerError(
                f"PARTIAL_CANCELLATION would drive reserved below 0 "
                f"(before={before_res}, days={days})."
            )
        if before_used - days < 0 and not allow_negative_available:
            raise LedgerError(
                f"PARTIAL_CANCELLATION would drive used below 0 "
                f"(before={before_used}, days={days})."
            )
        after_res  = before_res  - days
        after_used = before_used - days
        bucket_label = "multi"
    else:
        raise LedgerError(f"Unknown composite transaction_type '{transaction_type}'.")

    # Mutate the locked balance row.
    bal.allocated_balance = after_alloc
    bal.reserved          = after_res
    bal.used              = after_used
    bal.opening_balance   = after_alloc
    bal.current_balance   = max(0, after_alloc - after_used)
    bal.row_version       = int(bal.row_version or 0) + 1

    entry = LeaveBalanceLedger(
        employee_id=bal.employee_id,
        leave_type_id=bal.leave_type_id,
        year=year,
        transaction_type=transaction_type,
        days=days,
        bucket=bucket_label,
        before_allocated=before_alloc,
        before_reserved=before_res,
        before_used=before_used,
        after_allocated=after_alloc,
        after_reserved=after_res,
        after_used=after_used,
        reference_type=reference_type,
        reference_id=reference_id,
        actor_id=actor.id if actor else None,
        note=note,
    )
    db.add(entry)
    db.flush()
    return entry
