"""PMS email notifications — Phase 1 & 2.

All public functions are non-fatal: wrapped in try/except so a broken
SMTP config or missing employee email never crashes the main workflow.
Reuses email_dispatcher for actual delivery (SMTP or console fallback).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.services.email_dispatcher import (
    dispatch_html_for_recipient,
    dispatch_html_for_many,
)

logger = logging.getLogger("hrms.pms_email")

# ── Shared brand colours (match OTP email) ───────────────────────────────────
_HDR_BG     = "#2d3ec9"       # Indigo header
_HDR_LIGHT  = "#c7d2fe"       # Header sub-label
_BODY_BG    = "#f2f4f7"
_CARD_BG    = "#ffffff"
_TEXT_PRI   = "#1e293b"
_TEXT_SEC   = "#475569"
_TEXT_MUTED = "#94a3b8"


def _html(
    preview_text: str,
    greeting: str,
    lead: str,
    detail_rows: List[tuple],   # [(label, value), ...]
    cta_label: str,
    note: Optional[str] = None,
) -> str:
    """Build an Outlook-bulletproof HTML email matching the HRMS brand."""
    rows_html = "".join(
        f'<tr>'
        f'<td style="padding:4px 0;color:{_TEXT_MUTED};font-size:12px;font-family:Arial,Helvetica,sans-serif;white-space:nowrap;">{lbl}</td>'
        f'<td style="padding:4px 0 4px 12px;color:{_TEXT_PRI};font-size:12px;font-family:Arial,Helvetica,sans-serif;font-weight:600;">{val}</td>'
        f'</tr>'
        for lbl, val in detail_rows
    )
    note_html = (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top:20px;">'
        f'<tr><td bgcolor="#fffbeb" style="background-color:#fffbeb;border-left:4px solid #f59e0b;border-radius:4px;padding:12px 16px;">'
        f'<p style="margin:0;color:#92400e;font-size:13px;line-height:18px;font-family:Arial,Helvetica,sans-serif;">{note}</p>'
        f'</td></tr></table>'
        if note else ""
    )
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>WorkHive HRMS</title>
<!--[if mso]>
<style type="text/css">table{{border-collapse:collapse;}}td{{font-family:Arial,sans-serif;}}</style>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:{_BODY_BG};font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;font-size:1px;color:{_BODY_BG};line-height:1px;max-height:0;overflow:hidden;">{preview_text}</div>
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{_BODY_BG};">
    <tr><td align="center" style="padding:40px 16px;">
      <!--[if mso]><table role="presentation" border="0" cellpadding="0" cellspacing="0" width="480" align="center"><tr><td><![endif]-->
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"
             style="max-width:480px;background-color:{_CARD_BG};border:1px solid #e2e6ea;border-radius:10px;">
        <!-- HEADER -->
        <tr>
          <td align="center" bgcolor="{_HDR_BG}" style="background-color:{_HDR_BG};padding:24px 32px 20px;border-radius:10px 10px 0 0;">
            <p style="margin:0 0 4px;color:{_HDR_LIGHT};font-size:10px;font-weight:bold;letter-spacing:3px;text-transform:uppercase;font-family:Arial,Helvetica,sans-serif;">
              Acronotics HRMS
            </p>
            <p style="margin:0;color:#ffffff;font-size:20px;font-weight:bold;font-family:Arial,Helvetica,sans-serif;">
              Performance Management
            </p>
          </td>
        </tr>
        <!-- BODY -->
        <tr>
          <td style="padding:28px 32px 20px;font-family:Arial,Helvetica,sans-serif;">
            <p style="margin:0 0 12px;color:{_TEXT_PRI};font-size:15px;line-height:22px;">{greeting}</p>
            <p style="margin:0 0 20px;color:{_TEXT_SEC};font-size:14px;line-height:22px;">{lead}</p>
            <!-- Detail table -->
            <table role="presentation" border="0" cellpadding="0" cellspacing="0"
                   style="width:100%;background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;">
              <tbody>{rows_html}</tbody>
            </table>
            {note_html}
            <!-- CTA hint -->
            <p style="margin:24px 0 0;color:{_TEXT_MUTED};font-size:13px;line-height:18px;font-family:Arial,Helvetica,sans-serif;">
              Log in to <strong>WorkHive HRMS</strong> → Performance to {cta_label}.
            </p>
          </td>
        </tr>
        <!-- FOOTER -->
        <tr>
          <td align="center" bgcolor="#f8fafc" style="background-color:#f8fafc;border-top:1px solid #e2e8f0;border-radius:0 0 10px 10px;padding:14px 32px;">
            <p style="margin:0;color:{_TEXT_MUTED};font-size:12px;font-family:Arial,Helvetica,sans-serif;">
              &copy; WorkHive HRMS &bull; Acronotics Internal System
            </p>
          </td>
        </tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>"""


