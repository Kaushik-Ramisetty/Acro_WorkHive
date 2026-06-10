"""Salary Hike Request — pending approval workflow before applying a salary hike.

Admin creates a hike request → Finance reviews (approve/reject) → on approval
the salary revision is applied via payroll_service.create_salary_revision.

Status flow:
    pending_finance_review → approved  (salary applied)
                           → rejected  (salary unchanged)
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SalaryHikeRequest(Base):
    __tablename__ = "salary_hike_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    old_ctc: Mapped[float] = mapped_column(Float, default=0.0)
    new_ctc: Mapped[float] = mapped_column(Float, nullable=False)
    hike_type: Mapped[str] = mapped_column(String(20), nullable=False)   # 'percentage' or 'fixed'
    hike_value: Mapped[float] = mapped_column(Float, nullable=False)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(30), default="pending_finance_review", nullable=False, index=True
    )  # pending_finance_review | approved | rejected

    requested_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Production-grade approval fields (v15) ────────────────────────────
    # approved_by_id is set when Finance formally approves (status → approved).
    # reviewed_by_id may be set earlier when Finance reviews without approving.
    approved_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # rejection_reason is mandatory when status = 'rejected'.
    # Stored separately from review_comment to make it findable in compliance audits.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flag: the effective date was checked against closed payroll months at create time.
    effective_date_validated: Mapped[bool] = mapped_column(
        Integer, default=0, nullable=False  # stored as 0/1 for SQL Server compat
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    employee = relationship("Employee", foreign_keys=[employee_id])
    requested_by = relationship("Employee", foreign_keys=[requested_by_id])
    reviewed_by = relationship("Employee", foreign_keys=[reviewed_by_id])
    approved_by = relationship("Employee", foreign_keys=[approved_by_id])
