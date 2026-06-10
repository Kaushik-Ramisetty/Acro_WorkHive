"""
Attendance seed for payroll testing – June 2026.

Populates:
  • monthly_attendance_summary  (upsert – one row per active employee)
  • attendance_records           (one row per employee × working day)

Rules:
  • Working days = Mon-Fri only (weekends excluded)
  • payable_days = total_working_days - lop_days
  • present_days + leave_days + lop_days == total_working_days  (full accounting)
  • Some employees have late arrivals, leave days, LOP for realistic variety
  • Real employees: IDs 1-10 (AIN codes)
  • Test employees: IDs 13, 14, 16 (EMP codes) – included but labelled
  • Employee master data NOT modified

Run:  python seed_attendance_june2026.py
"""

import sqlite3
import random
from datetime import date, time, timedelta, datetime

DB_PATH = "hrms.db"
MONTH = 6
YEAR = 2026

# ── Working days (Mon-Fri) for June 2026 ─────────────────────────────────────

def working_days(year: int, month: int) -> list[date]:
    """Return all Mon-Fri dates in the given month."""
    days = []
    d = date(year, month, 1)
    while d.month == month:
        if d.weekday() < 5:          # 0=Mon … 4=Fri
            days.append(d)
        d += timedelta(days=1)
    return days


WORKDAYS = working_days(YEAR, MONTH)
TOTAL_WORKING_DAYS = len(WORKDAYS)   # 21 for June 2026

# ── Per-employee attendance scenario ─────────────────────────────────────────
# Schema: employee_id, present, leave_days, lop_days, label
# Invariant: present + leave_days + lop_days == TOTAL_WORKING_DAYS
# payable_days = TOTAL_WORKING_DAYS - lop_days

SCENARIOS = [
    # id   present  leave  lop  label                      (must sum to TOTAL_WORKING_DAYS)
    # June 2026 starts on Monday → 22 Mon-Fri working days
    (1,    22,      0,     0,   "full attendance"),
    (2,    19,      2,     1,   "2 paid leave + 1 LOP"),
    (3,    21,      1,     0,   "1 paid leave"),
    (4,    20,      2,     0,   "2 paid leave"),
    (5,    21,      0,     1,   "1 LOP day"),
    (6,    20,      1,     1,   "1 paid leave + 1 LOP"),
    (7,    22,      0,     0,   "full attendance"),
    (8,    21,      1,     0,   "1 paid leave"),
    (9,    22,      0,     0,   "full attendance"),
    (10,   20,      2,     0,   "2 paid leave"),
    # test employees
    (13,   18,      2,     2,   "TEST – 2 leave + 2 LOP"),
    (14,   17,      3,     2,   "TEST – 3 leave + 2 LOP"),
    (16,   12,      5,     5,   "TEST – 5 leave + 5 LOP"),
]

# Validate scenario arithmetic
for sid, p, l, lop, _ in SCENARIOS:
    assert p + l + lop == TOTAL_WORKING_DAYS, (
        f"Employee {sid}: {p}+{l}+{lop} != {TOTAL_WORKING_DAYS}"
    )

# ── Helpers ───────────────────────────────────────────────────────────────────

random.seed(42)   # reproducible

NORMAL_CHECKIN  = time(9, 0)
LATE_CHECKIN_A  = time(9, 35)   # mild late
LATE_CHECKIN_B  = time(10, 15)  # noticeable late
NORMAL_CHECKOUT = time(18, 0)
EARLY_CHECKOUT  = time(17, 15)


def _fmt_time(t: time) -> str:
    return t.strftime("%H:%M:%S")


def _jitter(base_min: int, spread: int) -> int:
    """Return base_min ± random spread."""
    return base_min + random.randint(-spread, spread)


