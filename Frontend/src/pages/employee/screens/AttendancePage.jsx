import { useEffect, useMemo, useState } from "react";
import { PageTitle, Card, StatCard, Badge, Pill, TableShell, OutlineButton } from "../parts/UI";
import { attendance, regularization } from "../../../services/attendance";
import TimesheetsPage from "./TimesheetsPage";

// Status -> Pill tone
const TONE = {
  present: "green", late: "amber", absent: "red",
  half_day: "amber", on_leave: "purple", holiday: "slate",
};
const DOT = {
  present: "#14b8a6", late: "#f59e0b", absent: "#ef4444",
  half_day: "#f59e0b", on_leave: "#a855f7", holiday: "#cbd5e1",
};

function fmtTime(t) {
  if (!t) return "-";
  if (typeof t === "string") return t.slice(0, 5);
  return t;
}
function fmtDate(s) {
  if (!s) return "-";
  const d = new Date(s);
  return d.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });
}
function dayOfWeek(s) {
  if (!s) return "-";
  return new Date(s).toLocaleDateString("en-IN", { weekday: "long" });
}
function hoursLabel(h) {
  if (h == null) return "-";
  const total = Math.round(h * 60);
  return `${Math.floor(total / 60)}h ${(total % 60).toString().padStart(2, "0")}m`;
}

function buildCalendar(records, year, month) {
  const first = new Date(year, month, 1);
  const last  = new Date(year, month + 1, 0);
  const startOffset = (first.getDay() + 6) % 7; // Mon-first
  const totalCells = Math.ceil((startOffset + last.getDate()) / 7) * 7;
  const byDate = Object.fromEntries(records.map((r) => [r.date, r]));
  const cells = [];
  for (let i = 0; i < totalCells; i++) {
    const dayNum = i - startOffset + 1;
    if (dayNum < 1 || dayNum > last.getDate()) {
      cells.push({ d: null });
    } else {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
      const r = byDate[iso];
      cells.push({ d: dayNum, status: r?.status || "neutral", record: r });
    }
  }
  return cells;
}

const RegularizeModal = ({ open, onClose, onSubmitted }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [type, setType] = useState("missed_checkout");
  const [checkIn, setCheckIn] = useState("09:00");
  const [checkOut, setCheckOut] = useState("18:00");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setSubmitting(true);
    try {
      await regularization.submit({
        date, regularization_type: type,
        requested_check_in: checkIn ? `${checkIn}:00` : null,
        requested_check_out: checkOut ? `${checkOut}:00` : null,
        reason,
      });
      onSubmitted();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Submit failed");
    } finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <form onSubmit={submit} className="bg-white w-[420px] rounded-xl shadow-xl p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-3">Regularize Attendance</h3>
        <div className="space-y-3 text-xs">
          <label className="block">
            <span className="text-slate-500">Date</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required
              className="w-full mt-1 px-2 py-1.5 border border-slate-200 rounded" />
          </label>
          <label className="block">
            <span className="text-slate-500">Type</span>
            <select value={type} onChange={(e) => setType(e.target.value)}
              className="w-full mt-1 px-2 py-1.5 border border-slate-200 rounded">
              <option value="full_day">Full day</option>
              <option value="wrong_time">Wrong time</option>
              <option value="missed_checkout">Missed checkout</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-slate-500">Requested check-in</span>
              <input type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)}
                className="w-full mt-1 px-2 py-1.5 border border-slate-200 rounded" />
            </label>
            <label className="block">
              <span className="text-slate-500">Requested check-out</span>
              <input type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)}
                className="w-full mt-1 px-2 py-1.5 border border-slate-200 rounded" />
            </label>
          </div>
          <label className="block">
            <span className="text-slate-500">Reason</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
              className="w-full mt-1 px-2 py-1.5 border border-slate-200 rounded" />
          </label>
          {err && <div className="text-rose-600 text-xs">{err}</div>}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-xs rounded border border-slate-200">Cancel</button>
          <button type="submit" disabled={submitting}
            className="px-3 py-1.5 text-xs rounded text-white" style={{ background: "#14b8a6" }}>
            {submitting ? "Submitting..." : "Submit"}
          </button>
        </div>
      </form>
    </div>
  );
};

