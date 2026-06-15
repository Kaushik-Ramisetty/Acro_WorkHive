"""Daily HR attendance digest generator.

Generic digest engine — designed to be reusable for payroll alerts,
leave anomalies, overtime violations, onboarding delays, and other
compliance summaries.

Primary job: aggregate today's unresolved attendance exceptions, group by
type, and push a single consolidated in-app notification to every
admin/HR recipient.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_t
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models import AttendanceException, Employee
from app.services.notification_service import notify_many

logger = logging.getLogger("hrms.digest")


# ── Exception-type display labels ─────────────────────────────────────

_EXCEPTION_LABELS: dict[str, str] = {
    "late_arrival":     "Late Arrivals",
    "early_checkout":   "Early Checkouts",
    "missing_checkout": "Missing Check-outs",
    "no_checkout":      "Missing Check-outs",
    "absent_no_leave":  "Absent Without Leave",
    "short_hours":      "Short Working Hours",
    "missing_checkin":  "Missing Check-ins",
}


# ── Generic digest engine ──────────────────────────────────────────────

@dataclass
class DigestResult:
    """Outcome of one digest run."""
    date: date_t
    digest_type: str
    summary: dict[str, int]      # {human-readable label: count}
    total: int
    recipients: list[int]
    notifications_sent: int
    detail_lines: list[str] = field(default_factory=list)


def run_digest(
    *,
    db: Session,
    digest_type: str,
    target_date: date_t,
    title_fn: Callable[[date_t, int], str],
    body_fn: Callable[[dict[str, int], list[str]], str],
    recipient_ids: list[int],
    aggregator: Callable[[Session, date_t], tuple[dict[str, int], list[str]]],
    reference_table: Optional[str] = None,
) -> DigestResult:
    """Generic digest runner.

    Parameters
    ----------
    aggregator    : returns (summary_dict, detail_lines) for target_date.
    title_fn      : builds the notification title from (date, total_count).
    body_fn       : builds the notification body from (summary_dict, detail_lines).
    """
    summary, detail_lines = aggregator(db, target_date)
    total = sum(summary.values())

    sent = 0
    if total > 0 and recipient_ids:
        sent = notify_many(
            db,
            recipient_ids,
            type_=digest_type,
            title=title_fn(target_date, total),
            body=body_fn(summary, detail_lines),
            reference_table=reference_table,
            autocommit=False,
        )

    return DigestResult(
        date=target_date,
        digest_type=digest_type,
        summary=summary,
        total=total,
        recipients=recipient_ids,
        notifications_sent=sent,
        detail_lines=detail_lines,
    )


# ── Attendance digest ─────────────────────────────────────────────────

def _aggregate_attendance_exceptions(
    db: Session,
    target_date: date_t,
) -> tuple[dict[str, int], list[str]]:
    """Return (summary_by_type, top_offender_lines) for unresolved exceptions on target_date."""
    rows = (
        db.query(AttendanceException)
        .filter(
            AttendanceException.date == target_date,
            AttendanceException.is_resolved.is_(False),
        )
        .all()
    )

    summary: dict[str, int] = {}
    emp_counts: dict[int, int] = {}

    for exc in rows:
        label = _EXCEPTION_LABELS.get(
            exc.exception_type or "",
            (exc.exception_type or "Other").replace("_", " ").title(),
        )
        summary[label] = summary.get(label, 0) + 1
        if exc.employee_id:
            emp_counts[exc.employee_id] = emp_counts.get(exc.employee_id, 0) + 1

    # Top offenders: up to 5 employees with the most exceptions.
    detail_lines: list[str] = []
    if emp_counts:
        top = sorted(emp_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        emp_map = {
            e.id: e.full_name
            for e in db.query(Employee)
            .filter(Employee.id.in_([eid for eid, _ in top]))
            .all()
        }
        for eid, count in top:
            name = emp_map.get(eid, f"Employee #{eid}")
            suffix = f" — {count} exception{'s' if count > 1 else ''}"
            detail_lines.append(f"• {name}{suffix}")

    return summary, detail_lines


def _attendance_title(target_date: date_t, total: int) -> str:
    date_str = f"{target_date.day} {target_date.strftime('%b %Y')}"
    return f"Attendance Exceptions — {date_str} ({total} total)"


def _attendance_body(summary: dict[str, int], detail_lines: list[str]) -> str:
    lines = [f"{label}: {count}" for label, count in sorted(summary.items())]
    if detail_lines:
        lines.append("")
        lines.extend(detail_lines)
    return "\n".join(lines)[:500]


def generate_attendance_digest(
    db: Session,
    target_date: date_t,
    recipient_ids: list[int],
) -> DigestResult:
    """Generate and deliver the daily attendance exceptions digest.

    Called by the 6:30 PM cron job. Pushes one consolidated notification
    per admin/HR recipient summarising all unresolved attendance exceptions
    for target_date. Returns a DigestResult even when total == 0 (no-op
    notification skipped, result still logged).
    """
    return run_digest(
        db=db,
        digest_type="attendance_digest",
        target_date=target_date,
        title_fn=_attendance_title,
        body_fn=_attendance_body,
        recipient_ids=recipient_ids,
        aggregator=_aggregate_attendance_exceptions,
        reference_table="attendance_exceptions",
    )
