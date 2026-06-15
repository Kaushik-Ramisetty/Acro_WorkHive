"""CTC Calculation Engine — Indian payroll salary breakup.

Given an annual CTC, produces the complete monthly salary structure:

  Annual CTC
  ├── Gross Monthly       = Annual CTC / 12
  ├── Salary Component Base = Annual CTC − Employer PF Annual
  ├── Basic Annual        = Salary Component Base × 50%
  ├── HRA Monthly         = Basic Monthly × 40%
  ├── LTA Monthly         = Basic Monthly × 16.66%
  ├── Transport Annual    = ₹5,000 × 12 = ₹60,000
  ├── Special Allowance   = Gross − Basic − HRA − LTA − Transport − Employer PF
  └── Employer PF Annual  = ₹21,600  (employer contribution — subtracted from take-home)

Gross Monthly = Annual CTC / 12.  Employer PF is an employer-side contribution
reported separately; it does not reduce gross salary, but it reduces take-home
under the company Excel CTC flow.

Employee deductions (monthly):
  ├── Employee PF   = min(Basic × 12%, ₹1,800)
  ├── Employee ESI  = 0 when gross > ₹21,000 (ESI threshold)
  ├── Professional Tax = ₹200 when gross > ₹21,000, else ₹0
  ├── Employer PF   = ₹1,800
  └── TDS           = 0 when CTC ≤ ₹12,00,000; else Annual Tax / 12

Net Monthly = Gross − Employee PF − Employer PF − ESI − PT − TDS

Tax slabs (New Regime FY 2025-26, Budget 2025):
  0 – 4 L   →  0%
  4 – 8 L   →  5%
  8 – 12 L  → 10%
  12 – 16 L → 15%
  16 – 20 L → 20%
  20 – 24 L → 25%
  > 24 L    → 30%
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payroll_extended import StatutorySettings

log = logging.getLogger("hrms.ctc")

# ─── Excel-aligned constants ──────────────────────────────────────────────────
_EMPLOYER_PF_ANNUAL   = 21_600.0   # fixed ₹21,600/year (12% × ₹15,000 × 12)
_EMPLOYER_PF_MONTHLY  =  1_800.0   # ₹1,800/month
_BASIC_PCT            =     0.50   # 50% of salary component base
_HRA_PCT              =     0.40   # 40% of Basic
_LTA_PCT              =     0.1666 # 16.66% of Basic
_TRANSPORT_MONTHLY    =  5_000.0   # flat ₹5,000/month
_TRANSPORT_ANNUAL     = 60_000.0   # flat ₹60,000/year
_ESI_GROSS_THRESHOLD  = 21_000.0   # ESI applicable only when gross ≤ ₹21,000
_PT_GROSS_THRESHOLD   = 21_000.0   # PT = ₹200 when gross > ₹21,000
_PT_AMOUNT            =    200.0
_EMPLOYEE_PF_RATE     =     0.12   # 12%
_EMPLOYEE_PF_CAP      =  1_800.0   # max ₹1,800/month


@dataclass
class SalaryBreakup:
    """Full monthly salary breakup — mirrors SalaryStructure fields."""
    # Earnings
    basic: float
    hra: float
    da: float               # Dearness Allowance (always 0 for private sector)
    lta: float              # Leave Travel Allowance (stored in other_allowances in DB)
    special_allowance: float
    transport_allowance: float
    medical_allowance: float
    other_allowances: float
    gross_monthly: float

    # Take-home deductions
    pf_employee: float
    esi_employee: float
    professional_tax: float
    tds: float
    total_deductions: float

    # Employer contributions (part of CTC, not in-hand)
    pf_employer: float
    esi_employer: float

    # Net in-hand
    net_monthly: float

    # Annual
    annual_ctc: float


def _get_settings(db: Session) -> StatutorySettings:
    """Return the active statutory settings row, or default values if none seeded."""
    settings = (
        db.query(StatutorySettings)
        .filter(StatutorySettings.is_active.is_(True))
        .order_by(StatutorySettings.effective_from.desc())
        .first()
    )
    return settings if settings else _default_settings()


def _default_settings() -> StatutorySettings:
    s = StatutorySettings.__new__(StatutorySettings)
    s.pf_employee_rate         = _EMPLOYEE_PF_RATE
    s.pf_employer_rate         = 0.12
    s.pf_wage_ceiling          = 15_000.0
    s.esi_employee_rate        = 0.0075
    s.esi_employer_rate        = 0.0325
    s.esi_wage_ceiling         = _ESI_GROSS_THRESHOLD
    s.gratuity_rate            = 0.0481
    s.gratuity_eligibility_years = 5.0
    s.basic_pct_of_ctc         = _BASIC_PCT
    s.hra_pct_of_basic         = _HRA_PCT
    s.transport_allowance      = _TRANSPORT_MONTHLY
    s.medical_allowance        = 0.0
    # PT slab: ₹200 when gross > ₹21,000
    s.pt_slab_json = '[{"min":0,"max":21000,"pt":0},{"min":21001,"max":9999999,"pt":200}]'
    return s


_CENT = Decimal("0.01")


def _to_decimal(v: float | Decimal | int | None) -> Decimal:
    return Decimal(str(v or 0))


def _round2(v: float | Decimal) -> float:
    return float(_to_decimal(v).quantize(_CENT, rounding=ROUND_HALF_UP))


def _sum_money(*values: float | Decimal | int | None) -> float:
    return _round2(sum((_to_decimal(v) for v in values), Decimal("0")))


def _subtract_money(base: float | Decimal, *values: float | Decimal | int | None) -> float:
    return _round2(_to_decimal(base) - sum((_to_decimal(v) for v in values), Decimal("0")))


def compute_from_ctc(
    annual_ctc: float,
    db: Session,
    extra_other_allowances: float = 0.0,
    monthly_tds: float = 0.0,
) -> SalaryBreakup:
    """Compute monthly salary breakup from annual CTC.

    Gross formula
    -------------
    Gross Monthly = Annual CTC / 12.
    Employer PF (₹1,800/month) is an employer-side contribution reported
    separately under CTC; it does NOT reduce the employee's gross salary.

    Excel CTC rounding policy
    -------------------
    All arithmetic uses ``decimal.Decimal``.  The *Special Allowance* is the
    residual absorber:

        component_base = annual_ctc − annual_employer_pf
        basic          = round((component_base × 50%) / 12, 2)
        hra            = round(basic × 40%, 2)
        lta            = round(basic × 16.66%, 2)
        special        = gross − basic − hra − lta − transport − employer_pf − other

    where ``gross_target = round(annual_ctc / 12, 2)``.
    This mirrors the company Excel sheet: employer PF is part of CTC and gross,
    but the earning components are calculated on CTC after removing employer PF.

    TDS policy (company rule)
    -------------------------
    If ``annual_ctc ≤ ₹12,00,000``:
        TDS = ₹0  (projected taxable income within exemption threshold)
    If ``annual_ctc > ₹12,00,000``:
        TDS computed from annualised gross using existing slab logic.

    The ``monthly_tds`` parameter overrides automatic computation when the
    caller already has a TDS value (e.g. from a tax declaration refresh).
    """
    # ── Step 1: Decimal-precision annual component calculation ───────────────
    _D = Decimal

    ctc_d = _D(str(annual_ctc))

    employer_pf_annual_d = _D(str(_EMPLOYER_PF_ANNUAL))
    component_base_d = ctc_d - employer_pf_annual_d

    # Gross Monthly = Annual CTC / 12.
    gross_target = _round2(ctc_d / 12)

    # ── Step 2: Monthly values — each rounded to 2 decimal places ────────────
    basic     = _round2((component_base_d * _D(str(_BASIC_PCT))) / 12)
    hra       = _round2(_to_decimal(basic) * _D(str(_HRA_PCT)))
    lta       = _round2(_to_decimal(basic) * _D(str(_LTA_PCT)))
    transport = _TRANSPORT_MONTHLY
    employer_pf_monthly = _EMPLOYER_PF_MONTHLY
    medical   = 0.0
    other     = _round2(extra_other_allowances)

    # ── Step 3: Special allowance residual ───────────────────────────────────
    special = _subtract_money(gross_target, basic, hra, lta, transport, employer_pf_monthly, other)

    # Gross remains Annual CTC / 12; employer PF is part of CTC, not an earning component.
    gross = gross_target

    # ── Step 4: Employer contributions ───────────────────────────────────────
    pf_employer  = employer_pf_monthly   # fixed ₹1,800
    esi_employer = 0.0
    if gross <= _ESI_GROSS_THRESHOLD:
        s = _get_settings(db)
        esi_employer = _round2(s.esi_employer_rate * gross)

    # ── Step 5: Employee deductions ──────────────────────────────────────────
    pf_employee  = _round2(min(basic * _EMPLOYEE_PF_RATE, _EMPLOYEE_PF_CAP))
    esi_employee = 0.0
    if gross <= _ESI_GROSS_THRESHOLD:
        s = _get_settings(db)
        esi_employee = _round2(s.esi_employee_rate * gross)

    # PT = ₹200 when gross > ₹21,000, else ₹0
    pt = _PT_AMOUNT if gross > _PT_GROSS_THRESHOLD else 0.0

    # ── Step 6: TDS — company policy + slab calculation ──────────────────────
    # Company rule: projected taxable income threshold = annual CTC.
    #   CTC ≤ ₹12,00,000  →  TDS = ₹0  (within tax exemption threshold)
    #   CTC > ₹12,00,000  →  TDS calculated from annualised gross (NOT from CTC)
    # The caller may pass monthly_tds to override (e.g. from tax declarations).
    if monthly_tds == 0.0:
        if annual_ctc <= 1_200_000.0:
            monthly_tds = 0.0   # Company rule: annual CTC within exemption threshold
        else:
            from app.services.statutory_service import estimate_monthly_tds
            annual_gross_for_tds = gross * 12
            monthly_tds = estimate_monthly_tds(
                annual_gross=annual_gross_for_tds,
                opted_new_regime=True,
                employee_label=f"CTC_preview_annualCTC={annual_ctc:,.0f}",
            )

    tds = _round2(monthly_tds)

    # ── Step 7: Totals ────────────────────────────────────────────────────────
    total_deductions = _sum_money(pf_employee, pf_employer, esi_employee, pt, tds)
    net = _subtract_money(gross, total_deductions)

    # Preserve the exact user-entered annual CTC.
    # DO NOT recompute from rounded gross — that produces a paisa mismatch
    # (e.g. ₹10,00,000 → ₹10,00,000.08 in the old approach).
    annual_ctc_stored = annual_ctc

    # annual_tax for audit logging (reconstructed from monthly TDS × 12)
    annual_tax = _round2(tds * 12)

    # gross_reconciliation_difference — should be 0 after this fix
    _component_sum = _sum_money(basic, hra, lta, transport, special, other, pf_employer)
    gross_recon_diff = _subtract_money(gross, _component_sum)

    # ── Structured validation log (all required fields) ──────────────────────
    log.info(
        "[CTC] annual_ctc=%.2f | "
        "basic=%.2f | hra=%.2f | lta=%.2f | "
        "transport=%.2f | special_allowance=%.2f | "
        "gross=%.2f | "
        "employee_pf=%.2f | employer_pf=%.2f | esi=%.2f | pt=%.2f | "
        "annual_gross=%.2f | annual_tax=%.2f | monthly_tds=%.2f | "
        "net=%.2f | gross_reconciliation_difference=%.2f",
        annual_ctc,
        basic, hra, lta, transport, special, gross,
        pf_employee, pf_employer, esi_employee, pt,
        gross * 12, annual_tax, tds,
        net, gross_recon_diff,
    )

    return SalaryBreakup(
        basic=basic,
        hra=hra,
        da=0.0,
        lta=lta,
        special_allowance=special,
        transport_allowance=transport,
        medical_allowance=medical,
        other_allowances=other,
        gross_monthly=gross,
        pf_employee=pf_employee,
        esi_employee=esi_employee,
        professional_tax=pt,
        tds=tds,
        total_deductions=total_deductions,
        pf_employer=pf_employer,
        esi_employer=esi_employer,
        net_monthly=net,
        annual_ctc=annual_ctc_stored,
    )


def apply_lop(breakup: SalaryBreakup, lop_days: int, working_days: int) -> SalaryBreakup:
    """Deduct Loss-of-Pay from a computed breakup.

    All earnings components are scaled proportionally.
    PT is NOT reduced (fixed per month in most Indian states).
    """
    if lop_days <= 0 or working_days <= 0:
        return breakup

    lop_days = min(lop_days, working_days)
    pay_days = working_days - lop_days
    ratio = pay_days / working_days

    def scale(v: float) -> float:
        return _round2(v * ratio)

    basic     = scale(breakup.basic)
    hra       = scale(breakup.hra)
    da        = scale(breakup.da)
    lta       = scale(breakup.lta)
    special   = scale(breakup.special_allowance)
    transport = scale(breakup.transport_allowance)
    medical   = scale(breakup.medical_allowance)
    other     = scale(breakup.other_allowances)
    # Employer PF is NOT scaled — fixed at ₹1,800 per policy
    pf_employer  = breakup.pf_employer
    gross        = _sum_money(basic, hra, da, lta, special, transport, medical, other, pf_employer)

    # Employee PF is NOT scaled — fixed at ₹1,800 per policy
    pf_employee  = breakup.pf_employee
    esi_employee = scale(breakup.esi_employee)
    esi_employer = scale(breakup.esi_employer)
    pt           = breakup.professional_tax  # PT is NOT reduced for LOP
    tds          = scale(breakup.tds)

    # Employer PF is NOT in employee deductions — only employee-side deductions affect net_pay
    total_deductions = _sum_money(pf_employee, esi_employee, pt, tds)
    net = _subtract_money(gross, total_deductions)

    return SalaryBreakup(
        basic=basic,
        hra=hra,
        da=da,
        lta=lta,
        special_allowance=special,
        transport_allowance=transport,
        medical_allowance=medical,
        other_allowances=other,
        gross_monthly=gross,
        pf_employee=pf_employee,
        esi_employee=esi_employee,
        professional_tax=pt,
        tds=tds,
        total_deductions=total_deductions,
        pf_employer=pf_employer,
        esi_employer=esi_employer,
        net_monthly=net,
        annual_ctc=breakup.annual_ctc,
    )
