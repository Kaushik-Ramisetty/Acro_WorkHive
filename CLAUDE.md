# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two siblings under the repo root, run independently:

- `Backend/` — FastAPI + SQLAlchemy app (Python 3.11+). SQLite for dev (`hrms.db` auto-created on first boot), SQL Server for prod via `DATABASE_URL`.
- `Frontend/` — React 19 + Vite 6 + Tailwind 3 SPA. Talks to the backend at `VITE_API_URL` (default `http://localhost:8000`).

There is no monorepo tooling — `cd` into the relevant folder before running any command.

## Common commands

### Backend

```bash
cd Backend
python -m venv venv && venv\Scripts\activate          # Windows
pip install -r requirements.txt

python run.py                                          # uvicorn http://127.0.0.1:8000, --reload on
python run.py --no-reload                              # disable autoreload
python run.py --host 0.0.0.0 --port 8080               # custom bind

pytest -q                                              # run full test suite (tests/)
pytest tests/test_auth.py::test_login_success -q       # single test
celery -A app.tasks.celery_app worker --loglevel=info  # background jobs (OTP, leave scheduler, attendance)
celery -A app.tasks.celery_app beat   --loglevel=info  # cron-style schedule
```

`run.py` watches `app/`, `api/`, and `utils/` for reload — edits in any of the three subtrees trigger a restart. Pytest config lives in `pytest.ini`; the suite uses an in-memory SQLite when `TESTING=1`.

### Frontend

```bash
cd Frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # production bundle to dist/
npm run preview  # serve the built bundle locally
```

No lint / test scripts are wired in `package.json` yet.

## High-level architecture

This is a **unified monolith that merged two previously-independent codebases** — "Core HRMS" and "Onboarding". Both share one `Base`, one engine, one `.env`, and one JWT secret. Understanding this dual heritage is essential: the same `Employee` row is read/written by code from both worlds, and many files contain compatibility shims.

### Backend dual structure

- `Backend/app/` — **canonical Core HRMS package**. Entry point is `app/main.py`; all ORM models live in `app/models/`; routers under `app/routes/`; services under `app/services/`; Celery tasks under `app/tasks/`.
- `Backend/api/` — **onboarding namespace**. Routers + Pydantic schemas only. `api/models.py` is a **shim re-exporting from `app.models.*`** — both packages reference the same SQLAlchemy classes.
- `Backend/utils/` — onboarding-era utilities (JWT, crypto, email_service, id_generator). Has its own `jwt_auth.py` parallel to `app/core/security.py`.
- `Backend/database.py` — shim re-exporting `Base / engine / SessionLocal / get_db` from `app.db.*` so legacy onboarding imports keep working.

`app/main.py` is the single FastAPI app. On startup it (1) runs `Base.metadata.create_all`, (2) runs idempotent `ALTER TABLE` migrations to backfill onboarding columns onto older Core DBs, (3) seeds master data (departments, designations, leave types), and (4) mounts ~21 routers from both modules. No Alembic.

### The Employee model is the integration point

`app/models/employee.py` carries fields from both worlds and uses SQLAlchemy synonyms to satisfy onboarding code that expects capitalised attribute names:

- `Password = synonym("password_hash")` — same column, two attribute names.
- `Nationality = synonym("nationality")`, `Marital_status = synonym("marital_status")`.
- Onboarding-only columns: `official_email`, `is_activated`, `force_password_change`.
- `password_hash` is nullable so legacy `users`-table candidate rows don't trip NOT NULL.

When writing code that touches Employee, never assume a single source of truth for case — both forms hit the same column.

### Two coexisting auth surfaces

There are **two login endpoints**, both mounted in the merged app:

1. `POST /auth/login` (Core, 2FA) — validates against `Employee.password_hash` or `Employee.official_email`, mints a 6-digit OTP in Redis, then `POST /auth/verify-otp` issues a JWT via `app/core/security.create_access_token`. **JWT `sub` is `str(employee.id)`** — `app/core/deps.get_current_user` casts it back to `int`.
2. `POST /api/v1/auth/login` (onboarding legacy, no OTP) — matches `Employee.email` *or* `Employee.official_email`, *or* the legacy `users` table. **JWT `sub` must also be `str(employee.id)`** for Path A (employees) so that tokens it mints are accepted by the Core dependency. Path B (legacy `users` table, candidates only) keeps `sub=email` — candidates hit the candidate portal, not Core endpoints.

The frontend's `services/api.js` tries `/auth/login` first and **falls back to `/api/v1/auth/login` on 401**. Both flows share the same `JWT_SECRET`/`SECRET_KEY` env var (read with either name).

OTP delivery (`app/services/auth_service.py` + `app/tasks/otp_tasks.py`) routes to `official_email` when the employee is activated, else to personal `email`. This matters because converted employees authenticate with their official email and expect the OTP there.

### Candidate → Employee conversion

`api/Onboarding_Model/convert.py` is the bridge:

- Finds-or-creates an `Employee` row from a `Candidate` (matched by email).
- Assigns the seeded `"employee"` Role (`role_id` must be set or `/auth/me` returns `role: null` and the FE can't pick a dashboard).
- Calls `_initialize_leave_balances()` which writes Core's columns (`opening_balance / current_balance / used / reserved`), **not** the legacy onboarding ones (`total_allocated / carried_forward / pending / remaining`).
- Triggers an IT-credentials email; HR then calls `PUT /onboarding/activate/{id}` to set `official_email`, `Password`, `is_activated=True`, `force_password_change=True`.

`app/services/auth_service.authenticate()` also self-heals: if it loads an Employee with `role_id=NULL`, it backfills the `"employee"` role on the fly. This is the safety net for records created before the conversion was fixed to assign role_id.

### Leave system

- `LeaveType` rows are seeded in `app/main.py` (`_LEAVE_TYPES`). `LT002` is the canonical "Paid Leaves" type (quota 12). `LT005` is hidden by the FE (`Frontend/src/services/leave.js::LEAVE_TYPE_HIDDEN_IDS`) — a legacy id whose quota was folded into LT002.
- Leave balance math: `current_balance = opening_balance - used - reserved`. `reserved` = approved but not yet consumed.
- Two-stage approval chain: pending → manager-approved (`next_approver_role = hr`) → hr-approved (`status = approved`). A nightly Celery scheduler (02:00 UTC) marks `approved` requests `consumed` if the employee was absent on those dates, or creates a `WorkedOnLeaveRequest` exception if they were present.
- Old single-approver fields (`approved_by`, `approved_at`) coexist with the new chain fields (`manager_approved_*`, `hr_approved_*`); code must handle both shapes.

### Frontend architecture

- `src/routes/AppRoutes.jsx` — all routes. `/admin-dashboard/*`, `/manager-dashboard/*`, `/employee-dashboard/*`, `/candidate-dashboard`, `/vendor/bgv-review/:token` (public, token-gated), `/change-password`, `/login`.
- `src/context/AuthContext.jsx` — single global auth context. JWT in `localStorage` key `hrms.auth.token`, cached user in `hrms.auth.user`. `dashboardPathForRole()` normalises casing and defaults missing roles to `/employee-dashboard`.
- `src/services/api.js` — fetch-based HTTP client (axios is in `package.json` but unused). Auto-attaches `Authorization: Bearer`, auto-logs out + redirects to `/login` on any 401 from a non-auth endpoint. **The login wrapper falls through to `/api/v1/auth/login` on a 401** — keep this fallback alive when refactoring.
- Core API returns raw payloads; onboarding API wraps everything in `{success, message, data}` — `onboardingApi.js` unwraps `.data`.

### Background jobs (Celery beat)

| Schedule (UTC) | Task | Purpose |
|---|---|---|
| 01:30 daily | `attendance.daily_processing` | Build `AttendanceRecord` rows from previous day's punches |
| 02:00 daily | `leave.process_pending_consumption` | Mark approved leave consumed / raise `WorkedOnLeaveRequest` |
| 03:00 daily | `leave.expire_comp_off_credits` | Expire stale comp-off |
| 20:00 daily | `attendance.detect_missed_checkouts` | Flag unclosed punches |
| 09:00 Mon | `timesheet.submission_reminder` | Nag employees with drafts |

Redis is required for OTP and Celery. If Redis is down, OTP login fails. In dev, OTPs are printed to stdout (`[DEV OTP] user_id=… code=…`) when `APP_ENV` ≠ `production`.

## Pitfalls and constraints

- **No Alembic.** Schema changes go through `Base.metadata.create_all` + idempotent `ALTER` statements in `app/main.py::_run_onboarding_migrations`. Test the ALTER path against existing dev DBs.
- **Two response envelopes.** Core: raw JSON. Onboarding: `{success, message, data}`. Don't accidentally switch one to the other.
- **Two JWT decoders.** `app/core/deps.get_current_user` does `int(sub)`. `utils/jwt_auth.get_current_user` keeps `sub` as a string. Tokens minted with an email as `sub` will 401 against every Core endpoint.
- **`pyodbc` on Linux.** `requirements.txt` declares `pyodbc ; sys_platform != "linux"`. On Linux, switch `DATABASE_URL` to `mssql+pymssql://...` and enable that line.
- **Email simulation.** Empty `SMTP_USERNAME`/`SMTP_PASSWORD` (core) and `EMAIL_SIMULATE=true` (onboarding) both keep dev console-only. Real outbound mail needs both pairs configured.
- **Timezone.** All scheduler timestamps assume UTC; `Employee.time_zone` is stored but not used in calculations.
- **Soft delete is inconsistent.** `Employee.is_deleted` exists; `Candidate` has no equivalent — filter explicitly when querying.
- **No rate limiting** on login or OTP endpoints. If you add it, do it in middleware so both auth surfaces are covered.

## Environment variables

Both naming conventions are read at startup — pick one per env file, but set the `JWT_SECRET`/`SECRET_KEY` pair to the same value:

- `JWT_SECRET` / `SECRET_KEY` — JWT signing key (required).
- `JWT_ALGORITHM` / `ALGORITHM` — defaults to `HS256`.
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` / `ACCESS_TOKEN_EXPIRE_MINUTES` — defaults to `480` (8h).
- `PII_ENCRYPTION_KEY` — Fernet key for `aadhaar_encrypted` / `pan_encrypted` / `bank_account_encrypted` columns.
- `DATABASE_URL` — SQLAlchemy URL. Defaults to SQLite at `Backend/hrms.db`.
- `REDIS_URL` — OTP + Celery broker.
- `ALLOWED_ORIGINS` / `CORS_ALLOWED_ORIGINS` — union read at startup.
- `APP_ENV` — `production` disables the `[DEV OTP]` console banner and routes OTP delivery through Celery.
- `VITE_API_URL` (frontend) — backend base URL.
