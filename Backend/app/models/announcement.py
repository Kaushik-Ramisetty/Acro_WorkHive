"""Announcements module models.

Three tables:
  announcements           — the announcement record itself
  announcement_targets    — audience targeting (company / dept / role / individual)
  announcement_reads      — per-employee read + acknowledgement tracking
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Taxonomy
    category: Mapped[str] = mapped_column(String(50), default="Company Updates", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)
    # priority: normal | important | critical

    # Lifecycle
    # status: draft | published | archived
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)

    # Authorship
    created_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Scheduling
    publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Features
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allow_acknowledgement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Audience scope: company | department | role | individual
    target_scope: Mapped[str] = mapped_column(String(20), default="company", nullable=False, index=True)

    # Relationships
    creator: Mapped["Employee"] = relationship(foreign_keys=[created_by])  # type: ignore[name-defined]
    targets: Mapped[list["AnnouncementTarget"]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )
    reads: Mapped[list["AnnouncementRead"]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan"
    )


class AnnouncementTarget(Base):
    """Stores one audience-targeting row per announcement.

    For scope 'company'   → no rows needed (all see it).
    For scope 'department'→ one row per department_id.
    For scope 'role'      → one row per role_id.
    For scope 'individual'→ one row per employee_id.
    """
    __tablename__ = "announcement_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True, index=True)

    announcement: Mapped["Announcement"] = relationship(back_populates="targets")


class AnnouncementRead(Base):
    """Tracks when an employee read or acknowledged an announcement.

    Unique per (announcement_id, employee_id) — a composite UNIQUE constraint
    ensures we never double-insert; the service layer uses INSERT-OR-IGNORE style
    upsert semantics.
    """
    __tablename__ = "announcement_reads"
    __table_args__ = (
        UniqueConstraint("announcement_id", "employee_id", name="uq_ann_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)

    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    announcement: Mapped["Announcement"] = relationship(back_populates="reads")
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
