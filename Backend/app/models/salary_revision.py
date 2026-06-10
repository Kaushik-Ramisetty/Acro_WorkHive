"""Salary Revision Log — enterprise audit table for salary structure changes.

Every time a new salary revision is created via upsert_salary_structure,
a SalaryRevisionLog row is written capturing:
  - old vs new salary component snapshots
  - CTC difference + % change
  - who made the change (revised_by_id)
  - why (revision_reason)
  - effective_from date

This table is the single source of truth for the revision audit trail.
Closed payrolls remain immutable — they reference salary_structures by id.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SalaryRevisionLog(Base):
    __tablename__ = "salary_revision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Employee this revision belongs to
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Exact salary_structures rows for diff/comparison
    old_salary_structure_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("salary_structures.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_salary_structure_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salary_structures.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── CTC snapshots ────────────────────────────────────────────────────────
    old_annual_ctc: Mapped[float] = mapped_column(Float, default=0.0)
    new_annual_ctc: Mapped[float] = mapped_column(Float, default=0.0)
    ctc_difference: Mapped[float] = mapped_column(Float, default=0.0)   # new − old
    ctc_change_pct: Mapped[float] = mapped_column(Float, default=0.0)   # % change

    # ── Earnings component snapshots ─────────────────────────────────────────
    old_basic: Mapped[float] = mapped_column(Float, default=0.0)
    new_basic: Mapped[float] = mapped_column(Float, default=0.0)
    old_hra: Mapped[float] = mapped_column(Float, default=0.0)
    new_hra: Mapped[float] = mapped_column(Float, default=0.0)
    old_da: Mapped[float] = mapped_column(Float, default=0.0)
    new_da: Mapped[float] = mapped_column(Float, default=0.0)
    old_special_allowance: Mapped[float] = mapped_column(Float, default=0.0)
    new_special_allowance: Mapped[float] = mapped_column(Float, default=0.0)
    old_transport_allowance: Mapped[float] = mapped_column(Float, default=0.0)
    new_transport_allowance: Mapped[float] = mapped_column(Float, default=0.0)
    old_medical_allowance: Mapped[float] = mapped_column(Float, default=0.0)
    new_medical_allowance: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Derived monthly totals ────────────────────────────────────────────────
    old_gross_monthly: Mapped[float] = mapped_column(Float, default=0.0)
    new_gross_monthly: Mapped[float] = mapped_column(Float, default=0.0)
    old_net_monthly: Mapped[float] = mapped_column(Float, default=0.0)
    new_net_monthly: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Deduction snapshots ───────────────────────────────────────────────────
    old_pf_employee: Mapped[float] = mapped_column(Float, default=0.0)
    new_pf_employee: Mapped[float] = mapped_column(Float, default=0.0)
    old_esi_employee: Mapped[float] = mapped_column(Float, default=0.0)
    new_esi_employee: Mapped[float] = mapped_column(Float, default=0.0)
    old_professional_tax: Mapped[float] = mapped_column(Float, default=0.0)
    new_professional_tax: Mapped[float] = mapped_column(Float, default=0.0)
    old_tds: Mapped[float] = mapped_column(Float, default=0.0)
    new_tds: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Revision metadata ─────────────────────────────────────────────────────
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    employee = relationship("Employee", foreign_keys=[employee_id])
    revised_by = relationship("Employee", foreign_keys=[revised_by_id])
    old_structure = relationship("SalaryStructure", foreign_keys=[old_salary_structure_id])
    new_structure = relationship("SalaryStructure", foreign_keys=[new_salary_structure_id])
