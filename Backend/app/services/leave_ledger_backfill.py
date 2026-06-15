"""One-shot startup hooks that bring the legacy data shape into the
Phase 5A model. Safe to run on every boot — every step checks state
before mutating and exits cleanly when there's nothing to do.

Two responsibilities:

  1. `seed_allocated_from_opening()`
     Copies the legacy `opening_balance` into the new `allocated_balance`
     column when allocated_balance is still at its default zero. Done as
     a single UPDATE for speed; no ledger entries are written because
     this is a representation change, not a balance mutation.

  2. `auto_close_hr_stage_leaves()`
     Picks up requests still sitting at `status='pending'`,
     `next_approver_role='hr'` from before HR was removed as an approver,
     and transitions them straight to 'approved' under the synthetic
     'system' actor. Reserved balance is written through the ledger so
     the new audit trail is consistent. Already-approved or terminal
     rows are skipped.

Both functions are idempotent and run inside their own short transaction.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import (
    LeaveBalance, LeaveRequest, LedgerTxn, Notification,
)
from app.services.leave_ledger import post_ledger_entry, adjust_pending
from utils.time_utils import now_utc


logger = logging.getLogger(__name__)


def seed_allocated_from_opening(db: Session) -> int:
    """Copy opening_balance -> allocated_balance once on rollout.

    Returns the row count updated. The WHERE clause ensures we only touch
    rows where allocated_balance is still 0 AND opening_balance is > 0,
    so re-running is a no-op."""
    stmt = (
        update(LeaveBalance)
        .where(
            LeaveBalance.allocated_balance == 0,
            LeaveBalance.opening_balance > 0,
        )
        .values(allocated_balance=LeaveBalance.opening_balance)
    )
    result = db.execute(stmt)
    db.commit()
    n = result.rowcount or 0
    if n:
        logger.info("Phase 5A backfill: seeded allocated_balance on %d row(s)", n)
    return n


def auto_close_hr_stage_leaves(db: Session) -> int:
    """Transition in-flight HR-stage requests to 'approved' under system actor.

    Per the deployment decision: the HR stage is removed, and any request
    that was sitting at next_approver_role='hr' had already been approved
    by the manager. The fair interpretation is to advance them to approved
    (rather than push them back to manager re-approval). A ledger RESERVE
    is posted so balance accounting stays correct.
    """
    rows = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.status == "pending",
            LeaveRequest.next_approver_role == "hr",
        )
        .all()
    )
    if not rows:
        return 0

    now = now_utc()
    closed = 0
    for req in rows:
        # Release pending if the row was counted in pending_balance.
        try:
            adjust_pending(db, req.employee_id, req.leave_type_id, -req.total_days,
                           year=req.start_date.year)
        except Exception:
            # Pending column may be 0 already for legacy rows.
            pass
        try:
            post_ledger_entry(
                db,
                employee_id=req.employee_id,
                leave_type_id=req.leave_type_id,
                transaction_type=LedgerTxn.RESERVE,
                days=req.total_days,
                reference_type="leave_request",
                reference_id=req.id,
                actor=None,
                note="Phase 5A backfill: HR stage removed; auto-approved",
                year=req.start_date.year,
            )
        except Exception as exc:
            logger.warning("Backfill could not RESERVE for %s: %s", req.id, exc)
            continue

        req.status = "approved"
        req.next_approver_role = None
        req.approved_by = req.manager_approved_by or req.approved_by
        req.approved_at = req.manager_approved_at or now
        # Audit it via the existing leave_audit_logs table.
        from app.models import LeaveAuditLog
        db.add(LeaveAuditLog(
            leave_request_id=req.id,
            action="auto_approved_hr_stage_removed",
            actor_id=None,
            from_status="pending",
            to_status="approved",
            note="HR approval stage removed; auto-approved by system on rollout.",
        ))
        # Notify the employee — they last heard "awaiting HR approval".
        db.add(Notification(
            recipient_id=req.employee_id,
            type="leave_approved",
            title="Leave approved (policy update)",
            body=(
                "HR approval is no longer required. Your manager-approved "
                f"leave ({req.start_date} -> {req.end_date}) has been finalized."
            ),
            leave_request_id=req.id,
        ))
        closed += 1

    db.commit()
    if closed:
        logger.info("Phase 5A backfill: auto-closed %d HR-stage leave(s)", closed)
    return closed


def run_phase5a_startup_hooks(db: Session) -> dict:
    """Combined entry point called from app startup."""
    seeded = seed_allocated_from_opening(db)
    closed = auto_close_hr_stage_leaves(db)
    return {"allocated_seeded": seeded, "hr_stage_auto_closed": closed}
