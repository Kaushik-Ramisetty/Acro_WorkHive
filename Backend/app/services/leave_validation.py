"""Centralized leave validation pipeline.

Every validator is a pure function that takes a `ValidationContext` and
appends human-readable error strings to `ctx.errors`. The pipeline runs
all validators, collecting every problem so the frontend can surface
them in one shot instead of one-error-at-a-time.

Validators implemented in Phase 1:
  - DateValidator        : range sanity, no past dates
  - EligibilityValidator : leave type exists, gender rule, probation cutoff
  - BalanceValidator     : opening - used - reserved - pending >= requested
  - OverlapValidator     : no overlap with pending / approved / cancel_pending
  - CalendarValidator    : weekend-only span and sandwich-rule warnings

Stubs for later phases (kept here so route layer wiring is stable):
  - DocumentValidator    : mandatory file presence + malware scan hook
  - TeamCapacityValidator: max concurrent leaves per team / blackout periods

Usage:
    errors = run_validation(db, employee, leave_type_id, start, end, reason,
                            require_documents=False, attached_files=None)
    if errors:
        raise LeaveEngineError(400, "; ".join(errors))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.models import (
    BlackoutPeriod, Employee, LeaveBalance, LeaveDocument, LeaveRequest,
    LeaveType, TeamCapacityPolicy,
)
from utils.time_utils import now_utc


# Statuses that should block a new overlapping request.
_BLOCKING_STATUSES = ("pending", "approved", "cancel_pending")

# How many days after joining the employee must wait before paid leave.
# Configurable later via leave_type or HR policy table.
DEFAULT_PROBATION_DAYS = 90


@dataclass
class ValidationContext:
    db: Session
    employee: Employee
    leave_type_id: str
    start: date
    end: date
    reason: Optional[str]
    # When set, the existing leave request id whose attached documents
    # should be inspected by the DocumentValidator. submit_draft passes
    # the draft id here so attached docs are considered.
    leave_request_id: Optional[str] = None
    # Loaded once by DateValidator so downstream validators reuse them.
    leave_type: Optional[LeaveType] = None
    days: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


Validator = Callable[[ValidationContext], None]


# ---------- individual validators -----------------------------------

def date_validator(ctx: ValidationContext) -> None:
    if not ctx.start or not ctx.end:
        ctx.fail("start_date and end_date are required.")
        return
    if ctx.end < ctx.start:
        ctx.fail("end_date cannot be before start_date.")
        return
    today = now_utc().date()
    if ctx.start < today:
        ctx.fail("Cannot apply for leave in the past.")
    # Working-day refactor: ctx.days is now the *working-day* count
    # (weekends + location-aware holidays skipped). Balance, overlap, and
    # ledger code already treats `total_days` as the unit of deduction —
    # this just changes how that unit is computed.
    from app.services.working_day_engine import count_working_days
    location = getattr(ctx.employee, "location", None)
    working = count_working_days(ctx.db, ctx.start, ctx.end, location)
    # Half-day flags ride in on the ValidationContext when callers
    # supply them (see apply_leave_by_days). When absent, we fall back
    # to whole days.
    if working <= 0:
        ctx.fail("Leave covers no working days (only weekends/holidays).")
    # Whole-day callers will see an integer here; half-day callers see a
    # float. The downstream balance/ledger layer still expects ints, so
    # we coerce when it's exactly integral.
    ctx.days = int(working) if abs(working - int(working)) < 1e-9 else working


def eligibility_validator(ctx: ValidationContext) -> None:
    lt = ctx.db.get(LeaveType, ctx.leave_type_id)
    if not lt:
        ctx.fail(f"Unknown leave type '{ctx.leave_type_id}'.")
        return
    ctx.leave_type = lt

    # Gender rule
    rule = (lt.applicable_gender or "all").lower()
    if rule != "all":
        emp_gender = (ctx.employee.gender or "").lower()
        if emp_gender != rule:
            ctx.fail(f"Leave type '{lt.name}' is restricted to {rule} employees.")

    # Probation rule — only block paid leave types during probation window.
    # Sick/medical leave is exempt so probationers can still apply when unwell.
    join_date = getattr(ctx.employee, "joining_date", None) or getattr(ctx.employee, "date_of_joining", None)
    lt_name = (lt.name or "").lower()
    is_sick = any(token in lt_name for token in ("sick", "medical"))
    if join_date and lt.is_paid and not is_sick:
        cutoff = join_date + timedelta(days=DEFAULT_PROBATION_DAYS)
        if ctx.start < cutoff:
            ctx.fail(
                f"You are still in probation until {cutoff.isoformat()}; "
                f"paid leave type '{lt.name}' is unavailable until then."
            )


def balance_validator(ctx: ValidationContext) -> None:
    if ctx.days <= 0 or not ctx.leave_type:
        return  # nothing to check; date/eligibility already failed
    # LOP / unpaid types have no quota or balance row — skip the check.
    if not ctx.leave_type.is_paid:
        return
    year = ctx.start.year if ctx.start else now_utc().year
    bal = (
        ctx.db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == ctx.employee.id,
            LeaveBalance.leave_type_id == ctx.leave_type_id,
            LeaveBalance.year == year,
        )
        .first()
    )
    base = int(bal.current_balance or 0) if bal else 0
    reserved = int(bal.reserved or 0) if bal else 0
    pending_days = (
        ctx.db.query(sqlfunc.coalesce(sqlfunc.sum(LeaveRequest.total_days), 0))
        .filter(
            LeaveRequest.employee_id == ctx.employee.id,
            LeaveRequest.leave_type_id == ctx.leave_type_id,
            LeaveRequest.status == "pending",
        )
        .scalar()
    ) or 0
    available = max(0, base - reserved - int(pending_days))
    if ctx.days > available:
        ctx.fail(
            f"Insufficient balance for {ctx.leave_type.name}: "
            f"available {available}, requested {ctx.days}."
        )


def overlap_validator(ctx: ValidationContext) -> None:
    if not ctx.start or not ctx.end:
        return
    clashing = (
        ctx.db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == ctx.employee.id,
            LeaveRequest.status.in_(_BLOCKING_STATUSES),
            LeaveRequest.start_date <= ctx.end,
            LeaveRequest.end_date >= ctx.start,
        )
        .first()
    )
    if clashing:
        ctx.fail(
            f"Overlapping leave already exists ({clashing.id}: "
            f"{clashing.start_date} -> {clashing.end_date})."
        )


def working_day_start_validator(ctx: ValidationContext) -> None:
    """Reject requests that start on a weekend or location-scoped holiday.

    Per spec, employees may not begin a leave on a non-working day — the
    earliest legal start is the next working day. (End-of-range non-
    working days are silently skipped by the working-day engine.)

    NOTE: this validator deliberately does NOT enforce a sandwich-rule
    deduction. Friday-and-Monday-only requests count as 2 working days,
    not 4 — that's the employee-friendly non-sandwich policy.
    """
    if not ctx.start:
        return
    from app.services.working_day_engine import is_weekend, is_working_day
    location = getattr(ctx.employee, "location", None)
    if is_weekend(ctx.start):
        ctx.fail("Cannot apply leave starting on a weekend — please pick the next working day.")
        return
    if not is_working_day(ctx.db, ctx.start, location):
        # Surface the holiday name so HR can verify against the calendar
        # without an extra round-trip.
        from app.models import Holiday
        h = (
            ctx.db.query(Holiday)
            .filter(Holiday.date == ctx.start)
            .first()
        )
        name = h.name if h else "company holiday"
        ctx.fail(f"Cannot apply leave starting on a holiday ({name}).")


def _docs_required(ctx: ValidationContext) -> bool:
    """Policy: medical/sick leaves longer than 2 days require a doc.

    This is intentionally a code-level rule rather than a column on
    LeaveType — HR can iterate on policy without a schema change."""
    if not ctx.leave_type or ctx.days < 3:
        return False
    name = (ctx.leave_type.name or "").lower()
    return any(token in name for token in ("sick", "medical"))


def document_validator(ctx: ValidationContext) -> None:
    """When the policy requires a supporting document, look up the
    LeaveDocument rows for `leave_request_id` and ensure at least one
    is `clean` (i.e. scanner verified). Pending/infected docs do not
    satisfy the requirement."""
    if not _docs_required(ctx):
        return
    if not ctx.leave_request_id:
        ctx.fail(
            "A supporting document is required for this leave type — "
            "save as draft and attach a file before submitting."
        )
        return
    rows = (
        ctx.db.query(LeaveDocument)
        .filter(LeaveDocument.leave_request_id == ctx.leave_request_id)
        .all()
    )
    if not rows:
        ctx.fail("A supporting document is required for this leave type.")
        return
    if any(r.scan_status == "infected" for r in rows):
        ctx.fail("An attached document was flagged as infected — please remove it.")
        return
    clean = [r for r in rows if r.scan_status == "clean"]
    if not clean:
        ctx.fail(
            "Attached document(s) are still being scanned or could not be verified. "
            "Wait for the scan to complete or replace the file."
        )


def _team_concurrent_count(ctx: ValidationContext, manager_id: int) -> int:
    """How many of the manager's reports already have an overlapping
    pending/approved leave on any day of this request."""
    if not manager_id:
        return 0
    overlap = (
        ctx.db.query(LeaveRequest)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .filter(
            Employee.reporting_manager_id == manager_id,
            LeaveRequest.employee_id != ctx.employee.id,
            LeaveRequest.status.in_(("pending", "approved", "cancel_pending")),
            LeaveRequest.start_date <= ctx.end,
            LeaveRequest.end_date >= ctx.start,
        )
        .count()
    )
    return overlap


def team_capacity_validator(ctx: ValidationContext) -> None:
    """Reject the request if applying it would push the team over the
    manager's `max_concurrent_on_leave` threshold."""
    mgr_id = ctx.employee.reporting_manager_id if ctx.employee else None
    if not mgr_id:
        return
    policy = (
        ctx.db.query(TeamCapacityPolicy)
        .filter(
            TeamCapacityPolicy.manager_id == mgr_id,
            TeamCapacityPolicy.is_active.is_(True),
        )
        .order_by(TeamCapacityPolicy.created_at.desc())
        .first()
    )
    if not policy:
        return
    # Effective cap is the *minimum* of any configured absolute cap and any
    # configured percentage cap. Either alone is enforced; both together pick
    # the tighter ceiling, matching how HR usually describes the rule
    # ("max 5, AND no more than 30% of the team").
    caps: list[int] = []
    if policy.max_concurrent_on_leave and policy.max_concurrent_on_leave > 0:
        caps.append(int(policy.max_concurrent_on_leave))
    if policy.max_concurrent_percent and policy.max_concurrent_percent > 0:
        team_size = (
            ctx.db.query(Employee)
            .filter(
                Employee.reporting_manager_id == mgr_id,
                Employee.is_deleted.is_(False),
                Employee.employment_status == "active",
            )
            .count()
        )
        if team_size > 0:
            # Ceiling so a 30%-of-10 cap is 3, not 2 (round half up).
            derived = -(-team_size * int(policy.max_concurrent_percent) // 100)
            caps.append(max(1, derived))
    if not caps:
        return
    effective_cap = min(caps)
    existing = _team_concurrent_count(ctx, mgr_id)
    if existing + 1 > effective_cap:
        ctx.fail(
            f"Team capacity reached: cap is {effective_cap} concurrent leave(s) "
            f"(already {existing} overlapping)."
        )


def _department_id(emp: Employee) -> Optional[str]:
    # Employee model uses department_id (string FK to departments.id)
    return getattr(emp, "department_id", None)


def blackout_validator(ctx: ValidationContext) -> None:
    """Refuse leave overlapping with any active BlackoutPeriod that
    applies to this employee (global, their department, or their manager)."""
    if not ctx.start or not ctx.end:
        return
    dept_id = _department_id(ctx.employee)
    mgr_id = ctx.employee.reporting_manager_id
    q = (
        ctx.db.query(BlackoutPeriod)
        .filter(
            BlackoutPeriod.is_active.is_(True),
            BlackoutPeriod.start_date <= ctx.end,
            BlackoutPeriod.end_date >= ctx.start,
        )
    )
    rows = q.all()
    for b in rows:
        scope = (b.scope_type or "").lower()
        if scope == "global":
            pass
        elif scope == "department":
            if not dept_id or str(b.scope_id) != str(dept_id):
                continue
        elif scope == "manager":
            if not mgr_id or str(b.scope_id) != str(mgr_id):
                continue
        else:
            continue
        ctx.fail(
            f"Leave overlaps a blackout period ({b.start_date} -> {b.end_date}): "
            f"{b.reason or 'no reason given'}."
        )
        return


# Ordered pipeline — date first because every later validator depends on
# ctx.days; eligibility before balance because balance needs leave_type.
DEFAULT_PIPELINE: list[Validator] = [
    date_validator,
    working_day_start_validator,   # weekend/holiday start guard
    eligibility_validator,
    balance_validator,
    overlap_validator,
    blackout_validator,
    team_capacity_validator,
    document_validator,
]


def run_validation(
    db: Session,
    employee: Employee,
    leave_type_id: str,
    start: date,
    end: date,
    reason: Optional[str] = None,
    *,
    leave_request_id: Optional[str] = None,
    pipeline: Optional[list[Validator]] = None,
) -> ValidationContext:
    """Run the full pipeline. Returns the context so callers can inspect
    both `errors` and `warnings`. Does NOT raise — caller decides whether
    a non-empty `errors` list is a 400 or a soft-fail."""
    ctx = ValidationContext(
        db=db,
        employee=employee,
        leave_type_id=leave_type_id,
        start=start,
        end=end,
        reason=reason,
        leave_request_id=leave_request_id,
    )
    for v in (pipeline or DEFAULT_PIPELINE):
        # Fail-soft per validator so one buggy check doesn't kill the whole
        # validation pass. Collect a generic error instead.
        try:
            v(ctx)
        except Exception as exc:  # noqa: BLE001
            ctx.fail(f"Validator '{v.__name__}' raised: {exc}")
    return ctx
