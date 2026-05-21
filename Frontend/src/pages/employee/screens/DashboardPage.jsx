import { useCallback, useEffect, useRef, useState } from "react";
import { formatUsdAsInr } from '../../../utils/formatCurrency';
import { useApp } from "../AppContext";
import { useAuth } from "../../../context/AuthContext";
import { holidays as holidaysApi } from "../../../services/holidays";
import { leaveApi } from "../../../services/leave";
import { regularization } from "../../../services/attendance";
import { attendance as attendanceApi } from "../../../services/attendance";
import RegularizeModal from "../../../components/RegularizeModal";

const statCards = [
  {
    label: "ATTENDANCE",
    value: "98%",
    sub: "↑ 2% vs last month",
    subColor: "#22c55e",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /><path d="M9 16l2 2 4-4" />
      </svg>
    ),
    iconBg: "#f0fdfa",
  },
  {
    label: "LEAVE BALANCE",
    value: "14",
    sub: "Days Available",
    subColor: "#64748b",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
    iconBg: "#eff6ff",
  },
  {
    label: "PENDING REQUESTS",
    value: "2",
    sub: "Requires Action",
    subColor: "#f97316",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
      </svg>
    ),
    iconBg: "#fff7ed",
  },
  {
    label: "UPCOMING HOLIDAY",
    value: "—",
    sub: "Loading…",
    subColor: "#64748b",
    isHolidaySlot: true,
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#a855f7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 12V22H4V12" /><path d="M22 7H2v5h20V7z" /><path d="M12 22V7" /><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z" /><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z" />
      </svg>
    ),
    iconBg: "#faf5ff",
  },
];

const quickActions = [
  {
    label: "Apply Leave",
    action: "applyLeave",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /><path d="M9 16l2 2 4-4" />
      </svg>
    ),
    bg: "#f0fdfa",
  },
  {
    label: "Apply Claim",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    bg: "#eff6ff",
  },
  {
    label: "Regularize Attendance",
    // `local` keeps the action inside this page (opens the shared
    // RegularizeModal) instead of routing through the app-level openModal
    // registry or navigating to the Attendance page.
    local: "regularize",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
    bg: "#f0fdf4",
  },
  {
    label: "Request WFH",
    action: "requestWfh",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
    bg: "#fff7ed",
  },
  {
    label: "View Payslip",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#eab308" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
    bg: "#fefce8",
  },
  {
    label: "View Documents",
    navTo: "documents",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#a855f7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </svg>
    ),
    bg: "#faf5ff",
  },
];

const calendar = {
  month: "October 2023",
  days: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
  weeks: [
    [{ d: 25, prev: true }, { d: 26, prev: true }, { d: 27, prev: true }, { d: 28, prev: true }, { d: 29, prev: true }, { d: 30, dot: "present" }, { d: 1 }],
    [{ d: 2 }, { d: 3 }, { d: 4 }, { d: 5 }, { d: 6 }, { d: 7 }, { d: 8 }],
    [{ d: 9 }, { d: 10, dot: "late" }, { d: 11 }, { d: 12, dot: "absent" }, { d: 13 }, { d: 14 }, { d: 15 }],
    [{ d: 16 }, { d: 17 }, { d: 18 }, { d: 19 }, { d: 20, dot: "present" }, { d: 21 }, { d: 22 }],
    [{ d: 23 }, { d: 24, today: true }, { d: 25, dot: "present" }, { d: 26, dot: "present" }, { d: 27, dot: "present" }, { d: 28 }, { d: 29 }],
    [{ d: 30 }, { d: 31, dot: "present" }, { d: 1, next: true }, { d: 2, next: true }, { d: 3, next: true }, { d: 4, next: true }, { d: 5, next: true }],
  ],
};

const dotColors = { present: "#22c55e", late: "#f97316", absent: "#ef4444", weekoff: "#94a3b8" };

