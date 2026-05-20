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


def _send_via_smtp(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    username = (s.SMTP_USERNAME or "").strip()
    password = (s.SMTP_PASSWORD or "").replace(" ", "").strip()  # Gmail shows app pw with spaces
    from_email = (s.SMTP_FROM_EMAIL or "").strip() or username
    from_name = (s.SMTP_FROM_NAME or "WorkHive HRMS").strip()
    host = (s.SMTP_HOST or "smtp.gmail.com").strip()
    port = int(s.SMTP_PORT or 587)
    use_tls = bool(s.SMTP_USE_TLS)

    logger.info(
        "SMTP send attempt: host=%s port=%s tls=%s user=%s from=%s to=%s",
        host, port, use_tls, username, from_email, to,
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain="hrms.local")
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    try:
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
        return True
    except Exception as e:
        logger.error("SMTP send to %s failed: %s — falling back to log", to, e)
        return False


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


def _send_email(to: str, subject: str, body: str) -> None:
    """Public entry point. Sends real email when SMTP is configured;
    otherwise logs only. Never raises."""
    if not to:
        return
    if _smtp_configured():
        sent = _send_via_smtp(to, subject, body)
        if not sent:
            _log_only(to, subject, body)
    else:
        _log_only(to, subject, body)


def dispatch_for_recipient(db: Session, recipient_id: int, subject: str, body: Optional[str]) -> None:
    """Resolve an Employee.id -> email -> _send_email. Silently skips if no email."""
    if not recipient_id:
        return
    emp = db.get(Employee, recipient_id)
    if not emp or not emp.email:
        return
    _send_email(emp.email, subject, body or "")