def _plain(greeting: str, lead: str, detail_rows: List[tuple], cta_label: str, note: Optional[str] = None) -> str:
    lines = [greeting, "", lead, ""]
    for lbl, val in detail_rows:
        lines.append(f"  {lbl}: {val}")
    if note:
        lines.extend(["", f"Note: {note}"])
    lines.extend(["", f"Log in to WorkHive HRMS → Performance to {cta_label}.", "", "— Acronotics HR Team"])
    return "\n".join(lines)


def _send(
    db: Session,
    recipient_id: int,
    subject: str,
    greeting: str,
    lead: str,
    detail_rows: List[tuple],
    cta_label: str,
    preview_text: str = "",
    note: Optional[str] = None,
) -> None:
    plain = _plain(greeting, lead, detail_rows, cta_label, note)
    html  = _html(preview_text or lead[:80], greeting, lead, detail_rows, cta_label, note)
    try:
        dispatch_html_for_recipient(db, recipient_id, subject, plain, html)
    except Exception as exc:
        logger.warning("PMS email to employee #%s failed: %s", recipient_id, exc)


def _send_many(
    db: Session,
    recipient_ids: List[int],
    subject: str,
    greeting: str,
    lead: str,
    detail_rows: List[tuple],
    cta_label: str,
    preview_text: str = "",
    note: Optional[str] = None,
) -> None:
    plain = _plain(greeting, lead, detail_rows, cta_label, note)
    html  = _html(preview_text or lead[:80], greeting, lead, detail_rows, cta_label, note)
    try:
        dispatch_html_for_many(db, recipient_ids, subject, plain, html)
    except Exception as exc:
        logger.warning("PMS bulk email failed: %s", exc)


# ── Phase 1 event emails ──────────────────────────────────────────────────────


def email_goals_assigned(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_id: Optional[int],
    period: Optional[str],
    template_name: Optional[str],
    due_date=None,  # CHANGE 9: Optional[datetime]
) -> None:
    """Goal sheet sent by HR → email employee + manager."""
    from datetime import datetime as _dt
    period_label = period or "—"
    due_label = due_date.strftime("%d %b %Y") if due_date else "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Your Goal Sheet for {period_label} has been shared",
            greeting=f"Hi {employee_name},",
            lead="HR has shared your goal sheet for this review period. Please review the goals and start a discussion with your manager.",
            detail_rows=[
                ("Phase", "Goal Setting"),
                ("Review Period", period_label),
                ("Template", template_name or "—"),
                ("Action Required", "Discuss with your manager"),
                ("Due Date", due_label),
            ],
            cta_label="view and discuss your goals",
            preview_text=f"Your {period_label} goal sheet is ready for review.",
        )
    except Exception as exc:
        logger.warning("goals_assigned email to employee #%s failed: %s", employee_id, exc)

    if manager_id:
        try:
            _send(
                db, manager_id,
                subject=f"[WorkHive PMS] Goals sent to {employee_name}",
                greeting="Hi,",
                lead=f"HR has assigned goals to {employee_name}. Please open the team goals queue and start the discussion.",
                detail_rows=[
                    ("Phase", "Goal Setting"),
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Template", template_name or "—"),
                    ("Action Required", "Open discussion"),
                    ("Due Date", due_label),
                ],
                cta_label="view team goals and open discussion",
                preview_text=f"Goals assigned to {employee_name} for {period_label}.",
            )
        except Exception as exc:
            logger.warning("goals_assigned email to manager #%s failed: %s", manager_id, exc)


