"""One-shot, idempotent migration from v1 (delayed-deduction) to v2
(immediate-deduction + reservation-tracking).

What this migration does
------------------------
Under v1, an approved-but-not-yet-consumed leave occupied days in the
`reserved` bucket only. Under v2, the same leave occupies both `reserved`
AND `used` (the deduction is moved forward from "scheduler" to
"approval"). This migration sweeps every already-approved leave request
and writes a synthetic LEAVE_DEDUCTION-equivalent into the ledger so the
balance row matches v2 invariants.

Idempotency
-----------
Each leave gets at most one migration ledger row. We detect prior runs by
looking for a `system_v2_migration` reference on the ledger for that
leave id. Subsequent runs are no-ops, and the function is safe to call
from app startup.

What we DO NOT do
-----------------
- We do not touch leaves already in terminal states (CONSUMED / COMPLETED
  / CANCELLED / REJECTED / PARTIALLY_CANCELLED). Those were settled under
  the old rules and don't need re-bookkeeping.
- We do not change `allocated_balance`. Per v2 semantics, `available =
  allocated - used`, so bumping `used` is enough to expose the same
  customer-facing balance.

Returns a summary dict so an admin endpoint / startup hook can log it.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    LeaveBalance, LeaveBalanceLedger, LeaveRequest, LedgerTxn,
)
from app.services.leave_state_machine import LeaveStatus


logger = logging.getLogger(__name__)


# We mark every migration entry with this fixed reference_type so re-runs
# can detect prior work without depending on free-form notes.
MIGRATION_REF_TYPE = "system_v2_migration"


def _already_migrated(db: Session, leave_request_id: str) -> bool:
    return db.query(LeaveBalanceLedger.id).filter(
        LeaveBalanceLedger.reference_type == MIGRATION_REF_TYPE,
        LeaveBalanceLedger.reference_id == leave_request_id,
    ).first() is not None


def _lock_balance(db: Session, employee_id: int, leave_type_id: str,
                  year: int) -> Optional[LeaveBalance]:
    return (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
        .with_for_update()
        .first()
    )


def migrate_to_v2(db: Session, *, dry_run: bool = False) -> dict:
    """Sweep approved leaves and bring their balances into v2 shape.

    For each candidate row we write ONE composite ledger entry with
    transaction_type=LEAVE_DEDUCTION, reference_type=system_v2_migration.
    `used` is bumped by `total_days` (or `total_days - consumed_days` if
    that field is already populated); `reserved` is left untouched
    because under v1 the days were already counted there.

    Set `dry_run=True` to log what would happen without writing.
    """
    candidates = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == LeaveStatus.APPROVED)
        .all()
    )

    summary = {
        "candidates":   len(candidates),
        "already_done": 0,
        "migrated":     0,
        "skipped":      0,
        "errors":       0,
    }

    for req in candidates:
        try:
            if _already_migrated(db, req.id):
                summary["already_done"] += 1
                continue

            # Days to push into `used`. consumed_days defaults to 0 on
            # fresh rows; if a prior partial-consumption ran (legacy
            # scheduler path) it might be set, so respect it.
            days = int(req.total_days) - int(req.consumed_days or 0)
            if days <= 0:
                summary["skipped"] += 1
                continue

            bal = _lock_balance(db, req.employee_id, req.leave_type_id,
                                req.start_date.year)
            if not bal:
                summary["skipped"] += 1
                continue

            before_alloc = int(bal.allocated_balance or 0)
            before_res   = int(bal.reserved or 0)
            before_used  = int(bal.used or 0)

            # v2 shape: `used` carries the deduction, `reserved` is the
            # informational marker. Under v1 the days were already in
            # `reserved` so we only need to bump `used`.
            after_used = before_used + days

            if dry_run:
                summary["migrated"] += 1
                continue

            bal.used = after_used
            bal.current_balance = max(0, before_alloc - after_used)
            bal.row_version = int(bal.row_version or 0) + 1

            entry = LeaveBalanceLedger(
                employee_id=req.employee_id,
                leave_type_id=req.leave_type_id,
                year=req.start_date.year,
                transaction_type=LedgerTxn.LEAVE_DEDUCTION,
                days=days,
                bucket="multi",
                before_allocated=before_alloc, before_reserved=before_res, before_used=before_used,
                after_allocated=before_alloc,  after_reserved=before_res,  after_used=after_used,
                reference_type=MIGRATION_REF_TYPE,
                reference_id=req.id,
                actor_id=None,
                note=("v1→v2 migration: shifted approved-leave deduction from "
                      "scheduler-time to approval-time. `reserved` left in place "
                      "as informational reservation."),
            )
            db.add(entry)
            summary["migrated"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("v2 migration: failed for leave %s", req.id)
            summary["errors"] += 1

    if not dry_run and summary["migrated"]:
        try:
            db.commit()
            logger.info("leave v2 migration committed: %s", summary)
        except Exception:
            db.rollback()
            logger.exception("leave v2 migration commit failed; rolled back")
            summary["errors"] += 1
            summary["migrated"] = 0
    return summary
