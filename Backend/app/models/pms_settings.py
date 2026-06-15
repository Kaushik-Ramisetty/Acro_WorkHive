"""PMS phase-level deadline settings.

One row per PMS phase.  HR (or admin) can update `default_days` at any time;
the system auto-computes the suggested deadline as  today + default_days.
No migration needed — Base.metadata.create_all() creates the table on first boot.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PMSPhaseSettings(Base):
    __tablename__ = "pms_phase_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phase_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    default_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=func.now())
