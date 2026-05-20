"""Celery tasks: negative-flow scan + comp-off expiry.

Beat schedule (registered in celery_app.py):
  - 02:00 UTC daily: leave.process_pending_consumption  (raises worked-on-leave validations or consumes)
  - 03:00 UTC daily: leave.expire_comp_off_credits     (expires unused approved credits)
"""
from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.leave_engine import process_pending_consumption, expire_comp_off_credits
from app.services.sla_escalation import run_sla_sweep
from app.services.payroll_bridge import retry_pending_syncs
from app.services.leave_accrual import run_monthly_accrual, run_year_end


logger = get_task_logger(__name__)


@celery_app.task(name="leave.process_pending_consumption")
def run_pending_consumption():
    with SessionLocal() as db:
        result = process_pending_consumption(db)
    logger.info("negative-flow scheduler ran: %s", result)
    return result


@celery_app.task(name="leave.expire_comp_off_credits")
def run_expire_comp_off():
    with SessionLocal() as db:
        result = expire_comp_off_credits(db)
    logger.info("comp-off expiry ran: %s", result)
    return result


@celery_app.task(name="leave.sla_sweep")
def run_sla_escalation():
    """Walk pending leave requests and apply the 24/48/72-hour ladder."""
    with SessionLocal() as db:
        result = run_sla_sweep(db)
    logger.info("SLA escalation sweep ran: %s", result)
    return result


@celery_app.task(name="leave.payroll_retry")
def run_payroll_retry():
    """Retry failed / pending payroll syncs."""
    with SessionLocal() as db:
        result = retry_pending_syncs(db)
    logger.info("payroll retry ran: %s", result)
    return result


@celery_app.task(name="leave.monthly_accrual")
def run_accrual_for_current_month():
    """Idempotent: re-running for the same month is a no-op because the
    ledger uses 'ACC-YYYY-MM' as the unique reference id."""
    from datetime import date
    today = date.today()
    with SessionLocal() as db:
        result = run_monthly_accrual(db, today.year, today.month)
    logger.info("monthly accrual ran: %s", result)
    return result


@celery_app.task(name="leave.year_end")
def run_year_end_task():
    """Carry-forward + yearly accrual. Runs on Jan 1; closing_year = previous calendar year."""
    from datetime import date
    today = date.today()
    closing_year = today.year - 1
    with SessionLocal() as db:
        result = run_year_end(db, closing_year)
    logger.info("year-end ran: %s", result)
    return result
