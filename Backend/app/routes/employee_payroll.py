"""Employee self-service payroll routes.

All endpoints require the authenticated employee to be active.
Employees can only see/modify their own data.
Prefix: /employee/payroll
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.employee import Employee
from app.models.payroll_extended import Payslip, Reimbursement, EmployeeTaxDeclaration
from app.models.payroll import PayrollRun, PayrollRunEmployee, SalaryStructure
from app.services import payslip_service, payroll_service


def _month_label_from_parts(month: int, year: int) -> str:
    return payroll_service.payroll_month_label(date(year, month, 1))


def _payslip_month_label(slip: Payslip) -> str:
    return payroll_service.payroll_month_label(slip.pay_period_start)

router = APIRouter(
    prefix="/employee/payroll",
    tags=["Employee Payroll (ESS)"],
)

CurrentUser = Depends(get_current_user)


# ─── Payslips ─────────────────────────────────────────────────────────────────

@router.get("/payslips", summary="List my published payslips")
def my_payslips(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    slips = (
        db.query(Payslip)
        .join(PayrollRun, PayrollRun.id == Payslip.run_id)
        .filter(
            Payslip.employee_id == current.id,
            or_(
                Payslip.is_published.is_(True),
                PayrollRun.status.in_(["approved", "completed", "disbursed"]),
            ),
        )
        .order_by(Payslip.pay_period_start.desc())
        .all()
    )
    result = []
    for s in slips:
        result.append({
            "id": s.id,
            "run_id": s.run_id,
            "month_label": _payslip_month_label(s),
            "pay_period_start": s.pay_period_start,
            "pay_period_end": s.pay_period_end,
            "gross_salary": s.gross_salary,
            "total_deductions": s.total_deductions,
            "net_salary": s.net_salary,
            "is_published": s.is_published,
            "published_at": s.published_at,
            "pdf_available": s.pdf_path is not None or True,
        })
    return result


@router.get("/payslips/{run_id}/detail", summary="My payslip breakdown for a run")
def my_payslip_detail(
    run_id: int,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=current.id).first()
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not slip:
        raise HTTPException(status_code=404, detail="Payslip not found or not yet published")
    run_is_published = run and run.status in ("approved", "completed", "disbursed")
    if not slip.is_published and not run_is_published:
        raise HTTPException(status_code=403, detail="Payslip not yet published")

    row = db.query(PayrollRunEmployee).filter_by(run_id=run_id, employee_id=current.id).first()

    earnings = {}
    deductions = {}
    attendance_summary = None
    if row:
        earning_components = payroll_service.payslip_earning_components(row)
        attendance_summary = payroll_service.payslip_attendance_summary(row)
        earnings = {c["label"]: c["amount"] for c in earning_components}
        earnings["Gross Salary"] = row.gross_earnings
        deductions = {
            "PF (Employee)": row.employee_pf,
            "ESI (Employee)": row.employee_esi,
            "Professional Tax": row.professional_tax,
            "TDS": row.tds,
            "Other Deductions": row.other_deductions,
            "Total Deductions": row.total_deductions,
        }

    return {
        "run_id": run_id,
        "month_label": _payslip_month_label(slip),
        "pay_period": f"{slip.pay_period_start} to {slip.pay_period_end}",
        "gross_salary": slip.gross_salary,
        "total_deductions": slip.total_deductions,
        "net_salary": slip.net_salary,
        "earnings": earnings,
        "deductions": deductions,
        "working_days": attendance_summary["working_days"] if attendance_summary else None,
        "present_days": attendance_summary["present_days"] if attendance_summary else None,
        "leave_days": attendance_summary["leave_days"] if attendance_summary else None,
        "holiday_days": attendance_summary["holiday_days"] if attendance_summary else None,
        "lop_days": attendance_summary["lop_days"] if attendance_summary else None,
        "attendance_reconciled": (
            attendance_summary["attendance_reconciled"] if attendance_summary else True
        ),
        "attendance_reconciliation_delta": (
            attendance_summary["attendance_reconciliation_delta"] if attendance_summary else 0
        ),
        "earnings_total": payroll_service.payslip_earnings_total(row) if row else 0.0,
        "earnings_reconciliation_delta": (
            payroll_service.payslip_earnings_reconciliation_delta(row) if row else 0.0
        ),
        "published_at": slip.published_at,
    }


@router.get("/payslips/{run_id}/pdf", summary="Download my payslip PDF")
def my_payslip_pdf(
    run_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=current.id).first()
    if not slip:
        raise HTTPException(status_code=404, detail="Payslip not found")
    run_pdf = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    run_is_published_pdf = run_pdf and run_pdf.status in ("approved", "completed", "disbursed")
    if not slip.is_published and not run_is_published_pdf:
        raise HTTPException(status_code=403, detail="Payslip not yet published")

    pdf_bytes = payslip_service.generate_payslip_pdf(db, run_id, current.id)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=503,
            detail="PDF generation unavailable. Contact HR to download your payslip."
        )

    # Record the download in the immutable audit trail
    try:
        ip_addr = None
        ua = None
        if request is not None:
            ip_addr = request.client.host if request.client else None
            ua = request.headers.get("user-agent", "")[:500]
        payslip_service.record_payslip_download(
            db=db,
            payslip_id=slip.id,
            employee_id=current.id,
            downloaded_by_id=current.id,
            ip_address=ip_addr,
            user_agent=ua,
            download_source="employee_self_service",
        )
    except Exception:
        pass  # Audit failure must never block the download

    emp_name = f"{current.first_name}_{current.last_name or ''}".strip("_")
    month = _payslip_month_label(slip).replace(" ", "_") if slip else f"run{run_id}"
    filename = f"payslip_{emp_name}_{month}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── YTD Summary ──────────────────────────────────────────────────────────────

@router.get("/ytd-summary", summary="Year-to-date salary summary")
def ytd_summary(
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    from app.models.payroll_extended import TaxDeduction
    if not financial_year:
        from datetime import date
        today = date.today()
        fy_start = today.year if today.month >= 4 else today.year - 1
        financial_year = f"{fy_start}-{str(fy_start + 1)[-2:]}"

    td_rows = (
        db.query(TaxDeduction)
        .filter_by(employee_id=current.id, financial_year=financial_year)
        .order_by(TaxDeduction.month)
        .all()
    )

    slips = (
        db.query(Payslip)
        .filter_by(employee_id=current.id, is_published=True)
        .order_by(Payslip.pay_period_start)
        .all()
    )

    return {
        "financial_year": financial_year,
        "total_gross": round(sum(s.gross_salary for s in slips), 2),
        "total_deductions": round(sum(s.total_deductions for s in slips), 2),
        "total_net": round(sum(s.net_salary for s in slips), 2),
        "total_tds": round(sum(t.tds for t in td_rows), 2),
        "total_pf": round(sum(t.pf_employee for t in td_rows), 2),
        "total_esi": round(sum(t.esi_employee for t in td_rows), 2),
        "total_pt": round(sum(t.professional_tax for t in td_rows), 2),
        "months_paid": len(slips),
        "monthly_breakdown": [
            {
                "month_label": _payslip_month_label(s),
                "gross": s.gross_salary,
                "deductions": s.total_deductions,
                "net": s.net_salary,
                "run_id": s.run_id,
            }
            for s in slips
        ],
    }


# ─── Reimbursements (Employee ESS) ────────────────────────────────────────────

@router.get("/reimbursements", summary="My reimbursement claims")
def my_reimbursements(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    claims = (
        db.query(Reimbursement)
        .filter_by(employee_id=current.id)
        .order_by(Reimbursement.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "claim_type": r.claim_type,
            "claim_amount": r.claim_amount,
            "approved_amount": r.approved_amount,
            "status": r.status,
            "description": getattr(r, "description", None),
            "is_taxable": getattr(r, "is_taxable", False),
            "manager_approved_at": getattr(r, "manager_approved_at", None),
            "approved_at": r.approved_at,
            "remarks": r.remarks,
            "created_at": r.created_at,
        }
        for r in claims
    ]


@router.post("/reimbursements", status_code=201, summary="Submit a reimbursement claim")
def submit_reimbursement(
    body: dict,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    claim_type = body.get("claim_type")
    claim_amount = body.get("claim_amount")
    if not claim_type or not claim_amount:
        raise HTTPException(status_code=400, detail="claim_type and claim_amount are required")
    if float(claim_amount) <= 0:
        raise HTTPException(status_code=400, detail="claim_amount must be positive")

    r = Reimbursement(
        employee_id=current.id,
        claim_type=claim_type,
        claim_amount=float(claim_amount),
        approved_amount=0.0,
        status="pending",
        description=body.get("description"),
        is_taxable=body.get("is_taxable", False),
        receipt_url=body.get("receipt_url"),
        remarks=body.get("remarks"),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {
        "id": r.id,
        "claim_type": r.claim_type,
        "claim_amount": r.claim_amount,
        "status": r.status,
        "created_at": r.created_at,
    }


@router.delete("/reimbursements/{claim_id}", status_code=204,
               summary="Cancel (withdraw) a pending reimbursement claim")
def cancel_reimbursement(
    claim_id: int,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    r = db.query(Reimbursement).filter_by(id=claim_id, employee_id=current.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Claim not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending claims can be cancelled")
    r.status = "cancelled"
    db.commit()


# ─── Tax Declarations (Employee ESS) ─────────────────────────────────────────

@router.get("/tax-declarations", summary="My tax declarations")
def my_tax_declarations(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    decls = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=current.id)
        .order_by(EmployeeTaxDeclaration.financial_year.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "financial_year": d.financial_year,
            "sec_80c": d.sec_80c,
            "sec_80d": d.sec_80d,
            "sec_80ccd": d.sec_80ccd,
            "hra_exemption": d.hra_exemption,
            "sec_24b": d.sec_24b,
            "other_deductions": d.other_deductions,
            "opted_new_regime": d.opted_new_regime,
            "proof_submitted": d.proof_submitted,
            "proof_verified": d.proof_verified,
            "submitted_at": d.submitted_at,
        }
        for d in decls
    ]


@router.put("/tax-declarations", summary="Submit or update my tax declaration")
def upsert_my_tax_declaration(
    body: dict,
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    from datetime import date
    today = date.today()
    fy_start = today.year if today.month >= 4 else today.year - 1
    default_fy = f"{fy_start}-{str(fy_start + 1)[-2:]}"
    financial_year = body.get("financial_year", default_fy)

    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=current.id, financial_year=financial_year)
        .first()
    )
    if not decl:
        decl = EmployeeTaxDeclaration(
            employee_id=current.id,
            financial_year=financial_year,
        )
        db.add(decl)

    if decl.proof_verified:
        raise HTTPException(
            status_code=400,
            detail="Declaration has been verified by HR. Contact HR to make changes."
        )

    for field in ("sec_80c", "sec_80d", "sec_80ccd", "hra_exemption",
                  "sec_24b", "other_deductions", "opted_new_regime"):
        if field in body:
            setattr(decl, field, body[field])

    if body.get("submit_proof"):
        decl.proof_submitted = True
        decl.submitted_at = datetime.utcnow()
        decl.proof_verified = False

    db.commit()
    db.refresh(decl)

    try:
        from app.services.statutory_service import refresh_tds_for_employee
        refresh_tds_for_employee(db, current.id)
    except Exception:
        pass

    return {
        "id": decl.id,
        "financial_year": decl.financial_year,
        "sec_80c": decl.sec_80c,
        "sec_80d": decl.sec_80d,
        "sec_80ccd": decl.sec_80ccd,
        "hra_exemption": decl.hra_exemption,
        "sec_24b": decl.sec_24b,
        "other_deductions": decl.other_deductions,
        "opted_new_regime": decl.opted_new_regime,
        "proof_submitted": decl.proof_submitted,
        "proof_verified": decl.proof_verified,
        "submitted_at": decl.submitted_at,
    }


# ─── Salary Structure (Employee ESS — read-only) ──────────────────────────────

@router.get("/salary-structure", summary="My current salary structure (read-only)")
def my_salary_structure(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    """Return the logged-in employee's active salary structure.

    Security: always filtered on current.id — employees never see other records.
    Read-only: no POST/PUT/PATCH exposed here.
    """
    ss = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == current.id,
            SalaryStructure.is_active.is_(True),
        )
        .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.created_at.desc())
        .first()
    )

    if not ss:
        return None  # 200 + null body → FE shows "not assigned" message

    # gross_monthly: always calculate from annual_ctc; stored value may be 0
    gross_monthly = round(ss.annual_ctc / 12, 2) if ss.annual_ctc else round(ss.gross_monthly or 0, 2)

    # net_monthly: prefer latest approved/disbursed payroll run record; fall back to stored value; else None
    net_monthly = None
    lta = 0.0
    try:
        pre = (
            db.query(PayrollRunEmployee)
            .join(PayrollRun, PayrollRun.id == PayrollRunEmployee.run_id)
            .filter(
                PayrollRunEmployee.employee_id == current.id,
                PayrollRun.status.in_(["approved", "disbursed"]),
            )
            .order_by(PayrollRunEmployee.created_at.desc())
            .first()
        )
        if pre:
            lta = getattr(pre, "lta", 0.0) or 0.0
            if pre.net_salary:
                net_monthly = round(pre.net_salary, 2)
    except Exception:
        pass

    if net_monthly is None and ss.net_monthly:
        net_monthly = round(ss.net_monthly, 2)

    return {
        "annual_ctc":          round(ss.annual_ctc, 2),
        "gross_monthly":       gross_monthly,
        "basic":               round(ss.basic or 0, 2),
        "hra":                 round(ss.hra or 0, 2),
        "da":                  round(ss.da or 0, 2),
        "lta":                 round(lta, 2),
        "special_allowance":   round(ss.special_allowance or 0, 2),
        "transport_allowance": round(ss.transport_allowance or 0, 2),
        "medical_allowance":   round(ss.medical_allowance or 0, 2),
        "other_allowances":    round(ss.other_allowances or 0, 2),
        "pf_employee":         round(ss.pf_employee or 0, 2),
        "professional_tax":    round(ss.professional_tax or 0, 2),
        "tds":                 round(ss.tds or 0, 2),
        "total_deductions":    round(ss.total_deductions or 0, 2),
        "net_monthly":         net_monthly,
        "effective_from":      ss.effective_from,
        "last_revised":        ss.updated_at,
    }


# ─── Attendance Used for Payroll (Employee ESS — read-only) ──────────────────

@router.get("/attendance-summary", summary="My attendance records used for payroll (read-only)")
def my_attendance_summary(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    """Return up to 24 months of attendance summary for the logged-in employee.

    Source: monthly_attendance_summary table (payroll bridge).
    Security: always filtered on current.id.
    Read-only: employees cannot edit attendance.
    """
    from app.models.monthly_attendance_summary import MonthlyAttendanceSummary

    rows = (
        db.query(MonthlyAttendanceSummary)
        .filter(MonthlyAttendanceSummary.employee_id == current.id)
        .order_by(
            MonthlyAttendanceSummary.year.desc(),
            MonthlyAttendanceSummary.month.desc(),
        )
        .limit(24)
        .all()
    )

    return [
        {
            "month":              r.month,
            "year":               r.year,
            "month_label":        _month_label_from_parts(r.month, r.year),
            "working_days":       r.total_working_days,
            "present_days":       r.present_days,
            "leave_days":         r.leave_days,
            "lop_days":           r.lop_days,
            "payable_days":       r.payable_days,
            "attendance_status":  r.attendance_status,
            "timesheet_status":   r.timesheet_status,
            "is_frozen":          r.is_frozen,
            "finalized_at":       r.finalized_at,
        }
        for r in rows
    ]


# ─── Payroll Status Card (Employee ESS — header summary) ─────────────────────

@router.get("/status", summary="My current payroll status card")
def my_payroll_status(
    db: Session = Depends(get_db),
    current: Employee = CurrentUser,
):
    """Lightweight status card for the Employee Payroll dashboard header.

    Returns:
      payroll_cycle_started — true only when a payroll_run is active
      net_monthly/gross_monthly — from this cycle's payroll_run_employee row
      payroll_month — active payroll_run month label
      attendance_status — attendance status for the active run's month
      attendance_frozen — is attendance frozen for the active run's month?
      payslip_status — only set for the active run
    """
    from app.models.monthly_attendance_summary import MonthlyAttendanceSummary

    empty_status = {
        "payroll_cycle_started": False,
        "message": "No payroll cycle started yet.",
        "payroll_run_id": None,
        "payroll_run_status": None,
        "net_monthly": None,
        "gross_monthly": None,
        "payroll_month": None,
        "attendance_status": "pending_cycle",
        "attendance_frozen": False,
        "payslip_status": None,
        "latest_payslip_month": None,
    }

    # ESS status must be driven by an actual payroll cycle. Monthly attendance
    # rows can survive demo resets and should never create a "current payroll".
    active_run = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.notin_(["disbursed", "closed", "cancelled"]))
        .order_by(PayrollRun.pay_period_start.desc(), PayrollRun.id.desc())
        .first()
    )
    active_run = payroll_service.normalize_payroll_run_period(active_run)
    if not active_run:
        return empty_status

    month = active_run.month or active_run.pay_period_start.month
    year = active_run.year or active_run.pay_period_start.year

    payroll_row = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=active_run.id, employee_id=current.id)
        .first()
    )
    att = (
        db.query(MonthlyAttendanceSummary)
        .filter(
            MonthlyAttendanceSummary.employee_id == current.id,
            MonthlyAttendanceSummary.month == month,
            MonthlyAttendanceSummary.year == year,
        )
        .first()
    )
    cycle_slip = (
        db.query(Payslip)
        .filter_by(run_id=active_run.id, employee_id=current.id)
        .order_by(Payslip.pay_period_start.desc())
        .first()
    )

    payslip_status = "pending"
    latest_payslip_month = None
    if cycle_slip:
        latest_payslip_month = _payslip_month_label(cycle_slip)
        payslip_status = "published" if cycle_slip.is_published else "generated"

    return {
        "payroll_cycle_started": True,
        "message": None,
        "payroll_run_id":        active_run.id,
        "payroll_run_status":    active_run.status,
        "net_monthly":           round(float(payroll_row.net_pay or 0.0), 2) if payroll_row else None,
        "gross_monthly":         round(float(payroll_row.gross_earnings or 0.0), 2) if payroll_row else None,
        "payroll_month":         active_run.month_label or _month_label_from_parts(month, year),
        "attendance_status":     att.attendance_status if att else "not_available",
        "attendance_frozen":     att.is_frozen if att else False,
        "payslip_status":        payslip_status,
        "latest_payslip_month":  latest_payslip_month,
    }
