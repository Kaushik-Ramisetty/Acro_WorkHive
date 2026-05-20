import { useEffect, useState } from "react";
import { useAuth } from "../../../context/AuthContext";

const initialsOf = (name) =>
  (name || "U").split(" ").filter(Boolean).map((s) => s[0]).slice(0, 2).join("").toUpperCase() || "U";

const Pill = ({ tone = "slate", children }) => {
  const tones = {
    slate:  "bg-slate-100 text-slate-600",
    teal:   "bg-teal-50 text-teal-700",
    green:  "bg-emerald-50 text-emerald-700",
    blue:   "bg-blue-50 text-blue-700",
    amber:  "bg-amber-50 text-amber-700",
    rose:   "bg-rose-50 text-rose-700",
    violet: "bg-violet-50 text-violet-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-semibold ${tones[tone] || tones.slate}`}>
      {children}
    </span>
  );
};

function Field({ label, value, onChange, type = "text", disabled = false }) {
  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label}</label>
      <input
        type={type}
        value={value || ""}
        onChange={onChange}
        disabled={disabled}
        className={
          "px-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-2 focus:ring-teal-300 focus:border-teal-400 transition " +
          (disabled
            ? "bg-slate-50 border-slate-200 text-slate-500"
            : "bg-white border-slate-200 text-slate-700")
        }
      />
    </div>
  );
}

