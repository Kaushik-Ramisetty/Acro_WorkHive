"""Policies module — business logic.

All role checks, version transitions, acknowledgement bookkeeping, and
query construction live here. Routes are thin wrappers (auth → call →
serialise).

The module is logically split into three sections that map to the
"PolicyService / PolicyVersionService / PolicyAcknowledgementService"
naming asked for in the spec — kept in one file to mirror the
announcement_service.py pattern used everywhere else in this codebase.

All datetimes follow the project's naive-UTC convention; we use
`utils.time_utils.now_utc()` everywhere.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, func as sa_func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee
from app.models.policy import (
    Policy,
    PolicyAcknowledgement,
    PolicyCategory,
    PolicyVersion,
)
from app.schemas.policy import (
    PolicyAnalyticsOut,
    PolicyCategoryIn,
    PolicyCategoryOut,
    PolicyCreateIn,
    PolicyOut,
    PolicyUpdateIn,
    PolicyVersionCreateIn,
    PolicyVersionOut,
    VALID_STATUSES,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)


# ===========================================================================
# Role helpers
# ===========================================================================

def _role(emp: Employee) -> str:
    """Lowercase role name; defaults to 'employee' if no role is set."""
    return emp.role.name.lower() if emp.role else "employee"


def _is_admin_or_hr(emp: Employee) -> bool:
    return _role(emp) in ("admin", "hr")


def _require_admin_or_hr(emp: Employee) -> None:
    if not _is_admin_or_hr(emp):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or HR users can perform this action.",
        )


# ===========================================================================
# Slug helpers
# ===========================================================================

_slug_pattern = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Produce a URL-safe slug. Empty input falls back to 'policy'."""
    s = _slug_pattern.sub("-", (text or "").lower()).strip("-")
    return s or "policy"


def _unique_slug(db: Session, base: str, exclude_id: Optional[int] = None) -> str:
    """Return a slug guaranteed to be unique in the policies table."""
    base = _slugify(base)
    candidate = base
    n = 1
    while True:
        q = db.query(Policy.id).filter(Policy.slug == candidate)
        if exclude_id is not None:
            q = q.filter(Policy.id != exclude_id)
        if not db.query(q.exists()).scalar():
            return candidate
        n += 1
        candidate = f"{base}-{n}"


# ===========================================================================
# Output serialisation
# ===========================================================================

def _employee_display_name(emp: Optional[Employee]) -> Optional[str]:
    if emp is None:
        return None
    return (
        getattr(emp, "full_name", None)
        or " ".join(filter(None, [getattr(emp, "first_name", None), getattr(emp, "last_name", None)])).strip()
        or getattr(emp, "email", None)
    )


def _serialise_policy(
    policy: Policy,
    *,
    current_version: Optional[PolicyVersion],
    category_name: Optional[str],
    creator_name: Optional[str],
    is_acknowledged: Optional[bool] = None,
    versions_count: Optional[int] = None,
    acknowledgement_count: Optional[int] = None,
) -> PolicyOut:
    cv = current_version
    return PolicyOut(
        id=policy.id,
        title=policy.title,
        slug=policy.slug,
        description=policy.description,
        category_id=policy.category_id,
        category_name=category_name,
        status=policy.status,
        created_by=policy.created_by,
        creator_name=creator_name,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        archived_at=policy.archived_at,
        current_version_id=cv.id if cv else None,
        current_version_number=cv.version_number if cv else None,
        current_pdf_path=cv.pdf_path if cv else None,
        current_effective_date=cv.effective_date if cv else None,
        current_expiry_date=cv.expiry_date if cv else None,
        current_change_summary=cv.change_summary if cv else None,
        current_version_created_at=cv.created_at if cv else None,
        is_acknowledged=is_acknowledged,
        versions_count=versions_count,
        acknowledgement_count=acknowledgement_count,
    )


def _serialise_version(v: PolicyVersion) -> PolicyVersionOut:
    return PolicyVersionOut.model_validate(v)


# ---------------------------------------------------------------------------
# Loading helpers (kept narrow to avoid N+1)
# ---------------------------------------------------------------------------

