"""Pydantic schemas for the Policies module.

All datetime fields are normalised to **naive UTC** before they reach the
service layer — see `_naive_utc` below — so storage comparisons remain
consistent (matches the convention used by Announcements).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_STATUSES = {"draft", "published", "archived"}


# ---------------------------------------------------------------------------
# Shared datetime normaliser
# ---------------------------------------------------------------------------

def _naive_utc(v: Optional[datetime]) -> Optional[datetime]:
    """Coerce any incoming datetime to a naive UTC datetime (no tzinfo).

    Mirrors `app/schemas/announcement.py::_naive_utc` so the two modules speak
    a single canonical datetime convention.
    """
    if v is None:
        return None
    if v.tzinfo is not None:
        return v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class PolicyCategoryIn(BaseModel):
    name:        str
    description: Optional[str] = None


class PolicyCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:          int
    name:        str
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Policy versions
# ---------------------------------------------------------------------------

class PolicyVersionCreateIn(BaseModel):
    """Body for POST /policies/{id}/versions (JSON, no file).

    PDF uploads use the dedicated multipart endpoint; this schema lets admins
    create a version that references a pre-existing pdf_path or carries inline
    text content only.
    """
    content:        Optional[str]  = None
    pdf_path:       Optional[str]  = None
    change_summary: Optional[str]  = None
    effective_date: Optional[date] = None
    expiry_date:    Optional[date] = None
    publish:        bool           = False  # if True, set this version live immediately


class PolicyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:             int
    policy_id:      int
    version_number: int
    content:        Optional[str]  = None
    pdf_path:       Optional[str]  = None
    change_summary: Optional[str]  = None
    effective_date: Optional[date] = None
    expiry_date:    Optional[date] = None
    is_published:   bool
    created_by:     int
    created_at:     datetime


# ---------------------------------------------------------------------------
# Policy create / update
# ---------------------------------------------------------------------------

class PolicyCreateIn(BaseModel):
    """Body for POST /policies — creates the container *and* an initial v1.

    If `pdf_path` is provided, v1 is created referencing it. If `content` is
    provided, v1 is created with inline content. Both may be set. If neither,
    the policy starts with a stub v1 that admins fill in later.
    """
    title:          str
    description:    Optional[str]  = None
    category_id:    Optional[int]  = None
    content:        Optional[str]  = None
    pdf_path:       Optional[str]  = None
    change_summary: Optional[str]  = None
    effective_date: Optional[date] = None
    expiry_date:    Optional[date] = None

    # Default: create as published so admins get the same one-step "publish on
    # create" UX the announcements module ships with.
    publish_immediately: bool = True


class PolicyUpdateIn(BaseModel):
    """Body for PATCH /policies/{id} — metadata-only update.

    Does **not** create a new version. Use the versions endpoint for content
    changes (versioned audit trail). This endpoint only touches title /
    description / category.
    """
    title:       Optional[str]  = None
    description: Optional[str]  = None
    category_id: Optional[int]  = None


# ---------------------------------------------------------------------------
# Policy output
# ---------------------------------------------------------------------------

class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 int
    title:              str
    slug:               str
    description:        Optional[str]   = None
    category_id:        Optional[int]   = None
    category_name:      Optional[str]   = None
    status:             str
    created_by:         int
    creator_name:       Optional[str]   = None
    created_at:         datetime
    updated_at:         datetime
    archived_at:        Optional[datetime] = None

    # Current version snapshot (denormalised for convenient frontend reads).
    current_version_id:     Optional[int]      = None
    current_version_number: Optional[int]      = None
    current_pdf_path:       Optional[str]      = None
    current_effective_date: Optional[date]     = None
    current_expiry_date:    Optional[date]     = None
    current_change_summary: Optional[str]      = None
    current_version_created_at: Optional[datetime] = None

    # Per-viewer flags (injected by service for employee/manager feed).
    is_acknowledged: Optional[bool] = None

    # Admin-only analytics.
    versions_count:        Optional[int] = None
    acknowledgement_count: Optional[int] = None

    @field_validator("created_at", "updated_at", "archived_at", "current_version_created_at", mode="after")
    @classmethod
    def _norm_dt(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _naive_utc(v)


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------

class PolicyAcknowledgementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    policy_version_id: int
    employee_id:       int
    acknowledged_at:   datetime


class PolicyAnalyticsOut(BaseModel):
    policy_id:             int
    title:                 str
    versions_count:        int
    acknowledgement_count: int
    current_version_id:    Optional[int] = None