const AttendancePage = () => {
  const today = new Date();
  const [year, setYear]   = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [todayState, setTodayState] = useState(null);
  const [records, setRecords] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showRegularize, setShowRegularize] = useState(false);
  // Sub-tab inside the Attendance section. Timesheets used to live in its own
  // sidebar entry; it now lives here as a sibling tab.
  const [tab, setTab] = useState("attendance"); // "attendance" | "timesheets"

  const monthLabel = useMemo(() =>
    new Date(year, month, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" }),
    [year, month],
  );

  const refresh = async () => {
    setErr("");
    try {
      const [t, recs] = await Promise.all([
        attendance.today(),
        attendance.records({
          start: `${year}-${String(month + 1).padStart(2, "0")}-01`,
          end:   `${year}-${String(month + 1).padStart(2, "0")}-${new Date(year, month + 1, 0).getDate()}`,
        }),
      ]);
      setTodayState(t);
      setRecords(Array.isArray(recs) ? recs : []);
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Could not load attendance");
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [year, month]);

  const doPunch = async (kind) => {
    setBusy(true); setErr("");
    try {
      const res = kind === "in" ? await attendance.checkIn() : await attendance.checkOut();
      if (res?.message) console.log(res.message);
      await refresh();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Punch failed");
    } finally { setBusy(false); }
  };

  const presentCount = records.filter((r) => r.status === "present" || r.status === "late").length;
  const lateAvg = (() => {
    const valid = records.filter((r) => r.late_minutes != null && r.check_in_time);
    if (!valid.length) return "-";
    const meanCheckin = valid
      .map((r) => {
        const [h, m] = (r.check_in_time || "00:00").split(":").map(Number);
        return h * 60 + (m || 0);
      })
      .reduce((a, b) => a + b, 0) / valid.length;
    const h = Math.floor(meanCheckin / 60), m = Math.round(meanCheckin % 60);
    return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  })();
  const totalHours = Math.round(records.reduce((a, r) => a + (r.working_hours || 0), 0));
  const attendancePct = records.length ? Math.round((presentCount / records.length) * 100) : 0;

  const calendarCells = useMemo(() => buildCalendar(records, year, month), [records, year, month]);
  const todayRec = todayState?.record;

  const tabBtn = (key, label) => (
    <button
      key={key}
      type="button"
      onClick={() => setTab(key)}
      className="px-4 py-2 text-xs font-semibold rounded-md transition-colors"
      style={{
        background: tab === key ? "#14b8a6" : "transparent",
        color: tab === key ? "#fff" : "#64748b",
      }}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-5">
      <PageTitle
        title="Attendance"
        sub="Track your daily attendance, work hours, history, and weekly timesheets."
        right={
          tab === "attendance" ? (
            <button
              onClick={() => setShowRegularize(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white"
              style={{ background: "#14b8a6" }}
            >
              + Regularize
            </button>
          ) : null
        }
      />

      {/* Sub-tabs: Attendance | Timesheets */}
      <div className="inline-flex items-center gap-1 p-1 rounded-lg border border-slate-200 bg-white">
        {tabBtn("attendance", "Attendance")}
        {tabBtn("timesheets", "Timesheets")}
      </div>

      {tab === "timesheets" ? (
        <TimesheetsPage />
      ) : (
      <>
      {err && <div className="bg-rose-50 text-rose-700 text-xs px-3 py-2 rounded">{err}</div>}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="PRESENT DAYS" value={String(presentCount)} sub={`/ ${records.length} records`} subColor="#22c55e" iconBg="#f0fdfa" icon={null} />
        <StatCard label="AVG CHECK-IN" value={lateAvg}             sub="rolling avg"           subColor="#f97316" iconBg="#fff7ed" icon={null} />
        <StatCard label="TOTAL HOURS"  value={`${totalHours}h`}    sub={`${records.length} days`} subColor="#64748b" iconBg="#eff6ff" icon={null} />
        <StatCard label="ATTENDANCE %" value={`${attendancePct}%`} sub="this month"             subColor="#22c55e" iconBg="#fefce8" icon={null} />
      </div>

      {/* Calendar + Today */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-slate-800">{monthLabel}</h3>
              <p className="text-[11px] text-slate-400 mt-0.5">Click on any day to see details</p>
            </div>
            <div className="flex gap-1">
              <button onClick={() => { const d = new Date(year, month - 1, 1); setYear(d.getFullYear()); setMonth(d.getMonth()); }}
                className="w-7 h-7 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-50">{"<"}</button>
              <button onClick={() => { const d = new Date(year, month + 1, 1); setYear(d.getFullYear()); setMonth(d.getMonth()); }}
                className="w-7 h-7 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-50">{">"}</button>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
            {["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map((d) => <div key={d}>{d}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {calendarCells.map((d, i) => (
              <div key={i} className="aspect-square rounded-md flex flex-col items-center justify-center text-xs"
                title={d.record ? `${d.status} (${hoursLabel(d.record.working_hours)})` : ""}
                style={{
                  background: d.d ? "#f8fafc" : "transparent",
                  color: d.d ? "#334155" : "transparent",
                }}>
                {d.d && (
                  <>
                    <span className="font-semibold">{d.d}</span>
                    {d.status && d.status !== "neutral" && (
                      <span className="w-1.5 h-1.5 rounded-full mt-0.5" style={{ background: DOT[d.status] || "#cbd5e1" }} />
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-4 mt-4 text-[11px] text-slate-500">
            {[["#14b8a6","Present"], ["#f59e0b","Late / half"], ["#a855f7","Leave"], ["#ef4444","Absent"], ["#cbd5e1","Holiday"]].map(([c, l]) => (
              <span key={l} className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: c }} /> {l}</span>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-bold text-slate-800">Today</h3>
          <p className="text-[11px] text-slate-400 mt-0.5 mb-4">
            {today.toLocaleDateString("en-IN", { weekday: "long", month: "short", day: "numeric", year: "numeric" })}
          </p>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Check-in</p>
                <p className="text-base font-bold text-slate-800">
                  {todayRec?.check_in_time ? fmtTime(todayRec.check_in_time) : "- Not yet"}
                </p>
              </div>
              {todayState?.has_checked_in
                ? <Pill tone={todayRec?.late_minutes ? "amber" : "green"}>{todayRec?.late_minutes ? `Late ${todayRec.late_minutes}m` : "On Time"}</Pill>
                : <button onClick={() => doPunch("in")} disabled={busy}
                    className="px-3 py-1.5 text-[11px] rounded text-white font-semibold" style={{ background: "#14b8a6" }}>
                    {busy ? "..." : "Check in"}
                  </button>
              }
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Check-out</p>
                <p className="text-base font-bold text-slate-800">
                  {todayRec?.check_out_time ? fmtTime(todayRec.check_out_time) : "- Pending"}
                </p>
              </div>
              {todayState?.has_checked_in && !todayState?.has_checked_out && (
                <button onClick={() => doPunch("out")} disabled={busy}
                  className="px-3 py-1.5 text-[11px] rounded text-white font-semibold" style={{ background: "#0f766e" }}>
                  {busy ? "..." : "Check out"}
                </button>
              )}
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Hours so far</p>
              <p className="text-base font-bold text-slate-800">{hoursLabel(todayRec?.working_hours)}</p>
            </div>
            {todayRec?.status && (
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Status</p>
                <Pill tone={TONE[todayRec.status] || "slate"}>{todayRec.status}</Pill>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Table */}
      <Card padding="p-0">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-800">Attendance History</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">{records.length} records this month</p>
          </div>
        </div>
        <TableShell headers={["Date", "Day", "Check-in", "Check-out", "Hours", "Status"]}>
          {records.length === 0 && (
            <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-400 text-xs">No records yet.</td></tr>
          )}
          {records.map((r) => (
            <tr key={r.id}>
              <td className="px-4 py-3 font-semibold text-slate-700">{fmtDate(r.date)}</td>
              <td className="px-4 py-3 text-slate-500">{dayOfWeek(r.date)}</td>
              <td className="px-4 py-3 text-slate-700">{fmtTime(r.check_in_time)}</td>
              <td className="px-4 py-3 text-slate-700">{fmtTime(r.check_out_time)}</td>
              <td className="px-4 py-3 text-slate-700">{hoursLabel(r.working_hours)}</td>
              <td className="px-4 py-3"><Pill tone={TONE[r.status] || "slate"}>{r.status || "-"}</Pill></td>
            </tr>
          ))}
        </TableShell>
      </Card>

      </>
      )}

      <RegularizeModal
        open={showRegularize}
        onClose={() => setShowRegularize(false)}
        onSubmitted={refresh}
      />
    </div>
  );
};

export default AttendancePage;