def _load_policy(db: Session, policy_id: int, *, include_deleted: bool = False) -> Policy:
    q = db.query(Policy).options(joinedload(Policy.category), joinedload(Policy.creator))
    if not include_deleted:
        q = q.filter(Policy.is_deleted.is_(False))
    p = q.filter(Policy.id == policy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return p


def _current_version(db: Session, policy: Policy) -> Optional[PolicyVersion]:
    if policy.current_version_id is None:
        return None
    return db.get(PolicyVersion, policy.current_version_id)


def _ack_map_for_employee(
    db: Session, employee_id: int, version_ids: List[int]
) -> set[int]:
    """Return the set of version_ids the employee has acknowledged."""
    if not version_ids:
        return set()
    rows = (
        db.query(PolicyAcknowledgement.policy_version_id)
        .filter(
            PolicyAcknowledgement.employee_id == employee_id,
            PolicyAcknowledgement.policy_version_id.in_(version_ids),
        )
        .all()
    )
    return {r[0] for r in rows}


# ===========================================================================
# PolicyService — categories
# ===========================================================================

def list_categories(db: Session) -> List[PolicyCategoryOut]:
    rows = db.query(PolicyCategory).order_by(PolicyCategory.name.asc()).all()
    return [PolicyCategoryOut.model_validate(r) for r in rows]


def create_category(db: Session, user: Employee, payload: PolicyCategoryIn) -> PolicyCategoryOut:
    _require_admin_or_hr(user)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required.")
    existing = db.query(PolicyCategory).filter(sa_func.lower(PolicyCategory.name) == name.lower()).first()
    if existing:
        return PolicyCategoryOut.model_validate(existing)
    cat = PolicyCategory(name=name, description=(payload.description or None))
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return PolicyCategoryOut.model_validate(cat)


# ===========================================================================
# PolicyService — list / read
# ===========================================================================

def _apply_search_and_category(
    q,
    *,
    search: Optional[str],
    category_id: Optional[int],
):
    if category_id is not None:
        q = q.filter(Policy.category_id == category_id)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            or_(
                sa_func.lower(Policy.title).like(like),
                sa_func.lower(Policy.description).like(like),
                sa_func.lower(Policy.slug).like(like),
            )
        )
    return q


