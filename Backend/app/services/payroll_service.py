"""Payroll business-logic service — Enterprise Grade.

All database mutations go through this layer so routes stay thin.

Key design principles (real company payroll):
  1. Salary versioning  — each revision creates a NEW salary_structures row.
                          Old rows are deactivated (is_active=False), never deleted.
  2. Effective dates    — payroll generation uses the LATEST active salary structure
                          whose effective_from <= pay_period_end.
  3. Audit trail        — every generated row stores salary_structure_id so the exact
                          salary version used is traceable forever.
  4. Run locking        — closed / approved / payslip_generated / published runs are
                          fully protected from recomputation.
  5. No stale salaries  — employee_salary table is NOT used for payroll generation;
                          salary_structures is the single source of truth.
  6. Validation         — mismatched or zero gross blocks generation with a clear error.
  7. TDS                — refreshed from tax declarations before every generate/recompute.
"""
from __future__ import annotations

import json
import logging
import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import or_
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.payroll import (
    PayrollApproval,
    PayrollError,
    PayrollLockHistory,
    PayrollRun,
    PayrollRunEmployee,
    SalaryStructure,
)
from app.models.payroll_extended import (
    EmployeeSalaryAssignment,
    PayrollAdjustment,
    PayrollAuditLog,
    Payslip,
    StatutoryDeduction,
)
from app.models.salary_revision import SalaryRevisionLog
from app.models.bonus_request import BonusRequest as _BonusRequest
# PayrollAttendanceSummary import removed — table is deprecated; payroll_service
# now uses MonthlyAttendanceSummary exclusively.
from app.models.monthly_attendance_summary import MonthlyAttendanceSummary
from app.models.employee import Employee
from app.models.department import Department
from app.services.ctc_engine import compute_from_ctc, apply_lop, SalaryBreakup
from app.services.payroll_bridge import aggregate_leave_days_for_payroll_month
from app.services import statutory_service as _stat_svc

log = logging.getLogger("hrms.payroll")

_CENT = Decimal("0.01")


