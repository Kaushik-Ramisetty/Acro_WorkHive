"""Notification model — in-app notification feed for users."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    # Discriminator: 'leave_applied', 'leave_approved', 'leave_rejected',
    # 'leave_cancel_requested', 'leave_cancelled', 'leave_pending_your_approval', etc.
    type: Mapped[str] = mapped_column(String(40), nullable=False, default="info", index=True)

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Loosely linked. We don't add a hard FK to leave_requests so that
    # future deletion of a request doesn't crash notifications.
    leave_request_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Generic reference target (per hrms_schema_complete.xlsx → notifications).
    # When the notification is about, e.g., an attendance_records row, this is
    # populated as ('attendance_records', 'AR000002'). Optional / additive.
    reference_table: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reference_id: Mapped[str | None]    = mapped_column(String(40), nullable=True)

    # Frontend deep-link target. Populated server-side from `type` +
    # reference when omitted (see services/notification_service.notify).
    # Nullable so older rows keep working — the frontend has a fallback map.
    action_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional small JSON-blob for arbitrary metadata (badge tone, route
    # params, etc.). Stored as a string so it works across SQLite + MSSQL
    # without dialect-specific JSON types.
    meta_json: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)

    recipient: Mapped["Employee"] = relationship(foreign_keys=[recipient_id])  # type: ignore[name-defined]
