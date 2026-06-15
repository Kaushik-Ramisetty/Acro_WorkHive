"""Single-row-per-task heartbeat used by the startup self-heal sweep.

Each scheduled background task that we care about updates its row here on
successful completion. The FastAPI lifespan reads this on boot: if the
last successful run is older than a threshold (default 25h), it runs the
task synchronously once so balances stay current even in dev
environments where Celery beat is not running.

Why a dedicated table:
  - `last_run_at` doesn't fit naturally on any existing model.
  - Using Redis would couple this check to Redis being up, defeating
    the point (dev fallback).
  - The table is one row per task name — trivial cost.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SchedulerHealth(Base):
    __tablename__ = "scheduler_health"

    # Task name is the primary key — one row per task.
    task_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
