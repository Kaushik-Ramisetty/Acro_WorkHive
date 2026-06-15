"""Seed the database from Employees-updated.xlsx (v2 schema).

v2 adds:
  - 4 new employee columns: location, Nationality, Marital_status, time_zone
  - 3 new sheets: leave_types, leave_balances, leave_requests

The seed is upsert-style and **non-destructive** by default. It now updates
EVERY column on existing employees (in v1 it only synced 5 fields, which is
why edits to phone/DOB/address etc. weren't reflected in the DB).

Usage:
    python seed.py                              # auto-discovers the xlsx
    python seed.py path/to/Employees-updated.xlsx
"""
import sys
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from dept_desig_migration import normalize_department_id, sync_master_data
from app.models import (
    Attendance, Department, Designation, Employee, Role,
    LeaveType, LeaveBalance, LeaveRequest,
    # hrms_schema_complete.xlsx — additive tables
    Shift, AttendancePolicy, OvertimeRule, EmployeeShift, Holiday,
    AttendanceLog, ValidationError, AttendanceRecord, AttendanceException,
    RegularizationRequest, RegularizationAttachment, OvertimeRecord,
    AttendanceReport, PayrollAttendanceSummary,
    AuditLog, Notification,
    Project, Task, Timesheet, TimesheetEntry, TimesheetPayrollSync,
    User,
)


MANAGER_DESIGNATIONS = {
    # Delivery leadership
    "Delivery Head", "Delivery Manager", "Associate Delivery Manager",
    "Product Delivery Manager",
    # Engineering / technical leads
    "Tech Lead", "Team Lead", "Lead Developer",
    "Senior AI & Automation Solution Architect",
    "Senior Solution Architect", "Technical Architect", "Senior Technical Architect",
    "Solution Architect", "Product Technical Lead",
    # Project / programme management
    "Project Manager", "Associate Project Manager", "Program Manager",
    "Scrum Master",
    # Product
    "Product Manager", "Product Architect", "Product Support Manager",
    # Sales & partnerships
    "Sales Head", "Sales Manager", "Account Manager",
    "Business Development Manager", "Manager-Partnerships & Alliances",
    "Head of Sales and Solutioning", "Engagement Manager",
    # Finance
    "Head of Finance", "Finance Manager",
    # HR & recruitment
    "HR & Recruitment Manager", "Recruitment Manager", "Lead Recruiter",
    # IT & operations
    "IT Manager", "Operations Head", "Operations Manager",
    # Learning & development
    "Head of Learning & Development",
    # Data / analytics
    "Lead Data Scientist",
}
ADMIN_DESIGNATIONS = {"HR Head", "Leadership"}
ADMIN_DEPARTMENTS = {"DEP003"}  # HR


def derive_role(designation_title: Optional[str], department_id: Optional[str], default: str = "employee") -> str:
    title = (designation_title or "").strip()
    if title in ADMIN_DESIGNATIONS or department_id in ADMIN_DEPARTMENTS:
        return "admin"
    if title in MANAGER_DESIGNATIONS:
        return "manager"
    return default


def to_date(v):
    """Coerce to datetime.date. Accepts date / datetime / 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS'."""
    from datetime import date as _date
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    s = str(v).strip()
    if not s:
        return None
    # Try common ISO forms.
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Last-ditch — drop a time suffix and re-try.
    if " " in s:
        try:
            return datetime.strptime(s.split(" ")[0], "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def to_dt(v):
    """Coerce to datetime. Accepts datetime / 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD'."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def to_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def to_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None


def to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def to_time(v):
    """Coerce excel time / 'HH:MM:SS' / datetime.time -> datetime.time."""
    if v is None or v == "":
        return None
    from datetime import time as _time
    if isinstance(v, _time):
        return v
    if isinstance(v, datetime):
        return v.time()
    s = str(v).strip()
    if not s:
        return None
    # accept 'HH:MM' or 'HH:MM:SS'
    parts = s.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(parts[2]) if len(parts) > 2 else 0
        return _time(h, m, sec)
    except (ValueError, IndexError):
        return None


def to_bool(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "t", "yes", "y"}


def upsert_role(db: Session, name: str, description: str = "") -> Role:
    role = db.query(Role).filter(Role.name == name).one_or_none()
    if not role:
        role = Role(name=name, description=description)
        db.add(role)
        db.flush()
    return role


def auto_upgrade_schema():
    """Add any model columns that are missing from the existing SQLite tables.

    SQLAlchemy's create_all() only creates missing TABLES, not missing COLUMNS.
    For SQLite this means new fields added to existing models go ignored unless
    you wipe the DB or run a migration. This helper inspects every mapped table
    and issues `ALTER TABLE ... ADD COLUMN` for any column the model declares
    that the on-disk table doesn't have yet.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() will create it from scratch
            existing_cols = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                # Type-aware NOT NULL default. SQLite stores ANY in declared columns
                # so a bad default once made it onto disk will linger; we use 0 for
                # numeric, '' for text/blob, FALSE for boolean.
                if col.nullable:
                    nullable = ""
                else:
                    t = col_type.upper()
                    if any(k in t for k in ("INT", "REAL", "FLOAT", "NUMERIC", "DECIMAL")):
                        nullable = " NOT NULL DEFAULT 0"
                    elif "BOOL" in t:
                        nullable = " NOT NULL DEFAULT 0"
                    else:
                        nullable = " NOT NULL DEFAULT ''"
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}{nullable}'))
                print(f"  + ALTER {table.name} ADD COLUMN {col.name} {col_type}")


