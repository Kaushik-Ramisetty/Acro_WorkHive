import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { attendance, regularization, compOffApi, overtimeApi, weeklyOffApi } from "../../../services/attendance";
import { useAuth } from "../../../context/AuthContext";
import Timesheets from "../../../components/Timesheets";
import RegularizeModal from "../../../components/RegularizeModal";
import { attendanceUnits, fmtDays } from "../../../utils/attendanceUtils";

// ── Design tokens ─────────────────────────────────────────────────────────────
const TEAL    = "#14b8a6";
const TEAL_DK = "#0d9488";
const FONT    = "'DM Sans', system-ui, sans-serif";

// Default shift window (fallback when API returns no shift data)
const DEFAULT_SHIFT_START = "09:00";
const DEFAULT_SHIFT_END   = "18:00";

// ── Status display config ─────────────────────────────────────────────────────
const STATUS_CFG = {
  present:        { label: "Present",    bg: "#D1FAE5", color: "#047857", dot: "#10B981" },
  late:           { label: "Late",       bg: "#FEF3C7", color: "#B45309", dot: "#F59E0B" },
  half_day:       { label: "Half Day",   bg: "#FFEDD5", color: "#C2410C", dot: "#F97316" },
  halfday:        { label: "Half Day",   bg: "#FFEDD5", color: "#C2410C", dot: "#F97316" },
  on_leave:       { label: "On Leave",   bg: "#EDE9FE", color: "#6D28D9", dot: "#A855F7" },
  holiday:        { label: "Holiday",    bg: "#E0F2FE", color: "#0369A1", dot: "#38BDF8" },
  absent:         { label: "Absent",     bg: "#FEE2E2", color: "#B91C1C", dot: "#EF4444" },
  wfh:            { label: "WFH",        bg: "#DBEAFE", color: "#1D4ED8", dot: "#3B82F6" },
  work_from_home: { label: "WFH",        bg: "#DBEAFE", color: "#1D4ED8", dot: "#3B82F6" },
  weekly_off:     { label: "Weekly Off", bg: "var(--hrms-surface-2)", color: "var(--hrms-text-2)", dot: "var(--hrms-text-faint)" },
};

function getStatusCfg(status) {
  return STATUS_CFG[(status || "").toLowerCase()] || { label: status || "—", bg: "var(--hrms-surface-2)", color: "var(--hrms-text-muted)", dot: "var(--hrms-text-faint)" };
}

