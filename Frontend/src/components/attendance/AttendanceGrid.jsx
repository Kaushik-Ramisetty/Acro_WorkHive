/**
 * Shared attendance grid component used by both admin (AttendancePage) and
 * manager (ManagerDashboard > Attendance) views.
 *
 * Presentational only — all data fetching and state live in the host page.
 * The host passes in:
 *   employees  : array of { id, full_name, employee_code }
 *   days       : array of 7 Date objects (Mon..Sun)
 *   cellStatus : (empId, isoDate) => status string | 'unmarked'
 *   busyCell   : "empId-isoDate" key of the cell being saved, or null
 *   onCellClick: (empId, isoDate) => void  — called on click / Enter / Space
 *   loading    : boolean
 *   readOnly   : boolean (default false)
 */

// ─── Status metadata ─────────────────────────────────────────────────────────

export const STATUS_TONE = {
  present:  { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Present'    },
  late:     { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'Late'       },
  absent:   { bg: 'bg-rose-100',    text: 'text-rose-700',    label: 'Absent'     },
  wfh:      { bg: 'bg-teal-100',    text: 'text-teal-700',    label: 'WFH'        },
  on_leave: { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'On Leave'   },
  leave:    { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'On Leave'   },
  half_day: { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'Half Day'   },
  halfday:  { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'Half Day'   },
  holiday:  { bg: 'bg-purple-100',  text: 'text-purple-700',  label: 'Holiday'    },
  unmarked: { bg: 'bg-slate-50',    text: 'text-slate-400',   label: 'Not Marked' },
};

export const LEGEND_ITEMS = [
  { key: 'present',  label: 'Present',    bg: 'bg-emerald-100', text: 'text-emerald-700' },
  { key: 'absent',   label: 'Absent',     bg: 'bg-rose-100',    text: 'text-rose-700'    },
  { key: 'wfh',      label: 'WFH',        bg: 'bg-teal-100',    text: 'text-teal-700'    },
  { key: 'on_leave', label: 'On Leave',   bg: 'bg-blue-100',    text: 'text-blue-700'    },
  { key: 'halfday',  label: 'Half Day',   bg: 'bg-amber-100',   text: 'text-amber-700'   },
  { key: 'holiday',  label: 'Holiday',    bg: 'bg-purple-100',  text: 'text-purple-700'  },
  { key: null,       label: 'Not Marked', bg: 'bg-slate-50',    text: 'text-slate-400'   },
];

// Click-to-cycle order: Not Marked → Present → Absent → WFH → On Leave → Half Day → Holiday → Not Marked
export const CYCLE_ORDER = [null, 'present', 'absent', 'wfh', 'on_leave', 'half_day', 'holiday'];

export function cycleNextStatus(current) {
  const key = (current === 'unmarked' || current === null) ? null : current;
  const idx = CYCLE_ORDER.indexOf(key);
  return CYCLE_ORDER[(idx + 1) % CYCLE_ORDER.length];
}

export function nextStatusLabel(current) {
  const next = cycleNextStatus(current);
  if (next === null) return 'Not Marked';
  return STATUS_TONE[next]?.label ?? next;
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

/** Returns Monday of the week containing d (local time, no UTC drift). */
export function startOfWeek(d) {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate()); // local midnight
  const dow = (out.getDay() + 6) % 7; // Mon=0
  out.setDate(out.getDate() - dow);
  return out;
}

/** Formats a Date as YYYY-MM-DD using LOCAL date (avoids UTC-offset bug). */
export function fmtIso(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Short column header, e.g. "Mon, 12 May". */
export function fmtCol(d) {
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
}

// ─── Grid component ───────────────────────────────────────────────────────────

export default function AttendanceGrid({
  employees,
  days,
  cellStatus,
  busyCell,
  onCellClick,
  loading,
  readOnly = false,
}) {
  return (
    <div className="flex flex-col gap-3">
      {/* Legend + week range */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Legend:</span>
        {LEGEND_ITEMS.map((item) => (
          <span
            key={item.key ?? 'not-marked'}
            className={'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ' + item.bg + ' ' + item.text}
          >
            {item.label}
          </span>
        ))}
        <div className="ml-auto flex items-center gap-3">
          {!readOnly && (
            <span className="text-xs text-slate-400 italic">Click a cell to cycle its status</span>
          )}
          <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
            {fmtCol(days[0])} — {fmtCol(days[6])}
          </span>
        </div>
      </div>

      {/* Grid */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th
                  className="sticky left-0 bg-slate-50 px-5 py-4 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500"
                  style={{ minWidth: 200 }}
                >
                  Employee
                </th>
                {days.map((d) => {
                  const isToday = fmtIso(d) === fmtIso(new Date());
                  return (
                    <th
                      key={fmtIso(d)}
                      className={
                        'px-2 py-3 text-center ' +
                        (isToday ? 'bg-teal-50' : '')
                      }
                      style={{ minWidth: 72 }}
                    >
                      <div className={
                        'text-[10px] font-bold uppercase tracking-wider ' +
                        (isToday ? 'text-teal-700' : 'text-slate-500')
                      }>
                        {d.toLocaleDateString('en-IN', { weekday: 'short' })}
                      </div>
                      <div className={
                        'text-[10px] font-medium ' +
                        (isToday ? 'text-teal-600' : 'text-slate-400')
                      }>
                        {d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-xs text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && employees.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-xs text-slate-400">
                    No employees in scope.
                  </td>
                </tr>
              )}
              {!loading && employees.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="sticky left-0 bg-white px-5 py-3 align-middle hover:bg-slate-50/70">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-[11px] font-bold text-white shadow-sm">
                        {(e.full_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-semibold text-slate-900">{e.full_name}</p>
                        {e.employee_code && (
                          <p className="text-[11px] text-slate-400">{e.employee_code}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  {days.map((d) => {
                    const iso     = fmtIso(d);
                    const isToday = iso === fmtIso(new Date());
                    const status  = cellStatus(e.id, iso);
                    const tone    = STATUS_TONE[status] || STATUS_TONE.unmarked;
                    const cellKey = e.id + '-' + iso;
                    const isBusy  = busyCell === cellKey;
                    const nextLbl = nextStatusLabel(status);
                    return (
                      <td
                        key={iso}
                        className={'px-2 py-3 text-center ' + (isToday ? 'bg-teal-50/40' : '')}
                      >
                        {readOnly ? (
                          <span
                            className={'inline-flex w-full justify-center rounded-lg px-2 py-1.5 text-[11px] font-semibold ' + tone.bg + ' ' + tone.text}
                          >
                            {tone.label}
                          </span>
                        ) : (
                          <button
                            onClick={() => onCellClick(e.id, iso)}
                            onKeyDown={(ev) => {
                              if (ev.key === 'Enter' || ev.key === ' ') {
                                ev.preventDefault();
                                onCellClick(e.id, iso);
                              }
                            }}
                            disabled={isBusy}
                            title={`Click → ${nextLbl}`}
                            aria-label={`${e.full_name} on ${iso}: ${tone.label}. Click to set ${nextLbl}.`}
                            className={
                              'w-full rounded-lg px-2 py-1.5 text-[11px] font-semibold transition-all select-none ' +
                              'cursor-pointer hover:scale-[1.05] hover:shadow-md active:scale-95 ' +
                              'focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400 ' +
                              tone.bg + ' ' + tone.text +
                              (isBusy ? ' opacity-50 cursor-wait' : '')
                            }
                          >
                            {isBusy
                              ? <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                              : tone.label}
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
