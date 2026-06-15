"""Pydantic schemas for the Announcements module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

# ---- Validation constants --------------------------------------------------

VALID_PRIORITIES  = {"normal", "important", "critical"}
VALID_STATUSES    = {"draft", "published", "archived"}
VALID_SCOPES      = {"company", "department", "role", "individual"}
VALID_CATEGORIES  = {
    "Company Updates", "Holidays", "Payroll", "Policies",
    "IT Maintenance", "Events", "Compliance", "Emergency Alerts", "Training",
}


# ---- Shared datetime normalizer --------------------------------------------

def _naive_utc(v: Optional[datetime]) -> Optional[datetime]:
    """Coerce an incoming datetime to a naive UTC datetime suitable for SQLite.

    • None         → None (field not provided)
    • naive        → assumed UTC, returned as-is
    • aware (+TZ)  → converted to UTC then tzinfo stripped

    This is used by every datetime field that touches DB storage so the
    comparison logic in _visibility_filter always operates in the same
    naive-UTC space.
    """
    if v is None:
        return None
    if v.tzinfo is not None:
        return v.astimezone(timezone.utc).replace(tzinfo=None)
    return v  # already naive → callers treat as UTC


# ---- Target sub-schemas ----------------------------------------------------

class AnnouncementTargetIn(BaseModel):
    employee_id:   Optional[int] = None
    department_id: Optional[str] = None
    role_id:       Optional[int] = None


class AnnouncementTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    employee_id:   Optional[int] = None
    department_id: Optional[str] = None
    role_id:       Optional[int] = None


# ---- Create / Update -------------------------------------------------------

class AnnouncementCreateIn(BaseModel):
    title:                 str
    content:               str
    category:              str = "Company Updates"
    priority:              str = "normal"
    target_scope:          str = "company"
    targets:               List[AnnouncementTargetIn] = []
    publish_at:            Optional[datetime] = None
    expires_at:            Optional[datetime] = None
    is_pinned:             bool = False
    allow_acknowledgement: bool = False
    attachment_path:       Optional[str] = None
    # When True (default) admin/hr announcements are published immediately;
    # any provided publish_at schedule is ignored.
    publish_immediately:   bool = True

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("target_scope")
    @classmethod
    def _check_scope(cls, v: str) -> str:
        if v not in VALID_SCOPES:
            raise ValueError(f"target_scope must be one of {sorted(VALID_SCOPES)}")
        return v

    @field_validator("publish_at", "expires_at", mode="after")
    @classmethod
    def _normalize_dt(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Normalize to naive UTC so the service can store it directly."""
        return _naive_utc(v)


class AnnouncementUpdateIn(BaseModel):
    title:                 Optional[str] = None
    content:               Optional[str] = None
    category:              Optional[str] = None
    priority:              Optional[str] = None
    target_scope:          Optional[str] = None
    targets:               Optional[List[AnnouncementTargetIn]] = None
    publish_at:            Optional[datetime] = None
    expires_at:            Optional[datetime] = None
    is_pinned:             Optional[bool] = None
    allow_acknowledgement: Optional[bool] = None
    attachment_path:       Optional[str] = None

    @field_validator("publish_at", "expires_at", mode="after")
    @classmethod
    def _normalize_dt(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Normalize to naive UTC so the service can store it directly."""
        return _naive_utc(v)


# ---- Output ----------------------------------------------------------------

class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    int
    title:                 str
    content:               str
    category:              str
    priority:              str
    status:                str
    created_by:            int
    creator_name:          Optional[str] = None
    created_at:            datetime
    updated_at:            datetime
    publish_at:            Optional[datetime] = None
    expires_at:            Optional[datetime] = None
    is_pinned:             bool
    attachment_path:       Optional[str] = None
    allow_acknowledgement: bool
    target_scope:          str
    targets:               List[AnnouncementTargetOut] = []

    # Viewer-specific (injected by service, not ORM attributes)
    is_read:                Optional[bool] = None
    is_acknowledged:        Optional[bool] = None
    # Admin/HR analytics fields
    read_count:             Optional[int] = None
    acknowledgement_count:  Optional[int] = None


class AnnouncementAnalyticsOut(BaseModel):
    announcement_id:      int
    title:                str
    total_targeted:       int
    read_count:           int
    acknowledgement_count: int


class AnnouncementReadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    announcement_id: int
    employee_id:     int
    read_at:         Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
