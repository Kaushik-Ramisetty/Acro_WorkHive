"""Unified Employee model — Core HRMS + Onboarding compatibility."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity
    employee_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    entra_object_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    # Personal info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    secondary_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Org
    designation_id: Mapped[str | None] = mapped_column(ForeignKey("designations.id"), nullable=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    reporting_manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    employment_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Sensitive fields
    aadhaar_encrypted: Mapped[str | None]      = mapped_column(String(255), nullable=True)
    pan_encrypted: Mapped[str | None]          = mapped_column(String(255), nullable=True)
    bank_account_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_ifsc: Mapped[str | None]              = mapped_column(String(20), nullable=True)

    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    blood_group: Mapped[str | None]       = mapped_column(String(10), nullable=True)
    emergency_contact_name: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Locale / personal
    location: Mapped[str | None]       = mapped_column(String(100), nullable=True)
    nationality: Mapped[str | None]    = mapped_column(String(100), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    time_zone: Mapped[str | None]      = mapped_column(String(40), nullable=True)

    # Onboarding capitalised aliases (same column, second Python attribute name).
    Nationality    = synonym("nationality")
    Marital_status = synonym("marital_status")

    # Auth
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    Password      = synonym("password_hash")

    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)

    # Resource-management profile fields (Phase 6, additive). Used by the
    # Bench page to display the employee's seniority + qualifications.
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    certifications: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Onboarding workflow fields
    official_email: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    is_activated: Mapped[bool]         = mapped_column(Boolean, default=False, nullable=False)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Soft delete + audit
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    role: Mapped["Role | None"]               = relationship(back_populates="employees")        # type: ignore[name-defined]
    designation: Mapped["Designation | None"] = relationship(back_populates="employees")        # type: ignore[name-defined]
    department: Mapped["Department | None"]   = relationship(back_populates="employees", foreign_keys=[department_id])  # type: ignore[name-defined]
    manager: Mapped["Employee | None"]        = relationship(remote_side="Employee.id", foreign_keys=[reporting_manager_id])

    @property
    def full_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))

    @property
    def role_name(self) -> str | None:
        return self.role.name if self.role else None