def _to_decimal(value: float | Decimal | int | None) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: float | Decimal) -> float:
    return float(_to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


def _sum_money(*values: float | Decimal | int | None) -> float:
    return _money(sum((_to_decimal(value) for value in values), Decimal("0")))


def _subtract_money(base: float | Decimal, *values: float | Decimal | int | None) -> float:
    return _money(_to_decimal(base) - sum((_to_decimal(value) for value in values), Decimal("0")))


PAYSLIP_BALANCING_COMPONENT_LABEL = "Special Allowance"

_PAYSLIP_EARNINGS_BEFORE_BALANCE = (
    ("Basic", "basic_pay"),
    ("HRA", "hra"),
)
_PAYSLIP_EARNINGS_AFTER_BALANCE = (
    ("DA", "da"),
    ("LTA", "lta"),
    ("Transport Allowance", "conveyance"),
    ("Bonus", "bonus"),
    ("Variable Pay", "variable_pay"),
    ("Overtime", "overtime_amount"),
)


def _positive_amount(value: float | Decimal | int | None) -> float:
    amount = _money(value or 0.0)
    return amount if amount > 0.0 else 0.0


def _balanced_special_allowance(
    gross_earnings: float | Decimal | int | None,
    *,
    basic_pay: float | Decimal | int | None = 0.0,
    hra: float | Decimal | int | None = 0.0,
    da: float | Decimal | int | None = 0.0,
    lta: float | Decimal | int | None = 0.0,
    conveyance: float | Decimal | int | None = 0.0,
    bonus: float | Decimal | int | None = 0.0,
    variable_pay: float | Decimal | int | None = 0.0,
    overtime_amount: float | Decimal | int | None = 0.0,
) -> float:
    """Return the payslip balancing amount that makes earnings equal gross."""
    return _subtract_money(
        gross_earnings or 0.0,
        basic_pay,
        hra,
        da,
        lta,
        conveyance,
        bonus,
        variable_pay,
        overtime_amount,
    )


def payslip_earning_components(row: PayrollRunEmployee) -> list[dict[str, float | str]]:
    """Positive earning components derived only from a payroll run employee row.

    Special Allowance is the balancing component: it absorbs any residual between
    payroll gross and the other payroll-record earning columns so the rendered
    payslip always reconciles to the computed gross pay.
    """
    gross = _money(getattr(row, "gross_earnings", 0.0) or 0.0)
    components: list[dict[str, float | str]] = []

    def append_positive(label: str, amount: float) -> None:
        if amount > 0.0:
            components.append({"label": label, "amount": amount})

    non_balancing_total = 0.0
    for _, attr in (*_PAYSLIP_EARNINGS_BEFORE_BALANCE, *_PAYSLIP_EARNINGS_AFTER_BALANCE):
        non_balancing_total = _sum_money(
            non_balancing_total,
            _positive_amount(getattr(row, attr, 0.0)),
        )

    for label, attr in _PAYSLIP_EARNINGS_BEFORE_BALANCE:
        append_positive(label, _positive_amount(getattr(row, attr, 0.0)))

    balancing_amount = _subtract_money(gross, non_balancing_total)
    if balancing_amount > 0.0:
        append_positive(PAYSLIP_BALANCING_COMPONENT_LABEL, balancing_amount)
    elif balancing_amount < -0.01:
        log.warning(
            "[PAYSLIP] payroll_record_id=%s has earnings greater than gross: "
            "gross=%.2f, non_balancing_total=%.2f, delta=%.2f",
            getattr(row, "id", None),
            gross,
            non_balancing_total,
            balancing_amount,
        )

    for label, attr in _PAYSLIP_EARNINGS_AFTER_BALANCE:
        append_positive(label, _positive_amount(getattr(row, attr, 0.0)))

    return components


def payslip_earnings_total(row: PayrollRunEmployee) -> float:
    return _sum_money(*(c["amount"] for c in payslip_earning_components(row)))


def payslip_earnings_reconciliation_delta(row: PayrollRunEmployee) -> float:
    return _subtract_money(getattr(row, "gross_earnings", 0.0) or 0.0, payslip_earnings_total(row))


def _attendance_reconciliation_delta(
    *,
    working_days: int,
    present_days: int,
    leave_days: int,
    holiday_days: int,
    lop_days: int,
) -> int:
    return int(working_days or 0) - int(
        (present_days or 0) + (leave_days or 0) + (holiday_days or 0) + (lop_days or 0)
    )


def payslip_attendance_summary(row: PayrollRunEmployee) -> dict[str, int | float | bool]:
    """Attendance summary derived from payroll record values for payslip display."""
    working_days = int(getattr(row, "working_days", 0) or 0)
    present_days = int(getattr(row, "present_days", 0) or 0)
    leave_days = int(getattr(row, "leave_days", 0) or 0)
    holiday_days = int(getattr(row, "holiday_days", 0) or 0)
    lop_days = int(getattr(row, "lop_days", 0) or 0)
    delta = _attendance_reconciliation_delta(
        working_days=working_days,
        present_days=present_days,
        leave_days=leave_days,
        holiday_days=holiday_days,
        lop_days=lop_days,
    )
    if delta > 0:
        holiday_days += delta
        delta = 0
    return {
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": leave_days,
        "holiday_days": holiday_days,
        "lop_days": lop_days,
        "payable_days": float(getattr(row, "payable_days", 0.0) or 0.0),
        "attendance_reconciliation_delta": delta,
        "attendance_reconciled": delta == 0,
    }


PAYROLL_GENERATION_EMPTY_ERROR = "Payroll generation failed: no employee payroll records created."


# ─── Status machine ──────────────────────────────────────────────────────────
#
# Full workflow:
#   draft
#     └─[freeze_attendance]──► attendance_frozen
#                                └─[generate]──► processing
#                                                  ├─[recompute]──► processing  (recompute in-place after adding adjustments)
#                                                  └─[submit_review]──► under_review
#                                                                         ├─[flag_error]──► error_found
#                                                                         │                   └─[recompute]──► processing
#                                                                         ├─[recompute]──► processing
#                                                                         └─[approve]──► pending_head_approval
#                                                                                          ├─[head_approve]──► approved
#                                                                                          └─[head_reject]──► under_review
#   approved
#     └─[generate_payslips]──► payslip_generated
#                                └─[publish]──► completed
#
# Error recovery: error_found ──[resolve_errors]──► under_review
# Cancellation: any non-final state ──[cancel]──► cancelled

_TRANSITIONS: dict[str, dict[str, str]] = {
    "draft": {
        # Finance can only freeze attendance (which records HR input accountability)
        # or cancel.  Direct generation from draft is not allowed — HR must first
        # freeze monthly_attendance_summary so there is an auditable readiness record.
        "freeze_attendance": "attendance_frozen",
        "cancel":            "cancelled",
    },
    "attendance_frozen": {
        "generate":          "processing",
        "process":           "processing",
        "cancel":            "cancelled",
    },
    "processing": {
        # One-click Finance submission: Generated → pending_head_approval directly.
        # Finance reviews the employee rows in-page and clicks Submit to Finance Head.
        "submit_review":       "pending_head_approval",
        "submit_for_approval": "pending_head_approval",
        # Two-step path: Finance can still enter an explicit under_review stage.
        "start_review":       "under_review",
        # Allow recompute directly from processing so Finance can add adjustments
        # and immediately re-run the payroll engine without the extra cycle.
        "recompute":          "processing",
        # Allow 'generate' from processing as an alias for recompute — Finance
        # clicking "Generate Payroll" again on a run with 0 employees must not 400.
        "generate":           "processing",
        "cancel":             "cancelled",
    },
    "under_review": {
        "flag_error":          "error_found",
        "recompute":           "processing",
        "approve":             "pending_head_approval",
        "finance_review":      "pending_head_approval",
        # Allow re-submission from under_review (head_reject recovery path) via
        # the same submit_review action Finance uses from processing.
        "submit_review":       "pending_head_approval",
        "submit_for_approval": "pending_head_approval",
        "reject":              "draft",
        "cancel":              "cancelled",
    },
    "error_found": {
        "recompute":         "processing",
        "resolve_errors":    "under_review",
        "cancel":            "cancelled",
    },
    "pending_head_approval": {
        "head_approve":      "approved",
        "finance_head_approve": "approved",
        "hr_confirm":        "approved",
        "head_reject":       "under_review",
        "cancel":            "cancelled",
    },
    "approved": {
        "finalize":          "approved",
        "generate_payslips": "payslip_generated",
        # "disburse" removed — Finance Head approval no longer bypasses the full
        # publication workflow.  Existing disbursed runs remain valid; new runs
        # must follow: payslip_generated → bank_advice_generated → published → closed.
    },
    "payslip_generated": {
        # Allow direct publish from payslip_generated for standard demo/live flow.
        "publish":              "published",
        # Optional intermediate: generate bank advice CSV before publishing.
        "generate_bank_advice": "bank_advice_generated",
    },
    "bank_advice_generated": {
        "publish":           "published",
    },
    "published": {
        "close":             "closed",
    },
    "completed":  {},   # legacy terminal — kept for runs closed before this workflow
    "disbursed":  {},   # legacy terminal — kept for pre-Sprint 3 runs
    "closed":     {},
    "cancelled":  {},
}

# Statuses from which recomputation is NEVER allowed (immutable payroll history)
_LOCKED_STATUSES = frozenset({
    "payslip_generated", "bank_advice_generated", "published", "completed", "closed", "cancelled",
})
_FINAL_APPROVED_STATUSES = frozenset({
    "approved", "payslip_generated", "bank_advice_generated",
    "published", "completed", "closed", "disbursed",
})
_PUBLISH_READY_STATUSES = frozenset({
    # payslip_generated removed — bank advice must be generated before payslips
    # can be published to employees.
    "bank_advice_generated", "published", "completed", "closed", "disbursed",
})

_STATUS_TO_DOCUMENT_LIFECYCLE = {
    "draft": "DRAFT",
    "attendance_frozen": "DRAFT",
    "processing": "PROCESSING",
    "under_review": "PENDING_APPROVAL",
    "error_found": "PENDING_APPROVAL",
    "pending_head_approval": "PENDING_APPROVAL",
    "approved": "APPROVED",
    "payslip_generated": "FINALIZED",
    "bank_advice_generated": "FINALIZED",
    "disbursed": "FINALIZED",
    "published": "PUBLISHED",
    "closed": "PUBLISHED",
    "cancelled": "CANCELLED",
}

_APPROVAL_ACTION_LEVEL = {
    "submit_review": "FINANCE_REVIEW",
    "submit_for_approval": "FINANCE_REVIEW",
    "approve": "FINANCE_REVIEW",
    "finance_review": "FINANCE_REVIEW",
    "head_approve": "FINANCE_HEAD_APPROVAL",
    "finance_head_approve": "FINANCE_HEAD_APPROVAL",
    "hr_confirm": "HR_CONFIRMATION",
}


def _next_status(current: str, action: str) -> Optional[str]:
    return _TRANSITIONS.get(current, {}).get(action)


def is_final_approved_run(run: PayrollRun | None) -> bool:
    """True once Finance Head final approval locked the payroll run."""
    return bool(
        run
        and run.status in _FINAL_APPROVED_STATUSES
        and bool(run.payroll_locked)
    )


def _is_immutable_run(run: PayrollRun | None) -> bool:
    return bool(run and (run.payroll_locked or run.status in _LOCKED_STATUSES))


def _ensure_editable_run(run: PayrollRun | None) -> None:
    if _is_immutable_run(run):
        raise ValueError("Final approved payroll cannot be edited.")


def ensure_payroll_records_exist(db: Session, run_id: int) -> int:
    count = db.query(PayrollRunEmployee).filter_by(run_id=run_id).count()
    if count <= 0:
        raise ValueError(PAYROLL_GENERATION_EMPTY_ERROR)
    return count


def is_false_salary_assignment_variance(row: PayrollRunEmployee) -> bool:
    """True for legacy assignment-only variance that current payroll ignores."""
    reason = (getattr(row, "variance_reason", None) or "").lower()
    salary_structure = getattr(row, "salary_structure", None)
    annual_ctc = float(getattr(salary_structure, "annual_ctc", 0.0) or 0.0)
    return bool(
        getattr(row, "variance_flag", False)
        and not getattr(row, "has_error", False)
        and annual_ctc > 0.0
        and "salary assignment" in reason
    )


def visible_variance_count(db: Session, run_id: int) -> int:
    rows = db.query(PayrollRunEmployee).filter_by(
        run_id=run_id,
        variance_flag=True,
    ).all()
    return sum(1 for row in rows if not is_false_salary_assignment_variance(row))


def _add_generation_error(
    db: Session,
    run: PayrollRun,
    emp: Employee,
    error_type: str,
    description: str,
    *,
    severity: str = "error",
    salary_structure_id: int | None = None,
    salary_assignment_id: int | None = None,
    working_days: int = 0,
    payable_days: float = 0.0,
    present_days: int = 0,
    leave_days: int = 0,
    lop_days: int = 0,
    holiday_days: int = 0,
) -> PayrollRunEmployee:
    """Create a visible run row for a generation error."""
    db.add(PayrollError(
        run_id=run.id,
        employee_id=emp.id,
        error_type=error_type,
        description=description,
        severity=severity,
    ))

    row = db.query(PayrollRunEmployee).filter_by(
        run_id=run.id,
        employee_id=emp.id,
    ).first()
    if row is None:
        row = PayrollRunEmployee(
            run_id=run.id,
            employee_id=emp.id,
            salary_structure_id=salary_structure_id,
            salary_assignment_id=salary_assignment_id,
            total_working_days=int(working_days or 0),
            working_days=int(working_days or 0),
            payable_days=float(payable_days or 0.0),
            present_days=int(present_days or 0),
            leave_days=int(leave_days or 0),
            lop_days=int(lop_days or 0),
            holiday_days=int(holiday_days or 0),
            gross_earnings=0.0,
            basic_pay=0.0,
            hra=0.0,
            da=0.0,
            special_allowance=0.0,
            lta=0.0,
            conveyance=0.0,
            bonus=0.0,
            variable_pay=0.0,
            overtime_amount=0.0,
            employee_pf=0.0,
            employer_pf=0.0,
            employee_esi=0.0,
            employer_esi=0.0,
            professional_tax=0.0,
            tds=0.0,
            lop_deduction=0.0,
            other_deductions=0.0,
            total_deductions=0.0,
            net_pay=0.0,
            has_error=True,
            record_status="ERROR",
            variance_flag=False,
            variance_reason=description,
            migration_completed=True,
        )
        row.sync_legacy_amount_columns()
        db.add(row)
    else:
        row.has_error = True
        row.record_status = "ERROR"
        row.variance_reason = description
        row.variance_flag = False
        if salary_structure_id is not None:
            row.salary_structure_id = salary_structure_id
        if salary_assignment_id is not None:
            row.salary_assignment_id = salary_assignment_id
    return row


def _get_employees_by_role(db: Session, *role_names: str) -> list:
    """Return active employees matching any of the given role names."""
    from app.models.role import Role as _Role
    roles = db.query(_Role).filter(_Role.name.in_(role_names)).all()
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


def _dispatch_payroll_notifications(
    db: Session,
    run: "PayrollRun",
    action: str,
    actor: Employee,
    remarks: Optional[str] = None,
) -> None:
    """Fire in-app notifications and HTML emails for payroll workflow events. Never raises.

    In-app notifications go through notification_service.notify (send_email=False here
    because payroll_notifications handles the HTML email side to avoid duplicates and
    to use properly formatted subjects/templates for each trigger).
    """
    try:
        from app.services import notification_service as _ns
        from app.services import payroll_notifications as _pn

        run_label = run.month_label or f"Run #{run.id}"
        actor_name = f"{actor.first_name} {actor.last_name or ''}".strip()
        run_ref_id = str(run.id)

        def _notify_group(role_names, ntype, title, body):
            """Write in-app notifications only; email is handled by payroll_notifications."""
            users = _get_employees_by_role(db, *role_names)
            notified_ids: set[int] = set()
            for u in users:
                if u.id in notified_ids:
                    continue
                notified_ids.add(u.id)
                _ns.notify(
                    db,
                    recipient_id=u.id,
                    type_=ntype,
                    title=title,
                    body=body,
                    reference_table="payroll_runs",
                    reference_id=run_ref_id,
                    send_email=False,
                    autocommit=True,
                )
            return users

        if action in ("create", "initiate"):
            title = f"Payroll run created — {run_label}"
            body = f"Payroll {run_label} has been created by {actor_name} and is ready for Finance."
            _notify_group(("finance",), "payroll_run_created", title, body)

        elif action == "freeze_attendance":
            # Trigger 1: Attendance frozen — notify Finance via in-app + email
            title = f"Payroll input frozen — {run_label}"
            body = f"Attendance/input freeze completed for payroll {run_label} by {actor_name}."
            _notify_group(("finance",), "payroll_freeze_done", title, body)
            _pn.notify_attendance_frozen(db, run, actor_name)

        elif action in ("generate", "process"):
            title = f"Payroll generated — {run_label}"
            body = f"Payroll computation for {run_label} initiated by {actor_name}."
            _notify_group(("admin",), "payroll_initiated", title, body)

        elif action in ("submit_review", "submit_for_approval"):
            # submit_review now goes directly to pending_head_approval — notify Finance Head
            title = f"Payroll awaiting your approval — {run_label}"
            body = f"Payroll {run_label} has been reviewed by Finance ({actor_name}) and is awaiting your final approval."
            _notify_group(("finance_head",), "payroll_awaiting_head_approval", title, body)
            _pn.notify_finance_approved(db, run, actor_name)

        elif action == "reject":
            # Trigger 3: Finance rejected — notify HR/Admin with reason
            title = f"Finance rejected payroll — {run_label}"
            body = f"Finance rejected payroll {run_label}. Remarks: {remarks or '—'}."
            _notify_group(("admin", "hr"), "payroll_rejected", title, body)
            _pn.notify_payroll_rejected(db, run, actor_name, remarks)

        elif action == "head_reject":
            title = f"Finance Head returned payroll — {run_label}"
            body = (
                f"Finance Head returned payroll {run_label} to Finance for review. "
                f"Remarks: {remarks or '—'}."
            )
            _notify_group(("finance", "admin"), "payroll_returned_to_finance", title, body)

        elif action in ("finance_review", "approve"):
            # Trigger 4: Finance approved → notify Finance Head for final approval
            title = f"Payroll approved by Finance — {run_label}"
            body = f"Payroll {run_label} was approved by Finance and is waiting for Finance Head approval."
            _notify_group(("finance_head",), "payroll_awaiting_head_approval", title, body)
            _pn.notify_finance_approved(db, run, actor_name)

        elif action in ("head_approve", "finance_head_approve"):
            # Trigger 5: Finance Head final approval — notify HR/Admin and Finance
            title = f"Payroll approved by Finance Head — {run_label}"
            body = f"Payroll {run_label} approved by Finance Head. Ready for payslip generation."
            _notify_group(("admin", "finance", "hr"), "payroll_finalized", title, body)
            _pn.notify_head_approved(db, run, actor_name)

        elif action == "recompute":
            title = f"Payroll recomputed — {run_label}"
            body = f"Payroll {run_label} has been recomputed and is ready for review."
            _notify_group(("finance", "finance_head"), "payroll_recomputed", title, body)

        elif action == "publish":
            # Trigger 6: Payslips published — notify in-app via existing helper,
            # then send individual HTML emails to each employee.
            published_slips = (
                db.query(Payslip)
                .filter_by(run_id=run.id, is_published=True)
                .all()
            )
            _dispatch_payslip_published_notifications(db, run, published_slips)
            _pn.notify_payslips_published(db, run)

    except Exception as _err:
        log.warning("Payroll notification dispatch failed (non-fatal): %s", _err)


def _dispatch_payslip_published_notifications(
    db: Session,
    run: "PayrollRun",
    slips: list[Payslip],
    *,
    send_email: bool = True,
) -> None:
    """Notify employees whose payslips were published. Never raises."""
    if not run or not slips:
        return
    try:
        from app.services import notification_service as _ns

        run_label = run.month_label or f"Run #{run.id}"
        seen_employee_ids: set[int] = set()
        for slip in slips:
            employee_id = getattr(slip, "employee_id", None)
            if not employee_id or employee_id in seen_employee_ids:
                continue
            seen_employee_ids.add(employee_id)
            _ns.notify(
                db,
                recipient_id=employee_id,
                type_="payslip_published",
                title="Payslip Published",
                body=f"Your {run_label} payslip is now available for viewing and download.",
                reference_table="payroll_runs",
                reference_id=str(run.id),
                send_email=send_email,
                autocommit=True,
            )
    except Exception as _err:
        log.warning("Employee payslip notification failed (non-fatal): %s", _err)


def document_lifecycle_status(status: str, payroll_locked: bool = False) -> str:
    """Map existing UI statuses to the Payroll DB document lifecycle."""
    if status == "approved" and payroll_locked:
        return "FINAL_APPROVED"
    return _STATUS_TO_DOCUMENT_LIFECYCLE.get(status, status.upper())


def derive_payroll_period_fields(pay_period_start: date) -> dict[str, int | str]:
    """Derive payroll month fields from the period start date."""
    month = pay_period_start.month
    year = pay_period_start.year
    return {
        "month_label": f"{calendar.month_name[month]} {year}",
        "month": month,
        "year": year,
    }


def payroll_month_label(pay_period_start: date) -> str:
    return str(derive_payroll_period_fields(pay_period_start)["month_label"])


def payroll_month_label_from_parts(month: int, year: int) -> str:
    return payroll_month_label(date(year, month, 1))


def normalize_payroll_run_period(run: PayrollRun | None) -> PayrollRun | None:
    if not run or not run.pay_period_start:
        return run
    fields = derive_payroll_period_fields(run.pay_period_start)
    run.month_label = str(fields["month_label"])
    run.month = int(fields["month"])
    run.year = int(fields["year"])
    return run


def normalize_payslip_period(slip: Payslip | None) -> Payslip | None:
    if not slip or not slip.pay_period_start:
        return slip
    fields = derive_payroll_period_fields(slip.pay_period_start)
    slip.month_label = str(fields["month_label"])
    slip.month = int(fields["month"])
    slip.year = int(fields["year"])
    return slip


def _period_month_year(run: PayrollRun) -> tuple[int, int, str]:
    fields = derive_payroll_period_fields(run.pay_period_start)
    month = int(fields["month"])
    return month, int(fields["year"]), calendar.month_name[month]


def _ensure_run_document_fields(run: PayrollRun) -> None:
    month, year, _ = _period_month_year(run)
    normalize_payroll_run_period(run)
    run.month = month
    run.year = year
    if not run.payroll_run_code and run.id:
        run.payroll_run_code = f"PR-{year}{month:02d}-{run.id:04d}"


def _sync_salary_assignment(db: Session, struct: SalaryStructure, actor: Employee | None) -> EmployeeSalaryAssignment:
    """Keep the additive salary assignment table in step with salary_structures."""
    effective_from = struct.effective_from or date.today()
    existing = (
        db.query(EmployeeSalaryAssignment)
        .filter(
            EmployeeSalaryAssignment.employee_id == struct.employee_id,
            EmployeeSalaryAssignment.salary_structure_id == struct.id,
        )
        .first()
    )

    for assignment in (
        db.query(EmployeeSalaryAssignment)
        .filter(
            EmployeeSalaryAssignment.employee_id == struct.employee_id,
            EmployeeSalaryAssignment.status == "ACTIVE",
            EmployeeSalaryAssignment.salary_structure_id != struct.id,
        )
        .all()
    ):
        assignment.status = "SUPERSEDED"
        assignment.effective_to = effective_from - timedelta(days=1)

    if existing:
        assignment = existing
    else:
        assignment = EmployeeSalaryAssignment(
            employee_id=struct.employee_id,
            salary_structure_id=struct.id,
            effective_from=effective_from,
        )
        db.add(assignment)

    assignment.effective_from = effective_from
    assignment.effective_to = None
    assignment.ctc_annual = struct.annual_ctc or 0.0
    assignment.monthly_ctc = round((struct.annual_ctc or 0.0) / 12, 2)
    assignment.status = "ACTIVE"
    assignment.assigned_by_id = actor.id if actor else None
    db.flush()
    return assignment


def _get_active_salary_assignment_for_period(
    db: Session, employee_id: int, pay_period_end: date
) -> EmployeeSalaryAssignment | None:
    return (
        db.query(EmployeeSalaryAssignment)
        .filter(
            EmployeeSalaryAssignment.employee_id == employee_id,
            EmployeeSalaryAssignment.status == "ACTIVE",
            EmployeeSalaryAssignment.effective_from <= pay_period_end,
            or_(
                EmployeeSalaryAssignment.effective_to.is_(None),
                EmployeeSalaryAssignment.effective_to >= pay_period_end,
            ),
        )
        .order_by(EmployeeSalaryAssignment.effective_from.desc(), EmployeeSalaryAssignment.created_at.desc())
        .first()
    )


def _get_salary_assignment_for_period(
    db: Session, employee_id: int, pay_period_end: date
) -> EmployeeSalaryAssignment | None:
    """Return the salary assignment valid for a pay period — includes SUPERSEDED.

    Unlike _get_active_salary_assignment_for_period, this does NOT filter by
    status so that historical payroll runs (e.g. March run after an April-1 hike)
    find the SUPERSEDED assignment that was still correct for that earlier period.
    Uses effective_from / effective_to dates as the sole selection criterion.
    """
    return (
        db.query(EmployeeSalaryAssignment)
        .filter(
            EmployeeSalaryAssignment.employee_id == employee_id,
            EmployeeSalaryAssignment.effective_from <= pay_period_end,
            or_(
                EmployeeSalaryAssignment.effective_to.is_(None),
                EmployeeSalaryAssignment.effective_to >= pay_period_end,
            ),
        )
        .order_by(EmployeeSalaryAssignment.effective_from.desc(), EmployeeSalaryAssignment.created_at.desc())
        .first()
    )


def _leave_lop_days(db: Session, employee_id: int, month: int, year: int) -> int:
    return aggregate_leave_days_for_payroll_month(db, employee_id, month, year)["lop_days"]


def _leave_paid_days(db: Session, employee_id: int, month: int, year: int) -> int:
    return aggregate_leave_days_for_payroll_month(db, employee_id, month, year)["paid_leave_days"]


def get_payroll_attendance_summary(
    db: Session, employee_id: int, month: int | str, year: int
) -> dict:
    """Return finalized payroll attendance from monthly_attendance_summary only.

    DEPRECATED fallbacks removed in Sprint 3:
      - payroll_attendance_summary (legacy table) fallback removed.
      - Demo-safe 26-day hardcoded fallback removed.
    Only frozen MonthlyAttendanceSummary rows are accepted as valid payroll input.
    """
    if isinstance(month, int):
        month_int = month
    else:
        try:
            month_int = list(calendar.month_name).index(str(month).capitalize())
        except ValueError:
            month_int = list(calendar.month_abbr).index(str(month)[:3].capitalize())

    leave_totals = aggregate_leave_days_for_payroll_month(db, employee_id, month_int, year)
    leave_paid_days = leave_totals["paid_leave_days"]

    mas = (
        db.query(MonthlyAttendanceSummary)
        .filter(
            MonthlyAttendanceSummary.employee_id          == employee_id,
            MonthlyAttendanceSummary.month                == month_int,
            MonthlyAttendanceSummary.year                 == year,
            MonthlyAttendanceSummary.is_frozen            == True,
            MonthlyAttendanceSummary.is_ready_for_payroll == True,
        )
        .first()
    )
    if mas:
        total_working_days = mas.total_working_days or 0
        lop_days           = int(mas.lop_days or 0)
        payable_days       = (
            float(mas.payable_days)
            if mas.payable_days is not None
            else float(max(total_working_days - lop_days, 0))
        )
        return {
            "total_working_days": total_working_days,
            "payable_days":       payable_days,
            "present_days":       mas.present_days or int(payable_days),
            "leave_days":         leave_paid_days,
            "lop_days":           lop_days,
            "holiday_days":       0,
            "overtime_hours":     float(mas.approved_timesheet_hours or 0.0),
            "is_finalized":       True,
            "fallback_used":      False,
            "fallback_reason":    None,
        }

    # No frozen MAS found — return not-finalized so callers can surface the error.
    return {
        "total_working_days": 0,
        "payable_days":       0.0,
        "present_days":       0,
        "leave_days":         leave_paid_days,
        "lop_days":           0,
        "holiday_days":       0,
        "overtime_hours":     0.0,
        "is_finalized":       False,
        "fallback_used":      False,
        "fallback_reason":    (
            f"No frozen MonthlyAttendanceSummary found for employee {employee_id} "
            f"({month_int}/{year}). HR must validate and freeze attendance before payroll."
        ),
    }


def _record_lock_history(
    db: Session,
    run: PayrollRun,
    lock_type: str,
    action: str,
    actor: Employee | None,
    reason: str | None = None,
) -> None:
    db.add(PayrollLockHistory(
        payroll_run_id=run.id,
        lock_type=lock_type,
        action=action,
        action_by=actor.id if actor else None,
        reason=reason,
    ))


def _mark_approval_step(
    db: Session,
    run: PayrollRun,
    actor: Employee,
    approval_level: str,
    approval_status: str,
    comments: str | None,
) -> None:
    existing = (
        db.query(PayrollApproval)
        .filter_by(run_id=run.id, approval_level=approval_level)
        .order_by(PayrollApproval.created_at.desc())
        .first()
    )
    now = datetime.utcnow()
    if existing and existing.approval_status == "PENDING":
        existing.approver_id = actor.id
        existing.actor_id = actor.id
        existing.action = approval_level.lower()
        existing.approval_status = approval_status
        existing.comments = comments
        existing.remarks = comments
        existing.approved_at = now if approval_status == "APPROVED" else None
    else:
        db.add(PayrollApproval(
            run_id=run.id,
            actor_id=actor.id,
            approver_id=actor.id,
            action=approval_level.lower(),
            approval_level=approval_level,
            approval_status=approval_status,
            comments=comments,
            remarks=comments,
            approved_at=now if approval_status == "APPROVED" else None,
        ))


def _ensure_pending_approval_steps(db: Session, run: PayrollRun, actor: Employee) -> None:
    for level in ("FINANCE_REVIEW", "FINANCE_HEAD_APPROVAL", "HR_CONFIRMATION"):
        exists = (
            db.query(PayrollApproval)
            .filter_by(run_id=run.id, approval_level=level)
            .first()
        )
        if not exists:
            db.add(PayrollApproval(
                run_id=run.id,
                actor_id=actor.id,
                action="approval_pending",
                approval_level=level,
                approval_status="PENDING",
            ))


def _finance_review_completed(db: Session, run_id: int) -> bool:
    return db.query(PayrollApproval).filter(
        PayrollApproval.run_id == run_id,
        PayrollApproval.approval_level == "FINANCE_REVIEW",
        PayrollApproval.approval_status == "APPROVED",
    ).first() is not None


def _detect_variance(
    db: Session,
    employee_id: int,
    run: PayrollRun,
    gross_earnings: float,
    total_deductions: float,
    net_pay: float,
    payable_days: float,
    lop_days: int,
    salary_structure: SalaryStructure | None,
    attendance_fallback_reason: str | None,
) -> tuple[bool, str | None]:
    reasons: list[str] = []

    if salary_structure is None:
        reasons.append("Salary structure missing")
    else:
        if float(salary_structure.annual_ctc or 0.0) <= 0.0:
            reasons.append("Annual CTC missing in salary structure")

    if attendance_fallback_reason:
        reasons.append(attendance_fallback_reason)

    return bool(reasons), "; ".join(reasons) if reasons else None


def _save_statutory_deductions(db: Session, row: PayrollRunEmployee) -> None:
    db.query(StatutoryDeduction).filter_by(payroll_record_id=row.id).delete(synchronize_session=False)
    entries = [
        ("PF", row.employee_pf, row.employer_pf, row.basic_pay, "PF from configured salary structure/statutory settings"),
        ("ESI", row.employee_esi, row.employer_esi, row.gross_earnings, "ESI from configured salary structure/statutory settings"),
        ("PT", row.professional_tax, 0.0, row.gross_earnings, "Professional tax from configured salary structure"),
        ("TDS", row.tds, 0.0, row.gross_earnings, "TDS from employee declarations/statutory service"),
    ]
    for code, employee_amount, employer_amount, wage_base, formula in entries:
        db.add(StatutoryDeduction(
            payroll_record_id=row.id,
            employee_id=row.employee_id,
            deduction_code=code,
            employee_amount=employee_amount or 0.0,
            employer_amount=employer_amount or 0.0,
            wage_base=wage_base or 0.0,
            calculation_formula=formula,
        ))


# ─── Payroll Variance Computation ────────────────────────────────────────────

def _compute_and_store_variance(db: Session, run: PayrollRun) -> None:
    """Store payroll variance context for review.

    Row-level warning flags are limited to current payroll source-of-truth
    issues. Salary assignments are audit-only for this flow; successful rows
    generated from salary_structures.annual_ctc are not variance rows.

    Called automatically after every generate/recompute.  Finance must
    acknowledge flagged rows before sending to Finance Head.
    """
    try:
        from app.models.payroll_extended import PayrollVarianceLog
    except ImportError:
        log.warning("PayrollVarianceLog model not available — skipping variance compute")
        return

    run_month = run.pay_period_start.month
    run_year  = run.pay_period_start.year

    # Find the immediately preceding closed/published/approved run
    prev_run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.pay_period_start < run.pay_period_start,
            PayrollRun.status.in_(["closed", "published", "approved", "payslip_generated"]),
        )
        .order_by(PayrollRun.pay_period_start.desc())
        .first()
    )

    # Clear existing variance log rows for this run (idempotent on recompute)
    try:
        db.query(PayrollVarianceLog).filter_by(run_id=run.id).delete(synchronize_session=False)
        db.flush()
    except Exception:
        pass

    current_rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    any_flagged = False

    for row in current_rows:
        curr_gross = float(row.gross_earnings or 0)
        curr_net   = float(row.net_pay or 0)
        curr_tds   = float(row.tds or 0)
        curr_lop   = float(row.lop_days     or 0)

        prev_gross = prev_net = prev_tds = prev_lop = 0.0
        prev_run_id = None

        if prev_run:
            prev_row = db.query(PayrollRunEmployee).filter_by(
                run_id=prev_run.id, employee_id=row.employee_id
            ).first()
            if prev_row:
                prev_gross  = float(prev_row.gross_earnings or 0)
                prev_net    = float(prev_row.net_pay or 0)
                prev_tds    = float(prev_row.tds or 0)
                prev_lop    = float(prev_row.lop_days     or 0)
                prev_run_id = prev_run.id

        def _pct_change(prev: float, curr: float) -> float:
            if not prev:
                return 0.0
            return round(abs(curr - prev) / abs(prev) * 100, 2)

        gross_var_pct = _pct_change(prev_gross, curr_gross)
        net_var_pct   = _pct_change(prev_net,   curr_net)

        flags: list[str] = []
        if (
            row.variance_flag
            and row.variance_reason
            and not is_false_salary_assignment_variance(row)
        ):
            flags.append(row.variance_reason)

        is_flagged = bool(flags)
        if is_flagged:
            any_flagged = True

        vlog = PayrollVarianceLog(
            run_id=run.id,
            employee_id=row.employee_id,
            prev_run_id=prev_run_id,
            prev_gross_pay=prev_gross,
            curr_gross_pay=curr_gross,
            gross_variance_pct=gross_var_pct,
            prev_net_pay=prev_net,
            curr_net_pay=curr_net,
            net_variance_pct=net_var_pct,
            prev_tds=prev_tds,
            curr_tds=curr_tds,
            prev_lop_days=prev_lop,
            curr_lop_days=curr_lop,
            variance_flags="; ".join(flags) if flags else None,
            is_flagged=is_flagged,
        )
        db.add(vlog)

    # No acknowledgement is needed when generation produced no approved variance warnings.
    try:
        run.variance_reviewed = not any_flagged
    except Exception:
        pass

    db.flush()
    log.info(
        "Variance log computed for run_id=%d: %d rows, flagged=%s",
        run.id, len(current_rows), any_flagged,
    )


