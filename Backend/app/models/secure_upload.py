"""SecureUpload — centralized tracking for every file uploaded to the HRMS.

One row per upload attempt across all modules (leave, onboarding, BGV,
regularization, profile, payroll, timesheet, etc.). Drives the malware-scan
state machine and feeds the admin "Quarantine & Scans" view.

State machine
-------------
    uploaded_temp → scanning → safe                (happy path)
                            → infected   (quarantined)
                            → scan_failed (quarantined, retryable)
                            → rejected   (validation failure / admin action)

Storage layout
--------------
    {root}/_temp/{id}_{stored_name}        immediately after upload
    {root}/{module}/{stored_name}          after scan returns 'safe'
    {root}/_quarantine/{id}_{stored_name}  after scan returns 'infected' or 'scan_failed'
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SecureUpload(Base):
    __tablename__ = "secure_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Provenance
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    module:       Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # 'leave' | 'onboarding' | 'regularization' | 'employee_documents'
    # 'payroll' | 'timesheet' | 'profile' | …
    reference_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)

    # File facts (post-sanitization)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename:   Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type:         Mapped[str | None] = mapped_column(String(80),  nullable=True)
    size_bytes:        Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Filesystem pointers
    temp_path:       Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_path:    Mapped[str | None] = mapped_column(String(500), nullable=True)
    quarantine_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Scan state
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded_temp", index=True)
    # 'uploaded_temp' | 'scanning' | 'safe' | 'infected' | 'scan_failed' | 'rejected'
    malware_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scan_engine: Mapped[str | None] = mapped_column(String(40),  nullable=True)
    scan_signature: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scan_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scan_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scan_started_at:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    uploader: Mapped["Employee"] = relationship(foreign_keys=[uploaded_by])  # type: ignore[name-defined]
