"""
api/Onboarding_Model/schemas.py
Pydantic request / response schemas for the full Onboarding workflow.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator

from utils.phone_validator import validate_e164


# ══════════════════════════════════════════════════════════════════════════════
# Enums (mirror api/models.py — kept separate to avoid circular imports)
# ══════════════════════════════════════════════════════════════════════════════

class CandidateStatusEnum(str, Enum):
    CREATED         = "CREATED"
    OFFER_GENERATED = "OFFER_GENERATED"
    OFFER_SENT      = "OFFER_SENT"
    OFFER_ACCEPTED  = "OFFER_ACCEPTED"
    OFFER_REJECTED  = "OFFER_REJECTED"
    DOCS_PENDING    = "DOCS_PENDING"
    DOCS_SUBMITTED  = "DOCS_SUBMITTED"
    BGV_IN_PROGRESS = "BGV_IN_PROGRESS"
    BGV_CLEAR       = "BGV_CLEAR"
    BGV_FAILED      = "BGV_FAILED"
    BGV_ON_HOLD     = "BGV_ON_HOLD"      # mirrors models.CandidateStatus.BGV_ON_HOLD
    CONVERTED       = "CONVERTED"
    JOINED          = "JOINED"
    NOT_JOINED      = "NOT_JOINED"


class BGVStatusEnum(str, Enum):
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    CLEAR       = "CLEAR"
    FAILED      = "FAILED"
    REVIEW      = "REVIEW"
    ON_HOLD     = "ON_HOLD"              # mirrors models.BGVStatus.ON_HOLD


class DocumentStatusEnum(str, Enum):
    PENDING  = "PENDING"
    UPLOADED = "UPLOADED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class OnboardedEmpStatusEnum(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE   = "ACTIVE"


# ══════════════════════════════════════════════════════════════════════════════
# Candidate Schemas
# ══════════════════════════════════════════════════════════════════════════════

class CandidateCreate(BaseModel):
    first_name:           str      = Field(..., min_length=1, max_length=100)
    last_name:            str      = Field(..., min_length=1, max_length=100)
    email:                EmailStr
    phone:                Optional[str] = None
    role:                 str      = Field(..., min_length=2, max_length=100)
    department:           Optional[str] = Field(None, max_length=100)
    ctc:                  Optional[str] = Field(None, max_length=50)
    expected_joining_date: Optional[date] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_e164(v)


class CandidateUpdate(BaseModel):
    first_name:           Optional[str]  = None
    last_name:            Optional[str]  = None
    phone:                Optional[str]  = None
    role:                 Optional[str]  = None
    department:           Optional[str]  = None
    ctc:                  Optional[str]  = None
    expected_joining_date: Optional[date] = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_e164(v)


class CandidateListItem(BaseModel):
    id:              int
    candidate_ref:   str
    first_name:      Optional[str]
    last_name:       Optional[str]
    name:            str
    email:           str
    phone:           Optional[str]
    role:            str
    department:      Optional[str]
    ctc:             Optional[str]
    status:          str
    is_offer_accepted: bool
    expected_joining_date: Optional[date]
    created_at:      datetime

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id:                int
    doc_type:          str
    original_filename: str
    file_url:          str
    status:            str
    uploaded_at:       datetime

    class Config:
        from_attributes = True


class BGVCheckOut(BaseModel):
    id:            int
    status:        str
    vendor_name:   Optional[str]
    initiated_at:  Optional[datetime]
    completed_at:  Optional[datetime]
    remarks:       Optional[str]

    class Config:
        from_attributes = True


class OnboardedEmployeeOut(BaseModel):
    id:              int
    employee_code:   str
    manager_name:    Optional[str]
    joining_date:    Optional[date]
    status:          str
    activated_at:    Optional[datetime]

    class Config:
        from_attributes = True


class CandidateDetail(BaseModel):
    id:                    int
    candidate_ref:         str
    first_name:            Optional[str]
    last_name:             Optional[str]
    name:                  str
    email:                 str
    phone:                 Optional[str]
    role:                  str
    department:            Optional[str]
    ctc:                   Optional[str]
    status:                str
    offer_letter_url:      Optional[str]
    offer_sent_at:         Optional[datetime]
    offer_accepted_at:     Optional[datetime]
    is_offer_accepted:     bool
    credentials_sent:      bool
    expected_joining_date: Optional[date]
    created_at:            datetime
    updated_at:            datetime
    documents:             List[DocumentOut]
    bgv_check:             Optional[BGVCheckOut]
    onboarded_employee:    Optional[OnboardedEmployeeOut]

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
# Offer Schemas
# ══════════════════════════════════════════════════════════════════════════════

class OfferGenerateResponse(BaseModel):
    candidate_id:     int
    offer_letter_url: str
    status:           str


class OfferSendRequest(BaseModel):
    """Optional overrides HR can supply before sending the offer email."""
    to_email: Optional[str]  = None   # defaults to candidate.email
    subject:  Optional[str]  = None   # defaults to built-in template
    body:     Optional[str]  = None   # defaults to built-in template


class OfferSendResponse(BaseModel):
    candidate_id: int
    email:        str
    sent_at:      datetime
    status:       str


class OfferAcceptResponse(BaseModel):
    candidate_id:     int
    accepted_at:      datetime
    status:           str


# ══════════════════════════════════════════════════════════════════════════════
# Document Schemas
# ══════════════════════════════════════════════════════════════════════════════

class DocumentUploadResponse(BaseModel):
    uploaded:    int
    failed:      int
    documents:   List[DocumentOut]


# ══════════════════════════════════════════════════════════════════════════════
# BGV Schemas
# ══════════════════════════════════════════════════════════════════════════════

class BGVStartRequest(BaseModel):
    vendor_name: Optional[str] = Field(None, max_length=100)


class BGVUpdateRequest(BaseModel):
    status:  BGVStatusEnum
    remarks: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Convert → Employee Schemas
# ══════════════════════════════════════════════════════════════════════════════

class ConvertToEmployeeRequest(BaseModel):
    manager_id:   Optional[int]  = None
    manager_name: Optional[str]  = None
    joining_date: Optional[date] = None


class AssignManagerRequest(BaseModel):
    manager_id:   Optional[int]  = None
    manager_name: str = Field(..., min_length=2)


class ActivateRequest(BaseModel):
    """Optional payload — activation needs no body but accepts notes."""
    notes: Optional[str] = None