def get_variance_summary(db: Session, run_id: int) -> dict:
    """Return variance summary for a payroll run.

    Used by Finance (for acknowledgement) and Finance Head (for final review).
    """
    try:
        from app.models.payroll_extended import PayrollVarianceLog
        rows = db.query(PayrollVarianceLog).filter_by(run_id=run_id).all()
        flagged = [
            r for r in rows
            if r.is_flagged and "salary assignment" not in (r.variance_flags or "").lower()
        ]
        acknowledged = [r for r in flagged if r.acknowledged_by_id is not None]

        run = db.query(PayrollRun).filter_by(id=run_id).first()
        variance_reviewed = bool(getattr(run, "variance_reviewed", False)) if run else False

        return {
            "run_id": run_id,
            "total_employees": len(rows),
            "flagged_count": len(flagged),
            "acknowledged_count": len(acknowledged),
            "pending_acknowledgement": len(flagged) - len(acknowledged),
            "variance_reviewed": variance_reviewed,
            "flagged_employees": [
                {
                    "employee_id": r.employee_id,
                    "flags": r.variance_flags,
                    "gross_variance_pct": r.gross_variance_pct,
                    "net_variance_pct": r.net_variance_pct,
                    "curr_gross": r.curr_gross_pay,
                    "prev_gross": r.prev_gross_pay,
                    "curr_net": r.curr_net_pay,
                    "prev_net": r.prev_net_pay,
                    "acknowledged": r.acknowledged_by_id is not None,
                    "acknowledged_note": r.acknowledgement_note,
                }
                for r in flagged
            ],
        }
    except Exception as exc:
        log.warning("get_variance_summary failed for run_id=%d: %s", run_id, exc)
        return {"run_id": run_id, "error": str(exc)}


def acknowledge_variance(
    db: Session,
    run_id: int,
    actor: Employee,
    note: Optional[str] = None,
    employee_ids: Optional[list[int]] = None,
) -> dict:
    """Finance acknowledges flagged variance entries.

    ``employee_ids=None`` acknowledges ALL flagged entries for the run.
    After all are acknowledged, sets run.variance_reviewed=True.
    """
    try:
        from app.models.payroll_extended import PayrollVarianceLog
        q = db.query(PayrollVarianceLog).filter(
            PayrollVarianceLog.run_id == run_id,
            PayrollVarianceLog.is_flagged.is_(True),
            PayrollVarianceLog.acknowledged_by_id.is_(None),
        )
        if employee_ids:
            q = q.filter(PayrollVarianceLog.employee_id.in_(employee_ids))

        rows = q.all()
        now = datetime.utcnow()
        for r in rows:
            r.acknowledged_by_id = actor.id
            r.acknowledged_at = now
            r.acknowledgement_note = note

        # Check if all flagged rows are now acknowledged
        still_pending = (
            db.query(PayrollVarianceLog)
            .filter(
                PayrollVarianceLog.run_id == run_id,
                PayrollVarianceLog.is_flagged.is_(True),
                PayrollVarianceLog.acknowledged_by_id.is_(None),
            )
            .count()
        )
        run = db.query(PayrollRun).filter_by(id=run_id).first()
        if run and still_pending == 0:
            try:
                run.variance_reviewed = True
                run.variance_reviewed_by_id = actor.id
                run.variance_reviewed_at = now
            except Exception:
                pass

        db.commit()
        return {
            "acknowledged_count": len(rows),
            "still_pending": still_pending,
            "variance_reviewed": still_pending == 0,
        }
    except Exception as exc:
        db.rollback()
        raise ValueError(f"Variance acknowledgement failed: {exc}")


# ─── Salary Structure — Versioned Upsert ─────────────────────────────────────

def upsert_salary_structure(db: Session, data: dict, actor: Employee) -> SalaryStructure:
    """
    Enterprise versioned salary structure save.

    Rules:
    - If an ACTIVE structure with the SAME effective_from already exists for this
      employee → UPDATE it in-place (same-day correction allowed).
    - Otherwise → DEACTIVATE all current active structures for this employee and
      CREATE a new revision row.

    This design preserves full salary history. payroll_run_employees rows continue
    to reference their original salary_structure_id even after salary revisions.
    Existing closed payrolls are never affected.
    """
    employee_id = data["employee_id"]
    effective_from: date = data.get("effective_from") or date.today()
    revision_reason: str | None = data.get("revision_reason")

    # Ensure effective_from is a date object (API may pass a string)
    if isinstance(effective_from, str):
        effective_from = date.fromisoformat(effective_from)

    # ── Check for same-date active structure (same-day correction) ──
    existing_same_date = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.is_active.is_(True),
            SalaryStructure.effective_from == effective_from,
        )
        .first()
    )

    _prev_structure_snapshot: SalaryStructure | None = None
    _is_new_revision: bool = False

    if existing_same_date:
        # Same-day correction: update the row that was just created today
        struct = existing_same_date
        log.info(
            "Salary structure same-day correction: id=%d, employee_id=%d, effective_from=%s",
            struct.id, employee_id, effective_from,
        )
    else:
        # New revision: deactivate all currently active structures for this employee
        prev_active = (
            db.query(SalaryStructure)
            .filter(
                SalaryStructure.employee_id == employee_id,
                SalaryStructure.is_active.is_(True),
            )
            .order_by(SalaryStructure.effective_from.desc())
            .all()
        )
        # Capture the most-recent active structure before deactivating (for revision diff)
        if prev_active:
            _prev_structure_snapshot = prev_active[0]

        for old in prev_active:
            old.is_active = False
            log.info(
                "Salary structure superseded: id=%d, employee_id=%d, "
                "was effective_from=%s — new revision effective %s will replace it.",
                old.id, employee_id, old.effective_from, effective_from,
            )
        db.flush()

        # Create the new revision row
        struct = SalaryStructure(employee_id=employee_id)
        db.add(struct)
        _is_new_revision = True
        log.info(
            "New salary structure revision: employee_id=%d, effective_from=%s",
            employee_id, effective_from,
        )

    # ── Set component fields ──
    for field in (
        "basic", "hra", "da", "special_allowance", "transport_allowance",
        "medical_allowance", "other_allowances",
        "pf_employee", "pf_employer", "esi_employee", "esi_employer",
        "professional_tax", "tds",
        "bank_name", "account_number", "ifsc_code",
        "is_active",
    ):
        if field in data:
            setattr(struct, field, data[field])

    # Always stamp effective_from — default to today if not passed
    struct.effective_from = effective_from

    # ── Recompute derived totals ──
    component_gross = (
        (struct.basic or 0.0)
        + (struct.hra or 0.0)
        + (struct.da or 0.0)
        + (struct.special_allowance or 0.0)
        + (struct.transport_allowance or 0.0)
        + (struct.medical_allowance or 0.0)
        + (struct.other_allowances or 0.0)
    )
    if "annual_ctc" in data and data["annual_ctc"] is not None:
        gross = _money(_to_decimal(data["annual_ctc"]) / Decimal("12"))
    else:
        gross = component_gross
    deductions = _sum_money(
        struct.pf_employee,
        struct.pf_employer,
        struct.esi_employee,
        struct.professional_tax,
        struct.tds,
    )
    struct.gross_monthly    = round(gross, 2)
    struct.total_deductions = deductions
    struct.net_monthly      = _subtract_money(gross, deductions)
    # Preserve exact user-entered annual CTC when the CTC engine provides it
    # (avoids ₹0.08 paisa residue from accumulated per-component rounding).
    # Fall back to computing from gross only when no explicit value is given.
    if "annual_ctc" in data and data["annual_ctc"] is not None:
        struct.annual_ctc = float(data["annual_ctc"])
    else:
        struct.annual_ctc = round(
            (gross + (struct.pf_employer or 0.0) + (struct.esi_employer or 0.0)) * 12, 2
        )

    db.commit()
    db.refresh(struct)

    try:
        _sync_salary_assignment(db, struct, actor)
        db.commit()
        db.refresh(struct)
    except Exception as assignment_err:
        db.rollback()
        log.warning(
            "Salary assignment sync skipped for salary_structure_id=%s: %s",
            struct.id, assignment_err,
        )

    log.info(
        "Salary structure saved: id=%d, employee_id=%d, effective_from=%s, "
        "gross_monthly=%.2f, annual_ctc=%.2f, is_active=%s",
        struct.id, employee_id, struct.effective_from,
        struct.gross_monthly, struct.annual_ctc, struct.is_active,
    )

    # ── Write revision audit log (only for true new revisions, not same-day corrections) ──
    if _is_new_revision:
        old = _prev_structure_snapshot
        old_ctc = (old.annual_ctc or 0.0) if old else 0.0
        new_ctc = struct.annual_ctc or 0.0
        diff = round(new_ctc - old_ctc, 2)
        pct = round((diff / old_ctc * 100), 2) if old_ctc else 0.0

        revision_log = SalaryRevisionLog(
            employee_id=employee_id,
            old_salary_structure_id=old.id if old else None,
            new_salary_structure_id=struct.id,
            old_annual_ctc=old_ctc,
            new_annual_ctc=new_ctc,
            ctc_difference=diff,
            ctc_change_pct=pct,
            old_basic=(old.basic or 0.0) if old else 0.0,
            new_basic=struct.basic or 0.0,
            old_hra=(old.hra or 0.0) if old else 0.0,
            new_hra=struct.hra or 0.0,
            old_da=(old.da or 0.0) if old else 0.0,
            new_da=struct.da or 0.0,
            old_special_allowance=(old.special_allowance or 0.0) if old else 0.0,
            new_special_allowance=struct.special_allowance or 0.0,
            old_transport_allowance=(old.transport_allowance or 0.0) if old else 0.0,
            new_transport_allowance=struct.transport_allowance or 0.0,
            old_medical_allowance=(old.medical_allowance or 0.0) if old else 0.0,
            new_medical_allowance=struct.medical_allowance or 0.0,
            old_gross_monthly=(old.gross_monthly or 0.0) if old else 0.0,
            new_gross_monthly=struct.gross_monthly or 0.0,
            old_net_monthly=(old.net_monthly or 0.0) if old else 0.0,
            new_net_monthly=struct.net_monthly or 0.0,
            old_pf_employee=(old.pf_employee or 0.0) if old else 0.0,
            new_pf_employee=struct.pf_employee or 0.0,
            old_esi_employee=(old.esi_employee or 0.0) if old else 0.0,
            new_esi_employee=struct.esi_employee or 0.0,
            old_professional_tax=(old.professional_tax or 0.0) if old else 0.0,
            new_professional_tax=struct.professional_tax or 0.0,
            old_tds=(old.tds or 0.0) if old else 0.0,
            new_tds=struct.tds or 0.0,
            effective_from=effective_from,
            revision_reason=revision_reason,
            revised_by_id=actor.id if actor else None,
        )
        db.add(revision_log)
        db.commit()
        log.info(
            "Salary revision log written: employee_id=%d, old_ctc=%.2f, "
            "new_ctc=%.2f, diff=%.2f (%.2f%%), effective_from=%s",
            employee_id, old_ctc, new_ctc, diff, pct, effective_from,
        )

    return struct


def upsert_salary_structure_from_ctc(
    db: Session, employee_id: int, annual_ctc: float, actor: Employee,
    bank_name: str = None, account_number: str = None, ifsc_code: str = None,
    effective_from: date = None, revision_reason: str = None,
) -> SalaryStructure:
    """Save salary structure CTC master data only.

    Breakup components (basic, hra, pf, etc.) are stored as 0 for DB compatibility.
    Actual payroll computation happens during payroll generation using annual_ctc.
    """
    data = {
        "employee_id":         employee_id,
        "basic":               0.0,
        "hra":                 0.0,
        "da":                  0.0,
        "special_allowance":   0.0,
        "transport_allowance": 0.0,
        "medical_allowance":   0.0,
        "other_allowances":    0.0,
        "pf_employee":         0.0,
        "pf_employer":         0.0,
        "esi_employee":        0.0,
        "esi_employer":        0.0,
        "professional_tax":    0.0,
        "tds":                 0.0,
        "bank_name":           bank_name,
        "account_number":      account_number,
        "ifsc_code":           ifsc_code,
        "effective_from":      effective_from or date.today(),
        "revision_reason":     revision_reason,
        "annual_ctc":          annual_ctc,
    }
    struct = upsert_salary_structure(db, data, actor)

    log.info(
        "[CTC_SAVE] employee_id=%d | annual_ctc=%.2f | salary_structure_id=%s",
        employee_id, annual_ctc, struct.id,
    )

    return struct


