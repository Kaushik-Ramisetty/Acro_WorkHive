"""Balance reconciliation against the immutable ledger.

For every `LeaveBalance` row, this service replays the ledger to compute
the *expected* values for each bucket:

    expected_allocated  = sum(days when bucket='allocated' and txn in ACCRUAL/CARRY_FORWARD/ADJUSTMENT)
                        - sum(days when bucket='allocated' and txn = ENCASHMENT)
    expected_reserved   = sum(days when bucket='reserved'  and txn = RESERVE)
                        - sum(days when bucket='reserved'  and txn in RELEASE/CANCELLATION)
    expected_used       = sum(days when bucket='used'      and txn = DEBIT)
                        - sum(days when bucket='used'      and txn = CREDIT)

It then compares to the current row state and reports drift, optionally
applying a correction. Default mode is dry_run=True — nothing is written.

This is the operational tool for healing the comp-off bypass corruption
(Phase 5D Cause A) and any future drift.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models import LeaveBalance, LeaveBalanceLedger, LedgerTxn


logger = logging.getLogger(__name__)


# Per-bucket sign table — mirrors leave_ledger._BUCKET_AND_SIGN but
# expressed positively for clarity here. Kept in sync deliberately.
_BUCKET_SIGN = {
    LedgerTxn.RESERVE:       ("reserved",  +1),
    LedgerTxn.RELEASE:       ("reserved",  -1),
    LedgerTxn.CANCELLATION:  ("reserved",  -1),
    LedgerTxn.DEBIT:         ("used",      +1),
    LedgerTxn.CREDIT:        ("used",      -1),
    LedgerTxn.ACCRUAL:       ("allocated", +1),
    LedgerTxn.CARRY_FORWARD: ("allocated", +1),
    LedgerTxn.ENCASHMENT:    ("allocated", -1),
    LedgerTxn.ADJUSTMENT:    ("allocated", +1),
}


@dataclass
class BalanceDrift:
    """Per-row diff between stored values and ledger-replayed values."""
    balance_id: str
    employee_id: int
    leave_type_id: str
    year: int
    stored_allocated: int
    stored_reserved: int
    stored_used: int
    stored_current: int
    stored_opening: int
    expected_allocated: int
    expected_reserved: int
    expected_used: int
    drifted_columns: list[str] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.drifted_columns)

    def to_dict(self) -> dict:
        return {
            "balance_id": self.balance_id,
            "employee_id": self.employee_id,
            "leave_type_id": self.leave_type_id,
            "year": self.year,
            "stored": {
                "allocated_balance": self.stored_allocated,
                "reserved": self.stored_reserved,
                "used": self.stored_used,
                "current_balance": self.stored_current,
                "opening_balance": self.stored_opening,
            },
            "expected": {
                "allocated_balance": self.expected_allocated,
                "reserved": self.expected_reserved,
                "used": self.expected_used,
                "current_balance": max(0, self.expected_allocated - self.expected_used),
                "opening_balance": self.expected_allocated,
            },
            "drifted_columns": self.drifted_columns,
        }


def _replay_ledger(db: Session, employee_id: int, leave_type_id: str,
                   year: int) -> dict[str, int]:
    """Sum the ledger entries for one (employee, type, year). Returns
    a dict with keys 'allocated', 'reserved', 'used'."""
    rows = (
        db.query(LeaveBalanceLedger)
        .filter(
            LeaveBalanceLedger.employee_id == employee_id,
            LeaveBalanceLedger.leave_type_id == leave_type_id,
            LeaveBalanceLedger.year == year,
        )
        .all()
    )
    totals = {"allocated": 0, "reserved": 0, "used": 0}
    for r in rows:
        sign_pair = _BUCKET_SIGN.get(r.transaction_type)
        if not sign_pair:
            # Unknown txn — skip; the ledger CHECK constraint should make
            # this unreachable, but be defensive.
            continue
        bucket, sign = sign_pair
        totals[bucket] += sign * int(r.days or 0)
    return totals


def _compare(bal: LeaveBalance, expected: dict[str, int]) -> BalanceDrift:
    drifted: list[str] = []

    stored_alloc = int(bal.allocated_balance or 0)
    stored_res   = int(bal.reserved or 0)
    stored_used  = int(bal.used or 0)
    stored_curr  = int(bal.current_balance or 0)
    stored_open  = int(bal.opening_balance or 0)

    exp_alloc = int(expected["allocated"])
    exp_res   = int(expected["reserved"])
    exp_used  = int(expected["used"])
    exp_curr  = max(0, exp_alloc - exp_used)
    exp_open  = exp_alloc

    if stored_alloc != exp_alloc:
        drifted.append("allocated_balance")
    if stored_res != exp_res:
        drifted.append("reserved")
    if stored_used != exp_used:
        drifted.append("used")
    if stored_curr != exp_curr:
        drifted.append("current_balance")
    if stored_open != exp_open:
        drifted.append("opening_balance")

    return BalanceDrift(
        balance_id=bal.id,
        employee_id=bal.employee_id,
        leave_type_id=bal.leave_type_id,
        year=bal.year,
        stored_allocated=stored_alloc,
        stored_reserved=stored_res,
        stored_used=stored_used,
        stored_current=stored_curr,
        stored_opening=stored_open,
        expected_allocated=exp_alloc,
        expected_reserved=exp_res,
        expected_used=exp_used,
        drifted_columns=drifted,
    )


def _apply(bal: LeaveBalance, expected: dict[str, int]) -> None:
    """Write the corrected values onto the row. `pending_balance` is NOT
    touched — it's a non-ledger cache that the engine maintains."""
    bal.allocated_balance = int(expected["allocated"])
    bal.reserved = int(expected["reserved"])
    bal.used = int(expected["used"])
    bal.current_balance = max(0, bal.allocated_balance - bal.used)
    bal.opening_balance = bal.allocated_balance
    bal.row_version = int(bal.row_version or 0) + 1


