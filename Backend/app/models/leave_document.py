"""Documents attached to leave requests.

A row is created on upload with `scan_status='pending'` and the file is
stored under LEAVE_UPLOAD_DIR before the scan runs. The scanner then
updates the row in place:
  - 'clean'        : file is OK; visible to approvers / employees
  - 'infected'     : file is quarantined (moved out of the main path),
                     and the row is kept for auditing
  - 'scan_failed'  : scanner unavailable / error; file is kept in
                     quarantine and admins are notified

Only 'clean' documents can be downloaded by anyone other than admins.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeaveDocument(Base):
    __tablename__ = "leave_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_request_id: Mapped[str] = mapped_column(
        ForeignKey("leave_requests.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    scan_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    scan_engine: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scan_detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    leave_request: Mapped["LeaveRequest"] = relationship()  # type: ignore[name-defined]
    uploader: Mapped["Employee"] = relationship(foreign_keys=[uploaded_by])  # type: ignore[name-defined]