def get_salary_structure(db: Session, employee_id: int) -> Optional[SalaryStructure]:
    """Return the latest active salary structure for an employee."""
    return (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.is_active.is_(True),
        )
        .order_by(
            SalaryStructure.effective_from.desc(),
            SalaryStructure.created_at.desc(),
        )
        .first()
    )


def get_salary_structure_for_period(
    db: Session, employee_id: int, pay_period_end: date
) -> Optional[SalaryStructure]:
    """Return the salary structure that was effective for a given pay period end date.

    Considers ALL revisions (active and superseded) so historical payroll for
    periods BEFORE a recent hike can still find the correct structure.
    Selects the latest revision where effective_from <= pay_period_end — the
    is_active flag is intentionally NOT filtered here because deactivated rows
    are simply earlier revisions that are still the correct choice for past periods.
    """
    return (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            or_(
                SalaryStructure.effective_from.is_(None),
                SalaryStructure.effective_from <= pay_period_end,
            ),
        )
        .order_by(
            SalaryStructure.effective_from.desc(),
            SalaryStructure.created_at.desc(),
        )
        .first()
    )


def list_salary_structures(db: Session, active_only: bool = True) -> list[SalaryStructure]:
    """List salary structures for active, non-deleted employees only.

    Joins with the employees table so that soft-deleted or inactive employees
    (is_deleted=True or employment_status != 'active') are excluded from the
    Salary Master list without physically removing any salary_structures rows.
    """
    q = (
        db.query(SalaryStructure)
        .join(Employee, SalaryStructure.employee_id == Employee.id)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
        )
    )
    if active_only:
        q = q.filter(SalaryStructure.is_active.is_(True))
    return q.order_by(SalaryStructure.employee_id, SalaryStructure.effective_from.desc()).all()


def list_salary_structure_history(db: Session, employee_id: int) -> list[SalaryStructure]:
    """Return ALL salary structure revisions for an employee (history), newest first."""
    return (
        db.query(SalaryStructure)
        .filter(SalaryStructure.employee_id == employee_id)
        .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.created_at.desc())
        .all()
    )


def list_salary_revisions(
    db: Session,
    employee_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SalaryRevisionLog]:
    """Return salary revision log entries, optionally filtered by employee."""
    q = db.query(SalaryRevisionLog)
    if employee_id:
        q = q.filter(SalaryRevisionLog.employee_id == employee_id)
    return (
        q.order_by(SalaryRevisionLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_salary_revision(db: Session, revision_id: int) -> Optional[SalaryRevisionLog]:
    """Return a single revision log entry by id."""
    return db.query(SalaryRevisionLog).filter(SalaryRevisionLog.id == revision_id).first()


# ─── Salary Revision — named public API ──────────────────────────────────────

def create_salary_revision(
    db: Session,
    employee_id: int,
    new_ctc_annual: float,
    effective_from: date,
    assigned_by: Employee,
    revision_reason: Optional[str] = None,
) -> SalaryStructure:
    """Create a salary hike / revision for an employee.

    Revision flow:
      1. Compute new monthly salary breakup from new_ctc_annual via CTC engine.
      2. Deactivate the current active salary_structures row for the employee.
      3. Create a new salary_structures row (new revision).
      4. employee_salary_assignments table is updated by _sync_salary_assignment:
           - Current ACTIVE assignment  → effective_to = effective_from - 1 day,
                                          status = SUPERSEDED.
           - New ACTIVE assignment      → effective_from = hike date,
                                          effective_to = NULL.
      5. SalaryRevisionLog audit entry is written automatically.

    Old salary structures, old payroll runs, and old payslips are never modified.
    Existing closed payrolls reference salary_structure_id directly and remain
    completely unaffected.

    Raises ValueError if the employee is not found.
    """
    if isinstance(effective_from, str):
        effective_from = date.fromisoformat(effective_from)

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")

    return upsert_salary_structure_from_ctc(
        db=db,
        employee_id=employee_id,
        annual_ctc=new_ctc_annual,
        actor=assigned_by,
        effective_from=effective_from,
        revision_reason=revision_reason,
    )


def get_active_salary_assignment(
    db: Session,
    employee_id: int,
    payroll_month: int,
    payroll_year: int,
) -> Optional[EmployeeSalaryAssignment]:
    """Return the salary assignment valid for a given payroll month/year.

    Finds the assignment whose effective_from <= last-day-of-month AND whose
    effective_to is NULL or >= last-day-of-month.  Includes SUPERSEDED
    assignments so historical periods work correctly after a salary hike.

    Returns None if no assignment exists for the period.
    """
    total_days = calendar.monthrange(payroll_year, payroll_month)[1]
    pay_period_end = date(payroll_year, payroll_month, total_days)
    return _get_salary_assignment_for_period(db, employee_id, pay_period_end)


def calculate_prorated_salary_if_revision_mid_month(
    db: Session,
    employee_id: int,
    payroll_month: int,
    payroll_year: int,
) -> dict:
    """Calculate prorated salary if a revision falls strictly mid-month.

    Returns a dict with:
      - is_prorated         : whether a mid-month revision was detected
      - hike_effective_from : ISO date string of the revision date (if prorated)
      - old_salary_days     : calendar days at old salary (before hike)
      - new_salary_days     : calendar days at new salary (from hike onwards)
      - total_days          : total calendar days in the month
      - old_gross_monthly   : full-month gross under old salary
      - new_gross_monthly   : full-month gross under new salary
      - old_gross_amount    : prorated gross at old salary
      - new_gross_amount    : prorated gross at new salary
      - prorated_gross      : blended gross for the month
      - prorated_basic      : blended basic
      - prorated_hra        : blended HRA
      - prorated_special    : blended special allowance
      - prorated_pf_emp     : blended employee PF
      - prorated_pf_er      : blended employer PF
      - prorated_esi_emp    : blended employee ESI (zeroed if gross > ceiling)
      - prorated_esi_er     : blended employer ESI
      - prorated_pt         : PT from the salary applicable for the majority of days
      - prorated_tds        : blended TDS
      - prorated_net        : prorated gross minus all prorated deductions
      - old_structure_id    : salary_structure id for old salary (or None)
      - new_structure_id    : salary_structure id for new salary

    If no mid-month revision exists, is_prorated=False and all prorated_*
    values equal the full-month values from the current structure.
    """
    total_days = calendar.monthrange(payroll_year, payroll_month)[1]
    pay_period_start = date(payroll_year, payroll_month, 1)
    pay_period_end = date(payroll_year, payroll_month, total_days)

    # A mid-month revision has effective_from strictly AFTER the 1st of the month
    mid_month_structures = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.effective_from > pay_period_start,
            SalaryStructure.effective_from <= pay_period_end,
        )
        .order_by(SalaryStructure.effective_from.asc())
        .all()
    )

    current_structure = get_salary_structure_for_period(db, employee_id, pay_period_end)

    def _statutory_from_structure(s: SalaryStructure) -> dict:
        """Extract statutory deduction fields from a salary structure row."""
        return {
            "pf_emp": s.pf_employee or 0.0,
            "pf_er":  s.pf_employer or 0.0,
            "esi_emp": s.esi_employee or 0.0,
            "esi_er":  s.esi_employer or 0.0,
            "pt":      s.professional_tax or 0.0,
            "tds":     s.tds or 0.0,
            "basic":   s.basic or 0.0,
            "hra":     s.hra or 0.0,
            "special": s.special_allowance or 0.0,
        }

    if not mid_month_structures:
        cs = current_structure
        if cs:
            st = _statutory_from_structure(cs)
            total_ded = _sum_money(st["pf_emp"], st["pf_er"], st["esi_emp"], st["pt"], st["tds"])
            return {
                "is_prorated": False,
                "hike_effective_from": None,
                "old_salary_days": 0,
                "new_salary_days": total_days,
                "total_days": total_days,
                "old_gross_monthly": 0.0,
                "new_gross_monthly": cs.gross_monthly,
                "old_gross_amount": 0.0,
                "new_gross_amount": cs.gross_monthly,
                "prorated_gross": cs.gross_monthly,
                "prorated_basic": st["basic"],
                "prorated_hra": st["hra"],
                "prorated_special": st["special"],
                "prorated_pf_emp": st["pf_emp"],
                "prorated_pf_er": st["pf_er"],
                "prorated_esi_emp": st["esi_emp"],
                "prorated_esi_er": st["esi_er"],
                "prorated_pt": st["pt"],
                "prorated_tds": st["tds"],
                "prorated_net": _subtract_money(cs.gross_monthly, total_ded),
                "old_structure_id": None,
                "new_structure_id": cs.id,
            }
        return {
            "is_prorated": False,
            "hike_effective_from": None,
            "old_salary_days": 0,
            "new_salary_days": total_days,
            "total_days": total_days,
            "old_gross_monthly": 0.0,
            "new_gross_monthly": 0.0,
            "old_gross_amount": 0.0,
            "new_gross_amount": 0.0,
            "prorated_gross": 0.0,
            "prorated_basic": 0.0,
            "prorated_hra": 0.0,
            "prorated_special": 0.0,
            "prorated_pf_emp": 0.0,
            "prorated_pf_er": 0.0,
            "prorated_esi_emp": 0.0,
            "prorated_esi_er": 0.0,
            "prorated_pt": 0.0,
            "prorated_tds": 0.0,
            "prorated_net": 0.0,
            "old_structure_id": None,
            "new_structure_id": None,
        }

    # Use the first revision that falls within the month
    new_structure = mid_month_structures[0]
    hike_date = new_structure.effective_from

    # Calendar days before the hike (day 1 to day before hike date)
    old_days = (hike_date - pay_period_start).days
    # Calendar days from the hike date to end of month (inclusive)
    new_days = total_days - old_days

    # Salary structure active the day before the hike
    pre_hike_structure = get_salary_structure_for_period(
        db, employee_id, hike_date - timedelta(days=1)
    )

    old_gross = pre_hike_structure.gross_monthly if pre_hike_structure else 0.0
    new_gross = new_structure.gross_monthly

    old_ratio = old_days / total_days
    new_ratio = new_days / total_days

    old_amount = round(old_gross * old_ratio, 2)
    new_amount = round(new_gross * new_ratio, 2)

    # ── Prorate each earnings component ──
    if pre_hike_structure:
        old_st = _statutory_from_structure(pre_hike_structure)
    else:
        old_st = {"pf_emp": 0.0, "pf_er": 0.0, "esi_emp": 0.0, "esi_er": 0.0,
                  "pt": 0.0, "tds": 0.0, "basic": 0.0, "hra": 0.0, "special": 0.0}
    new_st = _statutory_from_structure(new_structure)

    pro_basic   = round(old_st["basic"]   * old_ratio + new_st["basic"]   * new_ratio, 2)
    pro_hra     = round(old_st["hra"]     * old_ratio + new_st["hra"]     * new_ratio, 2)
    pro_special = round(old_st["special"] * old_ratio + new_st["special"] * new_ratio, 2)

    # ── Prorate statutory deductions ──
    # PF: prorated by day-ratio (employee + employer)
    pro_pf_emp = round(old_st["pf_emp"] * old_ratio + new_st["pf_emp"] * new_ratio, 2)
    pro_pf_er  = round(old_st["pf_er"]  * old_ratio + new_st["pf_er"]  * new_ratio, 2)

    # ESI: prorated by day-ratio; zeroed where gross exceeds the ESI ceiling.
    # We use the blended gross to determine applicability.
    pro_gross_blended = old_amount + new_amount
    try:
        esi_ceiling = _stat_svc.get_active_settings(db).esi_wage_ceiling or 21000.0
    except Exception:
        esi_ceiling = 21000.0
    if pro_gross_blended > esi_ceiling:
        pro_esi_emp = 0.0
        pro_esi_er  = 0.0
    else:
        pro_esi_emp = round(old_st["esi_emp"] * old_ratio + new_st["esi_emp"] * new_ratio, 2)
        pro_esi_er  = round(old_st["esi_er"]  * old_ratio + new_st["esi_er"]  * new_ratio, 2)

    # PT: fixed slab — use the structure with more working days.
    # In most Indian states PT is a flat monthly amount, not prorated.
    pro_pt = new_st["pt"] if new_days >= old_days else old_st["pt"]

    # TDS: prorated by day-ratio (monthly TDS is an annual estimate / 12)
    pro_tds = round(old_st["tds"] * old_ratio + new_st["tds"] * new_ratio, 2)

    total_ded = _sum_money(pro_pf_emp, pro_pf_er, pro_esi_emp, pro_pt, pro_tds)
    pro_net   = _subtract_money(pro_gross_blended, total_ded)

    return {
        "is_prorated": True,
        "hike_effective_from": hike_date.isoformat(),
        "old_salary_days": old_days,
        "new_salary_days": new_days,
        "total_days": total_days,
        "old_gross_monthly": old_gross,
        "new_gross_monthly": new_gross,
        "old_gross_amount": old_amount,
        "new_gross_amount": new_amount,
        "prorated_gross": round(pro_gross_blended, 2),
        "prorated_basic": pro_basic,
        "prorated_hra": pro_hra,
        "prorated_special": pro_special,
        "prorated_pf_emp": pro_pf_emp,
        "prorated_pf_er": pro_pf_er,
        "prorated_esi_emp": pro_esi_emp,
        "prorated_esi_er": pro_esi_er,
        "prorated_pt": pro_pt,
        "prorated_tds": pro_tds,
        "prorated_net": pro_net,
        "old_structure_id": pre_hike_structure.id if pre_hike_structure else None,
        "new_structure_id": new_structure.id,
    }


def list_employees_missing_salary_structure(db: Session) -> list[dict]:
    """Return active employees that have no active salary structure (or one with ₹0 gross)."""
    structured_ids = {
        row.employee_id
        for row in db.query(SalaryStructure)
        .filter(
            SalaryStructure.is_active.is_(True),
            or_(SalaryStructure.gross_monthly > 0, SalaryStructure.annual_ctc > 0),
        )
        .all()
    }
    employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )
    result = []
    for emp in employees:
        if emp.id not in structured_ids:
            has_zero_gross = db.query(SalaryStructure).filter(
                SalaryStructure.employee_id == emp.id,
                SalaryStructure.is_active.is_(True),
            ).first() is not None
            result.append({
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name or ''}".strip(),
                "employee_code": emp.employee_code or f"EMP{emp.id:04d}",
                "department": emp.department.name if emp.department else "—",
                "designation": emp.designation.title if emp.designation else "—",
                "issue": "Salary structure has ₹0 gross" if has_zero_gross else "No salary structure",
            })
    return result


# ─── Payroll Run CRUD ─────────────────────────────────────────────────────────

def create_payroll_run(db: Session, data: dict, actor: Employee) -> PayrollRun:
    fields = derive_payroll_period_fields(data["pay_period_start"])
    # Prevent duplicate: if a non-cancelled run already exists for this month/year, return it
    existing = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.month == int(fields["month"]),
            PayrollRun.year == int(fields["year"]),
            PayrollRun.status != "cancelled",
        )
        .first()
    )
    if existing:
        return normalize_payroll_run_period(existing)
    run = PayrollRun(
        pay_period_start=data["pay_period_start"],
        pay_period_end=data["pay_period_end"],
        month_label=str(fields["month_label"]),
        month=int(fields["month"]),
        year=int(fields["year"]),
        notes=data.get("notes"),
        status="draft",
        attendance_locked=False,
        payroll_locked=False,
        variance_threshold_pct=float(data.get("variance_threshold_pct") or 20.0),
        initiated_by_id=actor.id,
        initiated_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    _ensure_run_document_fields(run)
    _log_action(db, run, actor, "initiate", None, "draft")
    db.commit()
    db.refresh(run)
    _dispatch_payroll_notifications(db, run, "create", actor, data.get("notes"))
    return run


def get_payroll_run(db: Session, run_id: int) -> Optional[PayrollRun]:
    run = (
        db.query(PayrollRun)
        .options(
            joinedload(PayrollRun.employees),
            joinedload(PayrollRun.approvals),
            joinedload(PayrollRun.errors),
        )
        .filter(PayrollRun.id == run_id)
        .first()
    )
    return normalize_payroll_run_period(run)


def list_payroll_runs(db: Session, limit: int = 20, offset: int = 0) -> list[PayrollRun]:
    # Status priority: higher index = more advanced/preferred when deduplicating
    _STATUS_PRIORITY = {
        "draft": 0,
        "attendance_frozen": 1,
        "processing": 2,
        "under_review": 3,
        "pending_head_approval": 4,
        "approved": 5,
        "payslip_generated": 6,
        "bank_advice_generated": 7,
        "published": 8,
        "closed": 9,
    }
    all_runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.status != "cancelled")
        .order_by(PayrollRun.pay_period_start.desc())
        .all()
    )
    # Normalize first so month/year are always derived from pay_period_start
    # (DB columns are Optional — old runs may have NULL month/year)
    all_runs = [normalize_payroll_run_period(r) for r in all_runs if r]
    # Deduplicate: keep highest-priority status per month/year
    seen: dict = {}
    for run in all_runs:
        # Use pay_period_start as authoritative fallback if month/year still null
        m = run.month or (run.pay_period_start.month if run.pay_period_start else 0)
        y = run.year or (run.pay_period_start.year if run.pay_period_start else 0)
        key = (m, y)
        if key not in seen:
            seen[key] = run
        else:
            existing_priority = _STATUS_PRIORITY.get(seen[key].status, -1)
            this_priority = _STATUS_PRIORITY.get(run.status, -1)
            if this_priority > existing_priority:
                seen[key] = run
    deduped = sorted(seen.values(), key=lambda r: (
        r.year or (r.pay_period_start.year if r.pay_period_start else 0),
        r.month or (r.pay_period_start.month if r.pay_period_start else 0),
    ), reverse=True)
    return deduped[offset: offset + limit]


