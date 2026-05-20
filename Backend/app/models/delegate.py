"""Delegate assignment: a manager designates a deputy to approve on
their behalf for a time window (vacation, parental leave, etc).

A row is "active" when:
  - is_active is True, AND
  - today is between start_date and end_date (inclusive)

There can be at most one active delegate per manager at a time. The
service layer enforces this on insert/update; the model keeps the
column-level constraint loose to avoid migration headaches.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DelegateAssignment(Base):
    __tablename__ = "delegate_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    delegate_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    manager: Mapped["Employee"] = relationship(foreign_keys=[manager_id])  # type: ignore[name-defined]
    delegate: Mapped["Employee"] = relationship(foreign_keys=[delegate_id])  # type: ignore[name-defined]
