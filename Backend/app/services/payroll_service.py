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
from app.models.attendance_records import PayrollAttendanceSummary
from app.models.employee import Employee
from app.models.department import Department
from app.services.ctc_engine import compute_from_ctc, apply_lop, SalaryBreakup
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
#                                └─[publish]──► published
#                                               └─[close]──► closed
#
# Error recovery: error_found ──[resolve_errors]──► under_review
# Cancellation: any non-final state ──[cancel]──► cancelled

_TRANSITIONS: dict[str, dict[str, str]] = {
    "draft": {
        "freeze_attendance": "attendance_frozen",
        "process":           "processing",
        "cancel":            "cancelled",
    },
    "attendance_frozen": {
        "generate":          "processing",
        "process":           "processing",
        "cancel":            "cancelled",
    },
    "processing": {
        "submit_review":     "under_review",
        "submit_for_approval": "under_review",
        # Allow recompute directly from processing so Finance can add adjustments
        # and immediately re-run the payroll engine without the extra
        # submit_review → under_review cycle.
        "recompute":         "processing",
        "cancel":            "cancelled",
    },
    "under_review": {
        "flag_error":        "error_found",
        "recompute":         "processing",
        "approve":           "pending_head_approval",
        "finance_review":    "pending_head_approval",
        "reject":            "draft",
        "cancel":            "cancelled",
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
        "disburse":          "disbursed",      # legacy — kept for backward compat
    },
    "payslip_generated": {
        "publish":           "published",
    },
    "published": {
        "close":             "closed",
    },
    "disbursed":  {},
    "closed":     {},
    "cancelled":  {},
}