def advance_run_status(
    db: Session, run_id: int, action: str, remarks: Optional[str], actor: Employee
) -> PayrollRun:
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        raise ValueError(f"Payroll run {run_id} not found")
    _ensure_run_document_fields(run)

    # ── Defense-in-depth: explicitly block destructive actions on locked runs ──
    if (run.status in _LOCKED_STATUSES or run.payroll_locked) and action in ("generate", "recompute", "process"):
        raise ValueError(
            "Payroll is final approved and locked. Recompute/edit is not allowed."
        )

    new_status = _next_status(run.status, action)
    if new_status is None:
        raise ValueError(
            f"Action '{action}' is not valid from status '{run.status}'"
        )

    if action == "generate_payslips" and not is_final_approved_run(run):
        raise ValueError(
            "Finance Head final approval is required before generating payslips."
        )

    if action == "publish":
        if not is_final_approved_run(run):
            raise ValueError(
                "Finance Head final approval is required before publishing payslips to ESS."
            )
        ensure_payroll_records_exist(db, run.id)
        generated_slips = db.query(Payslip).filter_by(run_id=run.id).count()
        if generated_slips == 0:
            raise ValueError("Generate payslips before publishing to ESS.")

    # Gate: payroll generation requires either the run's attendance to have been
    # explicitly frozen (attendance_frozen status) OR the HR monthly attendance
    # summary to be frozen (checked by the bridge gate below).  Allowing "generate"
    # from "draft" lets Finance skip the redundant "Freeze Payroll Input" click when
    # HR has already frozen the monthly attendance summary.
    # Also allow "generate" from "processing" — treated as a recompute so Finance
    # can re-generate employee rows when the run has 0 records (e.g. after a prior
    # partial failure) without needing to know to use "recompute" explicitly.
    if action == "generate" and run.status not in ("attendance_frozen", "processing"):
        raise ValueError(
            "Payroll can only be generated from attendance_frozen or processing status. "
            "HR must freeze monthly attendance before payroll generation."
        )

    # ── Monthly Attendance Summary bridge gate ────────────────────────────
    # TEMPORARY PAYROLL BRIDGE: In production the Attendance/Timesheet modules
    # will populate monthly_attendance_summary and set is_frozen=True.
    # Until then, HR/Admin must freeze via /payroll/attendance-summary/freeze.
    if action in ("generate", "process"):
        run_month = run.pay_period_start.month
        run_year  = run.pay_period_start.year
        try:
            from app.services.payroll_attendance_bridge import check_frozen_for_payroll
            ok, reason = check_frozen_for_payroll(db, run_month, run_year)
            if not ok:
                raise ValueError(reason)
        except ValueError:
            raise
        except Exception as _gate_err:
            # If the bridge service itself errors (e.g. table not yet created on
            # a fresh DB), log and allow — the gate is best-effort until the table
            # is confirmed to exist.
            log.warning(
                "Attendance bridge gate check failed (non-fatal, allowing): %s", _gate_err
            )

    # Gate: cannot submit, approve, or produce payroll outputs if unresolved
    # generation/review errors exist.
    if action in (
        "submit_review",
        "submit_for_approval",
        "approve",
        "head_approve",
        "finance_review",
        "finance_head_approve",
        "hr_confirm",
        "generate_payslips",
        "generate_bank_advice",
        "publish",
        "close",
    ):
        open_errors = (
            db.query(PayrollError)
            .filter_by(run_id=run_id, is_resolved=False)
            .count()
        )
        if open_errors > 0:
            raise ValueError(
                f"Approval blocked. Resolve payroll issues before continuing. "
                f"({open_errors} unresolved error(s) found)"
            )

    if action in ("head_approve", "finance_head_approve") and not _finance_review_completed(db, run_id):
        raise ValueError("Finance review must be completed before Finance Head final approval")

    if action in (
        "start_review",
        "submit_review",
        "submit_for_approval",
        "approve",
        "finance_review",
        "head_approve",
        "finance_head_approve",
        "hr_confirm",
        "finalize",
        "generate_payslips",
        "generate_bank_advice",
        "publish",
        "close",
    ):
        ensure_payroll_records_exist(db, run.id)

    # Gate: Finance must acknowledge variance BEFORE sending to Finance Head.
    # Also covers submit_review/submit_for_approval which now go directly to
    # pending_head_approval (one-click Finance submission flow).
    if action in ("approve", "finance_review", "submit_review", "submit_for_approval"):
        try:
            from app.models.payroll_extended import PayrollVarianceLog
            flagged_rows = (
                db.query(PayrollVarianceLog)
                .filter(
                    PayrollVarianceLog.run_id == run_id,
                    PayrollVarianceLog.is_flagged.is_(True),
                    PayrollVarianceLog.acknowledged_by_id.is_(None),
                )
                .all()
            )
            flagged_unacknowledged = sum(
                1
                for variance_row in flagged_rows
                if "salary assignment" not in (variance_row.variance_flags or "").lower()
            )

            # Auto-acknowledge: when no variance entries are flagged (first payroll
            # run, or all employees have 0% variance vs previous run), mark
            # variance_reviewed automatically so Finance is not blocked.
            if flagged_unacknowledged == 0:
                try:
                    run.variance_reviewed = True
                except Exception:
                    pass

            variance_reviewed = getattr(run, "variance_reviewed", True)
            if flagged_unacknowledged > 0 and not variance_reviewed:
                raise ValueError(
                    f"Variance review required. {flagged_unacknowledged} employee(s) have "
                    "significant payroll changes that Finance must acknowledge before sending "
                    "to Finance Head. Use POST /finance/payroll/{run_id}/variance/acknowledge."
                )
        except ValueError:
            raise
        except Exception as _var_err:
            log.warning("Variance gate check failed (non-fatal): %s", _var_err)

    old_status = run.status
    run.status = new_status

    now = datetime.utcnow()
    _ensure_run_document_fields(run)

    if action == "freeze_attendance":
        run.attendance_locked = True
        _record_lock_history(db, run, "ATTENDANCE", "LOCK", actor, remarks or "Payroll attendance snapshot locked")

    if action in ("generate", "process", "recompute"):
        run.processed_at = now
        run.attendance_locked = True
        # Refresh TDS from latest tax declarations before computing rows
        try:
            _stat_svc.refresh_tds_for_run(db, run.id)
        except Exception as _tds_err:
            log.warning("TDS refresh failed before payroll processing (run %s): %s", run.id, _tds_err)
        _generate_employee_rows(db, run)
        # Compute and store variance log after generation
        try:
            _compute_and_store_variance(db, run)
        except Exception as _var_e:
            log.warning("Variance computation failed (non-fatal): %s", _var_e)
        # H-5: HR accountability audit — record that Finance generated payroll
        # against HR-frozen attendance inputs.
        try:
            _mark_approval_step(
                db, run, actor, "HR_INPUT_FROZEN", "APPROVED",
                f"Payroll generated by Finance based on HR-frozen attendance for {run.month_label}.",
            )
        except Exception as _hr_log_err:
            log.warning("HR input audit log failed (non-fatal): %s", _hr_log_err)

    elif action == "start_review":
        # H-3: Finance formally enters review state (processing → under_review).
        if (run.total_employees or 0) == 0:
            raise ValueError(
                "Cannot start Finance Review: payroll has 0 employee records. "
                "Generate payroll first."
            )
        _mark_approval_step(
            db, run, actor, "FINANCE_REVIEW", "INITIATED",
            remarks or f"Finance Review started for {run.month_label}.",
        )

    elif action in ("submit_review", "submit_for_approval"):
        # Validate payroll completeness before Finance submits to Finance Head.
        if (run.total_employees or 0) == 0:
            raise ValueError(
                "Cannot submit: payroll has 0 employee records. "
                "Generate payroll first before submitting to Finance Head."
            )
        if (run.total_gross or 0) <= 0:
            raise ValueError(
                "Cannot submit: total gross pay is ₹0. Regenerate payroll before submitting."
            )
        if (run.total_net or 0) <= 0:
            raise ValueError(
                "Cannot submit: total net pay is ₹0. Regenerate payroll before submitting."
            )
        # Record Finance team's review sign-off and set Finance approval timestamp.
        _mark_approval_step(db, run, actor, "FINANCE_REVIEW", "APPROVED", remarks)
        _ensure_pending_approval_steps(db, run, actor)
        run.approved_at = now
        run.approved_by_id = actor.id
        try:
            run.variance_reviewed = True
        except Exception:
            pass

    elif action in ("approve", "finance_review"):
        # Recovery path: Finance resubmitting after Finance Head rejection
        # (under_review → pending_head_approval). Set the same Finance sign-off
        # fields as the primary submit_review path.
        _mark_approval_step(db, run, actor, "FINANCE_REVIEW", "APPROVED", remarks)
        _ensure_pending_approval_steps(db, run, actor)
        run.approved_at = now
        run.approved_by_id = actor.id
        try:
            run.variance_reviewed = True
        except Exception:
            pass

    elif action in ("head_approve", "finance_head_approve"):
        _mark_approval_step(db, run, actor, "FINANCE_HEAD_APPROVAL", "APPROVED", remarks)
        _mark_approval_step(db, run, actor, "HR_CONFIRMATION", "APPROVED", "Legacy head approval confirmed payroll")
        run.approved_at = now
        run.approved_by_id = actor.id
        run.payroll_locked = True  # Lock payroll so is_final_approved_run() passes

    elif action == "hr_confirm":
        _mark_approval_step(db, run, actor, "HR_CONFIRMATION", "APPROVED", remarks)
        run.approved_at = now
        run.approved_by_id = actor.id

    elif action in ("reject", "head_reject"):
        level = "FINANCE_REVIEW" if action == "reject" else "FINANCE_HEAD_APPROVAL"
        _mark_approval_step(db, run, actor, level, "REJECTED", remarks)

    elif action == "finalize":
        run.payroll_locked = True
        run.finalized_by_id = actor.id
        run.finalized_at = now
        db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
            {"is_locked": True}, synchronize_session=False
        )
        _record_lock_history(db, run, "PAYROLL", "LOCK", actor, remarks or "Payroll finalized")

    elif action == "disburse":
        # Legacy action — no longer reachable via _TRANSITIONS.  Kept so that
        # pre-Sprint 3 disbursed runs can still be queried without errors.
        run.disbursed_at = now

    elif action == "generate_bank_advice":
        # Sprint 3: mandatory step between payslip_generated and published.
        # The actual CSV is generated by the route handler via payslip_service;
        # this handler records the audit trail and sets the run metadata.
        try:
            run.bank_advice_generated_at = now
            run.bank_advice_status = "generated"
        except Exception:
            pass
        _mark_approval_step(
            db, run, actor, "BANK_ADVICE", "GENERATED",
            remarks or f"Bank advice generated for {run.month_label}.",
        )

    elif action == "generate_payslips":
        _generate_payslip_records(db, run, actor)

    elif action == "publish":
        run.published_at = now
        # Final publish locks the payroll and completes the run.
        run.payroll_locked = True
        run.finalized_by_id = actor.id
        run.finalized_at = now
        db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
            {"is_locked": True}, synchronize_session=False
        )
        # Use payslip_service.bulk_publish_payslips for individual immutability.
        # Employee notifications are emitted once below through the shared
        # notification service after this transition commits.
        try:
            from app.services.payslip_service import bulk_publish_payslips as _bulk_pub
            pub_result = _bulk_pub(db, run_id=run.id, published_by_id=actor.id, send_emails=False)
            log.info(
                "Bulk publish run_id=%d: %s", run.id, pub_result
            )
        except Exception as _pub_err:
            log.warning("bulk_publish_payslips failed, falling back to direct update: %s", _pub_err)
            for slip in db.query(Payslip).filter_by(run_id=run.id, is_published=False).all():
                slip.is_published = True
                slip.status = "PUBLISHED"
                slip.published_at = now
                _log_audit(db, slip.run_id, slip.employee_id, "published")
        _record_lock_history(db, run, "PAYSLIP", "LOCK", actor, remarks or "Payslips published")
        # Store per-employee TDS monthly breakup for Form 16 Part B
        try:
            _upsert_tds_breakups_for_run(db, run)
        except Exception as _tds_bp_err:
            log.warning("TDS monthly breakup storage failed (non-fatal): %s", _tds_bp_err)

    if action == "close":
        # Ensure payroll is locked on close — may already be True from publish, but make explicit.
        run.payroll_locked = True
        _record_lock_history(db, run, "PAYROLL", "LOCK", actor, remarks or "Payroll run closed")

    # On completion or close: persist annual TDS summary (Form 16 Part A) for each employee
    if new_status in ("completed", "closed"):
        try:
            _upsert_annual_tds_summaries_for_run(db, run)
        except Exception as _tds_ann_err:
            log.warning("TDS annual summary storage failed (non-fatal): %s", _tds_ann_err)

    _log_action(db, run, actor, action, old_status, new_status, remarks)
    db.commit()
    db.refresh(run)
    _dispatch_payroll_notifications(db, run, action, actor, remarks)
    return run


def _upsert_tds_breakups_for_run(db: Session, run: PayrollRun) -> None:
    """After publish, write per-employee TDS monthly breakup rows for Form 16."""
    from app.services.statutory_service import upsert_tds_monthly_breakup
    month, year, _ = _period_month_year(run)
    fy_start = year if month >= 4 else year - 1
    financial_year = f"{fy_start}-{str(fy_start + 1)[-2:]}"

    rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    for row in rows:
        try:
            upsert_tds_monthly_breakup(
                db=db,
                employee_id=row.employee_id,
                run_id=run.id,
                month=month,
                year=year,
                financial_year=financial_year,
                monthly_tds=float(row.tds or 0),
                gross_salary=float(row.gross_earnings or 0),
                pf_employee=float(row.employee_pf or 0),
                esi_employee=float(row.employee_esi or 0),
                professional_tax=float(row.professional_tax or 0),
                regime_used="new",
                annual_taxable_at_time=float((row.gross_earnings or 0) * 12),
                remaining_months_at_time=12,
                tds_debug_json=None,
            )
        except Exception as _bp_err:
            log.warning(
                "TDS monthly breakup failed for employee_id=%d run=%d: %s",
                row.employee_id, run.id, _bp_err,
            )


def _upsert_annual_tds_summaries_for_run(db: Session, run: PayrollRun) -> None:
    """On close, aggregate monthly breakups into annual TDS summary for Form 16."""
    from app.services.statutory_service import upsert_tds_annual_summary
    month, year, _ = _period_month_year(run)
    fy_start = year if month >= 4 else year - 1
    financial_year = f"{fy_start}-{str(fy_start + 1)[-2:]}"

    rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    emp_ids = [r.employee_id for r in rows]
    for employee_id in emp_ids:
        try:
            upsert_tds_annual_summary(db=db, employee_id=employee_id, financial_year=financial_year)
        except Exception as _ann_err:
            log.warning(
                "TDS annual summary failed for employee_id=%d fy=%s: %s",
                employee_id, financial_year, _ann_err,
            )


# ─── Core Payroll Generation Engine ──────────────────────────────────────────

# Maps BonusRequest.bonus_type → PayrollAdjustment.adjustment_type
_BONUS_TYPE_TO_ADJ_TYPE: dict[str, str] = {
    "Joining Bonus":     "bonus",
    "Annual Bonus":      "bonus",
    "Performance Bonus": "bonus",
    "Incentive":         "bonus",
    "Arrears":           "arrears",
    "Special Bonus":     "bonus",
    "Other":             "other_addition",
}


