"""LeaveAuditLog — append-only trail of every state change on a leave request."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeaveAuditLog(Base):
    __tablename__ = "leave_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_request_id: Mapped[str] = mapped_column(ForeignKey("leave_requests.id"), nullable=False, index=True)

    # 'created', 'approved_manager', 'approved_hr', 'rejected',
    # 'cancel_requested', 'cancelled', 'cancel_approved_manager', 'cancel_approved_hr'
    action: Mapped[str] = mapped_column(String(40), nullable=False)

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    actor: Mapped["Employee | None"] = relationship(foreign_keys=[actor_id])  # type: ignore[name-defined]
