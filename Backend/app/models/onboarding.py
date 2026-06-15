"""
Onboarding-domain ORM models.

Brought over from the Onboarding module (originally `api/models.py`) and
re-anchored on the Core's `Base` so all metadata lives in a single
DeclarativeBase.

Tables
------
candidates              — applicants in the offer/BGV pipeline
candidate_documents     — uploaded onboarding documents
bgv_checks              — Background Verification record per candidate
bgv_tokens              — vendor-portal one-time-use tokens
onboarded_employees     — bridge row per candidate→employee conversion
users                   — legacy portal auth table (candidates + early employees)

Enums
-----
CandidateStatus, BGVStatus, DocumentStatus, OnboardedEmployeeStatus, UserRole
plus the CANDIDATE_TRANSITIONS state-machine map.
"""
from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum,
    ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ──────────────────────────── Candidate state machine ──────────────────────────

class CandidateStatus(str, enum.Enum):
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
    BGV_ON_HOLD     = "BGV_ON_HOLD"
    CONVERTED       = "CONVERTED"
    JOINED          = "JOINED"
    NOT_JOINED      = "NOT_JOINED"


CANDIDATE_TRANSITIONS: dict[str, list[str]] = {
    "CREATED":         ["OFFER_GENERATED"],
    "OFFER_GENERATED": ["OFFER_SENT"],
    "OFFER_SENT":      ["OFFER_ACCEPTED", "OFFER_REJECTED"],
    "OFFER_ACCEPTED":  ["DOCS_PENDING", "CONVERTED"],
    "OFFER_REJECTED":  [],
    "DOCS_PENDING":    ["DOCS_SUBMITTED"],
    "DOCS_SUBMITTED":  ["BGV_IN_PROGRESS", "CONVERTED"],
    "BGV_IN_PROGRESS": ["BGV_CLEAR", "BGV_FAILED"],
    "BGV_CLEAR":       ["CONVERTED"],
    "BGV_FAILED":      ["CONVERTED"],
    "CONVERTED":       ["JOINED", "NOT_JOINED"],
    "JOINED":          [],
    "NOT_JOINED":      [],
}


# ───────────────────────────────── Candidate ───────────────────────────────────

class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    candidate_ref: Mapped[str]   = mapped_column(String(20), unique=True, nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    last_name: Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str]            = mapped_column(String(150), nullable=False, index=True)
    email: Mapped[str]           = mapped_column(String(150), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[str]            = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ctc: Mapped[Optional[str]]   = mapped_column(String(50), nullable=True)
    expected_joining_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CandidateStatus.CREATED.value, index=True,
    )
    offer_letter_url: Mapped[Optional[str]]   = mapped_column(String(500), nullable=True)
    offer_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    offer_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_offer_accepted: Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    credentials_sent: Mapped[bool]            = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    documents: Mapped[list["CandidateDocument"]] = relationship(
        "CandidateDocument", back_populates="candidate", cascade="all, delete-orphan",
    )
    bgv_check: Mapped[Optional["BGVCheck"]] = relationship(
        "BGVCheck", back_populates="candidate", uselist=False, cascade="all, delete-orphan",
    )
    onboarded_employee: Mapped[Optional["OnboardedEmployee"]] = relationship(
        "OnboardedEmployee", back_populates="candidate", uselist=False, cascade="all, delete-orphan",
    )


# ─────────────────────────── Candidate documents ───────────────────────────────

class DocumentStatus(str, enum.Enum):
    PENDING  = "PENDING"
    UPLOADED = "UPLOADED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class CandidateDocument(Base):
    __tablename__ = "candidate_documents"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    candidate_id: Mapped[int]    = mapped_column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    doc_type: Mapped[str]        = mapped_column(String(50), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str]        = mapped_column(String(500), nullable=False)
    file_size_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str]          = mapped_column(String(20), nullable=False, default=DocumentStatus.UPLOADED.value)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="documents")


# ─────────────────────────────── BGV check ─────────────────────────────────────

class BGVStatus(str, enum.Enum):
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    CLEAR       = "CLEAR"
    FAILED      = "FAILED"
    REVIEW      = "REVIEW"
    ON_HOLD     = "ON_HOLD"


class BGVCheck(Base):
    __tablename__ = "bgv_checks"

    id: Mapped[int]                 = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    candidate_id: Mapped[int]       = mapped_column(Integer, ForeignKey("candidates.id"), unique=True, nullable=False, index=True)
    status: Mapped[str]             = mapped_column(String(20), nullable=False, default=BGVStatus.PENDING.value, index=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    initiated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"]  = relationship("Candidate", back_populates="bgv_check")


class BGVToken(Base):
    """One-time-use, time-bounded token for BGV vendor portal access."""
    __tablename__ = "bgv_tokens"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    candidate_id: Mapped[int]    = mapped_column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    token: Mapped[str]           = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    candidate: Mapped["Candidate"] = relationship("Candidate")


# ───────────────────────── Onboarded employee bridge ──────────────────────────

class OnboardedEmployeeStatus(str, enum.Enum):
    INACTIVE = "INACTIVE"
    ACTIVE   = "ACTIVE"


class OnboardedEmployee(Base):
    __tablename__ = "onboarded_employees"

    id: Mapped[int]                   = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    candidate_id: Mapped[int]         = mapped_column(Integer, ForeignKey("candidates.id"), unique=True, nullable=False, index=True)
    employee_code: Mapped[str]        = mapped_column(String(20), unique=True, nullable=False, index=True)
    manager_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("employees.id"), nullable=True)
    manager_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    joining_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str]               = mapped_column(String(20), nullable=False, default=OnboardedEmployeeStatus.INACTIVE.value)
    temp_password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    credentials_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[Optional[datetime]]        = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime]      = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    candidate: Mapped["Candidate"]    = relationship("Candidate", back_populates="onboarded_employee")
    manager: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys=[manager_id])  # type: ignore[name-defined]


# ─────────────────────────── Legacy portal user table ──────────────────────────

class UserRole(str, enum.Enum):
    ADMIN     = "ADMIN"
    HR        = "HR"
    MANAGER   = "MANAGER"
    EMPLOYEE  = "EMPLOYEE"
    CANDIDATE = "CANDIDATE"


class User(Base):
    """Legacy portal-auth table — used by candidates + early employees.

    New employees authenticate against `employees.password_hash` (a.k.a.
    `Employee.Password`) via the unified Onboarding `/api/v1/auth/login`
    handler. This table is kept for back-compat with onboarding flows that
    create candidate-portal logins before employee conversion.
    """
    __tablename__ = "users"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    email: Mapped[str]           = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str]   = mapped_column(String(200), nullable=False)
    role: Mapped[str]            = mapped_column(
        SAEnum("ADMIN", "HR", "MANAGER", "EMPLOYEE", "CANDIDATE", name="user_role_enum"),
        nullable=False, default=UserRole.EMPLOYEE.value,
    )
    is_active: Mapped[bool]      = mapped_column(Boolean, nullable=False, default=True)
    employee_id: Mapped[Optional[int]]   = mapped_column(Integer, ForeignKey("employees.id"), nullable=True)
    candidate_id: Mapped[Optional[int]]  = mapped_column(Integer, ForeignKey("candidates.id"), nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


__all__ = [
    "CandidateStatus", "CANDIDATE_TRANSITIONS",
    "Candidate", "CandidateDocument", "DocumentStatus",
    "BGVStatus", "BGVCheck", "BGVToken",
    "OnboardedEmployeeStatus", "OnboardedEmployee",
    "UserRole", "User",
]
