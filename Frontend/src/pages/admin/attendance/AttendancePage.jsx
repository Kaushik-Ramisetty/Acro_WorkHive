import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { attendanceApi, leaveApi } from '../../../services/leave';
import { employeesApi } from '../../../services/employees';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';

const STATUS_TONE = {
  present:  { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Present' },
  absent:   { bg: 'bg-rose-100',    text: 'text-rose-700',    label: 'Absent'  },
  wfh:      { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'WFH'     },
  leave:    { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'Leave'   },
  holiday:  { bg: 'bg-slate-200',   text: 'text-slate-700',   label: 'Holiday' },
  unmarked: { bg: 'bg-slate-50',    text: 'text-slate-400',   label: '—'       },
};

const STATUS_CYCLE = ['present', 'absent', 'wfh', 'leave', 'holiday', 'unmarked'];

function startOfWeek(d) {
  // Monday-start week
  const out = new Date(d);
  const day = (out.getDay() + 6) % 7; // Mon=0..Sun=6
  out.setHours(0, 0, 0, 0);
  out.setDate(out.getDate() - day);
  return out;
}

function fmtIso(d) { return d.toISOString().slice(0, 10); }
function fmtCol(d) {
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
}

export default function AttendancePage() {
  const { role } = useAuth();
  const isAdminOrManager = role === 'admin' || role === 'manager';

  const [employees, setEmployees] = useState([]);
  const [rows, setRows] = useState([]);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busyCell, setBusyCell] = useState(null); // 'EMPID-DATE'
  const [schedulerBusy, setSchedulerBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const flash = (tone, message) => { setToast({ tone, message }); setTimeout(() => setToast(null), 2500); };

  const days = useMemo(() => {
    const out = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      out.push(d);
    }
    return out;
  }, [weekStart]);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const start = fmtIso(days[0]);
      const end   = fmtIso(days[days.length - 1]);
      const [emps, atts] = await Promise.all([
        isAdminOrManager ? employeesApi.list({}) : Promise.resolve([]),
        attendanceApi.list({ start, end }),
      ]);
      if (isAdminOrManager) setEmployees(emps);
      setRows(atts);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Failed to load.');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [weekStart, isAdminOrManager]);

  // Build a lookup: { 'empId-yyyy-mm-dd': status }
  const grid = useMemo(() => {
    const m = new Map();
    for (const r of rows) m.set(r.employee_id + '-' + r.date, r.status);
    return m;
  }, [rows]);

  const visibleEmployees = isAdminOrManager
    ? employees
    : []; // employees see their own row only — handled separately below

  const cellStatus = (empId, dateIso) => grid.get(empId + '-' + dateIso) || 'unmarked';

  const cycle = async (empId, dateIso) => {
    if (!isAdminOrManager) return;
    const current = cellStatus(empId, dateIso);
    const idx = STATUS_CYCLE.indexOf(current);
    const next = STATUS_CYCLE[(idx + 1) % STATUS_CYCLE.length];
    if (next === 'unmarked') return; // can't go back to unmarked from UI
    setBusyCell(empId + '-' + dateIso);
    try {
      await attendanceApi.mark({ employee_id: empId, date: dateIso, status: next });
      // Optimistically update
      setRows((p) => {
        const clone = p.filter((r) => !(r.employee_id === empId && r.date === dateIso));
        clone.push({ employee_id: empId, date: dateIso, status: next, source: 'manual' });
        return clone;
      });
    } catch (e) {
      flash('rose', e?.data?.detail || 'Failed to mark.');
    } finally { setBusyCell(null); }
  };

  const onSchedulerRun = async () => {
    setSchedulerBusy(true);
    try {
      const res = await leaveApi.schedulerRun();
      flash('emerald', `Scheduler done — examined ${res.examined}, consumed ${res.consumed}, reversed ${res.reversed}.`);
    } catch (e) {
      flash('rose', e?.data?.detail || 'Scheduler failed.');
    } finally { setSchedulerBusy(false); }
  };

  const shiftWeek = (delta) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + 7 * delta);
    setWeekStart(d);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance"
        subtitle="Mark or correct attendance. Click any cell to cycle through statuses."
        right={
          <>
            <button onClick={() => shiftWeek(-1)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
              ← Prev Week
            </button>
            <button onClick={() => setWeekStart(startOfWeek(new Date()))}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
              This Week
            </button>
            <button onClick={() => shiftWeek(1)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
              Next Week →
            </button>
            {role === 'admin' && (
              <button onClick={onSchedulerRun} disabled={schedulerBusy}
                className="flex items-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-amber-700 disabled:opacity-60">
                <Icon name="clock" className="h-4 w-4" />
                {schedulerBusy ? 'Running…' : 'Run Scheduler'}
              </button>
            )}
          </>
        }
      />

      {toast && (
        <div className={
          'rounded-lg border px-3 py-2 text-sm shadow-sm ' +
          (toast.tone === 'emerald' ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                                    : 'border-rose-200 bg-rose-50 text-rose-800')
        }>{toast.message}</div>
      )}

      {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Legend:</span>
        {Object.entries(STATUS_TONE).filter(([k]) => k !== 'unmarked').map(([k, t]) => (
          <span key={k} className={'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ' + t.bg + ' ' + t.text}>
            {t.label}
          </span>
        ))}
        <span className="ml-auto text-xs text-slate-500">
          Week: {fmtCol(days[0])} → {fmtCol(days[6])}
        </span>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="sticky left-0 bg-slate-50 px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500" style={{ minWidth: 180 }}>
                  Employee
                </th>
                {days.map((d) => (
                  <th key={fmtIso(d)} className="px-3 py-3 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    {fmtCol(d)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {!loading && visibleEmployees.length === 0 && isAdminOrManager && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-xs text-slate-400">No employees in scope.</td></tr>
              )}
              {visibleEmployees.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50/60">
                  <td className="sticky left-0 bg-white px-4 py-2 align-middle">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-[11px] font-bold text-white">
                        {(e.full_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-slate-900">{e.full_name}</p>
                        {e.employee_code && <p className="text-[10px] text-slate-500">{e.employee_code}</p>}
                      </div>
                    </div>
                  </td>
                  {days.map((d) => {
                    const iso = fmtIso(d);
                    const status = cellStatus(e.id, iso);
                    const tone = STATUS_TONE[status] || STATUS_TONE.unmarked;
                    const cellKey = e.id + '-' + iso;
                    return (
                      <td key={iso} className="px-2 py-2 text-center">
                        <button
                          onClick={() => cycle(e.id, iso)}
                          disabled={busyCell === cellKey}
                          className={
                            'w-full rounded-md px-2 py-1 text-[11px] font-semibold transition ' +
                            tone.bg + ' ' + tone.text +
                            ' hover:opacity-80 disabled:opacity-50'
                          }
                        >
                          {tone.label}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}

              {/* Employee view — their own attendance only */}
              {!isAdminOrManager && (
                <tr>
                  <td className="sticky left-0 bg-white px-4 py-2 text-xs font-semibold text-slate-700">My attendance</td>
                  {days.map((d) => {
                    const iso = fmtIso(d);
                    // employees see their own row pre-filtered server-side
                    const r = rows.find((x) => x.date === iso);
                    const status = r ? r.status : 'unmarked';
                    const tone = STATUS_TONE[status] || STATUS_TONE.unmarked;
                    return (
                      <td key={iso} className="px-2 py-2 text-center">
                        <span className={'inline-flex w-full justify-center rounded-md px-2 py-1 text-[11px] font-semibold ' + tone.bg + ' ' + tone.text}>
                          {tone.label}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
