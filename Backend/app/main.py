"""
Unified FastAPI application — Core HRMS + Onboarding module.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env BEFORE any other imports so utils/crypto.py and app/core/config.py
# see PII_ENCRYPTION_KEY / JWT_SECRET / SECRET_KEY / SMTP_* etc. when they
# evaluate module-level expressions on import.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  -- registers ALL ORM tables on Base


logger = logging.getLogger("hrms")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _run_onboarding_migrations() -> None:
    """Idempotent ALTERs from the original Onboarding module's startup."""
    from sqlalchemy import text

    safe_alters = [
        "ALTER TABLE candidates ADD COLUMN first_name VARCHAR(100)",
        "ALTER TABLE candidates ADD COLUMN last_name  VARCHAR(100)",
        "ALTER TABLE candidates ADD COLUMN ctc        VARCHAR(50)",
        "ALTER TABLE designations ADD COLUMN department_id VARCHAR(20)",
        "ALTER TABLE employees ADD COLUMN secondary_phone       VARCHAR(20)",
        "ALTER TABLE employees ADD COLUMN created_by            INTEGER",
        "ALTER TABLE employees ADD COLUMN updated_by            INTEGER",
        "ALTER TABLE employees ADD COLUMN deleted_at            DATETIME",
        "ALTER TABLE employees ADD COLUMN location              VARCHAR(100)",
        "ALTER TABLE employees ADD COLUMN time_zone             VARCHAR(50)",
        "ALTER TABLE employees ADD COLUMN official_email        VARCHAR(150)",
        "ALTER TABLE employees ADD COLUMN is_activated          INTEGER DEFAULT 0",
        "ALTER TABLE employees ADD COLUMN force_password_change INTEGER DEFAULT 1",
        # Phase 2 — SLA escalation columns on leave_requests.
        "ALTER TABLE leave_requests ADD COLUMN sla_escalation_level INTEGER DEFAULT 0",
        "ALTER TABLE leave_requests ADD COLUMN sla_last_alert_at    DATETIME",
        "ALTER TABLE leave_requests ADD COLUMN approver_override_id INTEGER",
        # Phase 3 — payroll sync tracking on leave_requests.
        "ALTER TABLE leave_requests ADD COLUMN payroll_sync_status   VARCHAR(20) DEFAULT 'na'",
        "ALTER TABLE leave_requests ADD COLUMN payroll_synced_at     DATETIME",
        "ALTER TABLE leave_requests ADD COLUMN payroll_sync_attempts INTEGER DEFAULT 0",
        "ALTER TABLE leave_requests ADD COLUMN payroll_last_error    VARCHAR(500)",
        # Phase 5A — additive balance columns + optimistic-concurrency token.
        "ALTER TABLE leave_balances ADD COLUMN allocated_balance INTEGER DEFAULT 0",
        "ALTER TABLE leave_balances ADD COLUMN pending_balance   INTEGER DEFAULT 0",
        "ALTER TABLE leave_balances ADD COLUMN row_version       INTEGER DEFAULT 0",
        # Phase 5B — accrual policy on leave_types + optional flag on holidays.
        "ALTER TABLE leave_types ADD COLUMN accrual_frequency      VARCHAR(10)",
        "ALTER TABLE leave_types ADD COLUMN accrual_days_per_cycle INTEGER",
        "ALTER TABLE leave_types ADD COLUMN probation_months       INTEGER DEFAULT 0",
        "ALTER TABLE holidays ADD COLUMN is_optional INTEGER DEFAULT 0",
        # Phase 5C — capacity %, additive only.
        "ALTER TABLE team_capacity_policies ADD COLUMN max_concurrent_percent INTEGER",
        # Phase 6 — resource-management profile fields on employees.
        "ALTER TABLE employees ADD COLUMN experience_years INTEGER",
        "ALTER TABLE employees ADD COLUMN certifications VARCHAR(500)",
        # Notification deep-link + metadata (introduced with the notification
        # system refactor — additive, safe to re-run on existing databases).
        "ALTER TABLE notifications ADD COLUMN action_url VARCHAR(255)",
        "ALTER TABLE notifications ADD COLUMN meta_json  VARCHAR(1000)",
        # Hybrid v2 leave workflow — tracks days already consumed so the
        # partial-cancellation engine can compute the cancellable remainder.
        "ALTER TABLE leave_requests ADD COLUMN consumed_days INTEGER DEFAULT 0",
        # Working-day engine — half-day boundary markers on a leave request.
        "ALTER TABLE leave_requests ADD COLUMN start_half_day VARCHAR(10)",
        "ALTER TABLE leave_requests ADD COLUMN end_half_day   VARCHAR(10)",
        # Attendance integration — new columns on existing tables.
        "ALTER TABLE projects ADD COLUMN billing_rate REAL",
        # Timesheet client-approval flow columns.
        "ALTER TABLE timesheets ADD COLUMN client_manager_id INTEGER",
        "ALTER TABLE timesheets ADD COLUMN client_manager_name VARCHAR(200)",
        "ALTER TABLE timesheets ADD COLUMN client_manager_email VARCHAR(255)",
        "ALTER TABLE timesheets ADD COLUMN client_token VARCHAR(500)",
        "ALTER TABLE timesheets ADD COLUMN client_token_expires_at DATETIME",
        "ALTER TABLE timesheets ADD COLUMN client_email_sent_at DATETIME",
        "ALTER TABLE timesheets ADD COLUMN client_email_status VARCHAR(50)",
        "ALTER TABLE timesheets ADD COLUMN client_approved_at DATETIME",
        "ALTER TABLE timesheets ADD COLUMN client_rejected_at DATETIME",
        "ALTER TABLE timesheets ADD COLUMN client_review_comment VARCHAR(1000)",
        "ALTER TABLE timesheets ADD COLUMN reminder_count INTEGER DEFAULT 0",
        "ALTER TABLE timesheets ADD COLUMN has_mismatch INTEGER DEFAULT 0",
        # Timesheet entry billability flag.
        "ALTER TABLE timesheet_entries ADD COLUMN is_billable INTEGER DEFAULT 1",
        # Employee T&M / timesheet type fields.
        "ALTER TABLE employees ADD COLUMN employee_type VARCHAR(20) DEFAULT 'wfh'",
        "ALTER TABLE employees ADD COLUMN is_tm INTEGER DEFAULT 0",
        "ALTER TABLE employees ADD COLUMN hourly_cost_rate REAL",
        "ALTER TABLE employees ADD COLUMN client_manager_name VARCHAR(200)",
        "ALTER TABLE employees ADD COLUMN client_manager_email VARCHAR(255)",
        # ── Payroll schema alignment (Excel schema v5) ────────────────────────
        # salary_structures: add DA and is_active to match uploaded Excel schema
        "ALTER TABLE salary_structures ADD COLUMN da REAL NOT NULL DEFAULT 0",
        "ALTER TABLE salary_structures ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
        # payroll_attendance_summary: add payable_days + attendance_status
        "ALTER TABLE payroll_attendance_summary ADD COLUMN payable_days INTEGER DEFAULT 0",
        "ALTER TABLE payroll_attendance_summary ADD COLUMN attendance_status VARCHAR(20) DEFAULT 'pending'",
    ]
    with engine.connect() as conn:
        for stmt in safe_alters:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

        # Phase 5C: install the SQL Server ledger-immutability trigger so
        # ad-hoc UPDATE/DELETE on the ledger table fails at the DB layer,
        # not just in the service contract. SQLite (dev) skips this branch.
        if conn.dialect.name == "mssql":
            try:
                conn.execute(text(
                    "IF OBJECT_ID('trg_leave_balance_ledger_immutable', 'TR') IS NOT NULL "
                    "DROP TRIGGER trg_leave_balance_ledger_immutable;"
                ))
                conn.execute(text("""
                    CREATE TRIGGER trg_leave_balance_ledger_immutable
                    ON leave_balance_ledger
                    INSTEAD OF UPDATE, DELETE
                    AS
                    BEGIN
                        RAISERROR (
                            'leave_balance_ledger is append-only; UPDATE/DELETE rejected. '
                            'Post a compensating entry instead.', 16, 1);
                        ROLLBACK TRANSACTION;
                    END;
                """))
                conn.commit()
            except Exception:
                pass

    # ── Payroll versioning migrations (v6) ───────────────────────────────────
    _run_payroll_versioning_migrations()

    # ── Salary revision audit log migration (v7) ─────────────────────────────
    _run_salary_revision_migrations()

    # ── Enterprise hardening migrations (v8) ─────────────────────────────────
    _run_enterprise_hardening_migrations()

    # ── Payroll DB document gap migrations (v9) ───────────────────────────────
    _run_payroll_document_gap_migrations()

    # ── Salary Hike Request workflow (v10) ───────────────────────────────────
    _run_salary_hike_request_migrations()

    # ── Multi-portal auth_accounts table (v11) ───────────────────────────────
    _run_auth_accounts_migration()

    # ── Monthly attendance summary bridge (v12) ──────────────────────────────
    _run_monthly_attendance_summary_migration()

    # ── Cross-portal employee rows for staff roles (v13) ─────────────────────
    _seed_employee_portal_for_staff()

    # ── Production hardening migrations (v14) ────────────────────────────────
    _run_production_hardening_migrations()

    # ── Salary hike production fields (v15) ──────────────────────────────────
    _run_salary_hike_production_fields()

    # ── Form 16 readiness — TDS annual summary (v16) ─────────────────────────
    _run_form16_readiness_migrations()

    # ── Tax declaration approval workflow (v17) ───────────────────────────────
    _run_declaration_approval_migration()

    # ── Payroll amount source-of-truth migration (v18) ───────────────────────
    _run_payroll_amount_source_migration()