// Per-leave-type accent colour for the dashboard cards. The numbers themselves
// come from /leave/balance/me — see useLeaveBalances() below.
const LEAVE_TYPE_COLOR = {
  'Annual Leave':       '#3b82f6',
  'Casual Leave':       '#f97316',
  'Sick Leave':         '#22c55e',
  'Earned Leave':       '#22c55e',
  'Paid Leaves':        '#22c55e',
  'Compensatory_leave': '#eab308',
  'LOP_leaves':         '#ef4444',
  'Maternity Leave':    '#ec4899',
  'Paternity Leave':    '#8b5cf6',
  'Menstrual Leave':    '#f43f5e',
};
function colorForLeaveType(name) {
  if (!name) return '#3b82f6';
  if (LEAVE_TYPE_COLOR[name]) return LEAVE_TYPE_COLOR[name];
  // Cheap deterministic hash so unknown types get a stable colour.
  const palette = ['#3b82f6', '#22c55e', '#f97316', '#a855f7', '#eab308', '#14b8a6', '#ec4899'];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}
function prettyLeaveTypeName(name) {
  if (!name) return '';
  if (name === 'LOP_leaves')         return 'LOPs';
  if (name === 'Compensatory_leave') return 'Comp-Off';
  return String(name).replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const requests = [
  { label: "Expense Claim", sub: "Submitted on Oct 22, 2023", status: "Pending", statusColor: "#f97316" },
  { label: "Leave Request", sub: "Oct 31 - Nov 02, 2023", status: "Pending", statusColor: "#f97316" },
  { label: "WFH Request", sub: "Nov 3, 2023", status: "Approved", statusColor: "#22c55e" },
  { label: "Document Request", sub: "Experience Letter", status: "Pending", statusColor: "#f97316" },
];

const CircleProgress = ({ pct, color, size = 48, stroke = 4 }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
    </svg>
  );
};

