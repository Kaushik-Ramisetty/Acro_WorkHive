-- ============================================================
-- DUMMY ATTENDANCE SEED  --  June 2026
-- Purpose  : Payroll testing (LOP flow validation)
-- Month    : 6 (June), Year : 2026
-- DB       : SQLite  --  Backend/hrms.db
-- Run via  : sqlite3 hrms.db ".read scripts/seed_dummy_attendance_may_2026.sql"
-- Rollback : scripts/rollback_dummy_attendance_may_2026.sql
--
-- SAFE     : Only touches month=6 year=2026 rows.
--            No employee, salary_structure, or payroll logic changes.
--
-- June 2026 calendar:
--   Total days   : 30
--   Weekends     : 8   (6,7,13,14,20,21,27,28)
--   Working days : 22
--
-- Payable logic  : payable_days = total_working_days - lop_days
--                               = present_days + leave_days
-- Approved hours : payable_days x 8
--
-- LOP distribution (13 active employees):
--   LOP  0  --  id 1,2,3,4,5,6,7,8,9   (9 employees, majority)
--   LOP  1  --  id 10  (Darshan N T)
--   LOP  2  --  id 13  (Suraj M)
--   LOP  5  --  id 14  (rahul r)
--   LOP 10  --  id 16  (aashi g)
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- STEP 1  --  Show existing active employees (read-only)
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
-- STEP 2  --  Show any pre-existing June 2026 rows
-- ────────────────────────────────────────────────────────────
SELECT COUNT(*) AS existing_june2026_rows
FROM monthly_attendance_summary
WHERE month = 6 AND year = 2026;


-- ────────────────────────────────────────────────────────────
-- STEP 3  --  Clear any prior June 2026 rows for these 13
--             employees (idempotent -- safe to rerun)
-- ────────────────────────────────────────────────────────────
DELETE FROM monthly_attendance_summary
WHERE month = 6
  AND year  = 2026
  AND employee_id IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 16);


-- ────────────────────────────────────────────────────────────
-- STEP 4  --  Insert dummy attendance rows
-- ────────────────────────────────────────────────────────────

-- id=1 | AIN715 | Palem Mahendra | LOP 0 | present=22 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (1, 6, 2026,
        22, 22, 0, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=2 | AIN720 | Kaushik Ramisetty | LOP 0 | present=21 leave=1
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (2, 6, 2026,
        22, 21, 1, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=3 | AIN480 | Santhosh N | LOP 0 | present=22 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (3, 6, 2026,
        22, 22, 0, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=4 | AIN714 | Pranav J | LOP 0 | present=21 leave=1
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (4, 6, 2026,
        22, 21, 1, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=5 | AIN712 | Aashi Garg | LOP 0 | present=22 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (5, 6, 2026,
        22, 22, 0, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=6 | AIN719 | Manana Ravikumar | LOP 0 | present=20 leave=2
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (6, 6, 2026,
        22, 20, 2, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=7 | AIN422 | Sowmya H R | LOP 0 | present=22 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (7, 6, 2026,
        22, 22, 0, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=8 | AIN393 | Subhash Marahanumaiah | LOP 0 | present=21 leave=1
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (8, 6, 2026,
        22, 21, 1, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=9 | AIN662 | Nikhil MP | LOP 0 | present=22 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (9, 6, 2026,
        22, 22, 0, 0, 22.0, 176.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=10 | AIN617 | Darshan N T | LOP 1 | present=21 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (10, 6, 2026,
        22, 21, 0, 1, 21.0, 168.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=13 | EMP0003 | Suraj M | LOP 2 | present=19 leave=1
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (13, 6, 2026,
        22, 19, 1, 2, 20.0, 160.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=14 | EMP0004 | rahul r | LOP 5 | present=17 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (14, 6, 2026,
        22, 17, 0, 5, 17.0, 136.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- id=16 | EMP0006 | aashi g | LOP 10 | present=12 leave=0
INSERT INTO monthly_attendance_summary
    (employee_id, month, year,
     total_working_days, present_days, leave_days, lop_days, payable_days,
     approved_timesheet_hours,
     attendance_status, timesheet_status, validation_status,
     issues_count, validation_notes,
     is_ready_for_payroll, is_frozen,
     finalized_by, finalized_at, frozen_by_id, frozen_at, snapshot_note,
     created_at, updated_at)
VALUES (16, 6, 2026,
        22, 12, 0, 10, 12.0, 96.0,
        'finalized', 'finalized', 'passed',
        0, NULL, 1, 0, NULL, NULL, NULL, NULL,
        'Dummy seed - payroll testing June 2026',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);


-- ────────────────────────────────────────────────────────────
-- STEP 5  --  Final verification SELECT
-- ────────────────────────────────────────────────────────────
SELECT
    e.employee_code,
    e.first_name || ' ' || COALESCE(e.last_name, '') AS employee_name,
    mas.total_working_days,
    mas.present_days,
    mas.leave_days         AS paid_leave_days,
    mas.lop_days,
    mas.payable_days,
    mas.validation_status,
    mas.is_ready_for_payroll,
    mas.is_frozen
FROM monthly_attendance_summary mas
JOIN employees e ON e.id = mas.employee_id
WHERE mas.month = 6
  AND mas.year  = 2026
ORDER BY mas.lop_days ASC, e.id ASC;
