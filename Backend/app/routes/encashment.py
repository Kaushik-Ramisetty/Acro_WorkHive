"""Encashment endpoints + admin endpoints for tenure brackets.

Mounted at /leave/encashment to keep the leave namespace coherent.
"""
from __future__ import annotations

from datetime import date as _date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee, EncashmentRequest, LeaveAccrualBracket
from app.services.encashment import (
    EncashmentError, approve_request, create_request, reject_request,
)


router = APIRouter(prefix="/leave/encashment", tags=["leave"])


def _role(u: Employee) -> Optional[str]:
    return u.role.name.lower() if u and u.role else None


def _wrap(call):
    try:
        return call()
    except EncashmentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


class EncashmentIn(BaseModel):
    leave_type_id: str
    days: int
    rate_per_day: Optional[float] = None
    reason: Optional[str] = None
    year: Optional[int] = None


class EncashmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    leave_type_id: str
    year: int
    days: int
    rate_per_day: Optional[float] = None
    reason: Optional[str] = None
    status: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejected_by: Optional[int] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    payroll_sync_status: str
    created_at: datetime


class RejectIn(BaseModel):
    reason: Optional[str] = None


@router.post("", response_model=EncashmentOut, status_code=201)
def create(payload: EncashmentIn,
           db: Session = Depends(get_db),
           user: Employee = Depends(get_current_user)):
    req = _wrap(lambda: create_request(
        db, user, payload.leave_type_id, payload.days,
        rate_per_day=payload.rate_per_day,
        reason=payload.reason,
        year=payload.year,
    ))
    return EncashmentOut.model_validate(req)


@router.get("", response_model=list[EncashmentOut])
def list_my(
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = _role(user)
    q = db.query(EncashmentRequest).join(Employee, EncashmentRequest.employee_id == Employee.id)
    if role == "admin":
        if employee_id is not None:
            q = q.filter(EncashmentRequest.employee_id == employee_id)
    elif role == "manager":
        if employee_id is not None:
            target = db.get(Employee, employee_id)
            if not target or target.reporting_manager_id != user.id:
                raise HTTPException(403, "Not in your team.")
            q = q.filter(EncashmentRequest.employee_id == employee_id)
        else:
            q = q.filter(Employee.reporting_manager_id == user.id)
    else:
        q = q.filter(EncashmentRequest.employee_id == user.id)

    if status_filter:
        q = q.filter(EncashmentRequest.status == status_filter.lower())
    rows = q.order_by(EncashmentRequest.created_at.desc()).all()
    return [EncashmentOut.model_validate(r) for r in rows]


@router.post("/{req_id}/approve", response_model=EncashmentOut)
def approve(req_id: int,
            db: Session = Depends(get_db),
            user: Employee = Depends(get_current_user)):
    if _role(user) not in {"manager", "admin"}:
        raise HTTPException(403, "Only managers or admins can approve.")
    req = db.get(EncashmentRequest, req_id)
    if not req:
        raise HTTPException(404, "Not found.")
    return EncashmentOut.model_validate(_wrap(lambda: approve_request(db, user, req)))


@router.post("/{req_id}/reject", response_model=EncashmentOut)
def reject(req_id: int,
           payload: RejectIn = RejectIn(),
           db: Session = Depends(get_db),
           user: Employee = Depends(get_current_user)):
    if _role(user) not in {"manager", "admin"}:
        raise HTTPException(403, "Only managers or admins can reject.")
    req = db.get(EncashmentRequest, req_id)
    if not req:
        raise HTTPException(404, "Not found.")
    return EncashmentOut.model_validate(_wrap(lambda: reject_request(db, user, req, payload.reason)))


# ===================================================================
# Admin: tenure brackets
# ===================================================================

class BracketIn(BaseModel):
    leave_type_id: str
    min_years: int
    bonus_days_per_cycle: int
    note: Optional[str] = None


class BracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    leave_type_id: str
    min_years: int
    bonus_days_per_cycle: int
    is_active: bool
    note: Optional[str] = None
    created_at: datetime


@router.post("/admin/brackets", response_model=BracketOut, status_code=201)
def create_bracket(payload: BracketIn,
                   db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    if payload.min_years < 0 or payload.bonus_days_per_cycle <= 0:
        raise HTTPException(400, "min_years must be >= 0 and bonus_days_per_cycle > 0.")
    row = LeaveAccrualBracket(
        leave_type_id=payload.leave_type_id,
        min_years=payload.min_years,
        bonus_days_per_cycle=payload.bonus_days_per_cycle,
        note=payload.note,
        created_by=user.id,
        is_active=True,
    )
    db.add(row); db.commit(); db.refresh(row)
    return BracketOut.model_validate(row)


@router.get("/admin/brackets", response_model=list[BracketOut])
def list_brackets(
    leave_type_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    q = db.query(LeaveAccrualBracket)
    if leave_type_id:
        q = q.filter(LeaveAccrualBracket.leave_type_id == leave_type_id)
    return [BracketOut.model_validate(r) for r in q.order_by(
        LeaveAccrualBracket.leave_type_id, LeaveAccrualBracket.min_years.asc()
    ).all()]


@router.delete("/admin/brackets/{bracket_id}", status_code=204)
def deactivate_bracket(bracket_id: int,
                       db: Session = Depends(get_db),
                       user: Employee = Depends(get_current_user)):
    if _role(user) != "admin":
        raise HTTPException(403, "Admin only.")
    row = db.get(LeaveAccrualBracket, bracket_id)
    if not row:
        raise HTTPException(404, "Not found.")
    row.is_active = False
    db.commit()
    return None
