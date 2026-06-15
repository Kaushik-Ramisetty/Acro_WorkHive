"""Audit-log helper. Writes to the generic `audit_logs` table."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def _new_audit_id() -> str:
    """Generate a collision-proof audit ID using UUID4.

    The previous COUNT(*)-based approach caused PRIMARY KEY violations during
    bulk operations: all write_audit() calls within the same transaction saw the
    same COUNT value (uncommitted inserts are invisible to COUNT), so every call
    in the same bulk loop produced an identical ``AUDIT{N+1:05d}`` ID, triggering
    an IntegrityError → HTTP 500.

    UUID4 hex is statistically unique with no DB read required, making it safe
    for concurrent / bulk use.
    """
    return f"AUDIT{uuid.uuid4().hex[:12].upper()}"


def _to_json(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except Exception:
        return str(v)


def write_audit(
    db: Session,
    *,
    actor_id: Optional[int],
    action: str,
    target_table: str,
    target_id: Any,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: Optional[str] = None,
) -> Optional[AuditLog]:
    """Append a row to audit_logs. Never raises — audit is best-effort.

    IMPORTANT: do NOT call db.rollback() here.  Rolling back inside an audit
    helper would silently undo any enclosing savepoint created by a bulk route
    handler, corrupting the entire bulk operation.
    """
    try:
        row = AuditLog(
            id=_new_audit_id(),
            actor_employee_id=actor_id,
            action=(action or "")[:60],
            target_table=(target_table or "")[:80],
            target_id=str(target_id) if target_id is not None else None,
            old_value=_to_json(old_value),
            new_value=_to_json(new_value),
            ip_address=ip_address,
        )
        db.add(row)
        return row
    except Exception:
        # Silently swallow — audit failure must never break the calling operation.
        # Do NOT call db.rollback() here: that would corrupt any enclosing
        # savepoint or ongoing bulk transaction.
        return None