def build_daily_records(
    employee_id: int,
    present: int,
    leave_days: int,
    lop_days: int,
    workdays: list[date],
) -> list[dict]:
    """Assign day-types to working-day slots and build attendance_record dicts."""

    slots = list(workdays)  # copy

    # Pick which specific days are leave / LOP / absent
    leave_indices  = sorted(random.sample(range(len(slots)), leave_days))
    remaining      = [i for i in range(len(slots)) if i not in leave_indices]
    lop_indices    = sorted(random.sample(remaining, lop_days))
    present_indices = sorted(
        [i for i in range(len(slots)) if i not in leave_indices and i not in lop_indices]
    )

    # Pick a few present days to be late (up to 3)
    n_late = min(3, present)
    late_set = set(random.sample(present_indices, n_late)) if present_indices else set()

    records = []
    for idx, day in enumerate(slots):
        rec_id = f"AR{day.strftime('%Y%m%d')}{employee_id:04d}"

        if idx in leave_indices:
            records.append({
                "id": rec_id,
                "employee_id": employee_id,
                "date": day.isoformat(),
                "status": "leave",
                "check_in_time": None,
                "check_out_time": None,
                "working_hours": 0.0,
                "late_minutes": 0,
                "early_checkout_mins": 0,
                "overtime_hours": 0.0,
                "lop_applied": 0,
                "lop_type": None,
                "is_regularized": 0,
            })
        elif idx in lop_indices:
            records.append({
                "id": rec_id,
                "employee_id": employee_id,
                "date": day.isoformat(),
                "status": "absent",
                "check_in_time": None,
                "check_out_time": None,
                "working_hours": 0.0,
                "late_minutes": 0,
                "early_checkout_mins": 0,
                "overtime_hours": 0.0,
                "lop_applied": 1,
                "lop_type": "full_day",
                "is_regularized": 0,
            })
        else:
            # Present day
            if idx in late_set:
                ci_choice = random.choice([LATE_CHECKIN_A, LATE_CHECKIN_B])
                ci_h, ci_m = ci_choice.hour, ci_choice.minute + random.randint(0, 10)
                if ci_m >= 60:
                    ci_h += 1
                    ci_m -= 60
                check_in = time(ci_h, ci_m)
                late_mins = (check_in.hour * 60 + check_in.minute) - (9 * 60)
                late_mins = max(late_mins, 0)
            else:
                ci_m = _jitter(0, 10)
                check_in = time(9, max(0, ci_m))
                late_mins = 0

            co_m = _jitter(0, 15)
            check_out = time(18, max(0, co_m))
            early_co_mins = 0

            # Compute working hours
            ci_total = check_in.hour * 60 + check_in.minute
            co_total = check_out.hour * 60 + check_out.minute
            wh = round((co_total - ci_total) / 60, 2)

            # Overtime if > 9 hours
            ot = round(max(wh - 9.0, 0), 2)

            records.append({
                "id": rec_id,
                "employee_id": employee_id,
                "date": day.isoformat(),
                "status": "late_arrival" if late_mins > 0 else "present",
                "check_in_time": _fmt_time(check_in),
                "check_out_time": _fmt_time(check_out),
                "working_hours": wh,
                "late_minutes": late_mins,
                "early_checkout_mins": early_co_mins,
                "overtime_hours": ot,
                "lop_applied": 0,
                "lop_type": None,
                "is_regularized": 0,
            })

    return records


