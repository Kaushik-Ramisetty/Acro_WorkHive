"""Finance module API routes.

All endpoints require the 'finance' or 'admin' role.
Prefix: /finance
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.models.employee import Employee
from app.models.payroll_extended import (
    StatutorySettings,
    PayrollAdjustment,
    Payslip,
)
from app.schemas.payroll import (
    PayrollRunCreate,
    PayrollRunOut,
    PayrollRunStatusUpdate,
    PayrollRunEmployeeOut,
    PayrollApprovalOut,
    PayrollErrorCreate,
    PayrollErrorOut,
    PayrollErrorResolve,
    SalaryStructureIn,
    SalaryStructureOut,
    PayrollDashboardStats,
    DepartmentPayrollSummary,
    SalaryRevisionCreate,
    SalaryRevisionOut,
)
from app.schemas.payroll_extended import (
    StatutorySettingsOut,
    StatutorySettingsIn,
    PayrollAdjustmentIn,
    PayrollAdjustmentOut,
    PayslipOut,
    CTCComputeIn,
    CTCComputeOut,
    SalaryComponentIn,
    SalaryComponentOut,
    EmployeeSalaryOut,
    TaxDeductionOut,
    ReimbursementIn,
    ReimbursementApproveIn,
    ReimbursementRejectIn,
    ReimbursementMarkPaidIn,
    ReimbursementOut,
)
from app.services import payroll_service
from app.services import statutory_service
from app.services import payslip_service
from app.services import payroll_schema_service
from app.services.ctc_engine import compute_from_ctc

router = APIRouter(
    prefix="/finance",
    tags=["Finance"],
    dependencies=[Depends(role_required("finance", "admin", "finance_head"))],
)

FinanceUser = Depends(role_required("finance", "admin", "finance_head"))
FinanceHeadUser = Depends(role_required("finance_head", "admin"))
# Finance-only actions (Finance Head is excluded — they cannot publish or generate payslips)
FinanceOnlyUser = Depends(role_required("finance", "admin"))

_FINANCE_REVIEW_ACTIONS = {"approve", "finance_review", "reject"}
_FINANCE_HEAD_ACTIONS = {"head_approve", "finance_head_approve", "head_reject"}
_REJECT_ACTIONS = {"reject", "head_reject"}


def _actor_role(actor: Employee) -> str:
    return (
        (getattr(actor, "_jwt_role", None) or "")
        or (actor.role.name if actor.role else "")
    ).strip().lower()


def _require_action_role(actor: Employee, allowed: set[str], action: str) -> None:
    role = _actor_role(actor)
    if role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action '{action}' requires one of {sorted(allowed)}",
        )


def _require_reject_reason(action: str, remarks: Optional[str]) -> None:
    if action in _REJECT_ACTIONS and not (remarks or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required for reject/return actions.",
        )


def _pre_gross(row) -> float:
    return float(row.gross_earnings or 0.0)


def _pre_basic(row) -> float:
    return float(row.basic_pay or 0.0)


def _pre_allowance(row) -> float:
    return float(row.special_allowance or 0.0)


def _pre_employee_pf(row) -> float:
    return float(row.employee_pf or 0.0)


def _pre_employer_pf(row) -> float:
    return float(row.employer_pf or 0.0)


def _pre_employee_esi(row) -> float:
    return float(row.employee_esi or 0.0)


def _pre_employer_esi(row) -> float:
    return float(row.employer_esi or 0.0)


def _pre_net(row) -> float:
    return float(row.net_pay or 0.0)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", summary="Finance dashboard stats")
def finance_dashboard(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    stats = payroll_service.get_dashboard_stats(db)
    run = stats["current_run"]
    return {
        "current_run": PayrollRunOut.model_validate(run) if run else None,
        "total_payroll_runs": stats["total_payroll_runs"],
        "pending_approval_count": stats["pending_approval_count"],
        "total_employees": stats["total_employees"],
        "total_gross": stats["total_gross"],
        "total_deductions": stats["total_deductions"],
        "total_net_pay": stats["total_net_pay"],
        "last_run_net": stats["last_run_net"],
        "open_error_count": stats["open_error_count"],
        "attendance_frozen": stats["attendance_frozen"],
        "payroll_locked": stats["payroll_locked"],
        "is_finalized": stats["is_finalized"],
        "is_published": stats["is_published"],
        "approval_status": stats["approval_status"],
        "finance_review_status": stats["finance_review_status"],
        "payslip_generated_count": stats["payslip_generated_count"],
        "payslip_published_count": stats["payslip_published_count"],
        "variance_count": stats["variance_count"],
        "payroll_completion_pct": stats["payroll_completion_pct"],
        "department_summary": stats["department_summary"],
    }


# ─── Payroll Runs ─────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[PayrollRunOut], summary="List payroll runs")
def list_runs(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_service.list_payroll_runs(db, limit=limit, offset=offset)


@router.post("/runs", response_model=PayrollRunOut, status_code=status.HTTP_201_CREATED,
             summary="Create new payroll run")
def create_run(
    body: PayrollRunCreate,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    return payroll_service.create_payroll_run(db, body.model_dump(), actor)


@router.get("/runs/{run_id}", response_model=PayrollRunOut, summary="Get payroll run details")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    return run


@router.post("/runs/{run_id}/action", response_model=PayrollRunOut,
             summary="Advance payroll run workflow")
def run_action(
    run_id: int,
    body: PayrollRunStatusUpdate,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    action = (body.action or "").strip()
    if action in _FINANCE_REVIEW_ACTIONS:
        _require_action_role(actor, {"finance", "admin"}, action)
    if action in _FINANCE_HEAD_ACTIONS:
        _require_action_role(actor, {"finance_head", "admin"}, action)
    _require_reject_reason(action, body.remarks)

    # Finance Head may NOT generate payslips or publish — those are Finance-only actions
    _finance_head_blocked = {"generate_payslips", "publish", "recompute", "generate", "process"}
    actor_role = _actor_role(actor)
    if actor_role == "finance_head" and action in _finance_head_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Action '{action}' is not available to the Finance Head role. "
                "Finance Head may only perform Final Approval or Return to Finance."
            ),
        )
    try:
        run = payroll_service.advance_run_status(db, run_id, action, body.remarks, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if action in ("approve", "head_approve", "finance_head_approve", "hr_confirm", "finalize", "disburse", "close"):
        try:
            payroll_schema_service.populate_tax_deductions_for_run(db, run)
        except Exception:
            pass
    return run


@router.post("/runs/{run_id}/process", response_model=PayrollRunOut,
             summary="Process payroll run")
def process_run(
    run_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        return payroll_service.advance_run_status(db, run_id, "process", "Payroll processed", actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/submit-for-approval", response_model=PayrollRunOut,
             summary="Submit payroll for approval")
def submit_run_for_approval(
    run_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        return payroll_service.advance_run_status(db, run_id, "submit_for_approval", None, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/approve", response_model=PayrollRunOut,
             summary="Finance review approve or reject (FINANCE_REVIEW level only)")
def approve_run_level(
    run_id: int,
    body: dict,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    level = (body.get("approval_level") or "FINANCE_REVIEW").upper()
    approved = bool(body.get("approved", True))
    comments = body.get("comments") or body.get("remarks")

    if level == "FINANCE_REVIEW":
        _require_action_role(actor, {"finance", "admin"}, "finance_review")
    if level == "FINANCE_HEAD_APPROVAL":
        _require_action_role(actor, {"finance_head", "admin"}, "finance_head_approve")
    if level == "HR_CONFIRMATION":
        _require_action_role(actor, {"admin"}, "hr_confirm")

    action_map = {
        ("FINANCE_REVIEW", True): "finance_review",
        ("FINANCE_REVIEW", False): "reject",
        ("FINANCE_HEAD_APPROVAL", True): "finance_head_approve",
        ("FINANCE_HEAD_APPROVAL", False): "head_reject",
        ("HR_CONFIRMATION", True): "hr_confirm",
        ("HR_CONFIRMATION", False): "head_reject",
    }
    action = action_map.get((level, approved))
    if not action:
        raise HTTPException(status_code=400, detail=f"Unsupported approval level '{level}'")
    _require_reject_reason(action, comments)
    try:
        return payroll_service.advance_run_status(db, run_id, action, comments, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/final-approve", response_model=PayrollRunOut,
             summary="Finance Head final approval (finance_head role only)")
def final_approve_run(
    run_id: int,
    body: Optional[dict] = None,
    db: Session = Depends(get_db),
    actor: Employee = FinanceHeadUser,
):
    """Only users with the 'finance_head' or 'admin' role may call this endpoint.
    Approving locks the payroll permanently; recompute/edit are blocked afterwards.
    """
    body = body or {}
    comments = body.get("comments") or body.get("remarks")
    approved = body.get("approved", True)
    action = "finance_head_approve" if approved else "head_reject"
    _require_reject_reason(action, comments)
    try:
        return payroll_service.advance_run_status(db, run_id, action, comments, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/finalize", response_model=PayrollRunOut,
             summary="Finalize and lock payroll run")
def finalize_run(
    run_id: int,
    body: Optional[dict] = None,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        return payroll_service.advance_run_status(
            db, run_id, "finalize", (body or {}).get("remarks"), actor
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/publish", summary="Publish generated payslips (Finance/Admin only)")
def publish_run(
    run_id: int,
    send_email: bool = False,
    db: Session = Depends(get_db),
    actor: Employee = FinanceOnlyUser,  # Finance Head cannot publish — Finance team only
):
    try:
        count = payroll_service.bulk_publish_payslips(db, run_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    email_result = {"sent": 0, "failed": 0, "skipped": 0}
    if send_email:
        email_result = payslip_service.send_payslip_emails_for_run(db, run_id)
    return {"published": count, "email": email_result}


# ─── Run Employees ────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/employees", response_model=list[PayrollRunEmployeeOut],
            summary="Payroll run employee breakdown")
def run_employees(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    rows = payroll_service.list_run_employees(db, run_id)

    # Pre-load adjustments for this run to avoid N+1 queries
    all_adjustments = payroll_service.list_adjustments(db, run_id)
    adj_by_emp: dict[int, list] = {}
    for a in all_adjustments:
        adj_by_emp.setdefault(a.employee_id, []).append(a)

    result = []
    for row in rows:
        emp = row.employee
        adjs = adj_by_emp.get(row.employee_id, [])
        bonus_total = round(sum(
            a.amount for a in adjs
            if a.adjustment_type == "bonus" and a.direction == "addition"
        ), 2)
        variable_pay_total = round(sum(
            a.amount for a in adjs
            if a.adjustment_type == "variable_pay" and a.direction == "addition"
        ), 2)
        arrears_total = round(sum(
            a.amount for a in adjs
            if a.adjustment_type == "arrears" and a.direction == "addition"
        ), 2)
        gross = _pre_gross(row)
        basic = _pre_basic(row)
        allowance = _pre_allowance(row)
        employee_pf = _pre_employee_pf(row)
        employer_pf = _pre_employer_pf(row)
        employee_esi = _pre_employee_esi(row)
        employer_esi = _pre_employer_esi(row)
        net = _pre_net(row)
        out = PayrollRunEmployeeOut(
            id=row.id,
            payroll_record_id=row.id,
            run_id=row.run_id,
            payroll_run_id=row.run_id,
            employee_id=row.employee_id,
            employee_name=f"{emp.first_name} {emp.last_name}" if emp else "—",
            department=emp.department.name if emp and emp.department else "—",
            designation=emp.designation.title if emp and emp.designation else "—",
            salary_structure_id=row.salary_structure_id,
            salary_assignment_id=row.salary_assignment_id,
            total_working_days=row.total_working_days or row.working_days,
            working_days=row.working_days,
            payable_days=row.payable_days or row.present_days,
            present_days=row.present_days,
            leave_days=row.leave_days,
            lop_days=row.lop_days,
            gross_salary=gross,
            gross_earnings=gross,
            basic=basic,
            basic_pay=basic,
            hra=row.hra,
            da=row.da,
            special_allowance=row.special_allowance,
            lta=row.lta,
            conveyance=row.conveyance,
            bonus=row.bonus,
            variable_pay=row.variable_pay,
            overtime_amount=row.overtime_amount,
            allowances=allowance,
            employee_pf=employee_pf,
            pf_employee=employee_pf,
            pf_employer=employer_pf,
            employer_pf=employer_pf,
            employee_esi=employee_esi,
            esi_employee=employee_esi,
            esi_employer=employer_esi,
            employer_esi=employer_esi,
            professional_tax=row.professional_tax,
            tds=row.tds,
            lop_deduction=row.lop_deduction,
            other_deductions=row.other_deductions,
            total_deductions=row.total_deductions,
            net_salary=net,
            net_pay=net,
            bonus_total=bonus_total,
            variable_pay_total=variable_pay_total,
            arrears_total=arrears_total,
            has_error=row.has_error,
            is_locked=row.is_locked,
            payslip_generated=row.payslip_generated,
            record_status=row.record_status,
            variance_flag=row.variance_flag,
            variance_reason=row.variance_reason,
            payslip_url=row.payslip_url,
            migration_completed=row.migration_completed,
        )
        result.append(out)
    return result


@router.post("/runs/{run_id}/employees/{employee_id}/payslip",
             summary="Mark payslip generated for single employee")
def mark_payslip(
    run_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    ok = payroll_service.mark_payslip_generated(db, run_id, employee_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Employee record not found in this run")
    return {"detail": "Payslip marked as generated"}


# ─── Approval History ─────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/approvals", response_model=list[PayrollApprovalOut],
            summary="Approval audit trail")
def run_approvals(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollApproval
    approvals = (
        db.query(PayrollApproval)
        .filter_by(run_id=run_id)
        .order_by(PayrollApproval.created_at.asc())
        .all()
    )
    result = []
    for a in approvals:
        actor = a.actor
        result.append(PayrollApprovalOut(
            id=a.id,
            payroll_approval_id=a.id,
            run_id=a.run_id,
            payroll_run_id=a.run_id,
            actor_id=a.actor_id,
            actor_name=f"{actor.first_name} {actor.last_name}" if actor else "—",
            approval_level=a.approval_level,
            approver_id=a.approver_id,
            approval_status=a.approval_status,
            comments=a.comments,
            action=a.action,
            from_status=a.from_status,
            to_status=a.to_status,
            remarks=a.remarks,
            approved_at=a.approved_at,
            created_at=a.created_at,
            updated_at=a.updated_at,
        ))
    return result


# ─── Payroll Errors ───────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/errors", response_model=list[PayrollErrorOut],
            summary="List payroll errors")
def list_errors(
    run_id: int,
    resolved: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    errors = payroll_service.list_payroll_errors(db, run_id, resolved)
    result = []
    for e in errors:
        emp = e.employee
        result.append(PayrollErrorOut(
            id=e.id,
            run_id=e.run_id,
            employee_id=e.employee_id,
            employee_name=f"{emp.first_name} {emp.last_name}" if emp else "—",
            error_type=e.error_type,
            description=e.description,
            severity=e.severity,
            is_resolved=e.is_resolved,
            resolved_at=e.resolved_at,
            resolution_note=e.resolution_note,
            created_at=e.created_at,
        ))
    return result


@router.post("/runs/{run_id}/errors", response_model=PayrollErrorOut,
             status_code=201, summary="Flag a payroll error")
def create_error(
    run_id: int,
    body: PayrollErrorCreate,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    data = body.model_dump()
    data["run_id"] = run_id
    return payroll_service.create_payroll_error(db, data, actor)


@router.patch("/errors/{error_id}/resolve", response_model=PayrollErrorOut,
              summary="Resolve a payroll error")
def resolve_error(
    error_id: int,
    body: PayrollErrorResolve,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        err = payroll_service.resolve_payroll_error(db, error_id, body.resolution_note, actor)
        emp = err.employee
        return PayrollErrorOut(
            id=err.id,
            run_id=err.run_id,
            employee_id=err.employee_id,
            employee_name=f"{emp.first_name} {emp.last_name}" if emp else "—",
            error_type=err.error_type,
            description=err.description,
            severity=err.severity,
            is_resolved=err.is_resolved,
            resolved_at=err.resolved_at,
            resolution_note=err.resolution_note,
            created_at=err.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Employees list (for dropdowns / payroll assignment) ─────────────────────

@router.get("/employees", summary="List active employees for payroll assignment")
def list_employees_for_payroll(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )
    result = []
    for emp in employees:
        result.append({
            "id": emp.id,
            "name": f"{emp.first_name} {emp.last_name or ''}".strip(),
            "employee_code": emp.employee_code or f"EMP{emp.id:04d}",
            "email": emp.email or "",
            "department": emp.department.name if emp.department else "—",
            "designation": emp.designation.title if emp.designation else "—",
        })
    return result


# ─── Salary Structures ────────────────────────────────────────────────────────

@router.get("/salary-structures", response_model=list[SalaryStructureOut],
            summary="List all salary structures")
def list_structures(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    structures = payroll_service.list_salary_structures(db)
    result = []
    for ss in structures:
        emp = ss.employee
        out = SalaryStructureOut.model_validate(ss)
        out.employee_name = f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None
        out.employee_code = (emp.employee_code or f"EMP{emp.id:04d}") if emp else None
        result.append(out)
    return result


@router.get("/salary-structures/{employee_id}", response_model=SalaryStructureOut,
            summary="Get employee salary structure")
def get_structure(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    ss = payroll_service.get_salary_structure(db, employee_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Salary structure not found")
    emp = ss.employee
    out = SalaryStructureOut.model_validate(ss)
    out.employee_name = f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None
    out.employee_code = (emp.employee_code or f"EMP{emp.id:04d}") if emp else None
    return out


@router.get("/salary-structures/{employee_id}/history", response_model=list[SalaryStructureOut],
            summary="Get all salary revision history for an employee")
def get_structure_history(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    history = payroll_service.list_salary_structure_history(db, employee_id)
    result = []
    for ss in history:
        emp = ss.employee
        out = SalaryStructureOut.model_validate(ss)
        out.employee_name = f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None
        out.employee_code = (emp.employee_code or f"EMP{emp.id:04d}") if emp else None
        result.append(out)
    return result


@router.put("/salary-structures", response_model=SalaryStructureOut,
            summary="Create or update salary structure manually")
def upsert_structure(
    body: SalaryStructureIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    struct = payroll_service.upsert_salary_structure(db, body.model_dump(), actor)
    try:
        payroll_schema_service.sync_employee_salary_from_structure(db, struct)
    except Exception:
        pass
    return struct


@router.post("/salary-structures/from-ctc", response_model=SalaryStructureOut,
             summary="Auto-compute and save salary structure from annual CTC")
def structure_from_ctc(
    body: CTCComputeIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    struct = payroll_service.upsert_salary_structure_from_ctc(
        db,
        employee_id=body.employee_id,
        annual_ctc=body.annual_ctc,
        actor=actor,
        bank_name=body.bank_name,
        account_number=body.account_number,
        ifsc_code=body.ifsc_code,
        effective_from=body.effective_from,
        revision_reason=body.revision_reason,
    )
    try:
        payroll_schema_service.sync_employee_salary_from_structure(db, struct)
    except Exception:
        pass
    return struct


@router.post("/ctc/preview", response_model=CTCComputeOut,
             summary="Preview salary breakup for a given annual CTC (no save)")
def preview_ctc(
    body: CTCComputeIn,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    b = compute_from_ctc(body.annual_ctc, db)
    return CTCComputeOut(
        employee_id=body.employee_id,
        annual_ctc=b.annual_ctc,
        basic=b.basic,
        hra=b.hra,
        da=b.da,
        lta=b.lta,
        special_allowance=b.special_allowance,
        transport_allowance=b.transport_allowance,
        medical_allowance=b.medical_allowance,
        gross_monthly=b.gross_monthly,
        pf_employee=b.pf_employee,
        pf_employer=b.pf_employer,
        esi_employee=b.esi_employee,
        esi_employer=b.esi_employer,
        professional_tax=b.professional_tax,
        tds=b.tds,
        total_deductions=b.total_deductions,
        net_monthly=b.net_monthly,
    )


# ─── Salary Revision History & Audit ────────────────────────────────────────

def _revision_to_dict(rev) -> dict:
    """Convert a SalaryRevisionLog to a serialisable dict."""
    emp = rev.employee
    revised_by = rev.revised_by
    return {
        "id": rev.id,
        "employee_id": rev.employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name or ''}".strip() if emp else "—",
        "employee_code": (emp.employee_code or f"EMP{emp.id:04d}") if emp else "—",
        "department": emp.department.name if emp and emp.department else "—",
        "designation": emp.designation.title if emp and emp.designation else "—",
        "old_salary_structure_id": rev.old_salary_structure_id,
        "new_salary_structure_id": rev.new_salary_structure_id,
        "old_annual_ctc": rev.old_annual_ctc,
        "new_annual_ctc": rev.new_annual_ctc,
        "ctc_difference": rev.ctc_difference,
        "ctc_change_pct": rev.ctc_change_pct,
        "old_gross_monthly": rev.old_gross_monthly,
        "new_gross_monthly": rev.new_gross_monthly,
        "old_net_monthly": rev.old_net_monthly,
        "new_net_monthly": rev.new_net_monthly,
        "effective_from": rev.effective_from.isoformat() if rev.effective_from else None,
        "revision_reason": rev.revision_reason,
        "revised_by_id": rev.revised_by_id,
        "revised_by_name": (
            f"{revised_by.first_name} {revised_by.last_name or ''}".strip()
            if revised_by else "—"
        ),
        "revised_at": rev.created_at.isoformat() if rev.created_at else None,
        "created_at": rev.created_at.isoformat() if rev.created_at else None,
    }


def _revision_comparison_dict(rev) -> dict:
    """Full side-by-side comparison payload for a revision."""
    base = _revision_to_dict(rev)
    base["comparison"] = {
        "components": [
            {"label": "Annual CTC",          "old": rev.old_annual_ctc,         "new": rev.new_annual_ctc},
            {"label": "Gross Monthly",       "old": rev.old_gross_monthly,      "new": rev.new_gross_monthly},
            {"label": "Net Monthly",         "old": rev.old_net_monthly,        "new": rev.new_net_monthly},
            {"label": "Basic",               "old": rev.old_basic,              "new": rev.new_basic},
            {"label": "HRA",                 "old": rev.old_hra,                "new": rev.new_hra},
            {"label": "DA",                  "old": rev.old_da,                 "new": rev.new_da},
            {"label": "Special Allowance",   "old": rev.old_special_allowance,  "new": rev.new_special_allowance},
            {"label": "Transport Allowance", "old": rev.old_transport_allowance,"new": rev.new_transport_allowance},
            {"label": "Medical Allowance",   "old": rev.old_medical_allowance,  "new": rev.new_medical_allowance},
            {"label": "PF (Employee)",       "old": rev.old_pf_employee,        "new": rev.new_pf_employee},
            {"label": "ESI (Employee)",      "old": rev.old_esi_employee,       "new": rev.new_esi_employee},
            {"label": "Professional Tax",    "old": rev.old_professional_tax,   "new": rev.new_professional_tax},
            {"label": "TDS",                 "old": rev.old_tds,                "new": rev.new_tds},
        ]
    }
    return base


@router.post(
    "/salary-revisions",
    response_model=SalaryRevisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a salary revision (hike) for an employee",
)
def create_salary_revision(
    body: SalaryRevisionCreate,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    """
    Backward-compatible alias for POST /payroll/salary-revisions.

    Both routes call the same service function so there is exactly one
    implementation.  The /finance prefix is kept for frontend compatibility;
    the /payroll prefix is the canonical location added later.

    Deactivates the current active salary structure, creates a new revision,
    updates employee_salary_assignments, and writes a SalaryRevisionLog audit
    entry.  Existing payroll runs and payslips are never modified.
    """
    try:
        new_struct = payroll_service.create_salary_revision(
            db=db,
            employee_id=body.employee_id,
            new_ctc_annual=body.new_ctc_annual,
            effective_from=body.effective_from,
            assigned_by=actor,
            revision_reason=body.revision_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    revisions = payroll_service.list_salary_revisions(
        db, employee_id=body.employee_id, limit=1
    )
    if revisions:
        rev = revisions[0]
        emp = new_struct.employee
        revised_by = rev.revised_by
        return SalaryRevisionOut(
            id=rev.id,
            employee_id=rev.employee_id,
            employee_name=(
                f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None
            ),
            employee_code=(
                (emp.employee_code or f"EMP{emp.id:04d}") if emp else None
            ),
            old_annual_ctc=rev.old_annual_ctc,
            new_annual_ctc=rev.new_annual_ctc,
            ctc_difference=rev.ctc_difference,
            ctc_change_pct=rev.ctc_change_pct,
            old_gross_monthly=rev.old_gross_monthly,
            new_gross_monthly=rev.new_gross_monthly,
            old_net_monthly=rev.old_net_monthly,
            new_net_monthly=rev.new_net_monthly,
            effective_from=rev.effective_from,
            revision_reason=rev.revision_reason,
            revised_by_id=rev.revised_by_id,
            revised_by_name=(
                f"{revised_by.first_name} {revised_by.last_name or ''}".strip()
                if revised_by else None
            ),
            created_at=rev.created_at,
        )

    emp = new_struct.employee
    return SalaryRevisionOut(
        id=new_struct.id,
        employee_id=body.employee_id,
        employee_name=(
            f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None
        ),
        employee_code=(
            (emp.employee_code or f"EMP{emp.id:04d}") if emp else None
        ),
        old_annual_ctc=0.0,
        new_annual_ctc=new_struct.annual_ctc,
        ctc_difference=new_struct.annual_ctc,
        ctc_change_pct=0.0,
        old_gross_monthly=0.0,
        new_gross_monthly=new_struct.gross_monthly,
        old_net_monthly=0.0,
        new_net_monthly=new_struct.net_monthly,
        effective_from=new_struct.effective_from,
        revision_reason=body.revision_reason,
        revised_by_id=actor.id,
        revised_by_name=f"{actor.first_name} {actor.last_name or ''}".strip(),
        created_at=new_struct.created_at,
    )


@router.get("/salary-revisions",
            summary="List all salary revision audit log entries")
def list_salary_revisions(
    employee_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    revisions = payroll_service.list_salary_revisions(
        db, employee_id=employee_id, limit=limit, offset=offset
    )
    return [_revision_to_dict(r) for r in revisions]


@router.get("/salary-revisions/report",
            summary="Download salary revision report as CSV")
def salary_revision_report(
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    revisions = payroll_service.list_salary_revisions(
        db, employee_id=employee_id, limit=10000
    )
    lines = [
        "Employee Code,Employee Name,Department,Old CTC,New CTC,Difference,Change %,"
        "Old Gross/Month,New Gross/Month,Old Net/Month,New Net/Month,"
        "Effective From,Revised By,Revised At,Reason"
    ]
    for r in revisions:
        emp = r.employee
        revised_by = r.revised_by
        emp_code = emp.employee_code if emp else ""
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip() if emp else ""
        dept = emp.department.name if emp and emp.department else ""
        by_name = (
            f"{revised_by.first_name} {revised_by.last_name or ''}".strip()
            if revised_by else ""
        )
        reason = (r.revision_reason or "").replace(",", ";")
        lines.append(
            f"{emp_code},{emp_name},{dept},"
            f"{r.old_annual_ctc:.2f},{r.new_annual_ctc:.2f},"
            f"{r.ctc_difference:.2f},{r.ctc_change_pct:.2f}%,"
            f"{r.old_gross_monthly:.2f},{r.new_gross_monthly:.2f},"
            f"{r.old_net_monthly:.2f},{r.new_net_monthly:.2f},"
            f"{r.effective_from},{by_name},"
            f"{r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''},"
            f"{reason}"
        )
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="salary_revision_report.csv"'},
    )


@router.get("/salary-revisions/{revision_id}",
            summary="Get single salary revision with full comparison")
def get_salary_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    rev = payroll_service.get_salary_revision(db, revision_id)
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    return _revision_comparison_dict(rev)


# ─── Payroll Adjustments ─────────────────────────────────────────────────────

@router.get("/runs/{run_id}/adjustments", response_model=list[PayrollAdjustmentOut],
            summary="List adjustments for a run")
def list_adjustments(
    run_id: int,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_service.list_adjustments(db, run_id, employee_id)


@router.post("/runs/{run_id}/adjustments", response_model=PayrollAdjustmentOut,
             status_code=201, summary="Add one-time adjustment to run")
def add_adjustment(
    run_id: int,
    body: PayrollAdjustmentIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    data = body.model_dump()
    data["run_id"] = run_id
    try:
        return payroll_service.create_adjustment(db, data, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/adjustments/{adj_id}", status_code=204, summary="Remove an adjustment")
def delete_adjustment(
    adj_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    try:
        ok = payroll_service.delete_adjustment(db, adj_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Adjustment not found")


# ─── Payslips ─────────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/payslips", response_model=list[PayslipOut],
            summary="List payslip records for a run")
def list_run_payslips(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    slips = payroll_service.list_payslips(db, run_id=run_id)
    return [_payslip_to_out(s) for s in slips]


@router.get("/runs/{run_id}/payslips/{employee_id}/pdf",
            summary="Download payslip PDF for one employee")
def download_payslip_pdf(
    run_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    pdf_bytes = payslip_service.generate_payslip_pdf(db, run_id, employee_id)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=503,
            detail="PDF generation unavailable. Install 'reportlab' to enable payslip PDFs."
        )
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()
    if slip:
        slip.download_count = (slip.download_count or 0) + 1
        db.commit()
    emp_name = f"{emp.first_name}_{emp.last_name}" if emp else f"emp{employee_id}"
    filename = f"payslip_{emp_name}_run{run_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/runs/{run_id}/payslips/{employee_id}/publish",
             response_model=PayslipOut, summary="Publish payslip to ESS portal")
def publish_payslip(
    run_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()
    if not slip:
        raise HTTPException(status_code=404, detail="Payslip record not found")
    run = payroll_service.get_payroll_run(db, run_id)
    if run and run.status not in ("approved", "payslip_generated", "published", "closed", "disbursed"):
        raise HTTPException(
            status_code=400,
            detail="Payslip cannot be published before finance head approval."
        )
    try:
        slip = payroll_service.publish_payslip(db, slip.id, actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _payslip_to_out(slip)


@router.post("/runs/{run_id}/payslips/publish-all",
             summary="Publish all payslips for a run and email employees")
def publish_all_payslips(
    run_id: int,
    send_email: bool = True,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("approved", "payslip_generated", "published", "disbursed", "closed"):
        raise HTTPException(status_code=400, detail="Run must be approved before publishing payslips")
    try:
        count = payroll_service.bulk_publish_payslips(db, run_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    email_result = {"sent": 0, "failed": 0, "skipped": 0}
    if send_email:
        email_result = payslip_service.send_payslip_emails_for_run(db, run_id)
    return {
        "detail": f"{count} payslip(s) published",
        "published": count,
        "email": email_result,
    }


# ─── Bank Advice Export ───────────────────────────────────────────────────────

@router.get("/runs/{run_id}/bank-advice",
            summary="Download bank advice CSV for salary transfer")
def download_bank_advice(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    csv_content = payslip_service.generate_bank_advice_csv(db, run_id)
    filename = f"bank_advice_{run.month_label.replace(' ', '_')}.csv"
    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Compliance Reports ───────────────────────────────────────────────────────

@router.get("/runs/{run_id}/compliance", summary="Statutory compliance summary for a run")
def compliance_summary(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return statutory_service.get_compliance_summary(db, run_id)


@router.get("/runs/{run_id}/compliance/pf-register",
            summary="Download PF register CSV")
def pf_register(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    lines = [
        "Employee Code,Employee Name,Basic,Employee PF (12%),Employer PF (12%),Total PF"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        total_pf = round(_pre_employee_pf(row) + _pre_employer_pf(row), 2)
        lines.append(
            f"{emp_code},{emp_name},{_pre_basic(row):.2f},"
            f"{_pre_employee_pf(row):.2f},{_pre_employer_pf(row):.2f},{total_pf:.2f}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    filename = f"pf_register_{period}.csv"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/compliance/esi-register",
            summary="Download ESI register CSV")
def esi_register(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    lines = [
        "Employee Code,Employee Name,Gross Salary,Employee ESI (0.75%),Employer ESI (3.25%),Total ESI,ESI Applicable"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        applicable = "Yes" if (_pre_employee_esi(row) > 0 or _pre_employer_esi(row) > 0) else "No"
        total_esi = round(_pre_employee_esi(row) + _pre_employer_esi(row), 2)
        lines.append(
            f"{emp_code},{emp_name},{_pre_gross(row):.2f},"
            f"{_pre_employee_esi(row):.2f},{_pre_employer_esi(row):.2f},{total_esi:.2f},{applicable}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    filename = f"esi_register_{period}.csv"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics/summary", summary="Payroll analytics — last 6 runs trend")
def analytics_summary(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRun
    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.notin_(["cancelled"]))
        .order_by(PayrollRun.pay_period_start.desc())
        .limit(6)
        .all()
    )
    trend = []
    for r in reversed(runs):
        trend.append({
            "month": r.month_label,
            "gross": r.total_gross,
            "deductions": r.total_deductions,
            "net": r.total_net,
            "employees": r.total_employees,
            "pf": r.total_pf,
            "esi": r.total_esi,
            "tds": r.total_tds,
            "status": r.status,
        })
    return {"trend": trend}


# ─── Statutory Settings ───────────────────────────────────────────────────────

@router.get("/statutory-settings", response_model=StatutorySettingsOut,
            summary="Get active statutory settings")
def get_statutory_settings(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    s = statutory_service.get_active_settings(db)
    if not s:
        raise HTTPException(status_code=404, detail="No statutory settings configured")
    return s


@router.put("/statutory-settings", response_model=StatutorySettingsOut,
            summary="Update statutory settings (creates new version)")
def update_statutory_settings(
    body: StatutorySettingsIn,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    # Deactivate current active row
    current = statutory_service.get_active_settings(db)
    if current:
        current.is_active = False
        db.flush()
    new_s = StatutorySettings(**body.model_dump(), is_active=True)
    db.add(new_s)
    db.commit()
    db.refresh(new_s)
    return new_s


# ─── Salary Components ────────────────────────────────────────────────────────

@router.get("/salary-components", response_model=list[SalaryComponentOut],
            summary="List salary component master")
def list_salary_components(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_schema_service.list_salary_components(db, active_only=active_only)


@router.post("/salary-components", response_model=SalaryComponentOut,
             status_code=201, summary="Create or update a salary component")
def upsert_salary_component(
    body: SalaryComponentIn,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_schema_service.upsert_salary_component(db, body.model_dump())


# ─── Employee Salary History ──────────────────────────────────────────────────

@router.get("/employee-salary", response_model=list[EmployeeSalaryOut],
            summary="List employee salary history")
def list_employee_salary(
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_schema_service.list_employee_salary(db, employee_id=employee_id)


@router.get("/employee-salary/{employee_id}/active", response_model=EmployeeSalaryOut,
            summary="Get active salary record for an employee")
def get_active_employee_salary(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    rec = payroll_schema_service.get_active_employee_salary(db, employee_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No active salary record found")
    return rec


# ─── Tax Deductions ───────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/tax-deductions", response_model=list[TaxDeductionOut],
            summary="Tax deduction ledger for a payroll run")
def run_tax_deductions(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_schema_service.list_tax_deductions(db, run_id=run_id)


@router.get("/tax-deductions", response_model=list[TaxDeductionOut],
            summary="List tax deductions with optional filters")
def list_tax_deductions(
    employee_id: Optional[int] = None,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    return payroll_schema_service.list_tax_deductions(
        db, employee_id=employee_id, financial_year=financial_year
    )


# ─── Reimbursements ───────────────────────────────────────────────────────────

@router.get("/reimbursements", response_model=list[ReimbursementOut],
            summary="List reimbursement claims")
def list_reimbursements(
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    run_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    rows = payroll_schema_service.list_reimbursements(
        db, employee_id=employee_id, status=status, run_id=run_id
    )
    return [_reimbursement_to_out(r) for r in rows]


@router.post("/reimbursements", response_model=ReimbursementOut,
             status_code=201, summary="Submit a reimbursement claim")
def create_reimbursement(
    body: ReimbursementIn,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    r = payroll_schema_service.create_reimbursement(db, body.model_dump())
    return _reimbursement_to_out(r)


@router.post("/reimbursements/{reimbursement_id}/approve",
             response_model=ReimbursementOut, summary="Approve a reimbursement claim")
def approve_reimbursement(
    reimbursement_id: int,
    body: ReimbursementApproveIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        r = payroll_schema_service.approve_reimbursement(
            db, reimbursement_id, actor, body.approved_amount
        )
        return _reimbursement_to_out(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reimbursements/{reimbursement_id}/reject",
             response_model=ReimbursementOut, summary="Reject a reimbursement claim")
def reject_reimbursement(
    reimbursement_id: int,
    body: ReimbursementRejectIn,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    try:
        r = payroll_schema_service.reject_reimbursement(
            db, reimbursement_id, actor, body.remarks
        )
        return _reimbursement_to_out(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reimbursements/{reimbursement_id}/mark-paid",
             response_model=ReimbursementOut, summary="Mark reimbursement as paid")
def mark_reimbursement_paid(
    reimbursement_id: int,
    body: ReimbursementMarkPaidIn,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    try:
        r = payroll_schema_service.mark_reimbursement_paid(
            db, reimbursement_id, body.payroll_run_id
        )
        return _reimbursement_to_out(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reimbursements/{reimbursement_id}/cancel",
             response_model=ReimbursementOut, summary="Cancel a reimbursement claim")
def cancel_reimbursement(
    reimbursement_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    try:
        r = payroll_schema_service.cancel_reimbursement(db, reimbursement_id)
        return _reimbursement_to_out(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Missing Salary Structures ───────────────────────────────────────────────

@router.get("/employees/missing-salary-structure",
            summary="List active employees with no salary structure")
def employees_missing_structure(
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    """Returns employees that cannot be processed in payroll due to missing / ₹0 structure."""
    return payroll_service.list_employees_missing_salary_structure(db)


# ─── Additional Compliance / Payroll Reports ──────────────────────────────────

@router.get("/runs/{run_id}/compliance/pt-register",
            summary="Download Professional Tax register CSV")
def pt_register(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    lines = ["Employee Code,Employee Name,Gross Salary,Professional Tax"]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        lines.append(f"{emp_code},{emp_name},{_pre_gross(row):.2f},{row.professional_tax:.2f}")
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pt_register_{period}.csv"'},
    )


@router.get("/runs/{run_id}/compliance/tds-report",
            summary="Download TDS report CSV")
def tds_report(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    from app.models.payroll_extended import EmployeeTaxDeclaration
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    lines = [
        "Employee Code,Employee Name,Gross Salary,Annual Gross (Est.),Tax Regime,"
        "80C,80D,HRA Exemption,Monthly TDS"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        decl = (
            db.query(EmployeeTaxDeclaration)
            .filter_by(employee_id=emp.id)
            .order_by(EmployeeTaxDeclaration.financial_year.desc())
            .first()
        )
        regime = "New" if (decl and decl.opted_new_regime) else "Old"
        sec80c = decl.sec_80c if decl else 0.0
        sec80d = decl.sec_80d if decl else 0.0
        hra_ex = decl.hra_exemption if decl else 0.0
        annual_gross = _pre_gross(row) * 12
        lines.append(
            f"{emp_code},{emp_name},{_pre_gross(row):.2f},{annual_gross:.2f},"
            f"{regime},{sec80c:.2f},{sec80d:.2f},{hra_ex:.2f},{row.tds:.2f}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="tds_report_{period}.csv"'},
    )


@router.get("/runs/{run_id}/payroll-register",
            summary="Download full payroll register CSV")
def payroll_register(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    lines = [
        "Employee Code,Employee Name,Department,Designation,"
        "Working Days,Present Days,LOP Days,"
        "Basic,HRA,Allowances,Gross Salary,"
        "PF Employee,PF Employer,ESI Employee,ESI Employer,"
        "Professional Tax,TDS,Other Deductions,Total Deductions,Net Salary"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        dept = emp.department.name if emp.department else ""
        desig = emp.designation.title if emp.designation else ""
        lines.append(
            f"{emp_code},{emp_name},{dept},{desig},"
            f"{row.working_days},{row.present_days},{row.lop_days},"
            f"{_pre_basic(row):.2f},{row.hra:.2f},{_pre_allowance(row):.2f},{_pre_gross(row):.2f},"
            f"{_pre_employee_pf(row):.2f},{_pre_employer_pf(row):.2f},"
            f"{_pre_employee_esi(row):.2f},{_pre_employer_esi(row):.2f},"
            f"{row.professional_tax:.2f},{row.tds:.2f},"
            f"{row.other_deductions:.2f},{row.total_deductions:.2f},{_pre_net(row):.2f}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payroll_register_{period}.csv"'},
    )


@router.get("/runs/{run_id}/bonus-report",
            summary="Download bonus report CSV for a payroll run")
def bonus_report(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import PayrollAdjustment
    rows = (
        db.query(PayrollAdjustment)
        .filter_by(run_id=run_id, adjustment_type="bonus")
        .all()
    )
    run = payroll_service.get_payroll_run(db, run_id)
    lines = ["Employee Code,Employee Name,Department,Bonus Type,Direction,Amount,Taxable,Description"]
    for adj in rows:
        emp = adj.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        dept = emp.department.name if emp.department else ""
        taxable = "Yes" if adj.is_taxable else "No"
        desc = (adj.description or "").replace(",", ";")
        lines.append(
            f"{emp_code},{emp_name},{dept},Bonus,{adj.direction},{adj.amount:.2f},{taxable},{desc}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="bonus_report_{period}.csv"'},
    )


@router.get("/runs/{run_id}/variable-pay-report",
            summary="Download variable pay report CSV for a payroll run")
def variable_pay_report(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import PayrollAdjustment
    rows = (
        db.query(PayrollAdjustment)
        .filter_by(run_id=run_id, adjustment_type="variable_pay")
        .all()
    )
    run = payroll_service.get_payroll_run(db, run_id)
    lines = ["Employee Code,Employee Name,Department,Type,Direction,Amount,Taxable,Description"]
    for adj in rows:
        emp = adj.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        dept = emp.department.name if emp.department else ""
        taxable = "Yes" if adj.is_taxable else "No"
        desc = (adj.description or "").replace(",", ";")
        lines.append(
            f"{emp_code},{emp_name},{dept},Variable Pay,{adj.direction},{adj.amount:.2f},{taxable},{desc}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="variable_pay_report_{period}.csv"'},
    )


@router.get("/runs/{run_id}/reimbursement-report",
            summary="Download reimbursement report CSV for a payroll run")
def reimbursement_report(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import Reimbursement
    rows = (
        db.query(Reimbursement)
        .filter_by(payroll_run_id=run_id)
        .all()
    )
    run = payroll_service.get_payroll_run(db, run_id)
    lines = ["Employee Code,Employee Name,Claim Type,Claim Amount,Approved Amount,Status,Remarks"]
    for r in rows:
        emp = r.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        approved = r.approved_amount if r.approved_amount is not None else ""
        remarks = (r.remarks or "").replace(",", ";")
        lines.append(
            f"{emp_code},{emp_name},{r.claim_type},{r.claim_amount:.2f},{approved},{r.status},{remarks}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reimbursement_report_{period}.csv"'},
    )


@router.get("/runs/{run_id}/gratuity-report",
            summary="Download gratuity provision report CSV for a payroll run")
def gratuity_report(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee, SalaryStructure
    from app.services.statutory_service import get_active_settings
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    run = payroll_service.get_payroll_run(db, run_id)
    s = get_active_settings(db)
    gratuity_rate = s.gratuity_rate if s else 0.0481
    min_years = s.gratuity_eligibility_years if s else 5.0
    lines = [
        "Employee Code,Employee Name,Department,Date of Joining,Years of Service,"
        "Basic Monthly,Annual Gratuity Provision,Eligible (5yr+),Gratuity Payable (FF),Eligibility Reason"
    ]
    from datetime import date
    from app.services.statutory_service import compute_gratuity
    today = date.today()
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        dept = emp.department.name if emp.department else ""
        doj = getattr(emp, "date_of_joining", None) or getattr(emp, "joining_date", None)
        if doj:
            years = round((today - doj).days / 365.25, 2)
            eligible = "Yes" if years >= min_years else "No"
            if years >= min_years:
                eligibility_reason = f"{years} yrs service (>= {min_years} yrs)"
                ff_gratuity = compute_gratuity(_pre_basic(row), doj, today, db)
            else:
                remaining = round(min_years - years, 2)
                eligibility_reason = f"Only {years} yrs — needs {remaining} more yrs"
                ff_gratuity = 0.0
        else:
            years = ""
            eligible = "Unknown"
            eligibility_reason = "Date of joining not set"
            ff_gratuity = 0.0
        annual_provision = round(_pre_basic(row) * gratuity_rate * 12, 2)
        doj_str = doj.isoformat() if doj else ""
        lines.append(
            f"{emp_code},{emp_name},{dept},{doj_str},{years},"
            f"{_pre_basic(row):.2f},{annual_provision:.2f},{eligible},{ff_gratuity:.2f},"
            f"\"{eligibility_reason}\""
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="gratuity_report_{period}.csv"'},
    )


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@router.get("/admin-dashboard-stats",
            summary="Admin dashboard — real-time payroll status for Admin role")
def admin_dashboard_stats(
    run_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,   # finance_head must also reach this endpoint
):
    """Read-only view of payroll status for Admin dashboard.
    Pass run_id to switch between historical payroll runs.
    """
    from app.models.payroll import PayrollRun, PayrollRunEmployee, SalaryStructure
    from app.models.payroll_extended import Payslip
    stats = payroll_service.get_dashboard_stats(db)

    # If run_id given, use that specific run; otherwise use current
    if run_id:
        run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    else:
        run = stats["current_run"]

    total_active = stats["total_employees"]
    structured_count = (
        db.query(SalaryStructure)
        .filter(SalaryStructure.is_active.is_(True), SalaryStructure.gross_monthly > 0)
        .count()
    )

    payslip_generated = 0
    payslip_published = 0
    email_sent_count = 0
    variance_count = 0
    approval_status = None
    run_employees = []
    if run:
        payslip_generated = db.query(Payslip).filter_by(run_id=run.id).count()
        payslip_published = db.query(Payslip).filter_by(run_id=run.id, is_published=True).count()
        email_sent_count = db.query(Payslip).filter_by(run_id=run.id, email_sent=True).count()
        from app.models.payroll import PayrollRunEmployee as PRE
        rows = db.query(PRE).filter_by(run_id=run.id).all()
        for row in rows:
            emp = row.employee
            run_employees.append({
                "employee_id": row.employee_id,
                "employee_name": f"{emp.first_name} {emp.last_name or ''}".strip() if emp else "—",
                "department": emp.department.name if emp and emp.department else "—",
                "designation": emp.designation.title if emp and emp.designation else "—",
                "gross_salary": _pre_gross(row),
                "gross_earnings": _pre_gross(row),
                "total_deductions": row.total_deductions,
                "net_salary": _pre_net(row),
                "net_pay": _pre_net(row),
                "lop_days": row.lop_days,
                "has_error": row.has_error,
                "is_locked": row.is_locked,
                "payslip_generated": row.payslip_generated,
                "record_status": row.record_status,
                "variance_flag": row.variance_flag,
                "variance_reason": row.variance_reason,
            })
        variance_count = db.query(PRE).filter_by(run_id=run.id, variance_flag=True).count()
        approval_status = payroll_service._approval_status_summary(db, run.id)

    recent_runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.notin_(["cancelled"]))
        .order_by(PayrollRun.pay_period_start.desc())
        .limit(12)
        .all()
    )

    is_closed = run and run.status in ("closed", "published", "payslip_generated", "approved")

    # Build department summary for the SELECTED run (not always the live run)
    department_summary = payroll_service._build_dept_summary(db, run) if run else []

    # Compute open errors and completion % for the selected run accurately.
    # For final/closed runs this is always 0 errors and 100% complete.
    from app.models.payroll import PayrollError as _RunPayrollError
    if run:
        if run.status in ("closed", "published", "payslip_generated", "approved"):
            run_open_errors = 0
            run_completion_pct = 100.0
        else:
            run_open_errors = (
                db.query(_RunPayrollError)
                .filter_by(run_id=run.id, is_resolved=False)
                .count()
            )
            run_completion_pct = 0.0
            if run.total_employees and run.total_employees > 0:
                processed = (
                    db.query(PayrollRunEmployee)
                    .filter_by(run_id=run.id, is_locked=False, has_error=False)
                    .count()
                )
                run_completion_pct = round(processed / run.total_employees * 100, 1)
    else:
        run_open_errors = 0
        run_completion_pct = 0.0

    return {
        "total_active_employees": total_active,
        "salary_structure_count": structured_count,
        "salary_structure_missing": max(total_active - structured_count, 0),
        "current_run": {
            "id": run.id,
            "payroll_run_id": run.id,
            "payroll_run_code": run.payroll_run_code,
            "month_label": run.month_label,
            "month": run.month,
            "year": run.year,
            "status": run.status,
            "run_status": run.status,
            "lifecycle_status": payroll_service.document_lifecycle_status(run.status, run.payroll_locked),
            "total_employees": run.total_employees,
            "total_gross": run.total_gross,
            "total_net": run.total_net,
            "total_net_pay": run.total_net,
            "total_deductions": run.total_deductions,
            "total_pf": run.total_pf,
            "total_esi": run.total_esi,
            "total_tds": run.total_tds,
            "total_pt": run.total_pt,
            "open_errors": run_open_errors,
            "payroll_completion_pct": run_completion_pct,
            "payslip_generated": payslip_generated,
            "payslip_published": payslip_published,
            "email_sent": email_sent_count,
            "emailed_count": email_sent_count,
            "variance_count": variance_count,
            "approval_status": approval_status,
            "finance_review_status": approval_status.get("FINANCE_REVIEW") if approval_status else None,
            "payroll_locked": bool(run.payroll_locked),
            "finalized_at": run.finalized_at,
            "published_at": run.published_at,
            "is_read_only": bool(is_closed),
            "attendance_frozen": bool(run.attendance_locked or run.status not in ("draft",)),
            "finance_reviewed": run.status in (
                "under_review", "error_found", "pending_head_approval",
                "approved", "payslip_generated", "published", "closed",
            ),
            "finance_head_approved": run.status in (
                "approved", "payslip_generated", "published", "closed",
            ),
            "payslips_published": run.status in ("published", "closed"),
        } if run else None,
        "run_employees": run_employees,
        "department_summary": department_summary,
        "recent_runs": [
            {
                "id": r.id,
                "payroll_run_code": r.payroll_run_code,
                "month_label": r.month_label,
                "status": r.status,
                "lifecycle_status": payroll_service.document_lifecycle_status(r.status, r.payroll_locked),
                "total_employees": r.total_employees,
                "total_gross": r.total_gross,
                "total_net": r.total_net,
                "total_deductions": r.total_deductions,
                "pay_period_start": r.pay_period_start.isoformat() if r.pay_period_start else None,
            }
            for r in recent_runs
        ],
        "pending_approval_count": stats["pending_approval_count"],
        "last_run_net": stats["last_run_net"],
    }


# ─── Tax Declarations (Employee TDS declarations) ─────────────────────────────

@router.get("/tax-declarations",
            summary="List employee tax declarations")
def list_tax_declarations(
    employee_id: Optional[int] = None,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import EmployeeTaxDeclaration
    q = db.query(EmployeeTaxDeclaration)
    if employee_id:
        q = q.filter_by(employee_id=employee_id)
    if financial_year:
        q = q.filter_by(financial_year=financial_year)
    declarations = q.order_by(
        EmployeeTaxDeclaration.financial_year.desc()
    ).all()
    result = []
    for d in declarations:
        emp = d.employee
        result.append({
            "id": d.id,
            "employee_id": d.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "—",
            "financial_year": d.financial_year,
            "sec_80c": d.sec_80c,
            "sec_80d": d.sec_80d,
            "sec_80ccd": d.sec_80ccd,
            "hra_exemption": d.hra_exemption,
            "sec_24b": d.sec_24b,
            "other_deductions": d.other_deductions,
            "opted_new_regime": d.opted_new_regime,
            "created_at": d.created_at,
        })
    return result


@router.put("/tax-declarations",
            summary="Create or update tax declaration for an employee")
def upsert_tax_declaration(
    body: dict,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import EmployeeTaxDeclaration
    employee_id = body.get("employee_id")
    financial_year = body.get("financial_year")
    if not employee_id or not financial_year:
        raise HTTPException(status_code=400, detail="employee_id and financial_year are required")

    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=financial_year)
        .first()
    )
    if not decl:
        decl = EmployeeTaxDeclaration(
            employee_id=employee_id,
            financial_year=financial_year,
        )
        db.add(decl)

    for field in ("sec_80c", "sec_80d", "sec_80ccd", "hra_exemption", "sec_24b",
                  "other_deductions", "opted_new_regime"):
        if field in body:
            setattr(decl, field, body[field])

    db.commit()
    db.refresh(decl)

    # Refresh TDS in salary structure immediately
    try:
        from app.services.statutory_service import refresh_tds_for_employee
        refresh_tds_for_employee(db, employee_id)
    except Exception:
        pass

    emp = decl.employee
    return {
        "id": decl.id,
        "employee_id": decl.employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "—",
        "financial_year": decl.financial_year,
        "sec_80c": decl.sec_80c,
        "sec_80d": decl.sec_80d,
        "sec_80ccd": decl.sec_80ccd,
        "hra_exemption": decl.hra_exemption,
        "sec_24b": decl.sec_24b,
        "other_deductions": decl.other_deductions,
        "opted_new_regime": decl.opted_new_regime,
    }


# ─── Helper ───────────────────────────────────────────────────────────────────

def _reimbursement_to_out(r) -> ReimbursementOut:
    from app.models.payroll_extended import Reimbursement as _R
    emp = r.employee
    return ReimbursementOut(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}" if emp else "—",
        payroll_run_id=r.payroll_run_id,
        claim_type=r.claim_type,
        claim_amount=r.claim_amount,
        approved_amount=r.approved_amount,
        status=r.status,
        approved_by_id=r.approved_by_id,
        approved_at=r.approved_at,
        remarks=r.remarks,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _reimb_extra(r) -> dict:
    """Extra fields added in the enterprise hardening that may not be in the schema."""
    mgr = getattr(r, "manager_approved_by", None)
    return {
        "manager_approved_by_id": getattr(r, "manager_approved_by_id", None),
        "manager_approved_at": getattr(r, "manager_approved_at", None),
        "manager_remarks": getattr(r, "manager_remarks", None),
        "is_taxable": getattr(r, "is_taxable", False),
        "description": getattr(r, "description", None),
        "receipt_url": getattr(r, "receipt_url", None),
        "manager_approved_by_name": (
            f"{mgr.first_name} {mgr.last_name or ''}".strip() if mgr else None
        ),
    }


def _payslip_to_out(s: Payslip) -> PayslipOut:
    emp = s.employee
    return PayslipOut(
        id=s.id,
        payslip_id=s.id,
        payroll_record_id=s.payroll_record_id,
        run_id=s.run_id,
        payroll_run_id=s.run_id,
        employee_id=s.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}" if emp else "—",
        month_label=s.month_label,
        month=s.month,
        year=s.year,
        payslip_number=s.payslip_number,
        pay_period_start=s.pay_period_start,
        pay_period_end=s.pay_period_end,
        gross_salary=s.gross_salary,
        total_deductions=s.total_deductions,
        net_salary=s.net_salary,
        pdf_path=s.pdf_path,
        file_url=s.file_url,
        payslip_url=s.file_url or s.pdf_path,
        pdf_generated_at=s.pdf_generated_at,
        status=s.status,
        generated_by=s.generated_by_id,
        generated_at=s.generated_at,
        is_published=s.is_published,
        published_at=s.published_at,
        email_sent=s.email_sent,
        emailed_at=s.emailed_at or s.email_sent_at,
        download_count=s.download_count,
        created_at=s.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTERPRISE PAYROLL HARDENING — Additional endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Attendance Freeze / Hardening ────────────────────────────────────────────

@router.get("/runs/{run_id}/attendance-summary",
            summary="Attendance snapshot for a payroll run")
def get_attendance_summary(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.attendance_records import PayrollAttendanceSummary
    rows = db.query(PayrollAttendanceSummary).filter_by(payroll_run_id=run_id).all()
    result = []
    for r in rows:
        emp = db.query(Employee).filter(Employee.id == r.employee_id).first()
        result.append({
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name or ''}".strip() if emp else "—",
            "working_days": r.total_working_days,
            "total_working_days": r.total_working_days,
            "present_days": r.present_days,
            "leave_days": r.leave_days,
            "lop_days": r.lop_days,
            "holiday_days": r.holiday_count,
            "payable_days": getattr(r, "payable_days", r.present_days),
            "overtime_hours": getattr(r, "overtime_hours", 0),
            "is_finalized": r.is_finalized,
            "attendance_status": getattr(r, "attendance_status", "pending"),
        })
    return result


@router.post("/runs/{run_id}/attendance-summary/freeze",
             summary="Freeze attendance for all employees in a run")
def freeze_attendance(
    run_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    from app.models.attendance_records import PayrollAttendanceSummary
    rows = db.query(PayrollAttendanceSummary).filter_by(payroll_run_id=run_id).all()
    if not rows:
        try:
            payroll_service.advance_run_status(
                db, run_id, "freeze_attendance",
                "No finalized attendance rows yet; payroll will use temporary fallback values.",
                actor,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "detail": "No attendance summary rows found; payroll fallback values will be used.",
            "frozen_count": 0,
        }
    unfrozen = [r for r in rows if getattr(r, "attendance_status", "pending") != "frozen"]
    for r in unfrozen:
        r.attendance_status = "frozen"
    run = payroll_service.get_payroll_run(db, run_id)
    if run and run.status == "draft":
        try:
            payroll_service.advance_run_status(db, run_id, "freeze_attendance", "Attendance summary frozen", actor)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {"detail": f"Attendance frozen for {len(rows)} employee(s)", "frozen_count": len(rows)}


@router.post("/runs/{run_id}/attendance-summary/unfreeze",
             summary="Unfreeze attendance (revert to pending) for corrections")
def unfreeze_attendance(
    run_id: int,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    run = payroll_service.get_payroll_run(db, run_id)
    if run and run.status not in ("draft", "attendance_frozen"):
        raise HTTPException(status_code=400, detail="Cannot unfreeze attendance after payroll generation has started.")
    from app.models.attendance_records import PayrollAttendanceSummary
    rows = db.query(PayrollAttendanceSummary).filter_by(payroll_run_id=run_id).all()
    for r in rows:
        r.attendance_status = "pending"
    db.commit()
    return {"detail": f"Attendance unfrozen for {len(rows)} employee(s)"}


@router.post("/runs/{run_id}/attendance-summary/upsert",
             status_code=201,
             summary="Upsert attendance summary for an employee in a run")
def upsert_attendance_summary(
    run_id: int,
    body: dict,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    from app.models.attendance_records import PayrollAttendanceSummary
    employee_id = body.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id required")

    record = db.query(PayrollAttendanceSummary).filter_by(
        payroll_run_id=run_id, employee_id=employee_id
    ).first()
    if not record:
        run = payroll_service.get_payroll_run(db, run_id)
        next_id = db.query(PayrollAttendanceSummary).count() + 1
        record = PayrollAttendanceSummary(
            id=f"PAS{next_id:05d}",
            payroll_run_id=run_id,
            employee_id=employee_id,
            month=run.pay_period_start.strftime("%B") if run else body.get("month"),
            year=run.pay_period_start.year if run else body.get("year"),
        )
        db.add(record)

    field_map = {
        "working_days": "total_working_days",
        "total_working_days": "total_working_days",
        "present_days": "present_days",
        "leave_days": "leave_days",
        "lop_days": "lop_days",
        "holiday_days": "holiday_count",
        "holiday_count": "holiday_count",
        "payable_days": "payable_days",
        "overtime_hours": "overtime_hours",
        "attendance_status": "attendance_status",
        "is_finalized": "is_finalized",
    }
    for field, attr in field_map.items():
        if field in body:
            setattr(record, attr, body[field])

    db.commit()
    db.refresh(record)
    return {"detail": "Attendance summary upserted", "id": record.id}


# ─── Reimbursement Manager Approval ──────────────────────────────────────────

@router.post("/reimbursements/{reimbursement_id}/manager-approve",
             summary="Manager pre-approves a reimbursement claim")
def manager_approve_reimbursement(
    reimbursement_id: int,
    body: dict,
    db: Session = Depends(get_db),
    actor: Employee = Depends(role_required("finance", "admin", "manager", "finance_head")),
):
    from app.models.payroll_extended import Reimbursement
    from datetime import datetime
    r = db.query(Reimbursement).filter(Reimbursement.id == reimbursement_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reimbursement not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot manager-approve in status '{r.status}'")

    r.manager_approved_by_id = actor.id
    r.manager_approved_at = datetime.utcnow()
    r.manager_remarks = body.get("remarks")
    r.status = "manager_approved"
    db.commit()
    db.refresh(r)
    return {
        "id": r.id,
        "status": r.status,
        "manager_approved_by_id": r.manager_approved_by_id,
        "manager_approved_at": r.manager_approved_at,
        "manager_remarks": r.manager_remarks,
    }


@router.post("/reimbursements/{reimbursement_id}/manager-reject",
             summary="Manager rejects a reimbursement claim")
def manager_reject_reimbursement(
    reimbursement_id: int,
    body: dict,
    db: Session = Depends(get_db),
    actor: Employee = Depends(role_required("finance", "admin", "manager", "finance_head")),
):
    from app.models.payroll_extended import Reimbursement
    r = db.query(Reimbursement).filter(Reimbursement.id == reimbursement_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reimbursement not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot reject in status '{r.status}'")
    r.status = "rejected"
    r.remarks = body.get("remarks", "Rejected by manager")
    db.commit()
    return {"id": r.id, "status": r.status}


# ─── Tax Declaration Approval Flow ────────────────────────────────────────────

@router.get("/tax-declarations/{declaration_id}",
            summary="Get a single tax declaration with proof status")
def get_tax_declaration(
    declaration_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import EmployeeTaxDeclaration
    d = db.query(EmployeeTaxDeclaration).filter(EmployeeTaxDeclaration.id == declaration_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Declaration not found")
    emp = d.employee
    verified_by = d.verified_by
    return {
        "id": d.id,
        "employee_id": d.employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name or ''}".strip() if emp else "—",
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
        "verified_by_id": d.verified_by_id,
        "verified_by_name": f"{verified_by.first_name} {verified_by.last_name or ''}".strip() if verified_by else None,
        "submitted_at": d.submitted_at,
        "created_at": d.created_at,
    }


@router.post("/tax-declarations/{declaration_id}/verify",
             summary="HR/Finance verifies tax declaration proofs")
def verify_tax_declaration(
    declaration_id: int,
    body: dict,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    from app.models.payroll_extended import EmployeeTaxDeclaration
    from datetime import datetime
    d = db.query(EmployeeTaxDeclaration).filter(EmployeeTaxDeclaration.id == declaration_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Declaration not found")
    if not d.proof_submitted:
        raise HTTPException(status_code=400, detail="Proof has not been submitted yet")

    approved = body.get("approved", True)
    if approved:
        d.proof_verified = True
        d.verified_by_id = actor.id
        # Apply overrides if HR wants to adjust the declared amounts after proof review
        for field in ("sec_80c", "sec_80d", "sec_80ccd", "hra_exemption", "sec_24b", "other_deductions"):
            if field in body:
                setattr(d, field, float(body[field]))
        db.commit()
        # Recompute TDS with verified declarations
        try:
            from app.services.statutory_service import refresh_tds_for_employee
            refresh_tds_for_employee(db, d.employee_id)
        except Exception:
            pass
        return {"detail": "Declaration verified and TDS recomputed", "id": d.id, "proof_verified": True}
    else:
        d.proof_verified = False
        d.verified_by_id = actor.id
        db.commit()
        return {"detail": "Declaration proof rejected", "id": d.id, "proof_verified": False}


@router.post("/tax-declarations/{declaration_id}/submit-proof",
             summary="Mark proof as submitted for a declaration")
def submit_tax_declaration_proof(
    declaration_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import EmployeeTaxDeclaration
    from datetime import datetime
    d = db.query(EmployeeTaxDeclaration).filter(EmployeeTaxDeclaration.id == declaration_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Declaration not found")
    d.proof_submitted = True
    d.submitted_at = datetime.utcnow()
    db.commit()
    return {"detail": "Proof submission recorded", "id": d.id}


# ─── Payslip Email (on-demand, single run) ────────────────────────────────────

@router.post("/runs/{run_id}/payslips/send-emails",
             summary="Send payslip emails to all published employees in a run")
def send_payslip_emails(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    result = payslip_service.send_payslip_emails_for_run(db, run_id)
    return result


# ─── Compliance: Form 16 ──────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/form16",
            summary="Generate Form 16 annual TDS certificate (CSV)")
def form16(
    employee_id: int,
    financial_year: str = "2025-26",
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import TaxDeduction, EmployeeTaxDeclaration
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    deductions = (
        db.query(TaxDeduction)
        .filter_by(employee_id=employee_id, financial_year=financial_year.replace("-", "-20") if len(financial_year) < 8 else financial_year)
        .order_by(TaxDeduction.month)
        .all()
    )
    if not deductions:
        deductions = (
            db.query(TaxDeduction)
            .filter(TaxDeduction.employee_id == employee_id)
            .order_by(TaxDeduction.year, TaxDeduction.month)
            .all()
        )

    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=financial_year)
        .first()
    )

    emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
    emp_code = emp.employee_code or f"EMP{emp.id:04d}"

    total_gross = sum(d.pf_employee + d.esi_employee + d.professional_tax + d.tds + d.total_tax_deductions for d in deductions) if deductions else 0
    total_tds = sum(d.tds for d in deductions)
    total_pf = sum(d.pf_employee for d in deductions)
    total_esi = sum(d.esi_employee for d in deductions)
    total_pt = sum(d.professional_tax for d in deductions)

    lines = [
        f"FORM 16 — Annual TDS Certificate",
        f"Financial Year: {financial_year}",
        f"",
        f"PART A — TDS Details",
        f"Employee Name,{emp_name}",
        f"Employee Code,{emp_code}",
        f"PAN,{getattr(emp, 'pan', 'PENDING')}",
        f"Employer,Acronotics Inc.",
        f"",
        f"Month,Gross Salary (Est.),TDS Deducted,PF,ESI,Professional Tax",
    ]
    MONTHS = ["", "April", "May", "June", "July", "August", "September",
              "October", "November", "December", "January", "February", "March"]
    for d in deductions:
        m = MONTHS[d.month] if 1 <= d.month <= 12 else str(d.month)
        lines.append(
            f"{m} {d.year},{d.total_tax_deductions:.2f},{d.tds:.2f},{d.pf_employee:.2f},{d.esi_employee:.2f},{d.professional_tax:.2f}"
        )

    lines += [
        f"",
        f"TOTAL,,{total_tds:.2f},{total_pf:.2f},{total_esi:.2f},{total_pt:.2f}",
        f"",
        f"PART B — Declaration Details",
        f"Tax Regime,{'New Regime' if (decl and decl.opted_new_regime) else 'Old Regime'}",
        f"Section 80C,{decl.sec_80c if decl else 0:.2f}",
        f"Section 80D,{decl.sec_80d if decl else 0:.2f}",
        f"NPS (80CCD),{decl.sec_80ccd if decl else 0:.2f}",
        f"HRA Exemption,{decl.hra_exemption if decl else 0:.2f}",
        f"Home Loan Interest 24(b),{decl.sec_24b if decl else 0:.2f}",
        f"Other Deductions,{decl.other_deductions if decl else 0:.2f}",
        f"Proof Submitted,{'Yes' if (decl and decl.proof_submitted) else 'No'}",
        f"Proof Verified,{'Yes' if (decl and decl.proof_verified) else 'No'}",
    ]

    filename = f"form16_{emp_code}_{financial_year.replace('-', '_')}.csv"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/compliance/form16-batch",
            summary="Download Form 16 batch for all employees in a run")
def form16_batch(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    from app.models.payroll_extended import TaxDeduction, EmployeeTaxDeclaration
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    fy_start = run.pay_period_start.year if run.pay_period_start.month >= 4 else run.pay_period_start.year - 1
    financial_year = f"{fy_start}-{str(fy_start + 1)[-2:]}"

    lines = [
        "Employee Code,Employee Name,PAN,Financial Year,Tax Regime,"
        "Gross Salary,Total TDS,PF Employee,ESI Employee,Prof Tax,"
        "80C,80D,NPS,HRA Exemption,24b,Other Deductions,Proof Submitted,Proof Verified"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        pan = getattr(emp, "pan", "—")

        td_rows = db.query(TaxDeduction).filter_by(employee_id=emp.id, run_id=run_id).all()
        total_tds = sum(d.tds for d in td_rows)
        total_pf = sum(d.pf_employee for d in td_rows)
        total_esi = sum(d.esi_employee for d in td_rows)
        total_pt = sum(d.professional_tax for d in td_rows)

        decl = (
            db.query(EmployeeTaxDeclaration)
            .filter_by(employee_id=emp.id, financial_year=financial_year)
            .first()
        )
        regime = "New" if (decl and decl.opted_new_regime) else "Old"
        lines.append(
            f"{emp_code},{emp_name},{pan},{financial_year},{regime},"
            f"{_pre_gross(row):.2f},{total_tds:.2f},{total_pf:.2f},{total_esi:.2f},{total_pt:.2f},"
            f"{decl.sec_80c if decl else 0:.2f},"
            f"{decl.sec_80d if decl else 0:.2f},"
            f"{decl.sec_80ccd if decl else 0:.2f},"
            f"{decl.hra_exemption if decl else 0:.2f},"
            f"{decl.sec_24b if decl else 0:.2f},"
            f"{decl.other_deductions if decl else 0:.2f},"
            f"{'Yes' if (decl and decl.proof_submitted) else 'No'},"
            f"{'Yes' if (decl and decl.proof_verified) else 'No'}"
        )

    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="form16_batch_{period}.csv"'},
    )


@router.get("/runs/{run_id}/compliance/pf-challan",
            summary="Download PF challan format for ECR upload")
def pf_challan(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    lines = [
        "#,UAN,Employee Name,Gross Wages,EPF Wages,EPS Wages,EPF Contribution,EPS Contribution,"
        "EPF EPS Diff,NCP Days,Refund of Advances"
    ]
    for idx, row in enumerate(rows, 1):
        emp = row.employee
        if not emp:
            continue
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        uan = getattr(emp, "uan_number", "") or ""
        eps_wages = min(_pre_basic(row), 15000)
        eps_contribution = round(eps_wages * 0.0833, 2)
        epf_contribution = _pre_employer_pf(row)
        diff = round(epf_contribution - eps_contribution, 2)
        ncp_days = row.lop_days or 0
        lines.append(
            f"{idx},{uan},{emp_name},{_pre_gross(row):.0f},{min(_pre_basic(row),15000):.0f},"
            f"{eps_wages:.0f},{epf_contribution:.2f},{eps_contribution:.2f},"
            f"{diff:.2f},{ncp_days},0"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pf_challan_{period}.csv"'},
    )


@router.get("/runs/{run_id}/compliance/esi-filing",
            summary="Download ESI monthly contribution filing format")
def esi_filing(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll import PayrollRunEmployee
    run = payroll_service.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run_id).all()
    lines = [
        "IP No (ESIC),Employee Name,Days/Hours Worked,Total Wages,"
        "ESI Employee (0.75%),ESI Employer (3.25%),Total ESI,Applicable"
    ]
    for row in rows:
        emp = row.employee
        if not emp:
            continue
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        ip_no = getattr(emp, "esic_number", "") or ""
        applicable = "Yes" if (_pre_employee_esi(row) > 0 or _pre_employer_esi(row) > 0) else "No"
        total_esi = round(_pre_employee_esi(row) + _pre_employer_esi(row), 2)
        days = row.present_days or row.working_days or 26
        lines.append(
            f"{ip_no},{emp_name},{days},{_pre_gross(row):.2f},"
            f"{_pre_employee_esi(row):.2f},{_pre_employer_esi(row):.2f},{total_esi:.2f},{applicable}"
        )
    period = run.month_label.replace(" ", "_") if run else f"run{run_id}"
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="esi_filing_{period}.csv"'},
    )


@router.get("/compliance/tds-quarterly",
            summary="TDS quarterly return data (Form 24Q compatible)")
def tds_quarterly_return(
    financial_year: str = "2025-26",
    quarter: int = 4,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    from app.models.payroll_extended import TaxDeduction, EmployeeTaxDeclaration
    # Q1: Apr-Jun, Q2: Jul-Sep, Q3: Oct-Dec, Q4: Jan-Mar
    quarter_months = {1: [4, 5, 6], 2: [7, 8, 9], 3: [10, 11, 12], 4: [1, 2, 3]}
    months = quarter_months.get(quarter, [1, 2, 3])

    fy_year = int(financial_year.split("-")[0])
    year_for_months = fy_year + 1 if quarter == 4 else fy_year

    deductions = (
        db.query(TaxDeduction)
        .filter(
            TaxDeduction.month.in_(months),
            TaxDeduction.year == year_for_months,
        )
        .all()
    )

    lines = [
        f"Form 24Q — TDS Quarterly Return",
        f"Financial Year: {financial_year}, Quarter: Q{quarter}",
        f"Months: {', '.join(str(m) for m in months)} ({year_for_months})",
        f"",
        f"Employee Code,Employee Name,PAN,Tax Regime,Monthly Salary (Est.),TDS This Quarter,PF,ESI,PT",
    ]

    from collections import defaultdict
    emp_data: dict = defaultdict(lambda: {"tds": 0.0, "pf": 0.0, "esi": 0.0, "pt": 0.0, "months": 0})
    for d in deductions:
        emp_data[d.employee_id]["tds"] += d.tds
        emp_data[d.employee_id]["pf"] += d.pf_employee
        emp_data[d.employee_id]["esi"] += d.esi_employee
        emp_data[d.employee_id]["pt"] += d.professional_tax
        emp_data[d.employee_id]["months"] += 1

    for employee_id, totals in emp_data.items():
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            continue
        emp_code = emp.employee_code or f"EMP{emp.id:04d}"
        emp_name = f"{emp.first_name} {emp.last_name or ''}".strip()
        pan = getattr(emp, "pan", "—")
        decl = (
            db.query(EmployeeTaxDeclaration)
            .filter_by(employee_id=employee_id, financial_year=financial_year)
            .first()
        )
        regime = "New" if (decl and decl.opted_new_regime) else "Old"
        lines.append(
            f"{emp_code},{emp_name},{pan},{regime},"
            f"—,{totals['tds']:.2f},{totals['pf']:.2f},{totals['esi']:.2f},{totals['pt']:.2f}"
        )

    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="tds_quarterly_Q{quarter}_{financial_year}.csv"'
        },
    )


# ─── Payroll Variance Report & Acknowledgement ────────────────────────────────

@router.get(
    "/runs/{run_id}/variance",
    summary="[Finance/Admin] Payroll variance report vs previous closed run",
)
def get_payroll_variance(
    run_id: int,
    db: Session = Depends(get_db),
    _: Employee = FinanceUser,
):
    """Return per-employee variance vs the previous closed payroll run.

    Rows flagged above the threshold must be acknowledged before the run can
    be sent to Finance Head for final approval.  The response includes:

    - ``summary``: overall stats (flagged count, threshold, acknowledged count)
    - ``rows``: per-employee detail (prev/curr gross/net/tds, change %, flagged)
    - ``variance_reviewed``: True once Finance has acknowledged all flags
    - ``threshold_pct``: configurable threshold (default 20 %)
    """
    from app.services import payroll_service
    try:
        return payroll_service.get_variance_summary(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class VarianceAcknowledgeBody(BaseModel):
    row_ids: list[int] = []          # Empty list → acknowledge ALL flagged rows
    note: Optional[str] = None       # Optional reviewer note stored on each row


@router.post(
    "/runs/{run_id}/variance/acknowledge",
    summary="[Finance] Acknowledge flagged variance rows to unblock approval",
)
def acknowledge_payroll_variance(
    run_id: int,
    body: VarianceAcknowledgeBody,
    db: Session = Depends(get_db),
    actor: Employee = FinanceUser,
):
    """Mark one or more flagged variance rows as reviewed/acknowledged.

    Once ALL flagged rows are acknowledged, the run's ``variance_reviewed``
    flag is set to True and the run can proceed to Finance Head approval.

    Pass ``row_ids: []`` to acknowledge every flagged row for this run at once.

    Returns updated variance summary.
    """
    from app.services import payroll_service
    try:
        result = payroll_service.acknowledge_variance(
            db=db,
            run_id=run_id,
            actor_id=actor.id,
            row_ids=body.row_ids or None,   # None → all rows
            note=body.note,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