def _generate_employee_rows(db: Session, run: PayrollRun) -> None:
    """
    Enterprise payroll row generation.

    For each active employee:
      1. Find the LATEST active salary structure with effective_from <= pay_period_end.
      2. Validate the structure (gross > 0, no CTC mismatch).
      3. Apply LOP deduction from Leave Management payroll inputs.
      4. Apply one-time PayrollAdjustments (bonus, arrears, deductions).
      5. Store the salary_structure_id used (immutable audit anchor).
      6. Log TDS computation details.

    Locked runs (approved / payslip_generated / published / closed / cancelled)
    raise ValueError — they are never regenerated.

    ₹0 rows are NEVER inserted. Employees without a valid salary structure get
    a PayrollError instead of a placeholder row.
    """
    # ── Guard: never regenerate locked runs ──
    if run.status in _LOCKED_STATUSES or run.payroll_locked:
        raise ValueError(
            f"Payroll run {run.id} is '{run.status}' and cannot be recomputed. "
            f"Immutable statuses: {sorted(_LOCKED_STATUSES)}."
        )

    # ── Idempotent cleanup — safe to call on recompute ──
    # synchronize_session=False: bypass ORM identity-map evaluation so the DELETE
    # always hits the DB cleanly regardless of what objects are in the session cache.
    db.query(PayrollRunEmployee).filter_by(run_id=run.id).delete(synchronize_session=False)
    for error_type in (
        "employee_inactive",
        "doj_doe_issue",
        "duplicate_payroll_record",
        "invalid_net_pay",
        "lop_payable_mismatch",
        "missing_ctc",
        "missing_salary_structure",
        "salary_mismatch",
        "missing_attendance_summary",
        "computation_error",
    ):
        db.query(PayrollError).filter_by(
            run_id=run.id, error_type=error_type
        ).delete(synchronize_session=False)

    pay_period_start = run.pay_period_start
    pay_period_end = run.pay_period_end
    period_month_num, period_year, period_month = _period_month_year(run)

    log.info(
        "[Run %d] Generating payroll — period=%s, pay_period_end=%s",
        run.id, run.month_label, pay_period_end,
    )

    # All active, non-deleted employees are evaluated
    active_employees = (
        db.query(Employee)
        .filter(
            Employee.is_deleted.is_(False),
            Employee.employment_status == "active",
            or_(Employee.date_of_joining.is_(None), Employee.date_of_joining <= pay_period_end),
            or_(Employee.date_of_exit.is_(None), Employee.date_of_exit >= pay_period_start),
        )
        .order_by(Employee.id)
        .all()
    )
    active_employee_ids = {emp.id for emp in active_employees}
    attendance_employee_ids = {
        employee_id
        for (employee_id,) in (
            db.query(MonthlyAttendanceSummary.employee_id)
            .filter(
                MonthlyAttendanceSummary.month == period_month_num,
                MonthlyAttendanceSummary.year == period_year,
                MonthlyAttendanceSummary.is_frozen.is_(True),
                MonthlyAttendanceSummary.is_ready_for_payroll.is_(True),
            )
            .all()
        )
    }
    candidate_employee_ids = active_employee_ids | attendance_employee_ids
    active_employees = (
        db.query(Employee)
        .filter(
            Employee.id.in_(candidate_employee_ids),
            Employee.is_deleted.is_(False),
        )
        .order_by(Employee.id)
        .all()
        if candidate_employee_ids
        else []
    )

    generated = 0
    errors    = 0

    for emp in active_employees:
        emp_label = f"{emp.first_name} {emp.last_name or ''}".strip()

        employee_validation_issues: list[str] = []
        if (emp.employment_status or "").lower() != "active":
            employee_validation_issues.append("Employee is inactive for this payroll period")
        if emp.date_of_joining and emp.date_of_joining > pay_period_end:
            employee_validation_issues.append(
                f"DOJ {emp.date_of_joining} is after pay period end {pay_period_end}"
            )
        if emp.date_of_exit and emp.date_of_exit < pay_period_start:
            employee_validation_issues.append(
                f"DOE {emp.date_of_exit} is before pay period start {pay_period_start}"
            )
        if employee_validation_issues:
            _add_generation_error(
                db,
                run,
                emp,
                "doj_doe_issue"
                if any(issue.startswith(("DOJ", "DOE")) for issue in employee_validation_issues)
                else "employee_inactive",
                "; ".join(employee_validation_issues),
            )
            errors += 1
            continue

        # ── Step 1: Find salary structure for this payroll period ──
        # salary_structures is the approved payroll source of truth.  Assignment
        # rows are retained only as audit context for older data.
        assignment = _get_salary_assignment_for_period(db, emp.id, pay_period_end)
        ss = get_salary_structure_for_period(db, emp.id, pay_period_end)

        if ss is None:
            # Check whether there IS a structure but it's future-dated
            future_ss = (
                db.query(SalaryStructure)
                .filter(
                    SalaryStructure.employee_id == emp.id,
                    SalaryStructure.is_active.is_(True),
                )
                .order_by(SalaryStructure.effective_from.asc())
                .first()
            )

            if future_ss:
                desc = (
                    f"Salary structure for {emp_label} (id={emp.id}) is effective from "
                    f"{future_ss.effective_from}, which is AFTER the pay period end "
                    f"({pay_period_end}). No salary is assigned for this pay period. "
                    "Either backdate the effective_from or create a new structure effective "
                    "before or on the pay period end date."
                )
                log.warning(
                    "[Run %d] Employee %d (%s): salary structure effective %s is future-dated "
                    "(pay_period_end=%s) — skipping.",
                    run.id, emp.id, emp_label, future_ss.effective_from, pay_period_end,
                )
            else:
                desc = (
                    f"No salary structure found for {emp_label} (employee_id={emp.id}). "
                    "Please create a salary structure before running payroll."
                )
                log.warning(
                    "[Run %d] Employee %d (%s): no salary structure found.",
                    run.id, emp.id, emp_label,
                )

            _add_generation_error(
                db,
                run,
                emp,
                "missing_salary_structure",
                desc,
            )
            errors += 1
            continue

        annual_ctc = float(ss.annual_ctc or 0.0)
        gross_monthly = float(ss.gross_monthly or 0.0)
        has_earnings_breakup = any(
            float(value or 0.0) > 0.0
            for value in (
                ss.basic,
                ss.hra,
                ss.da,
                ss.special_allowance,
            )
        )
        # Always derive from annual_ctc when set — stale stored component values
        # (gross_monthly, basic, hra, etc.) are ignored to prevent using outdated data.
        ctc_only_structure = annual_ctc > 0.0

        # ── Step 2: Sanity validation ──
        if gross_monthly <= 0.0 and annual_ctc <= 0.0:
            _add_generation_error(
                db,
                run,
                emp,
                "missing_ctc",
                (
                    f"Salary structure (id={ss.id}) for {emp_label} has no Annual CTC. "
                    "Update Salary Master with valid Annual CTC before generating payroll."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
            )
            log.error(
                "[Run %d] Employee %d (%s): salary structure id=%d has ₹0 gross — skipping.",
                run.id, emp.id, emp_label, ss.id,
            )
            errors += 1
            continue

        if annual_ctc <= 0.0:
            _add_generation_error(
                db,
                run,
                emp,
                "missing_ctc",
                (
                    f"Annual CTC missing in salary structure (id={ss.id}) for {emp_label}. "
                    "Payroll must be generated from Annual CTC."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
            )
            errors += 1
            continue

        # CTC mismatch guard — catches accidental monthly-vs-annual data entry errors.
        # Threshold: gross_monthly < 30% of (annual_ctc / 12) is suspicious.
        if not ctc_only_structure and annual_ctc > 50_000:
            expected_monthly = annual_ctc / 12
            if gross_monthly < expected_monthly * 0.30:
                mismatch_pct = round(gross_monthly / expected_monthly * 100, 1)
                db.add(PayrollError(
                    run_id=run.id,
                    employee_id=emp.id,
                    error_type="salary_mismatch",
                    description=(
                        f"Salary mismatch warning for {emp_label} (id={emp.id}): "
                        f"annual_ctc=₹{ss.annual_ctc:,.0f} implies expected monthly gross "
                        f"~₹{expected_monthly:,.0f}, but salary_structure (id={ss.id}) "
                        f"gross_monthly=₹{ss.gross_monthly:,.2f} "
                        f"({mismatch_pct}% of expected). "
                        "Possible data entry error — verify whether annual CTC or monthly "
                        "salary was entered. Payroll row has been generated but requires review."
                    ),
                    severity="warning",
                ))
                log.warning(
                    "[Run %d] Employee %d (%s): salary mismatch — "
                    "annual_ctc=%.2f, expected_monthly=%.2f, actual_gross=%.2f (%.1f%%)",
                    run.id, emp.id, emp_label,
                    ss.annual_ctc, expected_monthly, gross_monthly, mismatch_pct,
                )
                # Warning only — row is still generated, Finance must review

        log.info(
            "[Run %d] Employee %d (%s): using salary_structure id=%d, "
            "effective_from=%s, gross=₹%.2f",
            run.id, emp.id, emp_label, ss.id, ss.effective_from, gross_monthly,
        )

        # ── Step 3: Finalized attendance/timesheet summary for this period ──
        # Primary source: MonthlyAttendanceSummary (integer month/year, is_frozen +
        # is_ready_for_payroll flags).  This is the canonical payroll bridge table
        # populated by Attendance/Timesheet modules (or manual HR entry).
        # Fallback: legacy PayrollAttendanceSummary may supply attendance fields
        # for backwards compatibility, but LOP still comes only from Leave Management.
        mas_att = (
            db.query(MonthlyAttendanceSummary)
            .filter(
                MonthlyAttendanceSummary.employee_id == emp.id,
                MonthlyAttendanceSummary.month == period_month_num,
                MonthlyAttendanceSummary.year == period_year,
                MonthlyAttendanceSummary.is_frozen.is_(True),
                MonthlyAttendanceSummary.is_ready_for_payroll.is_(True),
            )
            .first()
        )

        if mas_att is not None:
            working_days   = int(mas_att.total_working_days or 0)
            lop_days       = int(mas_att.lop_days or 0)
            payable_days   = (
                float(mas_att.payable_days)
                if mas_att.payable_days is not None
                else float(max(working_days - lop_days, 0))
            )
            present_days   = int(mas_att.present_days or 0)
            leave_days     = int(mas_att.leave_days or 0)
            holiday_days   = 0
            attendance_delta = _attendance_reconciliation_delta(
                working_days=working_days,
                present_days=present_days,
                leave_days=leave_days,
                holiday_days=holiday_days,
                lop_days=lop_days,
            )
            if attendance_delta > 0:
                holiday_days = attendance_delta
            elif attendance_delta < 0:
                _add_generation_error(
                    db,
                    run,
                    emp,
                    "attendance_reconciliation_mismatch",
                    (
                        f"Attendance summary mismatch for {emp_label}: present={present_days}, "
                        f"leave={leave_days}, holidays={holiday_days}, lop={lop_days}, "
                        f"working={working_days}."
                    ),
                    salary_structure_id=ss.id,
                    salary_assignment_id=assignment.id if assignment else None,
                    working_days=working_days,
                    payable_days=payable_days,
                    present_days=present_days,
                    leave_days=leave_days,
                    lop_days=lop_days,
                    holiday_days=holiday_days,
                )
                errors += 1
                continue
            overtime_hours = float(mas_att.approved_timesheet_hours) if mas_att.approved_timesheet_hours else 0.0
            log.info(
                "[Run %d] Employee %d (%s): attendance from MonthlyAttendanceSummary — "
                "working=%d, present=%d, leave=%d, holidays=%d, lop=%d, payable=%.1f",
                run.id, emp.id, emp_label,
                working_days, present_days, leave_days, holiday_days, lop_days, payable_days,
            )
            attendance = {
                "is_finalized": True,
                "fallback_used": False,
                "fallback_reason": None,
            }
        else:
            _add_generation_error(
                db,
                run,
                emp,
                "missing_attendance_summary",
                (
                    f"Frozen monthly attendance summary not found for {emp_label} "
                    f"(employee_id={emp.id}) for {period_month_num}/{period_year}. "
                    "Freeze monthly attendance before generating payroll."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
            )
            log.error(
                "[Run %d] Employee %d (%s): frozen MonthlyAttendanceSummary missing "
                "for month=%d year=%d — skipping.",
                run.id, emp.id, emp_label, period_month_num, period_year,
            )
            errors += 1
            continue

        # ── Step 4: One-time adjustments ──
        # Normalize direction to lowercase+stripped so any casing variation in the
        # DB ("Addition", " addition", "ADDITION") is handled correctly.
        expected_payable_days = float(max(working_days - lop_days, 0))
        if (
            working_days <= 0
            or lop_days < 0
            or lop_days > working_days
            or abs(float(payable_days or 0.0) - expected_payable_days) > 0.01
        ):
            _add_generation_error(
                db,
                run,
                emp,
                "lop_payable_mismatch",
                (
                    f"LOP/payable days mismatch for {emp_label}: working={working_days}, "
                    f"lop={lop_days}, payable={payable_days}, expected payable={expected_payable_days}."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
                working_days=working_days,
                payable_days=payable_days,
                present_days=present_days,
                leave_days=leave_days,
                lop_days=lop_days,
                holiday_days=holiday_days,
            )
            errors += 1
            continue

        # ── Materialise waiting bonus requests for this employee + payroll month ──
        # Only regular_payroll bonuses in waiting_for_payroll_application are picked up here.
        # off_cycle bonuses always go to status=approved and are never auto-applied by generation.
        # Idempotent: payroll_adjustment_id IS NULL prevents double-apply on recompute.
        waiting_bonuses = (
            db.query(_BonusRequest)
            .filter(
                _BonusRequest.employee_id   == emp.id,
                _BonusRequest.payroll_month == period_month_num,
                _BonusRequest.payroll_year  == period_year,
                _BonusRequest.status        == "waiting_for_payroll_application",
                _BonusRequest.payment_mode  == "regular_payroll",
                _BonusRequest.payroll_adjustment_id.is_(None),
            )
            .all()
        )
        for br in waiting_bonuses:
            adj = PayrollAdjustment(
                run_id=run.id,
                employee_id=br.employee_id,
                adjustment_type=_BONUS_TYPE_TO_ADJ_TYPE.get(br.bonus_type, "bonus"),
                direction="addition",
                amount=br.amount,
                description=f"{br.bonus_type}" + (f": {br.reason}" if br.reason else ""),
                is_taxable=True,
                approved_by_id=br.approved_by_id,
            )
            db.add(adj)
            db.flush()
            br.payroll_adjustment_id = adj.id
            br.payroll_run_id = run.id
            br.status = "applied"
            log.info(
                "[Run %d] Employee %d (%s): materialised waiting bonus request %d "
                "(%s ₹%.2f) → PayrollAdjustment %d",
                run.id, emp.id, emp_label, br.id, br.bonus_type, br.amount, adj.id,
            )

        adjustments = (
            db.query(PayrollAdjustment)
            .filter_by(run_id=run.id, employee_id=emp.id)
            .all()
        )
        additions     = sum(
            a.amount for a in adjustments
            if a.direction.strip().lower() == "addition"
        )
        deduction_adj = sum(
            a.amount for a in adjustments
            if a.direction.strip().lower() == "deduction"
        )
        taxable_additions = sum(
            a.amount for a in adjustments
            if a.direction.strip().lower() == "addition" and a.is_taxable
        )
        non_taxable_additions = additions - taxable_additions
        bonus_amount = round(sum(
            a.amount for a in adjustments
            if a.adjustment_type.strip().lower() == "bonus" and a.direction.strip().lower() == "addition"
        ), 2)
        variable_pay_amount = round(sum(
            a.amount for a in adjustments
            if a.adjustment_type.strip().lower() == "variable_pay" and a.direction.strip().lower() == "addition"
        ), 2)
        lta_amount = round(sum(
            a.amount for a in adjustments
            if a.adjustment_type.strip().lower() == "lta" and a.direction.strip().lower() == "addition"
        ), 2)
        overtime_amount = round(sum(
            a.amount for a in adjustments
            if a.adjustment_type.strip().lower() in ("overtime_pay", "overtime")
            and a.direction.strip().lower() == "addition"
        ), 2)

        log.info(
            "[Run %d] Employee %d (%s): adjustments loaded — "
            "total=%d, additions=₹%.2f (taxable=₹%.2f, non-taxable=₹%.2f), deductions=₹%.2f",
            run.id, emp.id, emp_label,
            len(adjustments), additions, taxable_additions, non_taxable_additions, deduction_adj,
        )
        if adjustments:
            for a in adjustments:
                log.info(
                    "[Run %d] Employee %d: adj id=%d type=%s direction=%s "
                    "amount=₹%.2f taxable=%s",
                    run.id, emp.id, a.id, a.adjustment_type,
                    a.direction, a.amount, a.is_taxable,
                )

        # ── Step 5: Base salary — check for mid-month revision first ──
        # If a salary revision became effective strictly after the 1st of this month,
        # we must prorate: days before hike at old salary + days from hike at new salary.
        try:
            proration = calculate_prorated_salary_if_revision_mid_month(
                db, emp.id, period_month_num, period_year
            )
        except Exception as _pro_err:
            log.warning(
                "[Run %d] Employee %d (%s): proration check failed (%s) — "
                "falling back to full-month salary.",
                run.id, emp.id, emp_label, _pro_err,
            )
            proration = {"is_prorated": False}

        is_mid_month = proration.get("is_prorated", False)

        if is_mid_month and not ctc_only_structure:
            # Use blended prorated values for every component
            base_gross      = proration["prorated_gross"]
            base_basic      = proration["prorated_basic"]
            base_hra        = proration["prorated_hra"]
            base_da         = round(
                (ss.da or 0.0) * proration["new_salary_days"] / proration["total_days"]
                + (
                    (get_salary_structure_for_period(
                        db, emp.id,
                        date(period_year, period_month_num, 1) - timedelta(days=1)
                    ) or ss).da or 0.0
                ) * proration["old_salary_days"] / proration["total_days"],
                2,
            )
            base_special    = proration["prorated_special"]
            base_conveyance = round(
                (ss.transport_allowance or 0.0)
                * proration["new_salary_days"] / proration["total_days"],
                2,
            )
            base_lta        = 0.0
            base_allowances = round(
                base_special + base_conveyance
                + (ss.medical_allowance or 0.0)
                + (ss.other_allowances or 0.0),
                2,
            )
            base_pf_emp     = proration["prorated_pf_emp"]
            base_pf_er      = proration["prorated_pf_er"]
            base_esi_emp    = proration["prorated_esi_emp"]
            base_esi_er     = proration["prorated_esi_er"]
            base_pt         = proration["prorated_pt"]
            base_tds        = proration["prorated_tds"]
            base_deductions = _sum_money(base_pf_emp, base_esi_emp, base_pt, base_tds)
            log.info(
                "[Run %d] Employee %d (%s): MID-MONTH REVISION detected — "
                "hike_date=%s, old_days=%d, new_days=%d, prorated_gross=₹%.2f",
                run.id, emp.id, emp_label,
                proration["hike_effective_from"],
                proration["old_salary_days"],
                proration["new_salary_days"],
                base_gross,
            )
        elif ctc_only_structure:
            # CTC-only salary master (from-ctc endpoint stores components as 0).
            # Compute the full monthly breakup via the CTC engine at generation time,
            # which is exactly what was intended by the from-ctc save path.
            _ctc_tds_override = ss.tds or 0.0
            try:
                breakup = compute_from_ctc(annual_ctc, db, monthly_tds=_ctc_tds_override)
            except Exception as _ctc_err:
                _add_generation_error(
                    db,
                    run,
                    emp,
                    "computation_error",
                    f"Payroll calculation failed for {emp_label}: {_ctc_err}",
                    salary_structure_id=ss.id,
                    salary_assignment_id=assignment.id if assignment else None,
                    working_days=working_days,
                    payable_days=payable_days,
                    present_days=present_days,
                    leave_days=leave_days,
                    lop_days=lop_days,
                    holiday_days=holiday_days,
                )
                errors += 1
                continue
            base_gross      = breakup.gross_monthly
            base_basic      = breakup.basic
            base_hra        = breakup.hra
            base_da         = breakup.da
            base_special    = breakup.special_allowance
            base_conveyance = breakup.transport_allowance
            base_lta        = breakup.lta
            base_allowances = (
                breakup.special_allowance
                + breakup.transport_allowance
                + breakup.medical_allowance
            )
            base_pf_emp     = breakup.pf_employee
            base_pf_er      = breakup.pf_employer
            base_esi_emp    = breakup.esi_employee
            base_esi_er     = breakup.esi_employer
            base_pt         = breakup.professional_tax
            base_tds        = breakup.tds
            base_deductions = _sum_money(
                breakup.pf_employee, breakup.esi_employee,
                breakup.professional_tax, breakup.tds,
            )
            log.info(
                "[Run %d] Employee %d (%s): CTC-only salary master — "
                "computed from annual_ctc=₹%.2f → gross=₹%.2f, basic=₹%.2f, "
                "hra=₹%.2f, pf_emp=₹%.2f, pt=₹%.2f, tds=₹%.2f, net=₹%.2f",
                run.id, emp.id, emp_label,
                annual_ctc, base_gross, base_basic, base_hra,
                base_pf_emp, base_pt, base_tds,
                _subtract_money(base_gross, base_deductions),
            )
        else:
            base_gross      = ss.gross_monthly
            base_basic      = ss.basic
            base_hra        = ss.hra
            base_da         = ss.da
            base_special    = ss.special_allowance
            base_conveyance = ss.transport_allowance
            # LTA is stored in other_allowances (no dedicated lta column in salary_structures)
            base_lta        = ss.other_allowances
            base_allowances = (
                ss.special_allowance + ss.transport_allowance
                + ss.medical_allowance
                # other_allowances (LTA) is tracked separately as base_lta
            )
            base_pf_emp     = ss.pf_employee
            base_pf_er      = ss.pf_employer
            base_esi_emp    = ss.esi_employee
            base_esi_er     = ss.esi_employer
            base_pt         = ss.professional_tax
            base_tds        = ss.tds
            base_deductions = _sum_money(ss.pf_employee, ss.esi_employee, ss.professional_tax, ss.tds)

        # ── PF Policy: Fixed at ₹1,800 — LOP does not reduce PF ──
        _FIXED_PF = 1800.0
        if base_pf_emp > 0:
            base_pf_emp = _FIXED_PF
        if base_pf_er > 0:
            base_pf_er = _FIXED_PF
        base_deductions = _sum_money(base_pf_emp, base_esi_emp, base_pt, base_tds)

        # ── ESI ceiling guard ──
        # If gross exceeds the statutory ESI wage ceiling, ESI is not applicable.
        try:
            esi_ceiling = _stat_svc.get_active_settings(db).esi_wage_ceiling or 21000.0
        except Exception:
            esi_ceiling = 21000.0
        if base_gross > esi_ceiling:
            base_esi_emp = 0.0
            base_esi_er  = 0.0
            base_deductions = _sum_money(base_pf_emp, base_pt, base_tds)

        original_base_gross = base_gross
        lop_deduction = 0.0

        # ── Step 6: Apply LOP (Loss of Pay) ──
        # Guard: lop_days can never exceed working_days (data-entry safeguard)
        lop_days = min(lop_days, working_days)
        if lop_days > 0 and working_days > 0:
            pay_ratio        = (working_days - lop_days) / working_days
            base_gross       = round(base_gross       * pay_ratio, 2)
            base_basic       = round(base_basic       * pay_ratio, 2)
            base_hra         = round(base_hra         * pay_ratio, 2)
            base_da          = round(base_da          * pay_ratio, 2)
            base_lta         = round(base_lta         * pay_ratio, 2)
            base_special     = round(base_special     * pay_ratio, 2)
            base_conveyance  = round(base_conveyance  * pay_ratio, 2)
            base_allowances  = round(base_allowances  * pay_ratio, 2)
            # PF (employee + employer) is NOT scaled — fixed at ₹1,800 per policy
            base_esi_emp     = round(base_esi_emp     * pay_ratio, 2)
            base_esi_er      = round(base_esi_er      * pay_ratio, 2)
            base_tds         = round(base_tds         * pay_ratio, 2)
            lop_deduction    = round(original_base_gross - base_gross, 2)
            # PT is NOT scaled for LOP in most Indian states (fixed per month)
            # Employer PF is NOT in employee deductions — only employee-side deductions affect net_pay
            base_deductions  = _sum_money(base_pf_emp, base_esi_emp, base_pt, base_tds)
            log.info(
                "[Run %d] Employee %d (%s): LOP applied — lop=%d, working=%d, "
                "pay_ratio=%.4f, gross ₹%.2f → ₹%.2f",
                run.id, emp.id, emp_label,
                lop_days, working_days, pay_ratio, original_base_gross, base_gross,
            )

        # ── Step 7: Apply one-time adjustments + recalculate TDS for taxable income ──
        tds_before = base_tds

        # If taxable additions exist, recompute TDS on the adjusted annual gross.
        # The bonus/incentive/arrears is a one-time receipt, so add it ONCE to the
        # annualised base (not multiplied by 12) to avoid inflating the tax slab.
        if taxable_additions > 0:
            adjusted_annual_for_tds = (base_gross * 12) + taxable_additions
            try:
                base_tds = _stat_svc.compute_monthly_tds_for_adjusted_gross(
                    db, emp.id, adjusted_annual_for_tds
                )
            except Exception as _tds_adj_err:
                log.warning(
                    "[Run %d] Employee %d (%s): TDS recompute for taxable adjustments "
                    "failed — keeping base TDS. Error: %s",
                    run.id, emp.id, emp_label, _tds_adj_err,
                )
            # Rebuild base_deductions with the updated TDS (keeps PF/ESI/PT intact)
            base_deductions = _sum_money(base_pf_emp, base_esi_emp, base_pt, base_tds)

        final_gross      = round(base_gross + additions, 2)
        final_deductions = _sum_money(base_deductions, deduction_adj)
        final_net        = _subtract_money(final_gross, final_deductions)
        if final_gross <= 0.0 or final_net <= 0.0:
            _add_generation_error(
                db,
                run,
                emp,
                "invalid_net_pay",
                (
                    f"Net pay is invalid for {emp_label}: gross={final_gross}, "
                    f"deductions={final_deductions}, net={final_net}."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
                working_days=working_days,
                payable_days=payable_days,
                present_days=present_days,
                leave_days=leave_days,
                lop_days=lop_days,
                holiday_days=holiday_days,
            )
            errors += 1
            continue
        row_lta = _sum_money(base_lta, lta_amount)
        balanced_special = _balanced_special_allowance(
            final_gross,
            basic_pay=base_basic,
            hra=base_hra,
            da=base_da,
            lta=row_lta,
            conveyance=base_conveyance,
            bonus=bonus_amount,
            variable_pay=variable_pay_amount,
            overtime_amount=overtime_amount,
        )
        if balanced_special < -0.01:
            _add_generation_error(
                db,
                run,
                emp,
                "earnings_reconciliation_mismatch",
                (
                    f"Earnings components exceed gross pay for {emp_label}: gross={final_gross}, "
                    f"basic={base_basic}, hra={base_hra}, da={base_da}, lta={row_lta}, "
                    f"transport={base_conveyance}, bonus={bonus_amount}, "
                    f"variable_pay={variable_pay_amount}, overtime={overtime_amount}."
                ),
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
                working_days=working_days,
                payable_days=payable_days,
                present_days=present_days,
                leave_days=leave_days,
                lop_days=lop_days,
                holiday_days=holiday_days,
            )
            errors += 1
            continue
        base_special = max(balanced_special, 0.0)
        variance_flag, variance_reason = _detect_variance(
            db=db,
            employee_id=emp.id,
            run=run,
            gross_earnings=final_gross,
            total_deductions=final_deductions,
            net_pay=final_net,
            payable_days=payable_days,
            lop_days=lop_days,
            salary_structure=ss,
            attendance_fallback_reason=attendance.get("fallback_reason"),
        )

        log.info(
            "[PAYROLL] employee_id=%d | payroll_run_id=%d | salary_structure_id=%s | "
            "annual_ctc=%.2f | "
            "basic_monthly=%.2f | hra_monthly=%.2f | lta_monthly=%.2f | "
            "transport_monthly=%.2f | special_allowance_monthly=%.2f | "
            "gross_monthly=%.2f%s | "
            "employee_pf=%.2f | employer_pf=%.2f | esi=%.2f | pt=%.2f | "
            "monthly_tds=%.2f (was %.2f) | "
            "net_monthly=%.2f | "
            "additions=%.2f deduction_adj=%.2f final_gross=%.2f final_net=%.2f",
            emp.id, run.id, ss.id,
            (ss.annual_ctc or 0.0),
            base_basic, base_hra, base_lta,
            base_conveyance, base_special,
            base_gross, " [PRORATED]" if is_mid_month else "",
            base_pf_emp, base_pf_er, base_esi_emp, base_pt,
            base_tds, tds_before,
            _subtract_money(base_gross, base_deductions),
            additions, deduction_adj, final_gross, final_net,
        )

        # ── Step 8: Create payroll row (duplicate-safe) ──
        existing_row = db.query(PayrollRunEmployee).filter_by(
            run_id=run.id, employee_id=emp.id
        ).first()
        if existing_row:
            log.warning(
                "[Run %d] Employee %d (%s): duplicate payroll row detected — skipping insert.",
                run.id, emp.id, emp_label,
            )
            _add_generation_error(
                db,
                run,
                emp,
                "duplicate_payroll_record",
                f"Duplicate payroll record exists for {emp_label} in run {run.id}.",
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
                working_days=working_days,
                payable_days=payable_days,
                present_days=present_days,
                leave_days=leave_days,
                lop_days=lop_days,
                holiday_days=holiday_days,
            )
            errors += 1
            continue

        row = PayrollRunEmployee(
            run_id=run.id,
            employee_id=emp.id,
            salary_structure_id=ss.id,   # ← immutable audit anchor
            salary_assignment_id=assignment.id if assignment else None,
            total_working_days=working_days,
            working_days=working_days,
            payable_days=payable_days,
            present_days=present_days,
            leave_days=leave_days,
            lop_days=lop_days,
            holiday_days=holiday_days,
            gross_earnings=final_gross,
            basic_pay=base_basic,
            hra=base_hra,
            da=base_da,
            special_allowance=base_special,
            lta=row_lta,
            conveyance=base_conveyance,
            bonus=bonus_amount,
            variable_pay=variable_pay_amount,
            overtime_amount=overtime_amount,
            employee_pf=base_pf_emp,
            employer_pf=base_pf_er,
            employee_esi=base_esi_emp,
            employer_esi=base_esi_er,
            professional_tax=base_pt,
            tds=base_tds,
            lop_deduction=lop_deduction,
            other_deductions=deduction_adj,
            total_deductions=final_deductions,
            net_pay=final_net,
            record_status="COMPUTED",
            variance_flag=variance_flag,
            variance_reason=variance_reason,
            migration_completed=True,
        )
        row.sync_legacy_amount_columns()
        try:
            # Use a nested transaction (savepoint) so a flush failure for one
            # employee only rolls back that employee's insert — all previously
            # inserted employees remain intact in the outer transaction.
            savepoint = db.begin_nested()
            db.add(row)
            db.flush()
            savepoint.commit()
        except Exception as _row_err:
            savepoint.rollback()
            log.error(
                "[Run %d] Employee %d (%s): failed to insert payroll row — %s",
                run.id, emp.id, emp_label, _row_err,
            )
            _add_generation_error(
                db,
                run,
                emp,
                "computation_error",
                f"Payroll row insert failed: {_row_err}",
                salary_structure_id=ss.id,
                salary_assignment_id=assignment.id if assignment else None,
                working_days=working_days,
                payable_days=payable_days,
                present_days=present_days,
                leave_days=leave_days,
                lop_days=lop_days,
                holiday_days=holiday_days,
            )
            errors += 1
            continue

        try:
            _save_statutory_deductions(db, row)
        except Exception as _stat_err:
            log.warning(
                "[Run %d] Employee %d (%s): statutory deduction save failed — %s",
                run.id, emp.id, emp_label, _stat_err,
            )
        generated += 1

        # Audit log — includes salary_structure_id and adjustment details for traceability
        _log_audit(db, run.id, emp.id, "computed", json.dumps({
            "salary_structure_id":   ss.id,
            "salary_assignment_id":  assignment.id if assignment else None,
            "effective_from":        str(ss.effective_from),
            "working_days":          working_days,
            "payable_days":          payable_days,
            "lop_days":              lop_days,
            "overtime_hours":        overtime_hours,
            "is_prorated":           is_mid_month,
            "proration_hike_date":   proration.get("hike_effective_from") if is_mid_month else None,
            "proration_old_days":    proration.get("old_salary_days") if is_mid_month else None,
            "proration_new_days":    proration.get("new_salary_days") if is_mid_month else None,
            "base_gross":            base_gross,
            "additions":             additions,
            "taxable_additions":     taxable_additions,
            "non_taxable_additions": non_taxable_additions,
            "deduction_adj":         deduction_adj,
            "final_gross":           final_gross,
            "basic":                 base_basic,
            "hra":                   base_hra,
            "tds_before":            tds_before,
            "tds_after":             base_tds,
            "final_deductions":      final_deductions,
            "net":                   final_net,
            "attendance_finalized":   attendance["is_finalized"],
            "attendance_fallback":    attendance["fallback_used"],
            "variance_flag":          variance_flag,
            "variance_reason":        variance_reason,
        }))

    db.flush()
    _refresh_run_totals(db, run)
    ensure_payroll_records_exist(db, run.id)

    log.info(
        "[Run %d] Generation complete — %d rows generated, %d errors/warnings.",
        run.id, generated, errors,
    )


# ─── Payslip generation ───────────────────────────────────────────────────────

def _generate_payslip_records(db: Session, run: PayrollRun, actor: Employee) -> None:
    """Create Payslip rows for every non-error employee in the run."""
    normalize_payroll_run_period(run)
    ensure_payroll_records_exist(db, run.id)
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    month, year, _ = _period_month_year(run)
    month_label = payroll_month_label(run.pay_period_start)
    now = datetime.utcnow()
    for row in rows:
        if row.has_error:
            continue
        existing = db.query(Payslip).filter_by(run_id=run.id, employee_id=row.employee_id).first()
        if existing:
            normalize_payslip_period(existing)
            row.payslip_generated = True
            row.payslip_url = existing.file_url or existing.pdf_path
            continue
        payslip_number = f"PS-{year}{month:02d}-{run.id:04d}-{row.employee_id:04d}"
        slip = Payslip(
            payroll_record_id=row.id,
            run_id=run.id,
            employee_id=row.employee_id,
            month_label=month_label,
            month=month,
            year=year,
            payslip_number=payslip_number,
            pay_period_start=run.pay_period_start,
            pay_period_end=run.pay_period_end,
            gross_salary=row.gross_earnings,
            total_deductions=row.total_deductions,
            net_salary=row.net_pay,
            status="GENERATED",
            generated_by_id=actor.id if actor else None,
            generated_at=now,
            is_published=False,
        )
        db.add(slip)
        row.payslip_generated = True
        row.payslip_url = slip.file_url or slip.pdf_path
        _log_audit(db, run.id, row.employee_id, "payslip_generated", None)
    db.flush()


def _refresh_run_totals(db: Session, run: PayrollRun) -> None:
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    run.total_employees = len(rows)
    run.total_gross     = round(sum(r.gross_earnings     for r in rows), 2)
    run.total_deductions= round(sum(r.total_deductions   for r in rows), 2)
    run.total_net       = round(sum(r.net_pay            for r in rows), 2)
    run.total_pf        = round(sum(r.employee_pf + r.employer_pf for r in rows), 2)
    run.total_esi       = round(sum(r.employee_esi + r.employer_esi for r in rows), 2)
    run.total_tds       = round(sum(r.tds                for r in rows), 2)
    run.total_pt        = round(sum(r.professional_tax   for r in rows), 2)


def _log_action(
    db: Session,
    run: PayrollRun,
    actor: Employee,
    action: str,
    from_status: Optional[str],
    to_status: Optional[str],
    remarks: Optional[str] = None,
) -> None:
    entry = PayrollApproval(
        run_id=run.id,
        actor_id=actor.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        remarks=remarks,
    )
    db.add(entry)


def _log_audit(
    db: Session, run_id: int, employee_id: int, event: str, details: Optional[str] = None
) -> None:
    log_entry = PayrollAuditLog(
        run_id=run_id,
        employee_id=employee_id,
        event=event,
        details=details,
    )
    db.add(log_entry)


# ─── Payroll Adjustments ─────────────────────────────────────────────────────

def create_adjustment(db: Session, data: dict, actor: Employee) -> PayrollAdjustment:
    run = db.query(PayrollRun).filter(PayrollRun.id == data["run_id"]).first()
    if run and (run.payroll_locked or run.status in _LOCKED_STATUSES or run.status == "approved"):
        raise ValueError("Payroll is locked for this run; unlock workflow is required before changes")
    # Normalize direction and type so comparisons in _generate_employee_rows always work.
    raw_direction = str(data["direction"]).strip().lower()
    if raw_direction not in ("addition", "deduction"):
        raise ValueError(
            f"Invalid adjustment direction '{data['direction']}'. "
            "Must be 'addition' or 'deduction'."
        )
    adj = PayrollAdjustment(
        run_id=data["run_id"],
        employee_id=data["employee_id"],
        adjustment_type=str(data["adjustment_type"]).strip().lower(),
        direction=raw_direction,
        amount=data["amount"],
        description=data.get("description"),
        is_taxable=data.get("is_taxable", True),
        approved_by_id=actor.id,
    )
    db.add(adj)
    db.commit()
    db.refresh(adj)
    log.info(
        "Adjustment created: run_id=%d employee_id=%d type=%s direction=%s "
        "amount=₹%.2f taxable=%s",
        adj.run_id, adj.employee_id, adj.adjustment_type,
        adj.direction, adj.amount, adj.is_taxable,
    )
    return adj


def list_adjustments(db: Session, run_id: int, employee_id: Optional[int] = None) -> list[PayrollAdjustment]:
    q = db.query(PayrollAdjustment).filter_by(run_id=run_id)
    if employee_id:
        q = q.filter_by(employee_id=employee_id)
    return q.all()


def delete_adjustment(db: Session, adj_id: int) -> bool:
    adj = db.query(PayrollAdjustment).filter(PayrollAdjustment.id == adj_id).first()
    if not adj:
        return False
    run = db.query(PayrollRun).filter(PayrollRun.id == adj.run_id).first()
    if run and (run.payroll_locked or run.status in _LOCKED_STATUSES or run.status == "approved"):
        raise ValueError("Payroll is locked for this run; unlock workflow is required before changes")
    db.delete(adj)
    db.commit()
    return True


# ─── Payroll Errors ───────────────────────────────────────────────────────────

def create_payroll_error(db: Session, data: dict, actor: Employee) -> PayrollError:
    run = db.query(PayrollRun).filter(PayrollRun.id == data["run_id"]).first()
    _ensure_editable_run(run)
    err = PayrollError(
        run_id=data["run_id"],
        employee_id=data["employee_id"],
        error_type=data["error_type"],
        description=data["description"],
        severity=data.get("severity", "warning"),
    )
    db.add(err)
    row = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=data["run_id"], employee_id=data["employee_id"])
        .first()
    )
    if row:
        row.has_error = True
    db.commit()
    db.refresh(err)
    return err


def resolve_payroll_error(
    db: Session, error_id: int, resolution_note: Optional[str], actor: Employee
) -> PayrollError:
    err = db.query(PayrollError).filter(PayrollError.id == error_id).first()
    if not err:
        raise ValueError(f"Error {error_id} not found")
    run = db.query(PayrollRun).filter(PayrollRun.id == err.run_id).first()
    _ensure_editable_run(run)
    err.is_resolved = True
    err.resolved_by_id = actor.id
    err.resolved_at = datetime.utcnow()
    err.resolution_note = resolution_note
    open_errors = (
        db.query(PayrollError)
        .filter_by(run_id=err.run_id, employee_id=err.employee_id, is_resolved=False)
        .count()
    )
    if open_errors <= 0:
        row = (
            db.query(PayrollRunEmployee)
            .filter_by(run_id=err.run_id, employee_id=err.employee_id)
            .first()
        )
        if row:
            row.has_error = False
    db.commit()
    db.refresh(err)
    return err


def list_payroll_errors(
    db: Session, run_id: int, resolved: Optional[bool] = None
) -> list[PayrollError]:
    q = db.query(PayrollError).filter(PayrollError.run_id == run_id)
    if resolved is not None:
        q = q.filter(PayrollError.is_resolved == resolved)
    return q.order_by(PayrollError.severity.desc()).all()


def _approval_status_summary(db: Session, run_id: int) -> dict[str, str]:
    summary = {
        "FINANCE_REVIEW": "PENDING",
        "FINANCE_HEAD_APPROVAL": "PENDING",
        "HR_CONFIRMATION": "PENDING",
    }
    rows = (
        db.query(PayrollApproval)
        .filter(PayrollApproval.run_id == run_id, PayrollApproval.approval_level.isnot(None))
        .order_by(PayrollApproval.created_at.asc())
        .all()
    )
    for row in rows:
        summary[row.approval_level] = row.approval_status
    return summary


# ─── Dashboard Stats ─────────────────────────────────────────────────────────

def get_dashboard_stats(db: Session) -> dict:
    current_run = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.notin_(["disbursed", "closed", "cancelled"]))
        .order_by(PayrollRun.pay_period_start.desc())
        .first()
    )
    normalize_payroll_run_period(current_run)

    last_disbursed = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.in_(["approved", "disbursed", "closed"]))
        .order_by(PayrollRun.pay_period_start.desc())
        .first()
    )
    normalize_payroll_run_period(last_disbursed)

    total_employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .count()
    )

    open_error_count = 0
    completion_pct = 0.0
    payslip_generated_count = 0
    payslip_published_count = 0
    variance_count = 0
    approval_status = None
    if current_run:
        open_error_count = (
            db.query(PayrollError)
            .filter_by(run_id=current_run.id, is_resolved=False)
            .count()
        )
        payslip_generated_count = db.query(Payslip).filter_by(run_id=current_run.id).count()
        payslip_published_count = db.query(Payslip).filter_by(
            run_id=current_run.id, is_published=True
        ).count()
        variance_count = visible_variance_count(db, current_run.id)
        approval_status = _approval_status_summary(db, current_run.id)
        if current_run.total_employees > 0:
            processed = (
                db.query(PayrollRunEmployee)
                .filter_by(run_id=current_run.id, is_locked=False, has_error=False)
                .count()
            )
            completion_pct = round(processed / current_run.total_employees * 100, 1)

    dept_summary = _build_dept_summary(db, current_run)

    return {
        "current_run": current_run,
        "total_payroll_runs": db.query(PayrollRun).count(),
        "pending_approval_count": (
            1 if current_run and current_run.status in ("under_review", "pending_head_approval")
            else 0
        ),
        "total_employees": total_employees,
        "total_gross": current_run.total_gross if current_run else 0.0,
        "total_deductions": current_run.total_deductions if current_run else 0.0,
        "total_net_pay": current_run.total_net if current_run else 0.0,
        "last_run_net": last_disbursed.total_net if last_disbursed else 0.0,
        "open_error_count": open_error_count,
        "attendance_frozen": (
            bool(current_run.attendance_locked or current_run.status not in ("draft",)) if current_run else False
        ),
        "payroll_locked": bool(current_run.payroll_locked) if current_run else False,
        "is_finalized": (
            bool(current_run.payroll_locked or current_run.status in ("payslip_generated", "published", "completed", "closed"))
            if current_run else False
        ),
        "is_published": bool(current_run and current_run.status in ("published", "completed", "closed")),
        "approval_status": approval_status,
        "finance_review_status": approval_status.get("FINANCE_REVIEW") if approval_status else None,
        "payslip_generated_count": payslip_generated_count,
        "payslip_published_count": payslip_published_count,
        "variance_count": variance_count,
        "payroll_completion_pct": completion_pct,
        "department_summary": dept_summary,
    }


