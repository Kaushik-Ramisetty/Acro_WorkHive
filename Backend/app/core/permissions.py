"""Centralised permission registry and authorization helpers.

This module is **additive** and **opt-in**. The existing
:func:`app.core.deps.role_required` dependency keeps working unchanged — every
router that uses it today continues to operate exactly as before. New routes
(and refactors of old ones, when desired) can switch to permission-based
authorization via :func:`require_permission` for a more future-proof API.

Rationale
---------
Scattered role checks like ``if user.role.name == "admin": ...`` are brittle:
adding a new role (for example ``IT_admin`` or ``HR``) requires hunting down
every comparison. A permission registry decouples *what* the user can do from
*which role* they have, so introducing a new role only requires updating one
table.

Backwards compatibility guarantees
----------------------------------
- Role names (``admin``, ``manager``, ``employee``) are preserved verbatim.
- All current ``role_required(...)`` call sites continue to work.
- Permission checks fall through to the legacy role check, so a JWT minted
  by the legacy ``/api/v1/auth/login`` (which carries ``role`` as a claim)
  is honoured even if the DB row lookup is bypassed.
- No new DB tables, columns, or migrations.
"""
from __future__ import annotations

from typing import Dict, Iterable, Set

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models import Employee


# ─────────────────────────────────────────────────────────────────────────────
# Permission catalogue
# ─────────────────────────────────────────────────────────────────────────────
# Permissions are plain strings of the form ``<resource>:<action>``. The
# catalogue here is intentionally a superset of what the codebase currently
# enforces — routes can opt into the relevant permission without us having
# to define one ad hoc on the spot.

class Permission:
    # Employee management
    EMPLOYEE_READ            = "employee:read"
    EMPLOYEE_READ_ALL        = "employee:read_all"
    EMPLOYEE_UPDATE          = "employee:update"
    EMPLOYEE_UPDATE_SELF     = "employee:update_self"
    EMPLOYEE_CREATE          = "employee:create"
    EMPLOYEE_DELETE          = "employee:delete"

    # Leave management
    LEAVE_APPLY              = "leave:apply"
    LEAVE_VIEW_OWN           = "leave:view_own"
    LEAVE_VIEW_TEAM          = "leave:view_team"
    LEAVE_VIEW_ALL           = "leave:view_all"
    LEAVE_APPROVE_MANAGER    = "leave:approve_manager"
    LEAVE_APPROVE_HR         = "leave:approve_hr"
    LEAVE_ADMIN              = "leave:admin"  # cleanup / scheduler / overrides

    # Attendance / regularization
    ATTENDANCE_PUNCH         = "attendance:punch"
    ATTENDANCE_VIEW_OWN      = "attendance:view_own"
    ATTENDANCE_VIEW_TEAM     = "attendance:view_team"
    ATTENDANCE_VIEW_ALL      = "attendance:view_all"
    REGULARIZATION_REQUEST   = "regularization:request"
    REGULARIZATION_APPROVE   = "regularization:approve"

    # Timesheet
    TIMESHEET_SUBMIT         = "timesheet:submit"
    TIMESHEET_REVIEW         = "timesheet:review"
    TIMESHEET_PAYROLL_SYNC   = "timesheet:payroll_sync"

    # Onboarding
    CANDIDATE_MANAGE         = "candidate:manage"
    OFFER_MANAGE             = "offer:manage"
    BGV_INITIATE             = "bgv:initiate"
    BGV_VIEW                 = "bgv:view"
    CONVERT_CANDIDATE        = "candidate:convert"
    ACTIVATE_EMPLOYEE        = "employee:activate"

    # Notifications / search / admin tools
    NOTIFICATION_READ_OWN    = "notification:read_own"
    SEARCH_GLOBAL            = "search:global"
    ADMIN_ALL                = "admin:*"


