"""Background tasks. Currently logs login activity to stdout — swap with a DB row or Sentry hook in production."""
from datetime import datetime, timezone
from typing import Optional

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="activity.log_login")
def log_login_activity(user_id: int, email: str, role: Optional[str], ip: Optional[str], user_agent: Optional[str]):
    when = datetime.now(timezone.utc).isoformat()
    logger.info(
        "login user_id=%s email=%s role=%s ip=%s user_agent=%s at=%s",
        user_id, email, role, ip, user_agent, when,
    )
    return {"user_id": user_id, "at": when, "ok": True}
