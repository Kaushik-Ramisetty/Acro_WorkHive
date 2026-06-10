"""Email dispatcher.

If SMTP credentials are configured (SMTP_USERNAME + SMTP_PASSWORD), this
sends real email via the configured SMTP server (Gmail by default).
Otherwise falls back to logging the email to stdout (and optionally a
file via the HRMS_EMAIL_LOG env var) so local dev still works without
any credentials.

The Gmail "app password" is normally displayed as 4 groups of 4 chars
separated by spaces. We strip whitespace when reading it so either form
in the env file works.
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Employee


logger = logging.getLogger("hrms.email")
EMAIL_LOG_PATH = os.environ.get("HRMS_EMAIL_LOG", "")


def _smtp_configured() -> bool:
    s = get_settings()
    return bool((s.SMTP_USERNAME or "").strip() and (s.SMTP_PASSWORD or "").strip())


def smtp_enabled() -> bool:
    return _smtp_configured()


def _smtp_message(to: str, subject: str, body: str, *, html_body: Optional[str] = None):
    s = get_settings()
    username = (s.SMTP_USERNAME or "").strip()
    from_email = (s.SMTP_FROM_EMAIL or "").strip() or username
    from_name = (s.SMTP_FROM_NAME or "WorkHive HRMS").strip()

    if html_body is None:
        msg = MIMEText(body, "plain", "utf-8")
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body or "", "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain="hrms.local")
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return msg


def _send_via_smtp(to: str, subject: str, body: str, *, html_body: Optional[str] = None) -> tuple[bool, str]:
    """Returns (delivered, error_reason). error_reason is '' on success."""
    s = get_settings()
    username = (s.SMTP_USERNAME or "").strip()
    password = (s.SMTP_PASSWORD or "").replace(" ", "").strip()  # Gmail shows app pw with spaces
    from_email = (s.SMTP_FROM_EMAIL or "").strip() or username
    host = (s.SMTP_HOST or "smtp.gmail.com").strip()
    port = int(s.SMTP_PORT or 587)
    use_tls = bool(s.SMTP_USE_TLS)

    logger.info(
        "SMTP send attempt: enabled=%s host=%s port=%s tls=%s user=%s from=%s to=%s",
        _smtp_configured(), host, port, use_tls, username, from_email, to,
    )

    try:
        msg = _smtp_message(to, subject, body, html_body=html_body)
        if use_tls and port != 465:
            # STARTTLS path (Gmail standard)
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg)
        else:
            # Implicit SSL (port 465)
            with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
        logger.info("SMTP delivered to %s subject=%r", to, subject)
        return True, ""
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed for %s — check SMTP_USERNAME / SMTP_PASSWORD", to)
        return False, "SMTP authentication failed — check SMTP_USERNAME / SMTP_PASSWORD"
    except Exception as e:
        logger.error("SMTP send to %s failed: %s — falling back to log", to, e)
        return False, f"SMTP error ({type(e).__name__}): {e}"


def _log_only(to: str, subject: str, body: str) -> None:
    line = (
        f"[{datetime.now(timezone.utc).isoformat()}] EMAIL  to={to}  "
        f"subject={subject!r}  body={body!r}"
    )
    logger.info(line)
    if EMAIL_LOG_PATH:
        try:
            Path(EMAIL_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(EMAIL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            logger.warning("Could not write to HRMS_EMAIL_LOG=%s", EMAIL_LOG_PATH)


def _send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Returns (delivered, reason). reason is '' on success, error description on failure. Never raises."""
    if not to:
        return False, "Missing recipient email"
    if _smtp_configured():
        sent, err = _send_via_smtp(to, subject, body)
        if not sent:
            _log_only(to, subject, body)
        return sent, err
    else:
        _log_only(to, subject, body)
        return False, "SMTP not configured"


def send_html_email(
    to: str,
    subject: str,
    html_body: str,
    *,
    text_fallback: Optional[str] = None,
) -> None:
    """Send HTML email when SMTP is configured; otherwise log and return.

    Never raises, so post-commit workflows such as timesheet submission cannot
    be rolled back by mail transport problems.
    """
    recipient = (to or "").strip()
    if not recipient:
        logger.info("HTML email skipped: missing recipient subject=%r", subject)
        return

    body = text_fallback or ""
    if _smtp_configured():
        sent, _ = _send_via_smtp(recipient, subject, body, html_body=html_body)
        if not sent:
            _log_only(recipient, subject, body or html_body)
    else:
        s = get_settings()
        logger.info(
            "HTML email skipped: SMTP disabled recipient=%s host=%s username_configured=%s password_configured=%s",
            recipient,
            s.SMTP_HOST,
            bool((s.SMTP_USERNAME or "").strip()),
            bool((s.SMTP_PASSWORD or "").strip()),
        )


def dispatch_for_recipient(db: Session, recipient_id: int, subject: str, body: Optional[str]) -> None:
    """Resolve an Employee.id -> email -> _send_email. Silently skips if no email."""
    if not recipient_id:
        return
    emp = db.get(Employee, recipient_id)
    if not emp or not emp.email:
        return
    _send_email(emp.email, subject, body or "")


def dispatch_html_for_recipient(
    db: Session,
    recipient_id: int,
    subject: str,
    plain_body: str,
    html_body: str,
) -> None:
    """Resolve Employee.id → email → HTML email. Silently skips if no email."""
    if not recipient_id:
        return
    emp = db.get(Employee, recipient_id)
    if not emp:
        return
    email_addr = getattr(emp, "official_email", None) or getattr(emp, "email", None)
    if not email_addr:
        return
    send_html_email(email_addr, subject, html_body, text_fallback=plain_body)


def dispatch_html_for_many(
    db: Session,
    recipient_ids: list,
    subject: str,
    plain_body: str,
    html_body: str,
) -> None:
    """Bulk dispatch HTML email to multiple Employee IDs. Non-fatal."""
    for rid in recipient_ids:
        try:
            dispatch_html_for_recipient(db, rid, subject, plain_body, html_body)
        except Exception:
            pass
