from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "hrms",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.activity",
        "app.tasks.leave_scheduler",
        "app.tasks.otp_tasks",
        "app.tasks.attendance_jobs",
        "app.tasks.scan_upload",
        "app.tasks.pms_auto_lock",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
)

celery_app.conf.beat_schedule = {
    "leave-pending-consumption": {
        "task": "leave.process_pending_consumption",
        "schedule": crontab(hour=2, minute=0),
    },
    "comp-off-expire": {
        "task": "leave.expire_comp_off_credits",
        "schedule": crontab(hour=3, minute=0),
    },
    # SLA escalation runs hourly so 24/48/72h thresholds are caught within
    # an hour of breach. The task itself is idempotent.
    "leave-sla-sweep": {
        "task": "leave.sla_sweep",
        "schedule": crontab(minute=15),  # every hour at :15
    },
    # Payroll retry every 30 min — picks up failed/pending syncs.
    "leave-payroll-retry": {
        "task": "leave.payroll_retry",
        "schedule": crontab(minute="0,30"),
    },
    # Monthly accrual: 02:30 UTC on day 1 of each month.
    "leave-monthly-accrual": {
        "task": "leave.monthly_accrual",
        "schedule": crontab(hour=2, minute=30, day_of_month=1),
    },
    # Year-end (carry-forward + yearly accrual): 03:00 UTC on Jan 1.
    "leave-year-end": {
        "task": "leave.year_end",
        "schedule": crontab(hour=3, minute=0, day_of_month=1, month_of_year=1),
    },
    # Attendance + timesheet jobs (Step 6/7/9 of the workflow).
    "attendance-daily-processing": {
        "task": "attendance.daily_processing",
        "schedule": crontab(hour=1, minute=30),    # 01:30 every day -> processes "yesterday"
    },
    "attendance-missed-checkouts": {
        "task": "attendance.detect_missed_checkouts",
        "schedule": crontab(hour=20, minute=0),    # 20:00 every day
    },
    "timesheet-submission-reminder": {
        "task": "timesheet.submission_reminder",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon"),  # weekly Monday 09:00
    },
    # Sweep abandoned temp uploads every 15 minutes — anything stuck in
    # 'uploaded_temp'/'scanning' for >30 min is flipped to 'scan_failed' and
    # the temp file is deleted.
    "secure-upload-cleanup-orphans": {
        "task": "secure_upload.cleanup_orphans",
        "schedule": crontab(minute="*/15"),
    },
    # PMS auto-lock: runs daily at 01:00 UTC, locks all three phase entities
    # (GoalAssignment / MidCycleReview / EndCycleAssessment) whose deadline
    # has elapsed. Auto-locked records are permanently immutable.
    "pms-auto-lock": {
        "task": "pms.auto_lock",
        "schedule": crontab(hour=1, minute=0),
    },
}