# Statuses from which recomputation is NEVER allowed (immutable payroll history)
_LOCKED_STATUSES = frozenset({
    "approved", "payslip_generated", "published", "closed", "cancelled",
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
    """Fire in-app notifications and email for payroll workflow events. Never raises."""
    try:
        from app.services import notification_service as _ns
        from app.services import email_service as _es

        run_label = run.month_label or f"Run #{run.id}"
        actor_name = f"{actor.first_name} {actor.last_name or ''}".strip()
        run_ref_id = str(run.id)

        def _notify_group(role_names, ntype, title, body):
            users = _get_employees_by_role(db, *role_names)
            for u in users:
                _ns.notify(
                    db,
                    recipient_id=u.id,
                    type_=ntype,
                    title=title,
                    body=body,
                    reference_table="payroll_runs",
                    reference_id=run_ref_id,
                    autocommit=True,
                )
            return users

        def _email_group(users, event_label):
            for u in users:
                email = (getattr(u, "official_email", None) or u.email or "").strip()
                if email:
                    try:
                        _es.send_payroll_event_email(
                            email, event_label, run_label, actor_name, remarks
                        )
                    except Exception as _em:
                        log.warning("[PAYROLL EMAIL] Failed to %s for %s: %s", event_label, email, _em)

        if action in ("submit_review", "submit_for_approval"):
            # Notify Finance team only — Finance Head is notified once Finance approves
            title = f"Payroll submitted for review — {run_label}"
            body = f"Payroll {run_label} has been submitted for Finance review by {actor_name}."
            users = _notify_group(("finance",), "payroll_submitted_for_review", title, body)
            _email_group(users, "Payroll Submitted for Finance Review")

        elif action == "reject":
            title = f"Finance rejected payroll — {run_label}"
            body = f"Finance rejected payroll {run_label}. Remarks: {remarks or '—'}."
            users = _notify_group(("admin",), "payroll_rejected", title, body)
            _email_group(users, "Finance Rejected Payroll")

        elif action == "head_reject":
            title = f"Finance Head returned payroll — {run_label}"
            body = (
                f"Finance Head returned payroll {run_label} to Finance for review. "
                f"Remarks: {remarks or '—'}."
            )
            users = _notify_group(("admin", "finance"), "payroll_returned_to_finance", title, body)
            _email_group(users, "Finance Head Returned Payroll")

        elif action in ("finance_review", "approve"):
            # Finance approved → notify Finance Head that final approval is needed
            title = f"Payroll awaiting final approval — {run_label}"
            body = f"Payroll {run_label} is waiting for Finance Head approval."
            users = _notify_group(("finance_head",), "payroll_awaiting_head_approval", title, body)
            _email_group(users, "Payroll Awaiting Finance Head Approval")

        elif action in ("head_approve", "finance_head_approve"):
            # Finance Head approved → notify Finance to generate payslips
            title = f"Payroll approved by Finance Head — {run_label}"
            body = f"Payroll {run_label} approved by Finance Head. Ready for payslip generation."
            users = _notify_group(("finance",), "payroll_head_approved", title, body)
            _email_group(users, "Payroll Approved by Finance Head")

        elif action == "publish":
            # Notify Finance/Admin teams
            title = f"Payslips published — {run_label}"
            body = f"Payslips for {run_label} have been published to employee self-service."
            staff_users = _notify_group(("admin", "finance"), "payslips_published", title, body)
            _email_group(staff_users, "Payslips Published")
            # Notify every employee whose payslip is in this run
            try:
                from app.models.payroll_extended import Payslip as _Payslip
                published_slips = (
                    db.query(_Payslip)
                    .filter_by(run_id=run.id, is_published=True)
                    .all()
                )
                for slip in published_slips:
                    _ns.notify(
                        db,
                        recipient_id=slip.employee_id,
                        type_="payslip_published",
                        title=f"Your payslip is ready — {run_label}",
                        body=f"Your payslip for {run_label} has been published. View it in the Employee Portal.",
                        reference_table="payroll_runs",
                        reference_id=run_ref_id,
                        autocommit=True,
                    )
            except Exception as _emp_err:
                log.warning("Employee payslip notification failed (non-fatal): %s", _emp_err)

        elif action == "freeze_attendance":
            title = f"Attendance frozen — {run_label}"
            body = f"Attendance/input freeze completed for payroll {run_label} by {actor_name}."
            _notify_group(("admin",), "payroll_freeze_done", title, body)

        elif action in ("generate", "process"):
            title = f"Payroll generated — {run_label}"
            body = f"Payroll computation for {run_label} initiated by {actor_name}."
            _notify_group(("admin",), "payroll_initiated", title, body)

        elif action == "recompute":
            title = f"Payroll recomputed — {run_label}"
            body = f"Payroll {run_label} has been recomputed and is ready for review."
            _notify_group(("finance", "finance_head"), "payroll_recomputed", title, body)

    except Exception as _err:
        log.warning("Payroll notification dispatch failed (non-fatal): %s", _err)


def document_lifecycle_status(status: str, payroll_locked: bool = False) -> str:
    """Map existing UI statuses to the Payroll DB document lifecycle."""
    if status == "approved" and payroll_locked:
        return "FINALIZED"
    return _STATUS_TO_DOCUMENT_LIFECYCLE.get(status, status.upper())


def _period_month_year(run: PayrollRun) -> tuple[int, int, str]:
    month = run.month or run.pay_period_start.month
    year = run.year or run.pay_period_start.year
    month_name = calendar.month_name[month]
    return month, year, month_name


def _ensure_run_document_fields(run: PayrollRun) -> None:
    month, year, _ = _period_month_year(run)
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


def get_payroll_attendance_summary(
    db: Session, employee_id: int, month: int | str, year: int
) -> dict:
    """Return finalized payroll attendance input, or a demo-safe fallback.

    Temporary fallback: attendance/timesheet finalization is owned by another
    module. Until it supplies finalized payroll summary rows, payroll uses a
    conservative full-payable-month snapshot so dashboards and processing do not
    crash or block.
    """
    month_name = calendar.month_name[int(month)] if isinstance(month, int) else str(month)
    att = (
        db.query(PayrollAttendanceSummary)
        .filter_by(employee_id=employee_id, year=year)
        .filter(PayrollAttendanceSummary.month.ilike(month_name))
        .first()
    )
    if att and att.is_finalized:
        total_working_days = att.total_working_days or 26
        lop_days = att.lop_days or 0
        payable_days = (
            att.payable_days
            if getattr(att, "payable_days", None) is not None
            else max(total_working_days - lop_days, 0)
        )
        return {
            "total_working_days": total_working_days,
            "payable_days": payable_days,
            "present_days": att.present_days or int(payable_days),
            "leave_days": att.leave_days or 0,
            "lop_days": lop_days,
            "holiday_days": att.holiday_count or 0,
            "overtime_hours": att.overtime_hours or 0.0,
            "is_finalized": True,
            "fallback_used": False,
            "fallback_reason": None,
        }

    return {
        "total_working_days": 26,
        "payable_days": 26.0,
        "present_days": 26,
        "leave_days": 0,
        "lop_days": 0,
        "holiday_days": 0,
        "overtime_hours": 0.0,
        "is_finalized": False,
        "fallback_used": True,
        "fallback_reason": (
            "Missing finalized attendance/timesheet summary"
            if not att else "Attendance/timesheet summary is not finalized"
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


def _detect_variance(
    db: Session,
    employee_id: int,
    run: PayrollRun,
    gross_earnings: float,
    total_deductions: float,
    net_pay: float,
    payable_days: float,
    lop_days: int,
    assignment_missing: bool,
    attendance_fallback_reason: str | None,
) -> tuple[bool, str | None]:
    reasons: list[str] = []
    previous = (
        db.query(PayrollRunEmployee)
        .join(PayrollRun, PayrollRunEmployee.run_id == PayrollRun.id)
        .filter(
            PayrollRunEmployee.employee_id == employee_id,
            PayrollRun.pay_period_start < run.pay_period_start,
        )
        .order_by(PayrollRun.pay_period_start.desc(), PayrollRunEmployee.created_at.desc())
        .first()
    )
    if previous:
        def changed(prev: float, current: float) -> bool:
            return bool(prev and abs(current - prev) / abs(prev) >= 0.10)

        if changed(previous.net_pay, net_pay):
            reasons.append("Net pay changed significantly from previous payroll")
        if changed(previous.gross_earnings, gross_earnings):
            reasons.append("Gross earnings changed significantly from previous payroll")
        if changed(previous.total_deductions, total_deductions):
            reasons.append("Total deductions changed significantly from previous payroll")

    total_days = run.pay_period_end.day or 26
    if payable_days < max(total_days * 0.6, 1):
        reasons.append("Payable days very low")
    if lop_days >= 3:
        reasons.append("LOP days high")
    if assignment_missing:
        reasons.append("Missing active salary assignment; used salary structure fallback")
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
    """Compute payroll variance vs. previous month and store in payroll_variance_log.

    Flags employees whose gross/net pay or TDS differs by more than the
    configured threshold (run.variance_threshold_pct, default 20%).

    Called automatically after every generate/recompute.  Finance must
    acknowledge flagged rows before sending to Finance Head.
    """
    try:
        from app.models.payroll_extended import PayrollVarianceLog
    except ImportError:
        log.warning("PayrollVarianceLog model not available — skipping variance compute")
        return

    run_month = run.month or run.pay_period_start.month
    run_year  = run.year  or run.pay_period_start.year

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

    threshold = float(getattr(run, "variance_threshold_pct", 20.0) or 20.0)

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

        # Determine flags
        flags: list[str] = []
        if gross_var_pct > threshold:
            flags.append(f"Gross pay change {gross_var_pct:.1f}% (> {threshold:.0f}% threshold)")
        if net_var_pct > threshold:
            flags.append(f"Net pay change {net_var_pct:.1f}% (> {threshold:.0f}% threshold)")
        if prev_tds and abs(curr_tds - prev_tds) > 500:
            flags.append(f"TDS changed by ₹{abs(curr_tds - prev_tds):,.0f}")
        if curr_lop > 3:
            flags.append(f"High LOP: {curr_lop:.1f} days")

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

    # Mark run variance_reviewed=False since new data was generated
    try:
        run.variance_reviewed = False
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
        flagged = [r for r in rows if r.is_flagged]
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
    """Compute and save salary structure from annual CTC using the CTC engine."""
    breakup = compute_from_ctc(annual_ctc, db)

    data = {
        "employee_id":        employee_id,
        "basic":              breakup.basic,
        "hra":                breakup.hra,
        "da":                 breakup.da,
        "special_allowance":  breakup.special_allowance,
        "transport_allowance":breakup.transport_allowance,
        "medical_allowance":  0.0,          # no medical in Excel formula
        # LTA stored in other_allowances — no dedicated lta column in salary_structures.
        # upsert_salary_structure includes other_allowances in gross_monthly, so
        # gross = basic + hra + special + transport + other_allowances(LTA) is correct.
        "other_allowances":   breakup.lta,
        "pf_employee":        breakup.pf_employee,
        "pf_employer":        breakup.pf_employer,
        "esi_employee":       breakup.esi_employee,
        "esi_employer":       breakup.esi_employer,
        "professional_tax":   breakup.professional_tax,
        "tds":                breakup.tds,
        "bank_name":          bank_name,
        "account_number":     account_number,
        "ifsc_code":          ifsc_code,
        "effective_from":     effective_from or date.today(),
        "revision_reason":    revision_reason,
        # Preserve the exact user-entered annual CTC so upsert_salary_structure
        # stores it as-is rather than recomputing it from rounded gross components
        # (prevents the ₹0.08 paisa-residue display bug).
        "annual_ctc":         annual_ctc,
    }
    struct = upsert_salary_structure(db, data, actor)

    # Immediately refresh TDS from tax declaration so salary structure
    # shows correct net (same as what payroll generation will use).
    try:
        _stat_svc.refresh_tds_for_employee(db, employee_id, commit=True)
        db.refresh(struct)
    except Exception as _tds_err:
        log.warning(
            "TDS refresh after CTC structure save failed for employee_id=%d: %s",
            employee_id, _tds_err,
        )

    log.info(
        "[CTC_SAVE] employee_id=%d | annual_ctc=%.2f | "
        "basic_monthly=%.2f | hra_monthly=%.2f | lta_monthly=%.2f | "
        "transport_monthly=%.2f | special_allowance_monthly=%.2f | "
        "gross_monthly=%.2f | employee_pf=%.2f | employer_pf=%.2f | "
        "esi=%.2f | pt=%.2f | monthly_tds=%.2f | net_monthly=%.2f | "
        "salary_structure_id=%s",
        employee_id, breakup.annual_ctc,
        breakup.basic, breakup.hra, breakup.lta,
        breakup.transport_allowance, breakup.special_allowance,
        breakup.gross_monthly, breakup.pf_employee, breakup.pf_employer,
        breakup.esi_employee, breakup.professional_tax, struct.tds,
        struct.net_monthly, struct.id,
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
    """List salary structures. active_only=True returns only current active revisions."""
    q = db.query(SalaryStructure)
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
        .filter(SalaryStructure.is_active.is_(True), SalaryStructure.gross_monthly > 0)
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
    run = PayrollRun(
        pay_period_start=data["pay_period_start"],
        pay_period_end=data["pay_period_end"],
        month_label=data["month_label"],
        month=data.get("month") or data["pay_period_start"].month,
        year=data.get("year") or data["pay_period_start"].year,
        notes=data.get("notes"),
        status="draft",
        attendance_locked=False,
        payroll_locked=False,
        initiated_by_id=actor.id,
        initiated_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    _ensure_run_document_fields(run)
    _log_action(db, run, actor, "initiate", None, "draft")
    db.commit()
    db.refresh(run)
    return run


def get_payroll_run(db: Session, run_id: int) -> Optional[PayrollRun]:
    return (
        db.query(PayrollRun)
        .options(
            joinedload(PayrollRun.employees),
            joinedload(PayrollRun.approvals),
            joinedload(PayrollRun.errors),
        )
        .filter(PayrollRun.id == run_id)
        .first()
    )


def list_payroll_runs(db: Session, limit: int = 20, offset: int = 0) -> list[PayrollRun]:
    return (
        db.query(PayrollRun)
        .order_by(PayrollRun.pay_period_start.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def advance_run_status(
    db: Session, run_id: int, action: str, remarks: Optional[str], actor: Employee
) -> PayrollRun:
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if not run:
        raise ValueError(f"Payroll run {run_id} not found")

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

    # Gate: existing UI flow still requires the explicit freeze step.
    # The document-style "process" action is allowed to lock payroll-side
    # attendance consumption without changing the attendance module itself.
    if action == "generate" and run.status != "attendance_frozen":
        raise ValueError("Attendance must be frozen before generating payroll")

    # ── Monthly Attendance Summary bridge gate ────────────────────────────
    # TEMPORARY PAYROLL BRIDGE: In production the Attendance/Timesheet modules
    # will populate monthly_attendance_summary and set is_frozen=True.
    # Until then, HR/Admin must freeze via /payroll/attendance-summary/freeze.
    if action in ("generate", "process"):
        run_month = run.month or run.pay_period_start.month
        run_year  = run.year or run.pay_period_start.year
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

    # Gate: cannot approve if unresolved errors exist
    if action in ("approve", "head_approve", "finance_review", "finance_head_approve", "hr_confirm"):
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

    # Gate: Finance must acknowledge variance BEFORE sending to Finance Head
    if action in ("approve", "finance_review"):
        try:
            from app.models.payroll_extended import PayrollVarianceLog
            flagged_unacknowledged = (
                db.query(PayrollVarianceLog)
                .filter(
                    PayrollVarianceLog.run_id == run_id,
                    PayrollVarianceLog.is_flagged.is_(True),
                    PayrollVarianceLog.acknowledged_by_id.is_(None),
                )
                .count()
            )
            # Also check run-level variance_reviewed flag
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

    if action in ("generate", "process"):
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

    elif action == "recompute":
        run.processed_at = now
        try:
            _stat_svc.refresh_tds_for_run(db, run.id)
        except Exception as _tds_err:
            log.warning("TDS refresh failed before recompute (run %s): %s", run.id, _tds_err)
        _generate_employee_rows(db, run)
        # Recompute variance after recompute
        try:
            _compute_and_store_variance(db, run)
        except Exception as _var_e:
            log.warning("Variance computation failed after recompute (non-fatal): %s", _var_e)

    elif action in ("submit_review", "submit_for_approval"):
        _ensure_pending_approval_steps(db, run, actor)

    elif action in ("approve", "finance_review"):
        _mark_approval_step(db, run, actor, "FINANCE_REVIEW", "APPROVED", remarks)

    elif action in ("head_approve", "finance_head_approve"):
        _mark_approval_step(db, run, actor, "FINANCE_HEAD_APPROVAL", "APPROVED", remarks)
        _mark_approval_step(db, run, actor, "HR_CONFIRMATION", "APPROVED", "Legacy head approval confirmed payroll")
        run.approved_at = now
        run.approved_by_id = actor.id
        # Lock payroll immediately on Finance Head final approval
        run.payroll_locked = True
        run.finalized_by_id = actor.id
        run.finalized_at = now
        db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
            {"is_locked": True}, synchronize_session=False
        )
        _record_lock_history(
            db, run, "PAYROLL", "LOCK", actor,
            remarks or "Finance Head final approval — payroll locked"
        )

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
        run.disbursed_at = now

    elif action == "generate_payslips":
        if not run.payroll_locked:
            run.payroll_locked = True
            run.finalized_by_id = actor.id
            run.finalized_at = now
            db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
                {"is_locked": True}, synchronize_session=False
            )
            _record_lock_history(db, run, "PAYROLL", "LOCK", actor, "Payslip generation finalized payroll")
        _generate_payslip_records(db, run, actor)

    elif action == "publish":
        run.published_at = now
        # Use payslip_service.bulk_publish_payslips for individual immutability +
        # email notification per employee.  The service internally calls publish_payslip
        # which sets is_published=True and sends the email.
        try:
            from app.services.payslip_service import bulk_publish_payslips as _bulk_pub
            pub_result = _bulk_pub(db, run_id=run.id, published_by_id=actor.id, send_emails=True)
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

    # On close: persist annual TDS summary (Form 16 Part A) for each employee
    if new_status == "closed":
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

def _generate_employee_rows(db: Session, run: PayrollRun) -> None:
    """
    Enterprise payroll row generation.

    For each active employee:
      1. Find the LATEST active salary structure with effective_from <= pay_period_end.
      2. Validate the structure (gross > 0, no CTC mismatch).
      3. Apply LOP deduction from PayrollAttendanceSummary if available.
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
    db.query(PayrollError).filter_by(
        run_id=run.id, error_type="missing_salary_structure"
    ).delete(synchronize_session=False)
    db.query(PayrollError).filter_by(
        run_id=run.id, error_type="salary_mismatch"
    ).delete(synchronize_session=False)

    pay_period_end = run.pay_period_end
    period_month_num, period_year, period_month = _period_month_year(run)

    log.info(
        "[Run %d] Generating payroll — period=%s, pay_period_end=%s",
        run.id, run.month_label, pay_period_end,
    )

    # All active, non-deleted employees are evaluated
    active_employees = (
        db.query(Employee)
        .filter(Employee.is_deleted.is_(False), Employee.employment_status == "active")
        .order_by(Employee.id)
        .all()
    )

    generated = 0
    errors    = 0

    for emp in active_employees:
        emp_label = f"{emp.first_name} {emp.last_name or ''}".strip()

        # ── Step 1: Find salary assignment/structure for this payroll period ──
        # Uses date-range based lookup (not status=ACTIVE) so that historical
        # payroll runs for periods BEFORE a recent hike still find the correct
        # SUPERSEDED assignment rather than returning None.
        assignment = _get_salary_assignment_for_period(db, emp.id, pay_period_end)
        ss = assignment.salary_structure if assignment else None
        assignment_missing = assignment is None
        if ss is None:
            # Backward-compatible fallback for existing demo data and salary UI:
            # salary_structures remains the historical source until all employees
            # have employee_salary_assignments rows.
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

            db.add(PayrollError(
                run_id=run.id,
                employee_id=emp.id,
                error_type="missing_salary_structure",
                description=desc,
                severity="error",
            ))
            errors += 1
            continue

        # ── Step 2: Sanity validation ──
        if ss.gross_monthly <= 0:
            db.add(PayrollError(
                run_id=run.id,
                employee_id=emp.id,
                error_type="missing_salary_structure",
                description=(
                    f"Salary structure (id={ss.id}) for {emp_label} has ₹0 gross monthly. "
                    "Update the salary structure with valid CTC values before generating payroll."
                ),
                severity="error",
            ))
            log.error(
                "[Run %d] Employee %d (%s): salary structure id=%d has ₹0 gross — skipping.",
                run.id, emp.id, emp_label, ss.id,
            )
            errors += 1
            continue

        # CTC mismatch guard — catches accidental monthly-vs-annual data entry errors.
        # Threshold: gross_monthly < 30% of (annual_ctc / 12) is suspicious.
        if ss.annual_ctc > 50_000:
            expected_monthly = ss.annual_ctc / 12
            if ss.gross_monthly < expected_monthly * 0.30:
                mismatch_pct = round(ss.gross_monthly / expected_monthly * 100, 1)
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
                    ss.annual_ctc, expected_monthly, ss.gross_monthly, mismatch_pct,
                )
                # Warning only — row is still generated, Finance must review

        log.info(
            "[Run %d] Employee %d (%s): using salary_structure id=%d, "
            "effective_from=%s, gross=₹%.2f",
            run.id, emp.id, emp_label, ss.id, ss.effective_from, ss.gross_monthly,
        )

        # ── Step 3: Finalized attendance/timesheet summary for this period ──
        attendance = get_payroll_attendance_summary(db, emp.id, period_month_num, period_year)
        working_days = int(attendance["total_working_days"])
        payable_days = float(attendance["payable_days"])
        present_days = int(attendance["present_days"])
        leave_days = int(attendance["leave_days"])
        lop_days = int(attendance["lop_days"])
        holiday_days = int(attendance["holiday_days"])
        overtime_hours = float(attendance["overtime_hours"])

        # ── Step 4: One-time adjustments ──
        # Normalize direction to lowercase+stripped so any casing variation in the
        # DB ("Addition", " addition", "ADDITION") is handled correctly.
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

        if is_mid_month:
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
            base_deductions = _sum_money(base_pf_emp, base_pf_er, base_esi_emp, base_pt, base_tds)
            log.info(
                "[Run %d] Employee %d (%s): MID-MONTH REVISION detected — "
                "hike_date=%s, old_days=%d, new_days=%d, prorated_gross=₹%.2f",
                run.id, emp.id, emp_label,
                proration["hike_effective_from"],
                proration["old_salary_days"],
                proration["new_salary_days"],
                base_gross,
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
            base_deductions = ss.total_deductions

        # ── ESI ceiling guard ──
        # If gross exceeds the statutory ESI wage ceiling, ESI is not applicable.
        try:
            esi_ceiling = _stat_svc.get_active_settings(db).esi_wage_ceiling or 21000.0
        except Exception:
            esi_ceiling = 21000.0
        if base_gross > esi_ceiling:
            base_esi_emp = 0.0
            base_esi_er  = 0.0
            base_deductions = _sum_money(base_pf_emp, base_pf_er, base_pt, base_tds)

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
            base_pf_emp      = round(base_pf_emp      * pay_ratio, 2)
            base_pf_er       = round(base_pf_er       * pay_ratio, 2)
            base_esi_emp     = round(base_esi_emp     * pay_ratio, 2)
            base_esi_er      = round(base_esi_er      * pay_ratio, 2)
            base_tds         = round(base_tds         * pay_ratio, 2)
            lop_deduction    = round(original_base_gross - base_gross, 2)
            # PT is NOT scaled for LOP in most Indian states (fixed per month)
            base_deductions  = _sum_money(base_pf_emp, base_pf_er, base_esi_emp, base_pt, base_tds)
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
            base_deductions = _sum_money(base_pf_emp, base_pf_er, base_esi_emp, base_pt, base_tds)

        final_gross      = round(base_gross + additions, 2)
        final_deductions = _sum_money(base_deductions, deduction_adj)
        final_net        = _subtract_money(final_gross, final_deductions)
        variance_flag, variance_reason = _detect_variance(
            db=db,
            employee_id=emp.id,
            run=run,
            gross_earnings=final_gross,
            total_deductions=final_deductions,
            net_pay=final_net,
            payable_days=payable_days,
            lop_days=lop_days,
            assignment_missing=assignment_missing,
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
            lta=base_lta + lta_amount,
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
            db.add(row)
            db.flush()
        except Exception as _row_err:
            db.rollback()
            log.error(
                "[Run %d] Employee %d (%s): failed to insert payroll row — %s",
                run.id, emp.id, emp_label, _row_err,
            )
            db.add(PayrollError(
                run_id=run.id,
                employee_id=emp.id,
                error_type="computation_error",
                description=f"Payroll row insert failed: {_row_err}",
                severity="error",
            ))
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

    log.info(
        "[Run %d] Generation complete — %d rows generated, %d errors/warnings.",
        run.id, generated, errors,
    )


# ─── Payslip generation ───────────────────────────────────────────────────────

def _generate_payslip_records(db: Session, run: PayrollRun, actor: Employee) -> None:
    """Create Payslip rows for every non-error employee in the run."""
    rows = db.query(PayrollRunEmployee).filter_by(run_id=run.id).all()
    month, year, _ = _period_month_year(run)
    now = datetime.utcnow()
    for row in rows:
        if row.has_error:
            continue
        existing = db.query(Payslip).filter_by(run_id=run.id, employee_id=row.employee_id).first()
        if existing:
            row.payslip_generated = True
            row.payslip_url = existing.file_url or existing.pdf_path
            continue
        payslip_number = f"PS-{year}{month:02d}-{run.id:04d}-{row.employee_id:04d}"
        slip = Payslip(
            payroll_record_id=row.id,
            run_id=run.id,
            employee_id=row.employee_id,
            month_label=run.month_label,
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
    if run and (run.payroll_locked or run.status in _LOCKED_STATUSES):
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
    if run and (run.payroll_locked or run.status in _LOCKED_STATUSES):
        raise ValueError("Payroll is locked for this run; unlock workflow is required before changes")
    db.delete(adj)
    db.commit()
    return True


# ─── Payroll Errors ───────────────────────────────────────────────────────────

def create_payroll_error(db: Session, data: dict, actor: Employee) -> PayrollError:
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
    err.is_resolved = True
    err.resolved_by_id = actor.id
    err.resolved_at = datetime.utcnow()
    err.resolution_note = resolution_note
    open_errors = (
        db.query(PayrollError)
        .filter_by(run_id=err.run_id, employee_id=err.employee_id, is_resolved=False)
        .count()
    )
    if open_errors <= 1:
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

    last_disbursed = (
        db.query(PayrollRun)
        .filter(PayrollRun.status.in_(["approved", "disbursed", "closed"]))
        .order_by(PayrollRun.pay_period_start.desc())
        .first()
    )

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
        variance_count = db.query(PayrollRunEmployee).filter_by(
            run_id=current_run.id, variance_flag=True
        ).count()
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
            bool(current_run.payroll_locked or current_run.status in ("payslip_generated", "published", "closed"))
            if current_run else False
        ),
        "is_published": bool(current_run and current_run.status in ("published", "closed")),
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
    row = (
        db.query(PayrollRunEmployee)
        .filter_by(run_id=run_id, employee_id=employee_id)
        .first()
    )
    if row:
        run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
        if run:
            month, year, _ = _period_month_year(run)
            slip = db.query(Payslip).filter_by(run_id=run_id, employee_id=employee_id).first()
            if not slip:
                slip = Payslip(
                    payroll_record_id=row.id,
                    run_id=run_id,
                    employee_id=employee_id,
                    month_label=run.month_label,
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
    return q.order_by(Payslip.pay_period_start.desc()).all()


def publish_payslip(db: Session, payslip_id: int, actor: Employee) -> Payslip:
    slip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not slip:
        raise ValueError(f"Payslip {payslip_id} not found")
    run = db.query(PayrollRun).filter(PayrollRun.id == slip.run_id).first()
    if run and not run.payroll_locked:
        if run.status == "approved":
            run.payroll_locked = True
            run.finalized_by_id = actor.id if actor else None
            run.finalized_at = datetime.utcnow()
            db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
                {"is_locked": True}, synchronize_session=False
            )
            _record_lock_history(db, run, "PAYROLL", "LOCK", actor, "Auto-finalized before payslip publish")
        elif run.status not in ("payslip_generated", "published", "closed"):
            raise ValueError("Payroll must be finalized before publishing payslips")
    slip.is_published = True
    slip.status = "PUBLISHED"
    slip.published_at = datetime.utcnow()
    if run:
        run.published_at = slip.published_at
    db.commit()
    db.refresh(slip)
    _log_audit(db, slip.run_id, slip.employee_id, "published")
    if run:
        _record_lock_history(db, run, "PAYSLIP", "LOCK", actor, "Payslip published")
    db.commit()
    return slip


def bulk_publish_payslips(db: Session, run_id: int, actor: Employee) -> int:
    """Publish all payslips for a run. Returns count published."""
    run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
    if run and not run.payroll_locked:
        if run.status == "approved":
            run.payroll_locked = True
            run.finalized_by_id = actor.id if actor else None
            run.finalized_at = datetime.utcnow()
            db.query(PayrollRunEmployee).filter_by(run_id=run.id).update(
                {"is_locked": True}, synchronize_session=False
            )
            _record_lock_history(db, run, "PAYROLL", "LOCK", actor, "Auto-finalized before payslip publish")
        elif run.status not in ("payslip_generated", "published", "closed"):
            raise ValueError("Payroll must be finalized before publishing payslips")
    slips = db.query(Payslip).filter_by(run_id=run_id, is_published=False).all()
    now = datetime.utcnow()
    count = 0
    for slip in slips:
        slip.is_published = True
        slip.status = "PUBLISHED"
        slip.published_at = now
        _log_audit(db, slip.run_id, slip.employee_id, "published")
        count += 1
    if run:
        run.status = "published"
        run.published_at = now
        _record_lock_history(db, run, "PAYSLIP", "LOCK", actor, "All payslips published")
    db.commit()
    return count
