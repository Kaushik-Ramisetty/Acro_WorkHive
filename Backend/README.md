# HRMS — Unified (Core + Onboarding)

A single FastAPI backend that merges two previously-independent codebases:

- **Core HRMS** — auth/2FA, attendance, leave, timesheet, holidays, notifications, search, admin/manager/employee role surfaces, Celery-driven background jobs.
- **Onboarding** — candidates, offer letters (PDF), document upload, BGV (Background Verification), candidate→employee conversion, IT credential workflow, vendor + admin + candidate portals.

Both modules share a single `Base`, single engine, single `.env`, and a common JWT secret so tokens issued by either auth flow are accepted everywhere.

---

## Quick start

Requires Python 3.11+. Redis is optional in dev (Core's Celery falls back to no-op when unreachable).

```bash
cd Backend
python -m venv venv
# Windows:  venv\Scripts\activate
# Linux:    source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env       # then open .env and replace the secrets

python run.py              # http://127.0.0.1:8000  (Swagger at /docs)
```

The first boot creates `hrms.db` (SQLite), runs idempotent ALTERs to backfill onboarding columns onto older DBs, and seeds master data (15 departments, 26 designations, 7 leave types).

---

## Folder layout

```
Backend/
├── app/                        ← Core HRMS — canonical package
│   ├── main.py                 ← single FastAPI app (mounts ALL routers)
│   ├── core/{config,security,deps}.py
│   ├── db/{base,session}.py    ← one Base, one engine
│   ├── models/                 ← all ORM models, including merged onboarding/
│   ├── routes/                 ← /auth, /admin, /manager, /employee, /leave,
│   │                              /attendance, /timesheet, /holidays,
│   │                              /notifications, /search
│   ├── schemas/, services/, tasks/, utils/
├── api/                        ← Onboarding namespace
│   ├── models.py               ← shim re-exporting from app.models.*
│   ├── Department_Model/       ← /departments
│   ├── Designation_Model/      ← /designations
│   ├── Employee_Model/         ← /employees (HR list/CRUD)
│   └── Onboarding_Model/       ← candidates, offers, BGV, convert, workflow
├── utils/                      ← onboarding utilities (jwt_auth, crypto,
│                                  email_service, id_generator, …)
├── tests/                      ← onboarding's pytest suite (conftest patches DB)
├── static/                     ← onboarding form templates (CIF-BGV-Form.docx)
├── uploads/                    ← runtime documents / offers
├── database.py                 ← shim → app.db.{base,session}.*
├── seed.py                     ← Core's seed/import-from-Excel utility
├── cleanup_leaves.py
├── run.py                      ← uvicorn launcher
├── requirements.txt            ← single merged dependency tree
├── .env.example, .env, .gitignore
└── README.md
```

---

## URL map

### Core HRMS (no `/api/v1` prefix)

| Path                 | Purpose                            |
|----------------------|------------------------------------|
| `POST /auth/login`        | step 1 of 2FA — email + password   |
| `POST /auth/verify-otp`   | step 2 — issue JWT                  |
| `POST /auth/resend-otp`   | re-send OTP                         |
| `GET  /auth/me`           | JWT-authenticated current-user      |
| `/admin/*`                | admin surface (RBAC: admin)         |
| `/manager/*`              | manager surface (RBAC: manager+)    |
| `/employee/*`             | self-service (RBAC: emp/mgr/admin)  |
| `/leave/*`                | leave engine (apply, approve)       |
| `/attendance/*`           | attendance / regularization         |
| `/timesheet/*`             | timesheet entries                   |
| `/holidays/*`              | holiday list                        |
| `/notifications/*`         | notifications                       |
| `/search/*`                | global search                       |

### Onboarding

| Path                                 | Purpose                                        |
|--------------------------------------|------------------------------------------------|
| `POST /api/v1/auth/login`            | single-step login (employees + portal users)   |
| `POST /api/v1/auth/change-password`  | first-login forced password change             |
| `/departments/*`                     | HR departments CRUD                            |
| `/designations/*`                    | HR designations CRUD                           |
| `/employees/*`                       | HR employees mass-CRUD (list/create)           |
| `/candidates/*`                      | candidate lifecycle                            |
| `/offer/*`                           | generate / send / accept offers                |
| `/bgv/*`                             | BGV admin operations                           |
| `/api/v1/bgv/*`                      | BGV vendor portal (token-gated)                |
| `/api/v1/admin/*`                    | onboarding admin portal                        |
| `/api/v1/...`                        | candidate portal                               |
| `/onboarding/*`                      | IT credential request, activation, mgmt        |
| `POST /convert/{candidate_id}`       | candidate → employee conversion                |
| `GET  /uploads/{path}`               | static-served candidate documents              |

Swagger lists everything at **`/docs`**.

---

## What changed during the merge

### Code & files moved

- **All Core HRMS code** kept under `app/` exactly as-is — same routes, services, models, tasks, schemas.
- **All Onboarding code** kept under `api/`, `utils/`, `static/`, `tests/` exactly as-is. *No imports were rewritten.* Two compatibility shims handle the cross-talk:
  - `database.py` re-exports `Base / engine / SessionLocal / get_db / check_db_connection` from `app.db.*`.
  - `api/models.py` re-exports `Department / Designation / Employee / Candidate / …` from `app.models`.
- Removed onboarding's standalone `main.py` — the merged app boots from `app.main:app`.
- Removed onboarding `*.bak` files (left over from earlier dev iterations).
- Removed onboarding `venv/` and `pytest-cache-files-*/`.

### Model unification

- **`Employee`** (`app/models/employee.py`) — extended to carry both worlds:
  - Core fields kept untouched.
  - `Password = synonym("password_hash")` — onboarding code that reads/writes `emp.Password` works against the same column Core uses.
  - `Nationality = synonym("nationality")` and `Marital_status = synonym("marital_status")` — same trick for the capitalised onboarding aliases.
  - New nullable columns: `official_email`, `is_activated`, `force_password_change` for the IT credential workflow.
  - `password_hash` made nullable so candidate-only rows from the legacy `users` table don't trip a NOT-NULL violation.
- **`Designation`** (`app/models/designation.py`) — added optional `department_id` FK (used by the Onboarding HR module).
- **`onboarding.py`** (new file in `app/models/`) — adds the onboarding-only tables (`candidates`, `candidate_documents`, `bgv_checks`, `bgv_tokens`, `onboarded_employees`, `users`) plus the `CandidateStatus` / `BGVStatus` / `DocumentStatus` / `OnboardedEmployeeStatus` / `UserRole` enums and the `CANDIDATE_TRANSITIONS` state-machine map.

### Behavioural patches

- **`api/Onboarding_Model/convert.py`** — `_initialize_leave_balances()` rewritten to write Core's leave-balance columns (`opening_balance / current_balance / used / reserved`) instead of the onboarding-only ones (`total_allocated / carried_forward / pending / remaining`). Same data, different field names. Onboarding's `id Integer` was generating colliding integer rows; it now generates a String key like `LB-{employee_id}-{leave_type_id}-{year}` (within the 20-char Core constraint).
- **`utils/jwt_auth.py`** — `_secret()` / `_ALGORITHM` / `_DEFAULT_EXPIRE_MIN` accept either the onboarding-style env names (`SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`) or the core-style names (`JWT_SECRET`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). Tokens issued by either auth flow are now mutually verifiable.
- **`utils/crypto.py`** — `encrypt_pii*()` / `decrypt_pii*()` now return / accept `str` so the same Fernet ciphertext fits Core's `String(255)` columns *and* the onboarding code that previously expected `bytes`. Backwards-compatible with both LargeBinary (legacy) and VARCHAR (new) storage.

### Configuration

- Single `.env` / `.env.example` exposing **both** sets of env names:
  - `JWT_SECRET=` and `SECRET_KEY=` (set them to the same value).
  - `ALLOWED_ORIGINS=` and `CORS_ALLOWED_ORIGINS=` (union read at startup).
  - `DATABASE_URL=` driven by Core's settings; `DB_ENGINE` / `SQLITE_PATH` retained so Onboarding's `database.py`-style users still work.
- `.gitignore` extended to cover both projects' artifacts (`uploads/{documents,offers}/`, `pytest-cache-files-*/`, `*.db`, `*.bak`, `.env`).

### Single startup pipeline

`app/main.py` boots in one place and:

1. Calls `Base.metadata.create_all(...)` — every table from both sides registers on the unified `Base`, so a single create-all builds the whole schema.
2. Runs the onboarding-introduced idempotent `ALTER TABLE` migrations (column adds; safe re-runs).
3. Seeds master data (departments, designations, leave types).
4. Mounts every router from both modules. No collisions — both auth surfaces coexist, and the route prefixes are disjoint (`/auth/*` vs `/api/v1/auth/*`, `/employee` (singular) vs `/employees`, `/admin` vs `/api/v1/admin`).

---

## Build for production

```bash
pip install -r requirements.txt --no-deps   # if you've vendored a wheelhouse
export APP_ENV=production
export JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
export SECRET_KEY=$JWT_SECRET
export PII_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
export DATABASE_URL="mssql+pyodbc://user:pwd@host:1433/HRMS?driver=ODBC+Driver+17+for+SQL+Server"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

For the Celery-backed jobs (OTP delivery, audit logging, leave scheduler):

```bash
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat   --loglevel=info
```

---

## Risks and edge cases

- **Two auth surfaces** are intentional. Frontends should pick *one* per route. Both verify the same JWT secret, so a token from `/api/v1/auth/login` works against `/auth/me` if the JWT subject can be coerced — Core's `get_current_user` casts `sub` to `int` (employee id), while onboarding's `get_current_user` keeps `sub` as the email string. Cross-flow calls that hit the *opposite* dependency will 401. The recommended pattern is to consolidate on the onboarding-style flow for new portal work and keep the 2FA flow only for the existing admin/employee dashboards.
- **Legacy `users` table** is preserved (candidates and pre-conversion portal logins). The seeder & `_backfill_user_records` helper from the original onboarding `main.py` are *not* run on every boot in the merged app — they were dev-only fix-up scripts. Re-add them as a one-off CLI command if you ever import data from a pre-merge DB.
- **Synonyms versus columns.** `Employee.Password` and `Employee.password_hash` resolve to *one* column. Two writes in the same transaction can race; the last write wins. No code path currently writes both.
- **`employees` constraints.** Core allows `department_id` / `designation_id` / `date_of_joining` to be NULL; onboarding's strict `_run_migrations` originally made them NOT NULL. The unified model keeps them nullable so existing seeded rows stay valid and the candidate→employee conversion can fill them in lazily. Conversion still validates the FKs at the API layer.
- **Leave balance schema.** Core's columns (`opening_balance / current_balance / reserved / used`) are canonical now. The onboarding `convert.py` was updated to write into them; any external scripts that write `total_allocated / carried_forward / remaining / pending` will silently no-op.
- **`pyodbc` on Linux.** The `requirements.txt` declares `pyodbc ; sys_platform != "linux"` because pip can't compile pyodbc without unixODBC headers. On Linux servers, switch `DATABASE_URL` to `mssql+pymssql://...` and uncomment the `pymssql` line.
- **Email simulation.** `EMAIL_SIMULATE=true` (onboarding) and empty `SMTP_USERNAME`/`SMTP_PASSWORD` (core) both keep the dev experience console-only. Real outbound mail needs both pairs configured.
- **Frontend.** Neither uploaded zip contained a frontend; the merge is backend-only. The onboarding code base assumes a Vite (5173) or CRA/Next (3000) frontend — both are added to the default CORS list.

---

## Running the test suite

```bash
cd Backend
pytest -q
```

Onboarding's tests (`tests/conftest.py`) provision an in-memory SQLite via `TESTING=1` and assume the legacy onboarding behaviour. They are kept in the merged tree for regression coverage; adapt them as you migrate features off the onboarding-style imports.
