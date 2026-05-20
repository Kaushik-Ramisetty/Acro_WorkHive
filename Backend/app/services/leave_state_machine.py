"""Strict workflow state machine for LeaveRequest.

Phase 5A removes the HR approval stage. The legal transitions are now:

    draft           -- submit          --> pending
    pending         -- approve_manager --> approved      (manager OR delegate; admins as override)
    pending         -- reject          --> rejected
    pending         -- cancel          --> cancelled     (owner withdraws before approval)
    approved        -- cancel          --> cancel_pending
    approved        -- consume         --> consumed      (scheduler; balance moves used)
    approved        -- reverse         --> cancelled     (WoL validation says "worked on leave")
    cancel_pending  -- approve_cancel  --> cancelled     (manager approval of cancellation)
    cancel_pending  -- reject_cancel   --> approved
    rejected | cancelled | consumed   -- (no further transitions; terminal)

This module is intentionally string-keyed so the existing String(20)
`status` column doesn't need a data migration. The conceptual
"PENDING_MANAGER" requested in the brief maps to the historical
lowercase string `'pending'`; the chain has a single approver now
(manager) so there's no ambiguity any more.

Usage:
    transition(req, action='approve_manager', actor=user)
        -> mutates req.status and bookkeeping fields, raises
           InvalidTransition on a disallowed move.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.models import Employee, LeaveRequest


# String constants — single source of truth used by engine + serializers.
class LeaveStatus:
    DRAFT               = "draft"
    PENDING             = "pending"          # PENDING_MANAGER conceptually
    APPROVED            = "approved"
    REJECTED            = "rejected"
    CANCEL_PENDING      = "cancel_pending"
    CANCELLED           = "cancelled"
    CONSUMED            = "consumed"         # legacy alias of COMPLETED
    COMPLETED           = "completed"        # Hybrid v2 — scheduler outcome
    PARTIALLY_CANCELLED = "partially_cancelled"  # Hybrid v2 — partial future cancel
    CLOSED              = "closed"           # reserved for future encashment/forfeit flows

    TERMINAL = frozenset({REJECTED, CANCELLED, CONSUMED, COMPLETED, PARTIALLY_CANCELLED, CLOSED})
    ACTIVE   = frozenset({DRAFT, PENDING, APPROVED, CANCEL_PENDING})


# Allowed actions per source status. Maps to a target status.
_ALLOWED: dict[tuple[str, str], str] = {
    (LeaveStatus.DRAFT,          "submit"):           LeaveStatus.PENDING,
    (LeaveStatus.DRAFT,          "discard"):          "__DELETED__",

    (LeaveStatus.PENDING,        "approve_manager"):  LeaveStatus.APPROVED,
    (LeaveStatus.PENDING,        "reject"):           LeaveStatus.REJECTED,
    (LeaveStatus.PENDING,        "cancel"):           LeaveStatus.CANCELLED,

    (LeaveStatus.APPROVED,       "cancel"):           LeaveStatus.CANCEL_PENDING,
    (LeaveStatus.APPROVED,       "consume"):          LeaveStatus.CONSUMED,        # legacy
    (LeaveStatus.APPROVED,       "complete"):         LeaveStatus.COMPLETED,        # Hybrid v2 — scheduler
    (LeaveStatus.APPROVED,       "reverse"):          LeaveStatus.CANCELLED,

    (LeaveStatus.CANCEL_PENDING, "approve_cancel"):       LeaveStatus.CANCELLED,
    (LeaveStatus.CANCEL_PENDING, "approve_partial_cancel"): LeaveStatus.PARTIALLY_CANCELLED,
    (LeaveStatus.CANCEL_PENDING, "reject_cancel"):        LeaveStatus.APPROVED,
}


class InvalidTransition(Exception):
    def __init__(self, current: str, action: str, msg: Optional[str] = None):
        self.current = current
        self.action = action
        super().__init__(
            msg or f"Cannot perform '{action}' on a leave in status '{current}'."
        )


@dataclass
class TransitionResult:
    from_status: str
    to_status: str
    action: str


def transition(req: LeaveRequest, action: str, actor: Optional[Employee] = None) -> TransitionResult:
    """Validate + apply a status change. Caller is responsible for the
    side effects (ledger writes, notifications, audit). This function
    only touches `req.status` and `req.next_approver_role`.
    """
    current = req.status or ""
    key = (current, action)
    if key not in _ALLOWED:
        raise InvalidTransition(current, action)

    target = _ALLOWED[key]
    if target == "__DELETED__":
        # Sentinel used for discard — caller deletes the row.
        return TransitionResult(current, target, action)

    req.status = target

    # Bookkeeping for `next_approver_role`:
    #   pending          -> 'manager' (single-stage approval after HR removal)
    #   cancel_pending   -> 'manager' (manager approves cancellation, HR notified)
    #   anything else    -> None
    if target == LeaveStatus.PENDING or target == LeaveStatus.CANCEL_PENDING:
        req.next_approver_role = "manager"
    else:
        req.next_approver_role = None

    return TransitionResult(current, target, action)


def can_transition(current: str, action: str) -> bool:
    return (current, action) in _ALLOWED


def assert_active(req: LeaveRequest) -> None:
    if req.status in LeaveStatus.TERMINAL:
        raise InvalidTransition(
            req.status, "any",
            msg=f"Leave {req.id} is in terminal status '{req.status}'.",
        )