_DEPARTMENTS = [
    {"id": "DEP001", "name": "Engineering",              "parent_department_id": None},
    {"id": "DEP002", "name": "Product",                  "parent_department_id": None},
    {"id": "DEP003", "name": "Human Resources",          "parent_department_id": None},
    {"id": "DEP004", "name": "Finance",                  "parent_department_id": None},
    {"id": "DEP005", "name": "Frontend Engineering",     "parent_department_id": "DEP001"},
    {"id": "DEP006", "name": "Backend Engineering",      "parent_department_id": "DEP001"},
    {"id": "DEP007", "name": "Quality Assurance",        "parent_department_id": "DEP001"},
    {"id": "DEP008", "name": "Data Engineering",         "parent_department_id": "DEP001"},
    {"id": "DEP009", "name": "DevOps & Infrastructure",  "parent_department_id": "DEP001"},
    {"id": "DEP010", "name": "Product Design",           "parent_department_id": None},
    {"id": "DEP011", "name": "Data Science & Analytics", "parent_department_id": None},
    {"id": "DEP012", "name": "Sales",                    "parent_department_id": None},
    {"id": "DEP013", "name": "Marketing",                "parent_department_id": None},
    {"id": "DEP014", "name": "Customer Success",         "parent_department_id": None},
    {"id": "DEP015", "name": "Legal & Compliance",       "parent_department_id": None},
]

_DESIGNATIONS = [
    {"id": "D1",  "title": "Software Engineer",          "level": 3},
    {"id": "D2",  "title": "Senior Software Engineer",   "level": 5},
    {"id": "D3",  "title": "Tech Lead",                  "level": 6},
    {"id": "D4",  "title": "Engineering Manager",        "level": 7},
    {"id": "D5",  "title": "Senior Manager",             "level": 8},
    {"id": "D6",  "title": "Junior Software Engineer",   "level": 2},
    {"id": "D7",  "title": "Associate Software Engineer","level": 1},
    {"id": "D8",  "title": "Principal Engineer",         "level": 9},
    {"id": "D9",  "title": "VP of Engineering",          "level": 10},
    {"id": "D10", "title": "CTO",                        "level": 12},
    {"id": "D11", "title": "Product Manager",            "level": 5},
    {"id": "D12", "title": "Senior Product Manager",     "level": 6},
    {"id": "D13", "title": "Director of Product",        "level": 8},
    {"id": "D14", "title": "Data Analyst",               "level": 3},
    {"id": "D15", "title": "Data Scientist",             "level": 5},
    {"id": "D16", "title": "Senior Data Scientist",      "level": 6},
    {"id": "D17", "title": "Trainee",                    "level": 1},
    {"id": "D18", "title": "HR",                         "level": 9},
    {"id": "D19", "title": "Finance Analyst",            "level": 3},
    {"id": "D20", "title": "DevOps Engineer",            "level": 4},
    {"id": "D21", "title": "Senior DevOps Engineer",     "level": 6},
    {"id": "D22", "title": "QA Engineer",                "level": 3},
    {"id": "D23", "title": "Senior QA Engineer",         "level": 5},
    {"id": "D24", "title": "UX Designer",                "level": 4},
    {"id": "D25", "title": "UI/UX Lead",                 "level": 6},
    {"id": "D26", "title": "CEO",                        "level": 12},
]

