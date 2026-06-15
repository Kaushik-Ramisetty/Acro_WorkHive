"""Services for the Excel-schema-aligned payroll tables:
- SalaryComponent  (reference master)
- EmployeeSalary   (per-employee salary history)
- TaxDeduction     (per-employee per-month tax ledger)
- Reimbursement    (expense claims)
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payroll_extended import (
    SalaryComponent,
    EmployeeSalary,
    TaxDeduction,
    Reimbursement,
)
from app.models.payroll import SalaryStructure, PayrollRun, PayrollRunEmployee
from app.models.employee import Employee


# ─── Default salary components (seeded once) ─────────────────────────────────

_DEFAULT_COMPONENTS = [
    {"component_code": "BASIC",   "component_name": "Basic Pay",              "component_type": "Earning",
     "calculation_type": "Fixed",            "default_value": 0,  "is_taxable": True,  "pf_applicable": True,  "esi_applicable": True,  "display_order": 1, "remarks": "Core salary component"},
    {"component_code": "HRA",     "component_name": "House Rent Allowance",   "component_type": "Earning",
     "calculation_type": "Percent_of_Basic", "default_value": 40, "is_taxable": True,  "pf_applicable": False, "esi_applicable": True,  "display_order": 2, "remarks": "40% of Basic (private sector default)"},
    {"component_code": "DA",      "component_name": "Dearness Allowance",     "component_type": "Earning",
     "calculation_type": "Percent_of_Basic", "default_value": 0,  "is_taxable": True,  "pf_applicable": True,  "esi_applicable": True,  "display_order": 3, "remarks": "DA — 0% default for private sector"},
    {"component_code": "SPECIAL", "component_name": "Special Allowance",      "component_type": "Earning",
     "calculation_type": "Residual",         "default_value": 0,  "is_taxable": True,  "pf_applicable": False, "esi_applicable": True,  "display_order": 4, "remarks": "Balancing component"},
    {"component_code": "TRANSPORT","component_name": "Transport Allowance",   "component_type": "Earning",
     "calculation_type": "Fixed",            "default_value": 1600, "is_taxable": True, "pf_applicable": False, "esi_applicable": False, "display_order": 5, "remarks": "Fixed ₹1,600/month"},
    {"component_code": "MEDICAL", "component_name": "Medical Allowance",      "component_type": "Earning",
     "calculation_type": "Fixed",            "default_value": 1250, "is_taxable": True, "pf_applicable": False, "esi_applicable": False, "display_order": 6, "remarks": "Fixed ₹1,250/month"},
    {"component_code": "PF_EMP",  "component_name": "Provident Fund (Employee)","component_type": "Deduction",
     "calculation_type": "Percent_of_Basic", "default_value": 12, "is_taxable": False, "pf_applicable": True,  "esi_applicable": False, "display_order": 7, "remarks": "12% of Basic, capped at ₹15,000 wage"},
    {"component_code": "PF_ER",   "component_name": "Provident Fund (Employer)","component_type": "Employer_Contribution",
     "calculation_type": "Percent_of_Basic", "default_value": 12, "is_taxable": False, "pf_applicable": True,  "esi_applicable": False, "display_order": 8, "remarks": "12% of Basic — employer CTC component"},
    {"component_code": "ESI_EMP", "component_name": "ESI (Employee)",         "component_type": "Deduction",
     "calculation_type": "Percent_of_Gross", "default_value": 0.75,"is_taxable": False,"pf_applicable": False, "esi_applicable": True,  "display_order": 9, "remarks": "0.75% of Gross, only if Gross ≤ ₹21,000"},
    {"component_code": "ESI_ER",  "component_name": "ESI (Employer)",         "component_type": "Employer_Contribution",
     "calculation_type": "Percent_of_Gross", "default_value": 3.25,"is_taxable": False,"pf_applicable": False, "esi_applicable": True,  "display_order": 10,"remarks": "3.25% of Gross — employer CTC component"},
    {"component_code": "PT",      "component_name": "Professional Tax",       "component_type": "Deduction",
     "calculation_type": "Slab",             "default_value": 200, "is_taxable": False, "pf_applicable": False, "esi_applicable": False, "display_order": 11,"remarks": "State-wise slab, max ₹200/month"},
    {"component_code": "TDS",     "component_name": "Tax Deducted at Source", "component_type": "Deduction",
     "calculation_type": "Slab",             "default_value": 0,   "is_taxable": False, "pf_applicable": False, "esi_applicable": False, "display_order": 12,"remarks": "Estimated TDS per old/new tax regime"},
]


def seed_salary_components(db: Session) -> None:
    """Idempotent seed of salary component master data."""
    for comp in _DEFAULT_COMPONENTS:
        exists = db.query(SalaryComponent).filter(
            SalaryComponent.component_code == comp["component_code"]
        ).first()
        if not exists:
            db.add(SalaryComponent(**comp))
    db.commit()


# ─── SalaryComponent CRUD ─────────────────────────────────────────────────────

def list_salary_components(db: Session, active_only: bool = True) -> list[SalaryComponent]:
    q = db.query(SalaryComponent)
    if active_only:
        q = q.filter(SalaryComponent.is_active.is_(True))
    return q.order_by(SalaryComponent.display_order).all()


def get_salary_component(db: Session, code: str) -> Optional[SalaryComponent]:
    return db.query(SalaryComponent).filter(SalaryComponent.component_code == code).first()


def upsert_salary_component(db: Session, data: dict) -> SalaryComponent:
    code = data.get("component_code", "")
    existing = db.query(SalaryComponent).filter(SalaryComponent.component_code == code).first()
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    comp = SalaryComponent(**data)
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


# ─── EmployeeSalary CRUD ──────────────────────────────────────────────────────

def sync_employee_salary_from_structure(db: Session, structure: SalaryStructure) -> EmployeeSalary:
    """Create/update an EmployeeSalary row that mirrors a SalaryStructure row.

    Marks previous active row as Superseded.
    """
    db.query(EmployeeSalary).filter(
        EmployeeSalary.employee_id == structure.employee_id,
        EmployeeSalary.status == "Active",
    ).update({"status": "Superseded"})

    es = EmployeeSalary(
        employee_id=structure.employee_id,
        salary_structure_id=structure.id,
        effective_from=structure.effective_from or date.today(),
        monthly_ctc=round(structure.annual_ctc / 12, 2) if structure.annual_ctc else 0.0,
        basic=structure.basic,
        hra=structure.hra,
        da=structure.da,
        special_allowance=structure.special_allowance,
        pf_employee=structure.pf_employee,
        pf_employer=structure.pf_employer,
        esi_employee=structure.esi_employee,
        professional_tax=structure.professional_tax,
        tds_estimated=structure.tds,
        net_estimated=structure.net_monthly,
        status="Active",
        remarks="Auto-synced from salary_structures",
    )
    db.add(es)
    db.commit()
    db.refresh(es)
    return es


def list_employee_salary(db: Session, employee_id: Optional[int] = None) -> list[EmployeeSalary]:
    q = db.query(EmployeeSalary)
    if employee_id:
        q = q.filter(EmployeeSalary.employee_id == employee_id)
    return q.order_by(EmployeeSalary.effective_from.desc()).all()


def get_active_employee_salary(db: Session, employee_id: int) -> Optional[EmployeeSalary]:
    return (
        db.query(EmployeeSalary)
        .filter(EmployeeSalary.employee_id == employee_id, EmployeeSalary.status == "Active")
        .order_by(EmployeeSalary.effective_from.desc())
        .first()
    )


# ─── TaxDeduction ─────────────────────────────────────────────────────────────

def populate_tax_deductions_for_run(db: Session, run: PayrollRun) -> int:
    """Auto-populate tax_deductions rows from payroll_run_employees when a run is approved/closed.

    Idempotent: skips employees already recorded for this run.
    Returns count of rows inserted.
    """
    # Derive financial year from run period
    start = run.pay_period_start
    fy = f"{start.year}-{str(start.year + 1)[-2:]}" if start.month >= 4 else f"{start.year - 1}-{str(start.year)[-2:]}"
    month_num = start.month
    year_num = start.year

    existing_emp_ids = {
        r[0] for r in db.query(TaxDeduction.employee_id)
        .filter(TaxDeduction.run_id == run.id).all()
    }

    run_employees = db.query(PayrollRunEmployee).filter(PayrollRunEmployee.run_id == run.id).all()
    inserted = 0
    for pre in run_employees:
        if pre.employee_id in existing_emp_ids:
            continue
        total = round(
            pre.employee_pf + pre.employee_esi + pre.professional_tax + pre.tds, 2
        )
        td = TaxDeduction(
            payroll_run_employee_id=pre.id,
            employee_id=pre.employee_id,
            run_id=run.id,
            financial_year=fy,
            month=month_num,
            year=year_num,
            pf_employee=pre.employee_pf,
            esi_employee=pre.employee_esi,
            professional_tax=pre.professional_tax,
            tds=pre.tds,
            total_tax_deductions=total,
            remarks=f"Auto-generated from payroll run {run.id}",
        )
        db.add(td)
        inserted += 1
    db.commit()
    return inserted


def list_tax_deductions(
    db: Session,
    run_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    financial_year: Optional[str] = None,
) -> list[TaxDeduction]:
    q = db.query(TaxDeduction)
    if run_id:
        q = q.filter(TaxDeduction.run_id == run_id)
    if employee_id:
        q = q.filter(TaxDeduction.employee_id == employee_id)
    if financial_year:
        q = q.filter(TaxDeduction.financial_year == financial_year)
    return q.order_by(TaxDeduction.year.desc(), TaxDeduction.month.desc()).all()


# ─── Reimbursement ────────────────────────────────────────────────────────────

def create_reimbursement(db: Session, data: dict) -> Reimbursement:
    r = Reimbursement(
        employee_id=data["employee_id"],
        claim_type=data["claim_type"],
        claim_amount=data["claim_amount"],
        remarks=data.get("remarks"),
        status="pending",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def list_reimbursements(
    db: Session,
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    run_id: Optional[int] = None,
) -> list[Reimbursement]:
    q = db.query(Reimbursement)
    if employee_id:
        q = q.filter(Reimbursement.employee_id == employee_id)
    if status:
        q = q.filter(Reimbursement.status == status)
    if run_id:
        q = q.filter(Reimbursement.payroll_run_id == run_id)
    return q.order_by(Reimbursement.created_at.desc()).all()


def get_reimbursement(db: Session, reimbursement_id: int) -> Optional[Reimbursement]:
    return db.query(Reimbursement).filter(Reimbursement.id == reimbursement_id).first()


def approve_reimbursement(db: Session, reimbursement_id: int, actor: Employee, approved_amount: Optional[float] = None) -> Reimbursement:
    r = get_reimbursement(db, reimbursement_id)
    if not r:
        raise ValueError("Reimbursement not found")
    if r.status != "pending":
        raise ValueError(f"Cannot approve: current status is '{r.status}'")
    r.status = "approved"
    r.approved_by_id = actor.id
    r.approved_at = datetime.utcnow()
    r.approved_amount = approved_amount if approved_amount is not None else r.claim_amount
    db.commit()
    db.refresh(r)
    return r


def reject_reimbursement(db: Session, reimbursement_id: int, actor: Employee, remarks: Optional[str] = None) -> Reimbursement:
    r = get_reimbursement(db, reimbursement_id)
    if not r:
        raise ValueError("Reimbursement not found")
    if r.status not in ("pending", "approved"):
        raise ValueError(f"Cannot reject: current status is '{r.status}'")
    r.status = "rejected"
    r.approved_by_id = actor.id
    r.approved_at = datetime.utcnow()
    if remarks:
        r.remarks = remarks
    db.commit()
    db.refresh(r)
    return r


def mark_reimbursement_paid(db: Session, reimbursement_id: int, run_id: Optional[int] = None) -> Reimbursement:
    r = get_reimbursement(db, reimbursement_id)
    if not r:
        raise ValueError("Reimbursement not found")
    if r.status != "approved":
        raise ValueError(f"Cannot mark paid: current status is '{r.status}'")
    r.status = "paid"
    if run_id:
        r.payroll_run_id = run_id
    db.commit()
    db.refresh(r)
    return r


def cancel_reimbursement(db: Session, reimbursement_id: int) -> Reimbursement:
    r = get_reimbursement(db, reimbursement_id)
    if not r:
        raise ValueError("Reimbursement not found")
    if r.status in ("paid",):
        raise ValueError("Cannot cancel a paid reimbursement")
    r.status = "cancelled"
    db.commit()
    db.refresh(r)
    return r