def list_for_admin(
    db: Session,
    user: Employee,
    *,
    status_filter: Optional[str] = None,
    category_id:   Optional[int] = None,
    search:        Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[PolicyOut], int]:
    """All policies, admin-style — includes drafts and archived."""
    _require_admin_or_hr(user)

    q = (
        db.query(Policy)
        .options(joinedload(Policy.category), joinedload(Policy.creator))
        .filter(Policy.is_deleted.is_(False))
    )
    q = _apply_search_and_category(q, search=search, category_id=category_id)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
        q = q.filter(Policy.status == status_filter)

    total = q.with_entities(sa_func.count(Policy.id)).scalar() or 0
    rows: List[Policy] = (
        q.order_by(Policy.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Preload current versions + counts in batch to avoid N+1.
    current_ids = [p.current_version_id for p in rows if p.current_version_id]
    versions_by_id: dict[int, PolicyVersion] = {}
    if current_ids:
        for v in db.query(PolicyVersion).filter(PolicyVersion.id.in_(current_ids)).all():
            versions_by_id[v.id] = v

    policy_ids = [p.id for p in rows]
    versions_counts: dict[int, int] = {}
    ack_counts: dict[int, int] = {}
    if policy_ids:
        for pid, cnt in (
            db.query(PolicyVersion.policy_id, sa_func.count(PolicyVersion.id))
            .filter(PolicyVersion.policy_id.in_(policy_ids))
            .group_by(PolicyVersion.policy_id)
            .all()
        ):
            versions_counts[pid] = cnt
        # Ack count is the sum across all versions of a policy.
        for pid, cnt in (
            db.query(PolicyVersion.policy_id, sa_func.count(PolicyAcknowledgement.id))
            .join(PolicyAcknowledgement, PolicyAcknowledgement.policy_version_id == PolicyVersion.id)
            .filter(PolicyVersion.policy_id.in_(policy_ids))
            .group_by(PolicyVersion.policy_id)
            .all()
        ):
            ack_counts[pid] = cnt

    items = [
        _serialise_policy(
            p,
            current_version=versions_by_id.get(p.current_version_id) if p.current_version_id else None,
            category_name=p.category.name if p.category else None,
            creator_name=_employee_display_name(p.creator),
            versions_count=versions_counts.get(p.id, 0),
            acknowledgement_count=ack_counts.get(p.id, 0),
        )
        for p in rows
    ]
    return items, total


def list_for_viewer(
    db: Session,
    user: Employee,
    *,
    category_id: Optional[int] = None,
    search:      Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[PolicyOut], int]:
    """Employee / Manager read-only feed. Returns ONLY published policies that
    have a current_version_id set."""
    q = (
        db.query(Policy)
        .options(joinedload(Policy.category), joinedload(Policy.creator))
        .filter(
            Policy.is_deleted.is_(False),
            Policy.status == "published",
            Policy.current_version_id.is_not(None),
        )
    )
    q = _apply_search_and_category(q, search=search, category_id=category_id)

    total = q.with_entities(sa_func.count(Policy.id)).scalar() or 0
    rows: List[Policy] = (
        q.order_by(Policy.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    current_ids = [p.current_version_id for p in rows if p.current_version_id]
    versions_by_id: dict[int, PolicyVersion] = {}
    if current_ids:
        for v in db.query(PolicyVersion).filter(PolicyVersion.id.in_(current_ids)).all():
            versions_by_id[v.id] = v

    acked = _ack_map_for_employee(db, user.id, current_ids)

    items = [
        _serialise_policy(
            p,
            current_version=versions_by_id.get(p.current_version_id) if p.current_version_id else None,
            category_name=p.category.name if p.category else None,
            creator_name=_employee_display_name(p.creator),
            is_acknowledged=(p.current_version_id in acked) if p.current_version_id else False,
        )
        for p in rows
    ]
    return items, total


def get_single(db: Session, policy_id: int, user: Employee) -> PolicyOut:
    p = _load_policy(db, policy_id)
    if not _is_admin_or_hr(user):
        # Non-admins only see published policies.
        if p.status != "published" or p.current_version_id is None:
            raise HTTPException(status_code=404, detail="Policy not found.")
    cv = _current_version(db, p)
    is_acked = None
    if cv is not None:
        is_acked = bool(
            db.query(PolicyAcknowledgement.id)
            .filter(
                PolicyAcknowledgement.policy_version_id == cv.id,
                PolicyAcknowledgement.employee_id == user.id,
            )
            .first()
        )
    versions_count = (
        db.query(sa_func.count(PolicyVersion.id))
        .filter(PolicyVersion.policy_id == p.id)
        .scalar()
        or 0
    )
    ack_count = (
        db.query(sa_func.count(PolicyAcknowledgement.id))
        .join(PolicyVersion, PolicyVersion.id == PolicyAcknowledgement.policy_version_id)
        .filter(PolicyVersion.policy_id == p.id)
        .scalar()
        or 0
    )
    return _serialise_policy(
        p,
        current_version=cv,
        category_name=p.category.name if p.category else None,
        creator_name=_employee_display_name(p.creator),
        is_acknowledged=is_acked,
        versions_count=versions_count,
        acknowledgement_count=ack_count,
    )


# ===========================================================================
# PolicyService — create / update / archive / delete
# ===========================================================================

def create_policy(db: Session, user: Employee, payload: PolicyCreateIn) -> Policy:
    """Create a new policy container plus its initial v1.

    If `publish_immediately` is True (the default), the new version is
    published and the policy status becomes 'published'.
    """
    _require_admin_or_hr(user)

    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    # Validate category if provided.
    if payload.category_id is not None:
        if not db.get(PolicyCategory, payload.category_id):
            raise HTTPException(status_code=400, detail="Unknown category_id.")

    slug = _unique_slug(db, title)
    policy = Policy(
        title=title,
        slug=slug,
        description=(payload.description or None),
        category_id=payload.category_id,
        status="draft",
        created_by=user.id,
    )
    db.add(policy)
    db.flush()  # need policy.id for the version

    v = PolicyVersion(
        policy_id=policy.id,
        version_number=1,
        content=payload.content or None,
        pdf_path=payload.pdf_path or None,
        change_summary=payload.change_summary or "Initial version",
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        is_published=False,
        created_by=user.id,
    )
    db.add(v)
    db.flush()

    if payload.publish_immediately:
        v.is_published = True
        policy.current_version_id = v.id
        policy.status = "published"
        policy.updated_at = now_utc()

    db.commit()
    db.refresh(policy)
    logger.info("Created policy id=%s title=%s (status=%s)", policy.id, policy.title, policy.status)
    return policy


def update_policy(db: Session, policy_id: int, user: Employee, payload: PolicyUpdateIn) -> Policy:
    """Metadata-only update: title / description / category. Does NOT spawn a
    new version (use create_version for that)."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot edit an archived policy.")

    if payload.title is not None:
        new_title = payload.title.strip()
        if not new_title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        if new_title != p.title:
            p.title = new_title
            p.slug = _unique_slug(db, new_title, exclude_id=p.id)
    if payload.description is not None:
        p.description = payload.description or None
    if payload.category_id is not None:
        if not db.get(PolicyCategory, payload.category_id):
            raise HTTPException(status_code=400, detail="Unknown category_id.")
        p.category_id = payload.category_id

    p.updated_at = now_utc()
    db.commit()
    db.refresh(p)
    return p


def publish_policy(db: Session, policy_id: int, user: Employee) -> Policy:
    """Set policy.status = 'published' using the latest version as current.

    If the policy was already published this is a no-op. If there is no
    version yet, returns 400.
    """
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot publish an archived policy. Reactivate first.")

    latest = (
        db.query(PolicyVersion)
        .filter(PolicyVersion.policy_id == p.id)
        .order_by(PolicyVersion.version_number.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(status_code=400, detail="Cannot publish a policy with no versions.")

    latest.is_published = True
    p.current_version_id = latest.id
    p.status = "published"
    p.updated_at = now_utc()
    db.commit()
    db.refresh(p)
    return p


def archive_policy(db: Session, policy_id: int, user: Employee) -> Policy:
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status == "archived":
        return p
    p.status = "archived"
    p.archived_at = now_utc()
    p.updated_at = now_utc()
    db.commit()
    db.refresh(p)
    return p


def reactivate_policy(db: Session, policy_id: int, user: Employee) -> Policy:
    """Inverse of archive — move back to draft so admin can edit / republish."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status != "archived":
        return p
    p.status = "draft"
    p.archived_at = None
    p.updated_at = now_utc()
    db.commit()
    db.refresh(p)
    return p


def delete_policy(db: Session, policy_id: int, user: Employee) -> None:
    """Soft-delete a *draft* policy only. Published / archived policies must be
    archived first; we never allow hard deletes (audit safety)."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft policies may be deleted. Archive published ones instead.",
        )
    p.is_deleted = True
    p.updated_at = now_utc()
    db.commit()


# ===========================================================================
# PolicyVersionService — version creation / listing / publishing
# ===========================================================================

def list_versions(db: Session, policy_id: int, user: Employee) -> List[PolicyVersionOut]:
    """Admin/HR see all versions. Non-admins get only the currently-published
    version (returned as a single-item list) — so the same endpoint can serve
    the read-only "What changed?" preview if we ever add one."""
    p = _load_policy(db, policy_id)
    if not _is_admin_or_hr(user):
        if p.status != "published" or p.current_version_id is None:
            raise HTTPException(status_code=404, detail="Policy not found.")
        cv = _current_version(db, p)
        return [_serialise_version(cv)] if cv else []
    rows = (
        db.query(PolicyVersion)
        .filter(PolicyVersion.policy_id == policy_id)
        .order_by(PolicyVersion.version_number.desc())
        .all()
    )
    return [_serialise_version(v) for v in rows]


def _next_version_number(db: Session, policy_id: int) -> int:
    latest = (
        db.query(sa_func.max(PolicyVersion.version_number))
        .filter(PolicyVersion.policy_id == policy_id)
        .scalar()
    )
    return int(latest or 0) + 1


def create_version(
    db: Session,
    policy_id: int,
    user: Employee,
    payload: PolicyVersionCreateIn,
) -> PolicyVersion:
    """Create a brand new version row (never overwrite an existing one)."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot version an archived policy.")

    v = PolicyVersion(
        policy_id=p.id,
        version_number=_next_version_number(db, p.id),
        content=payload.content or None,
        pdf_path=payload.pdf_path or None,
        change_summary=payload.change_summary or None,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        is_published=False,
        created_by=user.id,
    )
    db.add(v)
    db.flush()

    if payload.publish:
        v.is_published = True
        p.current_version_id = v.id
        p.status = "published"

    p.updated_at = now_utc()
    db.commit()
    db.refresh(v)
    logger.info("Policy %s: created v%s (published=%s)", p.id, v.version_number, payload.publish)
    return v


def publish_version(db: Session, policy_id: int, version_id: int, user: Employee) -> Policy:
    """Promote a specific version to "current" and mark the policy published."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    v = db.get(PolicyVersion, version_id)
    if not v or v.policy_id != p.id:
        raise HTTPException(status_code=404, detail="Version not found for this policy.")
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot publish a version on an archived policy.")

    v.is_published = True
    p.current_version_id = v.id
    p.status = "published"
    p.updated_at = now_utc()
    db.commit()
    db.refresh(p)
    return p


def attach_pdf_to_version(
    db: Session,
    policy_id: int,
    version_id: int,
    pdf_path: str,
    user: Employee,
) -> PolicyVersion:
    """Update a version's pdf_path (called after a successful file upload)."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    v = db.get(PolicyVersion, version_id)
    if not v or v.policy_id != p.id:
        raise HTTPException(status_code=404, detail="Version not found for this policy.")
    v.pdf_path = pdf_path
    p.updated_at = now_utc()
    db.commit()
    db.refresh(v)
    return v


# ===========================================================================
# PolicyAcknowledgementService
# ===========================================================================

def acknowledge_current(db: Session, policy_id: int, user: Employee) -> PolicyAcknowledgement:
    """Record acknowledgement of a policy's *current* version.

    Idempotent: re-acknowledging returns the existing row.
    """
    p = _load_policy(db, policy_id)
    if p.status != "published" or p.current_version_id is None:
        raise HTTPException(status_code=400, detail="Policy is not currently published.")
    cv = _current_version(db, p)
    if cv is None:
        raise HTTPException(status_code=400, detail="Policy has no current version.")

    existing = (
        db.query(PolicyAcknowledgement)
        .filter(
            PolicyAcknowledgement.policy_version_id == cv.id,
            PolicyAcknowledgement.employee_id == user.id,
        )
        .first()
    )
    if existing:
        return existing
    row = PolicyAcknowledgement(
        policy_version_id=cv.id,
        employee_id=user.id,
        acknowledged_at=now_utc(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_acknowledgements(
    db: Session, policy_id: int, user: Employee, *, version_id: Optional[int] = None
) -> List[PolicyAcknowledgement]:
    """Admin/HR: list ACK rows for a policy (optionally scoped to one version)."""
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    q = (
        db.query(PolicyAcknowledgement)
        .join(PolicyVersion, PolicyVersion.id == PolicyAcknowledgement.policy_version_id)
        .filter(PolicyVersion.policy_id == p.id)
        .order_by(PolicyAcknowledgement.acknowledged_at.desc())
    )
    if version_id is not None:
        q = q.filter(PolicyAcknowledgement.policy_version_id == version_id)
    return q.all()


# ===========================================================================
# Analytics
# ===========================================================================

def get_analytics(db: Session, policy_id: int, user: Employee) -> PolicyAnalyticsOut:
    _require_admin_or_hr(user)
    p = _load_policy(db, policy_id)
    vcount = (
        db.query(sa_func.count(PolicyVersion.id))
        .filter(PolicyVersion.policy_id == p.id)
        .scalar()
        or 0
    )
    acount = (
        db.query(sa_func.count(PolicyAcknowledgement.id))
        .join(PolicyVersion, PolicyVersion.id == PolicyAcknowledgement.policy_version_id)
        .filter(PolicyVersion.policy_id == p.id)
        .scalar()
        or 0
    )
    return PolicyAnalyticsOut(
        policy_id=p.id,
        title=p.title,
        versions_count=vcount,
        acknowledgement_count=acount,
        current_version_id=p.current_version_id,
    )