_LEAVE_TYPES = [
    {"id": "LT001", "name": "Sick Leave",         "annual_quota": 7,   "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "all"},
    # LT002 was originally "Casual Leave", later renamed to "Earned Leave",
    # and is now renamed to "Paid Leaves" (quota 12 unchanged). The id stays
    # LT002 so every LeaveBalance / LeaveRequest / audit row keeps working —
    # only the display name changes, and the seed updates the existing row's
    # name on startup. The legacy LT005 "Earned Leave" entry is still
    # filtered client-side via LEAVE_TYPE_HIDDEN_IDS in services/leave.js.
    {"id": "LT002", "name": "Paid Leaves",        "annual_quota": 12,   "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "all"},
    {"id": "LT003", "name": "Maternity Leave",    "annual_quota": 180,  "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "female"},
    {"id": "LT004", "name": "Paternity Leave",    "annual_quota": 15,   "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "male"},
    {"id": "LT006", "name": "Compensatory_leave", "annual_quota": None, "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "all"},
    {"id": "LT007", "name": "LOP_leaves",         "annual_quota": 0,    "carry_forward_limit": 0,  "is_paid": False, "applicable_gender": "all"},
    # Female-only menstrual leave; the existing applicable_gender filter in
    # ApplyLeaveModal hides it from non-female users automatically.
    {"id": "LT008", "name": "Menstrual Leave",    "annual_quota": 12,   "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "female"},
]


# ────────────────────────────────────────────────────────────────────────────
# Holiday seed — Pune 2026
# ----------------------------------------------------------------------------
# Source: Pune holiday list 2026 (uploaded PDF) + Government of Maharashtra
# gazetted holidays. Common holidays with Bangalore are not duplicated as
# separate rows — instead, the existing Bangalore row's `applicable_locations`
# is updated to "Bangalore,Pune" so a single record serves both offices.
# `applicable_locations` is comma-separated and matched as an exact token
# (case-insensitive) by app/routes/holidays.py::_filter_by_location.
#
# All entries below are idempotent — re-running the seed never duplicates and
# never overwrites manual admin edits except for adding Pune to a common
# holiday's `applicable_locations` field.
# ────────────────────────────────────────────────────────────────────────────

# Existing Bangalore holiday IDs that are ALSO observed in Pune (national /
# pan-India holidays). For these rows we only widen `applicable_locations`.
# Dates do not change — the existing seed's dates are respected.
_COMMON_BLR_PUNE_HOL_IDS: list[str] = [
    "HOL001",  # New Year's Day
    "HOL003",  # Republic Day (national)
    "HOL004",  # Holi / Dhulivandan
    "HOL006",  # Good Friday
    "HOL007",  # May Day  → also Maharashtra Day in Pune
    "HOL008",  # Bakrid / Eid al-Adha
    "HOL009",  # Independence Day (national)
    "HOL010",  # Ganesh Chaturthi (Pune is its cultural home)
    "HOL011",  # Gandhi Jayanti (national)
    "HOL012",  # Diwali
    "HOL013",  # Vijaya Dashami / Dussehra
    "HOL015",  # Christmas
]

# Pune-only public holidays for 2026. IDs use the HOL1xx range to avoid
# collision with the existing HOL0xx Bangalore seed. Dates follow the
# Government of Maharashtra 2026 calendar (Pune circle).
_PUNE_HOLIDAYS_2026: list[dict] = [
    {"id": "HOL101", "name": "Chhatrapati Shivaji Maharaj Jayanti", "date": "2026-02-19", "type": "public",   "optional": False},
    {"id": "HOL102", "name": "Gudi Padwa",                          "date": "2026-03-19", "type": "public",   "optional": False},
    {"id": "HOL103", "name": "Ram Navami",                          "date": "2026-03-26", "type": "public",   "optional": False},
    {"id": "HOL104", "name": "Mahavir Jayanti",                     "date": "2026-03-31", "type": "public",   "optional": False},
    {"id": "HOL105", "name": "Dr. Babasaheb Ambedkar Jayanti",      "date": "2026-04-14", "type": "public",   "optional": False},
    {"id": "HOL106", "name": "Maharashtra Day",                     "date": "2026-05-01", "type": "public",   "optional": False},
    {"id": "HOL107", "name": "Buddha Purnima",                      "date": "2026-05-31", "type": "public",   "optional": False},
    {"id": "HOL108", "name": "Muharram",                            "date": "2026-06-26", "type": "public",   "optional": False},
    {"id": "HOL109", "name": "Anant Chaturdashi (Ganesh Visarjan)", "date": "2026-09-24", "type": "public",   "optional": False},
    {"id": "HOL110", "name": "Diwali Padwa / Bali Pratipada",       "date": "2026-11-10", "type": "public",   "optional": False},
    {"id": "HOL111", "name": "Bhai Dooj",                           "date": "2026-11-11", "type": "public",   "optional": True },
    {"id": "HOL112", "name": "Guru Nanak Jayanti",                  "date": "2026-11-24", "type": "public",   "optional": False},
    # Optional / restricted holidays (Maharashtra optional list).
    {"id": "HOL113", "name": "Makara Sankranti",                    "date": "2026-01-14", "type": "optional", "optional": True },
    {"id": "HOL114", "name": "Parsi New Year",                      "date": "2026-08-16", "type": "optional", "optional": True },
    {"id": "HOL115", "name": "Chhath Puja",                         "date": "2026-11-15", "type": "optional", "optional": True },
]


def _seed_holidays_pune_2026() -> None:
    """Idempotent: insert Pune holidays + widen common Bangalore rows to
    include "Pune" in their applicable_locations token list.

    Re-running this function is safe:
      - existing HOL1xx rows are skipped (no overwrite of admin edits)
      - common rows already containing the "Pune" token are skipped
    """
    from datetime import date as _date
    from sqlalchemy.orm import Session
    from app.models import Holiday

    with Session(engine) as session:
        try:
            # 1) Widen common Bangalore rows to also serve Pune.
            for hid in _COMMON_BLR_PUNE_HOL_IDS:
                row = session.get(Holiday, hid)
                if not row:
                    continue
                raw = (row.applicable_locations or "").strip()
                tokens = [t.strip() for t in raw.split(",") if t.strip()]
                lowered = {t.lower() for t in tokens}
                if "pune" in lowered:
                    continue
                tokens.append("Pune")
                row.applicable_locations = ",".join(tokens)
            session.commit()

            # 2) Insert Pune-specific holidays.
            inserted = 0
            for row in _PUNE_HOLIDAYS_2026:
                if session.get(Holiday, row["id"]):
                    continue
                y, m, d = map(int, row["date"].split("-"))
                session.add(Holiday(
                    id=row["id"],
                    name=row["name"],
                    date=_date(y, m, d),
                    holiday_type=row["type"],
                    applicable_locations="Pune",
                    year=y,
                    is_optional=bool(row.get("optional", False)),
                ))
                inserted += 1
            session.commit()
            if inserted:
                logger.info("Pune 2026 holidays seeded: %d new row(s)", inserted)
        except Exception:
            session.rollback()
            logger.exception("Pune holiday seed failed (continuing).")


def _seed_master_data() -> None:
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.models import Department, Designation, LeaveType
    from app.models.role import Role

    with Session(engine) as session:
        for row in _DEPARTMENTS:
            if session.get(Department, row["id"]):
                continue
            if session.execute(select(Department).where(Department.name == row["name"])).scalar_one_or_none():
                continue
            session.add(Department(id=row["id"], name=row["name"], parent_department_id=row["parent_department_id"]))
        session.commit()
        for row in _DESIGNATIONS:
            existing = session.get(Designation, row["id"])
            if not existing:
                session.add(Designation(id=row["id"], title=row["title"], level=row["level"]))
            elif existing.level != row["level"]:
                existing.level = row["level"]
        session.commit()
        for row in _LEAVE_TYPES:
            existing = session.get(LeaveType, row["id"])
            if not existing:
                session.add(LeaveType(
                    id=row["id"], name=row["name"], annual_quota=row["annual_quota"],
                    carry_forward_limit=row["carry_forward_limit"], is_paid=row["is_paid"],
                    applicable_gender=row["applicable_gender"],
                ))
            else:
                existing.name = row["name"]; existing.annual_quota = row["annual_quota"]
                existing.carry_forward_limit = row["carry_forward_limit"]
                existing.is_paid = row["is_paid"]; existing.applicable_gender = row["applicable_gender"]
        session.commit()

        # Ensure 'finance' role exists (payroll management)
        if not session.execute(select(Role).where(Role.name == "finance")).scalar_one_or_none():
            session.add(Role(name="finance", description="Finance department — payroll & salary management"))
            session.commit()
            logger.info("Seeded 'finance' role")

        # Ensure 'finance_head' role exists (final payroll approval authority)
        if not session.execute(select(Role).where(Role.name == "finance_head")).scalar_one_or_none():
            session.add(Role(name="finance_head", description="Finance Head — final payroll approval authority"))
            session.commit()
            logger.info("Seeded 'finance_head' role")

        logger.info("Master data ready: %d departments, %d designations, %d leave types",
                    session.query(Department).count(), session.query(Designation).count(),
                    session.query(LeaveType).count())

    # Seed statutory settings (idempotent)
    try:
        from app.services.statutory_service import seed_default_settings
        from sqlalchemy.orm import Session as _Session
        with _Session(engine) as _s:
            seed_default_settings(_s)
    except Exception as _e:
        logger.warning("Statutory settings seed skipped: %s", _e)

    # Seed salary component master (idempotent — Excel schema alignment)
    try:
        from app.services.payroll_schema_service import seed_salary_components
        from sqlalchemy.orm import Session as _Session2
        with _Session2(engine) as _s2:
            seed_salary_components(_s2)
    except Exception as _e2:
        logger.warning("Salary components seed skipped: %s", _e2)


def _normalize_legacy_user_roles() -> None:
    """Normalize legacy users.role values to the uppercase onboarding enum."""
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            result = conn.execute(text("UPDATE users SET role = TRIM(UPPER(role)) WHERE role IS NOT NULL"))
            count = result.rowcount or 0
            if count:
                logger.info("Normalized %d legacy user role value(s) to uppercase.", count)
    except Exception:
        logger.exception("User role normalization failed (continuing).")


def _backfill_existing_employees_activated() -> None:
    """One-time, idempotent backfill: treat every pre-existing employee that
    already has a working login as "activated".

    Rationale
    ---------
    The ``employees.is_activated`` column was introduced for the onboarding
    workflow. It defaults to ``False`` for **every** row in the table —
    including employees seeded from Excel (``seed.py``) and any row created
    before the onboarding module shipped. Those rows have:

      - a valid ``password_hash``
      - ``employment_status = 'active'``
      - ``is_activated = False``  ← here be dragons

    The legacy login endpoint (``/api/v1/auth/login``) refuses any
    ``is_activated=False`` employee with the message
    *"Your account is not yet activated"*, so every pre-onboarding employee
    is permanently locked out.

    This routine flips ``is_activated → True`` **only** for rows that are
    clearly pre-activation-system employees (have a password + are active).
    It does **not** touch:

      - candidates converted via the new convert flow (no password_hash)
      - employees in ``pending_activation`` status
      - soft-deleted employees

    The query is idempotent: subsequent boots find no matching rows and
    are no-ops.
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import update
    from app.models import Employee

    with Session(engine) as session:
        try:
            res = session.execute(
                update(Employee)
                .where(
                    Employee.is_activated.is_(False),
                    Employee.is_deleted.is_(False),
                    Employee.employment_status == "active",
                    Employee.password_hash.is_not(None),
                )
                .values(is_activated=True)
            )
            session.commit()
            count = res.rowcount or 0
            if count:
                logger.info(
                    "Activation backfill: marked %d existing active employee(s) "
                    "as is_activated=True (had password + active status).",
                    count,
                )
        except Exception:
            session.rollback()
            logger.exception("Activation backfill failed (continuing).")


def _publish_orphaned_drafts() -> None:
    """One-time backfill: any announcement that is still 'draft' but has no
    explicit future publish_at was almost certainly created before the
    'publish_immediately' feature existed.  Publish them now so they become
    visible in the employee/manager feeds.

    Safe to run on every startup — it only touches rows that are still draft
    and whose publish_at is either NULL or already in the past.
    """
    from datetime import datetime as _dt, timezone as _tz
    from sqlalchemy import text as _text

    # Use timezone-aware UTC then strip tzinfo for naive-UTC string,
    # matching the storage convention used throughout announcement_service.
    now_iso = _dt.now(_tz.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                _text(
                    """
                    UPDATE announcements
                    SET    status     = 'published',
                           publish_at = NULL
                    WHERE  status = 'draft'
                      AND  (publish_at IS NULL OR publish_at <= :now)
                    """
                ),
                {"now": now_iso},
            )
            count = result.rowcount or 0
            if count:
                logger.info(
                    "Auto-published %d orphaned draft announcement(s) "
                    "(created before publish_immediately was introduced).",
                    count,
                )
    except Exception as exc:
        # Table may not exist yet on a fresh DB; Base.metadata.create_all
        # runs before this function so normally the table is already there.
        # Either way this is non-fatal.
        logger.warning("_publish_orphaned_drafts skipped: %s", exc)


_POLICY_CATEGORIES = [
    ("HR",                 "Human resources policies — leave, conduct, harassment, etc."),
    ("IT Security",        "Acceptable use, data security, asset handling."),
    ("Compliance",         "Regulatory and statutory compliance policies."),
    ("Finance",            "Reimbursements, claims, vendor payments."),
    ("Workplace",          "Office conduct, clear desk, remote work."),
    ("Onboarding",         "New-hire orientation and onboarding documents."),
    ("General",            "Other corporate guidelines."),
]


# Legacy PDFs that shipped with the static PoliciesPage. We migrate them into
# the DB so the existing files (still served from Frontend/public/policies)
# remain accessible after the switch to the API-driven module.
_LEGACY_POLICIES = [
    {
        "title":        "HR SECURITY POLICY",
        "category":     "HR",
        "description":  "Company-wide HR security policy.",
        "pdf_path":     "/policies/hr-security-policy.pdf",
    },
    {
        "title":        "EMPLOYEE REFERRAL PROGRAM 2023",
        "category":     "HR",
        "description":  "Employee referral program guidelines for 2023.",
        "pdf_path":     "/policies/employee-referral-program-2023.pdf",
    },
    {
        "title":        "CLEAR DESK AND CLEAR SCREEN POLICY",
        "category":     "Workplace",
        "description":  "Clear desk and clear screen standards.",
        "pdf_path":     "/policies/clear-desk-and-clear-screen-policy.pdf",
    },
    {
        "title":        "MOBILE COMPUTING AND TELEWORKING POLICY",
        "category":     "IT Security",
        "description":  "Mobile computing and teleworking policy.",
        "pdf_path":     "/policies/mobile-computing-and-teleworking-policy.pdf",
    },
]


def _seed_policy_categories_and_legacy_pdfs() -> None:
    """Idempotent: seed default policy categories and migrate the original
    static-PDF policies into the policies / policy_versions tables.

    Safe on every boot: if a category already exists (by name) it's skipped,
    and if a policy already exists (by slug) it's skipped. The legacy PDF
    paths point at `/policies/<file>.pdf` which is still served by Vite from
    `Frontend/public/policies/`, so old files remain accessible.
    """
    from sqlalchemy.orm import Session
    from app.models import (
        Employee, Policy, PolicyCategory, PolicyVersion, Role,
    )
    from app.services.policy_service import _slugify, _unique_slug

    with Session(engine) as session:
        try:
            # 1) Categories
            for name, desc in _POLICY_CATEGORIES:
                existing = (
                    session.query(PolicyCategory)
                    .filter(PolicyCategory.name == name)
                    .first()
                )
                if not existing:
                    session.add(PolicyCategory(name=name, description=desc))
            session.commit()

            # 2) Resolve a creator (an admin or HR employee). If neither
            # exists (fresh DB), we skip legacy seeding — admins will see
            # an empty list which is correct for a brand-new install.
            creator = (
                session.query(Employee)
                .join(Role, Role.id == Employee.role_id)
                .filter(
                    Role.name.in_(("admin", "hr", "Admin", "HR")),
                    Employee.is_deleted.is_(False),
                )
                .order_by(Employee.id.asc())
                .first()
            )
            if not creator:
                logger.info("Skipping legacy policy seed: no admin/HR user yet.")
                return

            # 3) Legacy PDFs
            cats_by_name = {c.name: c for c in session.query(PolicyCategory).all()}
            for row in _LEGACY_POLICIES:
                slug = _slugify(row["title"])
                if session.query(Policy).filter(Policy.slug == slug).first():
                    continue  # already migrated
                # Also skip if a title-matching policy already exists.
                if session.query(Policy).filter(Policy.title == row["title"]).first():
                    continue
                cat = cats_by_name.get(row["category"])
                p = Policy(
                    title=row["title"],
                    slug=_unique_slug(session, row["title"]),
                    description=row["description"],
                    category_id=cat.id if cat else None,
                    status="published",
                    created_by=creator.id,
                )
                session.add(p)
                session.flush()
                v = PolicyVersion(
                    policy_id=p.id,
                    version_number=1,
                    pdf_path=row["pdf_path"],
                    change_summary="Migrated from legacy static PDF.",
                    is_published=True,
                    created_by=creator.id,
                )
                session.add(v)
                session.flush()
                p.current_version_id = v.id
            session.commit()
            logger.info("Policy categories + legacy PDFs seed complete.")
        except Exception:
            session.rollback()
            logger.exception("Policy seed failed (continuing).")


# ─────────────────────────────────────────────────────────────────────────────
# Payroll migration helper functions (v6 – v18)
# All are idempotent and safe to re-run on startup.
# ─────────────────────────────────────────────────────────────────────────────

def _run_payroll_versioning_migrations() -> None:
    """Migration v6: Drop UNIQUE index on salary_structures.employee_id + add salary_structure_id to payroll_run_employees."""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            indexes = conn.execute(text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='salary_structures' AND sql IS NOT NULL"
            )).fetchall()
            for idx_name, idx_sql in indexes:
                if idx_sql and "UNIQUE" in idx_sql.upper() and "employee_id" in idx_sql.lower():
                    conn.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
                    conn.commit()
                    logger.info("Payroll migration v6A: dropped unique index '%s' from salary_structures.employee_id", idx_name)
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_salary_structures_emp_eff "
                "ON salary_structures(employee_id, effective_from DESC)"
            ))
            conn.commit()
        except Exception as exc:
            logger.warning("Payroll migration v6A skipped: %s", exc)

        try:
            conn.execute(text(
                "ALTER TABLE payroll_run_employees "
                "ADD COLUMN salary_structure_id INTEGER "
                "REFERENCES salary_structures(id) ON DELETE SET NULL"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists — idempotent


def _run_salary_revision_migrations() -> None:
    """Migration v7: Create salary_revision_logs table (enterprise audit trail)."""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS salary_revision_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    old_salary_structure_id INTEGER REFERENCES salary_structures(id) ON DELETE SET NULL,
                    new_salary_structure_id INTEGER NOT NULL REFERENCES salary_structures(id) ON DELETE CASCADE,
                    old_annual_ctc REAL DEFAULT 0.0, new_annual_ctc REAL DEFAULT 0.0,
                    ctc_difference REAL DEFAULT 0.0, ctc_change_pct REAL DEFAULT 0.0,
                    old_basic REAL DEFAULT 0.0, new_basic REAL DEFAULT 0.0,
                    old_hra REAL DEFAULT 0.0, new_hra REAL DEFAULT 0.0,
                    old_da REAL DEFAULT 0.0, new_da REAL DEFAULT 0.0,
                    old_special_allowance REAL DEFAULT 0.0, new_special_allowance REAL DEFAULT 0.0,
                    old_transport_allowance REAL DEFAULT 0.0, new_transport_allowance REAL DEFAULT 0.0,
                    old_medical_allowance REAL DEFAULT 0.0, new_medical_allowance REAL DEFAULT 0.0,
                    old_gross_monthly REAL DEFAULT 0.0, new_gross_monthly REAL DEFAULT 0.0,
                    old_net_monthly REAL DEFAULT 0.0, new_net_monthly REAL DEFAULT 0.0,
                    old_pf_employee REAL DEFAULT 0.0, new_pf_employee REAL DEFAULT 0.0,
                    old_esi_employee REAL DEFAULT 0.0, new_esi_employee REAL DEFAULT 0.0,
                    old_professional_tax REAL DEFAULT 0.0, new_professional_tax REAL DEFAULT 0.0,
                    old_tds REAL DEFAULT 0.0, new_tds REAL DEFAULT 0.0,
                    effective_from DATE NOT NULL,
                    revision_reason TEXT,
                    revised_by_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_salary_revision_logs_employee "
                "ON salary_revision_logs(employee_id, created_at DESC)"
            ))
            conn.commit()
        except Exception as exc:
            logger.warning("Salary revision migration v7 skipped: %s", exc)


def _run_enterprise_hardening_migrations() -> None:
    """Migration v8: Enterprise payroll hardening — new columns on reimbursements, final_settlements, payroll_attendance_summary."""
    from sqlalchemy import text

    safe_alters = [
        "ALTER TABLE reimbursements ADD COLUMN manager_approved_by_id INTEGER REFERENCES employees(id)",
        "ALTER TABLE reimbursements ADD COLUMN manager_approved_at DATETIME",
        "ALTER TABLE reimbursements ADD COLUMN manager_remarks TEXT",
        "ALTER TABLE reimbursements ADD COLUMN is_taxable INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE reimbursements ADD COLUMN description TEXT",
        "ALTER TABLE reimbursements ADD COLUMN receipt_url VARCHAR(500)",
        "ALTER TABLE final_settlements ADD COLUMN asset_recovery REAL NOT NULL DEFAULT 0",
        "ALTER TABLE final_settlements ADD COLUMN pending_reimbursements_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_attendance_summary ADD COLUMN overtime_hours REAL DEFAULT 0",
    ]
    with engine.connect() as conn:
        for stmt in safe_alters:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def _run_payroll_document_gap_migrations() -> None:
    """Migration v9: Additive payroll DB-document alignment — columns and extra tables."""
    from sqlalchemy import text

    safe_alters = [
        "ALTER TABLE payroll_runs ADD COLUMN payroll_run_code VARCHAR(40)",
        "ALTER TABLE payroll_runs ADD COLUMN month INTEGER",
        "ALTER TABLE payroll_runs ADD COLUMN year INTEGER",
        "ALTER TABLE payroll_runs ADD COLUMN attendance_locked INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_runs ADD COLUMN payroll_locked INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_runs ADD COLUMN finalized_by_id INTEGER REFERENCES employees(id)",
        "ALTER TABLE payroll_runs ADD COLUMN finalized_at DATETIME",
        "ALTER TABLE payroll_runs ADD COLUMN published_at DATETIME",
        "ALTER TABLE payroll_run_employees ADD COLUMN salary_assignment_id INTEGER REFERENCES employee_salary_assignments(id)",
        "ALTER TABLE payroll_run_employees ADD COLUMN total_working_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN payable_days REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN basic_pay REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN da REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN special_allowance REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN lta REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN conveyance REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN bonus REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN variable_pay REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN overtime_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN gross_earnings REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN lop_deduction REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN net_pay REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN employee_pf REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN employer_pf REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN employee_esi REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN employer_esi REAL NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN record_status VARCHAR(20) NOT NULL DEFAULT 'COMPUTED'",
        "ALTER TABLE payroll_run_employees ADD COLUMN variance_flag INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_run_employees ADD COLUMN variance_reason TEXT",
        "ALTER TABLE payroll_run_employees ADD COLUMN payslip_url VARCHAR(500)",
        "ALTER TABLE payroll_run_employees ADD COLUMN migration_completed INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_approvals ADD COLUMN approval_level VARCHAR(40)",
        "ALTER TABLE payroll_approvals ADD COLUMN approver_id INTEGER REFERENCES employees(id)",
        "ALTER TABLE payroll_approvals ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'",
        "ALTER TABLE payroll_approvals ADD COLUMN comments TEXT",
        "ALTER TABLE payroll_approvals ADD COLUMN approved_at DATETIME",
        "ALTER TABLE payroll_approvals ADD COLUMN updated_at DATETIME",
        "ALTER TABLE payslips ADD COLUMN payroll_record_id INTEGER REFERENCES payroll_run_employees(id)",
        "ALTER TABLE payslips ADD COLUMN month INTEGER",
        "ALTER TABLE payslips ADD COLUMN year INTEGER",
        "ALTER TABLE payslips ADD COLUMN payslip_number VARCHAR(60)",
        "ALTER TABLE payslips ADD COLUMN file_url VARCHAR(500)",
        "ALTER TABLE payslips ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'GENERATED'",
        "ALTER TABLE payslips ADD COLUMN generated_by_id INTEGER REFERENCES employees(id)",
        "ALTER TABLE payslips ADD COLUMN generated_at DATETIME",
        "ALTER TABLE payslips ADD COLUMN emailed_at DATETIME",
        "ALTER TABLE payslips ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_attendance_summary ADD COLUMN payroll_run_id INTEGER REFERENCES payroll_runs(id)",
        "ALTER TABLE payroll_attendance_summary ADD COLUMN payable_days REAL",
        "ALTER TABLE payroll_attendance_summary ADD COLUMN attendance_status VARCHAR(20)",
    ]
    with engine.connect() as conn:
        for stmt in safe_alters:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

        create_statements = [
            """CREATE TABLE IF NOT EXISTS payroll_lock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
                lock_type VARCHAR(20) NOT NULL, action VARCHAR(10) NOT NULL,
                action_by INTEGER REFERENCES employees(id),
                action_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, reason TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS statutory_deductions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_record_id INTEGER NOT NULL REFERENCES payroll_run_employees(id) ON DELETE CASCADE,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                deduction_code VARCHAR(10) NOT NULL,
                employee_amount REAL NOT NULL DEFAULT 0, employer_amount REAL NOT NULL DEFAULT 0,
                wage_base REAL NOT NULL DEFAULT 0, calculation_formula TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS employee_salary_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                salary_structure_id INTEGER NOT NULL REFERENCES salary_structures(id) ON DELETE CASCADE,
                effective_from DATE NOT NULL, effective_to DATE,
                ctc_annual REAL NOT NULL DEFAULT 0, monthly_ctc REAL NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                assigned_by_id INTEGER REFERENCES employees(id),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
        ]
        for stmt in create_statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

        index_statements = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_run_employee ON payroll_run_employees(run_id, employee_id)",
            "CREATE INDEX IF NOT EXISTS ix_payroll_lock_history_run ON payroll_lock_history(payroll_run_id)",
            "CREATE INDEX IF NOT EXISTS ix_statutory_deductions_record ON statutory_deductions(payroll_record_id)",
            "CREATE INDEX IF NOT EXISTS ix_salary_assignments_emp_status ON employee_salary_assignments(employee_id, status)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_payslip_number ON payslips(payslip_number)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_payslip_run_employee ON payslips(run_id, employee_id)",
        ]
        for stmt in index_statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def _run_salary_hike_request_migrations() -> None:
    """Migration v10: Create salary_hike_requests table."""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS salary_hike_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    old_ctc REAL DEFAULT 0.0, new_ctc REAL NOT NULL,
                    hike_type VARCHAR(20) NOT NULL, hike_value REAL NOT NULL,
                    effective_from DATE NOT NULL, reason TEXT,
                    status VARCHAR(30) NOT NULL DEFAULT 'pending_finance_review',
                    requested_by_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    reviewed_by_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    review_comment TEXT,
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_salary_hike_requests_employee ON salary_hike_requests(employee_id, created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_salary_hike_requests_status ON salary_hike_requests(status)"))
            conn.commit()
        except Exception as exc:
            logger.warning("Salary hike migration v10 skipped: %s", exc)


def _run_auth_accounts_migration() -> None:
    """Migration v11: Create auth_accounts table for multi-portal authentication."""
    from app.utils.db_compat import create_table_if_not_exists, is_mssql
    from sqlalchemy import text

    with engine.connect() as conn:
        create_table_if_not_exists(
            conn,
            "auth_accounts",
            column_defs=[
                "id            INTEGER PRIMARY KEY AUTOINCREMENT",
                "email         VARCHAR(150) NOT NULL",
                "password_hash VARCHAR(200) NOT NULL",
                "role          VARCHAR(50)  NOT NULL",
                "employee_id   INTEGER NOT NULL REFERENCES employees(id)",
                "is_active     INTEGER NOT NULL DEFAULT 1",
                "created_at    DATETIME DEFAULT CURRENT_TIMESTAMP",
            ],
            table_constraints=["UNIQUE(email, role)"],
            indexes=[
                ("ix_auth_accounts_email",    "auth_accounts", "email"),
                ("ix_auth_accounts_employee", "auth_accounts", "employee_id"),
            ],
        )
        # Auto-populate from existing employees
        try:
            mssql = is_mssql(conn)
            if mssql:
                conn.execute(text("""
                    INSERT INTO auth_accounts (email, password_hash, role, employee_id, is_active)
                    SELECT LOWER(LTRIM(RTRIM(e.email))), e.password_hash,
                           LOWER(COALESCE(r.name, 'employee')), e.id, 1
                    FROM employees e
                    LEFT JOIN roles r ON r.id = e.role_id
                    WHERE e.email IS NOT NULL AND e.password_hash IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM auth_accounts a
                          WHERE LOWER(LTRIM(RTRIM(a.email))) = LOWER(LTRIM(RTRIM(e.email)))
                            AND LOWER(LTRIM(RTRIM(a.role)))  = LOWER(COALESCE(r.name, 'employee'))
                      )
                """))
            else:
                conn.execute(text("""
                    INSERT OR IGNORE INTO auth_accounts (email, password_hash, role, employee_id, is_active)
                    SELECT LOWER(TRIM(e.email)), e.password_hash,
                           LOWER(COALESCE(r.name, 'employee')), e.id, 1
                    FROM employees e
                    LEFT JOIN roles r ON r.id = e.role_id
                    WHERE e.email IS NOT NULL AND e.password_hash IS NOT NULL
                """))
            conn.commit()
            logger.info("Auth accounts migration v11: auth_accounts populated.")
        except Exception as exc:
            logger.warning("Auth accounts v11 (auto-populate) skipped: %s", exc)


def _run_monthly_attendance_summary_migration() -> None:
    """Migration v12: monthly_attendance_summary + payroll_attendance_audit tables."""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monthly_attendance_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    month INTEGER NOT NULL, year INTEGER NOT NULL,
                    total_working_days INTEGER NOT NULL DEFAULT 0,
                    present_days INTEGER NOT NULL DEFAULT 0,
                    leave_days INTEGER NOT NULL DEFAULT 0,
                    lop_days INTEGER NOT NULL DEFAULT 0,
                    payable_days REAL NOT NULL DEFAULT 0.0,
                    approved_timesheet_hours REAL NOT NULL DEFAULT 0.0,
                    attendance_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    timesheet_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    validation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    issues_count INTEGER NOT NULL DEFAULT 0,
                    validation_notes TEXT,
                    is_ready_for_payroll INTEGER NOT NULL DEFAULT 0,
                    is_frozen INTEGER NOT NULL DEFAULT 0,
                    finalized_by INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    finalized_at DATETIME,
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now')),
                    UNIQUE(employee_id, month, year)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mas_employee ON monthly_attendance_summary(employee_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mas_month_year ON monthly_attendance_summary(month, year)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mas_frozen ON monthly_attendance_summary(is_frozen)"))
            conn.commit()
        except Exception as exc:
            logger.warning("Monthly attendance summary migration v12 skipped: %s", exc)

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS payroll_attendance_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    role VARCHAR(50), action VARCHAR(60) NOT NULL,
                    month INTEGER NOT NULL, year INTEGER NOT NULL,
                    details TEXT, created_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_paa_month_year ON payroll_attendance_audit(month, year)"))
            conn.commit()
        except Exception as exc:
            logger.warning("Payroll attendance audit migration v12 skipped: %s", exc)


def _seed_employee_portal_for_staff() -> None:
    """Migration v13: auto-create employee-portal auth_accounts rows for staff roles."""
    from sqlalchemy import text
    from app.utils.db_compat import is_mssql

    with engine.connect() as conn:
        mssql = is_mssql(conn)
        try:
            if mssql:
                conn.execute(text("""
                    INSERT INTO auth_accounts (email, password_hash, role, employee_id, is_active)
                    SELECT aa.email, aa.password_hash, 'employee', aa.employee_id, 1
                    FROM auth_accounts aa
                    WHERE LOWER(LTRIM(RTRIM(aa.role))) IN ('finance', 'finance_head', 'admin', 'manager')
                      AND NOT EXISTS (
                          SELECT 1 FROM auth_accounts x
                          WHERE LOWER(LTRIM(RTRIM(x.email))) = LOWER(LTRIM(RTRIM(aa.email)))
                            AND LOWER(LTRIM(RTRIM(x.role)))  = 'employee'
                      )
                """))
            else:
                conn.execute(text("""
                    INSERT OR IGNORE INTO auth_accounts (email, password_hash, role, employee_id, is_active)
                    SELECT aa.email, aa.password_hash, 'employee', aa.employee_id, 1
                    FROM auth_accounts aa
                    WHERE LOWER(TRIM(aa.role)) IN ('finance', 'finance_head', 'admin', 'manager')
                      AND NOT EXISTS (
                          SELECT 1 FROM auth_accounts x
                          WHERE LOWER(TRIM(x.email)) = LOWER(TRIM(aa.email))
                            AND LOWER(TRIM(x.role))  = 'employee'
                      )
                """))
            conn.commit()
            logger.info("Auth accounts migration v13: employee-portal rows seeded for staff.")
        except Exception as exc:
            logger.warning("Auth accounts v13 (employee-portal seed) skipped: %s", exc)


def _run_production_hardening_migrations() -> None:
    """Migration v14: payslip_download_audit, payroll_variance_log, variance/cutoff/snapshot columns."""
    from app.utils.db_compat import create_table_if_not_exists, add_column_if_not_exists

    with engine.connect() as conn:
        create_table_if_not_exists(conn, "payslip_download_audit", column_defs=[
            "id               INTEGER PRIMARY KEY AUTOINCREMENT",
            "payslip_id       INTEGER NOT NULL REFERENCES payslips(id)",
            "employee_id      INTEGER NOT NULL REFERENCES employees(id)",
            "downloaded_by_id INTEGER REFERENCES employees(id)",
            "downloaded_at    DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
            "ip_address       VARCHAR(50)", "user_agent VARCHAR(500)",
            "download_source  VARCHAR(30) NOT NULL DEFAULT 'web'",
        ], indexes=[
            ("ix_pda_payslip",    "payslip_download_audit", "payslip_id"),
            ("ix_pda_employee",   "payslip_download_audit", "employee_id"),
            ("ix_pda_downloaded", "payslip_download_audit", "downloaded_at"),
        ])
        create_table_if_not_exists(conn, "payroll_variance_log", column_defs=[
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "run_id INTEGER NOT NULL REFERENCES payroll_runs(id)",
            "employee_id INTEGER NOT NULL REFERENCES employees(id)",
            "prev_run_id INTEGER REFERENCES payroll_runs(id)",
            "prev_gross_pay FLOAT NOT NULL DEFAULT 0", "curr_gross_pay FLOAT NOT NULL DEFAULT 0",
            "gross_variance_pct FLOAT NOT NULL DEFAULT 0",
            "prev_net_pay FLOAT NOT NULL DEFAULT 0", "curr_net_pay FLOAT NOT NULL DEFAULT 0",
            "net_variance_pct FLOAT NOT NULL DEFAULT 0",
            "prev_tds FLOAT NOT NULL DEFAULT 0", "curr_tds FLOAT NOT NULL DEFAULT 0",
            "prev_lop_days FLOAT NOT NULL DEFAULT 0", "curr_lop_days FLOAT NOT NULL DEFAULT 0",
            "variance_flags VARCHAR(500)", "is_flagged INTEGER NOT NULL DEFAULT 0",
            "acknowledged_by_id INTEGER REFERENCES employees(id)",
            "acknowledged_at DATETIME", "acknowledgement_note TEXT",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        ], indexes=[
            ("ix_pvl_run",      "payroll_variance_log", "run_id"),
            ("ix_pvl_employee", "payroll_variance_log", "employee_id, run_id"),
        ])
        add_column_if_not_exists(conn, "payroll_runs", "variance_reviewed", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "payroll_runs", "variance_reviewed_by_id", "INTEGER REFERENCES employees(id)")
        add_column_if_not_exists(conn, "payroll_runs", "variance_reviewed_at", "DATETIME")
        add_column_if_not_exists(conn, "payroll_runs", "variance_threshold_pct", "FLOAT NOT NULL DEFAULT 20.0")
        add_column_if_not_exists(conn, "statutory_settings", "declaration_cutoff_month", "INTEGER NOT NULL DEFAULT 1")
        add_column_if_not_exists(conn, "statutory_settings", "declaration_cutoff_day", "INTEGER NOT NULL DEFAULT 31")
        add_column_if_not_exists(conn, "monthly_attendance_summary", "frozen_by_id", "INTEGER REFERENCES employees(id)")
        add_column_if_not_exists(conn, "monthly_attendance_summary", "frozen_at", "DATETIME")
        add_column_if_not_exists(conn, "monthly_attendance_summary", "snapshot_note", "TEXT")
    logger.info("Production hardening migration v14: complete.")


def _run_salary_hike_production_fields() -> None:
    """Migration v15: Add approved_by_id, approved_at, rejection_reason, effective_date_validated to salary_hike_requests."""
    from app.utils.db_compat import add_column_if_not_exists

    with engine.connect() as conn:
        add_column_if_not_exists(conn, "salary_hike_requests", "approved_by_id", "INTEGER REFERENCES employees(id)")
        add_column_if_not_exists(conn, "salary_hike_requests", "approved_at", "DATETIME")
        add_column_if_not_exists(conn, "salary_hike_requests", "rejection_reason", "TEXT")
        add_column_if_not_exists(conn, "salary_hike_requests", "effective_date_validated", "INTEGER NOT NULL DEFAULT 0")
    logger.info("Salary hike production fields migration v15: complete.")


def _run_form16_readiness_migrations() -> None:
    """Migration v16: tds_annual_summary, tds_monthly_breakup tables + TDS audit columns on payroll_run_employees."""
    from app.utils.db_compat import create_table_if_not_exists, add_column_if_not_exists

    with engine.connect() as conn:
        create_table_if_not_exists(conn, "tds_annual_summary", column_defs=[
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "employee_id INTEGER NOT NULL REFERENCES employees(id)",
            "financial_year VARCHAR(10) NOT NULL",
            "pan_number VARCHAR(20)", "tax_regime VARCHAR(20) NOT NULL DEFAULT 'new'",
            "gross_annual_income FLOAT NOT NULL DEFAULT 0",
            "standard_deduction FLOAT NOT NULL DEFAULT 75000",
            "sec_80c_claimed FLOAT NOT NULL DEFAULT 0", "sec_80d_claimed FLOAT NOT NULL DEFAULT 0",
            "hra_exemption_claimed FLOAT NOT NULL DEFAULT 0",
            "sec_24b_claimed FLOAT NOT NULL DEFAULT 0", "sec_80ccd_claimed FLOAT NOT NULL DEFAULT 0",
            "other_deductions_claimed FLOAT NOT NULL DEFAULT 0",
            "total_deductions FLOAT NOT NULL DEFAULT 0", "taxable_income FLOAT NOT NULL DEFAULT 0",
            "annual_tax_before_cess FLOAT NOT NULL DEFAULT 0", "cess_amount FLOAT NOT NULL DEFAULT 0",
            "annual_tax_with_cess FLOAT NOT NULL DEFAULT 0", "rebate_87a FLOAT NOT NULL DEFAULT 0",
            "total_tds_deducted FLOAT NOT NULL DEFAULT 0",
            "employer_tan VARCHAR(20)", "employer_name VARCHAR(200)", "employer_address TEXT",
            "is_finalized INTEGER NOT NULL DEFAULT 0", "finalized_at DATETIME",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        ], table_constraints=["UNIQUE(employee_id, financial_year)"],
        indexes=[("ix_tas_employee_fy", "tds_annual_summary", "employee_id, financial_year")])

        create_table_if_not_exists(conn, "tds_monthly_breakup", column_defs=[
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "employee_id INTEGER NOT NULL REFERENCES employees(id)",
            "run_id INTEGER NOT NULL REFERENCES payroll_runs(id)",
            "financial_year VARCHAR(10) NOT NULL",
            "month INTEGER NOT NULL", "year INTEGER NOT NULL",
            "gross_salary FLOAT NOT NULL DEFAULT 0", "monthly_tds FLOAT NOT NULL DEFAULT 0",
            "pf_employee FLOAT NOT NULL DEFAULT 0", "esi_employee FLOAT NOT NULL DEFAULT 0",
            "professional_tax FLOAT NOT NULL DEFAULT 0",
            "regime_used VARCHAR(20) NOT NULL DEFAULT 'new'",
            "annual_taxable_at_time FLOAT NOT NULL DEFAULT 0",
            "remaining_months_at_time INTEGER NOT NULL DEFAULT 12",
            "tds_debug_json TEXT",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        ], table_constraints=["UNIQUE(employee_id, run_id)"],
        indexes=[
            ("ix_tmb_employee_fy", "tds_monthly_breakup", "employee_id, financial_year"),
            ("ix_tmb_run", "tds_monthly_breakup", "run_id"),
        ])

        add_column_if_not_exists(conn, "payroll_run_employees", "tds_annual_gross", "FLOAT NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "payroll_run_employees", "tds_taxable_income", "FLOAT NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "payroll_run_employees", "tds_regime", "VARCHAR(20) NOT NULL DEFAULT 'new'")
        add_column_if_not_exists(conn, "payroll_run_employees", "tds_debug_json", "TEXT")
    logger.info("Form 16 readiness migration v16: complete.")


def _run_declaration_approval_migration() -> None:
    """Migration v17: Tax declaration approval workflow fields + declaration_audit_log table."""
    from app.utils.db_compat import add_column_if_not_exists, create_table_if_not_exists

    with engine.connect() as conn:
        add_column_if_not_exists(conn, "employee_tax_declarations", "declaration_status", "VARCHAR(20) NOT NULL DEFAULT 'draft'")
        add_column_if_not_exists(conn, "employee_tax_declarations", "rejection_reason", "TEXT")
        add_column_if_not_exists(conn, "employee_tax_declarations", "reviewed_by_id", "INTEGER REFERENCES employees(id)")
        add_column_if_not_exists(conn, "employee_tax_declarations", "reviewed_at", "DATETIME")
        add_column_if_not_exists(conn, "employee_tax_declarations", "submitted_at", "DATETIME")
        add_column_if_not_exists(conn, "employee_tax_declarations", "is_locked", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "employee_tax_declarations", "lock_reason", "VARCHAR(200)")

        create_table_if_not_exists(conn, "declaration_audit_log", column_defs=[
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "declaration_id INTEGER NOT NULL REFERENCES employee_tax_declarations(id)",
            "employee_id INTEGER NOT NULL REFERENCES employees(id)",
            "action VARCHAR(30) NOT NULL",
            "old_status VARCHAR(20)", "new_status VARCHAR(20)",
            "performed_by_id INTEGER REFERENCES employees(id)",
            "reason TEXT",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        ], indexes=[
            ("ix_dal_declaration", "declaration_audit_log", "declaration_id"),
            ("ix_dal_employee",    "declaration_audit_log", "employee_id"),
        ])
    logger.info("Declaration approval migration v17: complete.")


def _run_payroll_amount_source_migration() -> None:
    """Migration v18: make payroll_run_employees final amount columns authoritative."""
    from sqlalchemy import text
    from app.utils.db_compat import add_column_if_not_exists

    with engine.connect() as conn:
        add_column_if_not_exists(conn, "payroll_run_employees", "employee_pf", "FLOAT NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "payroll_run_employees", "employee_esi", "FLOAT NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "payroll_run_employees", "migration_completed", "INTEGER NOT NULL DEFAULT 0")

        try:
            conn.execute(text("""
                UPDATE payroll_run_employees SET
                    gross_earnings = CASE WHEN COALESCE(gross_earnings,0)=0 AND COALESCE(gross_salary,0)<>0 THEN gross_salary ELSE COALESCE(gross_earnings,gross_salary,0) END,
                    basic_pay      = CASE WHEN COALESCE(basic_pay,0)=0 AND COALESCE(basic,0)<>0 THEN basic ELSE COALESCE(basic_pay,basic,0) END,
                    employee_pf    = CASE WHEN COALESCE(employee_pf,0)=0 AND COALESCE(pf_employee,0)<>0 THEN pf_employee ELSE COALESCE(employee_pf,pf_employee,0) END,
                    employer_pf    = CASE WHEN COALESCE(employer_pf,0)=0 AND COALESCE(pf_employer,0)<>0 THEN pf_employer ELSE COALESCE(employer_pf,pf_employer,0) END,
                    employee_esi   = CASE WHEN COALESCE(employee_esi,0)=0 AND COALESCE(esi_employee,0)<>0 THEN esi_employee ELSE COALESCE(employee_esi,esi_employee,0) END,
                    employer_esi   = CASE WHEN COALESCE(employer_esi,0)=0 AND COALESCE(esi_employer,0)<>0 THEN esi_employer ELSE COALESCE(employer_esi,esi_employer,0) END,
                    net_pay        = CASE WHEN COALESCE(net_pay,0)=0 AND COALESCE(net_salary,0)<>0 THEN net_salary ELSE COALESCE(net_pay,net_salary,0) END
            """))
            conn.execute(text("""
                UPDATE payroll_run_employees SET
                    gross_salary=COALESCE(gross_earnings,0), basic=COALESCE(basic_pay,0),
                    pf_employee=COALESCE(employee_pf,0), pf_employer=COALESCE(employer_pf,0),
                    esi_employee=COALESCE(employee_esi,0), esi_employer=COALESCE(employer_esi,0),
                    net_salary=COALESCE(net_pay,0), migration_completed=1
            """))
            conn.commit()
        except Exception:
            pass  # Tables may be empty on first boot


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_onboarding_migrations()
    _normalize_legacy_user_roles()
    _seed_master_data()
    _seed_holidays_pune_2026()
    _backfill_existing_employees_activated()
    _publish_orphaned_drafts()
    _seed_policy_categories_and_legacy_pdfs()
    # Phase 5A: one-shot idempotent backfill that aligns legacy rows with the
    # new ledger model (seeds allocated_balance, auto-closes in-flight HR-stage
    # leave requests under the synthetic system actor).
    try:
        from app.db.session import SessionLocal
        from app.services.leave_ledger_backfill import run_phase5a_startup_hooks
        with SessionLocal() as _bf_db:
            _summary = run_phase5a_startup_hooks(_bf_db)
            if _summary.get("allocated_seeded") or _summary.get("hr_stage_auto_closed"):
                logger.info("Phase 5A backfill summary: %s", _summary)
    except Exception:
        logger.exception("Phase 5A backfill failed (continuing).")

    # Hybrid v2 migration — moves the "approved but not yet consumed" days
    # from reservation-only to immediate-deduction shape. Idempotent: each
    # leave gets at most one synthetic LEAVE_DEDUCTION ledger row tagged
    # with reference_type='system_v2_migration'.
    try:
        from app.db.session import SessionLocal
        from app.services.leave_v2_migration import migrate_to_v2
        with SessionLocal() as _v2_db:
            _v2_summary = migrate_to_v2(_v2_db)
            if _v2_summary.get("migrated"):
                logger.info("Leave v2 migration: %s", _v2_summary)
    except Exception:
        logger.exception("Leave v2 migration failed (continuing).")

    # ---------------------------------------------------------------
    # Phase 5D: startup self-heal sweep.
    #
    # If the Celery beat for leave.process_pending_consumption hasn't run
    # in the last 25 hours (or has never run), execute one synchronous
    # sweep here so balances stay current in dev environments where
    # Celery beat is not started. The sweep is idempotent — re-running
    # within the same boot is harmless.
    # ---------------------------------------------------------------
    try:
        from datetime import timedelta
        from app.db.session import SessionLocal
        from app.models import SchedulerHealth
        from app.services.leave_engine import process_pending_consumption
        from utils.time_utils import now_utc
        with SessionLocal() as _sh_db:
            row = _sh_db.get(SchedulerHealth, "leave.process_pending_consumption")
            stale = (
                row is None
                or row.last_run_at is None
                or (now_utc() - row.last_run_at) > timedelta(hours=25)
            )
            if stale:
                logger.info(
                    "startup: consumption sweep stale (last_run=%s); running sync",
                    getattr(row, "last_run_at", None),
                )
                summary = process_pending_consumption(_sh_db)
                logger.info("startup: consumption sweep summary: %s", summary)
            else:
                logger.info(
                    "startup: consumption sweep last ran at %s (fresh, skipping)",
                    row.last_run_at,
                )
    except Exception:
        logger.exception("startup self-heal sweep failed (continuing).")

    logger.info("HRMS unified app ready (env=%s)", settings.APP_ENV)
    yield


app = FastAPI(
    title="HRMS - Unified (Core + Onboarding)",
    description="Unified HRMS merging Core HRMS with the Onboarding module.",
    version="3.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
_cors_extra = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else []
_cors = list(dict.fromkeys((settings.allowed_origins or []) + _cors_extra)) or [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:3000", "http://127.0.0.1:3000",
]
app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Centralised AppException → JSON handler. Additive only — does not displace
# any of FastAPI's built-in handlers (HTTPException, RequestValidationError),
# so existing endpoints continue to emit their exact prior responses.
try:
    from app.core.exceptions import register_exception_handlers
    register_exception_handlers(app)
except Exception:  # pragma: no cover — defensive: never fail boot for this.
    logger.exception("Failed to register AppException handlers (continuing).")

# Request-logging middleware. Adds one structured log line per request and
# attaches the request id to the response as `X-Request-ID`. Disables via
# HRMS_DISABLE_REQUEST_LOG=true. Never modifies request/response bodies.
try:
    from app.middleware.request_logging import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
except Exception:  # pragma: no cover
    logger.exception("Failed to install RequestLoggingMiddleware (continuing).")

_upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
_upload_dir.mkdir(parents=True, exist_ok=True)
(_upload_dir / "policies").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")


@app.get("/health", tags=["health"])
def health():
    from database import check_db_connection
    return {"status": "ok" if check_db_connection() else "degraded",
            "service": "HRMS - Unified", "env": settings.APP_ENV, "version": "3.0.0"}


# Core HRMS routers
from app.routes import auth as auth_routes
from app.routes import auth_portal as auth_portal_routes
from app.routes import admin as admin_routes
from app.routes import manager as manager_routes
from app.routes import employee as employee_routes
from app.routes import leave as leave_routes
from app.routes import delegates as delegates_routes
from app.routes import leave_capacity as leave_capacity_routes
from app.routes import encashment as encashment_routes
from app.routes import notifications as notifications_routes
from app.routes import attendance as attendance_routes
from app.routes import timesheet as timesheet_routes
from app.routes import holidays as holidays_routes
from app.routes import search as search_routes
from app.routes import announcements as announcements_routes
from app.routes import policies as policies_routes
from app.routes import secure_uploads as secure_uploads_routes
from app.routes import billing as billing_routes
from app.routes import hr as hr_routes
from app.routes import utilization as utilization_routes
# Payroll routes
from app.routes import finance as finance_routes
from app.routes import payroll_attendance as payroll_att_routes
from app.routes import ff as ff_routes
from app.routes import employee_payroll as emp_payroll_routes
from app.routes import payroll_salary_revision as salary_revision_routes
from app.routes import salary_hike as salary_hike_routes
from app.routes import tax_declaration as tax_declaration_routes

app.include_router(auth_routes.router)
app.include_router(auth_portal_routes.router)   # Portal account management

# Resource-management routers — admin bench + admin/manager surfaces.
# Mounted BEFORE app.routes.admin so that path-precedence on
# /admin/resource-employees etc. is deterministic (these paths are
# disjoint from /admin/employees by design, but the order keeps the
# bench surface authoritative for future overlap).
try:
    from api.Resource_Model import bench_router as _resource_bench_router
    from api.Resource_Model import admin_router as _resource_admin_router
    from api.Resource_Model import manager_router as _resource_manager_router
    app.include_router(_resource_bench_router)
    app.include_router(_resource_admin_router)
    app.include_router(_resource_manager_router)
except Exception:
    logger.exception("Failed to mount Resource_Model routers (continuing).")

try:
    from api.Team_Model import admin_router as _team_admin_router
    from api.Team_Model import manager_router as _team_manager_router
    app.include_router(_team_admin_router)
    app.include_router(_team_manager_router)
except Exception:
    logger.exception("Failed to mount Team_Model routers (continuing).")

app.include_router(admin_routes.router)
app.include_router(manager_routes.router)
app.include_router(employee_routes.router)
app.include_router(leave_routes.router)
app.include_router(delegates_routes.router)
app.include_router(leave_capacity_routes.router)
app.include_router(encashment_routes.router)
app.include_router(notifications_routes.router)
app.include_router(attendance_routes.router)
app.include_router(timesheet_routes.router)
app.include_router(holidays_routes.router)
app.include_router(search_routes.router)
app.include_router(announcements_routes.router)
app.include_router(policies_routes.router)
app.include_router(secure_uploads_routes.router)
app.include_router(secure_uploads_routes.admin_router)
app.include_router(billing_routes.router)
app.include_router(hr_routes.router)
app.include_router(utilization_routes.router)
# Payroll routers
app.include_router(finance_routes.router)
app.include_router(payroll_att_routes.router)
app.include_router(ff_routes.router)
app.include_router(emp_payroll_routes.router)
app.include_router(salary_revision_routes.router)
app.include_router(salary_hike_routes.router)
app.include_router(tax_declaration_routes.router)


# Onboarding HR routers
from api.Department_Model.departments     import router as ob_department_router
from api.Designation_Model.designation    import router as ob_designation_router
from api.Employee_Model.employees         import router as ob_employee_router

app.include_router(ob_department_router)
app.include_router(ob_designation_router)
app.include_router(ob_employee_router)


# Onboarding workflow routers
from api.Onboarding_Model.candidates           import router as ob_candidates_router
from api.Onboarding_Model.offers               import router as ob_offers_router
from api.Onboarding_Model.documents            import router as ob_documents_router
from api.Onboarding_Model.bgv                  import router as ob_bgv_router
from api.Onboarding_Model.bgv_vendor           import router as ob_bgv_vendor_router
from api.Onboarding_Model.candidate_portal     import router as ob_candidate_portal_router
from api.Onboarding_Model.admin_portal         import router as ob_admin_portal_router
from api.Onboarding_Model.auth                 import router as ob_auth_router
from api.Onboarding_Model.onboarding_workflow  import router as ob_workflow_router
from api.Onboarding_Model.onboarding_workflow  import change_password_router as ob_change_pwd_router
from api.Onboarding_Model.convert              import router as ob_convert_router
from api.Onboarding_Model.onboarding_employees import (
    router_convert  as ob_oe_convert_router,
    router_activate as ob_oe_activate_router,
    router_mgmt     as ob_oe_mgmt_router,
)

app.include_router(ob_candidates_router)
app.include_router(ob_offers_router)
app.include_router(ob_documents_router)
app.include_router(ob_bgv_router)
app.include_router(ob_bgv_vendor_router)
app.include_router(ob_candidate_portal_router)
app.include_router(ob_admin_portal_router)
app.include_router(ob_auth_router)
app.include_router(ob_workflow_router)
app.include_router(ob_change_pwd_router)
app.include_router(ob_convert_router)
app.include_router(ob_oe_convert_router)
app.include_router(ob_oe_activate_router)
app.include_router(ob_oe_mgmt_router)