def _build_dept_summary(db: Session, run: Optional[PayrollRun]) -> list[dict]:
    if not run or run.status == "draft":
        return []

    rows = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=run.id)
        .options(joinedload(PayrollRunEmployee.employee))
        .all()
    )

    dept_map: dict[str, dict] = {}
    for row in rows:
        emp = row.employee
        dept_name = "Unknown"
        if emp and emp.department:
            dept_name = emp.department.name
        if dept_name not in dept_map:
            dept_map[dept_name] = {
                "department": dept_name,
                "headcount": 0,
                "gross": 0.0,
                "deductions": 0.0,
                "net": 0.0,
            }
        dept_map[dept_name]["headcount"]   += 1
        dept_map[dept_name]["gross"]       += row.gross_earnings
        dept_map[dept_name]["deductions"]  += row.total_deductions
        dept_map[dept_name]["net"]         += row.net_pay

    result = []
    for item in dept_map.values():
        item["variance_pct"] = 0.0
        result.append(item)
    return result


# ─── Run Employee helpers ─────────────────────────────────────────────────────

def list_run_employees(db: Session, run_id: int) -> list[PayrollRunEmployee]:
    return (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=run_id)
        .options(joinedload(PayrollRunEmployee.employee))
        .all()
    )


def mark_payslip_generated(db: Session, run_id: int, employee_id: int) -> bool:
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        return False
    ensure_payroll_records_exist(db, run_id)
    row = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=run_id, employee_id=employee_id)
        .first()
    )
    if row:
        if not is_final_approved_run(run):
            raise ValueError("Finance Head final approval is required before generating payslips.")
        if run:
            normalize_payroll_run_period(run)
            month, year, _ = _period_month_year(run)
            month_label = payroll_month_label(run.pay_period_start)
            slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()
            if not slip:
                slip = Payslip(
                    payroll_record_id=row.id,
                    run_id=run_id,
                    employee_id=employee_id,
                    month_label=month_label,
                    month=month,
                    year=year,
                    payslip_number=f"PS-{year}{month:02d}-{run_id:04d}-{employee_id:04d}",
                    pay_period_start=run.pay_period_start,
                    pay_period_end=run.pay_period_end,
                    gross_salary=row.gross_earnings,
                    total_deductions=row.total_deductions,
                    net_salary=row.net_pay,
                    status="GENERATED",
                    generated_at=datetime.utcnow(),
                    is_published=False,
                )
                db.add(slip)
            else:
                normalize_payslip_period(slip)
        row.payslip_generated = True
        db.commit()
        return True
    return False