def email_discussion_started(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_name: str,
    period: Optional[str],
) -> None:
    """Manager opens discussion → email employee."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Goal Discussion Started — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"Your manager {manager_name} has opened a discussion on your goal sheet. Please review any updates and confirm your goals.",
            detail_rows=[
                ("Review Period", period_label),
                ("Manager", manager_name),
                ("Next Step", "Review goals and confirm acceptance"),
            ],
            cta_label="view the discussion and confirm your goals",
            preview_text=f"{manager_name} started goal discussion for {period_label}.",
        )
    except Exception as exc:
        logger.warning("discussion_started email to employee #%s failed: %s", employee_id, exc)


def email_employee_confirmed(
    db: Session,
    *,
    manager_id: Optional[int],
    employee_name: str,
    period: Optional[str],
) -> None:
    """Employee confirms goals → email manager."""
    if not manager_id:
        return
    period_label = period or "—"
    try:
        _send(
            db, manager_id,
            subject=f"[WorkHive PMS] {employee_name} Confirmed Goals — {period_label}",
            greeting="Hi,",
            lead=f"{employee_name} has confirmed their goal sheet. Please review and give your final approval.",
            detail_rows=[
                ("Employee", employee_name),
                ("Review Period", period_label),
                ("Status", "Employee Confirmed — awaiting manager approval"),
            ],
            cta_label="approve the goal sheet",
            preview_text=f"{employee_name} confirmed goals for {period_label}.",
        )
    except Exception as exc:
        logger.warning("employee_confirmed email to manager #%s failed: %s", manager_id, exc)


def email_manager_approved(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_name: str,
    period: Optional[str],
    hr_ids: List[int],
) -> None:
    """Manager approves → email employee + HR pool."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Manager Approved Your Goals — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"Your manager {manager_name} has approved your goal sheet. It is now with HR for final review.",
            detail_rows=[
                ("Review Period", period_label),
                ("Approved By", manager_name),
                ("Next Step", "HR final review"),
            ],
            cta_label="view goal status",
            preview_text=f"Manager approved your goals for {period_label}.",
        )
    except Exception as exc:
        logger.warning("manager_approved email to employee #%s failed: %s", employee_id, exc)

    if hr_ids:
        try:
            _send_many(
                db, hr_ids,
                subject=f"[WorkHive PMS] Action Required: Review Goals for {employee_name}",
                greeting="Hi HR Team,",
                lead=f"Manager has approved the goal sheet for {employee_name}. Please open the HR review queue.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Approved By", manager_name),
                    ("Next Step", "HR review and lock"),
                ],
                cta_label="review and lock goal sheets",
                preview_text=f"Manager approved goals for {employee_name} — HR action needed.",
            )
        except Exception as exc:
            logger.warning("manager_approved email to HR pool failed: %s", exc)


def email_hr_reviewed(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    period: Optional[str],
) -> None:
    """HR marks reviewed → email employee."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] HR Reviewed Your Goals — {period_label}",
            greeting=f"Hi {employee_name},",
            lead="HR has reviewed your goal sheet. Your goals will be locked shortly.",
            detail_rows=[
                ("Review Period", period_label),
                ("Status", "HR Reviewed — pending lock"),
            ],
            cta_label="view your goal sheet",
            preview_text=f"HR reviewed your goals for {period_label}.",
        )
    except Exception as exc:
        logger.warning("hr_reviewed email to employee #%s failed: %s", employee_id, exc)


def email_goals_locked(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_id: Optional[int],
    period: Optional[str],
) -> None:
    """HR locks goals → email employee + manager."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Your Goals Are Now Locked — {period_label}",
            greeting=f"Hi {employee_name},",
            lead="Your goal sheet has been locked by HR. Goals are now finalised and cannot be edited.",
            detail_rows=[
                ("Review Period", period_label),
                ("Status", "Goals Locked"),
            ],
            cta_label="view your locked goal sheet",
            note="Contact HR if you need to make changes after locking.",
            preview_text=f"Your goals for {period_label} are now locked.",
        )
    except Exception as exc:
        logger.warning("goals_locked email to employee #%s failed: %s", employee_id, exc)

    if manager_id:
        try:
            _send(
                db, manager_id,
                subject=f"[WorkHive PMS] Goals Locked for {employee_name} — {period_label}",
                greeting="Hi,",
                lead=f"HR has locked the goal sheet for {employee_name}. The goals are finalised.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Status", "Goals Locked"),
                ],
                cta_label="view the locked goal sheet",
                preview_text=f"Goals locked for {employee_name}.",
            )
        except Exception as exc:
            logger.warning("goals_locked email to manager #%s failed: %s", manager_id, exc)


