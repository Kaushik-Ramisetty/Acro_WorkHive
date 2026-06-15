"""utils/email_service.py — Centralised email sending utility for WorkHive HRMS."""

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _cfg(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _smtp_config() -> dict:
    raw_pass = _cfg("EMAIL_PASS")
    password = raw_pass.replace(" ", "")
    return {
        "host":      _cfg("EMAIL_HOST", "smtp.gmail.com"),
        "port":      int(_cfg("EMAIL_PORT", "587")),
        "user":      _cfg("EMAIL_USER"),
        "password":  password,
        "from_addr": _cfg("EMAIL_FROM") or _cfg("EMAIL_USER"),
        "simulate":  _cfg("EMAIL_SIMULATE", "true").lower() == "true",
    }


def send_email_in_background(fn, *args, label: str = "email", **kwargs) -> None:
    """Run an email-sending function in a daemon background thread."""
    import threading

    def _run():
        try:
            fn(*args, **kwargs)
            logger.info("[BG EMAIL] %s sent", label)
        except Exception as exc:
            logger.error("[BG EMAIL] %s failed: %s", label, exc)

    t = threading.Thread(target=_run, daemon=True, name=f"email-{label}")
    t.start()


def send_email_with_cc(to: str, subject: str, body: str,
                        cc: Optional[List[str]] = None,
                        attachment_paths: Optional[List[str]] = None) -> None:
    cfg = _smtp_config()
    cc = cc or []
    attachment_paths = attachment_paths or []

    msg = MIMEMultipart()
    msg["From"]    = cfg["from_addr"]
    msg["To"]      = to
    if cc: msg["Cc"]  = ", ".join(cc)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    attached = 0
    for path_str in attachment_paths:
        attach_file = Path(path_str)
        if not attach_file.exists():
            logger.warning("attachment not found, skipping: %s", path_str)
            continue
        try:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attach_file.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attach_file.name}"')
            msg.attach(part)
            attached += 1
        except Exception as exc:
            logger.warning("Could not attach %s: %s", attach_file.name, exc)

    if cfg["simulate"]:
        logger.info("[EMAIL SIMULATED] to=%s cc=%s subject=%s attachments=%d",
                    to, ", ".join(cc) if cc else "(none)", subject, attached)
        return

    if not cfg["user"] or not cfg["password"]:
        raise RuntimeError("EMAIL_USER and EMAIL_PASS must be set in .env when EMAIL_SIMULATE=false.")

    all_recipients = [to] + cc
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_addr"], all_recipients, msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("Email authentication failed.") from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"Failed to send email: {exc}") from exc


def send_email(to: str, subject: str, body: str, attachment_path: Optional[str] = None) -> None:
    send_email_with_cc(to=to, subject=subject, body=body,
                       attachment_paths=[attachment_path] if attachment_path else [])


# ── BGV initiation email ────────────────────────────────────────────────────

_DOC_LABELS = {
    "aadhar": "Aadhaar Card",
    "pan":    "PAN Card",
    "degree": "Degree Certificate",
    "exp":    "Experience Letters",
    "photo":  "Passport Photo",
    "bank":   "Bank Account Proof",
}
_REQUIRED_ORDER = ["aadhar", "pan", "degree", "exp", "photo", "bank"]


def send_bgv_email(candidate, uploaded_docs: list) -> None:
    vendor_email = _cfg("BGV_VENDOR_EMAIL", "vendor@example.com")
    admin_cc     = _cfg("ADMIN_CC_EMAIL",   "admin@example.com")
    upload_dir   = _cfg("UPLOAD_DIR", "./uploads")
    latest_by_type: dict = {}
    for doc in uploaded_docs:
        prev = latest_by_type.get(doc.doc_type)
        if prev is None or (doc.uploaded_at and prev.uploaded_at and doc.uploaded_at > prev.uploaded_at):
            latest_by_type[doc.doc_type] = doc
    doc_lines = []
    for idx, key in enumerate(_REQUIRED_ORDER, 1):
        label = _DOC_LABELS.get(key, key)
        doc_lines.append(f"  {idx}. {label}" + ("" if key in latest_by_type else "  [missing]"))
    body = ("Hello Vendor Team,\n\nBackground Verification has been initiated for:\n\n"
            f"  Candidate Name   : {candidate.name}\n"
            f"  Candidate ID     : {candidate.candidate_ref}\n"
            f"  Candidate Email  : {candidate.email}\n\n"
            "Uploaded Documents:\n" + "\n".join(doc_lines) + "\n\n"
            "Please find the candidate's documents attached.\n\n"
            "Regards,\nHRMS Onboarding Team")
    attachment_paths = []
    for doc in latest_by_type.values():
        rel_path = doc.file_url.lstrip("/")
        disk_path = Path(rel_path)
        if not disk_path.exists():
            disk_path = Path(upload_dir).parent / rel_path
        attachment_paths.append(str(disk_path))
    send_email_with_cc(to=vendor_email,
                       subject=f"BGV Initiated for Candidate - {candidate.name}",
                       body=body, cc=[admin_cc] if admin_cc else [],
                       attachment_paths=attachment_paths)


