/**
 * Shared Settings page — used by Admin, Manager and Employee dashboards.
 *
 * Visual style intentionally mirrors the Employee dashboard (Tailwind-based,
 * teal accent #14b8a6) so all three roles get a consistent experience.
 *
 * Role-aware behaviour
 * --------------------
 * - Reads the current user from AuthContext (no props required).
 * - Notification list is role-specific so each role only sees relevant toggles.
 * - Persisted-state keys are namespaced per role so preferences don't bleed
 *   across accounts that share the same browser.
 *
 * Usage
 * -----
 *   import SettingsPage from '../../components/SettingsPage';
 *   // Then render <SettingsPage /> anywhere — works for admin, manager, employee.
 */
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { usePersistedState, useSaveFeedback } from "../hooks/usePersistedState";

// ── Tab definitions ─────────────────────────────────────────────────────────
const TABS = [
  { id: "profile",       label: "Profile",       icon: "👤" },
  { id: "security",      label: "Security",      icon: "🔒" },
  { id: "notifications", label: "Notifications", icon: "🔔" },
  { id: "appearance",    label: "Appearance",    icon: "🎨" },
];

// ── Role-specific notification definitions ──────────────────────────────────
const NOTIFS_BY_ROLE = {
  admin: [
    ["New Employee Onboarding",  "When a new employee completes onboarding",         true],
    ["Leave Requests",           "When employees submit leave applications",         true],
    ["Claims Submitted",         "When new expense claims are awaiting review",      false],
    ["Payroll Alerts",           "Monthly payroll processing reminders",             true],
    ["Performance Cycles",       "When new review cycles are initiated",             true],
    ["System Announcements",     "Important system updates and maintenance",         false],
  ],
  hr: [
    ["New Employee Onboarding",  "When a new employee completes onboarding",         true],
    ["Leave Requests",           "When employees submit leave applications",         true],
    ["Payroll Alerts",           "Monthly payroll processing reminders",             true],
    ["System Announcements",     "Important system updates and maintenance",         true],
  ],
  manager: [
    ["Leave Request Updates",    "When your team submits or updates leave requests", true],
    ["Team Attendance Alerts",   "Alerts when team members miss check-in",          true],
    ["Timesheet Reviews",        "When timesheets are submitted for your approval",  true],
    ["Performance Reviews",      "When review cycle tasks are assigned to you",     false],
    ["Meeting Reminders",        "Reminders 15 minutes before scheduled meetings",   true],
  ],
  employee: [
    ["Email — leave updates",    "Receive emails when leave requests are approved/rejected", true],
    ["Email — payslip ready",    "Receive an email when payslip is generated",              true],
    ["Push — daily attendance",  "Reminder if you haven't checked in by 10 AM",            false],
    ["Push — meetings & events", "Reminders 15 minutes before scheduled events",           true],
    ["Weekly digest",            "Summary of activity each Monday morning",                true],
  ],
};

// ── Theme options ────────────────────────────────────────────────────────────
const THEME_OPTIONS = [
  {
    id: "light",
    label: "Light",
    description: "Clean, bright surface — best for daytime.",
    preview: { surface: "#FFFFFF", card: "#F8FAFC", accent: "#14b8a6", text: "#0F172A", mutedText: "#94A3B8" },
  },
  {
    id: "dark",
    label: "Dark",
    description: "Easy on the eyes in low-light environments.",
    preview: { surface: "#0F172A", card: "#1E293B", accent: "#14b8a6", text: "#F8FAFC", mutedText: "#94A3B8" },
  },
];

