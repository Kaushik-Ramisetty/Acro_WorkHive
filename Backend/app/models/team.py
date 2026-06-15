"""Team + TeamMember models.

A `Team` is a soft grouping owned by a department, led by an employee
(`lead_id`), with N members. Distinct from the org-chart
`reporting_manager_id` chain on Employee — teams are flexible groupings
(squads, pods, capability groups) layered on top of the formal hierarchy.

Member rows carry their own role-in-team string so the same employee can
be a senior on one team and a member on another. Soft-deleted via
`is_active` so historical team composition is preserved.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True, index=True
    )

    # Soft delete — preserves history when a team is dissolved.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped["Department | None"] = relationship()  # type: ignore[name-defined]
    lead: Mapped["Employee | None"] = relationship(foreign_keys=[lead_id])  # type: ignore[name-defined]
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("name", "department_id", name="uq_team_name_per_dept"),
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    # Free-form role on this specific team (e.g. "Senior", "Member", "Intern").
    role_in_team: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    added_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    team: Mapped["Team"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]

    __table_args__ = (
        # An employee can be on the same team only once (active at a time).
        UniqueConstraint("team_id", "employee_id", name="uq_team_member"),
    )