# ── Phase 2: Mid-Cycle Review email events ────────────────────────────────────


def email_mid_cycle_created(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
    due_date=None,  # CHANGE 9: Optional[datetime]
) -> None:
    """HR creates mid-cycle review → email employee."""
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    due_label    = due_date.strftime("%d %b %Y") if due_date else "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] {cycle_label} Review Opened — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"HR has opened your {cycle_label} performance review. Please update your progress on each KPI and submit for manager review.",
            detail_rows=[
                ("Phase", "Mid Cycle Review"),
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Action Required", "Update progress and submit"),
                ("Due Date", due_label),
            ],
            cta_label="update your mid-cycle progress",
            preview_text=f"{cycle_label} review opened for {period_label}.",
        )
    except Exception as exc:
        logger.warning("mid_cycle_created email to employee #%s failed: %s", employee_id, exc)


def email_progress_submitted(
    db: Session,
    *,
    manager_id: Optional[int],
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """Employee submits progress → email manager."""
    if not manager_id:
        return
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    try:
        _send(
            db, manager_id,
            subject=f"[WorkHive PMS] {employee_name} Submitted {cycle_label} Progress",
            greeting="Hi,",
            lead=f"{employee_name} has submitted their {cycle_label} progress update. Please review and provide your feedback.",
            detail_rows=[
                ("Employee", employee_name),
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Next Step", "Review and provide feedback"),
            ],
            cta_label="review mid-cycle progress",
            preview_text=f"{employee_name} submitted {cycle_label} progress for {period_label}.",
        )
    except Exception as exc:
        logger.warning("progress_submitted email to manager #%s failed: %s", manager_id, exc)


def email_manager_reviewed_mid_cycle(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """Manager reviews mid-cycle → email employee."""
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Manager Reviewed Your {cycle_label} Progress",
            greeting=f"Hi {employee_name},",
            lead=f"Your manager {manager_name} has reviewed your {cycle_label} progress. Check their feedback in the Performance section.",
            detail_rows=[
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Reviewed By", manager_name),
            ],
            cta_label="view manager feedback",
            preview_text=f"Manager reviewed your {cycle_label} progress.",
        )
    except Exception as exc:
        logger.warning("manager_reviewed_mid_cycle email to employee #%s failed: %s", employee_id, exc)


def email_mid_cycle_manager_approved(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
    hr_ids: List[int],
) -> None:
    """Manager approves mid-cycle → email employee + HR pool."""
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] {cycle_label} Review Approved by Manager",
            greeting=f"Hi {employee_name},",
            lead=f"Your manager {manager_name} has approved your {cycle_label} review. It is now with HR.",
            detail_rows=[
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Approved By", manager_name),
            ],
            cta_label="view review status",
            preview_text=f"Manager approved {cycle_label} review for {period_label}.",
        )
    except Exception as exc:
        logger.warning("mid_cycle_manager_approved email to employee #%s failed: %s", employee_id, exc)

    if hr_ids:
        try:
            _send_many(
                db, hr_ids,
                subject=f"[WorkHive PMS] HR Action: {employee_name} {cycle_label} Review Approved",
                greeting="Hi HR Team,",
                lead=f"The {cycle_label} review for {employee_name} has been manager-approved. Please review and lock.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Review Cycle", cycle_label),
                    ("Next Step", "HR review and lock"),
                ],
                cta_label="review and lock mid-cycle",
                preview_text=f"{cycle_label} review ready for HR — {employee_name}.",
            )
        except Exception as exc:
            logger.warning("mid_cycle_manager_approved email to HR pool failed: %s", exc)


def email_mid_cycle_hr_reviewed(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """HR reviews mid-cycle → email employee."""
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] HR Reviewed Your {cycle_label} Progress",
            greeting=f"Hi {employee_name},",
            lead=f"HR has reviewed your {cycle_label} progress. The review will be locked shortly.",
            detail_rows=[
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Status", "HR Reviewed — pending lock"),
            ],
            cta_label="view review status",
            preview_text=f"HR reviewed your {cycle_label} progress.",
        )
    except Exception as exc:
        logger.warning("mid_cycle_hr_reviewed email to employee #%s failed: %s", employee_id, exc)


