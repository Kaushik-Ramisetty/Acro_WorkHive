"""Policies API routes.

Routes intentionally stay thin: auth → service call → serialise. All business
logic lives in `app.services.policy_service`.

Endpoints
---------
GET    /policies                        List policies (role-aware: admin sees all, others see published).
GET    /policies/{id}                   Get a single policy (with current-version snapshot).
POST   /policies                        Create policy + initial v1 (admin/HR).
PATCH  /policies/{id}                   Update metadata (title/description/category) (admin/HR).
POST   /policies/{id}/publish           Publish the latest version (admin/HR).
POST   /policies/{id}/archive           Archive the policy (admin/HR).
POST   /policies/{id}/reactivate        Move archived → draft (admin/HR).
DELETE /policies/{id}                   Soft-delete a draft policy (admin/HR).

GET    /policies/{id}/versions          List versions (admin/HR: all, viewer: current only).
POST   /policies/{id}/versions          Create a new version (admin/HR).
POST   /policies/{id}/versions/{v}/publish
                                        Promote a specific version to "current" (admin/HR).

POST   /policies/{id}/versions/{v}/upload
                                        Upload a PDF for a version, multipart/form-data (admin/HR).
POST   /policies/{id}/upload            Convenience: upload PDF for the current/latest version (admin/HR).

GET    /policies/categories             List categories (any authenticated user).
POST   /policies/categories             Add a category (admin/HR).

POST   /policies/{id}/acknowledge       Acknowledge the policy's current version (any user).
GET    /policies/{id}/acknowledgements  Audit list (admin/HR).

GET    /policies/{id}/analytics         Read/ack counts (admin/HR).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, UploadFile, status,
)
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.employee import Employee
from app.schemas.policy import (
    PolicyAcknowledgementOut,
    PolicyAnalyticsOut,
    PolicyCategoryIn,
    PolicyCategoryOut,
    PolicyCreateIn,
    PolicyOut,
    PolicyUpdateIn,
    PolicyVersionCreateIn,
    PolicyVersionOut,
)
from app.services import policy_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/policies", tags=["policies"])


# ---------------------------------------------------------------------------
# File-upload helpers (local to this module — small enough not to need its
# own service file, but kept here so the upload path is auditable in one place)
# ---------------------------------------------------------------------------

_ALLOWED_EXTS = {".pdf"}
_MAX_PDF_MB = int(os.getenv("MAX_POLICY_PDF_SIZE_MB", "20"))
_UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Strip path components and unsafe chars from a filename."""
    base = Path(name or "policy.pdf").name  # drops any directory parts
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "policy.pdf"
    return cleaned


