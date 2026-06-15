"""Generic AuditLog — append-only trail of any actor action on any target.

Mirrors the `audit_logs` sheet in hrms_schema_complete.xlsx. Distinct from
`leave_audit_logs` (leave-specific). For new audit-trail requirements that
span multiple target tables (regularizations, comp-off, attendance edits,
etc.), use this model.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. AUDIT00001
    actor_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)

    action: Mapped[str | None]       = mapped_column(String(60), nullable=True)
    target_table: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    target_id: Mapped[str | None]    = mapped_column(String(40), nullable=True, index=True)

    # JSON-as-text — portable across SQLite + SQL Server.
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    actor: Mapped["Employee | None"] = relationship(foreign_keys=[actor_employee_id])  # type: ignore[name-defined]