def email_mid_cycle_locked(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_id: Optional[int],
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """HR locks mid-cycle → email employee + manager."""
    period_label = period or "—"
    cycle_label  = cycle_period or "Mid-Cycle"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] {cycle_label} Review Locked — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"Your {cycle_label} review has been locked by HR. Progress records are finalised.",
            detail_rows=[
                ("Review Period", period_label),
                ("Review Cycle", cycle_label),
                ("Status", "Mid-Cycle Locked"),
            ],
            cta_label="view your locked review",
            preview_text=f"{cycle_label} review locked for {period_label}.",
        )
    except Exception as exc:
        logger.warning("mid_cycle_locked email to employee #%s failed: %s", employee_id, exc)

    if manager_id:
        try:
            _send(
                db, manager_id,
                subject=f"[WorkHive PMS] {cycle_label} Review Locked for {employee_name}",
                greeting="Hi,",
                lead=f"The {cycle_label} review for {employee_name} has been locked by HR.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Review Cycle", cycle_label),
                    ("Status", "Mid-Cycle Locked"),
                ],
                cta_label="view locked review",
                preview_text=f"{cycle_label} locked for {employee_name}.",
            )
        except Exception as exc:
            logger.warning("mid_cycle_locked email to manager #%s failed: %s", manager_id, exc)


# ── Phase 3: End Cycle Assessment email events ────────────────────────────────


def email_assessment_opened(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
    due_date=None,  # CHANGE 9: Optional[datetime]
) -> None:
    """HR opens end-cycle assessment → email employee."""
    period_label = period or "—"
    cycle_label  = cycle_period or period_label
    due_label    = due_date.strftime("%d %b %Y") if due_date else "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] End-Cycle Assessment Opened — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"HR has opened your end-of-cycle performance assessment. Please complete your self-assessment, rate each KRA and competency, and submit for manager review.",
            detail_rows=[
                ("Phase", "End Cycle Assessment"),
                ("Review Period", period_label),
                ("Cycle", cycle_label),
                ("Action Required", "Complete your self-assessment"),
                ("Due Date", due_label),
            ],
            cta_label="complete your self-assessment",
            preview_text=f"End-cycle assessment opened for {period_label}.",
        )
    except Exception as exc:
        logger.warning("assessment_opened email to employee #%s failed: %s", employee_id, exc)


def email_self_assessment_submitted(
    db: Session,
    *,
    manager_id: Optional[int],
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """Employee submits self-assessment → email manager."""
    if not manager_id:
        return
    period_label = period or "—"
    try:
        _send(
            db, manager_id,
            subject=f"[WorkHive PMS] {employee_name} Submitted Self-Assessment — {period_label}",
            greeting="Hi,",
            lead=f"{employee_name} has completed their self-assessment for {period_label}. Please review and submit your manager assessment.",
            detail_rows=[
                ("Employee", employee_name),
                ("Review Period", period_label),
                ("Next Step", "Complete your manager assessment"),
            ],
            cta_label="open the end-cycle assessment",
            preview_text=f"{employee_name} submitted self-assessment for {period_label}.",
        )
    except Exception as exc:
        logger.warning("self_assessment_submitted email to manager #%s failed: %s", manager_id, exc)


def email_manager_assessment_submitted(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """Manager completes assessment → email employee."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Manager Completed Your End-Cycle Assessment — {period_label}",
            greeting=f"Hi {employee_name},",
            lead=f"Your manager {manager_name} has completed your end-of-cycle assessment. View their ratings and feedback in the Performance section.",
            detail_rows=[
                ("Review Period", period_label),
                ("Assessed By", manager_name),
            ],
            cta_label="view your end-cycle assessment",
            preview_text=f"Manager completed your end-cycle assessment for {period_label}.",
        )
    except Exception as exc:
        logger.warning("manager_assessment_submitted email to employee #%s failed: %s", employee_id, exc)


def email_assessment_submitted_to_hr(
    db: Session,
    *,
    employee_name: str,
    period: Optional[str],
    cycle_period: Optional[str],
    hr_ids: List[int],
) -> None:
    """Assessment submitted to HR → email HR pool."""
    if not hr_ids:
        return
    period_label = period or "—"
    try:
        _send_many(
            db, hr_ids,
            subject=f"[WorkHive PMS] Action Required: End-Cycle Assessment for {employee_name}",
            greeting="Hi HR Team,",
            lead=f"The end-of-cycle assessment for {employee_name} has been submitted for HR review.",
            detail_rows=[
                ("Employee", employee_name),
                ("Review Period", period_label),
                ("Next Step", "Receive and lock the assessment"),
            ],
            cta_label="open the HR assessment queue",
            preview_text=f"End-cycle assessment submitted — {employee_name}.",
        )
    except Exception as exc:
        logger.warning("assessment_submitted_to_hr email to HR pool failed: %s", exc)


def email_assessment_hr_received(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_id: Optional[int],
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """HR receives assessment → email employee + manager."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] HR Received Your End-Cycle Assessment — {period_label}",
            greeting=f"Hi {employee_name},",
            lead="HR has received your end-of-cycle assessment. It will be reviewed and finalised shortly.",
            detail_rows=[
                ("Review Period", period_label),
                ("Status", "HR Received"),
            ],
            cta_label="view your assessment status",
            preview_text=f"HR received your end-cycle assessment for {period_label}.",
        )
    except Exception as exc:
        logger.warning("assessment_hr_received email to employee #%s failed: %s", employee_id, exc)

    if manager_id:
        try:
            _send(
                db, manager_id,
                subject=f"[WorkHive PMS] HR Received End-Cycle Assessment for {employee_name}",
                greeting="Hi,",
                lead=f"HR has received the end-of-cycle assessment for {employee_name}.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Status", "HR Received"),
                ],
                cta_label="view assessment status",
                preview_text=f"HR received assessment for {employee_name}.",
            )
        except Exception as exc:
            logger.warning("assessment_hr_received email to manager #%s failed: %s", manager_id, exc)