def _save_policy_pdf(upload: UploadFile, policy_id: int, version_id: int) -> str:
    """Persist an uploaded PDF and return its public URL path.

    Stores at `<UPLOAD_DIR>/policies/<policy_id>/v<version>_<safe_name>` and
    returns `/uploads/policies/<policy_id>/v<version>_<safe_name>` (served as
    static files by main.py).
    """
    if upload is None or upload.filename is None:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    ext = Path(upload.filename).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Only PDF is allowed.",
        )

    content = upload.file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_PDF_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_PDF_MB} MB limit.",
        )

    target_dir = _UPLOAD_DIR / "policies" / str(policy_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(upload.filename)
    fname = f"v{version_id}_{safe_name}"
    dest = target_dir / fname

    # Path traversal guard: resolve target and ensure it sits under target_dir.
    try:
        resolved = dest.resolve()
        if not str(resolved).startswith(str(target_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid file path.")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path.")

    dest.write_bytes(content)
    url_path = f"/uploads/policies/{policy_id}/{fname}"
    logger.info("Saved policy PDF: %s (%.1f KB)", url_path, len(content) / 1024)
    return url_path


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=List[PolicyCategoryOut], summary="List categories")
def list_categories(
    db: Session = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    return svc.list_categories(db)


@router.post(
    "/categories",
    response_model=PolicyCategoryOut,
    status_code=201,
    summary="Create a category (admin/HR)",
)
def create_category(
    payload: PolicyCategoryIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.create_category(db, user, payload)


# ---------------------------------------------------------------------------
# Listing & detail
# ---------------------------------------------------------------------------

@router.get("", summary="List policies (role-aware)")
def list_policies(
    mode:         str           = Query("feed", description="'feed' for viewer list, 'manage' for admin/HR table"),
    status_filter: Optional[str] = Query(None, alias="status", description="admin mode only"),
    category_id:  Optional[int] = Query(None),
    search:       Optional[str] = Query(None),
    limit:        int           = Query(50, ge=1, le=200),
    offset:       int           = Query(0,  ge=0),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = user.role.name.lower() if user.role else "employee"
    if mode == "manage" and role in ("admin", "hr"):
        items, total = svc.list_for_admin(
            db, user,
            status_filter=status_filter,
            category_id=category_id,
            search=search,
            limit=limit,
            offset=offset,
        )
    else:
        items, total = svc.list_for_viewer(
            db, user,
            category_id=category_id,
            search=search,
            limit=limit,
            offset=offset,
        )
    return {"total": total, "items": items}


@router.get("/{policy_id}", response_model=PolicyOut, summary="Get a single policy")
def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.get_single(db, policy_id, user)


# ---------------------------------------------------------------------------
# Create / update / lifecycle
# ---------------------------------------------------------------------------

@router.post("", response_model=PolicyOut, status_code=201, summary="Create policy + v1")
def create_policy(
    payload: PolicyCreateIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.create_policy(db, user, payload)
    return svc.get_single(db, p.id, user)


@router.patch("/{policy_id}", response_model=PolicyOut, summary="Update metadata")
def update_policy(
    policy_id: int,
    payload: PolicyUpdateIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.update_policy(db, policy_id, user, payload)
    return svc.get_single(db, p.id, user)


@router.post("/{policy_id}/publish", response_model=PolicyOut, summary="Publish latest version")
def publish_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.publish_policy(db, policy_id, user)
    return svc.get_single(db, p.id, user)


@router.post("/{policy_id}/archive", response_model=PolicyOut, summary="Archive policy")
def archive_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.archive_policy(db, policy_id, user)
    return svc.get_single(db, p.id, user)


@router.post("/{policy_id}/reactivate", response_model=PolicyOut, summary="Reactivate archived → draft")
def reactivate_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.reactivate_policy(db, policy_id, user)
    return svc.get_single(db, p.id, user)


@router.delete("/{policy_id}", status_code=204, summary="Soft-delete a draft policy")
def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    svc.delete_policy(db, policy_id, user)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

@router.get(
    "/{policy_id}/versions",
    response_model=List[PolicyVersionOut],
    summary="List versions",
)
def list_versions(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.list_versions(db, policy_id, user)


@router.post(
    "/{policy_id}/versions",
    response_model=PolicyVersionOut,
    status_code=201,
    summary="Create a new version",
)
def create_version(
    policy_id: int,
    payload: PolicyVersionCreateIn,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    v = svc.create_version(db, policy_id, user, payload)
    return v


@router.post(
    "/{policy_id}/versions/{version_id}/publish",
    response_model=PolicyOut,
    summary="Promote a specific version to current/published",
)
def publish_version(
    policy_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    p = svc.publish_version(db, policy_id, version_id, user)
    return svc.get_single(db, p.id, user)


# ---------------------------------------------------------------------------
# PDF upload
# ---------------------------------------------------------------------------

@router.post(
    "/{policy_id}/versions/{version_id}/upload",
    response_model=PolicyVersionOut,
    summary="Upload PDF for a specific version (admin/HR)",
)
def upload_version_pdf(
    policy_id: int,
    version_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    # Role check happens inside service.attach_pdf_to_version; doing it here
    # too lets us reject up front BEFORE reading the upload bytes.
    if not svc._is_admin_or_hr(user):
        raise HTTPException(status_code=403, detail="Only admin or HR may upload policy PDFs.")
    pdf_url = _save_policy_pdf(file, policy_id, version_id)
    v = svc.attach_pdf_to_version(db, policy_id, version_id, pdf_url, user)
    return v


@router.post(
    "/{policy_id}/upload",
    response_model=PolicyVersionOut,
    summary="Upload PDF for the policy's latest version (convenience)",
)
def upload_latest_pdf(
    policy_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if not svc._is_admin_or_hr(user):
        raise HTTPException(status_code=403, detail="Only admin or HR may upload policy PDFs.")
    # Find latest version; create v1 if the policy has none yet.
    from app.models.policy import PolicyVersion
    latest = (
        db.query(PolicyVersion)
        .filter(PolicyVersion.policy_id == policy_id)
        .order_by(PolicyVersion.version_number.desc())
        .first()
    )
    if latest is None:
        latest = svc.create_version(
            db, policy_id, user,
            PolicyVersionCreateIn(change_summary="Initial PDF upload"),
        )
    pdf_url = _save_policy_pdf(file, policy_id, latest.id)
    v = svc.attach_pdf_to_version(db, policy_id, latest.id, pdf_url, user)
    return v


# ---------------------------------------------------------------------------
# Acknowledgements
# ---------------------------------------------------------------------------

@router.post(
    "/{policy_id}/acknowledge",
    response_model=PolicyAcknowledgementOut,
    summary="Acknowledge the current published version",
)
def acknowledge_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.acknowledge_current(db, policy_id, user)


@router.get(
    "/{policy_id}/acknowledgements",
    response_model=List[PolicyAcknowledgementOut],
    summary="List acknowledgements (admin/HR)",
)
def list_acknowledgements(
    policy_id: int,
    version_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.list_acknowledgements(db, policy_id, user, version_id=version_id)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get(
    "/{policy_id}/analytics",
    response_model=PolicyAnalyticsOut,
    summary="Policy analytics (admin/HR)",
)
def policy_analytics(
    policy_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return svc.get_analytics(db, policy_id, user)
