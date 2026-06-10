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
    # LOP workflow notifications
    "lop_requested":                        "leave",
    "lop_manager_approved":                 "leave",
    "lop_rejected":                         "leave",
    "lop_approved":                         "leave",
    "lop_payroll_processed":                "leave",
    "lop_pending_manager_approval":         "approvals",
    "lop_pending_hr_approval":              "approvals",
    "lop_approved_hr_info":                 "approvals",
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
    # PMS — Phase 1: Goal-setting workflow
    "pms_goals_assigned":                  "performance",
    "pms_goals_discussed":                 "performance",
    "pms_goals_approved":                  "performance",
    "pms_goals_locked":                    "performance",
    # PMS — Phase 2: Mid-Cycle Review workflow
    "pms_mid_cycle_created":               "performance",
    "pms_progress_submitted":              "performance",
    "pms_manager_reviewed_progress":       "performance",
    "pms_mid_cycle_manager_approved":      "performance",
    "pms_mid_cycle_hr_reviewed":           "performance",
    "pms_mid_cycle_locked":                "performance",
    # PMS — Phase 3: End Cycle Assessment workflow
    "pms_assessment_opened":               "performance",
    "pms_self_assessed":                   "performance",
    "pms_manager_assessed":                "performance",
    "pms_assessment_submitted_to_hr":      "performance",
    "pms_assessment_hr_received":          "performance",
    "pms_assessment_locked":               "performance",
    # PMS — Phase 4: Normalization workflow
    "pms_rating_frozen":                   "performance",
    "pms_hike_generated":                  "performance",
    "pms_hike_approved":                   "performance",
    # PMS — Phase 5: Compensation workflow
    "pms_revision_letter_ready":           "performance",
    "pms_revision_acknowledged":           "performance",
    "pms_cycle_archived":                  "performance",
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
    "pms_goal_assignments":          "performance",
    "pms_mid_cycle_reviews":         "performance",
    "pms_end_cycle_assessments":     "performance",
    "pms_normalization_sessions":    "performance",
    "pms_compensation_revisions":    "performance",
    "pms_cycles":                    "performance",
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
    send_email: bool = False,
    autocommit: bool = False,
) -> Optional[Notification]:
    """Insert one in-app notification. Optionally dispatch an email as best-effort."""
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
        if send_email:
            try:
                from app.services.email_dispatcher import dispatch_for_recipient
                dispatch_for_recipient(db, recipient_id, n.title, n.body)
            except Exception:
                pass
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
    send_email: bool = False,
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
            send_email=send_email,
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
