# HRMS Attendance & Timesheet — Safe Integration Plan
**Target**: hrms_latest_frontend (hrms_integated_v4/hrms_integrated)  
**Source**: hrms_attendance (extracted from hrms_attendance.zip)  
**Date**: 2026-05-20  
**Author**: Principal HRMS Architect Integration Analysis

---

## 1. EXECUTIVE SUMMARY

This document covers the complete architectural analysis of both projects and the safe integration plan for merging Attendance + Timesheet workflows from the **source** (hrms_attendance) into the **main** project (hrms_integrated).

The main project is a production-grade HRMS monolith with:
- FastAPI + SQLAlchemy backend
- React 19 + Tailwind CSS 3 frontend
- Full dark/light theme system with `--hrms-*` CSS variables
- Existing attendance, timesheet, leave, onboarding, resource management modules
- JWT + OTP authentication with RBAC

The source project contains a **heavily enhanced version** of the Attendance and Timesheet modules with:
- 3x more backend route logic (attendance: 1106 vs 377 lines; timesheet: 1702 vs 464 lines)
- New multi-stage timesheet workflow (6 approval stages including external client approval)
- Comp-off, overtime, and weekly-off-change request workflows
- Finance portal (billing, utilization, project costing)
- Rich frontend attendance/timesheet components with week-aware hooks

---

## 2. FULL ARCHITECTURAL COMPARISON

### 2.1 BACKEND — Models

| Model/Table | Main Project | Source Project | Action |
|---|---|---|---|
| `attendance_logs` | ✅ Present | ✅ Present | No change |
| `validation_errors` | ✅ Present | ✅ Present | No change |
| `attendance_records` | ✅ Present | ✅ Present | No change |
| `attendance_exceptions` | ✅ Present | ✅ Present | No change |
| `regularization_requests` | ✅ Present | ✅ Present | No change |
| `regularization_attachments` | ✅ Present | ✅ Present | No change |
| `overtime_records` | ✅ Present | ✅ Present | No change |
| `attendance_reports` | ✅ Present | ✅ Present | No change |
| `payroll_attendance_summary` | ✅ Present | ✅ Present | No change |
| `weekly_off_change_requests` | ❌ Missing | ✅ Present | **ADD to attendance_records.py** |
| `projects` | ✅ Present (no billing_rate) | ✅ Present (+ billing_rate) | **ADD billing_rate column** |
| `tasks` | ✅ Present | ✅ Present | No change |
| `timesheets` | ✅ Present (no client fields) | ✅ Present (+ 12 client columns, UniqueConstraint) | **ADD 12 client columns + constraint** |
| `timesheet_entries` | ✅ Present (no is_billable) | ✅ Present (+ is_billable) | **ADD is_billable column** |
| `timesheet_payroll_sync` | ✅ Present | ✅ Present | No change |
| `timesheet_workflow_steps` | ❌ Missing | ✅ Present | **ADD TimesheetWorkflowStep model** |
| `jobs_log` | ❌ Missing | ✅ Present | **ADD jobs_log.py** |

### 2.2 BACKEND — Routes

| Route File | Main (lines) | Source (lines) | Action |
|---|---|---|---|
| `routes/attendance.py` | 377 | 1106 | **MERGE: add 15+ new endpoints** |
| `routes/timesheet.py` | 464 | 1702 | **MERGE: add 13+ new endpoints** |
| `routes/billing.py` | ❌ Missing | ✅ Present | **COPY** |
| `routes/hr.py` | ❌ Missing | ✅ Present | **COPY** |
| `routes/utilization.py` | ❌ Missing | ✅ Present | **COPY** |