# ─── Payslip helpers ──────────────────────────────────────────────────────────

def list_payslips(db: Session, run_id: Optional[int] = None, employee_id: Optional[int] = None) -> list[Payslip]:
    q = db.query(Payslip)
    if run_id:
        q = q.filter_by(run_id=run_id)
    if employee_id:
        q = q.filter_by(employee_id=employee_id)
    slips = q.order_by(Payslip.pay_period_start.desc()).all()
    return [normalize_payslip_period(slip) for slip in slips]


def publish_payslip(db: Session, payslip_id: int, actor: Employee) -> Payslip:
    slip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not slip:
        raise ValueError(f"Payslip {payslip_id} not found")
    run = db.query(PayrollRun).filter(PayrollRun.id == slip.run_id).first()
    was_published = bool(slip.is_published)
    if not run or not is_final_approved_run(run) or run.status not in _PUBLISH_READY_STATUSES:
        raise ValueError(
            "Payslips can be published only after they are generated following Finance Head final approval."
        )
    ensure_payroll_records_exist(db, run.id)
    slip.is_published = True
    slip.status = "PUBLISHED"
    slip.published_at = datetime.utcnow()
    if run:
        run.published_at = slip.published_at
        if run.status not in ("closed", "disbursed", "completed", "published"):
            run.status = "published"
    db.commit()
    db.refresh(slip)
    _log_audit(db, slip.run_id, slip.employee_id, "published")
    if run:
        if not run.payroll_locked:
            run.payroll_locked = True
            run.finalized_by_id = actor.id
            run.finalized_at = slip.published_at
            db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
                {"is_locked": True}, synchronize_session=False
            )
            _record_lock_history(db, run, "PAYROLL", "LOCK", actor, "Payslip published")
        else:
            _record_lock_history(db, run, "PAYSLIP", "LOCK", actor, "Payslip published")
    db.commit()
    if run and not was_published:
        _dispatch_payslip_published_notifications(db, run, [slip])
    return slip


def bulk_publish_payslips(
    db: Session,
    run_id: int,
    actor: Employee,
    *,
    send_notification_email: bool = True,
) -> int:
    """Publish all payslips for a run. Returns count published."""
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run or not is_final_approved_run(run) or run.status not in _PUBLISH_READY_STATUSES:
        raise ValueError(
            "Payslips can be published only after they are generated following Finance Head final approval."
        )
    ensure_payroll_records_exist(db, run_id)
    all_slips = db.query(Payslip).filter_by(run_id=run_id).all()
    if not all_slips:
        raise ValueError("Generate payslips before publishing to ESS.")
    slips = [slip for slip in all_slips if not slip.is_published]
    now = datetime.utcnow()
    count = 0
    published_slips: list[Payslip] = []
    for slip in slips:
        slip.is_published = True
        slip.status = "PUBLISHED"
        slip.published_at = now
        _log_audit(db, slip.run_id, slip.employee_id, "published")
        published_slips.append(slip)
        count += 1
    if run:
        if run.status not in ("closed", "disbursed", "completed", "published"):
            run.status = "published"
        run.published_at = now
        if not run.payroll_locked:
            run.payroll_locked = True
            run.finalized_by_id = actor.id
            run.finalized_at = now
            db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
                {"is_locked": True}, synchronize_session=False
            )
        _record_lock_history(db, run, "PAYSLIP", "LOCK", actor, "All payslips published")
    db.commit()
    if run and published_slips:
        _dispatch_payslip_published_notifications(
            db,
            run,
            published_slips,
            send_email=send_notification_email,
        )
    return count