// ── Pure formatters ───────────────────────────────────────────────────────────
function fmtIso(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fmtTime(t) {
  if (!t) return "—";
  return String(t).slice(0, 5);
}
function fmtTimeMeridiem(t) {
  if (!t) return "—";
  const [h, m] = String(t).split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const h12    = ((h + 11) % 12) + 1;
  return `${h12}:${String(m).padStart(2,"0")} ${period}`;
}
function fmtElapsed(secs) {
  const totalMins = Math.floor(secs / 60);
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2,"0")}m`;
  return `${m}m`;
}
function hoursLabel(h) {
  if (h == null) return "—";
  const totalMins = Math.round(h * 60);
  const hh = Math.floor(totalMins / 60);
  const mm = totalMins % 60;
  return `${hh}h ${String(mm).padStart(2,"0")}m`;
}
function fmtLateMins(mins) {
  if (!mins || mins <= 0) return "";
  const h = Math.floor(mins / 60), m = mins % 60;
  if (h > 0 && m > 0) return `Late ${h}h ${m}m`;
  if (h > 0) return `Late ${h}h`;
  return `Late ${m}m`;
}
function timeStrToMins(t) {
  if (!t) return 0;
  const [h, m] = String(t).split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}
function parseCheckInTimestamp(timeStr) {
  if (!timeStr) return null;
  const now = new Date();
  const [h, m, s] = timeStr.split(":").map(Number);
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m || 0, s || 0, 0);
}
function buildCalendar(records, year, month) {
  const first       = new Date(year, month, 1);
  const last        = new Date(year, month + 1, 0);
  const startOffset = (first.getDay() + 6) % 7;
  const totalCells  = Math.ceil((startOffset + last.getDate()) / 7) * 7;
  const byDate      = Object.fromEntries(records.map((r) => [r.date, r]));
  const cells       = [];
  for (let i = 0; i < totalCells; i++) {
    const dayNum = i - startOffset + 1;
    if (dayNum < 1 || dayNum > last.getDate()) { cells.push({ d: null }); continue; }
    const iso = `${year}-${String(month+1).padStart(2,"0")}-${String(dayNum).padStart(2,"0")}`;
    const r   = byDate[iso];
    cells.push({ d: dayNum, iso, status: r?.status || null, record: r });
  }
  return cells;
}

// Regularize modal lives in `src/components/RegularizeModal.jsx` — same
// behaviour and styling, shared with the Employee Dashboard's Quick Action.

// ── Attendance Stats Card ─────────────────────────────────────────────────────
function AttendanceStatsCard({ records, presentCount, attendancePct, totalWorkHrs }) {
  const halfDays  = records.filter(r => ["half_day","halfday"].includes((r.status||"").toLowerCase())).length;
  const leaveDays = records.filter(r => r.status === "on_leave").length;
  const lateDays  = records.filter(r => (r.late_minutes || 0) > 0 || r.status === "late").length;
  const fullPresent = records.filter(r => ["present","late","wfh","work_from_home"].includes((r.status||"").toLowerCase())).length;
  const onTimePct = fullPresent > 0 ? Math.round(((fullPresent - lateDays) / fullPresent) * 100) : 100;
  const avgHrs    = presentCount > 0 ? totalWorkHrs / Math.max(presentCount, 1) : 0;

  const metrics = [
    { label: "Avg hrs / day",    value: presentCount > 0 ? hoursLabel(avgHrs) : "—",    icon: "⏱" },
    { label: "On-time arrival",  value: `${onTimePct}%`,                                icon: "✅" },
    { label: "Present days",     value: fmtDays(presentCount),                          icon: "📅" },
    { label: "Half days",        value: String(halfDays),                               icon: "🌗" },
    { label: "Leave taken",      value: String(leaveDays) + " d",                       icon: "🏖" },
    { label: "Late arrivals",    value: String(lateDays),                               icon: "🕐" },
    { label: "Attendance %",     value: `${attendancePct}%`,                            icon: "📊" },
    { label: "Total hours",      value: hoursLabel(totalWorkHrs),                       icon: "⌛" },
  ];

  return (
    <div style={{ fontFamily: FONT, background: "var(--hrms-surface)", borderRadius: 16,
      border: "1px solid var(--hrms-border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
      {/* Header */}
      <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid var(--hrms-border)" }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: "var(--hrms-text)" }}>Attendance Stats</div>
        <div style={{ fontSize: 11, color: "var(--hrms-text-faint)", marginTop: 2 }}>Current period summary</div>
      </div>
      {/* Metric rows */}
      <div style={{ padding: "8px 0" }}>
        {metrics.map((m, i) => (
          <div key={m.label} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 20px",
            borderBottom: i < metrics.length - 1 ? "1px solid var(--hrms-border)" : "none",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 14 }}>{m.icon}</span>
              <span style={{ fontSize: 11.5, color: "var(--hrms-text-muted)", fontWeight: 500 }}>{m.label}</span>
            </div>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)" }}>{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Shift Timeline Card ───────────────────────────────────────────────────────
function ShiftTimelineCard({ todayRec, liveElapsed, clockNow, isWfo }) {
  const DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const todayDow   = (new Date().getDay() + 6) % 7; // 0=Mon, 6=Sun

  const shiftStart = DEFAULT_SHIFT_START;
  const shiftEnd   = DEFAULT_SHIFT_END;
  const shiftStartMins = timeStrToMins(shiftStart);
  const shiftEndMins   = timeStrToMins(shiftEnd);
  const totalShiftMins = shiftEndMins - shiftStartMins;

  const checkIn  = todayRec?.check_in_time;
  const checkOut = todayRec?.check_out_time;
  const checkInMins  = checkIn  ? timeStrToMins(checkIn)  : null;
  const checkOutMins = checkOut ? timeStrToMins(checkOut) : null;

  const nowMins = clockNow.getHours() * 60 + clockNow.getMinutes();

  const clampPct = (mins) => Math.min(100, Math.max(0, ((mins - shiftStartMins) / totalShiftMins) * 100));
  const nowPosPct    = clampPct(nowMins);
  const checkInPct   = checkInMins  != null ? clampPct(checkInMins)  : null;
  const checkOutPct  = checkOutMins != null ? clampPct(checkOutMins) : null;
  const activeEndPct = checkInPct != null
    ? (checkOutPct != null ? checkOutPct : Math.min(nowPosPct, 100))
    : null;

  const workedMins = checkInMins != null
    ? (checkOutMins != null ? checkOutMins : Math.min(nowMins, shiftEndMins)) - checkInMins
    : 0;
  const overtimeMins = checkOutMins != null
    ? Math.max(0, checkOutMins - shiftEndMins) : 0;

  const isActive = !!checkIn && !checkOut;

  return (
    <div style={{ fontFamily: FONT, background: "var(--hrms-surface)", borderRadius: 16,
      border: "1px solid var(--hrms-border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)", padding: 20 }}>
      {/* Card title */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: "var(--hrms-text)" }}>Today's Shift</div>
          <div style={{ fontSize: 11, color: "var(--hrms-text-faint)", marginTop: 2 }}>
            {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric" })}
          </div>
        </div>
        {isActive && (
          <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px",
            background: "#ECFDF5", borderRadius: 999 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#10B981",
              animation: "pulse 1.5s infinite" }} />
            <span style={{ fontSize: 10, fontWeight: 700, color: "#047857" }}>LIVE</span>
          </div>
        )}
      </div>

      {/* Weekday row */}
      <div style={{ display: "flex", gap: 4, marginBottom: 18 }}>
        {DAYS_SHORT.map((d, i) => (
          <div key={d} style={{
            flex: 1, height: 32, borderRadius: 8, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 10.5, fontWeight: i === todayDow ? 800 : 500,
            background: i === todayDow ? TEAL : "var(--hrms-surface-2)",
            color: i === todayDow ? "#fff" : i >= 5 ? "var(--hrms-text-faint)" : "var(--hrms-text-muted)",
            border: i === todayDow ? "none" : "1px solid var(--hrms-border)",
          }}>{d}</div>
        ))}
      </div>

      {/* Shift label row */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6,
        fontSize: 10.5, fontWeight: 600, color: "var(--hrms-text-faint)" }}>
        <span>Shift Start: {fmtTimeMeridiem(shiftStart)}</span>
        <span>Shift End: {fmtTimeMeridiem(shiftEnd)}</span>
      </div>

      {/* Progress bar */}
      <div style={{ position: "relative", height: 10, background: "var(--hrms-border)",
        borderRadius: 999, marginBottom: 8, overflow: "visible" }}>
        {/* Worked fill */}
        {checkInPct != null && activeEndPct != null && (
          <div style={{
            position: "absolute", left: `${checkInPct}%`,
            width: `${Math.max(0, activeEndPct - checkInPct)}%`,
            height: "100%", background: `linear-gradient(90deg, ${TEAL}, ${TEAL_DK})`,
            borderRadius: 999, transition: "width 0.5s ease",
          }} />
        )}
        {/* Overtime fill */}
        {checkOutPct != null && checkOutPct > 100 && (
          <div style={{
            position: "absolute", left: "100%", width: "6%",
            height: "100%", background: "#F59E0B", borderRadius: "0 999px 999px 0",
          }} />
        )}
        {/* Check-in marker */}
        {checkInPct != null && (
          <div title={`Check-in: ${fmtTimeMeridiem(checkIn)}`}
            style={{ position: "absolute", left: `calc(${checkInPct}% - 5px)`, top: -3,
              width: 10, height: 16, borderRadius: 3, background: TEAL,
              border: "2px solid var(--hrms-surface)", boxShadow: "0 1px 3px rgba(0,0,0,0.15)" }} />
        )}
        {/* Check-out marker */}
        {checkOutPct != null && (
          <div title={`Check-out: ${fmtTimeMeridiem(checkOut)}`}
            style={{ position: "absolute", left: `calc(${checkOutPct}% - 5px)`, top: -3,
              width: 10, height: 16, borderRadius: 3, background: "var(--hrms-text)",
              border: "2px solid var(--hrms-surface)", boxShadow: "0 1px 3px rgba(0,0,0,0.15)" }} />
        )}
        {/* Now marker (only when checked in and not checked out) */}
        {isActive && (
          <div title="Now"
            style={{ position: "absolute", left: `calc(${Math.min(nowPosPct,100)}% - 1.5px)`,
              top: -4, width: 3, height: 18, background: "#EF4444", borderRadius: 999 }} />
        )}
      </div>

      {/* Time labels */}
      <div style={{ display: "flex", justifyContent: "space-between",
        fontSize: 9.5, fontWeight: 500, color: "var(--hrms-text-faint)", marginBottom: 18 }}>
        <span>{fmtTimeMeridiem(shiftStart)}</span>
        <span>{fmtTimeMeridiem(shiftEnd)}</span>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { label: "Check-in",      value: checkIn  ? fmtTimeMeridiem(checkIn)  : "—",                       color: TEAL     },
          { label: "Check-out",     value: checkOut ? fmtTimeMeridiem(checkOut) : isActive ? "Pending" : "—", color: "var(--hrms-text)" },
          { label: "Work Duration", value: isActive
              ? (liveElapsed > 0 ? fmtElapsed(liveElapsed) : "—")
              : (workedMins > 0 ? hoursLabel(workedMins / 60) : "—"),
            color: isActive ? TEAL : "var(--hrms-text)",                                                       pulse: isActive },
          { label: "Overtime",      value: overtimeMins > 0 ? `+${hoursLabel(overtimeMins/60)}` : "—",        color: "#F59E0B" },
        ].map((s) => (
          <div key={s.label} style={{ flex: 1, background: "var(--hrms-surface-2)", borderRadius: 10,
            padding: "10px 12px", border: "1px solid var(--hrms-border)" }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--hrms-text-faint)",
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              {s.label}
            </div>
            <div style={{ fontSize: 13, fontWeight: 800, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {isWfo && (
        <div style={{ marginTop: 12, background: "#EFF6FF", border: "1px solid #BFDBFE",
          borderRadius: 8, padding: "8px 12px", fontSize: 11, color: "#1D4ED8", fontWeight: 500 }}>
          Biometric attendance — app punch is not available for WFO employees.
        </div>
      )}
    </div>
  );
}

// ── Quick Actions Card ────────────────────────────────────────────────────────
function QuickActionsCard({ todayRec, todayState, busy, onPunchIn, onPunchOut, onRegularize, isWfo, punchMsg }) {
  const [clock, setClock] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const MIN_CHECKOUT_HOURS = 6;

  const checkIn  = todayRec?.check_in_time;
  const checkOut = todayRec?.check_out_time;
  const status   = (todayRec?.status || "").toLowerCase();
  const isSpecial = ["on_leave","holiday","absent"].includes(status);
  const isCheckedIn  = todayState?.has_checked_in  ?? !!checkIn;
  const isCheckedOut = todayState?.has_checked_out ?? !!checkOut;

  const earliestCheckoutDate = (() => {
    if (!checkIn) return null;
    const parts = String(checkIn).split(":").map(Number);
    const d = new Date();
    d.setHours(parts[0], parts[1], parts[2] || 0, 0);
    d.setTime(d.getTime() + MIN_CHECKOUT_HOURS * 3600 * 1000);
    return d;
  })();
  const earliestCheckoutStr = earliestCheckoutDate
    ? `${String(earliestCheckoutDate.getHours()).padStart(2, "0")}:${String(earliestCheckoutDate.getMinutes()).padStart(2, "0")}`
    : null;
  const checkoutEligible = !earliestCheckoutDate || clock >= earliestCheckoutDate;

  const canPunchIn   = !isCheckedIn && !isSpecial && !isWfo;
  const canPunchOut  = isCheckedIn && !isCheckedOut && !isSpecial && !isWfo && checkoutEligible;
  const overtimeHrs  = todayRec?.overtime_hours || 0;
  const lateMins     = todayRec?.late_minutes || 0;
  const cfg          = getStatusCfg(status || "not_marked");

  const hh   = String(clock.getHours()).padStart(2,"0");
  const mm   = String(clock.getMinutes()).padStart(2,"0");
  const ss   = String(clock.getSeconds()).padStart(2,"0");
  const ampm = clock.getHours() >= 12 ? "PM" : "AM";
  const h12  = ((clock.getHours() + 11) % 12) + 1;

  const quickLinks = [
    { icon: "📝", label: "Regularize Attendance", onClick: onRegularize },
    { icon: "📋", label: "Attendance Policy",      onClick: () => {} },
  ];

  return (
    <div style={{ fontFamily: FONT, background: "var(--hrms-surface)", borderRadius: 16,
      border: "1px solid var(--hrms-border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)", padding: 20 }}>
      {/* Live clock */}
      <div style={{ textAlign: "center", marginBottom: 18, padding: "16px 0 12px",
        background: "linear-gradient(135deg, #F0FDFA 0%, #ECFDF5 100%)",
        borderRadius: 12, border: "1px solid #CCFBF1" }}>
        <div style={{ fontSize: 30, fontWeight: 800, color: "var(--hrms-text)", letterSpacing: -1,
          fontVariantNumeric: "tabular-nums" }}>
          {h12}:{mm}
          <span style={{ fontSize: 16, color: "var(--hrms-text-faint)", marginLeft: 4 }}>{ss}</span>
          <span style={{ fontSize: 14, color: "var(--hrms-text-muted)", marginLeft: 6, fontWeight: 600 }}>{ampm}</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--hrms-text-muted)", marginTop: 3, fontWeight: 500 }}>
          {clock.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric" })}
        </div>
      </div>

      {/* Status badge */}
      {status && (
        <div style={{ textAlign: "center", marginBottom: 14 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
            padding: "4px 14px", borderRadius: 999,
            background: cfg.bg, color: cfg.color,
            fontSize: 11, fontWeight: 700 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.dot }} />
            {cfg.label}
            {lateMins > 0 && ` · ${fmtLateMins(lateMins)}`}
          </span>
        </div>
      )}

      {/* Punch button */}
      {!isWfo && !isSpecial && (
        <button
          onClick={canPunchIn ? onPunchIn : canPunchOut ? onPunchOut : undefined}
          disabled={busy || (!canPunchIn && !canPunchOut)}
          style={{
            width: "100%", padding: "13px 0", borderRadius: 12, border: "none",
            fontSize: 13, fontWeight: 800, cursor: busy || (!canPunchIn && !canPunchOut) ? "default" : "pointer",
            background: busy ? "var(--hrms-text-faint)"
              : canPunchIn  ? `linear-gradient(135deg, ${TEAL}, ${TEAL_DK})`
              : canPunchOut ? "linear-gradient(135deg, #3B82F6, #1D4ED8)"
              : "var(--hrms-surface-2)",
            color: (canPunchIn || canPunchOut) && !busy ? "#fff" : "var(--hrms-text-faint)",
            boxShadow: (canPunchIn || canPunchOut) && !busy ? "0 4px 12px rgba(20,184,166,0.3)" : "none",
            transition: "all 0.2s",
            marginBottom: 12,
          }}>
          {busy ? "Processing…"
            : canPunchIn  ? "✓  Check In"
            : canPunchOut ? "⏏  Check Out"
            : isCheckedOut ? "✓  Checked Out"
            : "—"}
        </button>
      )}

      {/* Early-checkout info banner */}
      {isCheckedIn && !isCheckedOut && !checkoutEligible && earliestCheckoutStr && (
        <div style={{
          marginBottom: 10,
          padding: "8px 12px",
          borderRadius: 8,
          background: "#FFFBEB",
          color: "#92400E",
          fontSize: 12, fontWeight: 600,
          border: "1px solid #FDE68A",
        }}>
          <div>Minimum work duration: {MIN_CHECKOUT_HOURS} hours</div>
          <div style={{ fontWeight: 500, marginTop: 2, color: "#B45309" }}>
            You can check out after {fmtTimeMeridiem(earliestCheckoutStr)}
          </div>
        </div>
      )}

      {/* Inline punch feedback */}
      {punchMsg?.text && (
        <div style={{
          marginBottom: 10,
          padding: "8px 12px",
          borderRadius: 8,
          background: punchMsg.ok ? "#D1FAE5" : "#FFF7ED",
          color:      punchMsg.ok ? "#047857" : "#C2410C",
          fontSize: 12, fontWeight: 600, textAlign: "center",
          border: `1px solid ${punchMsg.ok ? "#A7F3D0" : "#FED7AA"}`,
        }}>
          {punchMsg.ok ? "✓ " : "ℹ "}{punchMsg.text}
        </div>
      )}

      {/* Check-in / check-out time strip */}
      {(checkIn || isCheckedIn) && (
        <div style={{ background: "var(--hrms-surface-2)", borderRadius: 10, padding: "8px 12px",
          fontSize: 11, color: "var(--hrms-text-muted)", marginBottom: checkOut ? 4 : 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Checked in</span>
            <span style={{ fontWeight: 700, color: "var(--hrms-text)" }}>{checkIn ? fmtTimeMeridiem(checkIn) : "—"}</span>
          </div>
        </div>
      )}
      {(checkOut || isCheckedOut) && (
        <div style={{ background: "#F0FDF4", borderRadius: 10, padding: "8px 12px",
          fontSize: 11, color: "var(--hrms-text-muted)", marginBottom: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Checked out</span>
            <span style={{ fontWeight: 700, color: "#047857" }}>{checkOut ? fmtTimeMeridiem(checkOut) : "—"}</span>
          </div>
          {todayRec?.working_hours != null && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span>Total hours</span>
              <span style={{ fontWeight: 700, color: "var(--hrms-text)" }}>{hoursLabel(todayRec.working_hours)}</span>
            </div>
          )}
        </div>
      )}
      {overtimeHrs > 0 && (
        <div style={{ background: "#FFFBEB", borderRadius: 10, padding: "6px 12px",
          fontSize: 11, marginBottom: 12, display: "flex", justifyContent: "space-between",
          border: "1px solid #FDE68A" }}>
          <span style={{ color: "#92400E", fontWeight: 600 }}>⏱ Overtime</span>
          <span style={{ fontWeight: 700, color: "#B45309" }}>{hoursLabel(overtimeHrs)}</span>
        </div>
      )}
      {!checkIn && !isCheckedIn && !checkOut && !isCheckedOut && <div style={{ marginBottom: 12 }} />}

      {/* Divider */}
      <div style={{ height: 1, background: "var(--hrms-border)", margin: "4px 0 12px" }} />

      {/* Quick links */}
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--hrms-text-faint)",
        textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
        Quick Actions
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {quickLinks.map((q) => (
          <button key={q.label} onClick={q.onClick}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px",
              background: "var(--hrms-surface-2)", border: "1px solid var(--hrms-border)", borderRadius: 10,
              fontSize: 12, fontWeight: 600, color: "var(--hrms-text-2)", cursor: "pointer",
              textAlign: "left", transition: "background 0.15s" }}
            onMouseEnter={e => e.currentTarget.style.background = "#F0FDF4"}
            onMouseLeave={e => e.currentTarget.style.background = "var(--hrms-surface-2)"}>
            <span style={{ fontSize: 14 }}>{q.icon}</span>
            {q.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Month Filter Bar ──────────────────────────────────────────────────────────
function MonthFilterBar({ year, month, filterMode, onSelect }) {
  const opts = useMemo(() => {
    const now = new Date();
    const items = [{ label: "30 DAYS", key: "30days", y: null, m: null }];
    for (let i = 0; i < 6; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      items.push({
        label: d.toLocaleDateString("en-IN", { month: "short", year: "numeric" }).toUpperCase(),
        key:   `${d.getFullYear()}-${d.getMonth()}`,
        y:     d.getFullYear(),
        m:     d.getMonth(),
      });
    }
    return items;
  }, []);

  const activeKey = filterMode === "30days" ? "30days" : `${year}-${month}`;

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", fontFamily: FONT }}>
      {opts.map((o) => {
        const active = activeKey === o.key;
        return (
          <button key={o.key}
            onClick={() => onSelect(o)}
            style={{
              padding: "6px 14px", borderRadius: 999, border: "1px solid",
              borderColor: active ? TEAL : "var(--hrms-border)",
              background: active ? TEAL : "var(--hrms-surface)",
              color: active ? "#fff" : "var(--hrms-text-muted)",
              fontSize: 11, fontWeight: active ? 700 : 600,
              cursor: "pointer", fontFamily: FONT,
              transition: "all 0.15s",
            }}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = getStatusCfg(status);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 9px", borderRadius: 999, fontSize: 10.5, fontWeight: 700,
      background: cfg.bg, color: cfg.color, whiteSpace: "nowrap",
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: cfg.dot }} />
      {cfg.label}
    </span>
  );
}

// ── Attendance Log Table ──────────────────────────────────────────────────────
function AttendanceLogTable({ records, year, month, filterMode, todayRec, liveElapsed, onCompOffRequest, onOvertimeRequest }) {
  const todayIso = fmtIso(new Date());

  const rows = useMemo(() => {
    const byDate = Object.fromEntries(records.map(r => [r.date, r]));
    const now    = new Date(); now.setHours(0,0,0,0);
    const result = [];

    let startDate, endDate;
    if (filterMode === "30days") {
      endDate   = new Date(now);
      startDate = new Date(now); startDate.setDate(now.getDate() - 29);
    } else {
      startDate = new Date(year, month, 1);
      endDate   = new Date(year, month + 1, 0);
    }

    for (let d = new Date(endDate); d >= startDate; d.setDate(d.getDate() - 1)) {
      const iso    = fmtIso(d);
      const dow    = d.getDay();
      const isWknd = dow === 0 || dow === 6;
      const isFuture = d > now;
      const isToday  = iso === todayIso;
      const rec      = byDate[iso];

      if (isFuture && !rec) continue;

      if (rec) {
        result.push({ iso, rec, isWknd, isFuture, isToday, inferred: false });
      } else if (!isFuture && !isWknd) {
        result.push({ iso, rec: null, isWknd, isFuture, isToday, inferred: true, inferredStatus: "absent" });
      }
    }
    return result;
  }, [records, year, month, filterMode, todayIso]);

  const isActiveSession = !!todayRec?.check_in_time && !todayRec?.check_out_time;

  return (
    <div style={{ borderRadius: 12, border: "1px solid var(--hrms-border)", overflow: "hidden",
      boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT }}>
          <thead>
            <tr style={{ background: "var(--hrms-surface-2)", borderBottom: "1px solid var(--hrms-border)" }}>
              {["Date", "Day", "Status", "Check-In", "Check-Out", "Effective Hrs", "OT Hrs", "Note", "Actions"].map((h) => (
                <th key={h} style={{ padding: "11px 16px", textAlign: "left",
                  fontSize: 10, fontWeight: 700, color: "var(--hrms-text-faint)",
                  textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ padding: "32px 16px", textAlign: "center",
                  color: "var(--hrms-text-faint)", fontSize: 13, fontFamily: FONT }}>
                  No attendance records found.
                </td>
              </tr>
            )}
            {rows.map(({ iso, rec, isWknd, isToday, inferred, inferredStatus }) => {
              const status = rec?.status || (inferred ? inferredStatus : null);
              const checkIn  = isToday && rec?.check_in_time  ? rec.check_in_time  : rec?.check_in_time;
              const checkOut = isToday && rec?.check_out_time ? rec.check_out_time : rec?.check_out_time;
              const hrs = isToday && isActiveSession
                ? (liveElapsed > 0 ? fmtElapsed(liveElapsed) : "—")
                : hoursLabel(rec?.working_hours);
              const lateMins = rec?.late_minutes || 0;
              const note = lateMins > 0 ? fmtLateMins(lateMins)
                : inferred ? "No time entries"
                : isWknd ? "Weekend"
                : rec ? "" : "—";

              const dateObj = new Date(iso + "T00:00:00");
              const dateLabel = dateObj.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
              const dayLabel  = dateObj.toLocaleDateString("en-IN", { weekday: "short" });

              return (
                <tr key={iso}
                  style={{
                    borderTop: "1px solid var(--hrms-border)",
                    background: isToday ? "#F0FDFA" : isWknd ? "var(--hrms-surface-2)" : "transparent",
                  }}>
                  {/* Date */}
                  <td style={{ padding: "11px 16px", whiteSpace: "nowrap" }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: isToday ? TEAL : "var(--hrms-text)" }}>
                      {dateLabel}
                      {isToday && (
                        <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, padding: "1px 5px",
                          background: TEAL, color: "#fff", borderRadius: 4 }}>TODAY</span>
                      )}
                    </div>
                  </td>
                  {/* Day */}
                  <td style={{ padding: "11px 16px", fontSize: 12, color: "var(--hrms-text-muted)", fontWeight: 500 }}>
                    {dayLabel}
                  </td>
                  {/* Status */}
                  <td style={{ padding: "11px 16px" }}>
                    {status ? <StatusBadge status={status} />
                      : <span style={{ color: "var(--hrms-text-faint)", fontSize: 12 }}>—</span>}
                  </td>
                  {/* Check-in */}
                  <td style={{ padding: "11px 16px", fontSize: 13, fontWeight: 600,
                    color: checkIn ? "var(--hrms-text)" : "var(--hrms-text-faint)" }}>
                    {checkIn ? fmtTimeMeridiem(checkIn) : "—"}
                  </td>
                  {/* Check-out */}
                  <td style={{ padding: "11px 16px", fontSize: 13,
                    color: checkOut ? "var(--hrms-text)" : isActiveSession && isToday ? TEAL : "var(--hrms-text-faint)",
                    fontWeight: checkOut ? 600 : 400 }}>
                    {checkOut ? fmtTimeMeridiem(checkOut)
                      : isActiveSession && isToday ? "Active…"
                      : "—"}
                  </td>
                  {/* Effective hours */}
                  <td style={{ padding: "11px 16px", fontSize: 13, fontWeight: 700,
                    color: hrs && hrs !== "—" ? "var(--hrms-text)" : "var(--hrms-text-faint)" }}>
                    {hrs || "—"}
                    {isActiveSession && isToday && (
                      <span style={{ marginLeft: 4, width: 6, height: 6, display: "inline-block",
                        borderRadius: "50%", background: "#10B981", verticalAlign: "middle" }} />
                    )}
                  </td>
                  {/* OT Hours */}
                  <td style={{ padding: "11px 16px", fontSize: 12, fontWeight: 600 }}>
                    {rec?.overtime_hours > 0
                      ? <span style={{ color: "#B45309" }}>{hoursLabel(rec.overtime_hours)}</span>
                      : <span style={{ color: "var(--hrms-text-faint)" }}>—</span>}
                  </td>
                  {/* Note */}
                  <td style={{ padding: "11px 16px", fontSize: 11, color: lateMins > 0 ? "#B45309" : "var(--hrms-text-faint)" }}>
                    {note}
                  </td>
                  {/* Actions */}
                  <td style={{ padding: "8px 12px", whiteSpace: "nowrap" }}>
                    <div style={{ display: "flex", gap: 4 }}>
                      {/* Comp-off: weekend with ≥4h worked */}
                      {isWknd && (rec?.working_hours || 0) >= 4 && onCompOffRequest && (
                        <button onClick={() => onCompOffRequest(iso, rec)}
                          title="Request Comp-Off for this weekend day"
                          style={{ fontSize: 10, fontWeight: 700, padding: "4px 8px", borderRadius: 6,
                            border: "1px solid #C7D2FE", background: "#EEF2FF",
                            color: "#4338CA", cursor: "pointer", whiteSpace: "nowrap" }}>
                          + Comp-Off
                        </button>
                      )}
                      {/* Overtime: record has overtime_hours > 0 */}
                      {(rec?.overtime_hours || 0) > 0 && onOvertimeRequest && (
                        <button onClick={() => onOvertimeRequest(iso, rec)}
                          title="Request Overtime Approval"
                          style={{ fontSize: 10, fontWeight: 700, padding: "4px 8px", borderRadius: 6,
                            border: "1px solid #FDE68A", background: "#FFFBEB",
                            color: "#92400E", cursor: "pointer", whiteSpace: "nowrap" }}>
                          + OT Req
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Calendar Tab ──────────────────────────────────────────────────────────────
function CalendarView({ records, year, month }) {
  const cells = useMemo(() => buildCalendar(records, year, month), [records, year, month]);
  const todayIso = fmtIso(new Date());
  const DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

  return (
    <div style={{ fontFamily: FONT }}>
      {/* Day headers */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4,
        marginBottom: 8, textAlign: "center" }}>
        {DAYS.map((d, i) => (
          <div key={d} style={{ fontSize: 10, fontWeight: 700,
            color: "var(--hrms-text-faint)",
            textTransform: "uppercase", letterSpacing: "0.06em", padding: "4px 0" }}>
            {d}
          </div>
        ))}
      </div>
      {/* Calendar grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {cells.map((cell, i) => {
          const isToday  = cell.iso === todayIso;
          const isWknd   = cell.d && (i % 7 >= 5);
          const cfg      = cell.status ? getStatusCfg(cell.status) : null;
          return (
            <div key={i}
              title={cell.record ? `${cfg?.label || cell.status} · ${hoursLabel(cell.record.working_hours)}` : ""}
              style={{
                aspectRatio: "1", borderRadius: 8, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", fontSize: 12,
                background: !cell.d ? "transparent" : isToday ? TEAL : "var(--hrms-surface-2)",
                border: isToday ? `2px solid ${TEAL_DK}` : "1px solid transparent",
                cursor: cell.record ? "pointer" : "default",
              }}>
              {cell.d && (
                <>
                  <span style={{ fontWeight: isToday ? 800 : 600,
                    color: isToday ? "#fff" : isWknd ? "var(--hrms-text-faint)" : "var(--hrms-text-2)",
                    fontSize: 12 }}>{cell.d}</span>
                  {cfg && (
                    <span style={{ width: 5, height: 5, borderRadius: "50%", marginTop: 2,
                      background: isToday ? "rgba(255,255,255,0.7)" : cfg.dot }} />
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
      {/* Legend */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
        {[["#10B981","Present"], ["#F59E0B","Late / Half"], ["#A855F7","On Leave"],
          ["#EF4444","Absent"], ["#38BDF8","Holiday"]].map(([c, l]) => (
          <span key={l} style={{ display: "flex", alignItems: "center", gap: 5,
            fontSize: 11, color: "var(--hrms-text-muted)" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />{l}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Regularization Requests Tab ───────────────────────────────────────────────
function RequestsTab() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [err, setErr]           = useState("");

  useEffect(() => {
    setLoading(true);
    regularization.list()
      .then(r => setRequests(Array.isArray(r) ? r : []))
      .catch(() => setErr("Could not load requests"))
      .finally(() => setLoading(false));
  }, []);

  const STATUS_COLOR = {
    pending:  { bg: "#FEF3C7", color: "#B45309", label: "Pending"  },
    approved: { bg: "#D1FAE5", color: "#047857", label: "Approved" },
    rejected: { bg: "#FEE2E2", color: "#B91C1C", label: "Rejected" },
  };

  if (loading) return <div style={{ padding: 24, textAlign: "center", color: "var(--hrms-text-faint)", fontSize: 13, fontFamily: FONT }}>Loading…</div>;
  if (err)     return <div style={{ padding: 16, background: "#FEE2E2", color: "#B91C1C", borderRadius: 8, fontSize: 12, fontFamily: FONT }}>{err}</div>;
  if (!requests.length) return (
    <div style={{ textAlign: "center", padding: 40, fontFamily: FONT }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
      <div style={{ fontSize: 14, color: "var(--hrms-text-muted)", fontWeight: 600 }}>No regularization requests</div>
      <div style={{ fontSize: 12, color: "var(--hrms-text-faint)", marginTop: 4 }}>Your submitted requests will appear here.</div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontFamily: FONT }}>
      {requests.map((req) => {
        const st = STATUS_COLOR[req.status] || STATUS_COLOR.pending;
        return (
          <div key={req.id} style={{ background: "var(--hrms-surface-2)", border: "1px solid var(--hrms-border)",
            borderRadius: 10, padding: "12px 16px",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)", marginBottom: 2 }}>
                {req.date}
                <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 500, color: "var(--hrms-text-muted)" }}>
                  {req.regularization_type?.replace(/_/g, " ")}
                </span>
              </div>
              {req.reason && (
                <div style={{ fontSize: 11, color: "var(--hrms-text-faint)" }}>"{req.reason}"</div>
              )}
              {req.requested_check_in && (
                <div style={{ fontSize: 11, color: "var(--hrms-text-muted)", marginTop: 2 }}>
                  {fmtTimeMeridiem(req.requested_check_in)} → {fmtTimeMeridiem(req.requested_check_out)}
                </div>
              )}
            </div>
            <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 10.5,
              fontWeight: 700, background: st.bg, color: st.color, whiteSpace: "nowrap" }}>
              {st.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Shared status badge ───────────────────────────────────────────────────────
const REQUEST_STATUS_COLORS = {
  pending:  { bg: "#FEF3C7", color: "#B45309", label: "Pending"  },
  approved: { bg: "#D1FAE5", color: "#047857", label: "Approved" },
  rejected: { bg: "#FEE2E2", color: "#B91C1C", label: "Rejected" },
};
function RequestStatusBadge({ status }) {
  const s = REQUEST_STATUS_COLORS[status] || REQUEST_STATUS_COLORS.pending;
  return (
    <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 10.5,
      fontWeight: 700, background: s.bg, color: s.color, whiteSpace: "nowrap" }}>
      {s.label}
    </span>
  );
}

// ── CompOffRequestModal ───────────────────────────────────────────────────────
function CompOffRequestModal({ open, date, workingHours, onClose, onSubmitted }) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (open) { setReason(""); setErr(""); } }, [open]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true); setErr("");
    try {
      await compOffApi.request({ worked_on: date, reason: reason || undefined });
      onSubmitted?.();
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex.message || "Submission failed");
    } finally { setSubmitting(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, fontFamily: FONT }}>
      <div style={{ background: "var(--hrms-surface)", borderRadius: 16, padding: 28, width: "100%", maxWidth: 420,
        boxShadow: "0 20px 60px rgba(0,0,0,0.2)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "var(--hrms-text)" }}>Request Comp-Off</h3>
          <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer",
            fontSize: 18, color: "var(--hrms-text-faint)" }}>✕</button>
        </div>

        <div style={{ background: "var(--hrms-surface-2)", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--hrms-text-muted)" }}>Date worked</span>
            <span style={{ fontWeight: 700, color: "var(--hrms-text)" }}>{date}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            <span style={{ color: "var(--hrms-text-muted)" }}>Hours worked</span>
            <span style={{ fontWeight: 700, color: "var(--hrms-text)" }}>{hoursLabel(workingHours)}</span>
          </div>
        </div>

        {err && <div style={{ background: "#FEE2E2", color: "#B91C1C", borderRadius: 8,
          padding: "8px 12px", fontSize: 12, marginBottom: 12 }}>{err}</div>}

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Reason (optional)
          </label>
          <textarea
            value={reason} onChange={e => setReason(e.target.value)}
            rows={3} placeholder="Why are you requesting comp-off?"
            style={{ width: "100%", borderRadius: 8, border: "1px solid var(--hrms-border)",
              padding: "10px 12px", fontSize: 12, resize: "vertical", fontFamily: FONT,
              boxSizing: "border-box", marginBottom: 16,
              background: "var(--hrms-surface)", color: "var(--hrms-text)" }}
          />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose}
              style={{ padding: "9px 18px", borderRadius: 9, border: "1px solid var(--hrms-border)",
                background: "var(--hrms-surface)", fontSize: 12, fontWeight: 600, cursor: "pointer",
                color: "var(--hrms-text-2)" }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              style={{ padding: "9px 18px", borderRadius: 9, border: "none",
                background: submitting ? "var(--hrms-text-faint)" : "#4F46E5",
                color: "#fff", fontSize: 12, fontWeight: 700, cursor: submitting ? "default" : "pointer" }}>
              {submitting ? "Submitting…" : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── OvertimeRequestModal ──────────────────────────────────────────────────────
function OvertimeRequestModal({ open, date, recordedOtHours, onClose, onSubmitted }) {
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (open) { setReason(""); setErr(""); setHours(recordedOtHours != null ? String(recordedOtHours) : ""); }
  }, [open, recordedOtHours]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const h = parseFloat(hours);
    if (!h || h <= 0) { setErr("Please enter valid overtime hours."); return; }
    setSubmitting(true); setErr("");
    try {
      await overtimeApi.submit({ date, overtime_hours: h, reason: reason || undefined });
      onSubmitted?.();
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex.message || "Submission failed");
    } finally { setSubmitting(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, fontFamily: FONT }}>
      <div style={{ background: "var(--hrms-surface)", borderRadius: 16, padding: 28, width: "100%", maxWidth: 420,
        boxShadow: "0 20px 60px rgba(0,0,0,0.2)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "var(--hrms-text)" }}>Request Overtime Approval</h3>
          <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer",
            fontSize: 18, color: "var(--hrms-text-faint)" }}>✕</button>
        </div>

        <div style={{ background: "#FFFBEB", borderRadius: 10, padding: "10px 14px",
          marginBottom: 16, fontSize: 12, border: "1px solid #FDE68A" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--hrms-text-muted)" }}>Date</span>
            <span style={{ fontWeight: 700, color: "var(--hrms-text)" }}>{date}</span>
          </div>
          {recordedOtHours > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span style={{ color: "var(--hrms-text-muted)" }}>Recorded OT</span>
              <span style={{ fontWeight: 700, color: "#B45309" }}>{hoursLabel(recordedOtHours)}</span>
            </div>
          )}
        </div>

        {err && <div style={{ background: "#FEE2E2", color: "#B91C1C", borderRadius: 8,
          padding: "8px 12px", fontSize: 12, marginBottom: 12 }}>{err}</div>}

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Overtime Hours
          </label>
          <input type="number" step="0.25" min="0.25" value={hours}
            onChange={e => setHours(e.target.value)}
            style={{ width: "100%", borderRadius: 8, border: "1px solid var(--hrms-border)",
              padding: "10px 12px", fontSize: 13, fontFamily: FONT, boxSizing: "border-box",
              marginBottom: 12, background: "var(--hrms-surface)", color: "var(--hrms-text)" }}
          />
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Reason
          </label>
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3}
            placeholder="Reason for overtime..."
            style={{ width: "100%", borderRadius: 8, border: "1px solid var(--hrms-border)",
              padding: "10px 12px", fontSize: 12, resize: "vertical", fontFamily: FONT,
              boxSizing: "border-box", marginBottom: 16,
              background: "var(--hrms-surface)", color: "var(--hrms-text)" }}
          />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose}
              style={{ padding: "9px 18px", borderRadius: 9, border: "1px solid var(--hrms-border)",
                background: "var(--hrms-surface)", fontSize: 12, fontWeight: 600, cursor: "pointer",
                color: "var(--hrms-text-2)" }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              style={{ padding: "9px 18px", borderRadius: 9, border: "none",
                background: submitting ? "var(--hrms-text-faint)" : "#D97706",
                color: "#fff", fontSize: 12, fontWeight: 700, cursor: submitting ? "default" : "pointer" }}>
              {submitting ? "Submitting…" : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── WeeklyOffRequestModal ─────────────────────────────────────────────────────
function WeeklyOffRequestModal({ open, onClose, onSubmitted }) {
  const DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
  const [requested, setRequested] = useState("Sunday");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (open) { setReason(""); setErr(""); } }, [open]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true); setErr("");
    try {
      await weeklyOffApi.submit({
        requested_weekly_off: requested,
        effective_from: effectiveFrom || undefined,
        reason: reason || undefined,
      });
      onSubmitted?.();
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex.message || "Submission failed");
    } finally { setSubmitting(false); }
  };

  const inputStyle = {
    width: "100%", borderRadius: 8, border: "1px solid var(--hrms-border)",
    padding: "10px 12px", fontSize: 12, fontFamily: FONT, boxSizing: "border-box",
    marginBottom: 12, background: "var(--hrms-surface)", color: "var(--hrms-text)",
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, fontFamily: FONT }}>
      <div style={{ background: "var(--hrms-surface)", borderRadius: 16, padding: 28, width: "100%", maxWidth: 420,
        boxShadow: "0 20px 60px rgba(0,0,0,0.2)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "var(--hrms-text)" }}>Request Weekly-Off Change</h3>
          <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer",
            fontSize: 18, color: "var(--hrms-text-faint)" }}>✕</button>
        </div>

        {err && <div style={{ background: "#FEE2E2", color: "#B91C1C", borderRadius: 8,
          padding: "8px 12px", fontSize: 12, marginBottom: 12 }}>{err}</div>}

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Requested Weekly-Off Day
          </label>
          <select value={requested} onChange={e => setRequested(e.target.value)} style={inputStyle}>
            {DAYS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Effective From (optional)
          </label>
          <input type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} style={inputStyle} />
          <label style={{ display: "block", fontSize: 11, fontWeight: 700,
            color: "var(--hrms-text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
            Reason
          </label>
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3}
            placeholder="Why do you need this change?"
            style={{ ...inputStyle, resize: "vertical", marginBottom: 16 }} />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose}
              style={{ padding: "9px 18px", borderRadius: 9, border: "1px solid var(--hrms-border)",
                background: "var(--hrms-surface)", fontSize: 12, fontWeight: 600, cursor: "pointer",
                color: "var(--hrms-text-2)" }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              style={{ padding: "9px 18px", borderRadius: 9, border: "none",
                background: submitting ? "var(--hrms-text-faint)" : TEAL,
                color: "#fff", fontSize: 12, fontWeight: 700, cursor: submitting ? "default" : "pointer" }}>
              {submitting ? "Submitting…" : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Overtime Requests Tab ─────────────────────────────────────────────────────
function OvertimeRequestsTab() {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");

  useEffect(() => {
    setLoading(true);
    overtimeApi.list()
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(() => setErr("Could not load overtime records"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 24, textAlign: "center", color: "var(--hrms-text-faint)", fontSize: 13, fontFamily: FONT }}>Loading…</div>;
  if (err)     return <div style={{ padding: 16, background: "#FEE2E2", color: "#B91C1C", borderRadius: 8, fontSize: 12, fontFamily: FONT }}>{err}</div>;
  if (!rows.length) return (
    <div style={{ textAlign: "center", padding: 40, fontFamily: FONT }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>⏱</div>
      <div style={{ fontSize: 14, color: "var(--hrms-text-muted)", fontWeight: 600 }}>No overtime records</div>
      <div style={{ fontSize: 12, color: "var(--hrms-text-faint)", marginTop: 4 }}>Overtime requests you submit will appear here.</div>
    </div>
  );

  return (
    <div style={{ borderRadius: 12, border: "1px solid var(--hrms-border)", overflow: "hidden", fontFamily: FONT }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--hrms-surface-2)", borderBottom: "1px solid var(--hrms-border)" }}>
              {["Date", "OT Hours", "Requested On", "Status", "Approved Hrs", "Approver"].map(h => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 10,
                  fontWeight: 700, color: "var(--hrms-text-faint)", textTransform: "uppercase",
                  letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id} style={{ borderTop: "1px solid var(--hrms-border)",
                background: i % 2 === 0 ? "transparent" : "var(--hrms-surface-2)" }}>
                <td style={{ padding: "11px 14px", fontSize: 13, fontWeight: 600, color: "var(--hrms-text)" }}>{r.date || "—"}</td>
                <td style={{ padding: "11px 14px", fontSize: 13, fontWeight: 700, color: "#B45309" }}>
                  {r.overtime_hours != null ? hoursLabel(r.overtime_hours) : "—"}
                </td>
                <td style={{ padding: "11px 14px", fontSize: 12, color: "var(--hrms-text-muted)" }}>
                  {r.created_at ? new Date(r.created_at).toLocaleDateString("en-IN") : "—"}
                </td>
                <td style={{ padding: "11px 14px" }}><RequestStatusBadge status={r.status} /></td>
                <td style={{ padding: "11px 14px", fontSize: 12, color: "var(--hrms-text-muted)" }}>
                  {r.overtime_type === "approved" && r.overtime_hours != null ? hoursLabel(r.overtime_hours) : "—"}
                </td>
                <td style={{ padding: "11px 14px", fontSize: 12, color: "var(--hrms-text-muted)" }}>
                  {r.approved_by ? `#${r.approved_by}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Shift Weekly-Off Requests Tab ─────────────────────────────────────────────
