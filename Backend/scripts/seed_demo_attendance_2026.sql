-- ============================================================
-- DEMO ATTENDANCE SEED  —  May / June / July 2026
-- Purpose  : Clean payroll demo — HR freeze → Finance generate → full flow
-- DB       : SQLite  —  Backend/hrms.db
-- Run via  : sqlite3 hrms.db ".read scripts/seed_demo_attendance_2026.sql"
-- Rollback : DELETE FROM monthly_attendance_summary WHERE month IN (5,6,7) AND year=2026;
--
-- Calendar working-day counts (Mon–Fri, no public holidays):
--   May  2026 : 21 working days  (31 days, 10 weekend days)
--   June 2026 : 22 working days  (30 days,  8 weekend days)
--   July 2026 : 23 working days  (31 days,  8 weekend days)
--
-- LOP distribution (applied to first 3 active employees by id, others = 0):
--   May  2026 : LOP = 0 for ALL employees
--   June 2026 : employee rank-1 → LOP 2, rank-2 → LOP 3, rest → 0
--   July 2026 : employee rank-2 → LOP 1, rank-3 → LOP 2, rest → 0
--
-- payable_days = total_working_days - lop_days
-- approved_timesheet_hours = payable_days × 8
--
-- SAFE : Only touches month IN (5,6,7), year=2026 rows.
--        No changes to employees, salary structures, or payroll runs.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- STEP 1  —  Show active employees
-- ────────────────────────────────────────────────────────────
SELECT
    e.id            AS employee_id,
    e.employee_code,
    e.first_name || ' ' || COALESCE(e.last_name, '') AS employee_name,
    e.employment_status
FROM employees e
WHERE e.employment_status = 'active'
  AND (e.is_deleted = 0 OR e.is_deleted IS NULL)
ORDER BY e.id;


-- ────────────────────────────────────────────────────────────
-- STEP 2  —  Clear existing May/June/July 2026 rows (idempotent)
-- ────────────────────────────────────────────────────────────
DELETE FROM monthly_attendance_summary
WHERE month IN (5, 6, 7)
  AND year = 2026;


-- ────────────────────────────────────────────────────────────
-- STEP 3  —  Insert May 2026 (LOP = 0 for ALL active employees)
--            21 working days
-- ────────────────────────────────────────────────────────────
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at,
     created_at, updated_at)
SELECT
    e.id,
    5, 2026,
    21,          -- total_working_days
    21,          -- present_days
    0,           -- leave_days
    0,           -- lop_days  (May: always 0)
    21.0,        -- payable_days = 21 - 0
    168.0,       -- approved_timesheet_hours = 21 × 8
    'validated', 'approved', 'passed',
    0, NULL,
    1, 0,        -- is_ready_for_payroll=1, is_frozen=0
    NULL, NULL,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM employees e
WHERE e.employment_status = 'active'
  AND (e.is_deleted = 0 OR e.is_deleted IS NULL)
ORDER BY e.id;


-- ────────────────────────────────────────────────────────────
-- STEP 4  —  Insert June 2026 (2 employees with LOP)
--            22 working days
--            Rank-1 employee: LOP 2 → payable 20
--            Rank-2 employee: LOP 3 → payable 19
--            Others: LOP 0  → payable 22
-- ────────────────────────────────────────────────────────────
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at,
     created_at, updated_at)
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
    FROM employees
    WHERE employment_status = 'active'
      AND (is_deleted = 0 OR is_deleted IS NULL)
),
june_lop AS (
    SELECT id,
           CASE rn
               WHEN 1 THEN 2   -- first active employee: 2 LOP days
               WHEN 2 THEN 3   -- second active employee: 3 LOP days
               ELSE 0
           END AS lop
    FROM ranked
)
SELECT
    j.id,
    6, 2026,
    22,                       -- total_working_days
    22 - j.lop,               -- present_days (approx — leave=0 assumed for LOP employees)
    0,                        -- leave_days
    j.lop,                    -- lop_days
    CAST(22 - j.lop AS REAL), -- payable_days
    CAST((22 - j.lop) * 8 AS REAL),  -- approved_timesheet_hours
    'validated', 'approved', 'passed',
    0, NULL,
    1, 0,
    NULL, NULL,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM june_lop j
ORDER BY j.id;


-- ────────────────────────────────────────────────────────────
-- STEP 5  —  Insert July 2026 (2 employees with LOP)
--            23 working days
--            Rank-2 employee: LOP 1 → payable 22
--            Rank-3 employee: LOP 2 → payable 21
--            Others: LOP 0  → payable 23
-- ────────────────────────────────────────────────────────────
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at,
     created_at, updated_at)
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
    FROM employees
    WHERE employment_status = 'active'
      AND (is_deleted = 0 OR is_deleted IS NULL)
),
july_lop AS (
    SELECT id,
           CASE rn
               WHEN 2 THEN 1   -- second active employee: 1 LOP day
               WHEN 3 THEN 2   -- third active employee: 2 LOP days
               ELSE 0
           END AS lop
    FROM ranked
)
SELECT
    j.id,
    7, 2026,
    23,                       -- total_working_days
    23 - j.lop,               -- present_days
    0,                        -- leave_days
    j.lop,                    -- lop_days
    CAST(23 - j.lop AS REAL), -- payable_days
    CAST((23 - j.lop) * 8 AS REAL),  -- approved_timesheet_hours
    'validated', 'approved', 'passed',
    0, NULL,
    1, 0,
    NULL, NULL,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM july_lop j
ORDER BY j.id;


-- ────────────────────────────────────────────────────────────
-- STEP 6  —  Verification: show all inserted rows
-- ────────────────────────────────────────────────────────────
SELECT
    e.employee_code,
    e.first_name || ' ' || COALESCE(e.last_name, '') AS employee_name,
    mas.month,
    mas.year,
    mas.total_working_days,
    mas.present_days,
    mas.leave_days,
    mas.lop_days,
    mas.payable_days,
    mas.validation_status,
    mas.is_ready_for_payroll,
    mas.is_frozen
FROM monthly_attendance_summary mas
JOIN employees e ON e.id = mas.employee_id
WHERE mas.month IN (5, 6, 7)
  AND mas.year = 2026
ORDER BY mas.month ASC, mas.lop_days DESC, e.id ASC;


-- ────────────────────────────────────────────────────────────
-- STEP 7  —  Row count per month (should match active employee count)
-- ────────────────────────────────────────────────────────────
SELECT
    month,
    year,
    COUNT(*) AS row_count,
    SUM(CASE WHEN is_ready_for_payroll = 1 THEN 1 ELSE 0 END) AS ready_count,
    SUM(CASE WHEN lop_days > 0 THEN 1 ELSE 0 END) AS employees_with_lop,
    SUM(lop_days) AS total_lop_days
FROM monthly_attendance_summary
WHERE month IN (5, 6, 7)
  AND year = 2026
GROUP BY month, year
ORDER BY month ASC;
