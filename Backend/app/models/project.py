"""Project / task / timesheet models (timesheet module).

Mirrors the `projects`, `tasks`, `timesheets`, `timesheet_entries`,
`timesheet_payroll_sync` sheets in hrms_schema_complete.xlsx.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. PRJ001
    project_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str | None]         = mapped_column(String(200), nullable=True)
    client_name: Mapped[str | None]  = mapped_column(String(200), nullable=True)

    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    project_manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None]   = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    department: Mapped["Department | None"] = relationship()  # type: ignore[name-defined]
    manager: Mapped["Employee | None"]      = relationship(foreign_keys=[project_manager_id])  # type: ignore[name-defined]
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. TSK001
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str | None]        = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project: Mapped["Project | None"] = relationship(back_populates="tasks")
    assignee: Mapped["Employee | None"] = relationship()  # type: ignore[name-defined]


class Timesheet(Base):
    __tablename__ = "timesheets"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. TS000001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    period_type: Mapped[str | None]  = mapped_column(String(20), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None]   = mapped_column(Date, nullable=True)

    total_logged_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), default="draft", nullable=True, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
    entries: Mapped[list["TimesheetEntry"]] = relationship(back_populates="timesheet")


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. TE0000001
    timesheet_id: Mapped[str | None] = mapped_column(ForeignKey("timesheets.id"), nullable=True, index=True)
    employee_id: Mapped[int | None]  = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)

    entry_date: Mapped[date | None]  = mapped_column(Date, nullable=True, index=True)
    project_id: Mapped[str | None]   = mapped_column(ForeignKey("projects.id"), nullable=True)
    task_id: Mapped[str | None]      = mapped_column(ForeignKey("tasks.id"), nullable=True)

    logged_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None]      = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_manual_entry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    attendance_record_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_records.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    timesheet: Mapped["Timesheet | None"] = relationship(back_populates="entries")


class TimesheetPayrollSync(Base):
    __tablename__ = "timesheet_payroll_sync"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. TPS00001
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    month: Mapped[str | None] = mapped_column(String(20),  nullable=True)
    year: Mapped[int | None]  = mapped_column(Integer,     nullable=True, index=True)

    timesheet_id: Mapped[str | None] = mapped_column(ForeignKey("timesheets.id"), nullable=True)
    payroll_summary_id: Mapped[str | None] = mapped_column(ForeignKey("payroll_attendance_summary.id"), nullable=True)

    timesheet_hours: Mapped[float | None]  = mapped_column(Float, nullable=True)
    attendance_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_hours: Mapped[float | None]   = mapped_column(Float, nullable=True)

    has_mismatch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mismatch_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
