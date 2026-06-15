"""
api/Employee_Model/schemas.py
Pydantic request / response schemas — Employee Management Module.
Ported from workhive_clean; adapted for SQLite (no Identity columns).
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator

from utils.phone_validator import validate_e164


class EmploymentStatus(str, Enum):
    active    = "active"
    on_notice = "on_notice"
    exited    = "exited"
    suspended = "suspended"


class Gender(str, Enum):
    male   = "male"
    female = "female"
    other  = "other"


# ── Department ─────────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    id:                   str
    name:                 str
    head_id:              Optional[int] = None
    parent_department_id: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name:                 Optional[str] = None
    head_id:              Optional[int] = None
    parent_department_id: Optional[str] = None


class DepartmentResponse(BaseModel):
    id:                   str
    name:                 str
    head_id:              Optional[int]
    parent_department_id: Optional[str]
    # created_at:           datetime
    # updated_at:           datetime

    class Config:
        from_attributes = True


# ── Designation ─────────────────────────────────────────────────────────────────

class DesignationCreate(BaseModel):
    id:    str
    title: str
    level: int = Field(..., ge=1, le=10)


class DesignationUpdate(BaseModel):
    title: Optional[str] = None
    level: Optional[int] = Field(None, ge=1, le=10)


class DesignationResponse(BaseModel):
    id:            str
    title:         str
    level:         int
    department_id: Optional[str] = None

    class Config:
        from_attributes = True


# ── Employee ────────────────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    employee_code:        str          = Field(..., max_length=20)
    entra_object_id:      Optional[str] = Field(None, max_length=128)
    first_name:           str          = Field(..., max_length=100)
    last_name:            str          = Field(..., max_length=100)
    email:                EmailStr
    phone:                Optional[str] = None
    date_of_birth:        date
    date_of_joining:      date
    date_of_exit:         Optional[date] = None
    department_id:        str
    designation_id:       str
    reporting_manager_id: Optional[int] = None
    employment_status:    EmploymentStatus = EmploymentStatus.active
    gender:               Gender
    bank_ifsc:            Optional[str] = Field(None, max_length=11)
    profile_photo_url:    Optional[str] = Field(None, max_length=500)
    blood_group:             Optional[str] = Field(None, max_length=10)
    emergency_contact_name:  Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = None

    @field_validator("employee_code")
    @classmethod
    def code_uppercase(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def validate_phones(cls, v: Optional[str]) -> Optional[str]:
        return validate_e164(v)


class FullEmployeeConvertRequest(BaseModel):
    """
    Payload for POST /employees/convert/{candidate_id}.
    HR fills this form to convert an offer-accepted candidate into a
    full Employee record in the HR system.
    """
    first_name:           str      = Field(..., min_length=1, max_length=100)
    last_name:            str      = Field(..., min_length=1, max_length=100)
    phone:                Optional[str]  = None
    date_of_birth:        date
    date_of_joining:      date
    department_id:        str      = Field(..., description="FK → departments.id")
    designation_id:       str      = Field(..., description="FK → designations.id")
    reporting_manager_id: Optional[int]  = None
    gender:               Gender
    aadhaar:              Optional[str]  = Field(None, max_length=16, description="Stored encrypted")

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_e164(v)


class EmployeeUpdate(BaseModel):
    first_name:           Optional[str]              = None
    last_name:            Optional[str]              = None
    email:                Optional[EmailStr]          = None
    phone:                Optional[str]              = None
    date_of_exit:         Optional[date]             = None
    department_id:        Optional[str]              = None
    designation_id:       Optional[str]              = None
    reporting_manager_id: Optional[int]              = None
    employment_status:    Optional[EmploymentStatus] = None
    gender:               Optional[Gender]           = None
    bank_ifsc:            Optional[str]              = None
    profile_photo_url:    Optional[str]              = None
    entra_object_id:      Optional[str]              = None
    blood_group:             Optional[str]           = None
    emergency_contact_name:  Optional[str]           = None
    emergency_contact_phone: Optional[str]           = None

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def validate_phones(cls, v: Optional[str]) -> Optional[str]:
        return validate_e164(v)


class EmployeeResponse(BaseModel):
    id:                   int
    employee_code:        str
    entra_object_id:      Optional[str]
    first_name:           str
    last_name:            str
    email:                str
    phone:                Optional[str]
    # date_of_birth and gender are Optional in the Employee model (nullable=True),
    # so they MUST be Optional here too — otherwise pydantic raises ValidationError
    # when serialising employees that have no DOB/gender set, returning a 500.
    date_of_birth:        Optional[date]
    date_of_joining:      date
    date_of_exit:         Optional[date]
    department_id:        str
    designation_id:       str
    reporting_manager_id: Optional[int]
    employment_status:    EmploymentStatus
    gender:               Optional[Gender]
    bank_ifsc:            Optional[str]
    profile_photo_url:    Optional[str]
    blood_group:             Optional[str]
    emergency_contact_name:  Optional[str]
    emergency_contact_phone: Optional[str]
    is_deleted:           bool
    created_at:           datetime
    updated_at:           datetime

    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    id:               int
    employee_code:    str
    first_name:       str
    last_name:        str
    email:            str
    employment_status: EmploymentStatus
    department_id:    str
    designation_id:   str

    class Config:
        from_attributes = True
