"""Payroll workflow email notification service.

Handles all six required payroll email triggers without touching any
payroll business logic, status machine, or UI.

Design rules:
- Never raises — a failed email must NOT abort any payroll action.
- Reuses SMTP_* env vars from existing Settings (no new env vars).
- Sends HTML + plain-text multipart emails.
- Deduplicates recipients by email address.
- Logs success / failure per email so failures are auditable.
- Tries to write a PayrollAuditLog entry for each notification batch.

Six triggers (called from payroll_service._dispatch_payroll_notifications):
  1. notify_attendance_frozen    → Finance users
  2. notify_payroll_submitted    → Finance users
  3. notify_payroll_rejected     → HR + Admin users  (includes rejection reason)
  4. notify_finance_approved     → Finance Head users
  5. notify_head_approved        → HR + Admin + Finance users
  6. notify_payslips_published   → Employees in the payroll run
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.payroll import PayrollRun, PayrollRunEmployee
from app.models.payroll_extended import Payslip

log = logging.getLogger("hrms.payroll.email")

# ── Email helper — delegates to the shared WorkHive dispatcher ────────────────

def _send_one(to_email: str, subject: str, body_plain: str, body_html: str) -> bool:
    """Send a single payroll email via the shared WorkHive email service.

    Delegates entirely to email_dispatcher so that SMTP credentials, the
    From address, and fallback logging are all controlled by the single
    existing SMTP_* / SMTP_FROM_EMAIL configuration — no separate sender,
    no hardcoded credentials.  Returns True when a valid address is given;
    email_dispatcher handles delivery failures internally and never raises.
    """
    addr = (to_email or "").strip()
    if not addr:
        return False
    from app.services.email_dispatcher import send_html_email
    send_html_email(addr, subject, body_html, text_fallback=body_plain)
    return True


def _send_to_many(recipients: list[Employee], subject: str, plain: str, html: str) -> int:
    """Broadcast email to a list of employees, deduplicated by address. Returns count sent."""
    seen: set[str] = set()
    sent = 0
    for emp in recipients:
        addr = (getattr(emp, "official_email", None) or emp.email or "").strip()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        if _send_one(addr, subject, plain, html):
            sent += 1
    return sent


# ── Recipient helpers ─────────────────────────────────────────────────────────

def get_recipients_by_role(db: Session, *role_names: str) -> list[Employee]:
    """Return active, non-deleted employees whose role matches any of role_names."""
    from app.models.role import Role
    if not role_names:
        return []
    roles = db.query(Role).filter(Role.name.in_(role_names)).all()
    role_ids = [r.id for r in roles]
    if not role_ids:
        return []
    return (
        db.query(Employee)
        .filter(
            Employee.role_id.in_(role_ids),
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
        .all()
    )


def get_employees_in_run(db: Session, run_id: int) -> list[Employee]:
    """Return all employees included in the given payroll run."""
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    emp_ids = list({r.employee_id for r in rows if r.employee_id})
    if not emp_ids:
        return []
    return (
        db.query(Employee)
        .filter(
            Employee.id.in_(emp_ids),
            Employee.is_deleted.is_(False),
        )
        .all()
    )


# ── HTML template ─────────────────────────────────────────────────────────────

def _html(heading: str, body_inner: str, *, accent: str = "#2d3ec9", footer: str = "") -> str:
    footer_html = f"<p style='color:#94a3b8;font-size:12px;margin:4px 0 0;'>{footer}</p>" if footer else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>WorkHive HRMS</title></head>
<body style="margin:0;padding:0;background:#f2f4f7;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f4f7;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" style="max-width:520px;background:#ffffff;border:1px solid #e2e6ea;border-radius:10px;">
  <!-- Header -->
  <tr><td style="background:{accent};border-radius:10px 10px 0 0;padding:24px 32px;">
    <p style="margin:0;color:#c7d2fe;font-size:11px;font-weight:bold;letter-spacing:3px;text-transform:uppercase;">
      Acronotics HRMS
    </p>
    <p style="margin:4px 0 0;color:#ffffff;font-size:20px;font-weight:bold;">{heading}</p>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px 32px;color:#1e293b;font-size:14px;line-height:22px;">
    {body_inner}
  </td></tr>
  <!-- Footer -->
  <tr><td style="border-top:1px solid #e2e8f0;background:#f8fafc;border-radius:0 0 10px 10px;
                 padding:14px 32px;text-align:center;">
    {footer_html}
    <p style="margin:4px 0 0;color:#94a3b8;font-size:12px;">
      &copy; WorkHive HRMS &bull; Acronotics Internal System
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def _info_box(text: str, *, color: str = "#2d3ec9", bg: str = "#eff6ff") -> str:
    return (
        f"<p style='background:{bg};border-left:4px solid {color};"
        f"padding:12px 16px;border-radius:4px;margin:16px 0;'>{text}</p>"
    )


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit_notification(
    db: Session,
    run: PayrollRun,
    event_label: str,
    recipient_count: int,
) -> None:
    """Write a PayrollAuditLog entry for the notification batch. Best-effort only.

    payroll_audit_logs.employee_id is NOT NULL FK to employees — never insert 0.
    We use the run's actor (initiated_by_id / approved_by_id) as a valid FK value.
    If no actor is available we skip the DB write (Python log is sufficient) to
    avoid corrupting the SQLAlchemy session with a pending IntegrityError rollback.
    """
    log.info(
        "[PAYROLL EMAIL] run_id=%d event=%s recipients=%d month=%s",
        run.id, event_label, recipient_count, run.month_label or run.id,
    )
    actor_id = getattr(run, "initiated_by_id", None) or getattr(run, "approved_by_id", None)
    if not actor_id:
        return  # No valid FK value — skip DB write, Python log above is sufficient
    try:
        from app.models.payroll_extended import PayrollAuditLog
        entry = PayrollAuditLog(
            run_id=run.id,
            employee_id=actor_id,
            event=f"email_notification:{event_label}",
            details=f"Sent {recipient_count} email(s) for {run.month_label or run.id}",
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()  # Clear pending-rollback state so the session stays usable
        log.debug("[PAYROLL EMAIL] Audit log write skipped: %s", exc)


# ── Six notification triggers ─────────────────────────────────────────────────

def notify_attendance_frozen(db: Session, run: PayrollRun, actor_name: str) -> None:
    """Trigger 1 — Attendance frozen by HR: notify Finance users."""
    try:
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payroll inputs frozen for {month_year}"
        plain = (
            f"Hi,\n\n"
            f"Attendance and timesheet inputs are frozen for payroll {month_year} "
            f"by {actor_name}. Payroll generation and review can now proceed.\n\n"
            f"Log in to HRMS → Finance → Payroll to continue.\n\n"
            f"— Acronotics HR Team"
        )
        html = _html(
            heading="Payroll Inputs Frozen",
            body_inner=(
                "<p>Hi,</p>"
                f"<p>Attendance and timesheet inputs have been <strong>frozen</strong> for payroll "
                f"<strong>{month_year}</strong> by <strong>{actor_name}</strong>.</p>"
                + _info_box(
                    "Payroll generation and review can now proceed.",
                    color="#16a34a", bg="#f0fdf4",
                )
                + "<p>Log in to HRMS &rarr; Finance &rarr; Payroll to proceed.</p>"
            ),
        )
        recipients = get_recipients_by_role(db, "finance")
        sent = _send_to_many(recipients, subject, plain, html)
        log.info(
            "[PAYROLL EMAIL] freeze_attendance: %d Finance recipient(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "attendance_frozen", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] freeze_attendance notification failed (non-fatal): %s", exc)


def notify_payroll_submitted(db: Session, run: PayrollRun, actor_name: str) -> None:
    """Trigger 2 — Payroll submitted for Finance review: notify Finance users."""
    try:
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payroll submitted for Finance Review - {month_year}"
        plain = (
            f"Hi,\n\n"
            f"Payroll for {month_year} has been submitted for Finance review by {actor_name}.\n\n"
            f"Log in to HRMS → Finance → Payroll to review and approve.\n\n"
            f"— Acronotics HR Team"
        )
        html = _html(
            heading="Payroll Submitted for Finance Review",
            body_inner=(
                "<p>Hi,</p>"
                f"<p>Payroll for <strong>{month_year}</strong> has been submitted for "
                f"<strong>Finance review</strong> by <strong>{actor_name}</strong>.</p>"
                + _info_box("Your review and approval are required.")
                + "<p>Log in to HRMS &rarr; Finance &rarr; Payroll to review and approve.</p>"
            ),
        )
        recipients = get_recipients_by_role(db, "finance")
        sent = _send_to_many(recipients, subject, plain, html)
        log.info(
            "[PAYROLL EMAIL] payroll_submitted: %d Finance recipient(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "payroll_submitted", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] payroll_submitted notification failed (non-fatal): %s", exc)


def notify_payroll_rejected(
    db: Session,
    run: PayrollRun,
    actor_name: str,
    reason: Optional[str],
) -> None:
    """Trigger 3 — Finance rejects payroll: notify HR and Admin users with reason."""
    try:
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payroll rejected by Finance - {month_year}"
        reason_text = (reason or "").strip() or "No reason provided."
        plain = (
            f"Hi,\n\n"
            f"Payroll for {month_year} has been rejected by Finance ({actor_name}).\n\n"
            f"Rejection reason: {reason_text}\n\n"
            f"Please log in to HRMS to review errors and recompute payroll.\n\n"
            f"— Acronotics HR Team"
        )
        html = _html(
            heading="Payroll Rejected by Finance",
            accent="#dc2626",
            body_inner=(
                "<p>Hi,</p>"
                f"<p>Payroll for <strong>{month_year}</strong> has been "
                f"<strong>rejected</strong> by Finance ({actor_name}).</p>"
                + _info_box(
                    f"<strong>Rejection reason:</strong> {reason_text}",
                    color="#ea580c", bg="#fff7ed",
                )
                + "<p>Log in to HRMS &rarr; Payroll to review errors and recompute.</p>"
            ),
        )
        recipients = get_recipients_by_role(db, "hr", "admin")
        sent = _send_to_many(recipients, subject, plain, html)
        log.info(
            "[PAYROLL EMAIL] payroll_rejected: %d HR/Admin recipient(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "payroll_rejected", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] payroll_rejected notification failed (non-fatal): %s", exc)


def notify_finance_approved(db: Session, run: PayrollRun, actor_name: str) -> None:
    """Trigger 4 — Finance approves: notify Finance Head users."""
    try:
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payroll ready for Finance Head Approval - {month_year}"
        plain = (
            f"Hi,\n\n"
            f"Payroll for {month_year} has been approved by Finance ({actor_name}) "
            f"and is now awaiting your final approval.\n\n"
            f"Log in to HRMS to review and give your final approval.\n\n"
            f"— Acronotics HR Team"
        )
        html = _html(
            heading="Payroll Ready for Final Approval",
            body_inner=(
                "<p>Hi,</p>"
                f"<p>Payroll for <strong>{month_year}</strong> has been approved by Finance "
                f"({actor_name}) and is now awaiting your <strong>final approval</strong>.</p>"
                + _info_box(
                    "Your action is required. Please log in to HRMS &rarr; Payroll Approvals."
                )
            ),
        )
        recipients = get_recipients_by_role(db, "finance_head")
        sent = _send_to_many(recipients, subject, plain, html)
        log.info(
            "[PAYROLL EMAIL] finance_approved: %d Finance Head recipient(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "finance_approved", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] finance_approved notification failed (non-fatal): %s", exc)


def notify_head_approved(db: Session, run: PayrollRun, actor_name: str) -> None:
    """Trigger 5 — Finance Head gives final approval: notify HR, Admin, and Finance."""
    try:
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payroll final approved - {month_year}"
        plain = (
            f"Hi,\n\n"
            f"Payroll for {month_year} has received final approval from Finance Head "
            f"({actor_name}). You can now generate and publish payslips.\n\n"
            f"Log in to HRMS → Finance → Payroll to proceed.\n\n"
            f"— Acronotics HR Team"
        )
        html = _html(
            heading="Payroll Final Approved",
            accent="#16a34a",
            body_inner=(
                "<p>Hi,</p>"
                f"<p>Payroll for <strong>{month_year}</strong> has received "
                f"<strong>final approval</strong> from Finance Head ({actor_name}).</p>"
                + _info_box(
                    "You can now generate payslips and publish them to the ESS portal.",
                    color="#16a34a", bg="#f0fdf4",
                )
                + "<p>Log in to HRMS &rarr; Finance &rarr; Payroll to proceed.</p>"
            ),
        )
        recipients = get_recipients_by_role(db, "hr", "admin", "finance")
        sent = _send_to_many(recipients, subject, plain, html)
        log.info(
            "[PAYROLL EMAIL] head_approved: %d HR/Admin/Finance recipient(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "head_approved", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] head_approved notification failed (non-fatal): %s", exc)


def notify_payslips_published(db: Session, run: PayrollRun) -> None:
    """Trigger 6 — Payslips published to ESS: notify each employee in the run."""
    try:
        from datetime import datetime as _dt
        month_year = run.month_label or f"Run #{run.id}"
        subject = f"Payslip Available - {month_year}"
        # Pre-load payslips to mark email_sent and prevent double-send via other paths
        slips_by_emp: dict[int, object] = {
            s.employee_id: s
            for s in db.query(Payslip).filter_by(run_id=run.id, is_published=True).all()
        }
        employees = get_employees_in_run(db, run.id)
        seen: set[str] = set()
        sent = 0
        for emp in employees:
            slip = slips_by_emp.get(emp.id)
            # Skip if already emailed
            if slip and (getattr(slip, "email_sent", False) or getattr(slip, "emailed_at", None)):
                continue
            addr = (getattr(emp, "official_email", None) or emp.email or "").strip()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            name = f"{emp.first_name} {(emp.last_name or '')}".strip()
            plain = (
                f"Hello {name},\n\n"
                f"Your {month_year} payslip has been published in WorkHive ESS.\n\n"
                f"Please login to the ESS portal to view and download your payslip.\n\n"
                f"Regards,\nWorkHive Payroll Team"
            )
            html = _html(
                heading="Payslip Available",
                body_inner=(
                    f"<p>Hello {name},</p>"
                    f"<p>Your <strong>{month_year}</strong> payslip has been published in "
                    f"<strong>WorkHive ESS</strong>.</p>"
                    + _info_box(
                        "Please login to the ESS portal to view and download your payslip.",
                        color="#16a34a", bg="#f0fdf4",
                    )
                ),
                footer="Regards,<br>WorkHive Payroll Team",
            )
            if _send_one(addr, subject, plain, html):
                sent += 1
                if slip:
                    now = _dt.utcnow()
                    try:
                        slip.email_sent = True
                        slip.email_sent_at = now
                        slip.emailed_at = now
                        db.commit()
                    except Exception:
                        pass
        log.info(
            "[PAYROLL EMAIL] payslips_published: %d employee(s) notified for %s",
            sent, month_year,
        )
        _audit_notification(db, run, "payslips_published", sent)
    except Exception as exc:
        log.warning("[PAYROLL EMAIL] payslips_published notification failed (non-fatal): %s", exc)