// ── Small local atoms (Tailwind, no external UI library needed) ──────────────
function PageTitle({ title, sub }) {
  return (
    <div className="flex items-center justify-between mb-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{title}</h1>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function Card({ children, className = "", padding = "p-5" }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-100 shadow-sm ${padding} ${className}`}>
      {children}
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────
function NotifList({ role }) {
  const notifs = NOTIFS_BY_ROLE[role] || NOTIFS_BY_ROLE.employee;
  const storageKey = `hrms.settings.${role}.notifs`;
  const [state, setState] = usePersistedState(storageKey, notifs.map(([, , on]) => on));
  const flags = state.length === notifs.length ? state : notifs.map(([, , on]) => on);

  return (
    <ul>
      {notifs.map(([label, desc], i) => (
        <li key={i} className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
          <div>
            <p className="text-sm font-semibold text-slate-700">{label}</p>
            <p className="text-xs text-slate-400">{desc}</p>
          </div>
          <button
            onClick={() => setState(flags.map((v, j) => (j === i ? !v : v)))}
            className="w-10 h-5 rounded-full relative transition-colors flex-shrink-0 ml-4"
            style={{ background: flags[i] ? "#14b8a6" : "#e2e8f0" }}
          >
            <span
              className="absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all"
              style={{ left: flags[i] ? "calc(100% - 18px)" : "2px" }}
            />
          </button>
        </li>
      ))}
    </ul>
  );
}

function AppearanceTab({ role: _role }) {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <h3 className="text-sm font-bold text-slate-800 mb-1">Appearance</h3>
      <p className="text-xs text-slate-400 mb-5">
        Choose how WorkHive looks for you. Your choice is saved to this browser.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 max-w-2xl">
        {THEME_OPTIONS.map((opt) => {
          const active = theme === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => setTheme(opt.id)}
              aria-pressed={active}
              className={
                "text-left p-3.5 rounded-xl transition bg-white " +
                (active
                  ? "border-2 border-teal-500 shadow-[0_0_0_4px_rgba(20,184,166,0.10)]"
                  : "border border-slate-200 hover:border-slate-300")
              }
            >
              {/* Mini preview */}
              <div
                className="relative h-24 rounded-lg border border-slate-200 overflow-hidden mb-3"
                style={{ background: opt.preview.surface }}
              >
                <div className="absolute top-2.5 left-2.5 right-2.5 h-3.5 rounded" style={{ background: opt.preview.card }} />
                <div className="absolute top-8 left-2.5 w-3/5 h-2 rounded" style={{ background: opt.preview.text, opacity: 0.85 }} />
                <div className="absolute top-[46px] left-2.5 w-2/5 h-1.5 rounded" style={{ background: opt.preview.mutedText }} />
                <div className="absolute bottom-3 right-3 w-[18px] h-[18px] rounded-full" style={{ background: opt.preview.accent }} />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[13px] font-bold text-slate-700">{opt.label}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{opt.description}</div>
                </div>
                <span
                  className="rounded-full bg-white flex-shrink-0"
                  style={{
                    width: 20, height: 20,
                    border: active ? "6px solid #14b8a6" : "2px solid #e2e8f0",
                  }}
                />
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-500 mt-3.5">
        Currently selected: <strong className="text-slate-700">{theme === "dark" ? "Dark" : "Light"}</strong> theme.
      </p>
    </div>
  );
}

function ProfileSaveButton() {
  const [saved, fire] = useSaveFeedback();
  return (
    <div className="mt-5 flex items-center gap-3">
      <button
        onClick={fire}
        className="px-4 py-2 rounded-lg text-xs font-semibold text-white"
        style={{ background: "#14b8a6" }}
      >
        Save Changes
      </button>
      {saved && (
        <span className="rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-[11px] font-semibold text-emerald-700">
          Saved ✓
        </span>
      )}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
const SettingsPage = () => {
  const { user } = useAuth();
  const role = (user?.role || "employee").toLowerCase();
  const fullName = user?.full_name || user?.name || "";
  const initials = (fullName || "U")
    .split(" ")
    .filter(Boolean)
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase() || "U";
  const [tab, setTab] = useState("profile");

  return (
    <div className="space-y-5">
      <PageTitle title="Settings" sub="Manage your workspace preferences." />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Tab rail */}
        <Card padding="p-3" className="lg:col-span-1 h-fit">
          <ul className="space-y-1">
            {TABS.map((t) => (
              <li key={t.id}>
                <button
                  onClick={() => setTab(t.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-colors ${
                    tab === t.id
                      ? "bg-teal-50 text-teal-600"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <span>{t.icon}</span> {t.label}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        {/* Content pane */}
        <Card className="lg:col-span-3">
          {/* ── Profile ── */}
          {tab === "profile" && (
            <div>
              <h3 className="text-sm font-bold text-slate-800 mb-1">Profile Settings</h3>
              <p className="text-xs text-slate-400 mb-5">Update your personal information.</p>
              <div className="flex items-center gap-4 mb-5">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-400 to-blue-500 flex items-center justify-center text-white font-bold text-xl">
                  {initials}
                </div>
                <div className="flex flex-col gap-2">
                  <button
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
                    style={{ background: "#14b8a6" }}
                  >
                    Upload Photo
                  </button>
                  <button className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 border border-slate-200">
                    Remove
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[
                  ["Full Name",      fullName],
                  ["Email",          user?.email || ""],
                  ["Phone",          user?.phone || ""],
                  ["Employee Code",  user?.employee_code || ""],
                  ["Designation",    user?.designation || ""],
                  ["Department",     user?.department || ""],
                ].map(([l, v]) => (
                  <div key={l}>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                      {l}
                    </label>
                    <input
                      defaultValue={v}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent"
                    />
                  </div>
                ))}
              </div>
              <ProfileSaveButton />
            </div>
          )}

          {/* ── Security ── */}
          {tab === "security" && (
            <div>
              <h3 className="text-sm font-bold text-slate-800 mb-1">Security Settings</h3>
              <p className="text-xs text-slate-400 mb-5">Manage your password and 2FA.</p>
              <div className="space-y-4 max-w-md">
                {["Current Password", "New Password", "Confirm New Password"].map((l) => (
                  <div key={l}>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                      {l}
                    </label>
                    <input
                      type="password"
                      placeholder="••••••••"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent"
                    />
                  </div>
                ))}
                <button
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-white"
                  style={{ background: "#14b8a6" }}
                >
                  Update Password
                </button>
              </div>
              <div className="mt-6 p-4 rounded-xl bg-slate-50 border border-slate-100">
                <p className="text-sm font-semibold text-slate-700">Two-Factor Authentication</p>
                <p className="text-xs text-slate-500 mt-1 mb-3">
                  Add an extra layer of security to your account.
                </p>
                <button className="px-4 py-1.5 rounded-lg text-xs font-semibold border border-teal-300 text-teal-600 hover:bg-teal-50">
                  Enable 2FA
                </button>
              </div>
            </div>
          )}

          {/* ── Notifications ── */}
          {tab === "notifications" && (
            <div>
              <h3 className="text-sm font-bold text-slate-800 mb-1">Notification Preferences</h3>
              <p className="text-xs text-slate-400 mb-5">Choose how you'd like to be notified.</p>
              <NotifList role={role} />
            </div>
          )}

          {/* ── Appearance ── */}
          {tab === "appearance" && <AppearanceTab role={role} />}
        </Card>
      </div>
    </div>
  );
};

export default SettingsPage;
