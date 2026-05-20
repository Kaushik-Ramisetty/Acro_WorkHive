"""Celery task: scan a SecureUpload row asynchronously.

Triggered by ``secure_upload_service.dispatch_scan(upload_id)`` after the
file has been written to the temp dir. Retries on transient ClamAV /
network errors (max 3 attempts, exponential backoff). On final failure
the row stays in ``scan_failed`` and the file is held in quarantine —
an admin can re-trigger via the admin UI.
"""
from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(
    name="secure_upload.scan_file",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def scan_secure_upload(self, upload_id: int) -> dict:
    """Scan a SecureUpload by id.

    Returns a small status dict so admin tools can poll Celery results.
    Any unexpected exception triggers Celery's autoretry; the final failure
    after ``max_retries`` is captured by ``scan_and_finalize`` (the row
    flips to ``scan_failed``) so the row is never stuck in 'scanning'.
    """
    from app.db.session import SessionLocal
    from app.services.secure_upload_service import scan_and_finalize

    with SessionLocal() as db:
        row = scan_and_finalize(db, upload_id)
        return {
            "id": row.id,
            "module": row.module,
            "scan_status": row.scan_status,
            "malware_detected": row.malware_detected,
            "engine": row.scan_engine,
            "signature": row.scan_signature,
        }


@celery_app.task(name="secure_upload.cleanup_orphans")
def cleanup_orphans(older_than_minutes: int = 30) -> int:
    """Beat-scheduled sweep of abandoned temp uploads."""
    from app.db.session import SessionLocal
    from app.services.secure_upload_service import cleanup_orphaned_temp
    with SessionLocal() as db:
        return cleanup_orphaned_temp(db, older_than_minutes=older_than_minutes)
