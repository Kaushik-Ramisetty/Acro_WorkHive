"""Policies module ORM models.

Four tables underpin the policies module:

  policies                  — one row per policy (the "container").
  policy_versions           — every edit creates a new version row; PDFs live here.
  policy_categories         — taxonomy (HR, IT, Compliance, ...).
  policy_acknowledgements   — per-employee acknowledgement of a SPECIFIC version
                              so audit trails survive when a new version ships.

Design notes
------------
* `policies.current_version_id` points at the *currently-published* version. It is
  a plain Integer (no FK constraint) because policies ↔ policy_versions form a
  circular reference (policy_versions.policy_id → policies.id is the canonical
  link). Application code keeps the pointer in sync; we avoid a circular FK to
  stay portable across SQLite and SQL Server without resorting to `use_alter`.

* Soft delete is implemented via `is_deleted` on `policies` so old acknowledgements
  remain referentially valid for audit. The version rows are never deleted —
  even after archiving — so the audit trail is preserved forever.

* Datetimes are stored as naive UTC (no tzinfo) following the project-wide
  convention. See `utils/time_utils.now_utc()` for the canonical helper.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# policy_categories
# ---------------------------------------------------------------------------

class PolicyCategory(Base):
    """Lookup table for policy taxonomy.

    Seeded on app startup with a known list (HR, IT, Compliance, …). Admins
    can add more via POST /policies/categories.
    """
    __tablename__ = "policy_categories"

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:        Mapped[str]            = mapped_column(String(80),  nullable=False, unique=True, index=True)
    description: Mapped[str | None]     = mapped_column(String(255), nullable=True)
    created_at:  Mapped[datetime]       = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Reverse relationship for convenience (no cascade — policies can outlive
    # a category rename; soft delete on category is intentionally not supported
    # yet to keep things simple).
    policies: Mapped[list["Policy"]] = relationship(back_populates="category")


# ---------------------------------------------------------------------------
# policies
# ---------------------------------------------------------------------------

class Policy(Base):
    """A policy "container" — the thing employees see in the list.

    A policy has many versions over its lifetime. Only the version pointed at
    by `current_version_id` is what gets shown in the read-only feed when
    `status == 'published'`.
    """
    __tablename__ = "policies"

    id:                 Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    title:              Mapped[str]             = mapped_column(String(200), nullable=False)
    slug:               Mapped[str]             = mapped_column(String(220), nullable=False, unique=True, index=True)
    description:        Mapped[str | None]      = mapped_column(Text,         nullable=True)

    category_id:        Mapped[int | None]      = mapped_column(
        ForeignKey("policy_categories.id"), nullable=True, index=True
    )

    # Points at the version that is "live" for readers. Application-managed
    # (no FK constraint) to avoid a circular FK between policies and
    # policy_versions. NULL until the first version is created.
    current_version_id: Mapped[int | None]      = mapped_column(Integer, nullable=True, index=True)

    # Lifecycle: draft | published | archived
    status:             Mapped[str]             = mapped_column(String(20), default="draft", nullable=False, index=True)

    created_by:         Mapped[int]             = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    created_at:         Mapped[datetime]        = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at:         Mapped[datetime]        = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at:        Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Soft-delete for safety. Acknowledgement audit rows survive deletion.
    is_deleted:         Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    category: Mapped["PolicyCategory | None"] = relationship(back_populates="policies")
    creator:  Mapped["Employee"]              = relationship(foreign_keys=[created_by])  # type: ignore[name-defined]
    versions: Mapped[list["PolicyVersion"]]   = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        foreign_keys="PolicyVersion.policy_id",
        order_by="PolicyVersion.version_number.desc()",
    )


# ---------------------------------------------------------------------------
# policy_versions
# ---------------------------------------------------------------------------

class PolicyVersion(Base):
    """An immutable revision of a policy.

    Every edit produces a brand new row. PDF attachments are referenced by
    *path* (not stored as BLOBs) — see `pdf_path`. The actual file lives on the
    filesystem under `UPLOAD_DIR/policies/<policy_id>/` (new uploads) or under
    the legacy `Frontend/public/policies/` path (pre-existing PDFs).
    """
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version_number", name="uq_policy_version_number"),
    )

    id:             Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id:      Mapped[int]             = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int]             = mapped_column(Integer, nullable=False)

    content:        Mapped[str | None]      = mapped_column(Text, nullable=True)
    pdf_path:       Mapped[str | None]      = mapped_column(String(500), nullable=True)
    change_summary: Mapped[str | None]      = mapped_column(String(500), nullable=True)

    effective_date: Mapped[date | None]     = mapped_column(Date, nullable=True)
    expiry_date:    Mapped[date | None]     = mapped_column(Date, nullable=True)

    is_published:   Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_by:     Mapped[int]             = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    created_at:     Mapped[datetime]        = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    policy:  Mapped["Policy"]    = relationship(back_populates="versions", foreign_keys=[policy_id])
    creator: Mapped["Employee"]  = relationship(foreign_keys=[created_by])  # type: ignore[name-defined]
    acknowledgements: Mapped[list["PolicyAcknowledgement"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# policy_acknowledgements
# ---------------------------------------------------------------------------

class PolicyAcknowledgement(Base):
    """Per-employee ACK row scoped to a specific version.

    Acknowledgements are version-scoped on purpose: when a new policy version
    is published, employees may need to re-acknowledge the new terms. The
    UniqueConstraint guarantees one ACK per (version, employee).
    """
    __tablename__ = "policy_acknowledgements"
    __table_args__ = (
        UniqueConstraint("policy_version_id", "employee_id", name="uq_policy_ack"),
    )

    id:                Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_version_id: Mapped[int]      = mapped_column(
        ForeignKey("policy_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id:       Mapped[int]      = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    acknowledged_at:   Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    version:  Mapped["PolicyVersion"] = relationship(back_populates="acknowledgements")
    employee: Mapped["Employee"]      = relationship(foreign_keys=[employee_id])  # type: ignore[name-defined]