#### New Attendance Endpoints (to merge):
- `GET /attendance/effective-hours` — single-day hours for logged-in employee
- `GET /attendance/weekly-hours` — 7-day hours summary for week
- `PATCH /attendance/admin/override` — admin force-mark attendance
- `POST /attendance/comp-off/request` — request comp-off for weekend work
- `GET /attendance/comp-off` — list employee's comp-off credits
- `POST /attendance/overtime` — submit overtime request
- `GET /attendance/overtime` — list overtime records
- `POST /attendance/weekly-off-request` — request weekly-off day change
- `GET /attendance/weekly-off-request` — list weekly-off requests
- `GET /attendance/regularization/me` — employee's own regularization requests
- `PATCH /attendance/exceptions/{exc_id}/resolve` — resolve an exception

#### New Timesheet Endpoints (to merge):
- `GET /timesheet/me` — employee's own timesheets
- `POST /timesheet/bulk-review` — manager bulk approve/reject
- `POST /timesheet/{id}/workflow/approve` — workflow step approve
- `POST /timesheet/{id}/workflow/reject` — workflow step reject
- `POST /timesheet/{id}/workflow/resubmit` — employee resubmit after rejection
- `GET /timesheet/{id}/workflow/steps` — workflow audit trail
- `GET /timesheet/{id}/workflow/billing-check` — billing/payroll readiness check
- `POST /timesheet/monthly-report` — submit monthly T&M report
- `GET /timesheet/monthly-report` — retrieve monthly report
- `GET /timesheet/{id}/monthly-detail` — monthly day-by-day breakdown
- `GET /timesheet/client-action` — external client approval link (tokenized)
- `POST /timesheet/client-action` — client approval/rejection form
- `GET /timesheet/{id}/mismatch-report` — variance breakdown

### 2.3 BACKEND — Services

| Service | Main | Source | Action |
|---|---|---|---|
| `attendance_engine.py` | ✅ (494 lines) | ✅ (743 lines) | **MERGE: add recompute_from_check_times, _next_record_id** |
| `attendance_digest.py` | ❌ Missing | ✅ Present | **COPY** |
| `comp_off_service.py` | ❌ Missing | ✅ Present | **COPY** |
| `cron_jobs.py` | ❌ Missing | ✅ Present | **COPY** |
| `timesheet_email.py` | ❌ Missing | ✅ Present | **COPY** |
| `token_service.py` | ❌ Missing | ✅ Present | **COPY** |

### 2.4 BACKEND — Schemas

| Missing Schemas (to add to schemas/attendance.py) |
|---|
| `AdminAttOverrideIn` |
| `CompOffRequestIn`, `CompOffRequestOut` |
| `OvertimeRequestIn`, `OvertimeRequestOut` |
| `WeeklyOffChangeRequestIn`, `WeeklyOffChangeRequestOut` |

### 2.5 FRONTEND — Pages

