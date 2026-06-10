"""Celery task: auto-lock PMS phases whose deadline has passed.

Beat schedule (registered in celery_app.py):
  - 01:00 UTC daily: pms.auto_lock  — scans all three lockable phases and
    auto-locks any record whose deadline has elapsed but is not yet locked.

Auto-lock is permanent: once lock_type='auto' is written, no API endpoint or
UI control permits unlocking.  The service-layer checks enforce this at the
business-logic level; this task only triggers the lock.

Phase coverage:
  Phase 1 — GoalAssignment   (statuses: goals_sent … hr_reviewed)
  Phase 2 — MidCycleReview   (statuses: draft … hr_reviewed)
  Phase 3 — EndCycleAssessment (statuses: draft … hr_received)

Phase 4/5 (Normalization, Compensation) are HR-internal processes that don't
have per-employee deadlines in the same sense, so they are not auto-locked.
"""
from __future__ import annotations

import logging
from datetime import datetime

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app
from app.db.session import SessionLocal

logger = get_task_logger(__name__)


@celery_app.task(name="pms.auto_lock")
def run_pms_auto_lock() -> dict:
    """Scan all lockable PMS records past their deadline and auto-lock them."""
    from app.models.pms import (
        GoalAssignment, MidCycleReview, EndCycleAssessment,
        PMS_STATUS_GOALS_LOCKED,
        MCR_STATUS_LOCKED,
        ECA_STATUS_LOCKED,
        LOCK_TYPE_AUTO,
    )
    from app.services.audit_service import write_audit

    now = datetime.utcnow()
    locked_p1 = locked_p2 = locked_p3 = 0

    with SessionLocal() as db:
        # ── Phase 1: GoalAssignment ──────────────────────────────────────────
        # Lock any assignment with a past deadline that isn't already locked.
        p1_candidates = (
            db.query(GoalAssignment)
            .filter(
                GoalAssignment.deadline < now,
                GoalAssignment.status != PMS_STATUS_GOALS_LOCKED,
                GoalAssignment.deadline.isnot(None),
            )
            .all()
        )
        for a in p1_candidates:
            try:
                a.status = PMS_STATUS_GOALS_LOCKED
                a.locked_at = now
                a.locked_by = None        # system — no human actor
                a.lock_type = LOCK_TYPE_AUTO
                write_audit(
                    db,
                    actor_id=0,           # 0 = system
                    action="pms.assignment.auto_lock",
                    target_table="pms_goal_assignments",
                    target_id=str(a.id),
                    old_value={"status": a.status},
                    new_value={"status": PMS_STATUS_GOALS_LOCKED, "lock_type": LOCK_TYPE_AUTO},
                )
                locked_p1 += 1
            except Exception as exc:
                logger.warning("PMS auto-lock Phase1 id=%s failed: %s", a.id, exc)

        # ── Phase 2: MidCycleReview ──────────────────────────────────────────
        p2_candidates = (
            db.query(MidCycleReview)
            .filter(
                MidCycleReview.deadline < now,
                MidCycleReview.status != MCR_STATUS_LOCKED,
                MidCycleReview.deadline.isnot(None),
            )
            .all()
        )
        for r in p2_candidates:
            try:
                r.status = MCR_STATUS_LOCKED
                r.locked_at = now
                r.locked_by = None
                r.lock_type = LOCK_TYPE_AUTO
                write_audit(
                    db,
                    actor_id=0,
                    action="pms.mid_cycle.auto_lock",
                    target_table="pms_mid_cycle_reviews",
                    target_id=str(r.id),
                    old_value={"status": r.status},
                    new_value={"status": MCR_STATUS_LOCKED, "lock_type": LOCK_TYPE_AUTO},
                )
                locked_p2 += 1
            except Exception as exc:
                logger.warning("PMS auto-lock Phase2 id=%s failed: %s", r.id, exc)

        # ── Phase 3: EndCycleAssessment ──────────────────────────────────────
        p3_candidates = (
            db.query(EndCycleAssessment)
            .filter(
                EndCycleAssessment.deadline < now,
                EndCycleAssessment.status != ECA_STATUS_LOCKED,
                EndCycleAssessment.deadline.isnot(None),
            )
            .all()
        )
        for eca in p3_candidates:
            try:
                eca.status = ECA_STATUS_LOCKED
                eca.locked_at = now
                eca.locked_by = None
                eca.lock_type = LOCK_TYPE_AUTO
                write_audit(
                    db,
                    actor_id=0,
                    action="pms.eca.auto_lock",
                    target_table="pms_end_cycle_assessments",
                    target_id=str(eca.id),
                    old_value={"status": eca.status},
                    new_value={"status": ECA_STATUS_LOCKED, "lock_type": LOCK_TYPE_AUTO},
                )
                locked_p3 += 1
            except Exception as exc:
                logger.warning("PMS auto-lock Phase3 id=%s failed: %s", eca.id, exc)

        db.commit()

    total = locked_p1 + locked_p2 + locked_p3
    logger.info(
        "PMS auto-lock done — phase1=%d phase2=%d phase3=%d total=%d",
        locked_p1, locked_p2, locked_p3, total,
    )
    return {"phase1": locked_p1, "phase2": locked_p2, "phase3": locked_p3, "total": total}
