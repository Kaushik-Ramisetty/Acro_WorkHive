"""Celery task: deliver OTP to the user via email.

Adapted from the source 2FA implementation; uses our Employee model
(not a separate User model) so it integrates with the existing HRMS auth.
"""
import logging
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Employee
from app.services.email_service import send_otp_email
from app.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _UserDeliveryInfo:
    user_id: int
    email: str
    full_name: str


@contextmanager
def _task_db_session():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fetch_user_details(user_id: int, db: Session):
    user = (
        db.query(Employee)
        .filter(Employee.id == user_id, Employee.is_deleted.is_(False))
        .first()
    )
    if user is None:
        return None
    if user.employment_status != "active":
        return None
    # Deliver to the official (company-issued) email when the employee has
    # been activated — that's the address tied to the credentials sent by
    # IT. For non-activated users (legacy seeded employees, demo accounts)
    # fall back to the personal email so existing flows keep working.
    official = (user.official_email or "").strip()
    delivery_email = official if (official and getattr(user, "is_activated", False)) else user.email
    return _UserDeliveryInfo(
        user_id=user.id,
        email=delivery_email,
        full_name=user.full_name or "",
    )


def _deliver_via_email(info: _UserDeliveryInfo, otp_code: str) -> None:
    # Always log the OTP for dev visibility
    logger.info(
        "OTP for user_id=%d  email=%s  code=%s  (expires in 2 minutes)",
        info.user_id, info.email, otp_code,
    )
    sent = send_otp_email(to_email=info.email, otp=otp_code, full_name=info.full_name)
    if not sent:
        logger.warning(
            "Email delivery skipped/failed for user_id=%d -- OTP visible in logs above.",
            info.user_id,
        )


@celery_app.task(
    name="otp.send_otp",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def send_otp_task(self, user_id: int, otp_code: str) -> None:
    """Deliver the OTP to the user. Retries on transient failures."""
    logger.debug(
        "OTP task started: user_id=%d attempt=%d/%d",
        user_id, self.request.retries + 1, self.max_retries + 1,
    )

    with _task_db_session() as db:
        info = _fetch_user_details(user_id, db)

    if info is None:
        logger.warning("OTP delivery skipped: user_id=%d not found or inactive.", user_id)
        return

    try:
        _deliver_via_email(info, otp_code)
        logger.debug("OTP task delivered: user_id=%d email=%s", user_id, info.email)
    except Exception as exc:
        logger.exception(
            "OTP delivery failed for user_id=%d (attempt %d/%d)",
            user_id, self.request.retries + 1, self.max_retries + 1,
        )
        countdown = self.default_retry_delay * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