function StatTile({ label, value, icon, tint = "bg-teal-50 text-teal-600" }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${tint}`}>{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider truncate">{label}</p>
        <p className="text-sm font-bold text-slate-800 truncate">{value}</p>
      </div>
    </div>
  );
}

function Toggle({ on, onChange }) {
  return (
    <button
      onClick={onChange}
      aria-pressed={on}
      className="relative h-[23px] w-[42px] flex-shrink-0 rounded-full transition-colors"
      style={{ background: on ? "#14b8a6" : "#e2e8f0" }}
    >
      <span
        className="absolute top-[3px] h-[17px] w-[17px] rounded-full bg-white shadow transition-all"
        style={{ left: on ? 21 : 4 }}
      />
    </button>
  );
}

function NotifRow({ label, desc, initial }) {
  const [on, setOn] = useState(initial);
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-3 last:border-0">
      <div className="min-w-0 pr-3">
        <p className="text-sm font-semibold text-slate-700">{label}</p>
        <p className="text-xs text-slate-500">{desc}</p>
      </div>
      <Toggle on={on} onChange={() => setOn((v) => !v)} />
    </div>
  );
}

const I = {
  mail: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" />
    </svg>
  ),
  phone: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92V21a1 1 0 0 1-1.1 1A19.86 19.86 0 0 1 2 4.1 1 1 0 0 1 3 3h4.09a1 1 0 0 1 1 .75l1 4a1 1 0 0 1-.27 1L7 10.5a16 16 0 0 0 6.5 6.5l1.74-1.79a1 1 0 0 1 1-.27l4 1a1 1 0 0 1 .76 1z" />
    </svg>
  ),
  pin: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
    </svg>
  ),
  calendar: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  star: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  ),
  clock: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  shield: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  activity: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  arrowRight: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  ),
  bell: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  ),
  download: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  ),
  settings: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

const MyProfilePage = () => {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState("personal");

  const seed = () => ({
    fullName:    user?.full_name
               || [user?.first_name, user?.last_name].filter(Boolean).join(" ")
               || user?.name
               || (user?.email ? user.email.split("@")[0] : ""),
    email:       user?.email || "",
    phone:       user?.phone || "",
    employeeId:  user?.employee_code || "",
    department:  user?.department || "",
    designation: user?.designation || "",
    manager:     user?.manager_name || "Not assigned",
    bloodGroup:  user?.blood_group || "",
    gender:      user?.gender || "",
    dob:         user?.date_of_birth || "",
    joined:      user?.date_of_joining || "",
    location:    user?.location || "",
    nationality: user?.nationality || "",
    marital:     user?.marital_status || "",
    // timeZone:    user?.time_zone || "",
  });
  const [data, setData] = useState(seed);
  useEffect(() => { setData(seed()); /* eslint-disable-next-line */ }, [user]);

  const upd = (k) => (e) => setData({ ...data, [k]: e.target.value });

  const [pwd, setPwd] = useState({ current: "", next: "", confirm: "" });
  const [pwdError, setPwdError] = useState("");
  const [saved, setSaved] = useState(false);
  const [pwdSaved, setPwdSaved] = useState(false);
  const updP = (k) => (e) => setPwd({ ...pwd, [k]: e.target.value });

  const onSave = (e) => {
    e?.preventDefault?.();
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const onPwdSubmit = (e) => {
    e?.preventDefault?.();
    setPwdError("");
    if (!pwd.current || !pwd.next || !pwd.confirm) { setPwdError("Please fill in every field."); return; }
    if (pwd.next.length < 6)      { setPwdError("New password must be at least 6 characters."); return; }
    if (pwd.next !== pwd.confirm) { setPwdError("Passwords do not match."); return; }
    setPwd({ current: "", next: "", confirm: "" });
    setPwdSaved(true);
    setTimeout(() => setPwdSaved(false), 2000);
  };

  const fullName = data.fullName;
  const initials = initialsOf(fullName);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">My Profile</h1>
        <p className="text-xs text-slate-400 mt-0.5">View and update your personal information.</p>
      </div>

      {/* Hero — mirrors the manager profile layout: avatar overlaps the
          gradient banner, Joined date sits directly below designation, and
          there's no right-side column or Edit Profile button (read-only). */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="relative h-32" style={{ background: "linear-gradient(135deg, #0f1c2e 0%, #1e3fc4 50%, #14b8a6 100%)" }}>
          <div className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-white/10 blur-2xl" />
        </div>
        <div className="px-6 pb-6">
          <div className="flex flex-wrap items-end gap-5 pt-3.5">
            <div className="relative -mt-[52px] flex-shrink-0">
              <div className="w-[104px] h-[104px] rounded-2xl border-4 border-white bg-gradient-to-br from-teal-400 to-blue-500 flex items-center justify-center text-white font-bold text-3xl shadow-lg">
                {initials}
              </div>
              <span className="absolute bottom-1 right-1 w-5 h-5 bg-emerald-500 rounded-full border-[3px] border-white" />
            </div>
            <div className="pb-1.5 min-w-0 flex-1">
              <h2 className="text-[22px] font-extrabold text-slate-800 leading-tight truncate">{fullName || "—"}</h2>
              <p className="text-sm text-slate-500 truncate mt-1">
                {data.designation || "—"}{data.department ? ` · ${data.department}` : ""}
              </p>
              {data.joined && (
                <p className="text-[11px] text-slate-400 mt-1">Joined {data.joined}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-2.5">
                <Pill tone="teal">Employee</Pill>
                <Pill tone="green">● Active</Pill>
                {data.employeeId && <Pill tone="slate">{data.employeeId}</Pill>}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 border-t border-slate-100 mt-5 pt-5">
            <div className="flex items-center gap-2 text-sm text-slate-700 min-w-0">
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">{I.mail}</span>
              <span className="truncate">{data.email || "—"}</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-700 min-w-0">
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">{I.phone}</span>
              <span className="truncate">{data.phone || "—"}</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-700 min-w-0">
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">{I.pin}</span>
              <span className="truncate">{data.location || data.department || "—"}</span>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="flex gap-1 border-b border-slate-100 px-3 pt-3">
            {[
              ["personal",    "Personal Info"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={
                  "px-4 py-2.5 text-xs font-semibold rounded-t-md border-b-2 transition " +
                  (tab === id
                    ? "border-teal-500 text-teal-600"
                    : "border-transparent text-slate-500 hover:text-slate-700")
                }
              >
                {label}
              </button>
            ))}
          </div>

          <div className="p-6">
            {tab === "personal" && (
              <>
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">Personal Information</h3>
                    <p className="text-xs text-slate-500 mt-0.5">Update your details — saved locally for this preview.</p>
                  </div>
                  {saved && <Pill tone="green">Saved</Pill>}
                </div>
                <form onSubmit={onSave}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field label="Full Name"      value={data.fullName}    onChange={upd("fullName")}    disabled={!editing} />
                    <Field label="Email"          value={data.email}       onChange={upd("email")}       disabled={!editing} type="email" />
                    <Field label="Phone"          value={data.phone}       onChange={upd("phone")}       disabled={!editing} type="tel" />
                    <Field label="Employee ID"    value={data.employeeId}  onChange={upd("employeeId")}  disabled />
                    <Field label="Department"     value={data.department}  onChange={upd("department")}  disabled={!editing} />
                    <Field label="Designation"    value={data.designation} onChange={upd("designation")} disabled={!editing} />
                    <Field label="Date of Birth"  value={data.dob}         onChange={upd("dob")}         disabled={!editing} />
                    <Field label="Gender"         value={data.gender}      onChange={upd("gender")}      disabled={!editing} />
                    <Field label="Blood Group"    value={data.bloodGroup}  onChange={upd("bloodGroup")}  disabled={!editing} />
                    <Field label="Location"       value={data.location}    onChange={upd("location")}    disabled={!editing} />
                    <Field label="Nationality"    value={data.nationality} onChange={upd("nationality")} disabled={!editing} />
                    <Field label="Marital Status" value={data.marital}     onChange={upd("marital")}     disabled={!editing} />
                    {/* <Field label="Time Zone"      value={data.timeZone}    onChange={upd("timeZone")}    disabled={!editing} /> */}
                    <Field label="Reporting Manager" value={data.manager}  onChange={upd("manager")}     disabled />
                  </div>
                  {editing && (
                    <div className="flex justify-end gap-2 mt-5">
                      <button type="button" onClick={() => setEditing(false)} className="px-4 py-2 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
                      <button type="submit" className="px-4 py-2 rounded-lg text-xs font-semibold text-white bg-teal-500 hover:bg-teal-600 shadow-sm">Save Changes</button>
                    </div>
                  )}
                </form>
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
};

export default MyProfilePage;
