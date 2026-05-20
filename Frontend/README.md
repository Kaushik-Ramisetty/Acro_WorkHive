# HRMS — Unified Frontend (React + Vite + Tailwind)

A single React 19 / Vite 6 / Tailwind 3 frontend that merges the Core HRMS UI
(admin / manager / employee dashboards, leave, attendance, regularization,
comp-off, timesheet, OTP login) with the Onboarding module's screens
(candidate portal, vendor BGV review, change-password, admin Onboarding tab).

## Quick start

```bash
cd Frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # production bundle in dist/
```

The frontend talks to the merged FastAPI backend at the URL set by
`VITE_API_URL` (default: `http://localhost:8000`). The same value is
re-exported as `VITE_API_BASE_URL` for any onboarding-domain code that
expected the older variable name.

## What the merge added

- **Components** — `Modal.jsx`, `PhoneInput.jsx` (used by the onboarding admin tab).
- **Pages**
  - `pages/candidate/CandidateDashboard.jsx` — candidate self-service portal.
  - `pages/vendor/VendorBGVReview.jsx` — public, token-based BGV vendor portal.
  - `pages/employee/ChangePasswordPage.jsx` — forced first-login password change.
  - `pages/admin/screens/Onboarding.jsx` — the candidate→employee workflow UI.
- **Services** — `candidateApi.js`, `onboardingApi.js`, `vendorApi.js` (now
  share the same JWT and base URL as Core's `services/api.js`).
- **Config shims** — `config/api.js` and `config/auth.js` (re-export Core's
  base URL and token getter, so the onboarding service files don't need
  any import edits).
- **Routes** — `/candidate-dashboard`, `/vendor/bgv-review/:token`,
  `/change-password` added to `routes/AppRoutes.jsx`. The admin
  Onboarding tab at `/admin-dashboard/onboarding` now renders the real
  screen instead of the placeholder.
- **AuthContext** — `dashboardPathForRole()` now recognises the
  `'candidate'` role and routes to `/candidate-dashboard`.

## What was kept untouched

Every existing Core screen — admin/manager/employee dashboards, leave UI,
attendance, regularization, comp-off, timesheet, OTP login — preserved
exactly as-is.

## Token & API URL

Both auth flows now use **one** `localStorage` key (`hrms.auth.token`) and
**one** API base URL. Anywhere the onboarding code did
`authHeaders({...})` or `import { BASE } from '../config/api'`, it now
reads from Core's `services/api.js`. Single token, single client.
