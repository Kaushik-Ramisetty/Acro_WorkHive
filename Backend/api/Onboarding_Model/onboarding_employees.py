"""api/Onboarding_Model/onboarding_employees.py — Employee lifecycle."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from utils.response import ok, created
from api.Onboarding_Model.schemas import AssignManagerRequest, ConvertToEmployeeRequest
from api.Onboarding_Model.services import employee_service as svc
from utils.jwt_auth import requires_role

logger = logging.getLogger(__name__)
_HR_GUARD = [Depends(requires_role("admin", "hr"))]
router_convert  = APIRouter(tags=["Onboarding — Employees"], dependencies=_HR_GUARD)
router_activate = APIRouter(tags=["Onboarding — Employees"], dependencies=_HR_GUARD)
router_mgmt     = APIRouter(prefix="/onboarding", tags=["Onboarding — Employees"], dependencies=_HR_GUARD)


@router_convert.post("/convert-to-employee/{candidate_id}")
def convert_to_employee(candidate_id: int,
                         payload: ConvertToEmployeeRequest = ConvertToEmployeeRequest(),
                         db: Session = Depends(get_db)):
    emp = svc.convert_to_employee(candidate_id, payload, db)
    return created(data=_serialize(emp),
                   message=f"Candidate converted to employee (code: {emp.employee_code})")


@router_activate.post("/employees/{employee_id}/activate")
def activate_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = svc.activate_employee(employee_id, db)
    return ok(data=_serialize(emp), message=f"Employee {emp.employee_code} activated")


@router_activate.post("/employees/{employee_id}/mark-joined")
def mark_joined(employee_id: int, db: Session = Depends(get_db)):
    emp, candidate = svc.mark_joined(employee_id, db)
    return ok(data={"employee": _serialize(emp), "candidate_status": candidate.status},
              message=f"Employee {emp.employee_code} marked as JOINED")


@router_activate.post("/employees/{employee_id}/mark-not-joined")
def mark_not_joined(employee_id: int, db: Session = Depends(get_db)):
    emp, candidate = svc.mark_not_joined(employee_id, db)
    return ok(data={"employee": _serialize(emp), "candidate_status": candidate.status},
              message=f"Employee {emp.employee_code} marked as NOT JOINED")


@router_mgmt.patch("/employees/{employee_id}/assign-manager")
def assign_manager(employee_id: int, payload: AssignManagerRequest, db: Session = Depends(get_db)):
    emp = svc.assign_manager(employee_id, payload, db)
    return ok(data=_serialize(emp),
              message=f"Manager '{emp.manager_name}' assigned to employee {emp.employee_code}")


@router_mgmt.get("/employees/by-candidate/{candidate_id}")
def get_employee_by_candidate(candidate_id: int, db: Session = Depends(get_db)):
    emp = svc.get_onboarded_employee_by_candidate(candidate_id, db)
    if not emp:
        from utils.response import error
        return error(f"No employee record found for candidate {candidate_id}", status_code=404)
    return ok(data=_serialize(emp))


def _serialize(emp) -> dict:
    return {
        "id":                  emp.id,
        "candidate_id":        emp.candidate_id,
        "employee_code":       emp.employee_code,
        "manager_id":          emp.manager_id,
        "manager_name":        emp.manager_name,
        "joining_date":        str(emp.joining_date) if emp.joining_date else None,
        "status":              emp.status,
        "credentials_sent_at": emp.credentials_sent_at.isoformat() if emp.credentials_sent_at else None,
        "activated_at":        emp.activated_at.isoformat() if emp.activated_at else None,
        "created_at":          emp.created_at.isoformat() if emp.created_at else None,
    }
