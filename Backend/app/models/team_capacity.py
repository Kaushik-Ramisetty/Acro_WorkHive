"""Team capacity policies + blackout periods.

`TeamCapacityPolicy` caps how many of a manager's direct reports may be
on approved/pending leave concurrently. Validators consult this when an
employee applies.

`BlackoutPeriod` declares date ranges where leave is restricted:
  - scope_type='global'      : applies to everyone (e.g. year-end freeze)
  - scope_type='department'  : applies to a department (scope_id = dep id)
  - scope_type='manager'     : applies to a manager's team (scope_id = manager_id)

Only admins can create/manage these; managers can read those that affect
their team.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TeamCapacityPolicy(Base):
    __tablename__ = "team_capacity_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    max_concurrent_on_leave: Mapped[int] = mapped_column(Integer, nullable=False)
    # Phase 5C: alternative cap expressed as a percentage of the manager's
    # active direct reports. When non-null, the effective cap is
    #     ceil(team_size * pct / 100)
    # and the LOWER of (absolute, derived-from-percent) is enforced so a
    # policy can carry both knobs without surprise.
    max_concurrent_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    manager: Mapped["Employee"] = relationship(foreign_keys=[manager_id])  # type: ignore[name-defined]


class BlackoutPeriod(Base):
    __tablename__ = "blackout_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # scope_id meaning depends on scope_type:
    #   'global'     -> None
    #   'department' -> Department.id (string PK)
    #   'manager'    -> Employee.id   (integer)
    # Stored as string for flexibility; validators cast as needed.
    scope_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
