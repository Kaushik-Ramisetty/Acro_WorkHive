"""Final Settlement (FF) API routes.

All endpoints require 'finance' or 'admin' role.
Prefix: /finance/ff
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.schemas.ff import (
    FinalSettlementCreate,
    FinalSettlementCalculateIn,
    FinalSettlementOut,
    FinalSettlementApproveIn,
    FinalSettlementMarkPaidIn,
)
from app.services import ff_service

router = APIRouter(
    prefix="/finance/ff",
    tags=["Final Settlement"],
    dependencies=[Depends(role_required("finance", "admin"))],
)

FinanceUser = Depends(role_required("finance", "admin"))


@router.get("", summary="List all Final Settlements")
def list_ff(
    status: Optional[str] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    records = ff_service.list_ff(db, status=status, employee_id=employee_id)
    return [ff_service.ff_to_dict(r) for r in records]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Initiate Final Settlement for an employee")
def create_ff(
    body: FinalSettlementCreate,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.create_ff(db, body.model_dump(), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.get("/{ff_id}", summary="Get Final Settlement details")
def get_ff(
    ff_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    ff = ff_service.get_ff(db, ff_id)
    if not ff:
        raise HTTPException(status_code=404, detail="Final settlement not found")
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/calculate", summary="Calculate FF amounts (auto + overrides)")
def calculate_ff(
    ff_id: int,
    body: FinalSettlementCalculateIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.calculate_ff(db, ff_id, body.model_dump(exclude_none=True), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/submit", summary="Submit FF for review")
def submit_ff(
    ff_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.advance_ff_status(db, ff_id, "submit", actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/approve", summary="Approve Final Settlement")
def approve_ff(
    ff_id: int,
    body: FinalSettlementApproveIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.advance_ff_status(
            db, ff_id, "approve", actor, remarks=body.remarks
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/reject", summary="Reject / send back FF for recalculation")
def reject_ff(
    ff_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.advance_ff_status(db, ff_id, "reject", actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/mark-paid", summary="Mark Final Settlement as paid")
def mark_ff_paid(
    ff_id: int,
    body: FinalSettlementMarkPaidIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.advance_ff_status(
            db, ff_id, "mark_paid", actor,
            paid_date=body.paid_date,
            payment_reference=body.payment_reference,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.post("/{ff_id}/cancel", status_code=status.HTTP_200_OK, summary="Cancel a Final Settlement")
def cancel_ff(
    ff_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        ff = ff_service.advance_ff_status(db, ff_id, "cancel", actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ff_service.ff_to_dict(ff)


@router.get("/{ff_id}/pdf", summary="Download Final Settlement PDF")
def ff_pdf(
    ff_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    ff = ff_service.get_ff(db, ff_id)
    if not ff:
        raise HTTPException(status_code=404, detail="Final settlement not found")
    if ff.status == "draft":
        raise HTTPException(status_code=400, detail="Calculate the settlement before generating PDF")
    pdf_bytes = ff_service.generate_ff_pdf(ff)
    if not pdf_bytes:
        raise HTTPException(
            status_code=503,
            detail="PDF generation unavailable. Install 'reportlab' to enable F&F PDFs."
        )
    data = ff_service.ff_to_dict(ff)
    emp_name = (data.get("employee_name") or "ff").replace(" ", "_")
    filename = f"ff_settlement_{emp_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{ff_id}/statement", summary="Download FF statement as CSV")
def ff_statement_csv(
    ff_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    ff = ff_service.get_ff(db, ff_id)
    if not ff:
        raise HTTPException(status_code=404, detail="Final settlement not found")
    data = ff_service.ff_to_dict(ff)
    lines = [
        "Final Settlement Statement",
        f"Employee,{data['employee_name']}",
        f"Employee Code,{data['employee_code'] or ''}",
        f"Department,{data['department']}",
        f"Designation,{data['designation']}",
        f"Date of Joining,{data['date_of_joining'] or ''}",
        f"Last Working Day,{data['last_working_day'] or ''}",
        f"Separation Type,{data['separation_type'] or ''}",
        "",
        "EARNINGS",
        f"Unpaid Salary,{data['unpaid_salary']:.2f}",
        f"Leave Encashment ({data['leave_encashment_days']:.1f} days),{data['leave_encashment_amount']:.2f}",
        f"Bonus Pending,{data['bonus_pending']:.2f}",
        f"Variable Pay Pending,{data['variable_pay_pending']:.2f}",
        f"Gratuity ({'Eligible' if data['gratuity_eligible'] else 'Not Eligible'}),{data['gratuity_amount']:.2f}",
        f"Other Earnings,{data['other_earnings']:.2f}",
        f"Gross Settlement,{data['gross_settlement']:.2f}",
        "",
        "DEDUCTIONS",
        f"Notice Period Recovery ({data['notice_period_days']} days),{data['notice_period_recovery']:.2f}",
        f"Loan Recovery,{data['loan_recovery']:.2f}",
        f"Advance Recovery,{data['advance_recovery']:.2f}",
        f"Asset Recovery,{data.get('asset_recovery', 0):.2f}",
        f"Other Deductions,{data['other_deductions']:.2f}",
        f"TDS on Settlement,{data['tds_on_settlement']:.2f}",
        f"Total Deductions,{data['total_deductions']:.2f}",
        "",
        f"NET FINAL PAYABLE,{data['net_payable']:.2f}",
        "",
        f"Status,{data['status']}",
        f"Approved By,{data['approved_by_name'] or ''}",
        f"Paid Date,{data['paid_date'] or ''}",
        f"Payment Reference,{data['payment_reference'] or ''}",
    ]
    emp_name = (data["employee_name"] or "ff").replace(" ", "_")
    filename = f"ff_statement_{emp_name}.csv"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
