"""Global search endpoint.

Searches across employees, leave requests, and comp-off credits — role-scoped
and matched against the fields a user would actually type:

Employees: first/last name, email, employee_code, phone, designation, department.
Leave requests: id, reason, employee name, leave_type name, status.
Comp-off: reason, employee name, status.

Role scope:
  admin     -> everything
  manager   -> direct reports (+ self)
  employee  -> self only
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    Employee, LeaveRequest, CompOffCredit, LeaveType, Designation, Department,
)


router = APIRouter(prefix="/search", tags=["search"])


def _role_name(u: Employee):
    return u.role.name.lower() if u.role else None


@router.get("")
def search(
    q: str = Query("", min_length=0, max_length=200),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    q = (q or "").strip()
    if not q:
        return {"employees": [], "leaves": [], "compoff": []}

    role = _role_name(user)
    like = f"%{q}%"
    q_lower = q.lower()

    # Status synonym map: 'pending' should match cancel_pending too.
    status_words = []
    if "pend" in q_lower:
        status_words.extend(["pending", "cancel_pending"])
    if "approv" in q_lower:
        status_words.append("approved")
    if "reject" in q_lower:
        status_words.append("rejected")
    if "cancel" in q_lower and "cancel_pending" not in status_words:
        status_words.extend(["cancelled", "cancel_pending"])
    if "consum" in q_lower:
        status_words.append("consumed")
    if "expir" in q_lower:
        status_words.append("expired")

    # ---- Employees ---------------------------------------------------
    emp_q = (
        db.query(Employee)
        .outerjoin(Designation, Employee.designation_id == Designation.id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .filter(Employee.is_deleted.is_(False))
        .filter(or_(
            Employee.first_name.ilike(like),
            Employee.last_name.ilike(like),
            Employee.email.ilike(like),
            Employee.employee_code.ilike(like),
            Employee.phone.ilike(like),
            Designation.title.ilike(like),
            Department.name.ilike(like),
        ))
    )
    if role == "manager":
        emp_q = emp_q.filter(or_(Employee.id == user.id, Employee.reporting_manager_id == user.id))
    elif role == "employee":
        emp_q = emp_q.filter(Employee.id == user.id)

    employees = []
    for e in emp_q.distinct().limit(limit).all():
        employees.append({
            "id": e.id,
            "full_name": e.full_name,
            "email": e.email,
            "employee_code": e.employee_code,
            "designation": e.designation.title if e.designation else None,
            "department": e.department.name if e.department else None,
            "role": e.role.name if e.role else None,
        })

    # ---- Leave requests ----------------------------------------------
    leave_filters = [
        LeaveRequest.id.ilike(like),
        LeaveRequest.reason.ilike(like),
        Employee.first_name.ilike(like),
        Employee.last_name.ilike(like),
        LeaveType.name.ilike(like),
    ]
    if status_words:
        leave_filters.append(LeaveRequest.status.in_(status_words))

    leave_q = (
        db.query(LeaveRequest)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .filter(or_(*leave_filters))
    )
    if role == "manager":
        leave_q = leave_q.filter(or_(
            LeaveRequest.employee_id == user.id,
            Employee.reporting_manager_id == user.id,
        ))
    elif role == "employee":
        leave_q = leave_q.filter(LeaveRequest.employee_id == user.id)

    leaves = []
    for r in leave_q.order_by(LeaveRequest.created_at.desc()).limit(limit).all():
        leaves.append({
            "id": r.id,
            "employee_name": r.employee.full_name if r.employee else "",
            "leave_type_name": r.leave_type.name if r.leave_type else "",
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "total_days": r.total_days,
            "status": r.status,
        })

    # ---- Comp-off credits --------------------------------------------
    co_filters = [
        CompOffCredit.reason.ilike(like),
        Employee.first_name.ilike(like),
        Employee.last_name.ilike(like),
    ]
    if status_words:
        co_filters.append(CompOffCredit.status.in_(status_words))

    co_q = (
        db.query(CompOffCredit)
        .join(Employee, CompOffCredit.employee_id == Employee.id)
        .filter(or_(*co_filters))
    )
    if role == "manager":
        co_q = co_q.filter(or_(
            CompOffCredit.employee_id == user.id,
            Employee.reporting_manager_id == user.id,
        ))
    elif role == "employee":
        co_q = co_q.filter(CompOffCredit.employee_id == user.id)

    compoff = []
    for c in co_q.order_by(CompOffCredit.created_at.desc()).limit(limit).all():
        compoff.append({
            "id": c.id,
            "employee_name": c.employee.full_name if c.employee else "",
            "days": c.days,
            "worked_on": c.worked_on.isoformat() if c.worked_on else None,
            "status": c.status,
        })

    return {"employees": employees, "leaves": leaves, "compoff": compoff}
