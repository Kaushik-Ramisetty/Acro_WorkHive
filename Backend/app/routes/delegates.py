"""Delegate assignments + SLA admin endpoints (Phase 2).

A manager (or admin) can designate a deputy approver for a date window.
While the window is active and is_active is True, the deputy can approve
leave requests pointing at the original manager. Skip-level escalation
and HR intervention are handled by `app.services.sla_escalation`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import DelegateAssignment, Employee
from app.schemas.leave import (
    DelegateAssignmentIn, DelegateAssignmentOut, SLASweepOut,
)
from app.services.sla_escalation import run_sla_sweep


router = APIRouter(prefix="/delegates", tags=["delegates"])


def _role_name(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u.role else None


def _serialize(d: DelegateAssignment) -> DelegateAssignmentOut:
    return DelegateAssignmentOut(
        id=d.id,
        manager_id=d.manager_id,
        manager_name=(d.manager.full_name if d.manager else None),
        delegate_id=d.delegate_id,
        delegate_name=(d.delegate.full_name if d.delegate else None),
        start_date=d.start_date,
        end_date=d.end_date,
        reason=d.reason,
        is_active=d.is_active,
        created_at=d.created_at,
    )


@router.post("", response_model=DelegateAssignmentOut, status_code=201)
def create_delegate(payload: DelegateAssignmentIn,
                    db: Session = Depends(get_db),
                    user: Employee = Depends(get_current_user)):
    role = _role_name(user)
    is_admin = role == "admin"
    if not is_admin and user.id != payload.manager_id:
        raise HTTPException(403, "You can only assign a delegate for yourself.")

    if payload.end_date < payload.start_date:
        raise HTTPException(400, "end_date cannot be before start_date.")
    if payload.delegate_id == payload.manager_id:
        raise HTTPException(400, "Manager and delegate must differ.")

    mgr = db.get(Employee, payload.manager_id)
    deleg = db.get(Employee, payload.delegate_id)
    if not mgr or not deleg:
        raise HTTPException(404, "Manager or delegate not found.")

    # Deactivate any overlapping active assignments for this manager — there
    # should be at most one active delegate at a time.
    overlapping = (
        db.query(DelegateAssignment)
        .filter(
            DelegateAssignment.manager_id == payload.manager_id,
            DelegateAssignment.is_active.is_(True),
            DelegateAssignment.start_date <= payload.end_date,
            DelegateAssignment.end_date >= payload.start_date,
        )
        .all()
    )
    for ov in overlapping:
        ov.is_active = False

    row = DelegateAssignment(
        manager_id=payload.manager_id,
        delegate_id=payload.delegate_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        is_active=True,
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.get("", response_model=list[DelegateAssignmentOut])
def list_delegates(db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_user),
                   manager_id: Optional[int] = Query(None),
                   active_only: bool = Query(False)):
    role = _role_name(user)
    q = db.query(DelegateAssignment)
    if role != "admin":
        # Employees see only assignments they're either the manager or the delegate on.
        q = q.filter(
            (DelegateAssignment.manager_id == user.id)
            | (DelegateAssignment.delegate_id == user.id)
        )
    elif manager_id is not None:
        q = q.filter(DelegateAssignment.manager_id == manager_id)

    if active_only:
        today = date.today()
        q = q.filter(
            DelegateAssignment.is_active.is_(True),
            DelegateAssignment.start_date <= today,
            DelegateAssignment.end_date >= today,
        )

    return [_serialize(d) for d in q.order_by(DelegateAssignment.created_at.desc()).all()]


@router.delete("/{delegate_id}", status_code=204)
def deactivate_delegate(delegate_id: int,
                         db: Session = Depends(get_db),
                         user: Employee = Depends(get_current_user)):
    row = db.get(DelegateAssignment, delegate_id)
    if not row:
        raise HTTPException(404, "Delegate assignment not found.")
    role = _role_name(user)
    if role != "admin" and user.id != row.manager_id:
        raise HTTPException(403, "Only the manager or admin can revoke a delegate.")
    row.is_active = False
    db.commit()
    return None


@router.post("/sla/run", response_model=SLASweepOut)
def admin_run_sla(db: Session = Depends(get_db),
                  user: Employee = Depends(get_current_user)):
    if _role_name(user) != "admin":
        raise HTTPException(403, "Admin only.")
    return run_sla_sweep(db)
