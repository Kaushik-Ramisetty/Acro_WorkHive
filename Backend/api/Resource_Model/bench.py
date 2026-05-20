"""Admin bench endpoints.

Mounted under /admin/* but in a separate router so the existing
app/routes/admin.py — which owns /admin/employees and /admin/reference
— keeps working unmodified. The path /admin/resource-employees is
chosen specifically to avoid colliding with /admin/employees.

This router is registered BEFORE app/routes/admin.py in main.py so the
shorter / more specific paths here win in case of any future overlap.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, role_required
from app.db.session import get_db
from app.models import Employee

from api.Resource_Model.schemas import (
    BenchEmployeeOut, EmployeeProjectOut, EmployeeResourceDetailsIn,
    EmployeeWithAllocationOut, ReassignIn,
)
from api.Resource_Model.services import (
    ResourceError, get_employee_projects, list_bench_employees_detail,
    list_employees_with_allocation, reassign_employee,
    save_employee_resource_details,
)


router = APIRouter(prefix="/admin", tags=["resource-admin-bench"],
                    dependencies=[Depends(role_required("admin"))])


def _wrap(call):
    try:
        return call()
    except ResourceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ---- All employees with allocation snapshot -----------------------

@router.get("/resource-employees", response_model=list[EmployeeWithAllocationOut])
def resource_employees(db: Session = Depends(get_db)):
    """Path chosen to avoid colliding with /admin/employees in
    app/routes/admin.py."""
    return list_employees_with_allocation(db)


# ---- Bench list with duration -------------------------------------

@router.get("/bench", response_model=list[BenchEmployeeOut])
def bench(db: Session = Depends(get_db)):
    return list_bench_employees_detail(db)


# ---- Employee project history -------------------------------------

@router.get("/employee/{employee_id}/projects",
            response_model=list[EmployeeProjectOut])
def employee_projects(employee_id: int, db: Session = Depends(get_db)):
    return get_employee_projects(db, employee_id)


# ---- Save details from the Edit modal -----------------------------

@router.put("/employee/{employee_id}/resource-details")
def save_resource_details(employee_id: int,
                          payload: EmployeeResourceDetailsIn,
                          db: Session = Depends(get_db)):
    return _wrap(lambda: save_employee_resource_details(db, employee_id, payload))


# ---- Reassign between projects ------------------------------------

@router.post("/reassign")
def reassign(payload: ReassignIn,
             db: Session = Depends(get_db),
             user: Employee = Depends(get_current_user)):
    return _wrap(lambda: reassign_employee(db, user, payload))
