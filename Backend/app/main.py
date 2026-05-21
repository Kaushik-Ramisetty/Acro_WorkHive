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
    {"id": "LT001", "name": "Sick Leave",         "annual_quota": 12,   "carry_forward_limit": 0,  "is_paid": True,  "applicable_gender": "all"},
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
        logger.info("Master data ready: %d departments, %d designations, %d leave types",
                    session.query(Department).count(), session.query(Designation).count(),
                    session.query(LeaveType).count())


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_onboarding_migrations()
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
        from datetime import datetime, timedelta
        from app.db.session import SessionLocal
        from app.models import SchedulerHealth
        from app.services.leave_engine import process_pending_consumption
        with SessionLocal() as _sh_db:
            row = _sh_db.get(SchedulerHealth, "leave.process_pending_consumption")
            stale = (
                row is None
                or row.last_run_at is None
                or (datetime.utcnow() - row.last_run_at) > timedelta(hours=25)
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

app.include_router(auth_routes.router)

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
