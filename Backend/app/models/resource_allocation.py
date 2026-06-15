"""Resource allocation: links an employee to a project for a window.

A single Employee may have multiple ACTIVE allocations (managers can
have up to 20, ICs up to 3 — enforced in the service layer). Released
allocations stay in the table with status='completed' and an
`actual_end_date` so we have a full project history per employee.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResourceAllocation(Base):
    __tablename__ = "resource_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    # The manager assigned to this allocation. May differ from the project's
    # project_manager_id over time (e.g. delegations). Captured per-row so
    # historical reassignments don't rewrite the project row.
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Filled when the employee is released early; preserved alongside
    # end_date so the "originally planned" vs "actually released" split is
    # visible in the audit / bench-duration calculation.
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 'active' = currently allocated, counts against the 3/20 cap.
    # 'completed' = released; preserved for history.
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    project: Mapped["Project"] = relationship()  # type: ignore[name-defined]
    manager: Mapped["Employee | None"] = relationship(foreign_keys=[manager_id])  # type: ignore[name-defined]
