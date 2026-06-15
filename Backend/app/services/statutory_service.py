"""Statutory Compliance Service — PF / ESI / PT / TDS / Gratuity / Bonus.

Provides:
- seed_default_settings()            : seeds one StatutorySettings row on startup
- get_active_settings()              : returns current active settings
- compute_pf()                       : employee + employer PF
- compute_esi()                      : employee + employer ESI
- compute_pt()                       : professional tax from slab
- estimate_monthly_tds()             : annual tax ÷ 12 with full debug logging
- estimate_monthly_tds_prorated()    : production-grade TDS with remaining months
- compute_gratuity()                 : gratuity for FF (Basic × 15/26 × years)
- compute_bonus()                    : statutory bonus (8.33% to 20% of Basic)
- get_compliance_summary()           : aggregate PF/ESI/PT for a payroll run
- refresh_tds_for_employee()         : re-compute + persist TDS from tax declaration
- refresh_tds_for_run()              : refresh TDS for all employees before payroll generate
- upsert_tds_annual_summary()        : update Form 16 readiness data after payroll finalize
- upsert_tds_monthly_breakup()       : store monthly TDS breakup for Form 16

Default tax regime: NEW REGIME
  Employees can opt into the Old Regime by setting opted_new_regime=False in their
  EmployeeTaxDeclaration for the financial year.  The default here matches
  Budget 2024 where the New Regime became the default for salaried employees.

Declaration policy:
  NEW REGIME  — no declarations needed; TDS from slabs only.
  OLD REGIME  — ONLY declarations with status='approved' are used.
               Draft/submitted/rejected declarations have NO effect on TDS.
               This prevents employees from claiming bogus deductions.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payroll_extended import StatutorySettings, EmployeeTaxDeclaration
from app.models.payroll import PayrollRun, PayrollRunEmployee, SalaryStructure

_tds_log = logging.getLogger("hrms.tds")
log      = logging.getLogger("hrms.statutory")

_CENT = Decimal("0.01")


def _to_decimal(value: float | Decimal | int | None) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: float | Decimal) -> float:
    return float(_to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


def _sum_money(*values: float | Decimal | int | None) -> float:
    return _money(sum((_to_decimal(value) for value in values), Decimal("0")))


def _subtract_money(base: float | Decimal, *values: float | Decimal | int | None) -> float:
    return _money(_to_decimal(base) - sum((_to_decimal(value) for value in values), Decimal("0")))


# ─── Default seed ─────────────────────────────────────────────────────────────

_DEFAULT_PT_SLABS = json.dumps([
    {"min": 0,     "max": 21000,   "pt": 0},
    {"min": 21001, "max": 9999999, "pt": 200},
])


def seed_default_settings(db: Session) -> None:
    """Insert one active StatutorySettings row if none exists."""
    exists = db.query(StatutorySettings).filter(StatutorySettings.is_active.is_(True)).first()
    if exists:
        return
    row = StatutorySettings(
        pf_employee_rate=0.12,
        pf_employer_rate=0.12,
        pf_wage_ceiling=15000.0,
        esi_employee_rate=0.0075,
        esi_employer_rate=0.0325,
        esi_wage_ceiling=21000.0,
        pt_slab_json=_DEFAULT_PT_SLABS,
        gratuity_rate=0.0481,
        gratuity_eligibility_years=5.0,
        bonus_min_rate=0.0833,
        bonus_max_rate=0.20,
        bonus_wage_ceiling=21000.0,
        basic_pct_of_ctc=0.50,
        hra_pct_of_basic=0.40,
        transport_allowance=5000.0,
        medical_allowance=0.0,
        effective_from=date(2025, 4, 1),
        is_active=True,
    )
    db.add(row)
    db.commit()


def get_active_settings(db: Session) -> Optional[StatutorySettings]:
    return (
        db.query(StatutorySettings)
        .filter(StatutorySettings.is_active.is_(True))
        .order_by(StatutorySettings.effective_from.desc())
        .first()
    )


# ─── PF ───────────────────────────────────────────────────────────────────────

def compute_pf(basic: float, db: Session) -> dict:
    """Returns {'employee': float, 'employer': float}."""
    s = get_active_settings(db)
    rate_e  = s.pf_employee_rate if s else 0.12
    rate_r  = s.pf_employer_rate if s else 0.12
    ceiling = s.pf_wage_ceiling  if s else 15000.0
    wage = min(basic, ceiling)
    return {
        "employee": round(rate_e * wage, 2),
        "employer": round(rate_r * wage, 2),
    }


# ─── ESI ──────────────────────────────────────────────────────────────────────

def compute_esi(gross: float, db: Session) -> dict:
    """Returns {'employee': float, 'employer': float}. Zero if gross > ceiling."""
    s = get_active_settings(db)
    ceiling = s.esi_wage_ceiling if s else 21000.0
    if gross > ceiling:
        return {"employee": 0.0, "employer": 0.0}
    rate_e = s.esi_employee_rate if s else 0.0075
    rate_r = s.esi_employer_rate if s else 0.0325
    return {
        "employee": round(rate_e * gross, 2),
        "employer": round(rate_r * gross, 2),
    }


# ─── Professional Tax ─────────────────────────────────────────────────────────

def compute_pt(gross: float, db: Session) -> float:
    s = get_active_settings(db)
    slabs_json = s.pt_slab_json if s else _DEFAULT_PT_SLABS
    try:
        slabs = json.loads(slabs_json)
        for slab in slabs:
            if slab["min"] <= gross <= slab["max"]:
                return float(slab["pt"])
    except (json.JSONDecodeError, KeyError):
        pass
    return 0.0


# ─── TDS ──────────────────────────────────────────────────────────────────────

def estimate_monthly_tds(
    annual_gross: float,
    sec_80c: float = 0.0,
    sec_80d: float = 0.0,
    hra_exemption: float = 0.0,
    sec_24b: float = 0.0,
    sec_80ccd: float = 0.0,
    other_deductions: float = 0.0,
    opted_new_regime: bool = True,        # ← NEW REGIME IS DEFAULT (Budget 2024)
    employee_label: str = "",             # optional — used in log messages only
    # Prorated TDS parameters (set these for production payroll)
    remaining_months: int = 12,           # months left in financial year incl. current
    tds_already_deducted: float = 0.0,   # TDS collected in earlier months of this FY
) -> float:
    """
    Estimate monthly TDS for an employee.

    Default regime: NEW REGIME (Budget 2024 default for salaried employees).
    Employees opt into Old Regime by setting opted_new_regime=False in their
    EmployeeTaxDeclaration.

    New Regime (FY 2025-26, Budget 2025):
      Standard deduction: ₹75,000
      Taxable = Annual Gross - ₹75,000
      Slabs:
        0 – 4L   →  0%
        4L – 8L  →  5%
        8L – 12L → 10%
        12L – 16L→ 15%
        16L – 20L→ 20%
        20L – 24L→ 25%
        > 24L    → 30%
      87A rebate: full rebate if net taxable ≤ ₹7L (tax becomes ₹0)

    Old Regime:
      Standard deduction: ₹50,000
      Taxable = Annual Gross - 50K - 80C - 80D - HRA - 24b - 80CCD - other
      Slabs:
        0 – 2.5L → 0%
        2.5L – 5L→ 5%
        5L – 10L → 20%
        > 10L    → 30%
      87A rebate: full rebate if taxable ≤ ₹5L

    Both regimes: +4% Health & Education Cess on tax.
    Monthly TDS = annual_tax_with_cess / 12.

    Every computation is logged at INFO level via hrms.tds logger for audit.
    """
    if opted_new_regime:
        regime_name       = "New Regime"
        standard_deduction= 75_000.0
        taxable           = max(annual_gross - standard_deduction, 0.0)
        annual_tax        = _new_regime_tax(taxable)
        rebate_limit      = 700_000.0
        total_deductions_applied = standard_deduction
    else:
        regime_name       = "Old Regime"
        standard_deduction= 50_000.0
        total_deductions_applied = (
            standard_deduction + sec_80c + sec_80d + hra_exemption
            + sec_24b + sec_80ccd + other_deductions
        )
        taxable    = max(annual_gross - total_deductions_applied, 0.0)
        annual_tax = _old_regime_tax(taxable)
        rebate_limit = 500_000.0

    # 4% Health & Education Cess
    tax_with_cess = annual_tax * 1.04

    # Section 87A Rebate — wipes tax completely if taxable income is within limit
    rebate_applied = False
    if taxable <= rebate_limit:
        tax_with_cess  = 0.0
        rebate_applied = True

    # ── Prorated TDS (production-grade remaining-months logic) ────────────
    # Instead of annual_tax / 12, subtract TDS already deducted in prior
    # months and spread remaining tax over remaining months in the FY.
    # This is how actual payroll systems handle mid-year salary changes,
    # approved declarations added late, etc.
    remaining_m = max(int(remaining_months), 1)
    remaining_tax = max(tax_with_cess - tds_already_deducted, 0.0)
    monthly_tds = round(remaining_tax / remaining_m, 2)

    # ── Determine reason for zero TDS (for audit log transparency) ──
    if monthly_tds == 0.0:
        if annual_gross <= standard_deduction:
            reason = f"Annual gross (₹{annual_gross:,.0f}) ≤ standard deduction (₹{standard_deduction:,.0f}) — no taxable income."
        elif taxable == 0.0:
            reason = "All deductions exhaust taxable income — taxable = ₹0."
        elif rebate_applied:
            reason = (
                f"Section 87A rebate applied — taxable income ₹{taxable:,.0f} ≤ "
                f"rebate limit ₹{rebate_limit:,.0f} under {regime_name}."
            )
        elif tds_already_deducted >= tax_with_cess:
            reason = (
                f"TDS already deducted (₹{tds_already_deducted:,.0f}) ≥ annual tax "
                f"(₹{tax_with_cess:,.0f}) — no further TDS required this FY."
            )
        else:
            reason = f"Annual tax = ₹0 (income falls in zero-rate slab under {regime_name})."
    else:
        reason = (
            f"Tax computed — remaining tax ₹{remaining_tax:,.0f} spread over "
            f"{remaining_m} month(s) remaining in FY."
        )

    # Structured TDS audit log — visible in server logs for Finance review
    _tds_log.info(
        "TDS | employee=%s | regime=%s | annual_gross=₹%.2f | "
        "total_deductions=₹%.2f | taxable=₹%.2f | "
        "annual_tax=₹%.2f | with_cess=₹%.2f | "
        "tds_already_deducted=₹%.2f | remaining_months=%d | monthly_tds=₹%.2f | %s",
        employee_label or "—",
        regime_name,
        annual_gross,
        total_deductions_applied,
        taxable,
        annual_tax,
        tax_with_cess,
        tds_already_deducted,
        remaining_m,
        monthly_tds,
        reason,
    )

    return monthly_tds


def build_tds_debug_dict(
    annual_gross: float,
    sec_80c: float,
    sec_80d: float,
    hra_exemption: float,
    sec_24b: float,
    sec_80ccd: float,
    other_deductions: float,
    opted_new_regime: bool,
    remaining_months: int,
    tds_already_deducted: float,
    monthly_tds: float,
) -> dict:
    """Build a structured debug/audit dict for TDS computation.

    Returned dict is stored as JSON in payroll_run_employees.tds_debug_json
    and tds_monthly_breakup.tds_debug_json for full auditability.
    """
    if opted_new_regime:
        regime_name = "new"
        std_ded = 75_000.0
        taxable = max(annual_gross - std_ded, 0.0)
        annual_tax = _new_regime_tax(taxable)
        rebate_limit = 700_000.0
        deductions_detail = {"standard_deduction": std_ded}
        total_deductions = std_ded
    else:
        regime_name = "old"
        std_ded = 50_000.0
        total_deductions = std_ded + sec_80c + sec_80d + hra_exemption + sec_24b + sec_80ccd + other_deductions
        taxable = max(annual_gross - total_deductions, 0.0)
        annual_tax = _old_regime_tax(taxable)
        rebate_limit = 500_000.0
        deductions_detail = {
            "standard_deduction": std_ded,
            "sec_80c": sec_80c,
            "sec_80d": sec_80d,
            "hra_exemption": hra_exemption,
            "sec_24b": sec_24b,
            "sec_80ccd": sec_80ccd,
            "other_deductions": other_deductions,
        }

    tax_with_cess = annual_tax * 1.04
    rebate_applied = taxable <= rebate_limit
    if rebate_applied:
        tax_with_cess = 0.0

    return {
        "regime": regime_name,
        "gross_annual_income": round(annual_gross, 2),
        "exempt_income_deductions": deductions_detail,
        "total_deductions_applied": round(total_deductions, 2),
        "taxable_income": round(taxable, 2),
        "rebate_limit": rebate_limit,
        "rebate_applied": rebate_applied,
        "annual_tax_before_cess": round(annual_tax, 2),
        "cess_4pct": round(annual_tax * 0.04, 2),
        "annual_tax_with_cess": round(tax_with_cess, 2),
        "tds_already_deducted": round(tds_already_deducted, 2),
        "remaining_months": remaining_months,
        "remaining_tax": round(max(tax_with_cess - tds_already_deducted, 0.0), 2),
        "monthly_tds": round(monthly_tds, 2),
    }


def _old_regime_tax(taxable: float) -> float:
    tax  = 0.0
    slabs = [(250_000, 0.0), (500_000, 0.05), (1_000_000, 0.20), (float("inf"), 0.30)]
    prev  = 0.0
    for limit, rate in slabs:
        chunk = min(taxable, limit) - prev
        if chunk <= 0:
            break
        tax  += chunk * rate
        prev  = limit
    return tax


def _new_regime_tax(taxable: float) -> float:
    """New Regime slabs — FY 2025-26 (Budget 2025)."""
    tax   = 0.0
    slabs = [
        (  400_000, 0.00),   # 0 – 4 L   → 0%
        (  800_000, 0.05),   # 4 – 8 L   → 5%
        (1_200_000, 0.10),   # 8 – 12 L  → 10%
        (1_600_000, 0.15),   # 12 – 16 L → 15%
        (2_000_000, 0.20),   # 16 – 20 L → 20%
        (2_400_000, 0.25),   # 20 – 24 L → 25%
        (float("inf"), 0.30),# > 24 L    → 30%
    ]
    prev = 0.0
    for limit, rate in slabs:
        chunk = min(taxable, limit) - prev
        if chunk <= 0:
            break
        tax  += chunk * rate
        prev  = limit
    return tax


# ─── Gratuity ─────────────────────────────────────────────────────────────────

def compute_gratuity(
    basic_monthly: float,
    date_of_joining: date,
    last_working_day: date,
    db: Session,
) -> float:
    """Gratuity = Basic × 15 / 26 × completed_years (payable after eligibility period)."""
    s = get_active_settings(db)
    min_years = s.gratuity_eligibility_years if s else 5.0
    delta = last_working_day - date_of_joining
    years = delta.days / 365.25
    if years < min_years:
        return 0.0
    completed_years = int(years)
    return round(basic_monthly * 15 / 26 * completed_years, 2)


# ─── Bonus ────────────────────────────────────────────────────────────────────

def compute_bonus(
    basic_monthly: float,
    months: int = 12,
    db: Session = None,
) -> dict:
    """Statutory bonus under the Payment of Bonus Act.

    Returns {'min_bonus': float, 'max_bonus': float} for the year.
    Applies only if basic ≤ bonus_wage_ceiling.
    """
    s = get_active_settings(db) if db else None
    ceiling  = s.bonus_wage_ceiling if s else 21000.0
    min_rate = s.bonus_min_rate     if s else 0.0833
    max_rate = s.bonus_max_rate     if s else 0.20

    if basic_monthly > ceiling:
        return {"min_bonus": 0.0, "max_bonus": 0.0, "eligible": False}

    annual_basic = basic_monthly * months
    return {
        "min_bonus": round(annual_basic * min_rate, 2),
        "max_bonus": round(annual_basic * max_rate, 2),
        "eligible": True,
    }


# ─── TDS Auto-compute from Tax Declarations ───────────────────────────────────

def _get_remaining_fy_months(pay_month: int, pay_year: int) -> int:
    """Return the number of months remaining in the Indian FY including current month.

    The Indian FY runs April–March.
    E.g. pay_month=4 (April) → 12 remaining; pay_month=3 (March) → 1 remaining.
    """
    if pay_month >= 4:
        fy_end_month = 3  # March of next year
        months_remaining = (12 - pay_month) + fy_end_month + 1
    else:
        # Jan–Mar
        months_remaining = 4 - pay_month  # e.g. Jan=3, Feb=2, Mar=1
    return max(months_remaining, 1)


def _get_tds_already_deducted(db: Session, employee_id: int, financial_year: str,
                               exclude_run_id: Optional[int] = None) -> float:
    """Sum TDS already deducted from completed/closed payroll runs in this FY."""
    from sqlalchemy import text as _text
    # Use tds_monthly_breakup if available, else fall back to payroll_run_employees
    try:
        from app.models.payroll_extended import TdsMonthlyBreakup
        rows = (
            db.query(TdsMonthlyBreakup)
            .filter(
                TdsMonthlyBreakup.employee_id == employee_id,
                TdsMonthlyBreakup.financial_year == financial_year,
            )
        )
        if exclude_run_id:
            rows = rows.filter(TdsMonthlyBreakup.run_id != exclude_run_id)
        total = sum(r.monthly_tds for r in rows.all())
        return round(total, 2)
    except Exception:
        return 0.0


def refresh_tds_for_employee(
    db: Session,
    employee_id: int,
    commit: bool = True,
    pay_month: Optional[int] = None,
    pay_year: Optional[int] = None,
    exclude_run_id: Optional[int] = None,
) -> float:
    """
    Re-compute monthly TDS from the employee's latest tax declaration and persist
    the result into salary_structures.tds.

    Production-grade behaviour:
    - Only APPROVED declarations affect OLD regime TDS.
    - Draft/submitted/rejected declarations do NOT affect TDS.
    - When pay_month/pay_year are provided, computes prorated TDS based on
      remaining months in the financial year and TDS already deducted.
    - Default regime: NEW REGIME (opted_new_regime=True when no declaration exists).

    Returns the new monthly TDS amount (0.0 if no salary structure exists).

    commit=True  (default): commits immediately.
    commit=False: only flushes — use when called inside a larger transaction.
    """
    current_fy = _current_financial_year()

    ss = (
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
    if not ss or ss.gross_monthly <= 0:
        return 0.0

    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=current_fy)
        .first()
    )

    # Derive employee label for log readability
    emp_label = f"employee_id={employee_id}"
    try:
        emp_label = f"{ss.employee.first_name} {ss.employee.last_name or ''}".strip()
    except Exception:
        pass

    # ── Regime selection & declaration enforcement ────────────────────────
    # New Regime: use regardless of declaration status (no deductions to apply).
    # Old Regime: ONLY if declaration exists AND status == 'approved'.
    #             If declaration is draft/submitted/rejected → fall back to NEW regime
    #             with a warning log. This prevents stale/unreviewed declarations
    #             from silently changing payroll.
    opted_new = True  # default: New Regime
    effective_decl = None

    if decl:
        if decl.opted_new_regime:
            opted_new = True
            effective_decl = decl   # new regime — declaration not required for deductions
        else:
            # Old regime — only use if APPROVED
            decl_status = getattr(decl, "declaration_status", "approved")
            if decl_status == "approved":
                opted_new = False
                effective_decl = decl
            else:
                log.warning(
                    "TDS: employee=%s declared OLD regime but declaration status='%s' (not approved). "
                    "Falling back to NEW regime until declaration is approved by Finance/HR.",
                    emp_label, decl_status,
                )
                opted_new = True   # Fallback to new regime

    # ── Prorated TDS: remaining months + already-deducted TDS ────────────
    today = date.today()
    effective_pay_month = pay_month or today.month
    effective_pay_year = pay_year or today.year
    remaining_months = _get_remaining_fy_months(effective_pay_month, effective_pay_year)
    tds_already_deducted = _get_tds_already_deducted(
        db, employee_id, current_fy, exclude_run_id=exclude_run_id
    )

    # annual_gross is computed here so it is always available for the audit
    # log below, regardless of which TDS branch runs.
    annual_gross = ss.gross_monthly * 12

    # ── Company TDS policy: projected taxable income threshold check ─────────
    # If annual CTC ≤ ₹12,00,000, the employee's income falls within the tax
    # exemption threshold — TDS = ₹0 regardless of gross or declarations.
    # If annual CTC > ₹12,00,000, calculate TDS from annualised gross normally.
    annual_ctc_check = float(ss.annual_ctc or 0.0)
    if 0 < annual_ctc_check <= 1_200_000.0:
        monthly_tds = 0.0
        log.info(
            "TDS refresh (company policy — CTC ≤ ₹12L): employee=%s, "
            "structure_id=%d, annual_ctc=₹%.2f → monthly_tds=₹0.00",
            emp_label, ss.id, annual_ctc_check,
        )
    else:
        monthly_tds  = estimate_monthly_tds(
            annual_gross        = annual_gross,
            sec_80c             = effective_decl.sec_80c          if effective_decl and not opted_new else 0.0,
            sec_80d             = effective_decl.sec_80d          if effective_decl and not opted_new else 0.0,
            hra_exemption       = effective_decl.hra_exemption    if effective_decl and not opted_new else 0.0,
            sec_24b             = effective_decl.sec_24b          if effective_decl and not opted_new else 0.0,
            sec_80ccd           = effective_decl.sec_80ccd        if effective_decl and not opted_new else 0.0,
            other_deductions    = effective_decl.other_deductions if effective_decl and not opted_new else 0.0,
            opted_new_regime    = opted_new,
            employee_label      = emp_label,
            remaining_months    = remaining_months,
            tds_already_deducted = tds_already_deducted,
        )

    # Persist TDS back to salary structure
    ss.tds              = monthly_tds
    ss.total_deductions = _sum_money(
        ss.pf_employee,
        ss.pf_employer,
        ss.esi_employee,
        ss.professional_tax,
        monthly_tds,
    )
    ss.net_monthly = _subtract_money(ss.gross_monthly, ss.total_deductions)
    if commit:
        db.commit()
    else:
        db.flush()

    log.info(
        "TDS refreshed: employee=%s, structure_id=%d, "
        "annual_gross=₹%.2f, remaining_months=%d, tds_already_deducted=₹%.2f, "
        "monthly_tds=₹%.2f, regime=%s",
        emp_label, ss.id, annual_gross, remaining_months, tds_already_deducted,
        monthly_tds, "New Regime" if opted_new else "Old Regime",
    )
    return monthly_tds


def refresh_tds_for_run(db: Session, run_id: int) -> dict:
    """
    Before generating payroll, refresh TDS on every ACTIVE salary structure
    using the employee's current-FY tax declaration.

    This must be called before _generate_employee_rows so that ss.tds reflects
    the correct TDS amount at the time of payroll generation.

    Returns a summary: {'updated': int, 'skipped': int}
    """
    # Only refresh structures that are active (these are the ones payroll will use)
    structures = (
        db.query(SalaryStructure)
        .filter(SalaryStructure.is_active.is_(True))
        .all()
    )
    updated = 0
    skipped = 0
    for ss in structures:
        if ss.gross_monthly <= 0:
            skipped += 1
            continue
        try:
            # commit=False: keep all TDS updates in the same transaction as the
            # payroll generate/recompute so the whole operation is atomic.
            refresh_tds_for_employee(db, ss.employee_id, commit=False)
            updated += 1
        except Exception as exc:
            log.warning("TDS refresh failed for employee_id=%d: %s", ss.employee_id, exc)
            skipped += 1

    # One single flush for all TDS structure updates; the caller commits.
    db.flush()
    log.info(
        "TDS refresh for run %d complete — updated=%d, skipped=%d",
        run_id, updated, skipped,
    )
    return {"updated": updated, "skipped": skipped}


def validate_pan_for_tds(db: Session, employee_id: int) -> Optional[str]:
    """Validate that the employee has a valid PAN number for TDS computation.

    Returns the PAN number if valid, or None if missing/invalid.
    Logs a warning if PAN is missing (TDS must still be computed at maximum rate).

    Per Indian Income Tax rules:
    - Employees without PAN → TDS at 20% (higher of applicable rate or 20%).
    - This function only validates presence/format; the caller decides the rate.
    """
    import re
    from app.models.employee import Employee as _Emp
    emp = db.query(_Emp).filter_by(id=employee_id).first()
    if not emp:
        return None

    # Try to get PAN from employee record
    # PAN may be stored in employee.pan_number or via PII encryption
    pan = getattr(emp, "pan_number", None)
    if not pan:
        # Try decrypted field if PII encryption is used
        try:
            from app.core.config import settings
            if hasattr(emp, "pan_encrypted") and emp.pan_encrypted:
                from cryptography.fernet import Fernet
                f = Fernet(settings.PII_ENCRYPTION_KEY.encode())
                pan = f.decrypt(emp.pan_encrypted.encode()).decode()
        except Exception:
            pass

    if not pan:
        log.warning(
            "TDS: employee_id=%d has NO PAN number. "
            "Per IT rules, TDS may be deducted at 20%% if required. "
            "Finance should ensure PAN is collected.",
            employee_id,
        )
        return None

    # Basic PAN format validation: 5 letters + 4 digits + 1 letter
    pan_clean = pan.strip().upper()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan_clean):
        log.warning(
            "TDS: employee_id=%d PAN '%s' has invalid format. "
            "Valid format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F).",
            employee_id, pan_clean,
        )
        return None

    return pan_clean


def compute_monthly_tds_for_adjusted_gross(
    db: Session, employee_id: int, adjusted_annual_gross: float
) -> float:
    """Compute monthly TDS for an employee given an already-adjusted annual gross.

    Used by payroll recompute when taxable one-time adjustments (bonus, incentive,
    arrears, etc.) increase the employee's taxable income beyond the base salary.
    Does NOT persist anything — caller stores the result in PayrollRunEmployee.tds.

    Args:
        adjusted_annual_gross: base_monthly_gross * 12 + sum of taxable additions.
                               Caller must pass the correct annualised figure.
    """
    current_fy = _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=current_fy)
        .first()
    )
    emp_label = f"employee_id={employee_id}"
    return estimate_monthly_tds(
        annual_gross     = adjusted_annual_gross,
        sec_80c          = decl.sec_80c          if decl else 0.0,
        sec_80d          = decl.sec_80d          if decl else 0.0,
        hra_exemption    = decl.hra_exemption    if decl else 0.0,
        sec_24b          = decl.sec_24b          if decl else 0.0,
        sec_80ccd        = decl.sec_80ccd        if decl else 0.0,
        other_deductions = decl.other_deductions if decl else 0.0,
        opted_new_regime = decl.opted_new_regime if decl else True,
        employee_label   = emp_label,
    )


def upsert_tds_monthly_breakup(
    db: Session,
    employee_id: int,
    run_id: int,
    month: int,
    year: int,
    financial_year: str,
    gross_salary: float,
    monthly_tds: float,
    pf_employee: float,
    esi_employee: float,
    professional_tax: float,
    regime_used: str,
    annual_taxable_at_time: float,
    remaining_months_at_time: int,
    tds_debug_json: Optional[str] = None,
    commit: bool = False,
) -> None:
    """Create or update TdsMonthlyBreakup for Form 16 Part B readiness.

    Called at payroll finalization time. After the run is closed this record
    is never updated (immutable historical data).
    """
    try:
        from app.models.payroll_extended import TdsMonthlyBreakup
        existing = (
            db.query(TdsMonthlyBreakup)
            .filter_by(employee_id=employee_id, run_id=run_id)
            .first()
        )
        if existing is None:
            existing = TdsMonthlyBreakup(employee_id=employee_id, run_id=run_id)
            db.add(existing)

        existing.financial_year           = financial_year
        existing.month                    = month
        existing.year                     = year
        existing.gross_salary             = gross_salary
        existing.monthly_tds              = monthly_tds
        existing.pf_employee              = pf_employee
        existing.esi_employee             = esi_employee
        existing.professional_tax         = professional_tax
        existing.regime_used              = regime_used
        existing.annual_taxable_at_time   = annual_taxable_at_time
        existing.remaining_months_at_time = remaining_months_at_time
        existing.tds_debug_json           = tds_debug_json

        if commit:
            db.commit()
        else:
            db.flush()
    except Exception as exc:
        log.warning("upsert_tds_monthly_breakup failed for emp=%d run=%d: %s",
                    employee_id, run_id, exc)


def upsert_tds_annual_summary(
    db: Session,
    employee_id: int,
    financial_year: str,
    commit: bool = False,
) -> None:
    """Aggregate TdsMonthlyBreakup rows → TdsAnnualSummary for Form 16 Part A.

    Called after each payroll run is finalized. Accumulates YTD totals.
    Should be called from payroll_service after run is closed.
    """
    try:
        from app.models.payroll_extended import TdsAnnualSummary, TdsMonthlyBreakup
        from app.models.employee import Employee as _Emp

        rows = (
            db.query(TdsMonthlyBreakup)
            .filter(
                TdsMonthlyBreakup.employee_id == employee_id,
                TdsMonthlyBreakup.financial_year == financial_year,
            )
            .all()
        )
        if not rows:
            return

        total_gross  = sum(r.gross_salary for r in rows)
        total_tds    = sum(r.monthly_tds  for r in rows)
        # Use latest row's debug JSON for annual computation details
        latest = max(rows, key=lambda r: (r.year, r.month))
        regime = latest.regime_used
        annual_taxable = latest.annual_taxable_at_time

        # Fetch declaration for deduction details
        decl = (
            db.query(EmployeeTaxDeclaration)
            .filter_by(employee_id=employee_id, financial_year=financial_year)
            .first()
        )
        decl_status = getattr(decl, "declaration_status", "approved") if decl else "approved"
        effective_decl = decl if decl and decl_status == "approved" else None

        pan = validate_pan_for_tds(db, employee_id)

        existing = (
            db.query(TdsAnnualSummary)
            .filter_by(employee_id=employee_id, financial_year=financial_year)
            .first()
        )
        if existing is None:
            existing = TdsAnnualSummary(
                employee_id=employee_id, financial_year=financial_year
            )
            db.add(existing)

        std_ded = 75000.0 if regime == "new" else 50000.0
        existing.pan_number           = pan
        existing.tax_regime           = regime
        existing.gross_annual_income  = round(total_gross * 12 / max(len(rows), 1), 2)
        existing.standard_deduction   = std_ded
        existing.sec_80c_claimed      = effective_decl.sec_80c          if effective_decl else 0.0
        existing.sec_80d_claimed      = effective_decl.sec_80d          if effective_decl else 0.0
        existing.hra_exemption_claimed = effective_decl.hra_exemption   if effective_decl else 0.0
        existing.sec_24b_claimed      = effective_decl.sec_24b          if effective_decl else 0.0
        existing.sec_80ccd_claimed    = effective_decl.sec_80ccd        if effective_decl else 0.0
        existing.other_deductions_claimed = effective_decl.other_deductions if effective_decl else 0.0
        total_deductions = std_ded + (
            (existing.sec_80c_claimed + existing.sec_80d_claimed + existing.hra_exemption_claimed
             + existing.sec_24b_claimed + existing.sec_80ccd_claimed + existing.other_deductions_claimed)
            if regime == "old" else 0.0
        )
        existing.total_deductions     = round(total_deductions, 2)
        existing.taxable_income       = round(annual_taxable, 2)
        existing.total_tds_deducted   = round(total_tds, 2)

        if commit:
            db.commit()
        else:
            db.flush()
    except Exception as exc:
        log.warning("upsert_tds_annual_summary failed for emp=%d fy=%s: %s",
                    employee_id, financial_year, exc)


def _current_financial_year() -> str:
    """Return the current Indian financial year string, e.g. '2025-26'.

    Uses IST (UTC+5:30) so the April 1 boundary is correct regardless of
    the server's local timezone.
    """
    ist = datetime.now().utcoffset()   # fallback
    try:
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        today  = datetime.now(tz=ist_tz).date()
    except Exception:
        today = date.today()

    if today.month >= 4:
        return f"{today.year}-{str(today.year + 1)[2:]}"
    return f"{today.year - 1}-{str(today.year)[2:]}"


# ─── Compliance Summary ───────────────────────────────────────────────────────

def get_compliance_summary(db: Session, run_id: int) -> dict:
    """Aggregate PF / ESI / PT totals for a payroll run — for compliance reports."""
    rows = (
        db.query(PayrollRunEmployee)
        .filter(PayrollRunEmployee.run_id == run_id)
        .all()
    )
    return {
        "total_employees":    len(rows),
        "pf_employee_total":  round(sum(r.employee_pf             for r in rows), 2),
        "pf_employer_total":  round(sum(r.employer_pf             for r in rows), 2),
        "pf_combined":        round(sum(r.employee_pf + r.employer_pf for r in rows), 2),
        "esi_employee_total": round(sum(r.employee_esi            for r in rows), 2),
        "esi_employer_total": round(sum(r.employer_esi            for r in rows), 2),
        "esi_combined":       round(sum(r.employee_esi + r.employer_esi for r in rows), 2),
        "pt_total":           round(sum(r.professional_tax        for r in rows), 2),
        "tds_total":          round(sum(r.tds                     for r in rows), 2),
    }