function ShiftWeeklyOffTab({ onNewRequest }) {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");

  const load = useCallback(() => {
    setLoading(true);
    weeklyOffApi.list()
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(() => setErr("Could not load requests"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: 24, textAlign: "center", color: "var(--hrms-text-faint)", fontSize: 13, fontFamily: FONT }}>Loading…</div>;
  if (err)     return <div style={{ padding: 16, background: "#FEE2E2", color: "#B91C1C", borderRadius: 8, fontSize: 12, fontFamily: FONT }}>{err}</div>;

  return (
    <div style={{ fontFamily: FONT }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)" }}>Weekly-Off Change Requests</div>
        <button onClick={onNewRequest}
          style={{ padding: "7px 14px", borderRadius: 9, border: "none", background: TEAL,
            color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
          + New Request
        </button>
      </div>

      {!rows.length ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📅</div>
          <div style={{ fontSize: 14, color: "var(--hrms-text-muted)", fontWeight: 600 }}>No requests yet</div>
          <div style={{ fontSize: 12, color: "var(--hrms-text-faint)", marginTop: 4 }}>
            Submit a request to change your weekly off day.
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {rows.map(req => (
            <div key={req.id} style={{ background: "var(--hrms-surface-2)", border: "1px solid var(--hrms-border)",
              borderRadius: 10, padding: "12px 16px",
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)", marginBottom: 2 }}>
                  {req.current_weekly_off || "Current"} → {req.requested_weekly_off}
                </div>
                {req.effective_from && (
                  <div style={{ fontSize: 11, color: "var(--hrms-text-muted)" }}>Effective: {req.effective_from}</div>
                )}
                {req.reason && (
                  <div style={{ fontSize: 11, color: "var(--hrms-text-faint)", marginTop: 2 }}>"{req.reason}"</div>
                )}
                {req.review_comment && (
                  <div style={{ fontSize: 11, color: "var(--hrms-text-2)", marginTop: 2 }}>
                    Reviewer note: {req.review_comment}
                  </div>
                )}
              </div>
              <RequestStatusBadge status={req.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Comp-Off History Tab ──────────────────────────────────────────────────────
function CompOffHistoryTab() {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");

  useEffect(() => {
    setLoading(true);
    compOffApi.list()
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(() => setErr("Could not load comp-off records"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 24, textAlign: "center", color: "var(--hrms-text-faint)", fontSize: 13 }}>Loading…</div>;
  if (err)     return <div style={{ padding: 16, background: "#FEE2E2", color: "#B91C1C", borderRadius: 8, fontSize: 12 }}>{err}</div>;
  if (!rows.length) return (
    <div style={{ textAlign: "center", padding: 40 }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>🗓</div>
      <div style={{ fontSize: 14, color: "var(--hrms-text-muted)", fontWeight: 600 }}>No comp-off requests</div>
      <div style={{ fontSize: 12, color: "var(--hrms-text-faint)", marginTop: 4 }}>
        Work on a weekend and request comp-off from the Attendance Log tab.
      </div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontFamily: FONT }}>
      {rows.map(r => (
        <div key={r.id} style={{ background: "var(--hrms-surface-2)", border: "1px solid var(--hrms-border)",
          borderRadius: 10, padding: "12px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)", marginBottom: 2 }}>
              Worked: {r.worked_on}
              <span style={{ marginLeft: 8, fontSize: 11, color: "var(--hrms-text-muted)", fontWeight: 500 }}>
                {r.days} day{r.days !== 1 ? "s" : ""}
              </span>
            </div>
            {r.reason && <div style={{ fontSize: 11, color: "var(--hrms-text-faint)" }}>"{r.reason}"</div>}
            {r.expires_on && (
              <div style={{ fontSize: 10, color: "var(--hrms-text-faint)", marginTop: 2 }}>Expires: {r.expires_on}</div>
            )}
            {r.rejection_reason && (
              <div style={{ fontSize: 11, color: "#B91C1C", marginTop: 2 }}>Rejected: {r.rejection_reason}</div>
            )}
          </div>
          <RequestStatusBadge status={r.status} />
        </div>
      ))}
    </div>
  );
}

// ── Main AttendancePage ───────────────────────────────────────────────────────
const AttendancePage = () => {
  const { employee_type } = useAuth();
  const isWfo        = employee_type === "wfo";
  const isClientSite = employee_type === "client_site";

  const today = new Date();
  const [year, setYear]             = useState(today.getFullYear());
  const [month, setMonth]           = useState(today.getMonth());
  const [filterMode, setFilterMode] = useState("monthly");
  const [todayState, setTodayState] = useState(null);
  const [records, setRecords]       = useState([]);
  const [busy, setBusy]             = useState(false);
  const [err, setErr]               = useState("");
  const [punchMsg, setPunchMsg]     = useState({ text: "", ok: true });
  const [showRegularize, setShowRegularize] = useState(false);
  const [outerTab, setOuterTab]     = useState("attendance");
  const [innerTab, setInnerTab]     = useState("log");

  // Modal state
  const [compOffModal, setCompOffModal] = useState(null);
  const [otModal, setOtModal]           = useState(null);
  const [showWoModal, setShowWoModal]   = useState(false);

  // Redirect non-client employees away from timesheets tab
  useEffect(() => {
    if (outerTab === "timesheets" && !isClientSite) {
      setOuterTab("attendance");
    }
  }, [outerTab, isClientSite]);

  // Live clock for timeline bar (updates every minute)
  const [clockNow, setClockNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setClockNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  // ── Data fetching ──
  const getDateRange = useCallback(() => {
    if (filterMode === "30days") {
      const end   = new Date(); end.setHours(23,59,59);
      const start = new Date(); start.setDate(start.getDate() - 29); start.setHours(0,0,0,0);
      return { start: fmtIso(start), end: fmtIso(end) };
    }
    return {
      start: `${year}-${String(month+1).padStart(2,"0")}-01`,
      end:   `${year}-${String(month+1).padStart(2,"0")}-${new Date(year,month+1,0).getDate()}`,
    };
  }, [filterMode, year, month]);

  const refresh = useCallback(async () => {
    setErr("");
    const { start, end } = getDateRange();
    try {
      const [t, recs] = await Promise.all([
        attendance.today(),
        attendance.records({ start, end }),
      ]);
      setTodayState(t);
      setRecords(Array.isArray(recs) ? recs : []);
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Could not load attendance");
    }
  }, [getDateRange]);

  useEffect(() => { refresh(); }, [refresh]);

  // ── Live elapsed timer (seconds) ──
  const timerRef   = useRef(null);
  const [liveElapsed, setLiveElapsed] = useState(0);
  const todayRec = todayState?.record;

  useEffect(() => {
    const checkIn  = todayRec?.check_in_time;
    const checkOut = todayRec?.check_out_time;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (!checkIn || checkOut) {
      setLiveElapsed(todayRec?.working_hours ? Math.round(todayRec.working_hours * 3600) : 0);
      return;
    }
    const startTs = parseCheckInTimestamp(checkIn);
    if (!startTs) return;
    const tick = () => setLiveElapsed(Math.max(0, Math.floor((Date.now() - startTs.getTime()) / 1000)));
    tick();
    timerRef.current = setInterval(tick, 60_000);
    return () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };
  }, [todayRec?.check_in_time, todayRec?.check_out_time]); // eslint-disable-line

  // ── Derived stats ──
  const presentCount = records.reduce((s, r) => s + attendanceUnits(r.status), 0);

  const { attendancePct, attnWorkingDays } = useMemo(() => {
    const now = new Date(); now.setHours(0,0,0,0);
    let upToDay;
    if (filterMode === "30days") {
      upToDay = 30;
    } else {
      const isCurrent = year === now.getFullYear() && month === now.getMonth();
      upToDay = isCurrent ? now.getDate() : new Date(year, month+1, 0).getDate();
    }
    let wd = 0;
    if (filterMode !== "30days") {
      for (let d = 1; d <= upToDay; d++) {
        const dow = new Date(year, month, d).getDay();
        if (dow !== 0 && dow !== 6) wd++;
      }
    } else {
      for (let i = 0; i < 30; i++) {
        const d = new Date(now); d.setDate(now.getDate() - i);
        if (d.getDay() !== 0 && d.getDay() !== 6) wd++;
      }
    }
    wd -= records.filter(r => r.status === "holiday").length;
    wd  = Math.max(wd, 0);
    const pd = records.filter(r => ["present","late","wfh","work_from_home"].includes(r.status)).length
             + records.filter(r => ["half_day","halfday"].includes(r.status)).length * 0.5;
    return { attendancePct: wd > 0 ? Math.round((pd / wd) * 100) : 0, attnWorkingDays: wd };
  }, [records, year, month, filterMode]);

  const totalWorkHrs = useMemo(() => {
    const now = new Date();
    const isCurrentView = filterMode !== "30days"
      ? year === now.getFullYear() && month === now.getMonth()
      : true;
    const todayIso = fmtIso(now);
    const isActive = isCurrentView && !!todayRec?.check_in_time && !todayRec?.check_out_time;
    const hist = records.reduce((a, r) => {
      if (isActive && r.date === todayIso) return a;
      return a + (r.working_hours || 0);
    }, 0);
    return hist + (isActive ? liveElapsed / 3600 : 0);
  }, [records, filterMode, year, month, todayRec, liveElapsed]);

  const doPunch = async (kind) => {
    setBusy(true); setErr(""); setPunchMsg({ text: "", ok: true });
    try {
      const result = await (kind === "in" ? attendance.checkIn() : attendance.checkOut());
      if (result?.log?.is_valid === false) {
        setPunchMsg({
          text: result.message || (kind === "in" ? "Check-in was rejected." : "Check-out was rejected."),
          ok: false,
        });
      } else {
        const msg = result?.message || (kind === "in" ? "Checked in successfully." : "Checked out successfully.");
        setPunchMsg({ text: msg, ok: true });
        setTimeout(() => setPunchMsg({ text: "", ok: true }), 4000);
      }
      await refresh();
    } catch (e) {
      setPunchMsg({ text: e?.data?.detail || e.message || "Punch failed. Please try again.", ok: false });
    } finally { setBusy(false); }
  };

  const handleFilterSelect = (opt) => {
    if (opt.key === "30days") { setFilterMode("30days"); }
    else { setFilterMode("monthly"); setYear(opt.y); setMonth(opt.m); }
  };

  const monthLabel = new Date(year, month, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

  // ── Outer tab buttons ──
  const outerTabBtn = (key, label) => (
    <button key={key} onClick={() => setOuterTab(key)}
      style={{
        padding: "7px 18px", borderRadius: 8, border: "none", cursor: "pointer",
        fontFamily: FONT, fontSize: 12, fontWeight: outerTab === key ? 700 : 500,
        background: outerTab === key ? TEAL : "transparent",
        color: outerTab === key ? "#fff" : "var(--hrms-text-muted)",
        transition: "all 0.15s",
      }}>{label}</button>
  );

  // ── Inner tab definitions ──
  const INNER_TABS = [
    { key: "log",       label: "Attendance Log"   },
    { key: "calendar",  label: "Calendar"          },
    { key: "requests",  label: "Requests"          },
    { key: "overtime",  label: "Overtime Requests" },
    { key: "weeklyoff", label: "Shift Weekly Off"  },
    { key: "compoff",   label: "Comp-Off"          },
  ];

  return (
    <div style={{ fontFamily: FONT, minHeight: "100vh" }}>
      {/* ── Page header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 20, flexWrap: "wrap", gap: 10 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--hrms-text)", margin: 0 }}>Attendance</h1>
          <p style={{ fontSize: 12, color: "var(--hrms-text-faint)", marginTop: 3 }}>
            Track daily attendance, work hours, history, and timesheets.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {outerTab === "attendance" && (
            <button onClick={() => setShowRegularize(true)}
              style={{ padding: "8px 16px", borderRadius: 10, border: "none",
                background: TEAL, color: "#fff", fontSize: 12, fontWeight: 700,
                cursor: "pointer", fontFamily: FONT }}>
              + Regularize
            </button>
          )}
        </div>
      </div>

      {/* ── Outer tabs: Attendance | Timesheets (Timesheets only for client-site) ── */}
      <div style={{ display: "inline-flex", gap: 2, padding: 4, borderRadius: 10,
        border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)", marginBottom: 20 }}>
        {outerTabBtn("attendance", "Attendance")}
        {isClientSite && outerTabBtn("timesheets", "Timesheets")}
      </div>

      {outerTab === "timesheets" ? (
        <Timesheets />
      ) : (
        <>
          {err && (
            <div style={{ background: "#FEE2E2", color: "#B91C1C", padding: "10px 14px",
              borderRadius: 8, fontSize: 12, marginBottom: 16 }}>{err}</div>
          )}

          {/* ── TOP: 3-column grid ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16, marginBottom: 20, alignItems: "stretch" }}
            className="attendance-top-grid">
            <AttendanceStatsCard
              records={records}
              presentCount={presentCount}
              attendancePct={attendancePct}
              totalWorkHrs={totalWorkHrs}
            />
            <ShiftTimelineCard
              todayRec={todayRec}
              liveElapsed={liveElapsed}
              clockNow={clockNow}
              isWfo={isWfo}
            />
            <QuickActionsCard
              todayRec={todayRec}
              todayState={todayState}
              busy={busy}
              onPunchIn={() => doPunch("in")}
              onPunchOut={() => doPunch("out")}
              onRegularize={() => setShowRegularize(true)}
              isWfo={isWfo}
              punchMsg={punchMsg}
            />
          </div>

          {/* ── Month Filter Bar ── */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)" }}>
              {filterMode === "30days" ? "Last 30 Days" : monthLabel}
              <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 500, color: "var(--hrms-text-faint)" }}>
                · {records.length} records · {attnWorkingDays} working days
              </span>
            </div>
            <MonthFilterBar
              year={year} month={month}
              filterMode={filterMode}
              onSelect={handleFilterSelect}
            />
          </div>

          {/* ── Logs & Requests Panel ── */}
          <div style={{ background: "var(--hrms-surface)", borderRadius: 16,
            border: "1px solid var(--hrms-border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            overflow: "hidden" }}>
            {/* Tab bar */}
            <div style={{ display: "flex", borderBottom: "1px solid var(--hrms-border)",
              padding: "0 20px", gap: 0 }}>
              {INNER_TABS.map((t) => (
                <button key={t.key} onClick={() => setInnerTab(t.key)}
                  style={{
                    padding: "13px 18px", border: "none", background: "transparent",
                    cursor: "pointer", fontFamily: FONT, fontSize: 12.5,
                    fontWeight: innerTab === t.key ? 700 : 500,
                    color: innerTab === t.key ? TEAL : "var(--hrms-text-muted)",
                    borderBottom: innerTab === t.key ? `2px solid ${TEAL}` : "2px solid transparent",
                    marginBottom: -1, transition: "all 0.15s",
                  }}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div style={{ padding: 20 }}>
              {innerTab === "log" && (
                <AttendanceLogTable
                  records={records}
                  year={year} month={month}
                  filterMode={filterMode}
                  todayRec={todayRec}
                  liveElapsed={liveElapsed}
                  onCompOffRequest={(date, rec) => setCompOffModal({ date, workingHours: rec?.working_hours })}
                  onOvertimeRequest={(date, rec) => setOtModal({ date, recordedOtHours: rec?.overtime_hours })}
                />
              )}
              {innerTab === "calendar" && (
                <>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--hrms-text)" }}>{monthLabel}</div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button onClick={() => { const d = new Date(year, month-1, 1); setYear(d.getFullYear()); setMonth(d.getMonth()); setFilterMode("monthly"); }}
                        style={{ width: 28, height: 28, borderRadius: 8, border: "1px solid var(--hrms-border)",
                          background: "var(--hrms-surface)", cursor: "pointer", color: "var(--hrms-text-2)", fontSize: 14,
                          display: "flex", alignItems: "center", justifyContent: "center" }}>‹</button>
                      <button onClick={() => { const d = new Date(year, month+1, 1); setYear(d.getFullYear()); setMonth(d.getMonth()); setFilterMode("monthly"); }}
                        style={{ width: 28, height: 28, borderRadius: 8, border: "1px solid var(--hrms-border)",
                          background: "var(--hrms-surface)", cursor: "pointer", color: "var(--hrms-text-2)", fontSize: 14,
                          display: "flex", alignItems: "center", justifyContent: "center" }}>›</button>
                    </div>
                  </div>
                  <CalendarView records={records} year={year} month={month} />
                </>
              )}
              {innerTab === "requests"  && <RequestsTab />}
              {innerTab === "overtime"  && <OvertimeRequestsTab />}
              {innerTab === "weeklyoff" && (
                <ShiftWeeklyOffTab onNewRequest={() => setShowWoModal(true)} />
              )}
              {innerTab === "compoff"   && <CompOffHistoryTab />}
            </div>
          </div>
        </>
      )}

      <RegularizeModal
        open={showRegularize}
        onClose={() => setShowRegularize(false)}
        onSubmitted={refresh}
      />

      <CompOffRequestModal
        open={!!compOffModal}
        date={compOffModal?.date}
        workingHours={compOffModal?.workingHours}
        onClose={() => setCompOffModal(null)}
        onSubmitted={() => setInnerTab("compoff")}
      />

      <OvertimeRequestModal
        open={!!otModal}
        date={otModal?.date}
        recordedOtHours={otModal?.recordedOtHours}
        onClose={() => setOtModal(null)}
        onSubmitted={() => setInnerTab("overtime")}
      />

      <WeeklyOffRequestModal
        open={showWoModal}
        onClose={() => setShowWoModal(false)}
        onSubmitted={() => { setShowWoModal(false); setInnerTab("weeklyoff"); }}
      />

      {/* Responsive CSS */}
      <style>{`
        @media (max-width: 900px) {
          .attendance-top-grid {
            grid-template-columns: 1fr 1fr !important;
          }
        }
        @media (max-width: 580px) {
          .attendance-top-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
};

export default AttendancePage;