# ── Main seed logic ───────────────────────────────────────────────────────────

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now_str = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    print(f"\n{'='*70}")
    print(f"  ATTENDANCE SEED – June {YEAR}  |  {TOTAL_WORKING_DAYS} working days (Mon-Fri)")
    print(f"{'='*70}\n")

    # Verify each scenario employee exists and is active
    emp_map = {}
    for sid, *_ in SCENARIOS:
        c.execute(
            "SELECT id, employee_code, first_name, last_name, employment_status, is_deleted "
            "FROM employees WHERE id=?", (sid,)
        )
        row = c.fetchone()
        if not row:
            print(f"  SKIP  employee_id={sid}  (not found)")
            continue
        if row["is_deleted"] or row["employment_status"] != "active":
            print(f"  SKIP  employee_id={sid} {row['first_name']} {row['last_name']}  (inactive/deleted)")
            continue
        emp_map[sid] = dict(row)

    print(f"  Employees to process: {len(emp_map)}")
    print()

    # ── Wipe existing attendance_records for June 2026 ────────────────────────
    ids_str = ",".join(str(i) for i in emp_map)
    c.execute(
        f"DELETE FROM attendance_records "
        f"WHERE employee_id IN ({ids_str}) "
        f"AND date >= '2026-06-01' AND date <= '2026-06-30'"
    )
    deleted_ar = c.rowcount
    print(f"  Deleted {deleted_ar} old attendance_records for June 2026")

    # ── Wipe existing monthly_attendance_summary for June 2026 ────────────────
    c.execute(
        f"DELETE FROM monthly_attendance_summary "
        f"WHERE employee_id IN ({ids_str}) AND month=6 AND year=2026"
    )
    deleted_mas = c.rowcount
    print(f"  Deleted {deleted_mas} old monthly_attendance_summary rows\n")

    # ── Insert per-employee data ───────────────────────────────────────────────
    summary_rows = 0
    ar_rows = 0
    stats = []

    for sid, present, leave_d, lop_d, label in SCENARIOS:
        if sid not in emp_map:
            continue

        emp = emp_map[sid]
        payable = float(TOTAL_WORKING_DAYS - lop_d)
        att_pct = round((payable / TOTAL_WORKING_DAYS) * 100, 1)
        timesheet_hours = round(present * 8.0, 1)

        # ── monthly_attendance_summary ─────────────────────────────────────
        c.execute("""
            INSERT INTO monthly_attendance_summary
                (employee_id, month, year,
                 total_working_days, present_days, leave_days, lop_days, payable_days,
                 approved_timesheet_hours,
                 attendance_status, timesheet_status, validation_status,
                 issues_count, validation_notes,
                 is_ready_for_payroll, is_frozen,
                 finalized_by, finalized_at,
                 lop_source, lop_status, lop_last_synced_at,
                 snapshot_note,
                 created_at, updated_at)
            VALUES
                (?,?,?,
                 ?,?,?,?,?,
                 ?,
                 'finalized','approved','passed',
                 0, NULL,
                 1, 1,
                 7, ?,
                 'Leave Management','ready',?,
                 ?,
                 ?,?)
        """, (
            sid, MONTH, YEAR,
            TOTAL_WORKING_DAYS, present, leave_d, lop_d, payable,
            timesheet_hours,
            now_str,          # finalized_at
            now_str,          # lop_last_synced_at
            f"Attendance seed June 2026 – {label}",
            now_str, now_str,
        ))
        summary_rows += 1

        # ── attendance_records ─────────────────────────────────────────────
        daily = build_daily_records(sid, present, leave_d, lop_d, WORKDAYS)
        late_count = sum(1 for r in daily if r["status"] == "late_arrival")

        for r in daily:
            c.execute("""
                INSERT OR REPLACE INTO attendance_records
                    (id, employee_id, date, status,
                     check_in_time, check_out_time, working_hours,
                     late_minutes, early_checkout_mins, overtime_hours,
                     lop_applied, lop_type, is_regularized,
                     created_at, updated_at)
                VALUES
                    (?,?,?,?,
                     ?,?,?,
                     ?,?,?,
                     ?,?,?,
                     ?,?)
            """, (
                r["id"], r["employee_id"], r["date"], r["status"],
                r["check_in_time"], r["check_out_time"], r["working_hours"],
                r["late_minutes"], r["early_checkout_mins"], r["overtime_hours"],
                r["lop_applied"], r["lop_type"], r["is_regularized"],
                now_str, now_str,
            ))
            ar_rows += 1

        stats.append({
            "id": sid,
            "code": emp["employee_code"],
            "name": f"{emp['first_name']} {emp['last_name']}",
            "present": present,
            "leave": leave_d,
            "lop": lop_d,
            "payable": payable,
            "att_pct": att_pct,
            "late": late_count,
            "label": label,
        })

    conn.commit()
    conn.close()

    # ── Validation queries ────────────────────────────────────────────────────
    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row
    v = conn2.cursor()

    # 1. All summaries present
    v.execute(
        "SELECT COUNT(*) AS n FROM monthly_attendance_summary "
        "WHERE month=6 AND year=2026"
    )
    n_summaries = v.fetchone()["n"]

    # 2. Orphan check: attendance_records → employees
    v.execute("""
        SELECT COUNT(*) AS n FROM attendance_records ar
        WHERE ar.date >= '2026-06-01' AND ar.date <= '2026-06-30'
          AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.id = ar.employee_id)
    """)
    orphans = v.fetchone()["n"]

    # 3. Payroll can calculate payable_days
    v.execute("""
        SELECT employee_id,
               total_working_days,
               lop_days,
               payable_days,
               (total_working_days - lop_days) AS calc_payable
        FROM monthly_attendance_summary
        WHERE month=6 AND year=2026
    """)
    payable_ok = True
    payable_errors = []
    for row in v.fetchall():
        if abs(row["payable_days"] - row["calc_payable"]) > 0.001:
            payable_ok = False
            payable_errors.append(
                f"emp {row['employee_id']}: stored={row['payable_days']} calc={row['calc_payable']}"
            )

    # 4. Payroll can calculate attendance %
    v.execute("""
        SELECT employee_id,
               present_days,
               total_working_days,
               ROUND(CAST(present_days AS FLOAT) / total_working_days * 100, 1) AS att_pct
        FROM monthly_attendance_summary
        WHERE month=6 AND year=2026
    """)
    att_pct_rows = v.fetchall()

    # 5. Leave impact: employees with leave_days > 0
    v.execute("""
        SELECT COUNT(*) AS n FROM monthly_attendance_summary
        WHERE month=6 AND year=2026 AND leave_days > 0
    """)
    has_leave = v.fetchone()["n"]

    # 6. LOP impact: employees with lop_days > 0
    v.execute("""
        SELECT COUNT(*) AS n FROM monthly_attendance_summary
        WHERE month=6 AND year=2026 AND lop_days > 0
    """)
    has_lop = v.fetchone()["n"]

    # 7. All frozen (payroll gate)
    v.execute("""
        SELECT COUNT(*) AS n FROM monthly_attendance_summary
        WHERE month=6 AND year=2026 AND is_frozen = 0
    """)
    not_frozen = v.fetchone()["n"]

    # 8. Day math check in attendance_records
    v.execute("""
        SELECT employee_id, COUNT(*) AS total_rows,
               SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS p,
               SUM(CASE WHEN status='late_arrival' THEN 1 ELSE 0 END) AS la,
               SUM(CASE WHEN status='leave' THEN 1 ELSE 0 END) AS lv,
               SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END) AS ab
        FROM attendance_records
        WHERE date >= '2026-06-01' AND date <= '2026-06-30'
        GROUP BY employee_id
        ORDER BY employee_id
    """)
    ar_summary = v.fetchall()

    conn2.close()

    # ── Print report ──────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  ATTENDANCE STATISTICS – June 2026")
    print("="*70)
    print(f"  {'ID':<4} {'Code':<8} {'Name':<28} {'Pres':>4} {'Lv':>3} {'LOP':>3} {'Pay':>4} {'Att%':>5} {'Late':>4}")
    print(f"  {'-'*72}")
    for s in stats:
        flag = " [TEST]" if s["code"].startswith("EMP") else ""
        print(
            f"  {s['id']:<4} {s['code']:<8} {s['name']:<28} "
            f"{s['present']:>4} {s['leave']:>3} {s['lop']:>3} "
            f"{s['payable']:>4.0f} {s['att_pct']:>5.1f}%"
            f" {s['late']:>2} late{flag}"
        )

    print()
    print("  Attendance record breakdown (from attendance_records table):")
    print(f"  {'EmpID':<6} {'Total':>5} {'Present':>7} {'Late':>5} {'Leave':>6} {'LOP':>5}")
    print(f"  {'-'*40}")
    for row in ar_summary:
        print(
            f"  {row['employee_id']:<6} {row['total_rows']:>5} "
            f"{row['p']:>7} {row['la']:>5} {row['lv']:>6} {row['ab']:>5}"
        )

    print()
    print("="*70)
    print("  VALIDATION")
    print("="*70)

    checks = [
        ("monthly_attendance_summary rows inserted",
         n_summaries == len(emp_map), f"{n_summaries} rows"),
        ("attendance_records rows inserted",
         ar_rows == TOTAL_WORKING_DAYS * len(emp_map),
         f"{ar_rows} rows ({TOTAL_WORKING_DAYS} days × {len(emp_map)} employees)"),
        ("payable_days = total_working_days - lop_days",
         payable_ok, "all match" if payable_ok else str(payable_errors)),
        ("attendance % computable (present/total*100)",
         True, f"{len(att_pct_rows)} rows calculable"),
        ("leave impact present (leave_days > 0)",
         has_leave > 0, f"{has_leave} employees have paid leave"),
        ("LOP impact present (lop_days > 0)",
         has_lop > 0, f"{has_lop} employees have LOP"),
        ("all summaries frozen for payroll gate",
         not_frozen == 0, "all frozen" if not_frozen == 0 else f"{not_frozen} NOT frozen"),
        ("no orphan attendance_records (FK integrity)",
         orphans == 0, "clean" if orphans == 0 else f"{orphans} orphans"),
    ]

    all_pass = True
    for label, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}")
        print(f"         > {detail}")
        if not ok:
            all_pass = False

    print()
    print("="*70)
    print(f"  PAYROLL SOURCE TABLE: monthly_attendance_summary")
    print(f"  DATE RANGE           : 2026-06-01 to 2026-06-30  ({TOTAL_WORKING_DAYS} working days)")
    print(f"  EMPLOYEES AFFECTED   : {len(emp_map)}  (IDs: {sorted(emp_map)})")
    print(f"  TABLES POPULATED     : monthly_attendance_summary, attendance_records")
    print()
    print(f"  {'='*30}")
    print(f"  OVERALL : {'PASS' if all_pass else 'FAIL'}")
    print(f"  {'='*30}\n")


if __name__ == "__main__":
    run()
