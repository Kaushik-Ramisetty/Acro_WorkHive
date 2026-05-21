import { useEffect, useMemo, useState } from "react";
import { timesheet as tsApi } from "../../../services/timesheet";
import { attendance as attendanceSvc } from "../../../services/attendance";
import { utilizationApi } from "../../../services/utilization";
import { holidays as holidaysApi } from "../../../services/holidays";

// ── helpers ──────────────────────────────────────────────────────────────────

function startOfWeek(d) {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = (out.getDay() + 6) % 7;
  out.setDate(out.getDate() - dow);
  return out;
}

function fmtIso(d) {
  const y   = d.getFullYear();
  const m   = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtDisplay(iso) {
  if (!iso) return "—";
  const [y, m, day] = iso.split("-");
  return new Date(Number(y), Number(m) - 1, Number(day)).toLocaleDateString(
    "en-IN",
    { day: "2-digit", month: "short", year: "numeric" }
  );
}

function fmtTime(t) {
  if (!t) return "—";
  return String(t).slice(0, 5);
}

function isWeekend(d) {
  const dow = d.getDay();
  return dow === 0 || dow === 6;
}

/** Payroll cycle: 25th of prev month → 25th of current month (or current→next if day > 25). */
function currentPayrollCycle() {
  const today = new Date();
  const day   = today.getDate();
  let start, end;
  if (day <= 25) {
    const prevMonth = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
    const prevYear  = today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();
    start = new Date(prevYear, prevMonth, 25);
    end   = new Date(today.getFullYear(), today.getMonth(), 25);
  } else {
    start = new Date(today.getFullYear(), today.getMonth(), 25);
    const nextMonth = today.getMonth() === 11 ? 0 : today.getMonth() + 1;
    const nextYear  = today.getMonth() === 11 ? today.getFullYear() + 1 : today.getFullYear();
    end = new Date(nextYear, nextMonth, 25);
  }
  return { start: fmtIso(start), end: fmtIso(end) };
}

// ── live timer ────────────────────────────────────────────────────────────────

function computeElapsed(checkInTime) {
  if (!checkInTime) return "—";
  const parts = String(checkInTime).split(":");
  const ciMinutes = Number(parts[0]) * 60 + Number(parts[1] || 0);
  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  const diff = nowMinutes - ciMinutes;
  if (diff < 0) return "—";
  const h = Math.floor(diff / 60);
  const min = diff % 60;
  return h > 0 ? `${h}h ${min}m` : `${min}m`;
}

function LiveTimer({ checkInTime }) {
  const [elapsed, setElapsed] = useState(() => computeElapsed(checkInTime));
  useEffect(() => {
    const id = setInterval(() => setElapsed(computeElapsed(checkInTime)), 60_000);
    return () => clearInterval(id);
  }, [checkInTime]);
  return (
    <span className="text-emerald-600 text-xs font-bold" title={`Checked in at ${fmtTime(checkInTime)}`}>
      {elapsed} ⏱
    </span>
  );
}

// ── status badge config ───────────────────────────────────────────────────────

const TS_BADGES = {
  draft:                            { bg: "bg-slate-100",   text: "text-slate-500",   label: "Auto-captured, not yet submitted"  },
  pending:                          { bg: "bg-amber-100",   text: "text-amber-700",   label: "Awaiting client approval"          },
  pending_client_review:            { bg: "bg-amber-100",   text: "text-amber-700",   label: "Awaiting client approval"          },
  pending_internal:                 { bg: "bg-amber-100",   text: "text-amber-700",   label: "Awaiting manager review"           },
  pending_reporting_manager_review: { bg: "bg-sky-100",     text: "text-sky-700",     label: "Awaiting manager review"           },
  client_approved:                  { bg: "bg-blue-100",    text: "text-blue-700",    label: "Client approved, awaiting manager" },
  manager_approved:                 { bg: "bg-emerald-100", text: "text-emerald-700", label: "Approved"                          },
  approved:                         { bg: "bg-emerald-100", text: "text-emerald-700", label: "Approved"                          },
  locked:                           { bg: "bg-emerald-100", text: "text-emerald-700", label: "Locked & sent to payroll"          },
  rejected:                         { bg: "bg-rose-100",    text: "text-rose-700",    label: "Rejected — please resubmit"        },
  client_rejected:                  { bg: "bg-rose-100",    text: "text-rose-700",    label: "Client rejected — please resubmit" },
};

const MONTHLY_STATUS_PILL = {
  draft:                            { bg: "#F8FAFC", color: "#64748B", label: "Draft"                         },
  pending:                          { bg: "#FEF3C7", color: "#B45309", label: "Awaiting Client Approval"        },
  pending_client_review:            { bg: "#FEF3C7", color: "#B45309", label: "Awaiting Client Approval"        },
  pending_review:                   { bg: "#DBEAFE", color: "#1D4ED8", label: "Pending Internal Review"         },
  pending_reporting_manager_review: { bg: "#DBEAFE", color: "#1D4ED8", label: "Awaiting Manager Review"         },
  client_approved:                  { bg: "#D1FAE5", color: "#047857", label: "Client Approved"                 },
  manager_approved:                 { bg: "#ECFDF5", color: "#065F46", label: "Fully Approved"                  },
  approved:                         { bg: "#ECFDF5", color: "#065F46", label: "Fully Approved"                  },
  locked:                           { bg: "#E0E7FF", color: "#3730A3", label: "Locked for Payroll"              },
  rejected:                         { bg: "#FEE2E2", color: "#B91C1C", label: "Rejected — Resubmit"             },
  client_rejected:                  { bg: "#FEE2E2", color: "#B91C1C", label: "Client Rejected — Resubmit"      },
};

function StatusBadge({ status, reviewComment }) {
  const t = TS_BADGES[status] || TS_BADGES.draft;
  return (
    <div className={"inline-flex flex-col gap-0.5 rounded-lg px-3 py-2 text-xs font-semibold " + t.bg + " " + t.text}>
      <span className="capitalize">{(status || "draft").replace(/_/g, " ")}</span>
      <span className="font-normal opacity-80">{t.label}</span>
      {status === "rejected" && reviewComment && (
        <span className="mt-0.5 font-normal italic">"{reviewComment}"</span>
      )}
    </div>
  );
}

function HoursCell({ rec, day, isoDate, todayIso, isHoliday }) {
  if (!rec) {
    if (isHoliday) return <span className="text-purple-600 text-xs font-semibold">Holiday</span>;
    if (isWeekend(day)) return <span className="text-slate-400 text-xs">Weekend</span>;
    return isoDate < todayIso
      ? <span className="text-rose-500 text-xs font-semibold">Absent</span>
      : <span className="text-slate-400 text-xs">—</span>;
  }
  const status = (rec.status || "").toLowerCase();
  if (status === "on_leave" || status === "leave") return <span className="text-blue-600 text-xs font-semibold">On Leave</span>;
  if (status === "holiday")                          return <span className="text-purple-600 text-xs font-semibold">Holiday</span>;
  if (status === "half_day" || status === "halfday") return <span className="text-amber-600 text-xs font-semibold">Half Day</span>;
  if (status === "absent")                           return <span className="text-rose-500 text-xs font-semibold">Absent</span>;
  if (rec.check_in_time && !rec.check_out_time && isoDate === todayIso) return <LiveTimer checkInTime={rec.check_in_time} />;
  const hrs = rec.working_hours;
  if (hrs == null || hrs === "") {
    return isoDate < todayIso ? <span className="text-rose-500 text-xs font-semibold">Absent</span> : <span className="text-slate-400 text-xs">—</span>;
  }
  return <span className="text-emerald-600 text-xs font-bold">{Number(hrs).toFixed(1)}h</span>;
}

// ── Monthly Report Submission Modal ──────────────────────────────────────────

function MonthlyReportModal({ onClose, onSuccess, cycleStart, cycleEnd }) {
  const [attRecords, setAttRecords] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [remarks, setRemarks]       = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [err, setErr]               = useState("");

  useEffect(() => {
    setLoading(true);
    attendanceSvc
      .records({ start: cycleStart, end: cycleEnd })
      .then((r) => setAttRecords(Array.isArray(r) ? r : []))
      .catch(() => setAttRecords([]))
      .finally(() => setLoading(false));
  }, [cycleStart, cycleEnd]);

  const stats = useMemo(() => {
    let totalHours = 0, overtimeHours = 0, presentDays = 0, leaveDays = 0, halfDays = 0;
    attRecords.forEach((r) => {
      totalHours    += r.working_hours   || 0;
      overtimeHours += r.overtime_hours  || 0;
      const s = (r.status || "").toLowerCase();
      if (["present", "late", "wfh"].includes(s)) presentDays++;
      else if (s === "on_leave")                   leaveDays++;
      else if (s === "half_day")                   halfDays++;
    });
    return { totalHours, overtimeHours, presentDays, leaveDays, halfDays };
  }, [attRecords]);

  const handleSubmit = async () => {
    setSubmitting(true); setErr("");
    try {
      const result = await tsApi.monthlyReport.submit({ remarks: remarks || null, client_manager_email: clientEmail.trim() || null });
      onSuccess(result);
    } catch (e) {
      const detail = e?.data?.detail || e?.message || "Submission failed";
      setErr(detail);
    } finally { setSubmitting(false); }
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 bg-gradient-to-r from-teal-50 to-emerald-50">
          <h2 className="text-base font-bold text-slate-900">Generate Monthly Timesheet Report</h2>
          <p className="text-xs text-slate-500 mt-1">Submit your T&amp;M report for client approval</p>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Reporting period */}
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Reporting Period</p>
            <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 flex items-center gap-3">
              <div className="h-8 w-8 rounded-full bg-teal-100 flex items-center justify-center text-teal-700 text-xs font-bold flex-shrink-0">
                📅
              </div>
              <div>
                <p className="text-sm font-bold text-slate-800">
                  {fmtDisplay(cycleStart)} — {fmtDisplay(cycleEnd)}
                </p>
                <p className="text-[10px] text-slate-400 mt-0.5">Payroll cycle (25th to 25th)</p>
              </div>
            </div>
          </div>

          {/* Summary */}
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Summary</p>
            {loading ? (
              <div className="text-xs text-slate-400 py-4 text-center">Calculating…</div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "Working Hours",   value: stats.totalHours.toFixed(1)    + " h",    color: "text-teal-700",   bg: "bg-teal-50"   },
                  { label: "Overtime",        value: stats.overtimeHours.toFixed(1) + " h",    color: "text-amber-700",  bg: "bg-amber-50"  },
                  { label: "Present Days",    value: String(stats.presentDays),                color: "text-emerald-700",bg: "bg-emerald-50"},
                  { label: "Leave Days",      value: String(stats.leaveDays),                  color: "text-blue-700",   bg: "bg-blue-50"   },
                  { label: "Half Days",       value: String(stats.halfDays),                   color: "text-orange-700", bg: "bg-orange-50" },
                ].map((s) => (
                  <div key={s.label} className={`rounded-xl ${s.bg} px-3 py-2.5 text-center`}>
                    <div className={`text-base font-bold ${s.color}`}>{s.value}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">{s.label}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Client Manager Email */}
          <div>
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              Client Manager Email <span className="text-slate-300 font-normal">(optional override)</span>
            </label>
            <input
              type="email"
              value={clientEmail}
              onChange={(e) => setClientEmail(e.target.value)}
              placeholder="Auto-populated from your employee profile"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-300"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Leave blank to use the client manager configured in your profile. Fill in to override for this submission.
            </p>
          </div>

          {/* Remarks */}
          <div>
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              Remarks <span className="text-slate-300 font-normal">(optional)</span>
            </label>
            <textarea
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              placeholder="Any comments for the client manager…"
              rows={3}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-300 resize-none"
            />
          </div>

          {err && (
            <div className="rounded-xl bg-rose-50 border border-rose-200 px-3 py-2.5 text-xs text-rose-700">
              {err}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 bg-slate-50/50">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || loading}
            className="rounded-xl bg-teal-500 px-5 py-2 text-xs font-bold text-white hover:bg-teal-600 disabled:opacity-60 flex items-center gap-2"
          >
            {submitting ? "Sending…" : "Generate & Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Monthly Report Status Card ────────────────────────────────────────────────

function MonthlyReportCard({ report, cycleStart, cycleEnd, onSendClick }) {
  const RESUBMITTABLE = ["draft", "rejected", "client_rejected"];
  const canResubmit = !report || RESUBMITTABLE.includes(report.status);
  const isLocked    = report && ["manager_approved", "approved", "locked", "processing", "completed"].includes(report.status);
  const pill        = report ? (MONTHLY_STATUS_PILL[report.status] || MONTHLY_STATUS_PILL.pending_client_review) : null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-slate-800">Monthly Client Report</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Payroll cycle: {fmtDisplay(cycleStart)} — {fmtDisplay(cycleEnd)}
          </p>
        </div>
        {canResubmit && (
          <button
            onClick={onSendClick}
            className="rounded-xl bg-teal-500 px-4 py-2 text-xs font-bold text-white hover:bg-teal-600 shadow-sm flex items-center gap-1.5"
          >
            <span>📤</span>
            {RESUBMITTABLE.includes(report?.status) ? "Resubmit Report" : "Send Monthly Report"}
          </button>
        )}
      </div>

      {/* Content */}
      <div className="px-5 py-4">
        {!report ? (
          <div className="py-4 text-center">
            <div className="text-2xl mb-2">📋</div>
            <p className="text-sm text-slate-500 font-medium">No report submitted yet</p>
            <p className="text-xs text-slate-400 mt-1">
              Click <strong>Send Monthly Report</strong> to generate and submit your payroll-cycle report for client approval.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Status row */}
            <div className="flex items-center gap-3 flex-wrap">
              <span
                className="inline-flex items-center rounded-full px-3 py-1 text-xs font-bold"
                style={{ background: pill.bg, color: pill.color }}
              >
                {pill.label}
              </span>
              {isLocked && (
                <span className="text-xs text-slate-400">🔒 Immutable — cannot resubmit</span>
              )}
            </div>

            {/* Details */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <span className="text-slate-400">Submitted</span>
                <div className="font-semibold text-slate-700 mt-0.5">
                  {report.submitted_at
                    ? new Date(report.submitted_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
                    : "—"}
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <span className="text-slate-400">Total Hours</span>
                <div className="font-bold text-teal-600 mt-0.5">
                  {(report.total_logged_hours || 0).toFixed(1)} h
                </div>
              </div>
            </div>

            {/* Review comment if rejected */}
            {RESUBMITTABLE.includes(report.status) && report.review_comment && (
              <div className="rounded-xl bg-rose-50 border border-rose-200 px-3 py-2.5 text-xs text-rose-700">
                <strong>{report.status === "client_rejected" ? "Client comment:" : "Manager comment:"}</strong> {report.review_comment}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function TimesheetsPage({ isClientSite = true }) {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [timesheets, setTimesheets] = useState([]);
  const [attRecords, setAttRecords] = useState([]);
  const [holidayDates, setHolidayDates] = useState(new Set());
  const [loading, setLoading]       = useState(true);
  const [err, setErr]               = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg]               = useState("");

  // Monthly report state
  const [monthlyReport, setMonthlyReport] = useState(null);
  const [monthlyLoading, setMonthlyLoading] = useState(true);
  const [showMonthlyModal, setShowMonthlyModal] = useState(false);
  const { start: cycleStart, end: cycleEnd } = useMemo(() => currentPayrollCycle(), []);

  // Utilization state (current payroll cycle)
  const [utilization, setUtilization] = useState(null);

  const days = useMemo(() => {
    const arr = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [weekStart]);

  const periodStart = fmtIso(days[0]);
  const periodEnd   = fmtIso(days[6]);
  const todayIso    = fmtIso(new Date());

  const load = async () => {
    setLoading(true); setErr(""); setMsg("");
    try {
      const years = [...new Set([days[0].getFullYear(), days[6].getFullYear()])];
      const [ts, recs, ...holidayLists] = await Promise.all([
        tsApi.list({}),
        attendanceSvc.records({ start: periodStart, end: periodEnd }),
        ...years.map((year) => holidaysApi.list(year)),
      ]);
      setTimesheets(Array.isArray(ts) ? ts : []);
      setAttRecords(Array.isArray(recs) ? recs : []);
      setHolidayDates(new Set(
        holidayLists.flatMap((rows) => Array.isArray(rows) ? rows.map((h) => h.date) : [])
      ));
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Failed to load");
    } finally { setLoading(false); }
  };

  const loadMonthlyReport = async () => {
    if (!isClientSite) return;
    setMonthlyLoading(true);
    try {
      const r = await tsApi.monthlyReport.get();
      setMonthlyReport(r);
    } catch (e) {
      // 404 = not submitted yet — that's fine
      setMonthlyReport(null);
    } finally { setMonthlyLoading(false); }
  };

  useEffect(() => { load(); }, [periodStart, periodEnd]); // eslint-disable-line
  useEffect(() => { loadMonthlyReport(); }, []); // eslint-disable-line

  useEffect(() => {
    utilizationApi.me({ start: cycleStart, end: cycleEnd })
      .then(setUtilization)
      .catch(() => setUtilization(null));
  }, [cycleStart, cycleEnd]); // eslint-disable-line

  const activeTs = timesheets.find(
    (t) => t.period_start === periodStart && t.period_end === periodEnd
  ) || null;

  const status    = activeTs?.status || "draft";
  const weekEnded = todayIso > periodEnd;
  const canSubmit = status === "draft" && weekEnded && activeTs !== null;

  const recByDate = useMemo(() => {
    const m = {};
    attRecords.forEach((r) => { m[r.date] = r; });
    return m;
  }, [attRecords]);

  const weekTotal = days.reduce((sum, d) => {
    const r = recByDate[fmtIso(d)];
    return sum + (r ? (r.working_hours || 0) : 0);
  }, 0);

  const handleSubmitWeekly = async () => {
    if (!activeTs) return;
    setSubmitting(true); setErr(""); setMsg("");
    try {
      await tsApi.submit(activeTs.id);
      setMsg("Timesheet submitted for approval.");
      await load();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Submit failed");
    } finally { setSubmitting(false); }
  };

  const handleMonthlySuccess = (result) => {
    setMonthlyReport(result);
    setShowMonthlyModal(false);
    setMsg("Monthly report submitted for client approval! Your manager will be notified.");
  };

  const goPrev     = () => { const d = new Date(weekStart); d.setDate(d.getDate() - 7); setWeekStart(startOfWeek(d)); };
  const goNext     = () => { const d = new Date(weekStart); d.setDate(d.getDate() + 7); setWeekStart(startOfWeek(d)); };
  const goThisWeek = () => setWeekStart(startOfWeek(new Date()));

  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  return (
    <div className="space-y-5">
      {/* ── Weekly timesheet section ── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Timesheets</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Week of {fmtDisplay(periodStart)} — {fmtDisplay(periodEnd)}
          </p>
          {!loading && (
            <p className="text-sm font-semibold text-slate-700 mt-1">
              Total hours this week:{" "}
              <span className="text-teal-600">{weekTotal.toFixed(1)} hrs</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={goPrev}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
            ← Prev Week
          </button>
          <button onClick={goThisWeek}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
            This Week
          </button>
          <button onClick={goNext}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
            Next Week →
          </button>
        </div>
      </div>

      {err && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
      {msg && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{msg}</div>}

      {/* ── Utilization summary for current payroll cycle ── */}
      {utilization && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">My Utilization</h3>
              <p className="text-[10px] text-slate-400 mt-0.5">
                Payroll cycle: {fmtDisplay(cycleStart)} — {fmtDisplay(cycleEnd)}
              </p>
            </div>
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center text-sm font-bold"
              style={{
                background: `conic-gradient(${
                  utilization.utilization_pct >= 80 ? '#10B981' :
                  utilization.utilization_pct >= 60 ? '#F59E0B' : '#EF4444'
                } ${utilization.utilization_pct * 3.6}deg, #F1F5F9 0deg)`,
                color: utilization.utilization_pct >= 80 ? '#047857' : utilization.utilization_pct >= 60 ? '#B45309' : '#B91C1C',
              }}
            >
              {utilization.utilization_pct.toFixed(0)}%
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-slate-100">
            {[
              { label: "Available", value: `${utilization.available_hours.toFixed(0)}h`, color: "text-slate-700" },
              { label: "Logged",    value: `${utilization.total_logged_hours.toFixed(1)}h`, color: "text-teal-600" },
              { label: "Billable",  value: `${utilization.billable_hours.toFixed(1)}h`,     color: "text-emerald-600" },
              { label: "Non-Billable", value: `${utilization.non_billable_hours.toFixed(1)}h`, color: "text-amber-600" },
            ].map((s) => (
              <div key={s.label} className="px-4 py-3 text-center">
                <div className={`text-base font-bold ${s.color}`}>{s.value}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weekly table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <div className="px-4 py-10 text-center text-xs text-slate-400">Loading…</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5 text-left font-bold">Day</th>
                <th className="px-4 py-2.5 text-left font-bold">Date</th>
                <th className="px-4 py-2.5 text-left font-bold">Clock In</th>
                <th className="px-4 py-2.5 text-left font-bold">Clock Out</th>
                <th className="px-4 py-2.5 text-left font-bold">Hours</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {days.map((d, i) => {
                const iso     = fmtIso(d);
                const rec     = recByDate[iso];
                const weekend = isWeekend(d);
                const holiday = holidayDates.has(iso);
                return (
                  <tr key={iso} className={(weekend || holiday) ? "bg-slate-50/50" : "hover:bg-slate-50/30"}>
                    <td className="px-4 py-3 font-semibold text-slate-700">{DAY_NAMES[i]}</td>
                    <td className="px-4 py-3 text-slate-600">{fmtDisplay(iso)}</td>
                    <td className="px-4 py-3 text-slate-600">{rec ? fmtTime(rec.check_in_time) : "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{rec ? fmtTime(rec.check_out_time) : "—"}</td>
                    <td className="px-4 py-3">
                      <HoursCell rec={rec} day={d} isoDate={iso} todayIso={todayIso} isHoliday={holiday} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Status badge + weekly submit */}
      {!loading && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <StatusBadge status={status} reviewComment={activeTs?.review_comment} />
          {canSubmit && (
            <button
              onClick={handleSubmitWeekly}
              disabled={submitting}
              className="rounded-lg bg-teal-500 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-600 disabled:opacity-60"
            >
              {submitting ? "Submitting…" : "Submit for Approval"}
            </button>
          )}
        </div>
      )}

      {/* ── Monthly Client Report section (client_site only) ── */}
      {isClientSite && (
        <div>
          {/* Divider */}
          <div className="flex items-center gap-3 my-2">
            <div className="flex-1 h-px bg-slate-100" />
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Monthly Payroll Report</span>
            <div className="flex-1 h-px bg-slate-100" />
          </div>

          {monthlyLoading ? (
            <div className="rounded-2xl border border-slate-200 bg-white px-5 py-6 text-center text-xs text-slate-400">
              Loading monthly report…
            </div>
          ) : (
            <MonthlyReportCard
              report={monthlyReport}
              cycleStart={cycleStart}
              cycleEnd={cycleEnd}
              onSendClick={() => setShowMonthlyModal(true)}
            />
          )}
        </div>
      )}

      {/* Recent weekly timesheets history */}
      {timesheets.filter((t) => t.period_type === "weekly" || !t.period_type).length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Recent Weekly Timesheets</h3>
          </div>
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2 text-left font-bold">Period</th>
                <th className="px-4 py-2 text-right font-bold">Hours</th>
                <th className="px-4 py-2 text-left font-bold pl-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {timesheets
                .filter((t) => t.period_type === "weekly" || !t.period_type)
                .slice(0, 12)
                .map((t) => {
                  const b = TS_BADGES[t.status] || TS_BADGES.draft;
                  return (
                    <tr key={t.id} className="hover:bg-slate-50/50">
                      <td className="px-4 py-2.5 text-slate-600">
                        {fmtDisplay(t.period_start)} – {fmtDisplay(t.period_end)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-semibold text-slate-700">
                        {(t.total_logged_hours || 0).toFixed(1)} h
                      </td>
                      <td className="px-4 py-2.5 pl-4">
                        <span className={"inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold " + b.bg + " " + b.text}>
                          {(t.status || "draft").replace(/_/g, " ")}
                        </span>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}

      {/* Monthly report submission modal */}
      {showMonthlyModal && (
        <MonthlyReportModal
          onClose={() => setShowMonthlyModal(false)}
          onSuccess={handleMonthlySuccess}
          cycleStart={cycleStart}
          cycleEnd={cycleEnd}
        />
      )}
    </div>
  );
}
