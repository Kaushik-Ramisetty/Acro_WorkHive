"""Notification helper.

Single entry point for queuing in-app notifications anywhere in the
backend. Writes to the `notifications` table (legacy fields + the
schema's reference_table / reference_id) and optionally fires a mock
email via email_dispatcher. Never raises — notifications must not
break the main flow.

action_url
----------
When a caller omits `action_url`, we derive one from the notification
`type` + `reference_table` so the frontend dropdown / notifications page
can deep-link the user straight to the relevant module. The frontend
also has a fallback mapping for old rows where `action_url` is NULL.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Notification


# ── Type → route fragment (relative; the FE prefixes the role base path) ──
# Keep this in sync with Frontend/src/services/notifications.js::routeFor.
_TYPE_ROUTE_HINTS: dict[str, str] = {
    # Leave
    "leave_applied":                       "leave",
    "leave_approved":                      "leave",
    "leave_rejected":                      "leave",
    "leave_cancelled":                     "leave",
    "leave_cancel_requested":              "leave",
    "leave_cancel_rejected":               "leave",
    "leave_pending_your_approval":         "approvals",
    "leave_cancel_pending_your_approval":  "approvals",
    "leave_escalated":                     "approvals",
    # Attendance
    "attendance_anomaly":                  "attendance",
    "attendance_missed_checkout":          "attendance",
    "regularization_submitted":            "regularization",
    "regularization_approved":             "attendance",
    "regularization_rejected":             "attendance",
    # Timesheet
    "timesheet_submitted":                 "timesheets",
    "timesheet_approved":                  "timesheets",
    "timesheet_rejected":                  "timesheets",
    "timesheet_reminder":                  "timesheets",
    # Comp-off
    "compoff_credited":                    "comp-off",
    "compoff_expiring":                    "comp-off",
    # Onboarding / BGV
    "onboarding_invite":                   "onboarding",
    "onboarding_completed":                "onboarding",
    "bgv_updated":                         "onboarding",
    # Payroll
    "payroll_sync_failed":                 "payroll",
    "payroll_processed":                   "payroll",
    "payslip_ready":                       "payroll",
    # Announcements / Policies
    "announcement":                        "announcements",
    "policy_published":                    "policies",
    # SLA / Admin escalations
    "sla_escalation":                      "approvals",
    "hr_escalation":                       "approvals",
    "compliance_alert":                    "reports",
}

# Reference-table → route fragment (used as a fallback when type is
# unknown but a reference is present).
_REF_ROUTE_HINTS: dict[str, str] = {
    "leave_requests":          "leave",
    "attendance_records":      "attendance",
    "timesheets":              "timesheets",
    "comp_off_credits":        "comp-off",
    "onboarding":              "onboarding",
    "candidates":              "onboarding",
    "payroll_runs":            "payroll",
    "announcements":           "announcements",
    "policies":                "policies",
}


def derive_action_url(
    type_: Optional[str],
    reference_table: Optional[str] = None,
    reference_id: Optional[str] = None,
    leave_request_id: Optional[str] = None,
) -> Optional[str]:
    """Return a relative route fragment (no leading slash, no role prefix).

    The frontend prefixes the active dashboard base (e.g. ``/employee-dashboard``)
    and the chosen segment, so we deliberately return just the page id like
    ``"leave"`` or ``"approvals"``. Callers that need an absolute URL can
    use the type hint as a key.
    """
    if type_ and type_ in _TYPE_ROUTE_HINTS:
        return _TYPE_ROUTE_HINTS[type_]
    if reference_table and reference_table in _REF_ROUTE_HINTS:
        return _REF_ROUTE_HINTS[reference_table]
    # Loose match: anything that starts with "leave_" → leave page.
    if type_:
        for prefix, page in (
            ("leave_",       "leave"),
            ("attendance_",  "attendance"),
            ("timesheet_",   "timesheets"),
            ("compoff_",     "comp-off"),
            ("payroll_",     "payroll"),
            ("onboarding_",  "onboarding"),
        ):
            if type_.startswith(prefix):
                return page
    return None


def notify(
    db: Session,
    *,
    recipient_id: int,
    type_: str,
    title: str,
    body: Optional[str] = None,
    reference_table: Optional[str] = None,
    reference_id: Optional[str] = None,
    leave_request_id: Optional[str] = None,
    action_url: Optional[str] = None,
    meta_json: Optional[str] = None,
    autocommit: bool = False,
) -> Optional[Notification]:
    """Insert one in-app notification. Returns the row (or None on failure)."""
    if not recipient_id:
        return None
    try:
        n = Notification(
            recipient_id=recipient_id,
            type=type_ or "info",
            title=(title or "")[:160] or "Notification",
            body=(body or "")[:500] or None,
            reference_table=reference_table,
            reference_id=str(reference_id) if reference_id is not None else None,
            leave_request_id=leave_request_id,
            action_url=(
                action_url
                or derive_action_url(type_, reference_table, reference_id, leave_request_id)
            ),
            meta_json=meta_json,
            is_read=False,
        )
        db.add(n)
        if autocommit:
            db.commit()
            db.refresh(n)
        return n
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


def notify_many(
    db: Session,
    recipient_ids: list[int],
    *,
    type_: str,
    title: str,
    body: Optional[str] = None,
    reference_table: Optional[str] = None,
    reference_id: Optional[str] = None,
    action_url: Optional[str] = None,
    meta_json: Optional[str] = None,
    autocommit: bool = False,
) -> int:
    """Bulk-notify multiple recipients. Returns number of rows written."""
    n = 0
    for rid in recipient_ids:
        if rid and notify(
            db,
            recipient_id=rid,
            type_=type_,
            title=title,
            body=body,
            reference_table=reference_table,
            reference_id=reference_id,
            action_url=action_url,
            meta_json=meta_json,
            autocommit=False,
        ):
            n += 1
    if autocommit and n:
        try:
            db.commit()
        except Exception:
            db.rollback()
            return 0
    return n