def send_bgv_vendor_link_email(candidate, vendor_link: str, expires_at=None) -> None:
    vendor_email = _cfg("BGV_VENDOR_EMAIL", "vendor@example.com")
    admin_cc     = _cfg("ADMIN_CC_EMAIL",   "admin@example.com")
    expiry_str   = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "48 hours from now"
    body = ("Hello Vendor Team,\n\nBGV initiated for:\n\n"
            f"  Candidate Name : {candidate.name}\n"
            f"  Candidate ID   : {candidate.candidate_ref}\n"
            f"  Email          : {candidate.email}\n\n"
            f"Secure Review Link: {vendor_link}\n\n"
            f"This link expires on {expiry_str} and can be used ONLY ONCE.\n\n"
            "Regards,\nHRMS Onboarding Team")
    send_email_with_cc(to=vendor_email,
                       subject=f"BGV Review Required - {candidate.name} [{candidate.candidate_ref}]",
                       body=body, cc=[admin_cc] if admin_cc else [])


def send_bgv_result_admin_email(candidate, status: str, remarks=None, reviewed_at=None) -> None:
    """Notify admin when vendor submits a BGV result.
    Maps the vendor-submitted shortcode to a user-facing label."""
    admin_email = _cfg("ADMIN_CC_EMAIL", "admin@example.com")
    _LABELS = {
        "CLEAR":   "BGV Cleared",
        "HOLD":    "BGV On Hold",
        "FAILED":  "BGV Rejected",
        "ON_HOLD": "BGV On Hold",
    }
    status_label = _LABELS.get(status, f"BGV {status}")
    reviewed_str = reviewed_at.strftime("%Y-%m-%d %H:%M UTC") if reviewed_at else "N/A"
    body = ("Hello Admin,\n\nThe BGV vendor has submitted a verification result.\n\n"
            f"  Candidate   : {candidate.name} [{candidate.candidate_ref}]\n"
            f"  BGV Result  : {status_label}\n"
            f"  Reviewed At : {reviewed_str}\n")
    if remarks:
        body += f"  Remarks     : {remarks}\n"
    body += "\nPlease log in to the HRMS admin dashboard.\n\nRegards,\nHRMS Onboarding System"
    send_email_with_cc(to=admin_email,
                       subject=f"BGV Result: {status_label} - {candidate.name} [{candidate.candidate_ref}]",
                       body=body)


def send_candidate_onboarding_email(candidate) -> None:
    subject = "Onboarding Documents Required for BGV Process"
    portal_url = _cfg("FRONTEND_BASE_URL", "http://localhost:5173") + "/candidate-dashboard"
    body = (f"Dear {candidate.name},\n\n"
            "As part of onboarding, please log in to the candidate portal and upload your documents.\n\n"
            "Required Documents:\n"
            "  1. Updated BGV Form\n"
            "  2. Highest Qualification\n"
            "  3. Latest Emp 1, 2 and 3\n"
            "  4. Address Proof\n\n"
            f"Login: {portal_url}\nEmail: {candidate.email}\nPassword: candidate123\n\n"
            "Regards,\nHR Team - Acronotics")
    cif_path = _cfg("CIF_FORM_PATH", "")
    if not cif_path:
        cif_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "CIF-BGV-Form.docx",
        )
    attachment_paths = []
    if os.path.isfile(cif_path):
        attachment_paths.append(cif_path)
    else:
        logger.warning("[ONBOARDING EMAIL] CIF form not found at '%s'.", cif_path)
    send_email_with_cc(to=candidate.email, subject=subject, body=body,
                       attachment_paths=attachment_paths)


def send_it_request_email(employee, manager_name: str = None, manager_email: str = None) -> None:
    it_email = _cfg("IT_EMAIL", "")
    admin_cc = _cfg("ADMIN_CC_EMAIL", "")
    if not it_email:
        raise ValueError("IT_EMAIL is not set in .env.")
    cc_list = [addr for addr in [admin_cc, manager_email] if addr]
    body = ("Hello IT Team,\n\nPlease create an official email account for:\n\n"
            f"  Employee Name  : {employee.first_name} {employee.last_name}\n"
            f"  Employee Code  : {employee.employee_code}\n"
            f"  Designation    : {employee.designation_id}\n"
            f"  Department     : {employee.department_id}\n"
            f"  Date of Joining: {employee.date_of_joining}\n"
            f"  Personal Email : {employee.email}\n")
    if manager_name:
        body += f"  Reporting To   : {manager_name}\n"
    body += "\nShare the official email and temp password with HR.\n\nRegards,\nHRMS System"
    send_email_with_cc(to=it_email,
                       subject=f"IT Account Creation Request - {employee.first_name} {employee.last_name} [{employee.employee_code}]",
                       body=body, cc=cc_list)


def send_employee_welcome_email(employee, temp_password: str) -> None:
    """Send to PERSONAL email (employee hasn't accessed official inbox yet)."""
    portal_url = _cfg("FRONTEND_BASE_URL", "http://localhost:5173") + "/employee-dashboard"
    company = _cfg("COMPANY_NAME", "WorkHive")
    body = (f"Dear {employee.first_name},\n\n"
            f"Welcome to {company}. Your employee portal account has been activated.\n\n"
            "Login credentials:\n"
            f"  Login Email    : {employee.official_email}\n"
            f"  Temp Password  : {temp_password}\n"
            f"  Employee Portal: {portal_url}\n\n"
            "IMPORTANT: You will be required to change your password on first login.\n\n"
            "Regards,\nHR Team - " + company)
    send_email_with_cc(to=employee.email,
                       subject=f"Welcome to {company} - Your Portal Account is Ready",
                       body=body)
