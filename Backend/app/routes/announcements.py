"""Announcements API routes.

All business logic lives in app.services.announcement_service.
This file is intentionally thin: auth, input binding, service call, serialise.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.employee import Employee
from app.schemas.announcement import (
    AnnouncementAnalyticsOut,
    AnnouncementCreateIn,
    AnnouncementOut,
    AnnouncementReadOut,
    AnnouncementUpdateIn,
)
from app.services import announcement_service as svc

router = APIRouter(prefix="/announcements", tags=["announcements"])


# ---------------------------------------------------------------------------
# Feed endpoints (employee / manager)
# ---------------------------------------------------------------------------

@router.get("", summary="List announcements visible to the current user")
def list_announcements(
    mode:        str  = Query("feed", description="'feed' for personal view, 'manage' for admin table"),
    unread_only: bool = Query(False),
    category:    Optional[str] = Query(None),
    priority:    Optional[str] = Query(None),
    status:      Optional[str] = Query(None, description="admin mode only: draft|published|archived"),
    search:      Optional[str] = Query(None),
    limit:       int  = Query(20, ge=1, le=100),
    offset:      int  = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = user.role.name.lower() if user.role else "employee"

    if mode == "manage" and role in ("admin", "hr"):
        items, total = svc.list_for_admin(
            db, user,
            status_filter=status,
            category=category,
            priority=priority,
            search=search,
            limit=limit,
            offset=offset,
        )
    elif role == "manager":
        items, total = svc.list_for_manager(
            db, user,
            unread_only=unread_only,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        )
    else:
        items, total = svc.list_for_employee(
            db, user,
            unread_only=unread_only,
            category=category,
            priority=priority,
            search=search,
            limit=limit,
            offset=offset,
        )

    return {"total": total, "items": items}


@router.get("/latest", summary="Latest announcements visible to the current user (lightweight)")
def latest_announcements(
    limit: int = Query(5, ge=1, le=25),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Convenience endpoint for dashboard widgets (e.g. the Admin "System
    Narrative" card). Returns a bare list sorted by pin-first then most
    recent — same audience filtering as the main feed, just a thinner
    payload and no pagination envelope.
    """
    role = user.role.name.lower() if user.role else "employee"
    if role in ("admin", "hr"):
        items, _ = svc.list_for_admin(
            db, user,
            status_filter="published",
            limit=limit, offset=0,
        )
    elif role == "manager":
        items, _ = svc.list_for_manager(
            db, user,
            unread_only=False, limit=limit, offset=0,
        )
    else:
        items, _ = svc.list_for_employee(
            db, user,
            unread_only=False, limit=limit, offset=0,
        )
    return items


@router.get("/unread-count", summary="Count unread announcements for current user")
def unread_count(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return {"count": svc.unread_count_for(db, user)}


@router.get("/{ann_id}", response_model=AnnouncementOut, summary="Get a single announcement")
def get_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.get_single(db, ann_id, user)


# ---------------------------------------------------------------------------
# Create / Update / Delete
# ---------------------------------------------------------------------------

@router.post("", response_model=AnnouncementOut, status_code=201, summary="Create a new announcement")
def create_announcement(
    payload: AnnouncementCreateIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ann = svc.create_announcement(db, user, payload)
    return svc.get_single(db, ann.id, user)


@router.put("/{ann_id}", response_model=AnnouncementOut, summary="Update an announcement")
def update_announcement(
    ann_id: int,
    payload: AnnouncementUpdateIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ann = svc.update_announcement(db, ann_id, user, payload)
    return svc.get_single(db, ann.id, user)


@router.delete("/{ann_id}", status_code=204, summary="Delete an announcement")
def delete_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    svc.delete_announcement(db, ann_id, user)


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

@router.post("/{ann_id}/publish", response_model=AnnouncementOut, summary="Publish an announcement")
def publish_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ann = svc.publish_announcement(db, ann_id, user)
    return svc.get_single(db, ann.id, user)


@router.post("/{ann_id}/archive", response_model=AnnouncementOut, summary="Archive an announcement")
def archive_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ann = svc.archive_announcement(db, ann_id, user)
    return svc.get_single(db, ann.id, user)


# ---------------------------------------------------------------------------
# Read / Acknowledgement tracking
# ---------------------------------------------------------------------------

@router.post("/{ann_id}/read", response_model=AnnouncementReadOut, summary="Mark announcement as read")
def mark_read(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.mark_read(db, ann_id, user)


@router.post("/{ann_id}/acknowledge", response_model=AnnouncementReadOut, summary="Acknowledge an announcement")
def acknowledge(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.acknowledge(db, ann_id, user)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/{ann_id}/analytics", response_model=AnnouncementAnalyticsOut, summary="Read/ack stats")
def analytics(
    ann_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.get_analytics(db, ann_id, user)
