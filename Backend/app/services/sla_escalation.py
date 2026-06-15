"""SLA escalation engine.

For each pending leave request (status in {'pending', 'cancel_pending'})
that has been waiting at its current stage longer than a threshold, this
service nudges the approver, then skip-level escalates, then forces HR
intervention.

Ladder:
  >= 24h since stage start AND level < 1 -> REMINDER
       sends a fresh notification to the current approver(s), sets
       level=1, alert_at=now. Nothing else changes.

  >= 48h AND level < 2 -> SKIP-LEVEL ESCALATION (manager stage only)
       finds the manager's manager (= "skip-level"). If found, sets
       approver_override_id to that person, notifies them. Level=2.
       For HR-stage requests at 48h, this step is skipped (no skip-level
       exists above HR); we wait for the 72h trigger to broaden the alert.

  >= 72h AND level < 3 -> HR INTERVENTION
       forces next_approver_role='hr', clears approver_override_id,
       notifies every active admin (HR) user. Level=3.

The engine is idempotent: running it twice within the same window does
nothing on the second run because each level is only advanced once.

Time-in-stage is computed from existing timestamps:
  - manager stage         : created_at
  - hr stage              : manager_approved_at (or created_at if no manager stage)
  - cancel_pending stage  : cancel_requested_at
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Employee, LeaveRequest, Notification
from app.services.email_dispatcher import dispatch_for_recipient
from utils.time_utils import now_utc


SLA_REMINDER_HOURS = 24
SLA_SKIP_LEVEL_HOURS = 48
SLA_HR_INTERVENTION_HOURS = 72


def _utcnow() -> datetime:
    return now_utc()


def _stage_started_at(req: LeaveRequest) -> Optional[datetime]:
    """Return the timestamp at which the *current* approval stage began."""
    if req.status == "cancel_pending":
        return req.cancel_requested_at or req.created_at
    if req.status != "pending":
        return None
    if req.next_approver_role == "hr":
        return req.manager_approved_at or req.created_at
    if req.next_approver_role == "manager":
        return req.created_at
    return None


def _notify(db: Session, recipient_id: int, type_: str, title: str,
            body: str, leave_request_id: Optional[str]) -> None:
    db.add(Notification(
        recipient_id=recipient_id,
        type=type_,
        title=title,
        body=body,
        leave_request_id=leave_request_id,
    ))
    try:
        dispatch_for_recipient(db, recipient_id, title, body)
    except Exception:
        pass


def _current_approver_ids(db: Session, req: LeaveRequest) -> list[int]:
    """All employee ids that can act on this request right now."""
    # Local import to avoid circular: leave_engine imports DelegateAssignment too.
    from app.services.leave_engine import _active_delegate_id, _hr_user_ids

    ids: set[int] = set()
    if req.approver_override_id:
        ids.add(req.approver_override_id)
    if req.next_approver_role == "manager" and req.employee:
        mgr_id = req.employee.reporting_manager_id
        if mgr_id:
            ids.add(mgr_id)
            d = _active_delegate_id(db, mgr_id)
            if d:
                ids.add(d)
    elif req.next_approver_role == "hr":
        ids.update(_hr_user_ids(db))
    ids.discard(req.employee_id)
    return sorted(ids)


def _skip_level_manager_id(db: Session, req: LeaveRequest) -> Optional[int]:
    """Manager's manager — the skip-level approver."""
    if not req.employee or not req.employee.reporting_manager_id:
        return None
    mgr = db.get(Employee, req.employee.reporting_manager_id)
    if not mgr:
        return None
    return mgr.reporting_manager_id


def run_sla_sweep(db: Session) -> dict:
    """Walk all pending/cancel_pending requests and apply the escalation
    ladder where due. Returns a summary dict for the scheduler logs."""
    from app.services.leave_engine import _hr_user_ids  # local: avoid cycle

    now = _utcnow()
    summary = {"examined": 0, "reminded": 0, "escalated": 0, "hr_intervention": 0}

    requests = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status.in_(["pending", "cancel_pending"]))
        .all()
    )

    for req in requests:
        summary["examined"] += 1
        started = _stage_started_at(req)
        if not started:
            continue
        age_hours = (now - started).total_seconds() / 3600.0
        level = int(req.sla_escalation_level or 0)

        # 72h: HR intervention
        if age_hours >= SLA_HR_INTERVENTION_HOURS and level < 3:
            req.next_approver_role = "hr"
            req.approver_override_id = None
            req.sla_escalation_level = 3
            req.sla_last_alert_at = now
            for hr_id in _hr_user_ids(db):
                if hr_id == req.employee_id:
                    continue
                _notify(
                    db, hr_id, "leave_sla_hr_intervention",
                    title="HR intervention: leave SLA breached",
                    body=(
                        f"Leave request {req.id} from "
                        f"{req.employee.full_name if req.employee else '?'} has been "
                        f"pending for {int(age_hours)}h. Routed to HR for action."
                    ),
                    leave_request_id=req.id,
                )
            summary["hr_intervention"] += 1
            continue

        # 48h: skip-level escalation (only when still at manager stage)
        if (
            age_hours >= SLA_SKIP_LEVEL_HOURS
            and level < 2
            and req.status == "pending"
            and req.next_approver_role == "manager"
        ):
            skip = _skip_level_manager_id(db, req)
            if skip and skip != req.employee_id:
                req.approver_override_id = skip
                req.sla_escalation_level = 2
                req.sla_last_alert_at = now
                _notify(
                    db, skip, "leave_sla_skip_level",
                    title="Escalated leave request needs your approval",
                    body=(
                        f"{req.employee.full_name if req.employee else '?'}'s leave "
                        f"({req.start_date} -> {req.end_date}) has been waiting "
                        f"{int(age_hours)}h. Escalated to you for skip-level action."
                    ),
                    leave_request_id=req.id,
                )
                summary["escalated"] += 1
                continue
            # No skip-level available: fall through to reminder-level handling
            # below if not yet reminded.

        # 24h: reminder
        if age_hours >= SLA_REMINDER_HOURS and level < 1:
            for rid in _current_approver_ids(db, req):
                _notify(
                    db, rid, "leave_sla_reminder",
                    title="Reminder: leave request awaiting your action",
                    body=(
                        f"Leave request {req.id} has been waiting "
                        f"{int(age_hours)}h. Please review."
                    ),
                    leave_request_id=req.id,
                )
            req.sla_escalation_level = max(level, 1)
            req.sla_last_alert_at = now
            summary["reminded"] += 1

    db.commit()
    return summary
