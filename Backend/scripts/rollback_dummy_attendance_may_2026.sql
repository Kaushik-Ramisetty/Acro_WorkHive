-- ============================================================
-- ROLLBACK  --  Dummy Attendance Seed (June 2026)
-- Purpose  : Remove only the 13 dummy rows inserted by
--            seed_dummy_attendance_may_2026.sql
-- Safe     : Deletes ONLY month=6 year=2026 rows that have
--            snapshot_note = 'Dummy seed - payroll testing June 2026'
--            No other data is touched.
-- DB       : SQLite  --  Backend/hrms.db
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- STEP 1  --  Preview what will be deleted (read-only check)
-- ────────────────────────────────────────────────────────────
SELECT
    e.employee_code,
    e.first_name || ' ' || COALESCE(e.last_name, '') AS employee_name,
    mas.month,
    mas.year,
    mas.lop_days,
    mas.is_frozen,
    mas.snapshot_note
FROM monthly_attendance_summary mas
JOIN employees e ON e.id = mas.employee_id
WHERE mas.month         = 6
  AND mas.year          = 2026
  AND mas.snapshot_note = 'Dummy seed - payroll testing June 2026'
ORDER BY e.id;

-- ────────────────────────────────────────────────────────────
-- STEP 2  --  Delete only the dummy seed rows
-- ────────────────────────────────────────────────────────────
DELETE FROM monthly_attendance_summary
WHERE month         = 6
  AND year          = 2026
  AND snapshot_note = 'Dummy seed - payroll testing June 2026';

-- ────────────────────────────────────────────────────────────
-- STEP 3  --  Verify deletion: expect 0 rows
-- ────────────────────────────────────────────────────────────
SELECT
    COUNT(*) AS remaining_dummy_rows_for_june2026
FROM monthly_attendance_summary
WHERE month         = 6
  AND year          = 2026
  AND snapshot_note = 'Dummy seed - payroll testing June 2026';
