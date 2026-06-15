"""Append-only audit log for resource-allocation mutations.

Every state change on `resource_allocations` (and every successful
team-member / team mutation routed through the service layer) writes a
row here. Rows are never updated or deleted; corrections are made by
writing a new compensating action.

action ∈ {
  'allocation_created', 'allocation_updated', 'allocation_released',
  'allocation_extended', 'allocation_reassigned',
  'skills_synced', 'project_created',
  'team_created', 'team_updated', 'team_deleted',
  'team_member_added', 'team_member_removed', 'team_lead_assigned',
}
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResourceAllocationAudit(Base):
    __tablename__ = "resource_allocation_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_allocations.id"), nullable=True, index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True, index=True
    )

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # JSON-serializable diff snapshot. Stored as TEXT for portability across
    # SQLite (dev) and SQL Server (prod).
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    actor: Mapped["Employee | None"] = relationship(foreign_keys=[actor_id])  # type: ignore[name-defined]
