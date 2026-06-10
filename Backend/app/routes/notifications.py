"""Notification routes — in-app feed for the current user.

Endpoints
---------
- GET    /notifications              paginated list (filters: type/category/search/unread)
- GET    /notifications/recent       top N (default 10) — used by the navbar dropdown
- GET    /notifications/unread-count
- PATCH  /notifications/{id}/read
- PUT    /notifications/{id}/read    alias (per the public spec)
- POST   /notifications/read-all
- PUT    /notifications/read-all     alias

Filtering on the paginated endpoint
-----------------------------------
- ``unread_only=true`` — only return is_read=false rows
- ``category=leave``  — coarse bucket: leave / attendance / timesheet / payroll /
                        onboarding / approvals / announcements / other. Maps to a
                        prefix match on Notification.type.
- ``type=...``        — exact type match (advanced)
- ``q=...``           — case-insensitive substring search across title + body
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Employee, Notification
from app.schemas.leave import NotificationOut, NotificationListOut
from app.services.notification_service import derive_action_url
from utils.time_utils import now_utc


router = APIRouter(prefix="/notifications", tags=["notifications"])


# Category → prefix(es) matched against Notification.type.
_CATEGORY_PREFIXES: dict[str, tuple[str, ...]] = {
    "leave":         ("leave_",),
    "attendance":    ("attendance_", "regularization_"),
    "timesheet":     ("timesheet_",),
    "payroll":       ("payroll_", "payslip_"),
    "onboarding":    ("onboarding_", "bgv_"),
    "approvals":     ("leave_pending_your_approval", "leave_cancel_pending_your_approval",
                      "sla_escalation", "hr_escalation"),
    "compoff":       ("compoff_",),
    "announcements": ("announcement",),
    "policies":      ("policy_",),
}


def _serialize(n: Notification) -> NotificationOut:
    """Fill action_url on the fly for legacy rows where the column is NULL."""
    data = NotificationOut.model_validate(n)
    if not data.action_url:
        data.action_url = derive_action_url(
            n.type, n.reference_table, n.reference_id, n.leave_request_id
        )
    return data


@router.get("", response_model=NotificationListOut)
def list_notifications(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    unread_only: bool = Query(False),
    category: Optional[str] = Query(None, description="leave|attendance|timesheet|payroll|onboarding|approvals|compoff|announcements|policies"),
    type: Optional[str] = Query(None, description="Exact Notification.type match"),
    q: Optional[str] = Query(None, description="Case-insensitive title/body search"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    base = db.query(Notification).filter(Notification.recipient_id == user.id)

    if unread_only:
        base = base.filter(Notification.is_read.is_(False))
    if type:
        base = base.filter(Notification.type == type)
    if category:
        prefixes = _CATEGORY_PREFIXES.get(category.lower())
        if prefixes:
            # Combine: type == prefix (for exact spec'd values) OR type LIKE prefix%
            clauses = []
            for p in prefixes:
                if p.endswith("_"):
                    clauses.append(Notification.type.like(p + "%"))
                else:
                    clauses.append(Notification.type == p)
            base = base.filter(or_(*clauses))
    if q:
        like = f"%{q.strip()}%"
        base = base.filter(or_(Notification.title.ilike(like), Notification.body.ilike(like)))

    total = base.count()
    unread = (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .count()
    )
    rows = (
        base.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NotificationListOut(
        items=[_serialize(n) for n in rows],
        total=total,
        unread=unread,
        limit=limit,
        offset=offset,
    )


@router.get("/recent", response_model=list[NotificationOut])
def recent_notifications(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=25),
):
    """Latest N notifications — used by the navbar dropdown.

    Kept deliberately small so the dropdown stays snappy regardless of the
    user's lifetime notification count.
    """
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(n) for n in rows]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    n = (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .count()
    )
    return {"count": n}


def _mark_read(db: Session, user: Employee, notification_id: int) -> NotificationOut:
    n = db.get(Notification, notification_id)
    if not n or n.recipient_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not n.is_read:
        n.is_read = True
        n.read_at = now_utc()
        db.commit()
        db.refresh(n)
    return _serialize(n)


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read_patch(notification_id: int, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    return _mark_read(db, user, notification_id)


@router.put("/{notification_id}/read", response_model=NotificationOut)
def mark_read_put(notification_id: int, db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    """Alias for PATCH — matches the public spec which mandates PUT."""
    return _mark_read(db, user, notification_id)


def _mark_all_read(db: Session, user: Employee) -> dict:
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .all()
    )
    now = now_utc()
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return {"updated": len(rows)}


@router.post("/read-all")
def mark_all_read_post(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    return _mark_all_read(db, user)


@router.put("/read-all")
def mark_all_read_put(db: Session = Depends(get_db), user: Employee = Depends(get_current_user)):
    return _mark_all_read(db, user)
