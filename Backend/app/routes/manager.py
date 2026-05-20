from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import role_required
from app.db.session import get_db
from app.models import Employee

router = APIRouter(prefix="/manager", tags=["manager"], dependencies=[Depends(role_required("manager", "admin"))])


@router.get("/ping")
def ping():
    return {"ok": True, "scope": "manager"}


@router.get("/team")
def my_team(current: Employee = Depends(role_required("manager", "admin")), db: Session = Depends(get_db)):
    members = db.query(Employee).filter(Employee.reporting_manager_id == current.id, Employee.is_deleted.is_(False)).all()
    return [{"id": m.id, "name": m.full_name, "email": m.email, "designation_id": m.designation_id} for m in members]
