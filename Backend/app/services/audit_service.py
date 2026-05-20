"""Audit-log helper. Writes to the generic `audit_logs` table."""
from __future__ import annotations

import json
import secrets
import string
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


_ALPHA = string.ascii_uppercase + string.digits


def _new_audit_id(db: Session) -> str:
    """Generate a fresh AUDIT##### id. Uses count + random suffix to avoid PK clash."""
    count = db.query(AuditLog).count()
    base = f"AUDIT{count + 1:05d}"
    if db.get(AuditLog, base) is None:
        return base
    # Collision fallback (rare).
    suffix = "".join(secrets.choice(_ALPHA) for _ in range(4))
    return f"AUDIT{count + 1:05d}{suffix}"


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
    """Append a row to audit_logs. Never raises — audit is best-effort."""
    try:
        row = AuditLog(
            id=_new_audit_id(db),
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
        try:
            db.rollback()
        except Exception:
            pass
        return None
