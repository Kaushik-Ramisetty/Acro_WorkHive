from datetime import date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ── Read shapes ──────────────────────────────────────────────────────
class EmployeeListItem(BaseModel):
    id: int
    employee_code: Optional[str] = None
    full_name: str
    first_name: str
    last_name: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    role: Optional[str] = None
    role_id: Optional[int] = None
    designation: Optional[str] = None
    designation_id: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[str] = None
    employment_status: str
    location: Optional[str] = None
    date_of_joining: Optional[date] = None
    # Reporting manager — exposed so the admin edit form can pre-select.
    # `reporting_manager_name` is populated server-side from the FK so the UI
    # can render the current value without an extra lookup.
    reporting_manager_id: Optional[int] = None
    reporting_manager_name: Optional[str] = None

    class Config:
        from_attributes = True


# ── Write shapes ─────────────────────────────────────────────────────
class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, description="Full name; split on first space into first/last")
    email: EmailStr
    role: str = Field(pattern=r"^(admin|manager|employee|finance|finance_head)$")
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    password: str = Field(min_length=4)
    phone: Optional[str] = None
    employee_code: Optional[str] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(default=None, pattern=r"^(admin|manager|employee|finance|finance_head)$")
    department_id: Optional[str] = None
    designation_id: Optional[str] = None
    phone: Optional[str] = None
    employment_status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    employee_code: Optional[str] = None
    location: Optional[str] = None
    # Admin can reassign the reporting manager. Pass `null` to detach.
    reporting_manager_id: Optional[int] = None


# ── Reference data for dropdowns ─────────────────────────────────────
class RefRole(BaseModel):
    id: int
    name: str
    class Config: from_attributes = True


class RefDepartment(BaseModel):
    id: str
    name: str
    class Config: from_attributes = True


class RefDesignation(BaseModel):
    id: str
    title: str
    level: Optional[int] = None
    class Config: from_attributes = True


class ReferenceData(BaseModel):
    roles: List[RefRole]
    departments: List[RefDepartment]
    designations: List[RefDesignation]
