"""Portal account management — admin-only endpoints for multi-portal credentials.

Allows an admin to add or update per-portal credentials in auth_accounts so
that the same company email can authenticate with different passwords on
different portals (Employee, Finance, Finance Head, etc.).

Portal → role mapping (must match login form values):
  Employee portal     → role = 'employee'
  Finance portal      → role = 'finance'
  Finance Head portal → role = 'finance_head'
  Admin portal        → role = 'admin'
  Manager portal      → role = 'manager'

Constraint: UNIQUE(email, role) — one credential set per (email, portal).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_db, role_required
from app.core.security import hash_password, verify_password
from app.models.employee import Employee

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_ADMIN = Depends(role_required("admin"))

# Valid portal role values (keep in sync with LoginForm.jsx PORTAL_OPTIONS)
_VALID_PORTAL_ROLES = {"employee", "finance", "finance_head", "admin", "manager", "candidate"}


class PortalAccountIn(BaseModel):
    """Request body for creating or updating a portal credential.

    ``email``         — the company email address of the employee.
    ``portal_role``   — target portal (employee / finance / finance_head / …).
    ``password``      — new plain-text password (will be hashed server-side).
                        Min 6 chars.  Never stored as plain text.
    """
    email: EmailStr
    portal_role: str = Field(..., description="Portal role: employee | finance | finance_head | admin | manager")
    password: str = Field(..., min_length=6, description="New password for this portal (hashed before storage)")


class PortalAccountOut(BaseModel):
    ok: bool = True
    email: str
    portal_role: str
    action: str       # "created" | "updated"
    employee_id: int
    message: str


class PortalAccountListItem(BaseModel):
    id: int
    email: str
    portal_role: str
    employee_id: int
    is_active: bool


@router.post(
    "/portal-accounts",
    response_model=PortalAccountOut,
    status_code=status.HTTP_200_OK,
    summary="[Admin] Add or update a portal credential for a company employee",
)
def upsert_portal_account(
    payload: PortalAccountIn,
    db: Session = Depends(get_db),
    _actor: Employee = _ADMIN,
):
    """Create or update a per-portal auth_accounts row for an employee.

    Use this endpoint to:
    - Give a Finance employee a SEPARATE Employee-portal password.
    - Give any staff member access to an additional portal.
    - Change an existing portal password.

    The password is hashed with bcrypt before storage — plain text is never
    persisted.  The employee is looked up by email (primary or official_email).

    Constraint: UNIQUE(email, role) — only one credential per (email, portal).

    Examples:
      # Give Manana a separate Employee-portal password
      POST /auth/portal-accounts
      { "email": "Manana.Ravikumar@acronotics.com",
        "portal_role": "employee",
        "password": "Manana@2003" }

      # Give Finance Head a separate Employee-portal password
      POST /auth/portal-accounts
      { "email": "finance.head@acronotics.com",
        "portal_role": "employee",
        "password": "Head@2003" }
    """
    role_clean = payload.portal_role.strip().lower()
    if role_clean not in _VALID_PORTAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid portal_role '{payload.portal_role}'. "
                   f"Must be one of: {sorted(_VALID_PORTAL_ROLES)}",
        )

    email_clean = payload.email.strip().lower()

    # Look up the employee — must exist and be active
    emp: Employee | None = (
        db.query(Employee)
        .filter(
            Employee.email.ilike(email_clean),
            Employee.is_deleted.is_(False),
        )
        .first()
    )
    if not emp:
        # Try official_email
        emp = (
            db.query(Employee)
            .filter(
                Employee.official_email.ilike(email_clean),
                Employee.is_deleted.is_(False),
            )
            .first()
        )
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active employee found with email '{payload.email}'.",
        )
    if emp.employment_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee account is not active.",
        )

    new_hash = hash_password(payload.password)

    # Check whether the row already exists
    # fetchone() returns at most one row — avoids LIMIT 1 (SQLite) / TOP 1 (MSSQL)
    existing = db.execute(
        text("""
            SELECT id FROM auth_accounts
            WHERE LOWER(LTRIM(RTRIM(email))) = :email AND LOWER(LTRIM(RTRIM(role))) = :role
        """),
        {"email": email_clean, "role": role_clean},
    ).fetchone()

    if existing:
        # Update existing row — LTRIM/RTRIM is SQL Server + SQLite compatible
        db.execute(
            text("""
                UPDATE auth_accounts
                SET password_hash = :pw, is_active = 1
                WHERE LOWER(LTRIM(RTRIM(email))) = :email AND LOWER(LTRIM(RTRIM(role))) = :role
            """),
            {"pw": new_hash, "email": email_clean, "role": role_clean},
        )
        action = "updated"
    else:
        # Create new row
        db.execute(
            text("""
                INSERT INTO auth_accounts (email, password_hash, role, employee_id, is_active)
                VALUES (:email, :pw, :role, :emp_id, 1)
            """),
            {
                "email": email_clean,
                "pw": new_hash,
                "role": role_clean,
                "emp_id": emp.id,
            },
        )
        action = "created"

    db.commit()
    logger.info(
        "[AUTH_PORTAL] Portal account %s: email=%s role=%s by admin_id=%d",
        action, email_clean, role_clean, _actor.id,
    )

    return PortalAccountOut(
        ok=True,
        email=email_clean,
        portal_role=role_clean,
        action=action,
        employee_id=emp.id,
        message=f"Portal credential for '{email_clean}' on portal '{role_clean}' {action} successfully.",
    )


@router.get(
    "/portal-accounts",
    summary="[Admin] List all auth_accounts entries (without password hashes)",
)
def list_portal_accounts(
    email: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Employee = _ADMIN,
):
    """Return all auth_accounts rows (passwords excluded).

    Filter by email to see all portals a specific employee has access to.
    """
    query = "SELECT id, email, role, employee_id, is_active FROM auth_accounts"
    params: dict = {}
    if email:
        query += " WHERE LOWER(TRIM(email)) = :email"
        params["email"] = email.strip().lower()
    query += " ORDER BY email, role"
    rows = db.execute(text(query), params).fetchall()
    return [
        {
            "id": r.id,
            "email": r.email,
            "portal_role": r.role,
            "employee_id": r.employee_id,
            "is_active": bool(r.is_active),
        }
        for r in rows
    ]


@router.patch(
    "/portal-accounts/toggle",
    summary="[Admin] Activate or deactivate a portal credential",
)
def toggle_portal_account(
    email: str,
    portal_role: str,
    is_active: bool,
    db: Session = Depends(get_db),
    actor: Employee = _ADMIN,
):
    """Enable or disable a specific (email, portal_role) credential.

    Deactivating blocks login without deleting the row.
    """
    email_clean = email.strip().lower()
    role_clean = portal_role.strip().lower()
    result = db.execute(
        text("""
            UPDATE auth_accounts SET is_active = :active
            WHERE LOWER(TRIM(email)) = :email AND LOWER(TRIM(role)) = :role
        """),
        {"active": 1 if is_active else 0, "email": email_clean, "role": role_clean},
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No portal account found for email='{email}' role='{portal_role}'.",
        )
    db.commit()
    logger.info(
        "[AUTH_PORTAL] Portal account %s: email=%s role=%s by admin_id=%d",
        "activated" if is_active else "deactivated",
        email_clean, role_clean, actor.id,
    )
    return {"ok": True, "email": email_clean, "portal_role": role_clean, "is_active": is_active}