| Page | Main | Source | Action |
|---|---|---|---|
| `employee/screens/AttendancePage.jsx` | ✅ (387 lines) | ✅ (1773 lines) | **REPLACE with source (richer)** |
| `employee/screens/TimesheetsPage.jsx` | ✅ (297 lines) | ✅ (719 lines) | **REPLACE with source (richer)** |
| `admin/timesheets/TimesheetManagementPage.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `finance/` folder (6 files) | ❌ Missing | ✅ Present | **ADD ALL** |
| `manager/timesheets/ManagerTimesheetReviewPage.jsx` | ✅ Present | ✅ Present | Verify — likely same |

### 2.6 FRONTEND — Components

| Component | Main | Source | Action |
|---|---|---|---|
| `components/Timesheets/ActionBar.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/EntriesTable.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/FilterBar.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/MetricCards.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/SubmitModal.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/Toast.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/WeekHeader.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/Timesheets/index.jsx` | ❌ Missing | ✅ Present | **ADD** |
| `components/attendance/AttendanceGrid.jsx` | ❌ Missing | ✅ Present | **ADD** |

### 2.7 FRONTEND — Services

| Service | Main | Source | Action |
|---|---|---|---|
| `services/attendance.js` | ✅ (partial) | ✅ (full) | **MERGE: add adminOverride, effectiveHours, weeklyHours, managerApi, compOffApi, overtimeApi, weeklyOffApi** |
| `services/timesheet.js` | ✅ (partial) | ✅ (full) | **MERGE: add bulkReview, workflow, monthlyReport methods** |
| `services/billing.js` | ❌ Missing | ✅ Present | **ADD** |
| `services/utilization.js` | ❌ Missing | ✅ Present | **ADD** |

### 2.8 FRONTEND — Hooks & Utils

| File | Main | Source | Action |
|---|---|---|---|
| `hooks/useWeekAttendance.js` | ❌ Missing | ✅ Present | **ADD** |
| `hooks/useTimesheets.js` | ❌ Missing | ✅ Present | **ADD** |
| `utils/attendanceUtils.js` | ❌ Missing | ✅ Present | **ADD** |
| `utils/weekHelpers.js` | ❌ Missing | ✅ Present | **ADD** |
| `utils/exportXlsx.js` | ❌ Missing | ✅ Present | **ADD** |

### 2.9 FRONTEND — Routing & Layout

| Item | Main | Source | Action |
|---|---|---|---|
| `/finance-dashboard/*` route | ❌ Missing | ✅ Present | **ADD to AppRoutes.jsx** |
| `layouts/FinanceLayout.jsx` | ❌ Missing | ✅ Present | **ADD** |
| Finance sidebar config | ❌ Missing | ✅ Present | **ADD to sidebarConfig.js** |
| Admin timesheets route | ❌ Missing | ✅ Present | **ADD to AppRoutes.jsx** |

---

## 3. RISK ASSESSMENT

### HIGH RISK AREAS

| Risk | Impact | Mitigation |
|---|---|---|
| `UniqueConstraint` on `timesheets(employee_id, period_start, period_end)` | May fail if duplicate rows exist | Add constraint with IF NOT EXISTS / try-except |
| Replacing `employee/screens/AttendancePage.jsx` | Could break existing check-in/out UI | Theme-adapt carefully, test check-in/out flow |
| Source has NO dark theme support | All source components display broken in dark mode | Apply `--hrms-*` CSS variables to all new components |
| Source frontend uses `axios`; main uses `fetch` | Incompatible API client | Source services already converted to use `api` (fetch wrapper) |
| `auto_create_timesheet_entry()` in attendance routes | Could create duplicate timesheet entries | Only runs for `employee_type = client_site`; safe |
| `token_service.py` generates single-use JWT for external clients | Could expose timesheet data | Only used in explicit client-action route; safe |

### MEDIUM RISK

| Risk | Impact | Mitigation |
|---|---|---|
| Source `billing.py`/`hr.py`/`utilization.py` routes may have different auth assumptions | Could allow unauthorized access | Verify `Depends(get_current_user)` + role checks present |
| `recompute_from_check_times()` in attendance_engine changes AttendanceRecord data | Could affect existing records | Only called on regularization approval; existing data safe |
| Finance pages use heavy inline styles with hardcoded hex colors | Broken dark mode | Replace inline hex colors with `--hrms-*` vars |

### LOW RISK

| Risk | Mitigation |
|---|---|
| New model classes with `Base.metadata.create_all` | Tables created on startup; existing data untouched |
| New service files (copy, no modifications) | Self-contained; no side effects on import |
| Adding new frontend utility files | Zero side effects; pure functions |

---

## 4. DATABASE MIGRATION STRATEGY

All migrations are **non-destructive ADD-ONLY** operations. No columns are dropped or renamed.

### New Tables (safe to create):
```sql
-- weekly_off_change_requests
CREATE TABLE IF NOT EXISTS weekly_off_change_requests (...)

-- timesheet_workflow_steps
CREATE TABLE IF NOT EXISTS timesheet_workflow_steps (...)

-- jobs_log (if needed)
CREATE TABLE IF NOT EXISTS jobs_log (...)
```

### New Columns (idempotent ALTER):
```sql
-- projects table
ALTER TABLE projects ADD COLUMN billing_rate FLOAT

-- timesheets table (12 client-approval columns)
ALTER TABLE timesheets ADD COLUMN client_manager_id INTEGER
ALTER TABLE timesheets ADD COLUMN client_manager_name VARCHAR(200)
ALTER TABLE timesheets ADD COLUMN client_manager_email VARCHAR(255)
ALTER TABLE timesheets ADD COLUMN client_token VARCHAR(500)
ALTER TABLE timesheets ADD COLUMN client_token_expires_at DATETIME
ALTER TABLE timesheets ADD COLUMN client_email_sent_at DATETIME
ALTER TABLE timesheets ADD COLUMN client_email_status VARCHAR(50)
ALTER TABLE timesheets ADD COLUMN client_approved_at DATETIME
ALTER TABLE timesheets ADD COLUMN client_rejected_at DATETIME
ALTER TABLE timesheets ADD COLUMN client_review_comment VARCHAR(1000)
ALTER TABLE timesheets ADD COLUMN reminder_count INTEGER DEFAULT 0
ALTER TABLE timesheets ADD COLUMN has_mismatch INTEGER DEFAULT 0

-- timesheet_entries table
ALTER TABLE timesheet_entries ADD COLUMN is_billable INTEGER DEFAULT 1
```

### UniqueConstraint (deferred — apply after data validation):
```sql
-- Only apply if no duplicate (employee_id, period_start, period_end) rows exist
CREATE UNIQUE INDEX IF NOT EXISTS uq_timesheet_emp_period
ON timesheets(employee_id, period_start, period_end)
```

---

## 5. THEME INTEGRATION STRATEGY

The source project has **NO dark theme support**. The main project has a comprehensive enterprise slate palette via CSS variables.

### Automatic Coverage (via main's index.css dark overrides):
The main project's `index.css` already handles these Tailwind classes in dark mode:
- `bg-white` → `var(--hrms-surface)`
- `bg-slate-50` → `var(--hrms-surface-2)`
- `text-gray-*`, `text-slate-*` → mapped to `--hrms-text*` vars
- `border-gray-*`, `border-slate-*` → `var(--hrms-border)`

### Manual Fixes Required (inline styles in source):
Pages using `style={{ background: '#fff', color: '#0F172A' }}` patterns:
- `TimesheetManagementPage.jsx` — 90+ inline style objects
- `finance/BillingPage.jsx`, `finance/UtilizationPage.jsx` — inline styled
- `components/Timesheets/` components — partial inline styles

**Approach**: Replace hardcoded hex values with CSS variables:
- `'#ffffff'` / `'#fff'` / `'white'` → `var(--hrms-surface)`
- `'#f8fafc'` / `'#F8FAFC'` → `var(--hrms-surface-2)`
- `'#0F172A'` / `'#0f172a'` → `var(--hrms-text)`
- `'#475569'` → `var(--hrms-text-2)`
- `'#64748B'` / `'#94A3B8'` → `var(--hrms-text-muted)` / `var(--hrms-text-faint)`
- `'#E2E8F0'` / `'#e2e8f0'` → `var(--hrms-border)`
- `'#EFF6FF'` accent bg → use `var(--hrms-accent-soft)`

---

## 6. FILES TO PRESERVE (DO NOT TOUCH)

```
Backend/app/routes/auth.py
Backend/app/routes/leave.py
Backend/app/routes/employee.py
Backend/app/routes/admin.py
Backend/app/routes/manager.py
Backend/app/routes/notifications.py
Backend/app/routes/search.py
Backend/app/routes/holidays.py
Backend/app/routes/delegates.py
Backend/app/routes/leave_capacity.py
Backend/app/routes/encashment.py
Backend/app/routes/policies.py
Backend/app/routes/secure_uploads.py
Backend/app/routes/announcements.py
Backend/app/services/leave_engine.py
Backend/app/services/leave_state_machine.py
Backend/app/services/leave_ledger.py
Backend/app/services/leave_accrual.py
Backend/app/services/leave_workflow_v2.py
Backend/app/services/leave_validation.py
Backend/app/services/payroll_bridge.py
Backend/app/services/malware_scanner.py
Backend/app/services/secure_upload_service.py
Backend/app/services/policy_service.py
Backend/app/core/
Backend/api/                    (entire onboarding module)
Frontend/src/context/
Frontend/src/components/ (all existing — only ADD new ones)
Frontend/src/pages/admin/employees/
Frontend/src/pages/admin/leave/
Frontend/src/pages/admin/policies/
Frontend/src/pages/admin/bench/
Frontend/src/pages/admin/teams/
Frontend/src/pages/candidate/
Frontend/src/pages/vendor/
Frontend/src/pages/shared/
Frontend/src/pages/employee/parts/
Frontend/src/pages/manager/leave/
Frontend/src/pages/manager/compoff/
Frontend/src/pages/manager/approvals/
Frontend/src/pages/manager/announcements/
Frontend/src/data/sidebarConfig.js  (EDIT only — add finance, don't touch others)
Frontend/src/routes/AppRoutes.jsx   (EDIT only — add finance route, don't touch others)
```

---

## 7. FILES TO MODIFY

### Backend
| File | Change |
|---|---|
| `Backend/app/models/attendance_records.py` | ADD `WeeklyOffChangeRequest` class |
| `Backend/app/models/project.py` | ADD columns + `TimesheetWorkflowStep` class |
| `Backend/app/models/__init__.py` | ADD exports for new models |
| `Backend/app/services/attendance_engine.py` | ADD `recompute_from_check_times`, `_next_record_id` |
| `Backend/app/schemas/attendance.py` | ADD 7 new Pydantic schemas |
| `Backend/app/routes/attendance.py` | ADD 11 new route handlers |
| `Backend/app/routes/timesheet.py` | ADD 13 new route handlers |
| `Backend/app/main.py` | ADD 3 router imports + registrations + DB migration ALTERs |

### Frontend
| File | Change |
|---|---|
| `Frontend/src/services/attendance.js` | ADD 8 new API methods + 4 new API objects |
| `Frontend/src/services/timesheet.js` | ADD bulk-review, workflow, monthly-report methods |
| `Frontend/src/routes/AppRoutes.jsx` | ADD finance-dashboard route + admin timesheets route |
| `Frontend/src/data/sidebarConfig.js` | ADD finance role sidebar navigation |
| `Frontend/src/pages/admin/index.jsx` | ADD TimesheetManagement export |
| `Frontend/src/pages/employee/screens/AttendancePage.jsx` | REPLACE with richer source (theme-adapted) |
| `Frontend/src/pages/employee/screens/TimesheetsPage.jsx` | REPLACE with richer source (theme-adapted) |

---

## 8. FILES TO CREATE (NEW)

### Backend
| File | Source |
|---|---|
| `Backend/app/services/attendance_digest.py` | Copy from source |
| `Backend/app/services/comp_off_service.py` | Copy from source |
| `Backend/app/services/cron_jobs.py` | Copy from source |
| `Backend/app/services/timesheet_email.py` | Copy from source |
| `Backend/app/services/token_service.py` | Copy from source |
| `Backend/app/routes/billing.py` | Copy from source |
| `Backend/app/routes/hr.py` | Copy from source |
| `Backend/app/routes/utilization.py` | Copy from source |

### Frontend
| File | Source |
|---|---|
| `Frontend/src/utils/attendanceUtils.js` | Copy from source |
| `Frontend/src/utils/weekHelpers.js` | Copy from source |
| `Frontend/src/utils/exportXlsx.js` | Copy from source |
| `Frontend/src/hooks/useWeekAttendance.js` | Copy from source |
| `Frontend/src/hooks/useTimesheets.js` | Copy from source |
| `Frontend/src/services/billing.js` | Copy from source |
| `Frontend/src/services/utilization.js` | Copy from source |
| `Frontend/src/components/Timesheets/*.jsx` (8 files) | Copy + theme-adapt |
| `Frontend/src/components/attendance/AttendanceGrid.jsx` | Copy + theme-adapt |
| `Frontend/src/layouts/FinanceLayout.jsx` | Copy from source |
| `Frontend/src/pages/admin/timesheets/TimesheetManagementPage.jsx` | Copy + theme-adapt |
| `Frontend/src/pages/finance/` (7 files) | Copy + theme-adapt |

---

## 9. ROLLBACK STRATEGY

Since no files are deleted and all model changes are additive:

1. **Backend rollback**: Revert `attendance.py`, `timesheet.py` routes to original. New tables/columns do not harm existing functionality even if unused.
2. **Frontend rollback**: Revert `AppRoutes.jsx`, `sidebarConfig.js`, `attendance.js`, `timesheet.js`, and the two upgraded pages to their git-committed originals.
3. **Database**: New tables/columns are nullable — existing data is never at risk. The UniqueConstraint can be dropped if it causes issues.

---

## 10. TESTING CHECKLIST

### Backend
- [ ] `GET /attendance/today` still works after route merge
- [ ] `POST /attendance/check-in` still works
- [ ] `POST /attendance/check-out` still works
- [ ] `GET /attendance/logs` still works
- [ ] `GET /attendance/records` still works
- [ ] `POST /attendance/regularization` still works
- [ ] `GET /timesheet/projects` still works
- [ ] `POST /timesheet` still works
- [ ] `GET /timesheet` still works
- [ ] `POST /timesheet/{id}/review` still works
- [ ] New: `GET /attendance/effective-hours` returns 200
- [ ] New: `GET /attendance/weekly-hours` returns 7-day array
- [ ] New: `PATCH /attendance/admin/override` returns 200 for admin
- [ ] New: `GET /timesheet/{id}/workflow/steps` returns steps array
- [ ] New: `/billing/*` endpoints accessible to finance role
- [ ] Server starts without errors after all changes

### Frontend
- [ ] Check-in / check-out buttons work in dark mode
- [ ] Check-in / check-out buttons work in light mode
- [ ] Attendance calendar renders correctly
- [ ] Timesheet weekly grid renders correctly
- [ ] Timesheet submit flow works
- [ ] Manager timesheet review works
- [ ] Finance dashboard loads for finance role
- [ ] No white backgrounds in dark mode
- [ ] No unreadable text in dark mode
- [ ] Sidebar shows correct items per role
- [ ] Finance role sees finance-dashboard navigation
- [ ] Admin timesheets route loads
- [ ] Existing admin pages (employees, leave, policies) unaffected
- [ ] Existing manager pages unaffected

---

## 11. KNOWN LIMITATIONS

1. **External client token approval** (`/timesheet/client-action` with single-use JWT tokens) requires `token_service.py` to be configured with a proper `CLIENT_SECRET` env variable. This will gracefully 500 if not set.

2. **attendance_digest.py** sends digest emails — requires SMTP configured in `.env`.

3. **Finance billing_rate calculations** require `Project.billing_rate` to be set per project — defaults to NULL/0 for existing projects.

4. **UniqueConstraint on timesheets** — adding this constraint to an existing database may fail if duplicate rows exist (same employee + period). The idempotent migration skips this safely; manual deduplication may be needed in production.

5. **Source components missing `workflow/statuses.js`** — the `useTimesheets.js` hook references `WF` from `components/Timesheets/workflow/statuses`. This file must be created.

---
*Integration plan complete. Safe to proceed with implementation.*
