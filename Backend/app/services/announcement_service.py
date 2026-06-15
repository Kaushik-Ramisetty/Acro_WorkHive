"""Centralized announcement business logic.

All role checks, targeting queries, and read/ack tracking live here.
Routes are thin wrappers — they validate input, call these functions,
and serialise the result.

Datetime convention
-------------------
Every datetime written to the DB is **naive UTC**.  The Pydantic schema
validators (_naive_utc) strip tzinfo from any incoming timezone-aware
values before they reach this layer.  All comparisons in _visibility_filter
therefore operate in a single consistent naive-UTC space.

All datetime writes use ``utils.time_utils.now_utc()`` — naive UTC, compatible
with SQLite's naive-datetime storage and SQLAlchemy comparison semantics.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.announcement import Announcement, AnnouncementRead, AnnouncementTarget
from app.models.employee import Employee
from app.schemas.announcement import AnnouncementCreateIn, AnnouncementOut, AnnouncementUpdateIn
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _role(emp: Employee) -> str:
    """Return lowercase role name, defaulting to 'employee'."""
    return emp.role.name.lower() if emp.role else "employee"


def _is_admin_or_hr(emp: Employee) -> bool:
    return _role(emp) in ("admin", "hr")


def _is_manager(emp: Employee) -> bool:
    return _role(emp) == "manager"


# ---------------------------------------------------------------------------
# Targeting query — the single source of truth for visibility
# ---------------------------------------------------------------------------

def _visibility_filter(db: Session, employee: Employee):
    """SQLAlchemy filter clause: published announcements visible to *employee*.

    Factors in:
      • status = published
      • not yet expired (or no expiry)
      • publish_at has passed, or publish_at is NULL (immediate / unscheduled)
      • audience scope matches the employee's profile

    All datetime comparisons use naive UTC, consistent with how datetimes
    are stored in the DB (see module docstring).
    """
    now = now_utc()

    # Freshness gates
    freshness = and_(
        Announcement.status == "published",
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
        or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now),
    )

    # --- Scope-based audience filter ---
    # company: always visible
    company_visible = Announcement.target_scope == "company"

    # department: announcement_targets has a row for this employee's department
    dept_sub = (
        db.query(AnnouncementTarget.announcement_id)
        .filter(AnnouncementTarget.department_id == employee.department_id)
    )
    dept_visible = and_(
        Announcement.target_scope == "department",
        Announcement.id.in_(dept_sub),
    )

    # role: announcement_targets has a row for this employee's role
    role_sub = (
        db.query(AnnouncementTarget.announcement_id)
        .filter(AnnouncementTarget.role_id == employee.role_id)
    )
    role_visible = and_(
        Announcement.target_scope == "role",
        Announcement.id.in_(role_sub),
    )

    # individual: announcement_targets has a row for this specific employee
    ind_sub = (
        db.query(AnnouncementTarget.announcement_id)
        .filter(AnnouncementTarget.employee_id == employee.id)
    )
    ind_visible = and_(
        Announcement.target_scope == "individual",
        Announcement.id.in_(ind_sub),
    )

    audience_filter = or_(company_visible, dept_visible, role_visible, ind_visible)

    return and_(freshness, audience_filter)


# ---------------------------------------------------------------------------
# Read / acknowledgement helpers
# ---------------------------------------------------------------------------

def _get_or_create_read(db: Session, ann_id: int, employee_id: int) -> AnnouncementRead:
    row = (
        db.query(AnnouncementRead)
        .filter(
            AnnouncementRead.announcement_id == ann_id,
            AnnouncementRead.employee_id == employee_id,
        )
        .first()
    )
    if row is None:
        row = AnnouncementRead(announcement_id=ann_id, employee_id=employee_id)
        db.add(row)
        db.flush()
    return row


def _enrich(ann: Announcement, read_row: Optional[AnnouncementRead], include_counts: bool = False) -> dict:
    """Build a dict ready for AnnouncementOut from the ORM row + optional read row."""
    data: dict = {
        "id":                    ann.id,
        "title":                 ann.title,
        "content":               ann.content,
        "category":              ann.category,
        "priority":              ann.priority,
        "status":                ann.status,
        "created_by":            ann.created_by,
        "creator_name":          ann.creator.full_name if ann.creator else None,
        "created_at":            ann.created_at,
        "updated_at":            ann.updated_at,
        "publish_at":            ann.publish_at,
        "expires_at":            ann.expires_at,
        "is_pinned":             ann.is_pinned,
        "attachment_path":       ann.attachment_path,
        "allow_acknowledgement": ann.allow_acknowledgement,
        "target_scope":          ann.target_scope,
        "targets":               [
            {
                "id":            t.id,
                "employee_id":   t.employee_id,
                "department_id": t.department_id,
                "role_id":       t.role_id,
            }
            for t in ann.targets
        ],
        "is_read":               read_row.read_at is not None if read_row else False,
        "is_acknowledged":       read_row.acknowledged_at is not None if read_row else False,
    }
    if include_counts:
        data["read_count"] = sum(1 for r in ann.reads if r.read_at)
        data["acknowledgement_count"] = sum(1 for r in ann.reads if r.acknowledged_at)
    return data


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

def create_announcement(
    db: Session,
    creator: Employee,
    payload: AnnouncementCreateIn,
) -> Announcement:
    """Create a new announcement.

    RBAC:
      - admin/hr   : any scope, any category
      - manager    : department scope only, targeting their own department

    Publish logic
    -------------
    Managers always produce a draft (admin must promote it later).

    For admin/hr the three paths are:

    1. publish_immediately = True (the default)
       → status = "published", publish_at = NULL
       → immediately visible in all employee/manager feeds
       → any publish_at value in the payload is intentionally ignored

    2. publish_immediately = False AND payload.publish_at is a future UTC time
       → status = "published", publish_at = <future naive UTC>
       → visible in feeds only after that UTC instant passes
       → the _visibility_filter gates visibility via publish_at <= now

    3. publish_immediately = False AND no publish_at provided
       → status = "draft", publish_at = NULL
       → invisible to employees; admin must click "Publish" in the table
    """
    role = _role(creator)

    if role not in ("admin", "hr", "manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create announcements",
        )

    if role == "manager":
        if payload.target_scope != "department":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers can only create department-scoped announcements",
            )
        # Force the target to the manager's own department
        from app.schemas.announcement import AnnouncementTargetIn
        payload = payload.model_copy(update={
            "targets": [AnnouncementTargetIn(department_id=creator.department_id)]
        })
        # Managers always produce a draft regardless of publish_immediately
        initial_status    = "draft"
        initial_publish_at = None

    elif getattr(payload, "publish_immediately", True):
        # Immediate publish: ignore any schedule the form may have sent
        initial_status     = "published"
        initial_publish_at = None          # NULL → always visible

    elif payload.publish_at is not None:
        # Scheduled publish: already normalized to naive UTC by schema validator
        initial_status     = "published"   # gated by publish_at in _visibility_filter
        initial_publish_at = payload.publish_at

    else:
        # Explicit draft (publish_immediately=False, no schedule)
        initial_status     = "draft"
        initial_publish_at = None

    ann = Announcement(
        title=payload.title,
        content=payload.content,
        category=payload.category,
        priority=payload.priority,
        status=initial_status,
        created_by=creator.id,
        publish_at=initial_publish_at,
        expires_at=payload.expires_at,    # already naive UTC from schema validator
        is_pinned=payload.is_pinned,
        attachment_path=payload.attachment_path,
        allow_acknowledgement=payload.allow_acknowledgement,
        target_scope=payload.target_scope,
    )
    db.add(ann)
    db.flush()  # get ann.id

    _replace_targets(db, ann, payload.targets)

    db.commit()
    db.refresh(ann)
    logger.info(
        "Announcement created: id=%d status=%s by employee_id=%d",
        ann.id, ann.status, creator.id,
    )
    return ann


def update_announcement(
    db: Session,
    ann_id: int,
    actor: Employee,
    payload: AnnouncementUpdateIn,
) -> Announcement:
    """Update an existing announcement.

    RBAC:
      - admin/hr can edit any announcement
      - creator can edit their own drafts

    publish_at / expires_at are already normalized to naive UTC by the
    schema validator, so we can write them to the DB directly.
    """
    ann = _get_or_404(db, ann_id)

    if not _can_manage(actor, ann):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit this announcement",
        )

    if _role(actor) == "manager" and payload.target_scope and payload.target_scope != "department":
        raise HTTPException(status_code=403, detail="Managers can only use department scope")

    for field, value in payload.model_dump(exclude_none=True, exclude={"targets"}).items():
        # Datetime fields are already naive-UTC from the schema validator.
        setattr(ann, field, value)

    if payload.targets is not None:
        _replace_targets(db, ann, payload.targets)

    db.commit()
    db.refresh(ann)
    return ann


def publish_announcement(db: Session, ann_id: int, actor: Employee) -> Announcement:
    """Publish a draft or scheduled announcement immediately.  Admin/HR only.

    Clicking "Publish" in the admin table always makes the announcement
    immediately visible — we set publish_at = NULL so the
    _visibility_filter's NULL-branch fires (never blocked by a stale time).
    """
    if not _is_admin_or_hr(actor):
        raise HTTPException(status_code=403, detail="Only admin/hr can publish announcements")
    ann = _get_or_404(db, ann_id)
    if ann.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot publish an archived announcement")
    ann.status     = "published"
    ann.publish_at = None   # NULL → always visible; cleared regardless of prior schedule
    db.commit()
    db.refresh(ann)
    logger.info("Announcement published: id=%d by employee_id=%d", ann.id, actor.id)
    return ann


def archive_announcement(db: Session, ann_id: int, actor: Employee) -> Announcement:
    """Archive an announcement. Admin/HR only."""
    if not _is_admin_or_hr(actor):
        raise HTTPException(status_code=403, detail="Only admin/hr can archive announcements")
    ann = _get_or_404(db, ann_id)
    ann.status = "archived"
    db.commit()
    db.refresh(ann)
    return ann


def delete_announcement(db: Session, ann_id: int, actor: Employee) -> None:
    """Delete an announcement.

    Admin/HR can delete anything.
    Creators can delete their own drafts.
    """
    ann = _get_or_404(db, ann_id)
    if not _is_admin_or_hr(actor):
        if ann.created_by != actor.id or ann.status != "draft":
            raise HTTPException(status_code=403, detail="Cannot delete this announcement")
    db.delete(ann)
    db.commit()
    logger.info("Announcement deleted: id=%d by employee_id=%d", ann_id, actor.id)


# ---- Feed queries ----------------------------------------------------------

def list_for_employee(
    db: Session,
    employee: Employee,
    *,
    unread_only: bool = False,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[dict], int]:
    """Return paginated announcements visible to *employee*, enriched with read state."""
    q = db.query(Announcement).filter(_visibility_filter(db, employee))

    if category:
        q = q.filter(Announcement.category == category)
    if priority:
        q = q.filter(Announcement.priority == priority)
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(Announcement.title.ilike(like), Announcement.content.ilike(like))
        )

    # Pinned first, then newest
    q = q.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())

    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    # Bulk-load read rows for this employee
    ann_ids = [a.id for a in rows]
    read_map = {
        r.announcement_id: r
        for r in db.query(AnnouncementRead).filter(
            AnnouncementRead.announcement_id.in_(ann_ids),
            AnnouncementRead.employee_id == employee.id,
        ).all()
    } if ann_ids else {}

    result = []
    for ann in rows:
        read_row = read_map.get(ann.id)
        if unread_only and read_row and read_row.read_at:
            continue
        result.append(_enrich(ann, read_row))

    return result, total


def list_for_admin(
    db: Session,
    actor: Employee,
    *,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[dict], int]:
    """Return all announcements for admin/hr management view (all statuses)."""
    if not _is_admin_or_hr(actor):
        raise HTTPException(status_code=403, detail="Forbidden")

    q = db.query(Announcement)
    if status_filter:
        q = q.filter(Announcement.status == status_filter)
    if category:
        q = q.filter(Announcement.category == category)
    if priority:
        q = q.filter(Announcement.priority == priority)
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(Announcement.title.ilike(like), Announcement.content.ilike(like))
        )

    q = q.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return [_enrich(ann, None, include_counts=True) for ann in rows], total


def list_for_manager(
    db: Session,
    manager: Employee,
    *,
    unread_only: bool = False,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[dict], int]:
    """Return announcements visible to manager + department-scoped ones they created."""
    q = db.query(Announcement).filter(_visibility_filter(db, manager))
    if category:
        q = q.filter(Announcement.category == category)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Announcement.title.ilike(like), Announcement.content.ilike(like)))

    q = q.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    ann_ids = [a.id for a in rows]
    read_map = {
        r.announcement_id: r
        for r in db.query(AnnouncementRead).filter(
            AnnouncementRead.announcement_id.in_(ann_ids),
            AnnouncementRead.employee_id == manager.id,
        ).all()
    } if ann_ids else {}

    result = []
    for ann in rows:
        read_row = read_map.get(ann.id)
        if unread_only and read_row and read_row.read_at:
            continue
        d = _enrich(ann, read_row, include_counts=True)
        result.append(d)

    return result, total


def get_single(db: Session, ann_id: int, viewer: Employee) -> dict:
    """Fetch a single announcement with viewer-specific read state."""
    ann = _get_or_404(db, ann_id)

    # Non-admin employees can only view published + not-expired that target them
    if not _is_admin_or_hr(viewer):
        f = _visibility_filter(db, viewer)
        ok = db.query(Announcement).filter(Announcement.id == ann_id, f).first()
        if not ok:
            raise HTTPException(status_code=404, detail="Announcement not found")

    read_row = (
        db.query(AnnouncementRead)
        .filter(
            AnnouncementRead.announcement_id == ann_id,
            AnnouncementRead.employee_id == viewer.id,
        )
        .first()
    )
    return _enrich(ann, read_row, include_counts=_is_admin_or_hr(viewer))


def mark_read(db: Session, ann_id: int, employee: Employee) -> AnnouncementRead:
    _get_or_404(db, ann_id)
    row = _get_or_create_read(db, ann_id, employee.id)
    if row.read_at is None:
        row.read_at = now_utc()
    db.commit()
    db.refresh(row)
    return row


def acknowledge(db: Session, ann_id: int, employee: Employee) -> AnnouncementRead:
    ann = _get_or_404(db, ann_id)
    if not ann.allow_acknowledgement:
        raise HTTPException(status_code=400, detail="This announcement does not require acknowledgement")
    row = _get_or_create_read(db, ann_id, employee.id)
    if row.read_at is None:
        row.read_at = now_utc()
    if row.acknowledged_at is None:
        row.acknowledged_at = now_utc()
    db.commit()
    db.refresh(row)
    return row


def get_analytics(db: Session, ann_id: int, actor: Employee) -> dict:
    """Return read/ack counts. Admin/HR only."""
    if not _is_admin_or_hr(actor) and not _is_manager(actor):
        raise HTTPException(status_code=403, detail="Forbidden")
    ann = _get_or_404(db, ann_id)

    reads = db.query(AnnouncementRead).filter(AnnouncementRead.announcement_id == ann_id).all()
    read_count = sum(1 for r in reads if r.read_at)
    ack_count  = sum(1 for r in reads if r.acknowledged_at)

    # Total targeted employees (approximate for company-wide)
    from app.models.employee import Employee as Emp
    if ann.target_scope == "company":
        total = db.query(Emp).filter(
            Emp.is_deleted.is_(False), Emp.employment_status == "active"
        ).count()
    elif ann.target_scope == "department":
        dept_ids = {t.department_id for t in ann.targets if t.department_id}
        total = db.query(Emp).filter(
            Emp.is_deleted.is_(False),
            Emp.employment_status == "active",
            Emp.department_id.in_(dept_ids),
        ).count()
    elif ann.target_scope == "role":
        role_ids = {t.role_id for t in ann.targets if t.role_id}
        total = db.query(Emp).filter(
            Emp.is_deleted.is_(False),
            Emp.employment_status == "active",
            Emp.role_id.in_(role_ids),
        ).count()
    else:
        total = len({t.employee_id for t in ann.targets if t.employee_id})

    return {
        "announcement_id":       ann.id,
        "title":                 ann.title,
        "total_targeted":        total,
        "read_count":            read_count,
        "acknowledgement_count": ack_count,
    }


def unread_count_for(db: Session, employee: Employee) -> int:
    """Count published, visible, unread announcements for the employee."""
    visible_ids = [
        row.id
        for row in db.query(Announcement.id).filter(_visibility_filter(db, employee)).all()
    ]
    if not visible_ids:
        return 0

    read_ids = {
        r.announcement_id
        for r in db.query(AnnouncementRead.announcement_id).filter(
            AnnouncementRead.employee_id == employee.id,
            AnnouncementRead.read_at.is_not(None),
            AnnouncementRead.announcement_id.in_(visible_ids),
        ).all()
    }
    return len(set(visible_ids) - read_ids)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, ann_id: int) -> Announcement:
    ann = db.get(Announcement, ann_id)
    if not ann:
        raise HTTPException(status_code=404, detail=f"Announcement {ann_id} not found")
    return ann


def _can_manage(actor: Employee, ann: Announcement) -> bool:
    """True if actor may edit/delete this announcement."""
    if _is_admin_or_hr(actor):
        return True
    # Creator can edit their own drafts
    if ann.created_by == actor.id and ann.status == "draft":
        return True
    return False


def _replace_targets(db: Session, ann: Announcement, targets) -> None:
    """Wipe existing targets and insert fresh ones."""
    db.query(AnnouncementTarget).filter(
        AnnouncementTarget.announcement_id == ann.id
    ).delete(synchronize_session=False)

    for t in targets:
        db.add(AnnouncementTarget(
            announcement_id=ann.id,
            employee_id=t.employee_id,
            department_id=t.department_id,
            role_id=t.role_id,
        ))