# ─────────────────────────────────────────────────────────────────────────────
# Role → permission map
# ─────────────────────────────────────────────────────────────────────────────
# Mirrors the *effective* role behaviour that already exists across the
# codebase. To onboard a new role (e.g. ``it_admin``, ``hr``), add a row
# here and the entire codebase that uses :func:`require_permission` adapts.

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        Permission.ADMIN_ALL,
        Permission.EMPLOYEE_READ_ALL, Permission.EMPLOYEE_READ,
        Permission.EMPLOYEE_CREATE, Permission.EMPLOYEE_UPDATE,
        Permission.EMPLOYEE_UPDATE_SELF, Permission.EMPLOYEE_DELETE,
        Permission.LEAVE_APPLY, Permission.LEAVE_VIEW_OWN, Permission.LEAVE_VIEW_TEAM,
        Permission.LEAVE_VIEW_ALL, Permission.LEAVE_APPROVE_MANAGER,
        Permission.LEAVE_APPROVE_HR, Permission.LEAVE_ADMIN,
        Permission.ATTENDANCE_PUNCH, Permission.ATTENDANCE_VIEW_OWN,
        Permission.ATTENDANCE_VIEW_TEAM, Permission.ATTENDANCE_VIEW_ALL,
        Permission.REGULARIZATION_REQUEST, Permission.REGULARIZATION_APPROVE,
        Permission.TIMESHEET_SUBMIT, Permission.TIMESHEET_REVIEW,
        Permission.TIMESHEET_PAYROLL_SYNC,
        Permission.CANDIDATE_MANAGE, Permission.OFFER_MANAGE,
        Permission.BGV_INITIATE, Permission.BGV_VIEW,
        Permission.CONVERT_CANDIDATE, Permission.ACTIVATE_EMPLOYEE,
        Permission.NOTIFICATION_READ_OWN, Permission.SEARCH_GLOBAL,
    },
    # ``hr`` is a synonym for the historical HR-flavoured admin used by
    # parts of the onboarding flow. Granting it the same permission set as
    # ``admin`` keeps existing behaviour when a JWT claims role=hr.
    "hr": {
        Permission.EMPLOYEE_READ_ALL, Permission.EMPLOYEE_READ,
        Permission.EMPLOYEE_CREATE, Permission.EMPLOYEE_UPDATE,
        Permission.EMPLOYEE_UPDATE_SELF,
        Permission.LEAVE_APPROVE_HR, Permission.LEAVE_VIEW_ALL,
        Permission.LEAVE_VIEW_TEAM, Permission.LEAVE_VIEW_OWN,
        Permission.ATTENDANCE_VIEW_ALL, Permission.ATTENDANCE_VIEW_TEAM,
        Permission.REGULARIZATION_APPROVE,
        Permission.CANDIDATE_MANAGE, Permission.OFFER_MANAGE,
        Permission.BGV_INITIATE, Permission.BGV_VIEW,
        Permission.CONVERT_CANDIDATE, Permission.ACTIVATE_EMPLOYEE,
        Permission.NOTIFICATION_READ_OWN,
    },
    "manager": {
        Permission.EMPLOYEE_READ, Permission.EMPLOYEE_UPDATE_SELF,
        Permission.LEAVE_APPLY, Permission.LEAVE_VIEW_OWN,
        Permission.LEAVE_VIEW_TEAM, Permission.LEAVE_APPROVE_MANAGER,
        Permission.ATTENDANCE_PUNCH, Permission.ATTENDANCE_VIEW_OWN,
        Permission.ATTENDANCE_VIEW_TEAM,
        Permission.REGULARIZATION_REQUEST, Permission.REGULARIZATION_APPROVE,
        Permission.TIMESHEET_SUBMIT, Permission.TIMESHEET_REVIEW,
        Permission.NOTIFICATION_READ_OWN, Permission.SEARCH_GLOBAL,
    },
    "employee": {
        Permission.EMPLOYEE_UPDATE_SELF, Permission.EMPLOYEE_READ,
        Permission.LEAVE_APPLY, Permission.LEAVE_VIEW_OWN,
        Permission.ATTENDANCE_PUNCH, Permission.ATTENDANCE_VIEW_OWN,
        Permission.REGULARIZATION_REQUEST,
        Permission.TIMESHEET_SUBMIT,
        Permission.NOTIFICATION_READ_OWN, Permission.SEARCH_GLOBAL,
    },
    # ``candidate`` users live in the legacy ``users`` table and only ever
    # talk to the candidate portal. They have no Core HRMS permissions.
    "candidate": set(),
    # Forward-compatibility placeholder. An IT admin can manage employees
    # (issue official email + temporary password) without leave/approval
    # power. Add real call sites as the role is rolled out.
    "it_admin": {
        Permission.EMPLOYEE_READ_ALL, Permission.EMPLOYEE_READ,
        Permission.EMPLOYEE_UPDATE, Permission.ACTIVATE_EMPLOYEE,
        Permission.NOTIFICATION_READ_OWN,
    },
}


def _normalise(role: str | None) -> str:
    return (role or "").strip().lower()


def permissions_for_role(role: str | None) -> Set[str]:
    """Return the effective permission set for a role name. Unknown roles
    receive an empty set (deny by default)."""
    return ROLE_PERMISSIONS.get(_normalise(role), set())


def has_permission(role: str | None, perm: str) -> bool:
    """Pure-Python check used by both the dependency and by ad-hoc call
    sites that have a role string but not a request context."""
    perms = permissions_for_role(role)
    if Permission.ADMIN_ALL in perms:
        return True
    return perm in perms


def require_permission(*required: str):
    """FastAPI dependency factory. Use exactly like ``role_required(...)``.

    Example::

        @router.post(
            "/leave/{id}/approve",
            dependencies=[Depends(require_permission(Permission.LEAVE_APPROVE_MANAGER))],
        )
        def approve_leave(...): ...

    The dependency reuses :func:`get_current_user`, which means existing
    JWT decoding + ``employment_status`` checks continue to apply — this
    is purely an authorization layer on top of the existing auth flow.
    """
    required_set = set(required)

    def dep(current: Employee = Depends(get_current_user)) -> Employee:
        role_name = current.role.name if current.role else None
        perms = permissions_for_role(role_name)
        if Permission.ADMIN_ALL in perms:
            return current
        if required_set.issubset(perms):
            return current
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: missing permission(s) {sorted(required_set - perms)}",
        )

    return dep


__all__ = [
    "Permission",
    "ROLE_PERMISSIONS",
    "has_permission",
    "permissions_for_role",
    "require_permission",
]
