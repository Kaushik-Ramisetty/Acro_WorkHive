"""Payslip PDF generation service.

Uses ReportLab to generate a professional payslip PDF.
Falls back gracefully if reportlab is not installed (returns None pdf_bytes).

PDF layout:
  ┌────────────────────────────────────────┐
  │  Company Header                         │
  │  SALARY SLIP — April 2025              │
  ├─────────────────┬──────────────────────┤
  │  Employee Info  │  Pay Period / Bank    │
  ├─────────────────┴──────────────────────┤
  │  Attendance Summary                     │
  ├────────────────────┬───────────────────┤
  │  EARNINGS          │  DEDUCTIONS        │
  │  Basic             │  Employee PF       │
  │  HRA               │  Employee ESI      │
  │  Special Allow.    │  Professional Tax  │
  │  Transport Allow.  │  TDS               │
  │  Medical Allow.    │  Other Deductions  │
  │  Other             │                    │
  ├────────────────────┴───────────────────┤
  │  Gross: ₹XX,XXX  │  Net Pay: ₹XX,XXX  │
  └────────────────────────────────────────┘
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payroll import PayrollRunEmployee, PayrollRun, SalaryStructure
from app.models.payroll_extended import Payslip, PayrollAdjustment, PayslipDownloadAudit
from app.models.employee import Employee

# Optional ReportLab import — service degrades gracefully if not installed
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

PAYSLIP_DIR = Path("payslips")


def _ensure_dir() -> None:
    PAYSLIP_DIR.mkdir(parents=True, exist_ok=True)


def _fmt_inr(amount: float) -> str:
    """Format as Indian currency with ₹ symbol."""
    if amount == 0:
        return "₹0"
    return f"₹{amount:,.2f}"


def generate_payslip_pdf(
    db: Session,
    run_id: int,
    employee_id: int,
    company_name: str = "Acronotics Inc.",
    company_address: str = "India",
) -> Optional[bytes]:
    """Generate payslip PDF bytes for one employee in a run.

    Returns None if ReportLab is unavailable or record not found.
    """
    if not _REPORTLAB_AVAILABLE:
        return None

    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    row = db.query(PayrollRunEmployee).filter_by(run_id=run_id, employee_id=employee_id).first()
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    ss = db.query(SalaryStructure).filter_by(employee_id=employee_id).first()

    if not run or not row or not emp:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    styles = getSampleStyleSheet()
    brand = colors.HexColor("#1e40af")   # brand blue
    light_gray = colors.HexColor("#f1f5f9")
    mid_gray = colors.HexColor("#94a3b8")
    dark = colors.HexColor("#1e293b")

    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=brand,
                         fontSize=18, spaceAfter=2, alignment=TA_CENTER)
    h2 = ParagraphStyle("H2", parent=styles["Normal"], textColor=dark,
                         fontSize=10, spaceAfter=2, alignment=TA_CENTER)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8,
                            textColor=mid_gray, alignment=TA_CENTER)
    label = ParagraphStyle("Label", parent=styles["Normal"], fontSize=8,
                            textColor=mid_gray)
    value = ParagraphStyle("Value", parent=styles["Normal"], fontSize=9,
                            textColor=dark, fontName="Helvetica-Bold")
    section_hdr = ParagraphStyle("SHdr", parent=styles["Normal"], fontSize=9,
                                  textColor=colors.white, fontName="Helvetica-Bold")

    emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
    dept = emp.department.name if emp.department else "—"
    desig = emp.designation.title if emp.designation else "—"
    emp_code = emp.employee_code or f"EMP{emp.id:04d}"
    bank_name = ss.bank_name if ss else "—"
    account_no = ss.account_number if ss else "—"

    elements = []

    # ── Header ──
    elements.append(Paragraph(company_name, h1))
    elements.append(Paragraph(company_address, small))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"SALARY SLIP — {run.month_label}", h2))
    elements.append(HRFlowable(width="100%", thickness=1, color=brand))
    elements.append(Spacer(1, 3*mm))

    # ── Employee + Pay Period Info ──
    info_data = [
        [Paragraph("Employee Name", label), Paragraph(emp_name, value),
         Paragraph("Pay Period", label), Paragraph(f"{run.pay_period_start} to {run.pay_period_end}", value)],
        [Paragraph("Employee Code", label), Paragraph(emp_code, value),
         Paragraph("Bank", label), Paragraph(bank_name, value)],
        [Paragraph("Department", label), Paragraph(dept, value),
         Paragraph("Account No.", label), Paragraph(account_no, value)],
        [Paragraph("Designation", label), Paragraph(desig, value),
         Paragraph("PF No.", label), Paragraph("—", value)],
    ]
    info_table = Table(info_data, colWidths=[35*mm, 55*mm, 35*mm, 55*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), light_gray),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [light_gray, colors.white]),
        ("BOX", (0, 0), (-1, -1), 0.5, mid_gray),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, mid_gray),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 4*mm))

    # ── Attendance ──
    att_data = [
        [Paragraph("ATTENDANCE SUMMARY", section_hdr), "", "", "", "", ""],
        [
            Paragraph("Working Days", label),
            Paragraph(str(row.working_days), value),
            Paragraph("Present", label),
            Paragraph(str(row.present_days), value),
            Paragraph("LOP Days", label),
            Paragraph(str(row.lop_days), value),
        ],
    ]
    att_table = Table(att_data, colWidths=[30*mm, 25*mm, 30*mm, 25*mm, 30*mm, 40*mm])
    att_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 1), (-1, 1), light_gray),
        ("BOX", (0, 0), (-1, -1), 0.5, mid_gray),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(att_table)
    elements.append(Spacer(1, 4*mm))

    # ── Earnings + Deductions side-by-side ──
    # Read component values directly from SalaryStructure for accuracy;
    # fall back to row values when structure is unavailable.
    special_allow   = ss.special_allowance   if ss else 0.0
    transport_allow = ss.transport_allowance if ss else 0.0
    medical_allow   = ss.medical_allowance   if ss else 0.0
    other_allow     = ss.other_allowances    if ss else 0.0

    # Query one-time adjustments for this employee in this run
    adjustments = (
        db.query(PayrollAdjustment)
        .filter_by(run_id=run_id, employee_id=employee_id)
        .all()
    )
    addition_adjs = [(a.adjustment_type.replace("_", " ").title(), a.amount)
                     for a in adjustments if a.direction == "addition"]
    deduction_adjs = [(a.adjustment_type.replace("_", " ").title(), a.amount)
                      for a in adjustments if a.direction == "deduction"]

    earnings_base = [
        ("Basic",              row.basic_pay),
        ("HRA",                row.hra),
        ("Special Allowance",  special_allow),
        ("Transport Allowance",transport_allow),
        ("Medical Allowance",  medical_allow),
    ]
    if other_allow > 0:
        earnings_base.append(("Other Allowances", other_allow))
    earnings_base.extend(addition_adjs)

    # TDS note: show reason when TDS is ₹0 but employee has non-zero salary
    tds_label = "TDS"
    if row.tds == 0 and row.gross_earnings > 0:
        annual_gross = row.gross_earnings * 12
        if annual_gross < 250000:
            tds_label = "TDS (below ₹2.5L limit)"
        else:
            tds_label = "TDS (no declaration filed)"

    deductions_base = [
        ("Employee PF",       row.employee_pf),
        ("Employee ESI",      row.employee_esi),
        ("Professional Tax",  row.professional_tax),
        (tds_label,           row.tds),
    ]
    deductions_base.extend(deduction_adjs)

    # Pad to equal length for the side-by-side table
    max_rows = max(len(earnings_base), len(deductions_base))
    earnings  = earnings_base  + [("", 0.0)] * (max_rows - len(earnings_base))
    deductions = deductions_base + [("", 0.0)] * (max_rows - len(deductions_base))

    sal_header = [
        Paragraph("EARNINGS", section_hdr), "", "",
        Paragraph("DEDUCTIONS", section_hdr), "", "",
    ]
    sal_rows = [sal_header]
    for (e_label, e_val), (d_label, d_val) in zip(earnings, deductions):
        sal_rows.append([
            Paragraph(e_label, label), "", Paragraph(_fmt_inr(e_val), value),
            Paragraph(d_label, label), "", Paragraph(_fmt_inr(d_val) if d_val else "—", value),
        ])

    sal_table = Table(sal_rows, colWidths=[40*mm, 5*mm, 40*mm, 40*mm, 5*mm, 50*mm])
    sal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (2, 0), brand),
        ("BACKGROUND", (3, 0), (-1, 0), colors.HexColor("#064e3b")),
        ("SPAN", (0, 0), (2, 0)),
        ("SPAN", (3, 0), (-1, 0)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_gray]),
        ("BOX", (0, 0), (2, -1), 0.5, mid_gray),
        ("BOX", (3, 0), (-1, -1), 0.5, mid_gray),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, mid_gray),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (5, 0), (5, -1), "RIGHT"),
    ]))
    elements.append(sal_table)
    elements.append(Spacer(1, 2*mm))

    # ── Totals ──
    total_data = [[
        Paragraph("GROSS SALARY", section_hdr),
        Paragraph(_fmt_inr(row.gross_earnings), ParagraphStyle(
            "TotalVal", parent=styles["Normal"], fontSize=11,
            fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph("TOTAL DEDUCTIONS", section_hdr),
        Paragraph(_fmt_inr(row.total_deductions), ParagraphStyle(
            "TotalVal2", parent=styles["Normal"], fontSize=11,
            fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph("NET PAY", section_hdr),
        Paragraph(_fmt_inr(row.net_pay), ParagraphStyle(
            "NetVal", parent=styles["Normal"], fontSize=12,
            fontName="Helvetica-Bold", textColor=colors.HexColor("#fbbf24"), alignment=TA_RIGHT)),
    ]]
    total_table = Table(total_data, colWidths=[40*mm, 35*mm, 45*mm, 35*mm, 25*mm, 40*mm])
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), brand),
        ("BOX", (0, 0), (-1, -1), 0.5, brand),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 6*mm))

    # ── Footer ──
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                                   textColor=mid_gray, alignment=TA_CENTER)
    elements.append(Paragraph(
        f"This is a computer-generated salary slip and does not require a signature. "
        f"Generated on {datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC.",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


def save_payslip_pdf(
    db: Session, run_id: int, employee_id: int,
    company_name: str = "Acronotics Inc.", company_address: str = "India",
    generated_by_id: Optional[int] = None,
) -> Optional[str]:
    """Generate PDF, save to disk, update Payslip record, return file path.

    IMMUTABILITY GUARD: If the payslip is already published (is_published=True),
    this function REFUSES to regenerate and returns the existing file path.
    Published payslips are immutable.  To regenerate, the run must be
    un-published first (admin only, with audit trail).
    """
    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()

    # ── Immutability guard ───────────────────────────────────────────────
    if slip and slip.is_published:
        import logging as _log
        _log.getLogger("hrms.payslip").warning(
            "BLOCKED: Attempt to regenerate PUBLISHED payslip "
            "(run_id=%d, employee_id=%d). Published payslips are immutable.",
            run_id, employee_id,
        )
        return slip.pdf_path or slip.file_url   # Return existing path — no regeneration

    pdf_bytes = generate_payslip_pdf(db, run_id, employee_id, company_name, company_address)
    if not pdf_bytes:
        return None

    _ensure_dir()
    filename = f"payslip_run{run_id}_emp{employee_id}.pdf"
    filepath = PAYSLIP_DIR / filename
    filepath.write_bytes(pdf_bytes)

    # Update Payslip record with pdf_path
    if slip:
        slip.pdf_path = str(filepath)
        slip.file_url = str(filepath)
        slip.pdf_generated_at = datetime.utcnow()
        slip.generated_at = slip.generated_at or slip.pdf_generated_at
        if generated_by_id:
            slip.generated_by_id = generated_by_id
        db.commit()

    return str(filepath)


def record_payslip_download(
    db: Session,
    payslip_id: int,
    employee_id: int,
    downloaded_by_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    download_source: str = "web",
) -> None:
    """Create an immutable audit record for every payslip download.

    Also increments the payslip.download_count counter.

    This must be called every time a payslip PDF is served to any user
    (employee, Finance, Admin).  Never raises — errors are logged only.
    """
    try:
        audit = PayslipDownloadAudit(
            payslip_id=payslip_id,
            employee_id=employee_id,
            downloaded_by_id=downloaded_by_id,
            downloaded_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            download_source=download_source,
        )
        db.add(audit)

        # Increment download counter on Payslip
        slip = db.query(Payslip).filter_by(id=payslip_id).first()
        if slip:
            slip.download_count = (slip.download_count or 0) + 1

        db.commit()
    except Exception as exc:
        import logging as _log
        _log.getLogger("hrms.payslip").warning(
            "record_payslip_download failed for payslip_id=%d: %s", payslip_id, exc
        )
        try:
            db.rollback()
        except Exception:
            pass


def publish_payslip(
    db: Session,
    run_id: int,
    employee_id: int,
    published_by_id: Optional[int] = None,
    send_email: bool = True,
) -> bool:
    """Mark a payslip as published (is_published=True).

    Once published, the payslip is immutable — no further regeneration allowed.
    Optionally sends an email notification to the employee.

    Returns True if the payslip was newly published, False if already published.
    """
    import logging as _log
    _logger = _log.getLogger("hrms.payslip")

    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()
    if not slip:
        _logger.warning("publish_payslip: no payslip found for run_id=%d emp_id=%d", run_id, employee_id)
        return False

    if slip.is_published:
        _logger.info("publish_payslip: payslip already published (run=%d emp=%d)", run_id, employee_id)
        return False

    now = datetime.utcnow()
    slip.is_published = True
    slip.published_at = now
    slip.status = "PUBLISHED"
    db.commit()

    _logger.info(
        "Payslip published: run_id=%d, employee_id=%d, published_by=%s",
        run_id, employee_id, published_by_id or "system",
    )

    # ── Email notification ────────────────────────────────────────────────
    if send_email:
        try:
            run = db.query(PayrollRun).filter_by(id=run_id).first()
            emp = db.query(Employee).filter_by(id=employee_id).first()
            if emp and run:
                recipient = (getattr(emp, "official_email", None) or emp.email or "").strip()
                if recipient:
                    from app.services.email_dispatcher import _send_email
                    subject = f"Your payslip for {run.month_label} is now available"
                    body = (
                        f"Hi {emp.first_name or 'Employee'},\n\n"
                        f"Your payslip for {run.month_label} has been published in WorkHive HRMS.\n\n"
                        f"Gross Pay:        ₹{slip.gross_salary:,.2f}\n"
                        f"Total Deductions: ₹{slip.total_deductions:,.2f}\n"
                        f"Net Pay:          ₹{slip.net_salary:,.2f}\n\n"
                        "Please log in to the Employee Portal to view or download your payslip.\n\n"
                        "This is a system-generated email. Please do not reply.\n"
                    )
                    _send_email(recipient, subject, body)
                    now2 = datetime.utcnow()
                    slip.email_sent = True
                    slip.email_sent_at = now2
                    slip.emailed_at = now2
                    db.commit()
        except Exception as email_exc:
            _logger.warning("Payslip publish email failed for emp=%d: %s", employee_id, email_exc)

    return True


def bulk_publish_payslips(
    db: Session,
    run_id: int,
    published_by_id: Optional[int] = None,
    send_emails: bool = True,
) -> dict:
    """Publish ALL generated (but not yet published) payslips for a run.

    Returns {"published": N, "already_published": N, "failed": N}.

    This is a bulk confirmation operation — it should only be called after
    Finance Head has given final approval.  Once called, each payslip is
    individually locked (is_published=True).
    """
    import logging as _log
    _logger = _log.getLogger("hrms.payslip")

    slips = db.query(Payslip).filter_by(run_id=run_id).all()
    published = already_published = failed = 0

    for slip in slips:
        if slip.is_published:
            already_published += 1
            continue
        try:
            ok = publish_payslip(
                db,
                run_id=run_id,
                employee_id=slip.employee_id,
                published_by_id=published_by_id,
                send_email=send_emails,
            )
            if ok:
                published += 1
        except Exception as exc:
            _logger.warning(
                "bulk_publish_payslips: failed for emp_id=%d run_id=%d: %s",
                slip.employee_id, run_id, exc,
            )
            failed += 1

    _logger.info(
        "Bulk publish run_id=%d: published=%d, already_published=%d, failed=%d",
        run_id, published, already_published, failed,
    )
    return {"published": published, "already_published": already_published, "failed": failed}


def send_payslip_emails_for_run(db: Session, run_id: int) -> dict:
    """Send payslip emails to all published employees in a run.

    Returns {"sent": N, "failed": N, "skipped": N}.
    Uses the existing WorkHive email dispatcher. Employee email is resolved from
    employees.official_email first, then employees.email. No payroll email
    address is stored.
    """
    import logging
    from app.services.email_dispatcher import _send_email

    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        return {"sent": 0, "failed": 0, "skipped": 0}

    slips = db.query(Payslip).filter_by(run_id=run_id, is_published=True).all()
    sent = failed = skipped = 0
    logger = logging.getLogger("hrms.payslip")

    for slip in slips:
        emp = slip.employee
        recipient = ""
        if emp:
            recipient = (getattr(emp, "official_email", None) or emp.email or "").strip()
        if not emp or not recipient:
            skipped += 1
            continue
        if slip.email_sent or slip.emailed_at:
            skipped += 1
            continue
        try:
            subject = f"Your WorkHive payslip for {run.month_label} is published"
            body = (
                f"Hi {emp.first_name or ''},\n\n"
                f"Your payslip for {run.month_label} has been published in WorkHive HRMS.\n\n"
                f"Gross Pay: INR {slip.gross_salary:,.2f}\n"
                f"Total Deductions: INR {slip.total_deductions:,.2f}\n"
                f"Net Pay: INR {slip.net_salary:,.2f}\n\n"
                "Please sign in to WorkHive to view or download the detailed payslip.\n"
            )
            delivered = _send_email(recipient, subject, body)
            if delivered:
                now = datetime.utcnow()
                slip.email_sent = True
                slip.email_sent_at = now
                slip.emailed_at = now
                db.commit()
                sent += 1
            else:
                # Existing dispatcher may run in log-only mode when SMTP is not
                # configured. Do not fake emailed_at in that case.
                skipped += 1
        except Exception as exc:
            logger.warning(
                "Failed to send payslip email to %s: %s", recipient or "?", exc
            )
            failed += 1

    return {"sent": sent, "failed": failed, "skipped": skipped}


def generate_bank_advice_csv(db: Session, run_id: int) -> str:
    """Generate bank advice as CSV string for bulk salary transfer."""
    rows = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=run_id)
        .all()
    )
    lines = ["Employee Code,Employee Name,Bank Name,Account Number,IFSC Code,Net Salary"]
    for row in rows:
        emp = row.employee
        ss = db.query(SalaryStructure).filter_by(employee_id=row.employee_id).first()
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        bank = ss.bank_name if ss else ""
        acct = ss.account_number if ss else ""
        ifsc = ss.ifsc_code if ss else ""
        net = f"{row.net_pay:.2f}"
        lines.append(f"{emp_code},{emp_name},{bank},{acct},{ifsc},{net}")
    return "\n".join(lines)