def reconcile(db: Session, *, employee_id: Optional[int] = None,
              leave_type_id: Optional[str] = None,
              year: Optional[int] = None,
              dry_run: bool = True) -> dict:
    """Walk LeaveBalance rows, compute expected values from the ledger,
    and either report (dry_run) or apply corrections.

    Filters narrow the scope so HR can heal a single employee without
    a full-table sweep. `pending_balance` is never modified here — that
    column is a non-ledger cache; reconciling it would require summing
    the live LeaveRequest table separately and is out of scope for the
    ledger-truth reconciliation.

    Returns a structured summary suitable for JSON response.
    """
    q = db.query(LeaveBalance)
    if employee_id is not None:
        q = q.filter(LeaveBalance.employee_id == employee_id)
    if leave_type_id is not None:
        q = q.filter(LeaveBalance.leave_type_id == leave_type_id)
    if year is not None:
        q = q.filter(LeaveBalance.year == year)

    examined = 0
    drift_count = 0
    drift_details: list[dict] = []
    applied = 0

    for bal in q.all():
        examined += 1
        expected = _replay_ledger(db, bal.employee_id, bal.leave_type_id, bal.year)

        # Phase 5A backfill seeded allocated_balance from opening_balance for
        # rows that pre-date the ledger. Those rows have legitimate state
        # but ZERO ledger entries, so the naive comparison flags them as
        # drift. Detect that case and reframe: if there are no ledger rows
        # AND allocated_balance == opening_balance, the row is consistent
        # with the pre-ledger seed and shouldn't be "corrected" to zeroes.
        if (
            expected["allocated"] == 0
            and expected["reserved"] == 0
            and expected["used"] == 0
            and int(bal.allocated_balance or 0) > 0
            and int(bal.allocated_balance or 0) == int(bal.opening_balance or 0)
        ):
            # Pre-ledger seeded row; skip silently.
            continue

        drift = _compare(bal, expected)
        if not drift.has_drift:
            continue
        drift_count += 1
        drift_details.append(drift.to_dict())
        if not dry_run:
            _apply(bal, expected)
            applied += 1

    if not dry_run and applied:
        db.commit()
        logger.info("Reconcile: applied corrections to %d row(s)", applied)

    return {
        "dry_run": dry_run,
        "examined": examined,
        "drift_count": drift_count,
        "applied": applied,
        "drifts": drift_details,
    }