def email_assessment_locked(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    manager_id: Optional[int],
    period: Optional[str],
    cycle_period: Optional[str],
) -> None:
    """HR locks assessment → email employee + manager."""
    period_label = period or "—"
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] End-Cycle Assessment Locked — {period_label}",
            greeting=f"Hi {employee_name},",
            lead="Your end-of-cycle assessment has been finalised and locked by HR.",
            detail_rows=[
                ("Review Period", period_label),
                ("Status", "Assessment Locked"),
            ],
            cta_label="view your locked assessment",
            preview_text=f"End-cycle assessment locked for {period_label}.",
        )
    except Exception as exc:
        logger.warning("assessment_locked email to employee #%s failed: %s", employee_id, exc)

    if manager_id:
        try:
            _send(
                db, manager_id,
                subject=f"[WorkHive PMS] Assessment Locked for {employee_name} — {period_label}",
                greeting="Hi,",
                lead=f"The end-of-cycle assessment for {employee_name} has been locked by HR.",
                detail_rows=[
                    ("Employee", employee_name),
                    ("Review Period", period_label),
                    ("Status", "Assessment Locked"),
                ],
                cta_label="view assessment",
                preview_text=f"Assessment locked for {employee_name}.",
            )
        except Exception as exc:
            logger.warning("assessment_locked email to manager #%s failed: %s", manager_id, exc)


# ── Phase 4: Normalization email events ───────────────────────────────────────


def email_rating_frozen(
    db: Session,
    *,
    period: str,
    employee_ids: List[int],
) -> None:
    """Ratings frozen → email each affected employee."""
    if not employee_ids:
        return
    try:
        _send_many(
            db, employee_ids,
            subject=f"[WorkHive PMS] Your Performance Rating Has Been Finalised — {period}",
            greeting="Hi,",
            lead=f"HR has finalised the performance rating normalization for the {period} cycle. Your rating has been frozen.",
            detail_rows=[
                ("Review Period", period),
                ("Status", "Rating Frozen"),
                ("Next Step", "Await compensation communication"),
            ],
            cta_label="view your performance assessment",
            preview_text=f"Performance rating frozen for {period}.",
        )
    except Exception as exc:
        logger.warning("rating_frozen email bulk send failed for period %s: %s", period, exc)


