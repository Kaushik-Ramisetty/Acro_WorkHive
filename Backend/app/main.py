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
from dept_desig_migration import sync_master_data


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
        # LOP workflow — flag for Loss-of-Pay leave requests (two-stage manager → HR approval).
        "ALTER TABLE leave_requests ADD COLUMN is_lop INTEGER DEFAULT 0",
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

    # ── Salary hike recommendation field (v19) ───────────────────────────────
    _run_salary_hike_recommendation_migration()

    # ── Bonus Request workflow table (v20) ───────────────────────────────────
    _run_bonus_request_migrations()

    # ── Bonus payment_mode column (v20b) ─────────────────────────────────────
    _run_bonus_payment_mode_migration()

    # ── Off-Cycle Payment tables (v22) ───────────────────────────────────────
    _run_off_cycle_payment_migration()

    # ── PMS Changes: template protection, deadlines, override audit, manual hike (v21) ─
    _run_pms_changes_migrations()


def _run_pms_changes_migrations() -> None:
    """Migration v21: PMS Changes 1, 3, 4, 5 additive columns."""
    from app.utils.db_compat import add_column_if_not_exists

    with engine.connect() as conn:
        # CHANGE 1: from_template flag on assigned KRAs/KPIs/competencies
        add_column_if_not_exists(conn, "pms_assigned_kras", "from_template", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "pms_assigned_kpis", "from_template", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_not_exists(conn, "pms_assigned_competencies", "from_template", "INTEGER NOT NULL DEFAULT 0")

        # CHANGE 3: deadline columns on every phase entity
        add_column_if_not_exists(conn, "pms_goal_assignments", "deadline", "DATETIME")
        add_column_if_not_exists(conn, "pms_mid_cycle_reviews", "deadline", "DATETIME")
        add_column_if_not_exists(conn, "pms_end_cycle_assessments", "deadline", "DATETIME")
        add_column_if_not_exists(conn, "pms_normalization_sessions", "deadline", "DATETIME")

        # CHANGE 4: override audit trail on normalization records
        add_column_if_not_exists(conn, "pms_normalization_records", "override_modified_by", "INTEGER")
        add_column_if_not_exists(conn, "pms_normalization_records", "override_modified_at", "DATETIME")

        # CHANGE 5: manual hike audit fields on normalization records
        add_column_if_not_exists(conn, "pms_normalization_records", "hike_entered_by", "INTEGER")
        add_column_if_not_exists(conn, "pms_normalization_records", "hike_entered_at", "DATETIME")
        add_column_if_not_exists(conn, "pms_normalization_records", "compensation_comments", "TEXT")

        # Auto-lock: lock source discriminator on every lockable phase entity.
        # 'manual' = HR-initiated; 'auto' = system deadline auto-lock.
        add_column_if_not_exists(conn, "pms_goal_assignments",    "lock_type", "VARCHAR(10)")
        add_column_if_not_exists(conn, "pms_mid_cycle_reviews",   "lock_type", "VARCHAR(10)")
        add_column_if_not_exists(conn, "pms_end_cycle_assessments", "lock_type", "VARCHAR(10)")

    logger.info("PMS changes migration v21: complete.")


_DEPARTMENTS = [
    {"id": "DEP001", "name": "HR",                     "parent_department_id": None},
    {"id": "DEP002", "name": "Delivery",               "parent_department_id": None},
    {"id": "DEP003", "name": "Learning & Development", "parent_department_id": None},
    {"id": "DEP004", "name": "Product",                "parent_department_id": None},
    {"id": "DEP005", "name": "Sales",                  "parent_department_id": None},
    {"id": "DEP006", "name": "Operations",             "parent_department_id": None},
    {"id": "DEP007", "name": "Management",             "parent_department_id": None},
    {"id": "DEP008", "name": "Solutioning",            "parent_department_id": None},
]

_DESIGNATIONS = [
    {"id": "D1",  "title": "Delivery Head",                            "level": 10},
    {"id": "D2",  "title": "Delivery Manager",                         "level": 7},
    {"id": "D3",  "title": "Associate Delivery Manager",               "level": 6},
    {"id": "D4",  "title": "Developer",                                "level": 3},
    {"id": "D5",  "title": "Junior Developer",                         "level": 2},
    {"id": "D6",  "title": "Senior Developer",                         "level": 5},
    {"id": "D7",  "title": "Senior AI & Automation Solution Architect", "level": 8},
    {"id": "D8",  "title": "AI Engineer",                              "level": 4},
    {"id": "D9",  "title": "Quality Analyst",                          "level": 3},
    {"id": "D10", "title": "Senior Devops Engineer",                   "level": 6},
    {"id": "D11", "title": "Senior Designer",                          "level": 6},
    {"id": "D12", "title": "Chief AI Officer",                         "level": 12},
    {"id": "D13", "title": "Junior Tester",                            "level": 2},
    {"id": "D14", "title": "Tester",                                   "level": 3},
    {"id": "D15", "title": "Data Analyst",                             "level": 3},
    {"id": "D16", "title": "Tableau Administrator",                    "level": 3},
    {"id": "D17", "title": "Lead Developer",                           "level": 6},
    {"id": "D18", "title": "Team Lead",                                "level": 6},
    {"id": "D19", "title": "Project Manager",                          "level": 7},
    {"id": "D20", "title": "Associate Project Manager",                "level": 6},
    {"id": "D21", "title": "Program Manager",                          "level": 8},
    {"id": "D22", "title": "Business Analyst",                         "level": 4},
    {"id": "D23", "title": "Junior Business Analyst",                  "level": 2},
    {"id": "D24", "title": "Senior Business Analyst",                  "level": 6},
    {"id": "D25", "title": "Solution Architect",                       "level": 8},
    {"id": "D26", "title": "Engagement Manager",                       "level": 7},
    {"id": "D27", "title": "Junior Solution Architect",                "level": 5},
    {"id": "D28", "title": "Senior Solution Architect",                "level": 9},
    {"id": "D29", "title": "Technical Architect",                      "level": 8},
    {"id": "D30", "title": "Junior Technical Architect",               "level": 5},
    {"id": "D31", "title": "Senior Technical Architect",               "level": 9},
    {"id": "D32", "title": "Consultant",                               "level": 4},
    {"id": "D33", "title": "Senior Consultant",                        "level": 6},
    {"id": "D34", "title": "Junior Consultant",                        "level": 2},
    {"id": "D35", "title": "Support Engineer",                         "level": 3},
    {"id": "D36", "title": "Technical Trainer",                        "level": 5},
    {"id": "D37", "title": "Senior Technical Trainer",                 "level": 6},
    {"id": "D38", "title": "Infrastructure Support Engineer",          "level": 3},
    {"id": "D39", "title": "Infrastructure Engineer",                  "level": 4},
    {"id": "D40", "title": "Senior Data Analyst",                      "level": 6},
    {"id": "D41", "title": "Data Scientist",                           "level": 5},
    {"id": "D42", "title": "Senior Data Scientist",                    "level": 6},
    {"id": "D43", "title": "Lead Data Scientist",                      "level": 7},
    {"id": "D44", "title": "Senior Data Engineer",                     "level": 6},
    {"id": "D45", "title": "Data Engineer",                            "level": 4},
    {"id": "D46", "title": "Trainee",                                  "level": 1},
    {"id": "D47", "title": "Intern",                                   "level": 1},
    {"id": "D48", "title": "Product Technical Lead",                   "level": 7},
    {"id": "D49", "title": "Product Manager",                          "level": 7},
    {"id": "D50", "title": "Product Architect",                        "level": 8},
    {"id": "D51", "title": "QA Engineer",                              "level": 3},
    {"id": "D52", "title": "Devops Engineer",                          "level": 4},
    {"id": "D53", "title": "UI/UX Designer",                           "level": 3},
    {"id": "D54", "title": "Senior UI/UX Developer",                   "level": 6},
    {"id": "D55", "title": "AI Designer",                              "level": 4},
    {"id": "D56", "title": "Product Support Manager",                  "level": 7},
    {"id": "D57", "title": "Product Support Engineer",                 "level": 3},
    {"id": "D58", "title": "Sales Head",                               "level": 10},
    {"id": "D59", "title": "Sales Manager",                            "level": 7},
    {"id": "D60", "title": "Account Manager",                          "level": 7},
    {"id": "D61", "title": "Account Executive",                        "level": 4},
    {"id": "D62", "title": "Business Development Manager",             "level": 7},
    {"id": "D63", "title": "Manager-Partnerships & Alliances",         "level": 7},
    {"id": "D64", "title": "Head of Finance",                          "level": 9},
    {"id": "D65", "title": "Finance Manager",                          "level": 7},
    {"id": "D66", "title": "Senior Finance Executive",                 "level": 5},
    {"id": "D67", "title": "HR Head",                                  "level": 10},
    {"id": "D68", "title": "HR & Recruitment Manager",                 "level": 7},
    {"id": "D69", "title": "HR Executive",                             "level": 3},
    {"id": "D70", "title": "Recruitment Manager",                      "level": 7},
    {"id": "D71", "title": "Lead Recruiter",                           "level": 6},
    {"id": "D72", "title": "Junior Recruiter",                         "level": 2},
    {"id": "D73", "title": "Senior Recruiter",                         "level": 5},
    {"id": "D74", "title": "Recruiter",                                "level": 3},
    {"id": "D75", "title": "Talent Acquisition Specialist",            "level": 4},
    {"id": "D76", "title": "IT Manager",                               "level": 7},
    {"id": "D77", "title": "IT Admin",                                 "level": 3},
    {"id": "D78", "title": "Operations Head",                          "level": 10},
    {"id": "D79", "title": "Operations Manager",                       "level": 7},
    {"id": "D80", "title": "Admin",                                    "level": 3},
    {"id": "D81", "title": "Leadership",                               "level": 11},
    {"id": "D82", "title": "Junior Automation Developer",              "level": 2},
    {"id": "D83", "title": "Junior Technical Trainer",                 "level": 3},
    {"id": "D84", "title": "Head of Learning & Development",           "level": 9},
    {"id": "D85", "title": "Tech Lead",                                "level": 6},
    {"id": "D86", "title": "Junior QA Engineer",                       "level": 2},
    {"id": "D87", "title": "Product Delivery Manager",                 "level": 7},
    {"id": "D88", "title": "Head of Sales and Solutioning",            "level": 10},
    {"id": "D89", "title": "Associate Solution Architect",             "level": 5},
    {"id": "D90", "title": "Full Stack Developer",                     "level": 4},
    {"id": "D91", "title": "Junior Finance Executive",                 "level": 2},
    {"id": "D92", "title": "Developer Power Platform",                 "level": 4},
    {"id": "D93", "title": "Automation Edge Developer",                "level": 3},
    {"id": "D94", "title": "Scrum Master",                             "level": 6},
    {"id": "D95", "title": "Inside Sales Executive",                   "level": 3},
    {"id": "D96", "title": "Intern Data Scientist",                    "level": 1},
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


_PMS_PHASE_DEFAULTS = [
    {"phase_key": "goal_setting",  "label": "Goal Setting",         "default_days": 14},
    {"phase_key": "mid_cycle",     "label": "Mid Cycle Review",      "default_days": 14},
    {"phase_key": "end_cycle",     "label": "End Cycle Assessment",  "default_days": 21},
    {"phase_key": "normalization", "label": "Normalization",         "default_days": 14},
    {"phase_key": "compensation",  "label": "Compensation",          "default_days": 7},
]


def _seed_pms_phase_settings() -> None:
    """Idempotent: insert PMS phase deadline defaults if they don't exist yet."""
    from sqlalchemy.orm import Session
    from app.models.pms_settings import PMSPhaseSettings

    with Session(engine) as session:
        for row in _PMS_PHASE_DEFAULTS:
            existing = session.query(PMSPhaseSettings).filter_by(phase_key=row["phase_key"]).first()
            if not existing:
                session.add(PMSPhaseSettings(
                    phase_key=row["phase_key"],
                    label=row["label"],
                    default_days=row["default_days"],
                ))
        session.commit()


def _cleanup_orphaned_pms_rows() -> None:
    """Remove AssignedKRA/KPI/Competency rows whose parent assignment no longer exists.

    SQLite disables FK cascades by default, so prior manual deletions of
    pms_goal_assignments rows left orphaned child rows behind.  Those orphans
    get silently attached to any new assignment that SQLite later assigns the
    same integer id, causing duplicate KRAs in the goal sheet.  This function
    runs at startup and is idempotent.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        deleted_kpis = s.execute(text(
            "DELETE FROM pms_assigned_kpis "
            "WHERE kra_id NOT IN (SELECT id FROM pms_assigned_kras)"
        )).rowcount
        deleted_kras = s.execute(text(
            "DELETE FROM pms_assigned_kras "
            "WHERE assignment_id NOT IN (SELECT id FROM pms_goal_assignments)"
        )).rowcount
        deleted_comps = s.execute(text(
            "DELETE FROM pms_assigned_competencies "
            "WHERE assignment_id NOT IN (SELECT id FROM pms_goal_assignments)"
        )).rowcount
        s.commit()
    if deleted_kras or deleted_kpis or deleted_comps:
        logger.warning(
            "PMS orphan cleanup: removed %d orphaned KRAs, %d KPIs, %d competencies.",
            deleted_kras, deleted_kpis, deleted_comps,
        )


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


_NEW_DEPT_IDS  = {"DEP001", "DEP002", "DEP003", "DEP004", "DEP005", "DEP006", "DEP007", "DEP008"}
_NEW_DESIG_IDS = {f"D{i}" for i in range(1, 97)}


def _run_dept_desig_v2_migration() -> None:
    """Synchronise master data to the official 8 departments and 96 designations."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        try:
            sync_master_data(session, overwrite_department_id=True)
            session.commit()
            logger.info("dept/desig master data synchronised to the official org chart.")
        except Exception:
            session.rollback()
            logger.exception("dept/desig migration failed (continuing).")


def _seed_master_data() -> None:
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.models import Department, Designation, LeaveType, Employee
    from app.models.role import Role

    with Session(engine) as session:
        sync_master_data(session, overwrite_department_id=True)
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

        # Idempotent: ensure known finance/finance_head employees have the correct role.
        # These employees may have been seeded from Excel with role="employee" by default.
        _FINANCE_ROLE_MAP = [
            ("manana.ravikumar@acronotics.com", "finance_head"),
            ("pranav.j@acronotics.com",         "finance"),
        ]
        for _email_lower, _role_name in _FINANCE_ROLE_MAP:
            _role_obj = session.execute(select(Role).where(Role.name == _role_name)).scalar_one_or_none()
            if not _role_obj:
                continue
            _emp = session.execute(
                select(Employee).where(
                    Employee.email.ilike(_email_lower),
                    Employee.is_deleted.is_(False),
                )
            ).scalar_one_or_none()
            if _emp and _emp.role_id != _role_obj.id:
                _emp.role_id = _role_obj.id
                logger.info("Corrected role for %s → %s (id=%d)", _emp.email, _role_name, _role_obj.id)
        session.commit()

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


def _seed_attendance_summary() -> None:
    """Seed monthly_attendance_summary for the previous and current calendar month.

    Runs on every startup but is a no-op whenever the table already has data.
    On a fresh database (after employees are seeded via seed.py) this populates
    two months of realistic, payroll-ready attendance summaries so that the
    Finance → Generate Payroll flow works out of the box.

    Contract
    --------
    - If monthly_attendance_summary has ANY row, return immediately.
    - Covers the previous calendar month and the current calendar month.
    - payable_days = total_working_days - lop_days  (payroll formula).
    - Rows are marked finalized / frozen / passed for immediate payroll use.
    - Attendance pattern is deterministic (based on employee.id % 5) so the
      result is identical on every fresh-DB run — no randomness.
    """
    from datetime import date as _date, timedelta as _td, datetime as _dt
    from sqlalchemy.orm import Session
    from app.models.monthly_attendance_summary import MonthlyAttendanceSummary
    from app.models.employee import Employee

    def _count_working_days(year: int, month: int) -> int:
        """Count Mon-Fri working days in the given calendar month."""
        n, d = 0, _date(year, month, 1)
        while d.month == month:
            if d.weekday() < 5:
                n += 1
            d += _td(days=1)
        return n

    with Session(engine) as session:
        try:
            if session.query(MonthlyAttendanceSummary).count() > 0:
                logger.info("Attendance summary seed: table already has data — skipping.")
                return

            active_emps = (
                session.query(Employee)
                .filter(
                    Employee.is_deleted.is_(False),
                    Employee.employment_status == "active",
                )
                .order_by(Employee.id)
                .all()
            )
            if not active_emps:
                logger.info("Attendance summary seed: no active employees yet — skipping.")
                return

            # Deterministic attendance pattern keyed by (employee.id % 5).
            # Values: (leave_days, lop_days).  Invariant: present = total - leave - lop.
            _PATTERN: dict[int, tuple[int, int]] = {
                0: (0, 0),  # full attendance
                1: (2, 0),  # 2 paid-leave days, no LOP
                2: (1, 0),  # 1 paid-leave day, no LOP
                3: (0, 1),  # 1 LOP day
                4: (1, 1),  # 1 paid-leave + 1 LOP
            }

            today = _date.today()
            first_of_this = _date(today.year, today.month, 1)
            first_of_prev = (first_of_this - _td(days=1)).replace(day=1)
            periods = [
                (first_of_prev.month, first_of_prev.year),
                (today.month, today.year),
            ]
            now = _dt.utcnow()
            inserted = 0

            for emp in active_emps:
                leave_d, lop_d = _PATTERN[emp.id % 5]
                for month, year in periods:
                    total_wd = _count_working_days(year, month)
                    present_d = total_wd - leave_d - lop_d
                    session.add(MonthlyAttendanceSummary(
                        employee_id=emp.id,
                        month=month,
                        year=year,
                        total_working_days=total_wd,
                        present_days=present_d,
                        leave_days=leave_d,
                        lop_days=lop_d,
                        payable_days=float(total_wd - lop_d),
                        approved_timesheet_hours=float(present_d * 8),
                        attendance_status="finalized",
                        timesheet_status="approved",
                        validation_status="passed",
                        issues_count=0,
                        is_ready_for_payroll=True,
                        is_frozen=True,
                        lop_source="Leave Management",
                        lop_status="ready",
                        lop_last_synced_at=now,
                        finalized_at=now,
                    ))
                    inserted += 1

            session.commit()
            logger.info(
                "Attendance summary seed: inserted %d rows for %d employee(s) "
                "(May 2026 + June 2026).",
                inserted,
                len(active_emps),
            )
        except Exception:
            session.rollback()
            logger.exception("Attendance summary seed failed (continuing).")


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
                    lop_source VARCHAR(50) NOT NULL DEFAULT 'Leave Management',
                    lop_status VARCHAR(20) NOT NULL DEFAULT 'ready',
                    lop_last_synced_at DATETIME,
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
            from app.utils.db_compat import add_column_if_not_exists, create_table_if_not_exists

            add_column_if_not_exists(conn, "monthly_attendance_summary", "lop_source", "VARCHAR(50) NOT NULL DEFAULT 'Leave Management'")
            add_column_if_not_exists(conn, "monthly_attendance_summary", "lop_status", "VARCHAR(20) NOT NULL DEFAULT 'ready'")
            add_column_if_not_exists(conn, "monthly_attendance_summary", "lop_last_synced_at", "DATETIME")

            create_table_if_not_exists(conn, "payroll_lop_inputs", column_defs=[
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "leave_request_id VARCHAR(20) NOT NULL REFERENCES leave_requests(id) ON DELETE CASCADE",
                "employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE",
                "month INTEGER NOT NULL",
                "year INTEGER NOT NULL",
                "lop_days FLOAT NOT NULL DEFAULT 0",
                "source VARCHAR(50) NOT NULL DEFAULT 'Leave Management'",
                "status VARCHAR(20) NOT NULL DEFAULT 'ready'",
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
            ], table_constraints=[
                "UNIQUE(leave_request_id, employee_id, month, year)",
            ], indexes=[
                ("ix_pli_leave", "payroll_lop_inputs", "leave_request_id"),
                ("ix_pli_employee_month", "payroll_lop_inputs", "employee_id, month, year"),
            ])
        except Exception as exc:
            logger.warning("Leave LOP payroll input migration skipped: %s", exc)

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
        add_column_if_not_exists(conn, "payroll_runs", "bank_advice_path", "VARCHAR(500)")
        add_column_if_not_exists(conn, "payroll_runs", "bank_advice_generated_at", "DATETIME")
        add_column_if_not_exists(conn, "payroll_runs", "bank_advice_status", "VARCHAR(20)")
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


def _run_salary_hike_recommendation_migration() -> None:
    """Migration v19: Add finance_recommendation column to salary_hike_requests."""
    from app.utils.db_compat import add_column_if_not_exists

    with engine.connect() as conn:
        add_column_if_not_exists(conn, "salary_hike_requests", "finance_recommendation", "VARCHAR(30)")
    logger.info("Salary hike recommendation migration v19: complete.")


def _run_bonus_request_migrations() -> None:
    """Migration v20: Create bonus_requests table for one-time bonus workflow."""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bonus_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id),
                    payroll_month INTEGER NOT NULL,
                    payroll_year  INTEGER NOT NULL,
                    bonus_type    VARCHAR(50) NOT NULL,
                    amount        REAL NOT NULL,
                    reason        TEXT,
                    status        VARCHAR(40) NOT NULL DEFAULT 'pending_finance_review',
                    payroll_adjustment_id INTEGER REFERENCES payroll_adjustments(id) ON DELETE SET NULL,
                    finance_recommendation VARCHAR(20),
                    finance_comment        TEXT,
                    requested_by_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    reviewed_by_id  INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    approved_by_id  INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                    approved_at     DATETIME,
                    rejection_reason TEXT,
                    created_at DATETIME DEFAULT (datetime('now')),
                    updated_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bonus_requests_employee "
                "ON bonus_requests(employee_id, created_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bonus_requests_status "
                "ON bonus_requests(status)"
            ))
            conn.commit()
        except Exception as exc:
            logger.warning("Bonus request migration v20 skipped: %s", exc)
    logger.info("Bonus request migration v20: complete.")


