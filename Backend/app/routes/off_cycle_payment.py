"""Off-Cycle Payment API.

Prefix : /finance
Auth   : admin/hr view, finance manages docs+payment, finance_head approves/rejects/returns

Status flow
-----------
approved_off_cycle  (created by bonus_request head-approve for off_cycle mode)
    → Finance: generate payslip  → payslip_path set
    → Finance: generate bank advice → bank_advice_path set
    → When both docs exist: status = payment_ready
    → Finance: mark-paid → status = paid

Finance Head can: return (→ approved_off_cycle, clears docs) | reject (terminal)

Invariant: OffCyclePayment NEVER touches payroll_runs, payroll_adjustments, or monthly payroll.

Endpoints
---------
POST   /finance/off-cycle-payments                           Internal: create from bonus request (admin/hr)
GET    /finance/off-cycle-payments                           List (all roles)
GET    /finance/off-cycle-payments/{id}                      Get single
GET    /finance/off-cycle-payments/{id}/audit               Audit log
POST   /finance/off-cycle-payments/{id}/generate-payslip    Finance: generate payslip PDF
GET    /finance/off-cycle-payments/{id}/payslip/pdf         Download payslip PDF
POST   /finance/off-cycle-payments/{id}/generate-bank-advice Finance: generate bank advice
GET    /finance/off-cycle-payments/{id}/bank-advice         Download bank advice
POST   /finance/off-cycle-payments/{id}/mark-paid           Finance: confirm payment
POST   /finance/off-cycle-payments/{id}/return              Finance Head: return for rework
POST   /finance/off-cycle-payments/{id}/reject              Finance Head: reject
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.models.off_cycle_payment import OffCycleAuditLog, OffCyclePayment

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/finance",
    tags=["Finance - Off-Cycle Payments"],
    dependencies=[Depends(role_required("admin", "hr", "finance", "finance_head"))],
)

_CreateActor   = Depends(role_required("admin", "hr"))
_ReadActor     = Depends(role_required("admin", "hr", "finance", "finance_head"))
_FinanceActor  = Depends(role_required("finance"))
_HeadActor     = Depends(role_required("finance_head"))
_FinanceOrHead = Depends(role_required("finance", "finance_head"))

STATUS_APPROVED   = "approved_off_cycle"
STATUS_READY      = "payment_ready"
STATUS_PAID       = "paid"
STATUS_REJECTED   = "rejected"

# Off-cycle payslips are stored outside the main payslips/ dir to avoid confusion
_OFF_CYCLE_DIR = Path(os.getenv("OFF_CYCLE_DIR", "./off_cycle_payslips"))

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# ── PDF deps ──────────────────────────────────────────────────────────────────
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    )
    _REPORTLAB = True
except ImportError:
    _REPORTLAB = False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _emp_name(emp: Employee) -> str:
    return f"{emp.first_name} {emp.last_name or ''}".strip()


def _ensure_dir() -> None:
    _OFF_CYCLE_DIR.mkdir(parents=True, exist_ok=True)


def _audit(
    db: Session,
    payment: OffCyclePayment,
    actor_id: int | None,
    action: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
) -> None:
    db.add(OffCycleAuditLog(
        off_cycle_payment_id=payment.id,
        actor_id=actor_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=note,
    ))


def _serialize(ocp: OffCyclePayment) -> dict:
    emp = ocp.employee
    return {
        "id":                 ocp.id,
        "bonus_request_id":   ocp.bonus_request_id,
        "employee_id":        ocp.employee_id,
        "employee_name":      _emp_name(emp) if emp else str(ocp.employee_id),
        "employee_code":      (emp.employee_code or f"EMP{ocp.employee_id:04d}") if emp else "",
        "bonus_type":         ocp.bonus_type,
        "amount":             ocp.amount,
        "reason":             ocp.reason,
        "payment_status":     ocp.payment_status,
        "approved_by_id":     ocp.approved_by_id,
        "approved_by_name":   _emp_name(ocp.approved_by) if ocp.approved_by else None,
        "approved_date":      ocp.approved_date.isoformat() if ocp.approved_date else None,
        "payslip_path":       ocp.payslip_path,
        "bank_advice_path":   ocp.bank_advice_path,
        "paid_by_id":         ocp.paid_by_id,
        "paid_by_name":       _emp_name(ocp.paid_by) if ocp.paid_by else None,
        "paid_date":          ocp.paid_date.isoformat() if ocp.paid_date else None,
        "remarks":            ocp.remarks,
        "reference_number":   ocp.reference_number,
        "payslip_generated":  ocp.payslip_path is not None,
        "bank_advice_generated": ocp.bank_advice_path is not None,
        "created_at":         ocp.created_at.isoformat() if ocp.created_at else None,
        "updated_at":         ocp.updated_at.isoformat() if ocp.updated_at else None,
    }


def _fmt_inr(amount: float) -> str:
    return f"₹{amount:,.2f}"


# ─── PDF: Off-Cycle Payslip ───────────────────────────────────────────────────

def _generate_payslip_pdf(ocp: OffCyclePayment) -> bytes | None:
    if not _REPORTLAB:
        return None

    emp = ocp.employee
    if not emp:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("header", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14)
    sub_style    = ParagraphStyle("sub",    parent=styles["Normal"],   alignment=TA_CENTER, fontSize=10)
    label_style  = ParagraphStyle("label",  parent=styles["Normal"],   fontSize=9, textColor=colors.HexColor("#64748b"))
    value_style  = ParagraphStyle("value",  parent=styles["Normal"],   fontSize=9, fontName="Helvetica-Bold")
    amount_style = ParagraphStyle("amount", parent=styles["Normal"],   fontSize=14,
                                  fontName="Helvetica-Bold", textColor=colors.HexColor("#059669"), alignment=TA_CENTER)

    BRAND = colors.HexColor("#7c3aed")

    elems = []

    # Header
    elems.append(Paragraph("Acronotics Inc.", header_style))
    elems.append(Paragraph("Off-Cycle Bonus Payment — Payslip", sub_style))
    elems.append(Spacer(1, 6 * mm))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=BRAND))
    elems.append(Spacer(1, 4 * mm))

    # Employee info table
    bank_name = getattr(emp, "bank_name", None) or "—"
    account_raw = getattr(emp, "bank_account_encrypted", None) or ""
    account_display = f"****{account_raw[-4:]}" if len(account_raw) >= 4 else "—"
    bank_ifsc  = getattr(emp, "bank_ifsc", None) or "—"
    dept_name  = (emp.department.name if emp and emp.department else "—")
    desig_name = (emp.designation.title if emp and emp.designation else "—")

    info_data = [
        [Paragraph("Employee Name", label_style), Paragraph(_emp_name(emp), value_style),
         Paragraph("Payment Mode", label_style),  Paragraph("Off-Cycle", value_style)],
        [Paragraph("Employee Code", label_style), Paragraph(emp.employee_code or "—", value_style),
         Paragraph("Payment Date", label_style),  Paragraph(
             ocp.paid_date.strftime("%d %b %Y") if ocp.paid_date else "—", value_style)],
        [Paragraph("Department", label_style),    Paragraph(dept_name, value_style),
         Paragraph("Designation", label_style),   Paragraph(desig_name, value_style)],
        [Paragraph("Bank Name", label_style),     Paragraph(bank_name, value_style),
         Paragraph("IFSC Code", label_style),     Paragraph(bank_ifsc, value_style)],
        [Paragraph("Account No.", label_style),   Paragraph(account_display, value_style),
         Paragraph("Reference No.", label_style), Paragraph(ocp.reference_number or "—", value_style)],
    ]
    info_table = Table(info_data, colWidths=[40 * mm, 60 * mm, 40 * mm, 60 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(info_table)
    elems.append(Spacer(1, 6 * mm))

    # Bonus details table
    approved_by_name = _emp_name(ocp.approved_by) if ocp.approved_by else "—"
    approved_date    = ocp.approved_date.strftime("%d %b %Y") if ocp.approved_date else "—"

    bonus_data = [
        [Paragraph("<b>Bonus Details</b>", styles["Normal"]), ""],
        [Paragraph("Bonus Type", label_style),    Paragraph(ocp.bonus_type, value_style)],
        [Paragraph("Amount", label_style),        Paragraph(_fmt_inr(ocp.amount), value_style)],
        [Paragraph("Approved By", label_style),   Paragraph(approved_by_name, value_style)],
        [Paragraph("Approved Date", label_style), Paragraph(approved_date, value_style)],
    ]
    if ocp.reason:
        bonus_data.append([Paragraph("Reason", label_style), Paragraph(ocp.reason, value_style)])

    bonus_table = Table(bonus_data, colWidths=[60 * mm, 140 * mm])
    bonus_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(bonus_table)
    elems.append(Spacer(1, 8 * mm))

    # Net amount box
    elems.append(Table(
        [[Paragraph(f"Net Off-Cycle Payment: {_fmt_inr(ocp.amount)}", amount_style)]],
        colWidths=[200 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ecfdf5")),
            ("BOX", (0, 0), (0, 0), 1.5, colors.HexColor("#059669")),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (0, 0), (0, 0), 10),
        ]),
    ))
    elems.append(Spacer(1, 6 * mm))

    # Footer note
    note_style = ParagraphStyle("note", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER)
    elems.append(Paragraph(
        "This is a system-generated off-cycle payslip. "
        "This payment is separate from monthly payroll and does not affect Annual CTC.",
        note_style,
    ))

    doc.build(elems)
    return buf.getvalue()


# ─── PDF: Off-Cycle Bank Advice ───────────────────────────────────────────────

def _generate_bank_advice_pdf(ocp: OffCyclePayment) -> bytes | None:
    if not _REPORTLAB:
        return None

    emp = ocp.employee
    if not emp:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("h", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14)
    sub_style    = ParagraphStyle("s", parent=styles["Normal"],   alignment=TA_CENTER, fontSize=10)
    label_style  = ParagraphStyle("l", parent=styles["Normal"],   fontSize=9, textColor=colors.HexColor("#64748b"))
    value_style  = ParagraphStyle("v", parent=styles["Normal"],   fontSize=9, fontName="Helvetica-Bold")
    amount_style = ParagraphStyle("a", parent=styles["Normal"],   fontSize=13,
                                  fontName="Helvetica-Bold", textColor=colors.HexColor("#059669"), alignment=TA_CENTER)

    BRAND = colors.HexColor("#7c3aed")

    elems = []
    elems.append(Paragraph("Acronotics Inc.", header_style))
    elems.append(Paragraph("Off-Cycle Bonus — Bank Advice", sub_style))
    elems.append(Spacer(1, 4 * mm))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=BRAND))
    elems.append(Spacer(1, 5 * mm))

    bank_name      = getattr(emp, "bank_name", None) or "—"
    account_raw    = getattr(emp, "bank_account_encrypted", None) or ""
    account_display = account_raw if account_raw else "—"
    bank_ifsc      = getattr(emp, "bank_ifsc", None) or "—"
    dept_name      = (emp.department.name if emp and emp.department else "—")

    advice_data = [
        [Paragraph("<b>Bank Transfer Details</b>", styles["Normal"]), ""],
        [Paragraph("Employee Name",   label_style), Paragraph(_emp_name(emp), value_style)],
        [Paragraph("Employee Code",   label_style), Paragraph(emp.employee_code or "—", value_style)],
        [Paragraph("Department",      label_style), Paragraph(dept_name, value_style)],
        [Paragraph("Bank Name",       label_style), Paragraph(bank_name, value_style)],
        [Paragraph("Account Number",  label_style), Paragraph(account_display, value_style)],
        [Paragraph("IFSC Code",       label_style), Paragraph(bank_ifsc, value_style)],
        [Paragraph("Bonus Type",      label_style), Paragraph(ocp.bonus_type, value_style)],
        [Paragraph("Amount",          label_style), Paragraph(_fmt_inr(ocp.amount), value_style)],
        [Paragraph("Reference Number", label_style), Paragraph(ocp.reference_number or "—", value_style)],
        [Paragraph("Payment Mode",    label_style), Paragraph("Off-Cycle (NEFT/RTGS/IMPS)", value_style)],
        [Paragraph("Generated On",    label_style),
         Paragraph(datetime.utcnow().strftime("%d %b %Y %H:%M UTC"), value_style)],
    ]
    advice_table = Table(advice_data, colWidths=[70 * mm, 130 * mm])
    advice_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(advice_table)
    elems.append(Spacer(1, 8 * mm))

    elems.append(Table(
        [[Paragraph(f"Transfer Amount: {_fmt_inr(ocp.amount)}", amount_style)]],
        colWidths=[200 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ecfdf5")),
            ("BOX", (0, 0), (0, 0), 1.5, colors.HexColor("#059669")),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (0, 0), (0, 0), 10),
        ]),
    ))
    elems.append(Spacer(1, 6 * mm))

    note_style = ParagraphStyle("note", parent=styles["Normal"], fontSize=7,
                                textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER)
    elems.append(Paragraph(
        "This bank advice is for Finance/HR reference only. "
        "The system does not initiate bank transfers. "
        "Upload this file to your bank portal to process the payment.",
        note_style,
    ))
    doc.build(elems)
    return buf.getvalue()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class CreateOffCyclePayload(BaseModel):
    bonus_request_id: Optional[int] = None
    employee_id:      int
    bonus_type:       str
    amount:           float
    reason:           Optional[str] = None
    approved_by_id:   Optional[int] = None
    approved_date:    Optional[datetime] = None


class MarkPaidPayload(BaseModel):
    remarks:          Optional[str] = None
    paid_date:        Optional[datetime] = None


class ReturnPayload(BaseModel):
    note: Optional[str] = None


class RejectPayload(BaseModel):
    note: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/off-cycle-payments", status_code=201)
def create_off_cycle_payment(
    body:  CreateOffCyclePayload,
    db:    Session  = Depends(get_db),
    actor: Employee = _CreateActor,
):
    """Create an off-cycle payment record (called by HR after bonus approval or directly)."""
    emp = db.get(Employee, body.employee_id)
    if not emp or getattr(emp, "is_deleted", False):
        raise HTTPException(404, "Employee not found")

    ref = f"OCP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    ocp = OffCyclePayment(
        bonus_request_id=body.bonus_request_id,
        employee_id=body.employee_id,
        bonus_type=body.bonus_type,
        amount=body.amount,
        reason=body.reason,
        payment_status=STATUS_APPROVED,
        approved_by_id=body.approved_by_id,
        approved_date=body.approved_date or datetime.utcnow(),
        reference_number=ref,
    )
    db.add(ocp)
    db.flush()
    _audit(db, ocp, actor.id, "created", None, STATUS_APPROVED,
           f"Off-cycle payment created for {body.bonus_type} ₹{body.amount:,.2f}")
    db.commit()
    db.refresh(ocp)
    return _serialize(ocp)


@router.get("/off-cycle-payments")
def list_off_cycle_payments(
    status_filter: Optional[str] = None,
    employee_id:   Optional[int] = None,
    limit:         int = 200,
    db:    Session  = Depends(get_db),
    _:     Employee = _ReadActor,
):
    q = db.query(OffCyclePayment)
    if status_filter:
        q = q.filter(OffCyclePayment.payment_status == status_filter)
    if employee_id:
        q = q.filter(OffCyclePayment.employee_id == employee_id)
    return [_serialize(r) for r in q.order_by(OffCyclePayment.created_at.desc()).limit(limit)]


@router.get("/off-cycle-payments/pending-count")
def off_cycle_pending_count(
    db: Session  = Depends(get_db),
    _:  Employee = _ReadActor,
):
    count = (
        db.query(OffCyclePayment)
        .filter(OffCyclePayment.payment_status.in_([STATUS_APPROVED, STATUS_READY]))
        .count()
    )
    return {"pending_count": count}


@router.get("/off-cycle-payments/{ocp_id}")
def get_off_cycle_payment(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    _:      Employee = _ReadActor,
):
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    return _serialize(ocp)


@router.get("/off-cycle-payments/{ocp_id}/audit")
def get_audit_log(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    _:      Employee = _ReadActor,
):
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    logs = (
        db.query(OffCycleAuditLog)
        .filter(OffCycleAuditLog.off_cycle_payment_id == ocp_id)
        .order_by(OffCycleAuditLog.created_at.asc())
        .all()
    )
    return [
        {
            "id":          lg.id,
            "actor_id":    lg.actor_id,
            "actor_name":  _emp_name(lg.actor) if lg.actor else None,
            "action":      lg.action,
            "from_status": lg.from_status,
            "to_status":   lg.to_status,
            "note":        lg.note,
            "created_at":  lg.created_at.isoformat() if lg.created_at else None,
        }
        for lg in logs
    ]


@router.post("/off-cycle-payments/{ocp_id}/generate-payslip")
def generate_payslip(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    actor:  Employee = _FinanceActor,
):
    """Finance: generate the off-cycle payslip PDF and store it on disk."""
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    if ocp.payment_status not in (STATUS_APPROVED, STATUS_READY):
        raise HTTPException(400, f"Cannot generate payslip in status '{ocp.payment_status}'")

    pdf_bytes = _generate_payslip_pdf(ocp)

    _ensure_dir()
    filename = f"ocp_{ocp_id}_payslip_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    filepath = _OFF_CYCLE_DIR / filename

    if pdf_bytes:
        filepath.write_bytes(pdf_bytes)
        ocp.payslip_path = str(filepath)
    else:
        # ReportLab unavailable — store a sentinel path so status can progress
        ocp.payslip_path = f"__no_pdf__/ocp_{ocp_id}_payslip.pdf"

    _maybe_advance_to_ready(ocp)
    _audit(db, ocp, actor.id, "payslip_generated", None, ocp.payment_status,
           f"Payslip generated: {ocp.payslip_path}")
    db.commit()
    db.refresh(ocp)
    return _serialize(ocp)


@router.get("/off-cycle-payments/{ocp_id}/payslip/pdf")
def download_payslip(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    _:      Employee = _ReadActor,
):
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp or not ocp.payslip_path:
        raise HTTPException(404, "Payslip not generated yet")
    if ocp.payslip_path.startswith("__no_pdf__"):
        raise HTTPException(503, "PDF generation unavailable (ReportLab not installed)")

    path = Path(ocp.payslip_path)
    if not path.exists():
        raise HTTPException(404, "Payslip file not found on disk")

    emp_name_slug = _emp_name(ocp.employee).replace(" ", "_") if ocp.employee else "employee"
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="off_cycle_payslip_{emp_name_slug}_{ocp_id}.pdf"'},
    )


@router.post("/off-cycle-payments/{ocp_id}/generate-bank-advice")
def generate_bank_advice(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    actor:  Employee = _FinanceActor,
):
    """Finance: generate the bank advice PDF and store it on disk."""
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    if ocp.payment_status not in (STATUS_APPROVED, STATUS_READY):
        raise HTTPException(400, f"Cannot generate bank advice in status '{ocp.payment_status}'")

    pdf_bytes = _generate_bank_advice_pdf(ocp)

    _ensure_dir()
    filename = f"ocp_{ocp_id}_bank_advice_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    filepath = _OFF_CYCLE_DIR / filename

    if pdf_bytes:
        filepath.write_bytes(pdf_bytes)
        ocp.bank_advice_path = str(filepath)
    else:
        ocp.bank_advice_path = f"__no_pdf__/ocp_{ocp_id}_bank_advice.pdf"

    _maybe_advance_to_ready(ocp)
    _audit(db, ocp, actor.id, "bank_advice_generated", None, ocp.payment_status,
           f"Bank advice generated: {ocp.bank_advice_path}")
    db.commit()
    db.refresh(ocp)
    return _serialize(ocp)


@router.get("/off-cycle-payments/{ocp_id}/bank-advice")
def download_bank_advice(
    ocp_id: int,
    db:     Session  = Depends(get_db),
    _:      Employee = _ReadActor,
):
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp or not ocp.bank_advice_path:
        raise HTTPException(404, "Bank advice not generated yet")
    if ocp.bank_advice_path.startswith("__no_pdf__"):
        raise HTTPException(503, "PDF generation unavailable (ReportLab not installed)")

    path = Path(ocp.bank_advice_path)
    if not path.exists():
        raise HTTPException(404, "Bank advice file not found on disk")

    emp_name_slug = _emp_name(ocp.employee).replace(" ", "_") if ocp.employee else "employee"
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="off_cycle_bank_advice_{emp_name_slug}_{ocp_id}.pdf"'},
    )


@router.post("/off-cycle-payments/{ocp_id}/mark-paid")
def mark_paid(
    ocp_id: int,
    body:   MarkPaidPayload = MarkPaidPayload(),
    db:     Session  = Depends(get_db),
    actor:  Employee = _FinanceActor,
):
    """Finance: confirm that payment has been made manually via bank upload."""
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    if ocp.payment_status not in (STATUS_APPROVED, STATUS_READY):
        raise HTTPException(400, f"Cannot mark paid in status '{ocp.payment_status}'")

    prev = ocp.payment_status
    ocp.payment_status = STATUS_PAID
    ocp.paid_by_id     = actor.id
    ocp.paid_date      = body.paid_date or datetime.utcnow()
    ocp.remarks        = body.remarks

    _audit(db, ocp, actor.id, "mark_paid", prev, STATUS_PAID,
           body.remarks or "Payment confirmed by Finance")
    db.commit()
    db.refresh(ocp)
    logger.info(
        "[OffCycle] Payment %d marked PAID by employee %d (₹%.2f, %s)",
        ocp.id, actor.id, ocp.amount, ocp.bonus_type,
    )
    return _serialize(ocp)


@router.post("/off-cycle-payments/{ocp_id}/return")
def return_payment(
    ocp_id: int,
    body:   ReturnPayload = ReturnPayload(),
    db:     Session  = Depends(get_db),
    actor:  Employee = _HeadActor,
):
    """Finance Head: return for rework (clears docs, resets to approved_off_cycle)."""
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    if ocp.payment_status not in (STATUS_APPROVED, STATUS_READY):
        raise HTTPException(400, f"Cannot return in status '{ocp.payment_status}'")

    prev = ocp.payment_status
    ocp.payment_status   = STATUS_APPROVED
    ocp.payslip_path     = None
    ocp.bank_advice_path = None

    _audit(db, ocp, actor.id, "returned", prev, STATUS_APPROVED,
           body.note or "Returned for rework by Finance Head")
    db.commit()
    db.refresh(ocp)
    return _serialize(ocp)


@router.post("/off-cycle-payments/{ocp_id}/reject")
def reject_payment(
    ocp_id: int,
    body:   RejectPayload = RejectPayload(),
    db:     Session  = Depends(get_db),
    actor:  Employee = _HeadActor,
):
    """Finance Head: permanently reject the off-cycle payment."""
    ocp = db.get(OffCyclePayment, ocp_id)
    if not ocp:
        raise HTTPException(404, "Off-cycle payment not found")
    if ocp.payment_status in (STATUS_PAID, STATUS_REJECTED):
        raise HTTPException(400, f"Cannot reject in status '{ocp.payment_status}'")

    prev = ocp.payment_status
    ocp.payment_status = STATUS_REJECTED

    _audit(db, ocp, actor.id, "rejected", prev, STATUS_REJECTED,
           body.note or "Rejected by Finance Head")
    db.commit()
    db.refresh(ocp)
    return _serialize(ocp)


# ─── Internal helper ──────────────────────────────────────────────────────────

def _maybe_advance_to_ready(ocp: OffCyclePayment) -> None:
    """Advance to payment_ready when both documents exist."""
    if (
        ocp.payment_status == STATUS_APPROVED
        and ocp.payslip_path
        and ocp.bank_advice_path
    ):
        ocp.payment_status = STATUS_READY


# ─── Internal creation helper (called from bonus_request head-approve) ────────

def create_off_cycle_payment_from_bonus(
    db:         Session,
    bonus_req,          # BonusRequest ORM instance
    actor_id:   int,
) -> OffCyclePayment:
    """Create an OffCyclePayment when Finance Head approves an off_cycle BonusRequest."""
    ref = f"OCP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    ocp = OffCyclePayment(
        bonus_request_id=bonus_req.id,
        employee_id=bonus_req.employee_id,
        bonus_type=bonus_req.bonus_type,
        amount=bonus_req.amount,
        reason=bonus_req.reason,
        payment_status=STATUS_APPROVED,
        approved_by_id=actor_id,
        approved_date=datetime.utcnow(),
        reference_number=ref,
    )
    db.add(ocp)
    db.flush()
    db.add(OffCycleAuditLog(
        off_cycle_payment_id=ocp.id,
        actor_id=actor_id,
        action="created_from_bonus_request",
        from_status=None,
        to_status=STATUS_APPROVED,
        note=f"Auto-created from BonusRequest #{bonus_req.id} ({bonus_req.bonus_type} ₹{bonus_req.amount:,.2f})",
    ))
    return ocp
