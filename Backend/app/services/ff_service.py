"""Final Settlement (Full & Final) Service.

PDF generation uses ReportLab when available; falls back to None.

Handles:
- Creating FF records (using existing employee_id ONLY — never creates employees)
- Auto-calculating FF components from HR records
- Approval workflow: draft → calculated → under_review → approved → paid | cancelled
- PDF-ready summary data
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums import TA_CENTER
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

from app.models.payroll_extended import FinalSettlement, Reimbursement
from app.models.payroll import SalaryStructure
from app.models.employee import Employee
from app.models.leave import LeaveBalance
from app.services.statutory_service import compute_gratuity


# ─── Status Machine ───────────────────────────────────────────────────────────

_FF_TRANSITIONS: dict[str, dict[str, str]] = {
    "draft":        {"calculate": "calculated", "cancel": "cancelled"},
    "calculated":   {"submit": "under_review", "recalculate": "calculated", "cancel": "cancelled"},
    "under_review": {"approve": "approved", "reject": "draft", "cancel": "cancelled"},
    "approved":     {"mark_paid": "paid"},
    "paid":         {},
    "cancelled":    {},
}


def _next_ff_status(current: str, action: str) -> Optional[str]:
    return _FF_TRANSITIONS.get(current, {}).get(action)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def create_ff(db: Session, data: dict, actor: Employee) -> FinalSettlement:
    """Create a new FF record for an existing employee."""
    employee_id = data["employee_id"]
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")

    # Prevent duplicate active FF for same employee
    existing = (
        db.query(FinalSettlement)
        .filter(
            FinalSettlement.employee_id == employee_id,
            FinalSettlement.status.notin_(["cancelled", "paid"]),
        )
        .first()
    )
    if existing:
        raise ValueError(
            f"An active Final Settlement (id={existing.id}) already exists for this employee."
        )

    ff = FinalSettlement(
        employee_id=employee_id,
        last_working_day=data.get("last_working_day"),
        separation_type=data.get("separation_type"),
        remarks=data.get("remarks"),
        status="draft",
        created_by_id=actor.id,
    )
    db.add(ff)
    db.commit()
    db.refresh(ff)
    return ff


def get_ff(db: Session, ff_id: int) -> Optional[FinalSettlement]:
    return (
        db.query(FinalSettlement)
        .options(joinedload(FinalSettlement.employee))
        .filter(FinalSettlement.id == ff_id)
        .first()
    )


def list_ff(db: Session, status: Optional[str] = None, employee_id: Optional[int] = None) -> list[FinalSettlement]:
    q = db.query(FinalSettlement).options(joinedload(FinalSettlement.employee))
    if status:
        q = q.filter(FinalSettlement.status == status)
    if employee_id:
        q = q.filter(FinalSettlement.employee_id == employee_id)
    return q.order_by(FinalSettlement.created_at.desc()).all()


def calculate_ff(db: Session, ff_id: int, overrides: dict, actor: Employee) -> FinalSettlement:
    """Compute all FF components and save. Overrides dict can supply manual values."""
    ff = db.query(FinalSettlement).filter(FinalSettlement.id == ff_id).first()
    if not ff:
        raise ValueError(f"Final settlement {ff_id} not found")
    if ff.status not in ("draft", "calculated"):
        raise ValueError(f"Cannot recalculate FF in status '{ff.status}'")

    emp = ff.employee
    if not emp:
        raise ValueError("Employee record not found")

    ss = db.query(SalaryStructure).filter_by(employee_id=ff.employee_id).first()
    basic_monthly = ss.basic if ss else 0.0
    gross_monthly = ss.gross_monthly if ss else 0.0

    last_working_day = ff.last_working_day or date.today()

    # ── Unpaid Salary ──
    if overrides.get("unpaid_salary") is not None:
        unpaid_salary = float(overrides["unpaid_salary"])
    else:
        # Compute for partial month based on last working day
        days_in_month = 30
        lwd = last_working_day
        worked_days = min(lwd.day, days_in_month)
        unpaid_salary = round(gross_monthly * worked_days / days_in_month, 2) if gross_monthly else 0.0

    # ── Leave Encashment ──
    if overrides.get("leave_encashment_days") is not None:
        leave_days = float(overrides["leave_encashment_days"])
    else:
        # Sum leave balances for all paid leave types.
        # Uses LeaveType.is_paid as the encashability proxy (no is_encashable column exists).
        # Available = current_balance - reserved (days approved but not yet consumed).
        balances = db.query(LeaveBalance).filter_by(employee_id=ff.employee_id).all()
        leave_days = sum(
            max(b.current_balance - b.reserved, 0)
            for b in balances
            if b.leave_type and b.leave_type.is_paid
        )

    daily_rate = round(basic_monthly / 26, 2)  # 26 working days standard
    leave_encashment_amount = round(daily_rate * leave_days, 2)

    # ── Gratuity ──
    gratuity_amount = 0.0
    gratuity_eligible = False
    if emp.date_of_joining and basic_monthly > 0:
        gratuity_amount = compute_gratuity(basic_monthly, emp.date_of_joining, last_working_day, db)
        gratuity_eligible = gratuity_amount > 0

    # ── Notice Period Recovery ──
    notice_days = int(overrides.get("notice_period_days", 0))
    notice_recovery = round(daily_rate * notice_days, 2) if notice_days > 0 else 0.0

    # ── Pending approved reimbursements auto-pull ──
    pending_reimb = (
        db.query(Reimbursement)
        .filter(
            Reimbursement.employee_id == ff.employee_id,
            Reimbursement.status == "approved",
            Reimbursement.paid_in_payroll_record_id.is_(None),
        )
        .all()
    )
    pending_reimbursements_amount = round(
        sum(r.approved_amount for r in pending_reimb), 2
    )

    # ── Other components from overrides ──
    bonus_pending = float(overrides.get("bonus_pending", 0.0))
    variable_pay_pending = float(overrides.get("variable_pay_pending", 0.0))
    other_earnings = float(overrides.get("other_earnings", 0.0))
    loan_recovery = float(overrides.get("loan_recovery", 0.0))
    advance_recovery = float(overrides.get("advance_recovery", 0.0))
    asset_recovery = float(overrides.get("asset_recovery", 0.0))
    other_deductions = float(overrides.get("other_deductions", 0.0))
    tds_on_settlement = float(overrides.get("tds_on_settlement", 0.0))

    # ── Totals ──
    gross_settlement = round(
        unpaid_salary + leave_encashment_amount + bonus_pending
        + variable_pay_pending + gratuity_amount + other_earnings
        + pending_reimbursements_amount,
        2,
    )
    total_deductions = round(
        notice_recovery + loan_recovery + advance_recovery
        + asset_recovery + other_deductions + tds_on_settlement,
        2,
    )
    net_payable = round(gross_settlement - total_deductions, 2)

    # ── Save ──
    ff.unpaid_salary = unpaid_salary
    ff.leave_encashment_days = leave_days
    ff.leave_encashment_amount = leave_encashment_amount
    ff.bonus_pending = bonus_pending
    ff.variable_pay_pending = variable_pay_pending
    ff.gratuity_eligible = gratuity_eligible
    ff.gratuity_amount = gratuity_amount
    ff.other_earnings = other_earnings
    ff.pending_reimbursements_amount = pending_reimbursements_amount
    ff.notice_period_days = notice_days
    ff.notice_period_recovery = notice_recovery
    ff.loan_recovery = loan_recovery
    ff.advance_recovery = advance_recovery
    ff.asset_recovery = asset_recovery
    ff.other_deductions = other_deductions
    ff.tds_on_settlement = tds_on_settlement
    ff.gross_settlement = gross_settlement
    ff.total_deductions = total_deductions
    ff.net_payable = net_payable
    ff.status = "calculated"

    db.commit()
    db.refresh(ff)
    return ff


def advance_ff_status(
    db: Session, ff_id: int, action: str, actor: Employee,
    remarks: Optional[str] = None,
    paid_date: Optional[date] = None,
    payment_reference: Optional[str] = None,
) -> FinalSettlement:
    ff = db.query(FinalSettlement).filter(FinalSettlement.id == ff_id).first()
    if not ff:
        raise ValueError(f"Final settlement {ff_id} not found")

    new_status = _next_ff_status(ff.status, action)
    if new_status is None:
        raise ValueError(f"Action '{action}' not valid from status '{ff.status}'")

    ff.status = new_status
    now = datetime.utcnow()

    if action == "approve":
        ff.approved_by_id = actor.id
        ff.approved_at = now
        if remarks:
            ff.remarks = remarks

    if action == "mark_paid":
        ff.paid_by_id = actor.id
        ff.paid_date = paid_date or date.today()
        ff.payment_reference = payment_reference

    db.commit()
    db.refresh(ff)
    return ff


# ─── FF to output dict ────────────────────────────────────────────────────────

def ff_to_dict(ff: FinalSettlement) -> dict:
    """Enrich FF with employee details for API response."""
    emp = ff.employee
    emp_name = f"{emp.first_name} {emp.last_name or ''}".strip() if emp else "—"
    dept = emp.department.name if emp and emp.department else "—"
    desig = emp.designation.title if emp and emp.designation else "—"
    emp_code = emp.employee_code if emp else None
    doj = emp.date_of_joining if emp else None

    approved_by = ff.approved_by
    approved_by_name = (
        f"{approved_by.first_name} {approved_by.last_name or ''}".strip()
        if approved_by else None
    )

    return {
        "id": ff.id,
        "employee_id": ff.employee_id,
        "employee_name": emp_name,
        "employee_code": emp_code,
        "department": dept,
        "designation": desig,
        "date_of_joining": doj,
        "last_working_day": ff.last_working_day,
        "separation_type": ff.separation_type,
        "unpaid_salary": ff.unpaid_salary,
        "leave_encashment_days": ff.leave_encashment_days,
        "leave_encashment_amount": ff.leave_encashment_amount,
        "bonus_pending": ff.bonus_pending,
        "variable_pay_pending": ff.variable_pay_pending,
        "gratuity_eligible": ff.gratuity_eligible,
        "gratuity_amount": ff.gratuity_amount,
        "other_earnings": ff.other_earnings,
        "pending_reimbursements_amount": getattr(ff, "pending_reimbursements_amount", 0.0),
        "notice_period_days": ff.notice_period_days,
        "notice_period_recovery": ff.notice_period_recovery,
        "loan_recovery": ff.loan_recovery,
        "advance_recovery": ff.advance_recovery,
        "asset_recovery": getattr(ff, "asset_recovery", 0.0),
        "other_deductions": ff.other_deductions,
        "tds_on_settlement": ff.tds_on_settlement,
        "gross_settlement": ff.gross_settlement,
        "total_deductions": ff.total_deductions,
        "net_payable": ff.net_payable,
        "status": ff.status,
        "remarks": ff.remarks,
        "approved_by_id": ff.approved_by_id,
        "approved_by_name": approved_by_name,
        "approved_at": ff.approved_at,
        "paid_date": ff.paid_date,
        "payment_reference": ff.payment_reference,
        "created_at": ff.created_at,
        "updated_at": ff.updated_at,
    }


# ─── FF PDF Generation ────────────────────────────────────────────────────────

def generate_ff_pdf(ff: FinalSettlement, company_name: str = "Acronotics Inc.") -> Optional[bytes]:
    """Generate a Full & Final Settlement PDF. Returns None if ReportLab unavailable."""
    if not _REPORTLAB_AVAILABLE:
        return None

    data = ff_to_dict(ff)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )
    styles = getSampleStyleSheet()
    brand = colors.HexColor("#1e40af")
    light_gray = colors.HexColor("#f1f5f9")
    story = []

    title_style = styles["Heading1"]
    title_style.textColor = brand
    title_style.alignment = TA_CENTER

    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph("Full & Final Settlement Statement", styles["Heading2"]))
    story.append(Spacer(1, 6*mm))

    # Employee info table
    emp_rows = [
        ["Employee", data["employee_name"], "Employee Code", data["employee_code"] or "—"],
        ["Department", data["department"], "Designation", data["designation"]],
        ["Date of Joining", str(data["date_of_joining"] or "—"), "Last Working Day", str(data["last_working_day"] or "—")],
        ["Separation Type", (data["separation_type"] or "—").replace("_", " ").title(), "Status", data["status"].upper()],
    ]
    emp_table = Table(emp_rows, colWidths=[45*mm, 55*mm, 45*mm, 45*mm])
    emp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), light_gray),
        ("BACKGROUND", (2, 0), (2, -1), light_gray),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 6*mm))

    # Earnings & Deductions
    def _inr(v):
        return f"₹{float(v or 0):,.2f}"

    earnings = [
        ["EARNINGS", "Amount"],
        ["Unpaid Salary", _inr(data["unpaid_salary"])],
        [f"Leave Encashment ({data['leave_encashment_days']:.1f} days)", _inr(data["leave_encashment_amount"])],
        ["Bonus Pending", _inr(data["bonus_pending"])],
        ["Variable Pay Pending", _inr(data["variable_pay_pending"])],
        [f"Gratuity ({'Eligible' if data['gratuity_eligible'] else 'Not Eligible'})", _inr(data["gratuity_amount"])],
        ["Pending Reimbursements", _inr(data.get("pending_reimbursements_amount", 0))],
        ["Other Earnings", _inr(data["other_earnings"])],
        ["Gross Settlement", _inr(data["gross_settlement"])],
    ]
    deductions = [
        ["DEDUCTIONS", "Amount"],
        [f"Notice Period Recovery ({data['notice_period_days']} days)", _inr(data["notice_period_recovery"])],
        ["Loan Recovery", _inr(data["loan_recovery"])],
        ["Advance Recovery", _inr(data["advance_recovery"])],
        ["Asset Recovery", _inr(data.get("asset_recovery", 0))],
        ["Other Deductions", _inr(data["other_deductions"])],
        ["TDS on Settlement", _inr(data["tds_on_settlement"])],
        ["Total Deductions", _inr(data["total_deductions"])],
        ["", ""],
    ]
    combined = []
    for i in range(max(len(earnings), len(deductions))):
        e = earnings[i] if i < len(earnings) else ["", ""]
        d = deductions[i] if i < len(deductions) else ["", ""]
        combined.append(e + d)

    col_w = [65*mm, 30*mm, 65*mm, 30*mm]
    fin_table = Table(combined, colWidths=col_w)
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (1, 0), brand),
        ("BACKGROUND", (2, 0), (3, 0), colors.HexColor("#dc2626")),
        ("TEXTCOLOR", (0, 0), (3, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, -1), (1, -1), colors.HexColor("#dbeafe")),
        ("BACKGROUND", (2, -1), (3, -1), colors.HexColor("#fee2e2")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 6*mm))

    # Net Payable highlight
    net_row = [["NET FINAL PAYABLE", _inr(data["net_payable"])]]
    net_table = Table(net_row, colWidths=[140*mm, 50*mm])
    net_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#059669")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 3*mm))

    # Approval footer
    footer_text = (
        f"Approved by: {data.get('approved_by_name') or '—'}  |  "
        f"Approved at: {str(data.get('approved_at') or '—')[:16]}  |  "
        f"Paid date: {data.get('paid_date') or '—'}  |  "
        f"Payment ref: {data.get('payment_reference') or '—'}"
    )
    story.append(Paragraph(footer_text, styles["Normal"]))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "This is a computer-generated statement and does not require a physical signature.",
        styles["Italic"]
    ))

    doc.build(story)
    return buffer.getvalue()