def backfill_legacy_chain_fields():
    """One-shot fix for leave_requests rows that pre-date the Phase 1 schema
    (column added later by auto_upgrade_schema, but value never populated).

    For every pending / cancel_pending row whose next_approver_role is NULL
    or empty, infer the stage from the employee's reporting chain. Idempotent
    -- safe to run on every seed.
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        # Run the backfill via a single SQL statement so it's atomic.
        result = conn.execute(text("""
            UPDATE leave_requests
            SET next_approver_role = CASE
                WHEN (SELECT reporting_manager_id FROM employees WHERE id = leave_requests.employee_id) IS NOT NULL
                    THEN 'manager'
                ELSE 'hr'
            END
            WHERE status IN ('pending', 'cancel_pending')
              AND (next_approver_role IS NULL OR next_approver_role = '')
        """))
        n = result.rowcount or 0
    if n:
        print(f"  + Backfilled next_approver_role for {n} legacy leave_requests row(s)")
    return n


def find_xlsx(arg: Optional[str]) -> Optional[Path]:
    candidates = []
    here = Path.cwd()
    backend_root = Path(__file__).resolve().parent
    project_root = backend_root.parent

    if arg:
        candidates.append(Path(arg).expanduser())
    candidates.extend([
        # New full-schema workbook (preferred)
        backend_root / "hrms_schema_complete.xlsx",
        here / "hrms_schema_complete.xlsx",
        project_root / "hrms_schema_complete.xlsx",
        backend_root / "data" / "hrms_schema_complete.xlsx",
        # Legacy employees-only workbook (still supported for backward compat)
        backend_root / "Employees-updated.xlsx",
        here / "Employees-updated.xlsx",
        project_root / "Employees-updated.xlsx",
        backend_root / "data" / "Employees-updated.xlsx",
    ])
    if project_root.exists():
        candidates.extend(sorted(project_root.glob("hrms_schema_complete*.xlsx")))
        candidates.extend(sorted(project_root.glob("Employees*.xlsx")))

    seen: set[Path] = set()
    for p in candidates:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if rp.is_file():
            return rp
    return None


def find_backup_db(arg: Optional[str]) -> Optional[Path]:
    candidates = []
    backend_root = Path(__file__).resolve().parent
    project_root = backend_root.parent

    if arg:
        candidates.append(Path(arg).expanduser())

    import os
    backup_env = os.getenv("HRMS_BACKUP_DB_PATH")
    if backup_env:
        candidates.append(Path(backup_env).expanduser())

    candidates.extend([
        project_root / "hrms_integrated_v4_backup" / "Backend" / "hrms.db",
        project_root.parent / "hrms_integrated_v4_backup" / "Backend" / "hrms.db",
    ])

    seen: set[Path] = set()
    for p in candidates:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if rp.is_file():
            return rp
    return None


def _normalize_user_role(value: Optional[str]) -> str:
    clean = (str(value or "").strip().upper() or "EMPLOYEE")
    aliases = {
        "ADMINISTRATOR": "ADMIN",
        "CANDIDATES": "CANDIDATE",
    }
    clean = aliases.get(clean, clean)
    return clean if clean in {"ADMIN", "HR", "MANAGER", "EMPLOYEE", "CANDIDATE"} else "EMPLOYEE"


def _clean_nullable_fk(value):
    if value in (None, "", "NULL", "null", "None"):
        return None
    return value


def _next_prefixed_id(db: Session, model, prefix: str, width: int) -> str:
    max_num = 0
    for raw in db.query(model.id).all():
        value = raw[0] if not isinstance(raw, str) else raw
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        suffix = value[len(prefix):]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"{prefix}{max_num + 1:0{width}d}"


def _import_backup_db_data(db: Session, backup_db_path: Path) -> dict[str, tuple[int, int, int]]:
    """Import compatible demo data from the backup SQLite DB.

    The main integrated project's schema remains authoritative. We only merge
    compatible employee, attendance, timesheet, and legacy user data without
    replacing the current DB wholesale.
    """
    from sqlalchemy import text

    counts: dict[str, tuple[int, int, int]] = {}
    src = sqlite3.connect(str(backup_db_path))
    src.row_factory = sqlite3.Row

    def _record(name: str, inserted: int, updated: int, skipped: int) -> None:
        if inserted or updated or skipped:
            counts[name] = (inserted, updated, skipped)

    def _rows(query: str):
        return src.execute(query).fetchall()

    attendance_id_map: dict[str, str] = {}
    timesheet_id_map: dict[str, str] = {}

    try:
        emp_inserted = emp_updated = emp_skipped = 0
        for row in _rows("SELECT * FROM employees ORDER BY id"):
            emp_id = to_int(row["id"])
            if emp_id is None:
                emp_skipped += 1
                continue
            existing = db.get(Employee, emp_id)
            if existing is None:
                db.add(Employee(
                    id=emp_id,
                    employee_code=to_str(row["employee_code"]),
                    first_name=to_str(row["first_name"]) or "",
                    last_name=to_str(row["last_name"]),
                    email=to_str(row["email"]),
                    official_email=to_str(row["official_email"]),
                    employment_status=(to_str(row["employment_status"]) or "active").lower(),
                    role_id=to_int(row["role_id"]),
                    password_hash=to_str(row["password_hash"]),
                    is_activated=bool(row["is_activated"] if row["is_activated"] is not None else True),
                    force_password_change=bool(row["force_password_change"] if row["force_password_change"] is not None else False),
                    is_deleted=bool(row["is_deleted"] if row["is_deleted"] is not None else False),
                    employee_type=to_str(row["employee_type"]),
                    is_tm=bool(row["is_tm"] or False),
                    client_manager_name=to_str(row["client_manager_name"]),
                    client_manager_email=to_str(row["client_manager_email"]),
                ))
                emp_inserted += 1
                continue

            touched = False
            for field in ("employment_status", "official_email", "employee_type", "client_manager_name", "client_manager_email"):
                new_value = row[field]
                if new_value is None:
                    continue
                if getattr(existing, field) != new_value:
                    setattr(existing, field, new_value)
                    touched = True
            new_is_tm = bool(row["is_tm"] or False)
            if bool(existing.is_tm or False) != new_is_tm:
                existing.is_tm = new_is_tm
                touched = True
            if not getattr(existing, "password_hash", None) and row["password_hash"]:
                existing.password_hash = row["password_hash"]
                touched = True
            if touched:
                emp_updated += 1
            else:
                emp_skipped += 1
        db.flush()
        _record("backup_employees", emp_inserted, emp_updated, emp_skipped)

        user_inserted = user_updated = user_skipped = 0
        for row in _rows("SELECT * FROM users ORDER BY id"):
            employee_id = to_int(_clean_nullable_fk(row["employee_id"]))
            candidate_id = to_int(_clean_nullable_fk(row["candidate_id"]))
            if employee_id is not None and db.get(Employee, employee_id) is None:
                user_skipped += 1
                continue
            if candidate_id is not None:
                candidate_exists = db.execute(
                    text("SELECT 1 FROM candidates WHERE id = :candidate_id"),
                    {"candidate_id": candidate_id},
                ).fetchone()
                if candidate_exists is None:
                    user_skipped += 1
                    continue
            existing = db.get(User, to_int(row["id"]))
            if existing is None:
                existing = db.query(User).filter(User.email == row["email"]).one_or_none()
            if existing is None:
                db.add(User(
                    id=to_int(row["id"]),
                    email=to_str(row["email"]) or "",
                    password_hash=to_str(row["password_hash"]) or "",
                    role=_normalize_user_role(row["role"]),
                    is_active=bool(row["is_active"] if row["is_active"] is not None else True),
                    employee_id=employee_id,
                    candidate_id=candidate_id,
                    last_login=to_dt(row["last_login"]),
                ))
                user_inserted += 1
            else:
                existing.email = to_str(row["email"]) or existing.email
                existing.password_hash = to_str(row["password_hash"]) or existing.password_hash
                existing.role = _normalize_user_role(row["role"])
                existing.is_active = bool(row["is_active"] if row["is_active"] is not None else True)
                existing.employee_id = employee_id
                existing.candidate_id = candidate_id
                existing.last_login = to_dt(row["last_login"])
                user_updated += 1
        _record("backup_users", user_inserted, user_updated, user_skipped)

        ar_inserted = ar_updated = ar_skipped = 0
        for row in _rows("SELECT * FROM attendance_records ORDER BY date, employee_id, id"):
            employee_id = to_int(row["employee_id"])
            if employee_id is None or db.get(Employee, employee_id) is None:
                ar_skipped += 1
                continue
            natural = (employee_id, to_date(row["date"]))
            existing = db.query(AttendanceRecord).filter(
                AttendanceRecord.employee_id == natural[0],
                AttendanceRecord.date == natural[1],
            ).one_or_none()
            target_id = to_str(row["id"]) or _next_prefixed_id(db, AttendanceRecord, "AR", 6)
            if existing is None and db.get(AttendanceRecord, target_id) is not None:
                target_id = _next_prefixed_id(db, AttendanceRecord, "AR", 6)
            attendance_id_map[to_str(row["id"]) or target_id] = existing.id if existing is not None else target_id
            if existing is None:
                db.add(AttendanceRecord(
                    id=target_id,
                    employee_id=employee_id,
                    date=natural[1],
                    shift_id=to_str(row["shift_id"]),
                    check_in_time=to_time(row["check_in_time"]),
                    check_out_time=to_time(row["check_out_time"]),
                    working_hours=to_float(row["working_hours"]),
                    status=(to_str(row["status"]) or "absent").lower(),
                    late_minutes=to_int(row["late_minutes"]),
                    early_checkout_mins=to_int(row["early_checkout_mins"]),
                    overtime_hours=to_float(row["overtime_hours"]),
                    leave_request_id=to_str(row["leave_request_id"]),
                    is_regularized=bool(row["is_regularized"] or False),
                    lop_applied=bool(row["lop_applied"] or False),
                    lop_type=to_str(row["lop_type"]),
                ))
                db.flush()
                ar_inserted += 1
            else:
                existing.shift_id = to_str(row["shift_id"])
                existing.check_in_time = to_time(row["check_in_time"])
                existing.check_out_time = to_time(row["check_out_time"])
                existing.working_hours = to_float(row["working_hours"])
                existing.status = (to_str(row["status"]) or existing.status or "absent").lower()
                existing.late_minutes = to_int(row["late_minutes"])
                existing.early_checkout_mins = to_int(row["early_checkout_mins"])
                existing.overtime_hours = to_float(row["overtime_hours"])
                existing.leave_request_id = to_str(row["leave_request_id"])
                existing.is_regularized = bool(row["is_regularized"] or False)
                existing.lop_applied = bool(row["lop_applied"] or False)
                existing.lop_type = to_str(row["lop_type"])
                ar_updated += 1
        db.flush()
        _record("backup_attendance_records", ar_inserted, ar_updated, ar_skipped)

        ts_inserted = ts_updated = ts_skipped = 0
        for row in _rows("SELECT * FROM timesheets ORDER BY period_start, employee_id, id"):
            employee_id = to_int(row["employee_id"])
            if employee_id is None or db.get(Employee, employee_id) is None:
                ts_skipped += 1
                continue
            natural = (employee_id, to_date(row["period_start"]), to_date(row["period_end"]))
            existing = db.query(Timesheet).filter(
                Timesheet.employee_id == natural[0],
                Timesheet.period_start == natural[1],
                Timesheet.period_end == natural[2],
            ).one_or_none()
            target_id = to_str(row["id"]) or _next_prefixed_id(db, Timesheet, "TS", 6)
            if existing is None and db.get(Timesheet, target_id) is not None:
                target_id = _next_prefixed_id(db, Timesheet, "TS", 6)
            timesheet_id_map[to_str(row["id"]) or target_id] = existing.id if existing is not None else target_id
            if existing is None:
                db.add(Timesheet(
                    id=target_id,
                    employee_id=employee_id,
                    period_type=to_str(row["period_type"]),
                    period_start=natural[1],
                    period_end=natural[2],
                    total_logged_hours=to_float(row["total_logged_hours"]),
                    status=to_str(row["status"]),
                    submitted_at=to_dt(row["submitted_at"]),
                    reviewed_by=to_int(row["reviewed_by"]),
                    review_comment=to_str(row["review_comment"]),
                    reviewed_at=to_dt(row["reviewed_at"]),
                    is_locked=bool(row["is_locked"] or False),
                    locked_at=to_dt(row["locked_at"]),
                    client_manager_id=to_int(_clean_nullable_fk(row["client_manager_id"])),
                    client_manager_name=to_str(row["client_manager_name"]),
                    client_manager_email=to_str(row["client_manager_email"]),
                    client_token=to_str(row["client_token"]),
                    client_token_expires_at=to_dt(row["client_token_expires_at"]),
                    client_email_sent_at=to_dt(row["client_email_sent_at"]),
                    client_email_status=to_str(row["client_email_status"]),
                    client_approved_at=to_dt(row["client_approved_at"]),
                    client_rejected_at=to_dt(row["client_rejected_at"]),
                    client_review_comment=to_str(row["client_review_comment"]),
                    reminder_count=to_int(row["reminder_count"]) or 0,
                    has_mismatch=bool(row["has_mismatch"] or False),
                ))
                db.flush()
                ts_inserted += 1
            else:
                existing.period_type = to_str(row["period_type"])
                existing.total_logged_hours = to_float(row["total_logged_hours"])
                existing.status = to_str(row["status"])
                existing.submitted_at = to_dt(row["submitted_at"])
                existing.reviewed_by = to_int(row["reviewed_by"])
                existing.review_comment = to_str(row["review_comment"])
                existing.reviewed_at = to_dt(row["reviewed_at"])
                existing.is_locked = bool(row["is_locked"] or False)
                existing.locked_at = to_dt(row["locked_at"])
                existing.client_manager_id = to_int(_clean_nullable_fk(row["client_manager_id"]))
                existing.client_manager_name = to_str(row["client_manager_name"])
                existing.client_manager_email = to_str(row["client_manager_email"])
                existing.client_token = to_str(row["client_token"])
                existing.client_token_expires_at = to_dt(row["client_token_expires_at"])
                existing.client_email_sent_at = to_dt(row["client_email_sent_at"])
                existing.client_email_status = to_str(row["client_email_status"])
                existing.client_approved_at = to_dt(row["client_approved_at"])
                existing.client_rejected_at = to_dt(row["client_rejected_at"])
                existing.client_review_comment = to_str(row["client_review_comment"])
                existing.reminder_count = to_int(row["reminder_count"]) or 0
                existing.has_mismatch = bool(row["has_mismatch"] or False)
                ts_updated += 1
        db.flush()
        _record("backup_timesheets", ts_inserted, ts_updated, ts_skipped)

        te_inserted = te_updated = te_skipped = 0
        for row in _rows("SELECT * FROM timesheet_entries ORDER BY timesheet_id, entry_date, id"):
            source_ts_id = to_str(row["timesheet_id"])
            if not source_ts_id or source_ts_id not in timesheet_id_map:
                te_skipped += 1
                continue
            employee_id = to_int(row["employee_id"])
            if employee_id is None or db.get(Employee, employee_id) is None:
                te_skipped += 1
                continue
            mapped_ts_id = timesheet_id_map[source_ts_id]
            attendance_record_id = attendance_id_map.get(to_str(row["attendance_record_id"]) or "")
            existing = db.get(TimesheetEntry, to_str(row["id"]))
            if existing is None:
                existing = db.query(TimesheetEntry).filter(
                    TimesheetEntry.timesheet_id == mapped_ts_id,
                    TimesheetEntry.entry_date == to_date(row["entry_date"]),
                    TimesheetEntry.project_id == to_str(row["project_id"]),
                    TimesheetEntry.task_id == to_str(row["task_id"]),
                ).one_or_none()
            target_id = to_str(row["id"]) or _next_prefixed_id(db, TimesheetEntry, "TE", 7)
            if existing is None and db.get(TimesheetEntry, target_id) is not None:
                target_id = _next_prefixed_id(db, TimesheetEntry, "TE", 7)
            if existing is None:
                db.add(TimesheetEntry(
                    id=target_id,
                    timesheet_id=mapped_ts_id,
                    employee_id=employee_id,
                    entry_date=to_date(row["entry_date"]),
                    project_id=to_str(row["project_id"]),
                    task_id=to_str(row["task_id"]),
                    logged_hours=to_float(row["logged_hours"]),
                    is_billable=bool(row["is_billable"] or False),
                    source=to_str(row["source"]),
                    description=to_str(row["description"]),
                    is_manual_entry=bool(row["is_manual_entry"] or False),
                    attendance_record_id=attendance_record_id,
                ))
                db.flush()
                te_inserted += 1
            else:
                existing.timesheet_id = mapped_ts_id
                existing.employee_id = employee_id
                existing.entry_date = to_date(row["entry_date"])
                existing.project_id = to_str(row["project_id"])
                existing.task_id = to_str(row["task_id"])
                existing.logged_hours = to_float(row["logged_hours"])
                existing.is_billable = bool(row["is_billable"] or False)
                existing.source = to_str(row["source"])
                existing.description = to_str(row["description"])
                existing.is_manual_entry = bool(row["is_manual_entry"] or False)
                existing.attendance_record_id = attendance_record_id
                te_updated += 1
        _record("backup_timesheet_entries", te_inserted, te_updated, te_skipped)
    finally:
        src.close()

    return counts


def _parse_args(argv: list[str]) -> tuple[Optional[str], Optional[str]]:
    xlsx_arg = None
    backup_arg = None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--backup-db" and i + 1 < len(argv):
            backup_arg = argv[i + 1]
            i += 2
            continue
        if token.startswith("--backup-db="):
            backup_arg = token.split("=", 1)[1]
            i += 1
            continue
        if xlsx_arg is None:
            xlsx_arg = token
        i += 1
    return xlsx_arg, backup_arg


def _row_to_employee_fields(row, designations_by_id, roles, password_existing=None):
    """Pad short rows and return (kwargs, role) ready for inserting/updating an Employee."""
    cells = (list(row) + [None] * 35)[:35]
    (
        eid, employee_code, entra_object_id, first_name, last_name, email, phone, secondary_phone,
        date_of_birth, date_of_joining, date_of_exit, designation_id, reporting_manager_id, employment_status,
        gender, aadhaar, pan, bank_acc, bank_ifsc, photo_url, blood_group, em_name, em_phone,
        is_deleted, created_at, updated_at, created_by, updated_by, deleted_at, department_id, password,
        location, nationality, marital_status, time_zone,
    ) = cells

    designation_id = to_str(designation_id)
    department_id  = normalize_department_id(to_str(department_id))
    designation_title = (
        designations_by_id[designation_id].title
        if designation_id and designation_id in designations_by_id else None
    )
    role = roles[derive_role(designation_title, department_id)]

    if password:
        password_hash = hash_password(str(password))
    else:
        password_hash = password_existing or hash_password("Welcome@2024")

    return {
        "employee_code": to_str(employee_code),
        "entra_object_id": to_str(entra_object_id),
        "first_name": (to_str(first_name) or ""),
        "last_name": to_str(last_name),
        "email": to_str(email),
        "phone": to_str(phone),
        "secondary_phone": to_str(secondary_phone),
        "date_of_birth": to_date(date_of_birth),
        "date_of_joining": to_date(date_of_joining),
        "date_of_exit": to_date(date_of_exit),
        "designation_id": designation_id,
        "department_id": department_id,
        "reporting_manager_id": to_int(reporting_manager_id),
        "employment_status": (to_str(employment_status) or "active").lower(),
        "gender": to_str(gender),
        "aadhaar_encrypted": to_str(aadhaar),
        "pan_encrypted": to_str(pan),
        "bank_account_encrypted": to_str(bank_acc),
        "bank_ifsc": to_str(bank_ifsc),
        "profile_photo_url": to_str(photo_url),
        "blood_group": to_str(blood_group),
        "emergency_contact_name": to_str(em_name),
        "emergency_contact_phone": to_str(em_phone),
        "is_deleted": bool(to_bool(is_deleted) or False),
        "deleted_at": to_dt(deleted_at),
        "location": to_str(location),
        "nationality": to_str(nationality),
        "marital_status": to_str(marital_status),
        "time_zone": to_str(time_zone),
        "password_hash": password_hash,
        "role_id": role.id,
    }, role


def _has_sheet(wb, name: str) -> bool:
    try:
        return name in wb.sheetnames
    except Exception:
        return False


def _data_rows(wb, name: str):
    """Yield value-only data rows from a sheet, skipping title/header rows.

    The legacy Employees-updated.xlsx puts column headers on row 1 (so data
    starts at min_row=2). The newer hrms_schema_complete.xlsx puts a banner
    like "📋 employees" on row 1, the real headers on row 2, and the data
    on rows 3+. We detect this by inspecting the first cell of row 1 — if
    it starts with the sheet name (or contains a non-ASCII glyph), data
    starts on row 3; otherwise on row 2.
    """
    if name not in wb.sheetnames:
        return
    sh = wb[name]
    rows = list(sh.iter_rows(values_only=True))
    if not rows:
        return
    first = rows[0]
    first_cell = str(first[0]) if first and first[0] is not None else ""
    looks_like_banner = (
        first_cell.startswith(name)
        or any(ord(c) > 127 for c in first_cell)  # emoji / unicode
        or (len(first) > 1 and (first[1] is None or first[1] == ""))
    )
    skip = 2 if looks_like_banner else 1
    for row in rows[skip:]:
        if row is None:
            continue
        # drop trailing all-None tuples from openpyxl
        if all(c is None or c == "" for c in row):
            continue
        yield row


def _upsert_pk(db: Session, model, pk: str | int, fields: dict):
    """Generic 'INSERT-or-UPDATE by primary key' helper. Returns (obj, was_new)."""
    obj = db.get(model, pk)
    if obj is None:
        # Identify the PK column name from the model's mapper.
        pk_col = list(model.__table__.primary_key.columns)[0].name
        kwargs = {pk_col: pk, **fields}
        obj = model(**kwargs)
        db.add(obj)
        return obj, True
    for k, v in fields.items():
        setattr(obj, k, v)
    return obj, False


def _seed_new_schema_sheets(db: Session, wb) -> dict[str, tuple[int, int]]:
    """Load all hrms_schema_complete.xlsx additive sheets.

    Each loader is a no-op when the sheet is missing, so the same code
    works against the legacy Employees-updated.xlsx workbook too.
    Returns a dict of sheet_name -> (inserted, updated) for the summary.
    """
    counts: dict[str, tuple[int, int]] = {}

    def _do(sheet, model, mapper):
        ins = upd = 0
        for row in _data_rows(wb, sheet):
            try:
                pk, fields = mapper(row)
            except Exception:
                continue
            if pk is None or pk == "":
                continue
            _, was_new = _upsert_pk(db, model, pk, fields)
            if was_new: ins += 1
            else:       upd += 1
        if ins or upd:
            counts[sheet] = (ins, upd)

    # ── FK-safe lookup helpers ─────────────────────────────────────────────────
    # _fk(Model) builds a guard function: returns the PK value when the parent
    # row exists in the current session/DB, or None when it is absent.
    #
    # Usage pattern:
    #   - nullable FK column  → store None directly (constraint satisfied)
    #   - NOT NULL FK column  → mapper returns (None, {}) so _do() skips the row
    #
    # This prevents every SQLite IntegrityError caused by dangling FK values
    # from the xlsx (rows that reference parents not yet committed, parents that
    # were never seeded, or parents in sheets the xlsx happens to omit).
    def _fk(model, cast=to_str):
        def guard(v):
            pk = cast(v)
            if pk is None:
                return None
            return pk if db.get(model, pk) else None
        return guard

    emp_id        = _fk(Employee, to_int)          # employees.id              (int PK)
    leave_req_id  = _fk(LeaveRequest)              # leave_requests.id         (never seeded)
    shift_id_safe = _fk(Shift)                     # shifts.id
    att_log_id    = _fk(AttendanceLog)             # attendance_logs.id
    att_rec_id    = _fk(AttendanceRecord)          # attendance_records.id
    att_pol_id    = _fk(AttendancePolicy)          # attendance_policies.id
    reg_req_id    = _fk(RegularizationRequest)     # regularization_requests.id
    dept_id_safe  = _fk(Department)                # departments.id
    proj_id       = _fk(Project)                   # projects.id
    task_id_safe  = _fk(Task)                      # tasks.id
    ts_id         = _fk(Timesheet)                 # timesheets.id
    pas_id        = _fk(PayrollAttendanceSummary)  # payroll_attendance_summary.id
    # ──────────────────────────────────────────────────────────────────────────

    # ── shifts ─────────────────────────────────────────────────────
    def _m_shift(r):
        c = (list(r) + [None] * 11)[:11]
        return to_str(c[0]), dict(
            name=to_str(c[1]) or "",
            start_time=to_time(c[2]),
            end_time=to_time(c[3]),
            grace_period_mins=to_int(c[4]) or 0,
            break_duration_mins=to_int(c[5]) or 0,
            weekly_off_days=to_str(c[6]),
            is_night_shift=bool(to_bool(c[7]) or False),
            is_flexible=bool(to_bool(c[8]) or False),
        )
    _do("shifts", Shift, _m_shift)

    # ── attendance_policies ────────────────────────────────────────
    def _m_pol(r):
        c = (list(r) + [None] * 13)[:13]
        sid = shift_id_safe(c[1])
        if sid is None:
            return None, {}
        return to_str(c[0]), dict(
            shift_id=sid,
            policy_name=to_str(c[2]) or "",
            min_working_hours_full_day=to_float(c[3]),
            min_working_hours_half_day=to_float(c[4]),
            overtime_threshold_hours=to_float(c[5]),
            short_day_cutoff_hours=to_float(c[6]),
            late_deduction_after_mins=to_int(c[7]),
            absent_after_missing_mins=to_int(c[8]),
            weekly_overtime_threshold=to_float(c[9]),
            is_active=bool(to_bool(c[10]) if c[10] is not None else True),
        )
    _do("attendance_policies", AttendancePolicy, _m_pol)

    # ── overtime_rules ─────────────────────────────────────────────
    def _m_otr(r):
        c = (list(r) + [None] * 8)[:8]
        pid = att_pol_id(c[1])
        if pid is None:
            return None, {}
        return to_str(c[0]), dict(
            policy_id=pid,
            day_type=to_str(c[2]) or "weekday",
            rate_multiplier=to_float(c[3]) or 1.0,
            min_overtime_hours=to_float(c[4]),
            max_overtime_hours_per_day=to_float(c[5]),
            comp_leave_eligible=bool(to_bool(c[6]) or False),
        )
    _do("overtime_rules", OvertimeRule, _m_otr)

    # ── employee_shifts ────────────────────────────────────────────
    def _m_es(r):
        c = (list(r) + [None] * 7)[:7]
        eid = emp_id(c[1])
        sid = shift_id_safe(c[2])
        if eid is None or sid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            shift_id=sid,
            effective_from=to_date(c[3]),
            effective_to=to_date(c[4]),
        )
    _do("employee_shifts", EmployeeShift, _m_es)

    # ── holidays ───────────────────────────────────────────────────
    def _m_hol(r):
        c = (list(r) + [None] * 7)[:7]
        return to_str(c[0]), dict(
            name=to_str(c[1]) or "",
            date=to_date(c[2]),
            holiday_type=to_str(c[3]),
            applicable_locations=to_str(c[4]),
            year=to_int(c[5]),
        )
    _do("holidays", Holiday, _m_hol)

    db.flush()  # so attendance_logs can FK-reference shifts/employees

    # ── attendance_logs ────────────────────────────────────────────
    def _m_alog(r):
        c = (list(r) + [None] * 12)[:12]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            punch_type=to_str(c[2]),
            punch_timestamp=to_dt(c[3]),
            device_info=to_str(c[4]),
            location_lat=to_float(c[5]),
            location_lng=to_float(c[6]),
            source=to_str(c[7]),
            is_valid=bool(to_bool(c[8]) if c[8] is not None else True),
            validation_error=to_str(c[9]),
            validation_rule=to_str(c[11]),
        )
    _do("attendance_logs", AttendanceLog, _m_alog)

    db.flush()

    # ── validation_errors ──────────────────────────────────────────
    def _m_ve(r):
        c = (list(r) + [None] * 8)[:8]
        return to_str(c[0]), dict(
            attendance_log_id=att_log_id(c[1]),
            employee_id=emp_id(c[2]),
            punch_timestamp=to_dt(c[3]),
            validation_rule=to_str(c[4]),
            rule_description=to_str(c[5]),
            severity=to_str(c[6]),
        )
    _do("validation_errors", ValidationError, _m_ve)

    # ── attendance_records ────────────────────────────────────────
    def _m_ar(r):
        c = (list(r) + [None] * 18)[:18]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            date=to_date(c[2]),
            shift_id=shift_id_safe(c[3]),
            check_in_time=to_time(c[4]),
            check_out_time=to_time(c[5]),
            working_hours=to_float(c[6]),
            status=to_str(c[7]),
            late_minutes=to_int(c[8]),
            early_checkout_mins=to_int(c[9]),
            overtime_hours=to_float(c[10]),
            leave_request_id=leave_req_id(c[11]),
            is_regularized=bool(to_bool(c[12]) or False),
            # Skip FK to regularization_id during seed — populated in 2nd pass below.
            lop_applied=bool(to_bool(c[14]) or False),
            lop_type=to_str(c[15]),
        )
    _do("attendance_records", AttendanceRecord, _m_ar)

    db.flush()

    # ── attendance_exceptions ─────────────────────────────────────
    def _m_ae(r):
        c = (list(r) + [None] * 9)[:9]
        return to_str(c[0]), dict(
            attendance_record_id=att_rec_id(c[1]),
            employee_id=emp_id(c[2]),
            date=to_date(c[3]),
            exception_type=to_str(c[4]),
            description=to_str(c[5]),
            is_resolved=bool(to_bool(c[6]) or False),
            resolved_at=to_dt(c[7]),
        )
    _do("attendance_exceptions", AttendanceException, _m_ae)

    # ── regularization_requests ───────────────────────────────────
    def _m_rr(r):
        c = (list(r) + [None] * 15)[:15]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            attendance_record_id=att_rec_id(c[2]),
            date=to_date(c[3]),
            regularization_type=to_str(c[4]),
            requested_check_in=to_time(c[5]),
            requested_check_out=to_time(c[6]),
            reason=to_str(c[7]),
            attachment_url=to_str(c[8]),
            status=(to_str(c[9]) or "pending").lower(),
            reviewed_by=emp_id(c[10]),
            review_comment=to_str(c[11]),
            reviewed_at=to_dt(c[12]),
        )
    _do("regularization_requests", RegularizationRequest, _m_rr)

    db.flush()

    # 2nd pass — populate AttendanceRecord.regularization_id (now that RRs exist).
    for row in _data_rows(wb, "attendance_records"):
        cells = (list(row) + [None] * 18)[:18]
        ar_id = to_str(cells[0])
        reg_id = to_str(cells[13])
        if ar_id and reg_id:
            ar = db.get(AttendanceRecord, ar_id)
            if ar and db.get(RegularizationRequest, reg_id):
                ar.regularization_id = reg_id

    # ── regularization_attachments ────────────────────────────────
    def _m_ra(r):
        c = (list(r) + [None] * 7)[:7]
        return to_str(c[0]), dict(
            regularization_id=reg_req_id(c[1]),
            employee_id=emp_id(c[2]),
            file_name=to_str(c[3]),
            file_url=to_str(c[4]),
            file_type=to_str(c[5]),
            uploaded_at=to_dt(c[6]),
        )
    _do("regularization_attachments", RegularizationAttachment, _m_ra)

    # ── overtime_records ──────────────────────────────────────────
    def _m_or(r):
        c = (list(r) + [None] * 11)[:11]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            attendance_record_id=att_rec_id(c[2]),
            date=to_date(c[3]),
            overtime_hours=to_float(c[4]),
            overtime_type=to_str(c[5]),
            status=to_str(c[6]),
            approved_by=emp_id(c[7]),
            approved_at=to_dt(c[8]),
            comp_leave_request_id=leave_req_id(c[10]),
        )
    _do("overtime_records", OvertimeRecord, _m_or)

    # ── notifications ─────────────────────────────────────────────
    # Existing model uses recipient_id/type/title for legacy fields; we map
    # the schema columns into both sides so old code keeps reading them.
    def _m_notif(r):
        c = (list(r) + [None] * 9)[:9]
        nid = to_str(c[0])
        message = to_str(c[5])
        return nid, dict(
            recipient_id=emp_id(c[1]),
            type=to_str(c[2]) or "info",
            title=(message[:160] if message else "Notification"),
            body=message,
            reference_table=to_str(c[3]),
            reference_id=to_str(c[4]),
            is_read=bool(to_bool(c[6]) or False),
            read_at=to_dt(c[8]),
        )
    # Notification PK is INT autoincrement; schema PK is "NOTIF0001".
    # We can't store the schema string PK in an int column, so we upsert
    # by (recipient_id, reference_table, reference_id) instead. Simpler:
    # we just append all notifications as new rows on a fresh seed.
    if _has_sheet(wb, "notifications"):
        ins = 0
        for row in _data_rows(wb, "notifications"):
            try:
                _, fields = _m_notif(row)
            except Exception:
                continue
            if fields.get("recipient_id") is None:
                continue
            # de-dupe by (recipient_id, reference_table, reference_id, body)
            existing = (
                db.query(Notification)
                .filter(
                    Notification.recipient_id == fields["recipient_id"],
                    Notification.reference_table == fields.get("reference_table"),
                    Notification.reference_id == fields.get("reference_id"),
                    Notification.body == fields.get("body"),
                )
                .first()
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                db.add(Notification(**fields))
                ins += 1
        if ins:
            counts["notifications"] = (ins, 0)

    # ── audit_logs (generic) ──────────────────────────────────────
    def _m_audit(r):
        c = (list(r) + [None] * 9)[:9]
        return to_str(c[0]), dict(
            actor_employee_id=emp_id(c[1]),
            action=to_str(c[2]),
            target_table=to_str(c[3]),
            target_id=to_str(c[4]),
            old_value=to_str(c[5]),
            new_value=to_str(c[6]),
            ip_address=to_str(c[7]),
        )
    _do("audit_logs", AuditLog, _m_audit)

    # ── attendance_reports ────────────────────────────────────────
    def _m_rpt(r):
        c = (list(r) + [None] * 12)[:12]
        return to_str(c[0]), dict(
            report_type=to_str(c[1]),
            report_scope=to_str(c[2]),
            generated_for_id=to_int(c[3]),
            period_start=to_date(c[4]),
            period_end=to_date(c[5]),
            generated_by=emp_id(c[6]),
            file_url=to_str(c[7]),
            file_format=to_str(c[8]),
            is_scheduled=bool(to_bool(c[9]) or False),
            schedule_frequency=to_str(c[10]),
        )
    _do("attendance_reports", AttendanceReport, _m_rpt)

    # ── payroll_attendance_summary ────────────────────────────────
    def _m_pas(r):
        c = (list(r) + [None] * 17)[:17]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            month=to_str(c[2]),
            year=to_int(c[3]),
            total_working_days=to_int(c[4]),
            present_days=to_int(c[5]),
            absent_days=to_int(c[6]),
            half_days=to_int(c[7]),
            late_days=to_int(c[8]),
            leave_days=to_int(c[9]),
            holiday_count=to_int(c[10]),
            lop_days=to_int(c[11]),
            overtime_hours=to_float(c[12]),
            is_finalized=bool(to_bool(c[13]) or False),
            finalized_at=to_dt(c[14]),
        )
    _do("payroll_attendance_summary", PayrollAttendanceSummary, _m_pas)

    # ── projects ──────────────────────────────────────────────────
    def _m_prj(r):
        c = (list(r) + [None] * 12)[:12]
        return to_str(c[0]), dict(
            project_code=to_str(c[1]),
            name=to_str(c[2]),
            client_name=to_str(c[3]),
            department_id=dept_id_safe(c[4]),
            project_manager_id=emp_id(c[5]),
            start_date=to_date(c[6]),
            end_date=to_date(c[7]),
            status=to_str(c[8]),
            is_billable=bool(to_bool(c[9]) or False),
        )
    _do("projects", Project, _m_prj)

    db.flush()

    # ── tasks ─────────────────────────────────────────────────────
    def _m_task(r):
        c = (list(r) + [None] * 8)[:8]
        return to_str(c[0]), dict(
            project_id=proj_id(c[1]),
            name=to_str(c[2]),
            description=to_str(c[3]),
            assigned_to=emp_id(c[4]),
            status=to_str(c[5]),
        )
    _do("tasks", Task, _m_task)

    db.flush()

    # ── timesheets ────────────────────────────────────────────────
    def _m_ts(r):
        c = (list(r) + [None] * 15)[:15]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            period_type=to_str(c[2]),
            period_start=to_date(c[3]),
            period_end=to_date(c[4]),
            total_logged_hours=to_float(c[5]),
            status=to_str(c[6]),
            submitted_at=to_dt(c[7]),
            reviewed_by=emp_id(c[8]),
            review_comment=to_str(c[9]),
            reviewed_at=to_dt(c[10]),
            is_locked=bool(to_bool(c[11]) or False),
            locked_at=to_dt(c[12]),
        )
    _do("timesheets", Timesheet, _m_ts)

    db.flush()

    # ── timesheet_entries ─────────────────────────────────────────
    def _m_te(r):
        c = (list(r) + [None] * 13)[:13]
        return to_str(c[0]), dict(
            timesheet_id=ts_id(c[1]),
            employee_id=emp_id(c[2]),
            entry_date=to_date(c[3]),
            project_id=proj_id(c[4]),
            task_id=task_id_safe(c[5]),
            logged_hours=to_float(c[6]),
            source=to_str(c[7]),
            description=to_str(c[8]),
            is_manual_entry=bool(to_bool(c[9]) or False),
            attendance_record_id=att_rec_id(c[10]),
        )
    _do("timesheet_entries", TimesheetEntry, _m_te)

    # ── timesheet_payroll_sync ────────────────────────────────────
    def _m_tps(r):
        c = (list(r) + [None] * 14)[:14]
        eid = emp_id(c[1])
        if eid is None:
            return None, {}
        return to_str(c[0]), dict(
            employee_id=eid,
            month=to_str(c[2]),
            year=to_int(c[3]),
            timesheet_id=ts_id(c[4]),
            payroll_summary_id=pas_id(c[5]),
            timesheet_hours=to_float(c[6]),
            attendance_hours=to_float(c[7]),
            variance_hours=to_float(c[8]),
            has_mismatch=bool(to_bool(c[9]) or False),
            mismatch_reason=to_str(c[10]),
            resolved_by=emp_id(c[11]),
            resolved_at=to_dt(c[12]),
        )
    _do("timesheet_payroll_sync", TimesheetPayrollSync, _m_tps)

    return counts


def seed(xlsx_path: Path, backup_db_path: Optional[Path] = None):
    print(f"Loading: {xlsx_path}")
    try:
        wb = load_workbook(xlsx_path, data_only=True)
    except PermissionError as e:
        print()
        print("ERROR: Couldn't open the spreadsheet -- Windows is holding a lock on it.")
        print("   Most common causes:")
        print("     1. The file is open in Excel.  Close the workbook and retry.")
        print("     2. OneDrive is mid-sync.       Wait for the green-check icon, then retry.")
        print("     3. A stale ~$Employees-updated.xlsx Excel lock file exists. Delete it.")
        print()
        print(f"   Underlying error: {e}")
        sys.exit(1)

    print("Ensuring tables exist + applying additive schema upgrades...")
    Base.metadata.create_all(bind=engine)
    auto_upgrade_schema()
    backfill_legacy_chain_fields()

    with SessionLocal() as db:
        sync_master_data(db, overwrite_department_id=True)
        db.commit()

        # 1) Roles
        roles = {
            "admin":    upsert_role(db, "admin",    "Workspace administrator -- full access"),
            "manager":  upsert_role(db, "manager",  "People manager -- team scope"),
            "employee": upsert_role(db, "employee", "Employee -- personal scope"),
        }

        # 2) Leave types
        if _has_sheet(wb, "leave_types"):
            for row in wb["leave_types"].iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                cells = (list(row) + [None] * 6)[:6]
                lt_id, lt_name, quota, carry, paid, gender = cells
                obj = db.get(LeaveType, lt_id)
                fields = dict(
                    name=str(lt_name or "").strip(),
                    annual_quota=to_int(quota),
                    carry_forward_limit=to_int(carry),
                    is_paid=bool(to_bool(paid) if paid is not None else True),
                    applicable_gender=(to_str(gender) or "all").lower(),
                )
                if obj is None:
                    db.add(LeaveType(id=str(lt_id), **fields))
                else:
                    for k, v in fields.items():
                        setattr(obj, k, v)

        db.flush()

        # 3) Employees (full-field upsert)
        designations_by_id = {d.id: d for d in db.query(Designation).all()}
        emps_inserted = emps_updated = 0
        for row in wb["employees"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            email = to_str(row[5]) if len(row) > 5 else None
            if not email:
                continue

            existing = db.query(Employee).filter(Employee.email.ilike(email)).one_or_none()
            existing_hash = existing.password_hash if existing else None

            fields, _role = _row_to_employee_fields(
                row, designations_by_id, roles, password_existing=existing_hash,
            )

            if existing is None:
                db.add(Employee(**fields))
                emps_inserted += 1
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
                emps_updated += 1

        db.flush()

        # 4) Leave balances.
        # Comp-off balances are NEVER seeded -- those days only accrue when a
        # manager grants comp-off and HR approves it via /leave/comp-off/grant.
        # If the Excel sheet has a Compensatory_leave row, we deliberately
        # skip it so employees can't apply comp-off without a real grant.
        comp_type_ids = {
            t.id for t in db.query(LeaveType).filter(LeaveType.name.ilike("%comp%")).all()
        }
        lb_inserted = lb_updated = lb_skipped = 0
        if _has_sheet(wb, "leave_balances"):
            for row in wb["leave_balances"].iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                cells = (list(row) + [None] * 7)[:7]
                lb_id, lb_emp_id, lt_id, year, opening, used, current = cells
                if not (lb_id and lb_emp_id and lt_id):
                    continue
                if str(lt_id) in comp_type_ids:
                    lb_skipped += 1
                    continue
                lb_emp_int = to_int(lb_emp_id)
                lb_lt_str  = str(lt_id)
                if db.get(Employee, lb_emp_int) is None or db.get(LeaveType, lb_lt_str) is None:
                    lb_skipped += 1
                    continue
                obj = db.get(LeaveBalance, lb_id)
                fields = dict(
                    employee_id=lb_emp_int,
                    leave_type_id=lb_lt_str,
                    year=to_int(year) or 0,
                    opening_balance=to_int(opening) or 0,
                    used=to_int(used) or 0,
                    current_balance=to_int(current) or 0,
                )
                if obj is None:
                    db.add(LeaveBalance(id=str(lb_id), **fields))
                    lb_inserted += 1
                else:
                    for k, v in fields.items():
                        setattr(obj, k, v)
                    lb_updated += 1

        # 5) Leave requests -- DISABLED.
        # The original Excel `leave_requests` sheet is no longer authoritative;
        # actual leave applications come from the UI through /leave/apply.
        # Setting these to 0 so the summary block below still works.
        lr_inserted = lr_updated = 0


        # ── 9) Attendance (optional sheet) ───────────────────────────
        # Sheet 'attendance' columns (1-indexed):
        #   A: employee_id   B: date   C: status (present/absent/wfh/leave/holiday)   D: source (manual/biometric/import)   E: note
        att_inserted = att_updated = 0
        if _has_sheet(wb, "attendance"):
            for row in wb["attendance"].iter_rows(min_row=2, values_only=True):
                if not row or row[0] is None:
                    continue
                cells = (list(row) + [None] * 5)[:5]
                att_emp_id, dt, status, source, note = cells
                att_emp_id = to_int(att_emp_id)
                dt = to_date(dt)
                if not (att_emp_id and dt):
                    continue
                if db.get(Employee, att_emp_id) is None:
                    continue
                existing = (
                    db.query(Attendance)
                    .filter(Attendance.employee_id == att_emp_id, Attendance.date == dt)
                    .first()
                )
                fields = dict(
                    status=(to_str(status) or "present").lower(),
                    source=(to_str(source) or "manual").lower(),
                    note=to_str(note),
                )
                if existing is None:
                    db.add(Attendance(employee_id=att_emp_id, date=dt, **fields))
                    att_inserted += 1
                else:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    att_updated += 1

        # ── 10) hrms_schema_complete.xlsx — additive sheets ──────────
        # Each loader is gated by _has_sheet() so this same seed.py keeps
        # working against the legacy Employees-updated.xlsx workbook.
        new_counts = _seed_new_schema_sheets(db, wb)
        backup_counts = {}
        if backup_db_path and backup_db_path.is_file():
            backup_counts = _import_backup_db_data(db, backup_db_path)

        db.commit()

        print()
        print("Seed summary:")
        print(f"  Employees       : +{emps_inserted} new, ~{emps_updated} updated")
        print(f"  Attendance      : +{att_inserted} new, ~{att_updated} updated")
        if lb_skipped:
            print(f"  Leave balances  : +{lb_inserted} new, ~{lb_updated} updated, {lb_skipped} comp-off rows skipped (grant-only)")
        else:
            print(f"  Leave balances  : +{lb_inserted} new, ~{lb_updated} updated")
        print(f"  Leave requests  : +{lr_inserted} new, ~{lr_updated} updated")
        if new_counts:
            print("  -- new schema sheets --")
            for sheet_name in sorted(new_counts):
                ins, upd = new_counts[sheet_name]
                print(f"  {sheet_name:<28s}: +{ins} new, ~{upd} updated")
        if backup_counts:
            print("  -- backup db merge --")
            for sheet_name in sorted(backup_counts):
                ins, upd, skipped = backup_counts[sheet_name]
                print(f"  {sheet_name:<28s}: +{ins} new, ~{upd} updated, {skipped} skipped")
        print("Done.")


def main():
    xlsx_arg, backup_arg = _parse_args(sys.argv[1:])
    xlsx = find_xlsx(xlsx_arg)
    if not xlsx:
        print("ERROR: No xlsx file found.")
        print("   Pass an explicit path:  python seed.py path/to/hrms_schema_complete.xlsx")
        sys.exit(1)
    backup_db = find_backup_db(backup_arg)
    if backup_arg and not backup_db:
        print(f"ERROR: Backup db not found: {backup_arg}")
        sys.exit(1)
    seed(xlsx, backup_db)


if __name__ == "__main__":
    main()