def _run_bonus_payment_mode_migration() -> None:
    """Migration v20b/v20c: bonus_requests columns for payment_mode and future-month handling."""
    from app.utils.db_compat import add_column_if_not_exists

    with engine.connect() as conn:
        add_column_if_not_exists(
            conn, "bonus_requests", "payment_mode",
            "VARCHAR(20) NOT NULL DEFAULT 'regular_payroll'"
        )
        # v20c: payroll_run_id — linked when bonus is materialised during payroll generation
        add_column_if_not_exists(
            conn, "bonus_requests", "payroll_run_id",
            "INTEGER NULL REFERENCES payroll_runs(id) ON DELETE SET NULL"
        )
    logger.info("Bonus payment_mode/payroll_run_id migration v20b-c: complete.")


def _run_off_cycle_payment_migration() -> None:
    """Migration v22: off_cycle_payments and off_cycle_audit_log tables."""
    from app.utils.db_compat import create_table_if_not_exists, add_column_if_not_exists

    with engine.connect() as conn:
        create_table_if_not_exists(conn, "off_cycle_payments", [
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "bonus_request_id INTEGER REFERENCES bonus_requests(id) ON DELETE SET NULL",
            "employee_id INTEGER NOT NULL REFERENCES employees(id)",
            "bonus_type VARCHAR(50) NOT NULL",
            "amount REAL NOT NULL",
            "reason TEXT",
            "payment_status VARCHAR(30) NOT NULL DEFAULT 'approved_off_cycle'",
            "approved_by_id INTEGER REFERENCES employees(id)",
            "approved_date DATETIME",
            "payslip_path VARCHAR(500)",
            "bank_advice_path VARCHAR(500)",
            "paid_by_id INTEGER REFERENCES employees(id)",
            "paid_date DATETIME",
            "remarks TEXT",
            "reference_number VARCHAR(100)",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        ])
        create_table_if_not_exists(conn, "off_cycle_audit_log", [
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "off_cycle_payment_id INTEGER NOT NULL REFERENCES off_cycle_payments(id) ON DELETE CASCADE",
            "actor_id INTEGER REFERENCES employees(id)",
            "action VARCHAR(50) NOT NULL",
            "from_status VARCHAR(30)",
            "to_status VARCHAR(30)",
            "note TEXT",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        ])
    logger.info("Off-cycle payment migration v22: complete.")


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
    _run_dept_desig_v2_migration()
    _seed_master_data()
    _seed_pms_phase_settings()
    _cleanup_orphaned_pms_rows()
    _seed_holidays_pune_2026()
    _backfill_existing_employees_activated()
    _publish_orphaned_drafts()
    _seed_policy_categories_and_legacy_pdfs()
    _seed_attendance_summary()
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
from app.routes import bonus_request as bonus_request_routes
from app.routes import off_cycle_payment as off_cycle_payment_routes
# PMS routes
from app.routes import pms as pms_routes
from app.routes import pms_phase2 as pms_phase2_routes
from app.routes import pms_phase3 as pms_phase3_routes
from app.routes import pms_phase4 as pms_phase4_routes
from app.routes import pms_phase5 as pms_phase5_routes

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
app.include_router(bonus_request_routes.router)
app.include_router(off_cycle_payment_routes.router)
# PMS routers — ordered so more-specific prefixes come before generic ones.
app.include_router(pms_routes.router)           # /pms
app.include_router(pms_phase2_routes.router)    # /pms/mid-cycle
app.include_router(pms_phase3_routes.router)    # /pms/end-cycle
app.include_router(pms_phase4_routes.router)    # /pms/normalization
app.include_router(pms_phase5_routes.router)    # /pms/compensation


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
