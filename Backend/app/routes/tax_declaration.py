"""Tax Declaration Approval Flow.

Implements the production-grade declaration workflow:

  Employee:
    - Submit their 80C/HRA/NPS/etc. declarations for the current FY.
    - Declaration starts in 'draft' state.
    - After submitting (status → 'submitted'), locked until reviewed.
    - Cannot edit after cutoff unless admin reopens.

  Finance / HR:
    - Review submitted declarations.
    - APPROVE (status → 'approved') — declaration affects OLD regime TDS.
    - REJECT (status → 'rejected', rejection_reason MANDATORY) — reverts to new regime.

  Admin:
    - Can reopen a locked declaration (past cutoff) if employee needs to revise.

Policy enforced here:
  - NEW REGIME: declarations are irrelevant; TDS comes from slabs only.
  - OLD REGIME: ONLY status='approved' declarations are applied to TDS.
  - Draft/submitted/rejected → NEW REGIME is used as fallback for TDS.
  - After cutoff date: employees cannot change declarations unless admin reopens.

Prefix: /tax-declarations
Auth:   Varies per endpoint (see decorators below).
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, role_required
from app.models.employee import Employee
from app.models.payroll_extended import EmployeeTaxDeclaration, DeclarationAuditLog
from app.services.statutory_service import (
    _current_financial_year,
    refresh_tds_for_employee,
)

logger = logging.getLogger("hrms.tax_declaration")

router = APIRouter(prefix="/tax-declarations", tags=["Tax Declarations"])

_FinanceOrAdmin = Depends(role_required("finance", "admin", "finance_head"))
_AnyStaff       = Depends(role_required("finance", "admin", "finance_head", "manager"))


# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class DeclarationUpsert(BaseModel):
    """Employee submits their tax declarations."""
    financial_year: Optional[str] = None          # defaults to current FY
    opted_new_regime: bool = True                  # default: New Regime

    # Old regime declarations (only used when opted_new_regime=False and APPROVED)
    sec_80c: float = Field(default=0.0, ge=0, le=150000)
    sec_80d: float = Field(default=0.0, ge=0, le=50000)
    sec_80ccd: float = Field(default=0.0, ge=0, le=50000)
    hra_exemption: float = Field(default=0.0, ge=0)
    sec_24b: float = Field(default=0.0, ge=0, le=200000)
    other_deductions: float = Field(default=0.0, ge=0)


class DeclarationRejectBody(BaseModel):
    rejection_reason: str = Field(..., min_length=5, description="Mandatory rejection reason (min 5 chars)")


class DeclarationReopenBody(BaseModel):
    reason: str = Field(..., min_length=5, description="Reason for reopening past-cutoff declaration")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_or_create_decl(
    db: Session, employee_id: int, financial_year: str
) -> EmployeeTaxDeclaration:
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=financial_year)
        .first()
    )
    if not decl:
        decl = EmployeeTaxDeclaration(
            employee_id=employee_id,
            financial_year=financial_year,
            opted_new_regime=True,
            declaration_status="draft",
        )
        db.add(decl)
        db.flush()
    return decl


def _append_audit(
    db: Session,
    decl: EmployeeTaxDeclaration,
    action: str,
    old_status: Optional[str],
    new_status: Optional[str],
    performed_by_id: Optional[int],
    reason: Optional[str] = None,
) -> None:
    try:
        audit = DeclarationAuditLog(
            declaration_id=decl.id,
            employee_id=decl.employee_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            performed_by_id=performed_by_id,
            reason=reason,
        )
        db.add(audit)
    except Exception as exc:
        logger.warning("Failed to write declaration audit log: %s", exc)


def _is_past_cutoff(financial_year: str) -> bool:
    """Check if current date is past the declaration cutoff (Jan 31 of the FY end year by default).

    Cutoff is configurable via StatutorySettings.declaration_cutoff_month/day.
    Default: January 31 of the current financial year's closing year.
    """
    try:
        from app.services.statutory_service import get_active_settings
        from app.db.session import SessionLocal
        with SessionLocal() as _db:
            s = get_active_settings(_db)
            cutoff_month = getattr(s, "declaration_cutoff_month", 1) if s else 1
            cutoff_day   = getattr(s, "declaration_cutoff_day",   31) if s else 31
    except Exception:
        cutoff_month = 1
        cutoff_day   = 31

    # Parse FY end year from "2025-26" → 2026
    try:
        end_year = int(financial_year.split("-")[0]) + 1
    except (ValueError, IndexError):
        return False

    cutoff = date(end_year, cutoff_month, cutoff_day)
    return date.today() > cutoff


def _serialize_decl(decl: EmployeeTaxDeclaration) -> dict:
    return {
        "id": decl.id,
        "employee_id": decl.employee_id,
        "financial_year": decl.financial_year,
        "declaration_status": getattr(decl, "declaration_status", "draft"),
        "opted_new_regime": decl.opted_new_regime,
        "sec_80c": decl.sec_80c,
        "sec_80d": decl.sec_80d,
        "sec_80ccd": decl.sec_80ccd,
        "hra_exemption": decl.hra_exemption,
        "sec_24b": decl.sec_24b,
        "other_deductions": decl.other_deductions,
        "is_locked": getattr(decl, "is_locked", False),
        "lock_reason": getattr(decl, "lock_reason", None),
        "rejection_reason": getattr(decl, "rejection_reason", None),
        "reviewed_by_id": getattr(decl, "reviewed_by_id", None),
        "reviewed_at": getattr(decl, "reviewed_at", None),
        "submitted_at": decl.submitted_at.isoformat() if decl.submitted_at else None,
        "is_effective_for_tds": (
            decl.opted_new_regime or
            getattr(decl, "declaration_status", "draft") == "approved"
        ),
        "created_at": decl.created_at.isoformat() if decl.created_at else None,
        "updated_at": decl.updated_at.isoformat() if decl.updated_at else None,
    }


# ─── Employee: Save/update their own declaration ───────────────────────────────

@router.put(
    "/my",
    summary="[Employee] Save/update own tax declaration for current FY",
)
def save_my_declaration(
    body: DeclarationUpsert,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_user),
):
    """Employee saves their tax declaration.

    - Can only save when declaration_status is 'draft' or 'rejected'.
    - Cannot save after 'submitted' (must wait for review outcome).
    - Cannot save after cutoff date unless admin has reopened.
    """
    fy = body.financial_year or _current_financial_year()
    decl = _get_or_create_decl(db, current.id, fy)
    decl_status = getattr(decl, "declaration_status", "draft")

    # Status gate
    if decl_status == "submitted":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Declaration is already submitted and awaiting review. "
                   "You cannot edit it until Finance/HR completes the review.",
        )
    if decl_status == "approved":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Declaration is already approved. Submit a revision request to Finance.",
        )

    # Cutoff gate
    if getattr(decl, "is_locked", False):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                f"Declaration is locked ({getattr(decl, 'lock_reason', 'past cutoff date')}). "
                "Contact Admin to reopen."
            ),
        )

    # Apply updates
    old_status = decl_status
    decl.opted_new_regime  = body.opted_new_regime
    decl.sec_80c           = body.sec_80c
    decl.sec_80d           = body.sec_80d
    decl.sec_80ccd         = body.sec_80ccd
    decl.hra_exemption     = body.hra_exemption
    decl.sec_24b           = body.sec_24b
    decl.other_deductions  = body.other_deductions
    if hasattr(decl, "declaration_status") and decl_status == "rejected":
        decl.declaration_status = "draft"   # Resets to draft so employee can re-submit

    _append_audit(db, decl, "save_draft", old_status, "draft", current.id)
    db.commit()
    return _serialize_decl(decl)


@router.post(
    "/my/submit",
    summary="[Employee] Submit declaration for Finance/HR review",
)
def submit_my_declaration(
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_user),
):
    """Submit declaration for review. Status changes to 'submitted'.

    Once submitted:
    - Employee cannot edit until reviewed (approved/rejected).
    - Finance/HR must approve before OLD regime TDS is applied.
    - Cutoff check: blocks submission after cutoff date.
    """
    fy = financial_year or _current_financial_year()
    decl = _get_or_create_decl(db, current.id, fy)
    decl_status = getattr(decl, "declaration_status", "draft")

    if decl_status == "submitted":
        raise HTTPException(400, detail="Declaration already submitted.")
    if decl_status == "approved":
        raise HTTPException(400, detail="Declaration already approved.")

    if getattr(decl, "is_locked", False):
        raise HTTPException(
            403,
            detail=(
                f"Declaration is locked ({getattr(decl, 'lock_reason', 'past cutoff date')}). "
                "Contact Admin to reopen."
            ),
        )

    # Cutoff check
    if _is_past_cutoff(fy):
        raise HTTPException(
            403,
            detail=(
                f"The declaration submission cutoff for FY {fy} has passed. "
                "New declarations cannot be submitted. Contact Admin if an exception is needed."
            ),
        )

    old_status = decl_status
    decl.declaration_status = "submitted"
    decl.submitted_at = datetime.utcnow()
    if hasattr(decl, "rejection_reason"):
        decl.rejection_reason = None   # Clear previous rejection reason on resubmit

    _append_audit(db, decl, "submit", old_status, "submitted", current.id)
    db.commit()
    logger.info("Declaration submitted: employee_id=%d, FY=%s", current.id, fy)
    return _serialize_decl(decl)


@router.get(
    "/my",
    summary="[Employee] View own declaration for current FY",
)
def get_my_declaration(
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_user),
):
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=current.id, financial_year=fy)
        .first()
    )
    if not decl:
        return {
            "employee_id": current.id,
            "financial_year": fy,
            "declaration_status": "not_submitted",
            "opted_new_regime": True,
            "message": "No declaration found. Default: New Regime (TDS from slabs only).",
        }
    return _serialize_decl(decl)


# ─── Finance / HR: Review declarations ───────────────────────────────────────

@router.get(
    "/pending",
    summary="[Finance/Admin] List all pending (submitted) declarations for review",
)
def list_pending_declarations(
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = _FinanceOrAdmin,
):
    fy = financial_year or _current_financial_year()
    decls = (
        db.query(EmployeeTaxDeclaration)
        .filter(
            EmployeeTaxDeclaration.financial_year == fy,
            EmployeeTaxDeclaration.declaration_status == "submitted",
        )
        .all()
    )
    return [_serialize_decl(d) for d in decls]


@router.get(
    "/all",
    summary="[Finance/Admin] List ALL declarations for a FY (any status)",
)
def list_all_declarations(
    financial_year: Optional[str] = None,
    decl_status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = _FinanceOrAdmin,
):
    fy = financial_year or _current_financial_year()
    q = db.query(EmployeeTaxDeclaration).filter(
        EmployeeTaxDeclaration.financial_year == fy
    )
    if decl_status:
        q = q.filter(EmployeeTaxDeclaration.declaration_status == decl_status)
    return [_serialize_decl(d) for d in q.all()]


@router.get(
    "/{employee_id}",
    summary="[Finance/Admin] View a specific employee's declaration",
)
def get_declaration_by_employee(
    employee_id: int,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = _FinanceOrAdmin,
):
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        raise HTTPException(404, detail=f"No declaration for employee {employee_id} in FY {fy}")
    return _serialize_decl(decl)


@router.post(
    "/{employee_id}/approve",
    summary="[Finance/Admin] Approve a submitted declaration — enables Old Regime TDS",
)
def approve_declaration(
    employee_id: int,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceOrAdmin,
):
    """Approve declaration.

    - Status must be 'submitted'.
    - After approval, declaration is used for OLD regime TDS computation.
    - TDS is immediately refreshed in the employee's salary structure.
    - Audit log entry is written.
    """
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        raise HTTPException(404, detail=f"No declaration for employee {employee_id} in FY {fy}")

    decl_status = getattr(decl, "declaration_status", "draft")
    if decl_status != "submitted":
        raise HTTPException(
            400,
            detail=f"Cannot approve declaration with status '{decl_status}'. "
                   "Only 'submitted' declarations can be approved.",
        )

    old_status = decl_status
    decl.declaration_status = "approved"
    decl.reviewed_by_id = actor.id
    decl.reviewed_at = datetime.utcnow()
    if hasattr(decl, "rejection_reason"):
        decl.rejection_reason = None   # Clear any previous rejection reason

    _append_audit(db, decl, "approve", old_status, "approved", actor.id)
    db.commit()

    # Refresh TDS immediately after approval
    try:
        refresh_tds_for_employee(db, employee_id, commit=True)
        logger.info(
            "TDS refreshed after declaration approval: employee_id=%d, FY=%s", employee_id, fy
        )
    except Exception as exc:
        logger.warning("TDS refresh failed after declaration approval (non-fatal): %s", exc)

    logger.info(
        "Declaration APPROVED: employee_id=%d, FY=%s, approved_by=%d",
        employee_id, fy, actor.id,
    )
    return _serialize_decl(decl)


@router.post(
    "/{employee_id}/reject",
    summary="[Finance/Admin] Reject a submitted declaration — rejection reason MANDATORY",
)
def reject_declaration(
    employee_id: int,
    body: DeclarationRejectBody,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: Employee = _FinanceOrAdmin,
):
    """Reject declaration.

    - Status must be 'submitted'.
    - Rejection reason is MANDATORY (min 5 chars).
    - After rejection, employee falls back to NEW regime for TDS.
    - Employee is notified (if email service is configured).
    - TDS is immediately refreshed (will now use New Regime).
    """
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        raise HTTPException(404, detail=f"No declaration for employee {employee_id} in FY {fy}")

    decl_status = getattr(decl, "declaration_status", "draft")
    if decl_status != "submitted":
        raise HTTPException(
            400,
            detail=f"Cannot reject declaration with status '{decl_status}'. "
                   "Only 'submitted' declarations can be rejected.",
        )

    old_status = decl_status
    decl.declaration_status = "rejected"
    decl.reviewed_by_id = actor.id
    decl.reviewed_at = datetime.utcnow()
    decl.rejection_reason = body.rejection_reason

    _append_audit(db, decl, "reject", old_status, "rejected", actor.id, body.rejection_reason)
    db.commit()

    # Refresh TDS — will fall back to New Regime since declaration is rejected
    try:
        refresh_tds_for_employee(db, employee_id, commit=True)
    except Exception as exc:
        logger.warning("TDS refresh failed after declaration rejection (non-fatal): %s", exc)

    # Notify employee
    try:
        emp = db.query(Employee).filter_by(id=employee_id).first()
        if emp:
            recipient = (getattr(emp, "official_email", None) or emp.email or "").strip()
            if recipient:
                from app.services.email_dispatcher import _send_email
                subject = f"Your tax declaration for FY {fy} was not approved"
                body_text = (
                    f"Hi {emp.first_name or 'Employee'},\n\n"
                    f"Your tax declaration for FY {fy} has been reviewed and NOT approved.\n\n"
                    f"Reason: {body.rejection_reason}\n\n"
                    "Your TDS will be computed under the New Tax Regime until you submit "
                    "a corrected declaration that is approved by Finance/HR.\n\n"
                    "Please log in to WorkHive to update and resubmit your declaration.\n"
                )
                _send_email(recipient, subject, body_text)
    except Exception as email_exc:
        logger.warning("Declaration rejection email failed (non-fatal): %s", email_exc)

    logger.info(
        "Declaration REJECTED: employee_id=%d, FY=%s, rejected_by=%d, reason=%s",
        employee_id, fy, actor.id, body.rejection_reason,
    )
    return _serialize_decl(decl)


# ─── Admin: Lock / Reopen declarations ────────────────────────────────────────

@router.post(
    "/{employee_id}/lock",
    summary="[Admin] Lock a declaration after cutoff (prevents employee edits)",
)
def lock_declaration(
    employee_id: int,
    reason: str = "Cutoff date passed — declaration locked for this FY.",
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: Employee = Depends(role_required("admin")),
):
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        raise HTTPException(404, detail=f"No declaration for employee {employee_id} in FY {fy}")

    decl.is_locked   = True
    decl.lock_reason = reason
    _append_audit(db, decl, "lock", None, None, actor.id, reason)
    db.commit()
    return {"ok": True, "message": f"Declaration for employee {employee_id} FY {fy} locked."}


@router.post(
    "/{employee_id}/reopen",
    summary="[Admin] Reopen a locked declaration so employee can revise",
)
def reopen_declaration(
    employee_id: int,
    body: DeclarationReopenBody,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: Employee = Depends(role_required("admin")),
):
    """Admin reopens a past-cutoff declaration. Employee can then edit and resubmit."""
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        raise HTTPException(404, detail=f"No declaration for employee {employee_id} in FY {fy}")

    old_status = getattr(decl, "declaration_status", "draft")
    decl.is_locked          = False
    decl.lock_reason        = None
    # If was approved, reopen to 'draft' so it can be re-reviewed
    if old_status == "approved":
        decl.declaration_status = "draft"

    _append_audit(db, decl, "reopen", old_status, decl.declaration_status, actor.id, body.reason)
    db.commit()

    logger.info(
        "Declaration REOPENED: employee_id=%d, FY=%s, reopened_by=%d, reason=%s",
        employee_id, fy, actor.id, body.reason,
    )
    return {"ok": True, "message": f"Declaration for employee {employee_id} FY {fy} reopened."}


@router.get(
    "/{employee_id}/audit-log",
    summary="[Finance/Admin] View audit trail for an employee's declaration",
)
def get_declaration_audit(
    employee_id: int,
    financial_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = _FinanceOrAdmin,
):
    fy = financial_year or _current_financial_year()
    decl = (
        db.query(EmployeeTaxDeclaration)
        .filter_by(employee_id=employee_id, financial_year=fy)
        .first()
    )
    if not decl:
        return []
    logs = (
        db.query(DeclarationAuditLog)
        .filter_by(declaration_id=decl.id)
        .order_by(DeclarationAuditLog.created_at.asc())
        .all()
    )
    return [
        {
            "id": log.id,
            "action": log.action,
            "old_status": log.old_status,
            "new_status": log.new_status,
            "performed_by_id": log.performed_by_id,
            "reason": log.reason,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