def email_hike_generated(
    db: Session,
    *,
    period: str,
    hr_ids: List[int],
) -> None:
    """Hike recommendations generated → email HR pool."""
    if not hr_ids:
        return
    try:
        _send_many(
            db, hr_ids,
            subject=f"[WorkHive PMS] Hike Recommendations Generated — {period}",
            greeting="Hi HR Team,",
            lead=f"Hike recommendations have been generated for the {period} cycle. Please review and obtain management approval.",
            detail_rows=[
                ("Review Period", period),
                ("Next Step", "Management approval required"),
            ],
            cta_label="review and approve hike recommendations",
            preview_text=f"Hike recommendations ready for {period}.",
        )
    except Exception as exc:
        logger.warning("hike_generated email to HR pool failed: %s", exc)


def email_hike_approved(
    db: Session,
    *,
    period: str,
    employee_ids: List[int],
) -> None:
    """Hikes approved → email each affected employee."""
    if not employee_ids:
        return
    try:
        _send_many(
            db, employee_ids,
            subject=f"[WorkHive PMS] Your Hike Has Been Approved — {period}",
            greeting="Hi,",
            lead=f"Management has approved your hike recommendation for the {period} cycle. HR will communicate your revised compensation shortly.",
            detail_rows=[
                ("Review Period", period),
                ("Status", "Hike Approved"),
                ("Next Step", "Await compensation revision letter"),
            ],
            cta_label="view your performance summary",
            preview_text=f"Your hike for {period} has been approved.",
        )
    except Exception as exc:
        logger.warning("hike_approved email bulk send failed for period %s: %s", period, exc)


# ── Phase 5: Compensation email events ────────────────────────────────────────


def email_revision_letter_ready(
    db: Session,
    *,
    employee_id: int,
    employee_name: str,
    period: str,
    old_ctc: float,
    new_ctc: float,
    hike_percent: float,
    effective_from: str,
) -> None:
    """Compensation revision letter generated → email employee."""
    try:
        _send(
            db, employee_id,
            subject=f"[WorkHive PMS] Your Compensation Revision Letter — {period}",
            greeting=f"Hi {employee_name},",
            lead=f"Your compensation revision for the {period} performance cycle is ready. Please log in to review and acknowledge your revised CTC.",
            detail_rows=[
                ("Review Period",   period),
                ("Previous CTC",    f"₹{old_ctc:,.0f} per annum"),
                ("Revised CTC",     f"₹{new_ctc:,.0f} per annum"),
                ("Hike",            f"{hike_percent:.1f}%"),
                ("Effective From",  effective_from),
                ("Action Required", "Acknowledge your revision letter"),
            ],
            cta_label="view and acknowledge your revision letter",
            note="Please acknowledge receipt within 7 days.",
            preview_text=f"Your revised CTC for {period} is ₹{new_ctc:,.0f}.",
        )
    except Exception as exc:
        logger.warning("revision_letter_ready email to employee #%s failed: %s", employee_id, exc)


def email_revision_acknowledged(
    db: Session,
    *,
    employee_name: str,
    hr_ids: List[int],
) -> None:
    """Employee acknowledges revision → email HR pool."""
    if not hr_ids:
        return
    try:
        _send_many(
            db, hr_ids,
            subject=f"[WorkHive PMS] {employee_name} Acknowledged Compensation Revision",
            greeting="Hi HR Team,",
            lead=f"{employee_name} has acknowledged their compensation revision letter.",
            detail_rows=[
                ("Employee", employee_name),
                ("Status",   "Acknowledged"),
            ],
            cta_label="view compensation revision records",
            preview_text=f"{employee_name} acknowledged their revision letter.",
        )
    except Exception as exc:
        logger.warning("revision_acknowledged email to HR pool failed: %s", exc)


def email_cycle_archived(
    db: Session,
    *,
    period: str,
    hr_ids: List[int],
) -> None:
    """PMS cycle archived → email HR pool."""
    if not hr_ids:
        return
    try:
        _send_many(
            db, hr_ids,
            subject=f"[WorkHive PMS] Performance Cycle {period} Archived",
            greeting="Hi HR Team,",
            lead=f"The {period} performance management cycle has been successfully archived. All records are preserved for future reference.",
            detail_rows=[
                ("Cycle Period", period),
                ("Status",       "Archived"),
            ],
            cta_label="view archived cycle records",
            preview_text=f"PMS cycle {period} archived.",
        )
    except Exception as exc:
        logger.warning("cycle_archived email to HR pool failed: %s", exc)