function DatePickerDropdown({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState({ month: value.getMonth(), year: value.getFullYear() });
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const monthLabel = new Date(view.year, view.month, 1)
    .toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const first = new Date(view.year, view.month, 1);
  const last  = new Date(view.year, view.month + 1, 0).getDate();
  const startOffset = (first.getDay() + 6) % 7;
  const cells = [];
  for (let i = 0; i < startOffset; i++) cells.push(null);
  for (let d = 1; d <= last; d++) cells.push(d);
  const isSel = (d) => (
    d === value.getDate() &&
    view.month === value.getMonth() &&
    view.year === value.getFullYear()
  );
  const today = new Date();
  const isToday = (d) => (
    d === today.getDate() &&
    view.month === today.getMonth() &&
    view.year === today.getFullYear()
  );
  const select = (d) => {
    onChange(new Date(view.year, view.month, d));
    setOpen(false);
  };
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-2 bg-white hover:bg-slate-50"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
        </svg>
        <span className="text-xs font-medium text-slate-600">
          {value.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" })}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-white border border-slate-200 rounded-xl shadow-lg p-3 z-30">
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              onClick={() => setView((v) => {
                const d = new Date(v.year, v.month - 1, 1);
                return { month: d.getMonth(), year: d.getFullYear() };
              })}
              className="w-7 h-7 rounded-md hover:bg-slate-100 text-slate-500 flex items-center justify-center"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <span className="text-xs font-bold text-slate-700">{monthLabel}</span>
            <button
              type="button"
              onClick={() => setView((v) => {
                const d = new Date(v.year, v.month + 1, 1);
                return { month: d.getMonth(), year: d.getFullYear() };
              })}
              className="w-7 h-7 rounded-md hover:bg-slate-100 text-slate-500 flex items-center justify-center"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center mb-1">
            {["M","T","W","T","F","S","S"].map((d, i) => (
              <span key={i} className="text-[9px] font-bold text-slate-400">{d}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((d, i) => (
              d == null ? (
                <span key={i} />
              ) : (
                <button
                  key={i}
                  type="button"
                  onClick={() => select(d)}
                  className={`text-[11px] font-medium w-7 h-7 rounded-md flex items-center justify-center
                    ${isSel(d) ? "text-white font-bold" : isToday(d) ? "text-teal-600 font-bold" : "text-slate-600 hover:bg-slate-100"}`}
                  style={isSel(d) ? { background: "#14b8a6" } : {}}
                >
                  {d}
                </button>
              )
            ))}
          </div>
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={() => { onChange(new Date()); setOpen(false); setView({ month: new Date().getMonth(), year: new Date().getFullYear() }); }}
              className="text-[11px] font-semibold text-teal-600 hover:underline"
            >
              Today
            </button>
            <button type="button" onClick={() => setOpen(false)} className="text-[11px] text-slate-400 hover:underline">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

const DashboardPage = () => {
  const { openModal, navigate: appNavigate } = useApp();
  const { user } = useAuth();
  const [nextHoliday, setNextHoliday] = useState(null);
  // All upcoming holidays — used by the modal that opens when the user
  // clicks the "UPCOMING HOLIDAY" stat card.
  const [allHolidays, setAllHolidays] = useState([]);
  const [holidaysModalOpen, setHolidaysModalOpen] = useState(false);
  useEffect(() => {
    holidaysApi.upcoming({ days: 365, limit: 1 })
      .then((rows) => setNextHoliday(Array.isArray(rows) && rows.length ? rows[0] : null))
      .catch(() => setNextHoliday(null));
    // Use the full-year /holidays endpoint so the modal lists every holiday
    // for the current year, not just the next 365 days from "today".
    holidaysApi.list(new Date().getFullYear())
      .then((rows) => setAllHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setAllHolidays([]));
  }, []);
  // Live KPIs
  const [kpiAttn, setKpiAttn] = useState(null);
  const [kpiLeave, setKpiLeave] = useState(null);
  const [kpiPending, setKpiPending] = useState(null);
  // Regularize-attendance modal — opened from the Quick Actions tile.
  const [regOpen, setRegOpen] = useState(false);
  // Refetcher used both on mount and after a regularize submit so the
  // "Pending Requests" KPI tile reflects the just-created row.
  const refreshPendingRegs = useCallback(() => {
    regularization.list({ status: 'pending' })
      .then((rows) => setKpiPending(Array.isArray(rows) ? rows.length : 0))
      .catch(() => setKpiPending(null));
  }, []);
  useEffect(() => {
    const t = new Date();
    const y = t.getFullYear(), m = t.getMonth();
    const start = `${y}-${String(m + 1).padStart(2, '0')}-01`;
    const end   = `${y}-${String(m + 1).padStart(2, '0')}-${new Date(y, m + 1, 0).getDate()}`;
    attendanceApi.records({ start, end })
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        const total = arr.length;
        const present = arr.filter((r) => r.status === 'present' || r.status === 'late').length;
        setKpiAttn({ pct: total ? Math.round((present / total) * 100) : 0, present, total });
      })
      .catch(() => setKpiAttn(null));
    leaveApi.myBalance()
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        const days = arr.reduce((s, b) => s + (b.current_balance || 0) - (b.reserved || 0), 0);
        setKpiLeave({ days });
        // Populate the "My Leave Balance" card with the same payload — used to
        // be a hard-coded mock array. Filter out zero-quota types like LOPs so
        // the card stays focused on actually meaningful balances.
        setLeaveBalanceItems(
          arr.filter((b) => (b.opening_balance || 0) > 0)
        );
      })
      .catch(() => { setKpiLeave(null); setLeaveBalanceItems([]); });
    refreshPendingRegs();
  }, [refreshPendingRegs]);
  // Live leave balances for the "My Leave Balance" card. Populated by the same
  // /leave/balance/me call that drives the KPI tile above.
  const [leaveBalanceItems, setLeaveBalanceItems] = useState([]);

  // Live "My Requests" feed: latest leaves + regularizations.
  const [liveRequests, setLiveRequests] = useState([]);
  useEffect(() => {
    const STATUS_TONE = {
      pending:        '#f97316',
      cancel_pending: '#f97316',
      approved:       '#22c55e',
      consumed:       '#22c55e',
      rejected:       '#ef4444',
      cancelled:      '#94a3b8',
    };
    const STATUS_LABEL = {
      pending: 'Pending', cancel_pending: 'Cancel Pending',
      approved: 'Approved', consumed: 'Approved',
      rejected: 'Rejected', cancelled: 'Cancelled',
    };
    const fmt = (iso) => {
      if (!iso) return '';
      try {
        return new Date(iso).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' });
      } catch { return iso; }
    };
    Promise.all([
      leaveApi.list({}).catch(() => []),
      regularization.list({}).catch(() => []),
    ]).then(([leaves, regs]) => {
      const items = [];
      (Array.isArray(leaves) ? leaves : []).forEach((l) => {
        items.push({
          key: 'L' + l.id,
          label: 'Leave Request',
          sub: `${fmt(l.start_date)} - ${fmt(l.end_date)}`,
          status: STATUS_LABEL[l.status] || l.status,
          statusColor: STATUS_TONE[l.status] || '#64748b',
          when: l.created_at || l.start_date,
        });
      });
      (Array.isArray(regs) ? regs : []).forEach((r) => {
        items.push({
          key: 'R' + r.id,
          label: 'Regularization',
          sub: r.regularization_type ? `${r.regularization_type} - ${fmt(r.date)}` : fmt(r.date),
          status: STATUS_LABEL[r.status] || r.status,
          statusColor: STATUS_TONE[r.status] || '#64748b',
          when: r.created_at || r.date,
        });
      });
      items.sort((a, b) => new Date(b.when || 0) - new Date(a.when || 0));
      setLiveRequests(items.slice(0, 5));
    });
  }, []);
  const fmtHolidayDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });
  };
  // Live calendar (current month) built from attendance.records + holidays.
  const today = new Date();
  const [pickedDate, setPickedDate] = useState(today);
  const [calMonth, setCalMonth] = useState(today.getMonth());
  const [calYear, setCalYear]   = useState(today.getFullYear());
  const [calRecords, setCalRecords] = useState([]);
  const [calHolidays, setCalHolidays] = useState([]);
  useEffect(() => {
    setCalMonth(pickedDate.getMonth());
    setCalYear(pickedDate.getFullYear());
  }, [pickedDate]);
  useEffect(() => {
    const yyyymm = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const last = new Date(calYear, calMonth + 1, 0).getDate();
    const start = yyyymm(calYear, calMonth, 1);
    const end   = yyyymm(calYear, calMonth, last);
    attendanceApi.records({ start, end })
      .then((rows) => setCalRecords(Array.isArray(rows) ? rows : []))
      .catch(() => setCalRecords([]));
    holidaysApi.upcoming({ days: 365, limit: 50 })
      .then((rows) => setCalHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setCalHolidays([]));
  }, [calMonth, calYear]);
  const liveCalendar = (() => {
    const monthLabel = new Date(calYear, calMonth, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
    const recByDate = Object.fromEntries(calRecords.map((r) => [r.date, r]));
    const holDates  = new Set(
      calHolidays
        .map((h) => h.date)
        .filter((d) => {
          const dt = new Date(d);
          return dt.getFullYear() === calYear && dt.getMonth() === calMonth;
        })
    );
    const first = new Date(calYear, calMonth, 1);
    const last  = new Date(calYear, calMonth + 1, 0).getDate();
    const startOffset = (first.getDay() + 6) % 7; // Mon-first
    const cells = [];
    // leading days from prev month
    const prevLast = new Date(calYear, calMonth, 0).getDate();
    for (let i = startOffset - 1; i >= 0; i--) cells.push({ d: prevLast - i, prev: true });
    // current month
    for (let d = 1; d <= last; d++) {
      const iso = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const r = recByDate[iso];
      let dot = null;
      if (holDates.has(iso))                     dot = 'weekoff';
      else if (r?.status === 'present')          dot = 'present';
      else if (r?.status === 'late')             dot = 'late';
      else if (r?.status === 'half_day')         dot = 'late';
      else if (r?.status === 'absent')           dot = 'absent';
      else if (r?.status === 'on_leave')         dot = 'late';
      else if (r?.status === 'holiday')          dot = 'weekoff';
      const isToday = (calYear === today.getFullYear() && calMonth === today.getMonth() && d === today.getDate());
      cells.push({ d, dot, today: isToday });
    }
    // trailing days
    while (cells.length % 7 !== 0) cells.push({ d: cells.length - startOffset - last + 1, next: true });
    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
    return { month: monthLabel, days: ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'], weeks };
  })();
  const renderedStatCards = statCards.map((c) => {
    if (c.label === "ATTENDANCE" && kpiAttn != null) {
      return { ...c, value: `${kpiAttn.pct}%`, sub: `${kpiAttn.present}/${kpiAttn.total} this month` };
    }
    if (c.label === "LEAVE BALANCE" && kpiLeave != null) {
      return { ...c, value: String(kpiLeave.days), sub: 'Days available' };
    }
    if (c.label === "PENDING REQUESTS" && kpiPending != null) {
      return { ...c, value: String(kpiPending), sub: kpiPending ? 'Awaiting decision' : 'All clear' };
    }
    if (!c.isHolidaySlot) return c;
    if (nextHoliday) {
      return { ...c, value: nextHoliday.name, sub: fmtHolidayDate(nextHoliday.date) };
    }
    return { ...c, value: "None", sub: "Nothing scheduled" };
  });
  const greetingName = (user?.first_name) || (user?.full_name?.split(' ')[0]) || (user?.name?.split(' ')[0]) || 'there';
  const greetingTime = (() => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();

  return (
    <div className="space-y-5">
      {/* Greeting */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{`${greetingTime}, ${greetingName}!`} 👋</h1>
          <p className="text-xs text-slate-400 mt-0.5">Here's your personal workspace overview.</p>
        </div>
        <DatePickerDropdown value={pickedDate} onChange={setPickedDate} />
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-3">
        {renderedStatCards.map((c) => (
          <div
            key={c.label}
            onClick={c.isHolidaySlot ? () => setHolidaysModalOpen(true) : undefined}
            role={c.isHolidaySlot ? 'button' : undefined}
            tabIndex={c.isHolidaySlot ? 0 : undefined}
            onKeyDown={c.isHolidaySlot ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setHolidaysModalOpen(true); } } : undefined}
            className={"bg-white rounded-xl border border-slate-100 p-4 shadow-sm" + (c.isHolidaySlot ? " cursor-pointer hover:border-slate-300 hover:shadow-md transition" : "")}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[9px] font-bold tracking-wider text-slate-400">{c.label}</span>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: c.iconBg }}>{c.icon}</div>
            </div>
            <div className="text-xl font-bold text-slate-800 mb-1">{c.value}</div>
            <div className="text-[10px] font-medium" style={{ color: c.subColor }}>{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-xl border border-slate-100 p-5 shadow-sm">
        <h2 className="text-sm font-bold text-slate-700 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-6 gap-3">
          {quickActions.map((a) => (
            <button key={a.label}
              onClick={() => {
                if (a.local === 'regularize') return setRegOpen(true);
                if (a.action) return openModal(a.action);
                if (a.navTo) return appNavigate(a.navTo);
              }}
              className="flex flex-col items-center gap-2.5 p-3 rounded-xl border border-slate-100 hover:border-slate-200 hover:shadow-sm transition-all duration-150 group">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center group-hover:scale-105 transition-transform" style={{ background: a.bg }}>
                {a.icon}
              </div>
              <span className="text-[10px] font-medium text-slate-600 text-center leading-tight">{a.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Bottom grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Attendance Calendar */}
        <div className="bg-white rounded-xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-bold text-slate-700">My Attendance</h2>
            <button type="button" onClick={() => appNavigate('attendance')}
              className="flex items-center gap-1 text-xs font-medium border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-500 hover:bg-slate-50">
              View Full Calendar
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
          </div>
          <p className="text-[11px] font-semibold mb-3" style={{ color: "#14b8a6" }}>{liveCalendar.month}</p>
          <table className="w-full text-center">
            <thead>
              <tr>
                {liveCalendar.days.map((d) => (
                  <th key={d} className="text-[9px] font-bold text-slate-400 pb-2">{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {liveCalendar.weeks.map((week, wi) => (
                <tr key={wi}>
                  {week.map((cell, ci) => (
                    <td key={ci} className="py-1">
                      <div className="flex flex-col items-center gap-0.5">
                        <span className={`text-[11px] font-medium w-6 h-6 flex items-center justify-center rounded-full
                          ${cell.today ? "text-white font-bold" : cell.prev || cell.next ? "text-slate-300" : "text-slate-600"}`}
                          style={cell.today ? { background: "#14b8a6" } : {}}>
                          {cell.d}
                        </span>
                        {cell.dot && <span className="w-1 h-1 rounded-full" style={{ background: dotColors[cell.dot] }} />}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-slate-100">
            {[["#22c55e", "Present"], ["#f97316", "Late"], ["#ef4444", "Absent"], ["#94a3b8", "Weekoff"]].map(([c, l]) => (
              <div key={l} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: c }} />
                <span className="text-[10px] text-slate-500">{l}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Leave Balance */}
          <div className="bg-white rounded-xl border border-slate-100 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-700">My Leave Balance</h2>
              <button type="button" onClick={() => appNavigate('leave')}
                className="text-xs font-semibold" style={{ color: "#14b8a6" }}>View Details</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {leaveBalanceItems.length === 0 && (
                <div className="col-span-2 text-[11px] text-slate-400 py-3">
                  Loading your leave balances…
                </div>
              )}
              {leaveBalanceItems.map((lb) => {
                const total = lb.opening_balance || 0;
                const used  = (lb.used || 0) + (lb.reserved || 0);
                const pct   = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
                const label = prettyLeaveTypeName(lb.leave_type_name);
                const color = colorForLeaveType(lb.leave_type_name);
                const usedLabel = `${lb.used || 0} Day${(lb.used || 0) === 1 ? '' : 's'} Used`;
                return (
                  <div key={lb.id} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100">
                    <CircleProgress pct={pct} color={color} size={42} stroke={4} />
                    <div>
                      <div className="text-xs font-bold text-slate-700">{label}</div>
                      <div className="text-base font-bold text-slate-800">{lb.used || 0} / {total}</div>
                      <div className="text-[10px] text-slate-400">{usedLabel}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* My Requests */}
          <div className="bg-white rounded-xl border border-slate-100 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-700">My Requests</h2>
              <button type="button" onClick={() => appNavigate('myrequests')}
                className="text-xs font-semibold" style={{ color: "#14b8a6" }}>View All</button>
            </div>
            <div className="space-y-3">
              {liveRequests.length === 0 && (
                <div className="text-xs text-slate-400 py-3">No requests yet.</div>
              )}
              {liveRequests.map((r) => (
                <div key={r.key} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-slate-700">{r.label}</div>
                      <div className="text-[10px] text-slate-400">{r.sub}</div>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-1 rounded-full"
                    style={{ color: r.statusColor, background: r.statusColor + "18" }}>
                    {r.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Upcoming Holidays modal */}
      {holidaysModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
             onClick={() => setHolidaysModalOpen(false)}>
          <div className="w-full max-w-md max-h-[80vh] flex flex-col rounded-xl bg-white shadow-2xl"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-800">Holidays — {new Date().getFullYear()}</h3>
                <p className="text-[10px] text-slate-400 mt-0.5">{allHolidays.length} scheduled this year</p>
              </div>
              <button type="button"
                onClick={() => setHolidaysModalOpen(false)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-3">
              {allHolidays.length === 0 ? (
                <p className="py-8 text-center text-xs text-slate-400">No upcoming holidays.</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {allHolidays.map((h, i) => (
                    <li key={(h.id ?? '') + ':' + (h.date ?? i)} className="flex items-center justify-between py-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-700">{h.name}</div>
                        {h.holiday_type && (
                          <div className="text-[10px] text-slate-400 mt-0.5">{h.holiday_type}</div>
                        )}
                      </div>
                      <div className="text-xs font-medium text-slate-500">{fmtHolidayDate(h.date)}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Regularize Attendance modal — opened from the Quick Actions tile
          without leaving the dashboard. Reuses the same component the
          Attendance page hosts, so styling + behaviour are identical. */}
      <RegularizeModal
        open={regOpen}
        onClose={() => setRegOpen(false)}
        onSubmitted={refreshPendingRegs}
      />
    </div>
  );
};

export default DashboardPage;
