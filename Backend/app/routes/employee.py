from fastapi import APIRouter, Depends

from app.core.deps import role_required
from app.models import Employee

router = APIRouter(prefix="/employee", tags=["employee"], dependencies=[Depends(role_required("employee", "manager", "admin"))])


@router.get("/ping")
def ping():
    return {"ok": True, "scope": "employee"}


@router.get("/profile")
def my_profile(current: Employee = Depends(role_required("employee", "manager", "admin"))):
    return {
        "id": current.id, "name": current.full_name, "email": current.email,
        "designation_id": current.designation_id, "department_id": current.department_id,
        "role": current.role.name if current.role else None,
    }
