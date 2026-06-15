import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { attendanceApi, leaveApi } from '../../../services/leave';
import { employeesApi } from '../../../services/employees';
import {
  attendance as attendanceSvc,
  regularization as regularizationSvc,
  triggerCsvDownload,
  managerApi,
} from '../../../services/attendance';
import { timesheet as tsApi } from '../../../services/timesheet';
import { api } from '../../../services/api';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';
import AttendanceGrid, {
  STATUS_TONE, LEGEND_ITEMS, CYCLE_ORDER,
  cycleNextStatus, nextStatusLabel,
  startOfWeek, fmtIso, fmtCol,
} from '../../../components/attendance/AttendanceGrid';

// ─── TabBtn ───────────────────────────────────────────────────────────────────
function TabBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={active ? {} : { color: "var(--hrms-text-2)" }}
      className={
        'px-4 py-2 text-xs font-semibold rounded-md transition-colors ' +
        (active ? 'bg-teal-500 text-white' : 'hover:bg-slate-100')
      }
    >
      {children}
    </button>
  );
}

// ─── RegularizationsTab ───────────────────────────────────────────────────────
function RegularizationsTab() {
  const [filter, setFilter] = useState('pending');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState(null);
  const [comment, setComment] = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const data = await regularizationSvc.list(filter ? { status: filter } : {});
      setRows(Array.isArray(data) ? data : []);
    } catch (e) { setErr(e?.data?.detail || e.message || 'Failed'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [filter]);

  const doReview = async (decision) => {
    if (!reviewing) return;
    setBusy(true); setErr('');
    try {
      await regularizationSvc.review(reviewing.id, { decision, comment: comment || null });
      setReviewing(null); setComment('');
      await load();
    } catch (e) { setErr(e?.data?.detail || e.message || 'Review failed'); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      {err && <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}

      {/* Filter bar */}
      <div className="flex gap-2">
        {['pending', 'approved', 'rejected', ''].map((f) => (
          <button key={f || 'all'} onClick={() => setFilter(f)}
            className={'rounded-lg px-3 py-1.5 text-xs font-semibold transition ' + (filter === f ? 'bg-teal-500 text-white' : 'border hover:bg-slate-50')}
            style={filter === f ? {} : { borderColor: "var(--hrms-border)", color: "var(--hrms-text-2)" }}
          >
            {f ? f.charAt(0).toUpperCase() + f.slice(1) : 'All'}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
        <table className="w-full text-xs">
          <thead style={{ background: "var(--hrms-surface-2)" }}>
            <tr>
              {['Employee', 'Date', 'Reason', 'Status', 'Submitted', ''].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>No requests found.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid var(--hrms-border)" }}>
                <td className="px-4 py-3 font-semibold" style={{ color: "var(--hrms-text)" }}>{r.employee_name || 'Unknown Employee'}</td>
                <td className="px-4 py-3" style={{ color: "var(--hrms-text-2)" }}>{r.date}</td>
                <td className="px-4 py-3 max-w-[200px] truncate" style={{ color: "var(--hrms-text-2)" }}>{r.reason || '—'}</td>
                <td className="px-4 py-3">
                  <span className={'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ' +
                    (r.status === 'approved' ? 'bg-emerald-100 text-emerald-700' :
                     r.status === 'rejected' ? 'bg-rose-100 text-rose-700' :
                     'bg-amber-100 text-amber-700')}>{r.status}</span>
                </td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "var(--hrms-text-faint)" }}>
                  {r.created_at ? new Date(r.created_at).toLocaleDateString('en-IN') : '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  {r.status === 'pending' && (
                    <button onClick={() => { setReviewing(r); setComment(''); }}
                      className="rounded bg-indigo-500 px-3 py-1 text-[11px] font-semibold text-white hover:bg-indigo-600">
                      Review
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {reviewing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={() => setReviewing(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[480px] rounded-xl p-5 shadow-xl" style={{ background: "var(--hrms-surface)" }}>
            <h3 className="mb-1 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Review Regularization</h3>
            <p className="mb-1 text-xs" style={{ color: "var(--hrms-text-muted)" }}>{reviewing.employee_name || 'Unknown Employee'} — {reviewing.date}</p>
            <p className="mb-3 text-xs rounded p-2" style={{ color: "var(--hrms-text-2)", background: "var(--hrms-surface-2)" }}>{reviewing.reason || 'No reason provided.'}</p>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (optional)" rows={2}
              className="mb-3 w-full rounded border px-2 py-1.5 text-xs"
              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }} />
            <div className="flex justify-end gap-2">
              <button onClick={() => setReviewing(null)} className="rounded border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--hrms-border)", color: "var(--hrms-text-2)" }}>Cancel</button>
              <button onClick={() => doReview('reject')} disabled={busy} className="rounded bg-rose-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60">Reject</button>
              <button onClick={() => doReview('approve')} disabled={busy} className="rounded bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60">Approve</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── TS_STATUS_TONE / TsPill / SubTabBtn ──────────────────────────────────────
const TS_STATUS_TONE = {
  draft:             { bg: 'bg-slate-100',   text: 'text-slate-600'   },
  pending_review:    { bg: 'bg-amber-100',   text: 'text-amber-700'   },
  approved:          { bg: 'bg-emerald-100', text: 'text-emerald-700' },
  rejected:          { bg: 'bg-rose-100',    text: 'text-rose-700'    },
  pending_client:    { bg: 'bg-sky-100',     text: 'text-sky-700'     },
  client_approved:   { bg: 'bg-teal-100',    text: 'text-teal-700'    },
  pending_RM:        { bg: 'bg-violet-100',  text: 'text-violet-700'  },
  RM_approved:       { bg: 'bg-purple-100',  text: 'text-purple-700'  },
  pending_HR:        { bg: 'bg-orange-100',  text: 'text-orange-700'  },
  HR_approved:       { bg: 'bg-green-100',   text: 'text-green-700'   },
  pending_finance:   { bg: 'bg-lime-100',    text: 'text-lime-700'    },
  finance_approved:  { bg: 'bg-cyan-100',    text: 'text-cyan-700'    },
  processing:        { bg: 'bg-blue-100',    text: 'text-blue-700'    },
  completed:         { bg: 'bg-emerald-200', text: 'text-emerald-800' },
};

function TsPill({ status }) {
  const t = TS_STATUS_TONE[status] || TS_STATUS_TONE.draft;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${t.bg} ${t.text}`}>
      {status}
    </span>
  );
}

function SubTabBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className={'px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ' + (active ? 'bg-teal-500 text-white' : 'hover:bg-slate-100')}
      style={active ? {} : { color: "var(--hrms-text-2)" }}>
      {children}
    </button>
  );
}

// ─── AdminTimesheetExportCard ─────────────────────────────────────────────────
function AdminTimesheetExportCard() {
  const today = new Date();
  const [startDate, setStartDate] = useState(fmtIso(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [endDate, setEndDate]     = useState(fmtIso(today));
  const [empId, setEmpId]         = useState('');
  const [dept, setDept]           = useState('');
  const [status, setStatus]       = useState('');
  const [employees, setEmployees] = useState([]);
  const [busy, setBusy]           = useState(false);
  const [err, setErr]             = useState('');

  useEffect(() => {
    employeesApi.list({}).then((d) => setEmployees(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  const handleExport = async () => {
    setBusy(true); setErr('');
    try {
      const params = { start_date: startDate, end_date: endDate };
      if (empId)   params.employee_id = empId;
      if (dept)    params.department  = dept;
      if (status)  params.status      = status;
      const csv = await tsApi.hrExportCsv(params);
      triggerCsvDownload(typeof csv === 'string' ? csv : '', `timesheets_${startDate}_${endDate}.csv`);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Export failed');
    } finally { setBusy(false); }
  };

  const inputCls = 'w-full rounded-lg border px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-teal-400';
  const inputStyle = { background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" };
  const labelCls = 'flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-wider';

  return (
    <div className="rounded-2xl p-5 shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
      <p className="mb-4 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Export Timesheets (CSV)</p>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 mb-4">
        <label className={labelCls} style={{ color: "var(--hrms-text-muted)" }}>
          Start Date
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={inputCls} style={inputStyle} />
        </label>
        <label className={labelCls} style={{ color: "var(--hrms-text-muted)" }}>
          End Date
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={inputCls} style={inputStyle} />
        </label>
        <label className={labelCls} style={{ color: "var(--hrms-text-muted)" }}>
          Employee
          <select value={empId} onChange={(e) => setEmpId(e.target.value)} className={inputCls} style={inputStyle}>
            <option value="">All employees</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name || `#${e.id}`}</option>)}
          </select>
        </label>
        <label className={labelCls} style={{ color: "var(--hrms-text-muted)" }}>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls} style={inputStyle}>
            <option value="">All statuses</option>
            {['draft','pending_review','approved','rejected','pending_client','client_approved',
              'pending_RM','RM_approved','pending_HR','HR_approved','pending_finance','finance_approved',
              'processing','completed'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      {err && <div className="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
      <button onClick={handleExport} disabled={busy}
        className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-600 disabled:opacity-60">
        <Icon name="download" className="h-3.5 w-3.5" />
        {busy ? 'Exporting…' : 'Download CSV'}
      </button>
    </div>
  );
}

// ─── TsOverviewTab ────────────────────────────────────────────────────────────
function TsOverviewTab() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const list = await tsApi.list({});
        const rows = Array.isArray(list) ? list : [];
        const counts = { total: rows.length, draft: 0, pending: 0, approved: 0, rejected: 0, hours: 0 };
        rows.forEach((t) => {
          const s = t.status || '';
          if (s === 'draft') counts.draft++;
          else if (s.startsWith('pending')) counts.pending++;
          else if (s === 'approved' || s.endsWith('approved') || s === 'completed') counts.approved++;
          else if (s === 'rejected') counts.rejected++;
          counts.hours += t.total_logged_hours || 0;
        });
        setStats(counts);
      } catch { setStats(null); }
      finally { setLoading(false); }
    })();
  }, []);

  const cards = stats ? [
    { label: 'Total', value: stats.total, tone: 'blue' },
    { label: 'Draft', value: stats.draft, tone: 'slate' },
    { label: 'Pending', value: stats.pending, tone: 'amber' },
    { label: 'Approved / Locked', value: stats.approved, tone: 'emerald' },
    { label: 'Rejected', value: stats.rejected, tone: 'rose' },
    { label: 'Total Hours', value: stats.hours.toFixed(1) + ' h', tone: 'teal' },
  ] : [];

  const TONES = {
    blue:    { wrap: 'border-blue-200 bg-blue-50',       val: 'text-blue-700',    lbl: 'text-blue-600' },
    slate:   { wrap: 'border-slate-200 bg-slate-50',     val: 'text-slate-700',   lbl: 'text-slate-500' },
    amber:   { wrap: 'border-amber-200 bg-amber-50',     val: 'text-amber-700',   lbl: 'text-amber-600' },
    emerald: { wrap: 'border-emerald-200 bg-emerald-50', val: 'text-emerald-700', lbl: 'text-emerald-600' },
    rose:    { wrap: 'border-rose-200 bg-rose-50',       val: 'text-rose-700',    lbl: 'text-rose-600' },
    teal:    { wrap: 'border-teal-200 bg-teal-50',       val: 'text-teal-700',    lbl: 'text-teal-600' },
  };

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {loading
        ? Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl border p-4 animate-pulse" style={{ borderColor: "var(--hrms-border)", background: "var(--hrms-surface-2)" }}>
              <div className="h-3 w-16 rounded mb-2" style={{ background: "var(--hrms-border)" }} />
              <div className="h-7 w-10 rounded" style={{ background: "var(--hrms-border)" }} />
            </div>
          ))
        : cards.map((c) => {
            const T = TONES[c.tone] || TONES.slate;
            return (
              <div key={c.label} className={`rounded-xl border p-4 flex flex-col gap-1 ${T.wrap}`}>
                <p className={`text-[10px] font-bold uppercase tracking-wider ${T.lbl}`}>{c.label}</p>
                <p className={`text-2xl font-extrabold ${T.val}`}>{c.value}</p>
              </div>
            );
          })
      }
    </div>
  );
}

// ─── TsAllTab ─────────────────────────────────────────────────────────────────
function TsAllTab() {
  const [list, setList]           = useState([]);
  const [empMap, setEmpMap]       = useState({});
  const [loading, setLoading]     = useState(true);
  const [err, setErr]             = useState('');
  const [drawer, setDrawer]       = useState(null);
  const [drawerMode, setDrawerMode] = useState('view');
  const [drawerErr, setDrawerErr] = useState('');
  const [drawerBusy, setDrawerBusy] = useState(false);
  const [editEntries, setEditEntries] = useState([]);
  const [projects, setProjects]   = useState([]);
  const [tasksCache, setTasksCache] = useState({});
  const [filterStatus, setFilterStatus] = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const [ts, emps] = await Promise.all([
        tsApi.hrList ? tsApi.hrList({}) : tsApi.list({}),
        employeesApi.list({}).catch(() => []),
      ]);
      setList(Array.isArray(ts) ? ts : []);
      const m = {};
      (Array.isArray(emps) ? emps : []).forEach((e) => { m[e.id] = e.full_name || e.name || `#${e.id}`; });
      setEmpMap(m);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openDrawer = async (id) => {
    setDrawerMode('view'); setDrawerErr('');
    try {
      const d = await tsApi.get(id);
      setDrawer(d);
    } catch (e) { setErr(e?.data?.detail || e.message); }
  };

  const enterEdit = async () => {
    if (!drawer) return;
    setDrawerMode('edit'); setDrawerErr('');
    const entries = (drawer.entries || []).map((e) => ({ ...e, _key: e.id, _delete: false, _isNew: false }));
    setEditEntries(entries);
    if (projects.length === 0) {
      try {
        const ps = await (tsApi.hrProjects ? tsApi.hrProjects() : tsApi.projects());
        setProjects(Array.isArray(ps) ? ps : []);
      } catch { /* ignore */ }
    }
    // Pre-fetch tasks for any existing entries
    const projectIds = [...new Set(entries.map((e) => e.project_id).filter(Boolean))];
    for (const pid of projectIds) {
      if (!tasksCache[pid]) {
        try {
          const ts2 = await (tsApi.hrTasks ? tsApi.hrTasks(pid) : tsApi.tasks(pid));
          setTasksCache((prev) => ({ ...prev, [pid]: Array.isArray(ts2) ? ts2 : [] }));
        } catch { /* ignore */ }
      }
    }
  };

  const updateEntry = async (key, field, value) => {
    setEditEntries((prev) => prev.map((e) => {
      if (e._key !== key) return e;
      const updated = { ...e, [field]: value };
      return updated;
    }));
    if (field === 'project_id' && value && !tasksCache[value]) {
      try {
        const ts2 = await (tsApi.hrTasks ? tsApi.hrTasks(value) : tsApi.tasks(value));
        setTasksCache((prev) => ({ ...prev, [value]: Array.isArray(ts2) ? ts2 : [] }));
      } catch { /* ignore */ }
    }
  };

  const deleteEntry = (key) => setEditEntries((prev) => prev.map((e) => e._key === key ? { ...e, _delete: !e._delete } : e));

  const addEntry = () => setEditEntries((prev) => [
    ...prev,
    { _key: `new-${Date.now()}`, _isNew: true, _delete: false, entry_date: fmtIso(new Date()), project_id: '', task_id: '', logged_hours: 8, description: '' },
  ]);

  const saveEntries = async () => {
    if (!drawer) return;
    setDrawerBusy(true); setDrawerErr('');
    try {
      const toSave = editEntries
        .filter((e) => !e._delete || !e._isNew)
        .map((e) => ({
          id: e._isNew ? undefined : e.id,
          entry_date: e.entry_date,
          project_id: e.project_id || null,
          task_id: e.task_id || null,
          logged_hours: parseFloat(e.logged_hours) || 0,
          description: e.description || '',
          _delete: e._delete && !e._isNew,
        }));
      await (tsApi.hrEditEntries ? tsApi.hrEditEntries(drawer.id, toSave) : api.put(`/timesheet/${drawer.id}/entries`, toSave));
      const updated = await tsApi.get(drawer.id);
      setDrawer(updated);
      setDrawerMode('view');
    } catch (e) {
      setDrawerErr(e?.data?.detail || e.message || 'Save failed');
    } finally { setDrawerBusy(false); }
  };

  const filtered = filterStatus ? list.filter((t) => t.status === filterStatus) : list;

  const STAGES = [
    { key: 'pending_client',   label: 'Client Review' },
    { key: 'client_approved',  label: 'Client ✓' },
    { key: 'pending_RM',       label: 'RM Review' },
    { key: 'RM_approved',      label: 'RM ✓' },
    { key: 'pending_HR',       label: 'HR Review' },
    { key: 'HR_approved',      label: 'HR ✓' },
    { key: 'pending_finance',  label: 'Finance Review' },
    { key: 'finance_approved', label: 'Finance ✓' },
    { key: 'processing',       label: 'Processing' },
    { key: 'completed',        label: 'Completed' },
  ];

  const stageIndex = (status) => STAGES.findIndex((s) => s.key === status);

  return (
    <div className="flex gap-4" style={{ minHeight: 400 }}>
      {/* List panel */}
      <div className="flex-1 min-w-0">
        <div className="mb-3 flex flex-wrap gap-2 items-center">
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-lg border px-2.5 py-1.5 text-xs"
            style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }}>
            <option value="">All statuses</option>
            {Object.keys(TS_STATUS_TONE).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="text-xs" style={{ color: "var(--hrms-text-faint)" }}>{filtered.length} timesheets</span>
        </div>
        {err && <div className="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
        <div className="overflow-hidden rounded-2xl shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
          <table className="w-full text-xs">
            <thead style={{ background: "var(--hrms-surface-2)" }}>
              <tr>
                {['Employee', 'Period', 'Hours', 'Status', ''].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>Loading…</td></tr>}
              {!loading && filtered.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>No timesheets found.</td></tr>}
              {filtered.map((t) => (
                <tr key={t.id} style={{ borderTop: "1px solid var(--hrms-border)", cursor: "pointer" }}
                  onClick={() => openDrawer(t.id)}>
                  <td className="px-4 py-3 font-semibold" style={{ color: "var(--hrms-text)" }}>{empMap[t.employee_id] || `#${t.employee_id}`}</td>
                  <td className="px-4 py-3" style={{ color: "var(--hrms-text-2)" }}>{t.period_start} – {t.period_end}</td>
                  <td className="px-4 py-3 font-semibold" style={{ color: "var(--hrms-text)" }}>{(t.total_logged_hours || 0).toFixed(2)} h</td>
                  <td className="px-4 py-3"><TsPill status={t.status} /></td>
                  <td className="px-4 py-3 text-right">
                    <button className="rounded bg-indigo-500 px-3 py-1 text-[11px] font-semibold text-white hover:bg-indigo-600"
                      onClick={(e) => { e.stopPropagation(); openDrawer(t.id); }}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Drawer */}
      {drawer && (
        <div className="flex-shrink-0 flex flex-col rounded-2xl shadow-lg overflow-hidden" style={{ width: 520, border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
          {/* Drawer header */}
          <div className="flex items-center justify-between px-5 py-3 flex-shrink-0" style={{ borderBottom: "1px solid var(--hrms-border)", background: "var(--hrms-surface-2)" }}>
            <div>
              <p className="text-sm font-bold" style={{ color: "var(--hrms-text)" }}>{drawer.id}</p>
              <p className="text-xs" style={{ color: "var(--hrms-text-muted)" }}>
                {empMap[drawer.employee_id] || `#${drawer.employee_id}`} · {drawer.period_start} → {drawer.period_end} · <strong>{(drawer.total_logged_hours || 0).toFixed(2)} h</strong>
              </p>
            </div>
            <div className="flex items-center gap-2">
              {drawerMode === 'view' && (
                <button onClick={enterEdit} className="rounded border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100">Edit</button>
              )}
              <button onClick={() => { setDrawer(null); setDrawerMode('view'); }} className="rounded p-1 text-lg leading-none" style={{ color: "var(--hrms-text-faint)" }}>×</button>
            </div>
          </div>

          {drawerErr && <div className="mx-4 mt-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{drawerErr}</div>}

          {/* Drawer body */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {/* Status + Timeline */}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <TsPill status={drawer.status} />
              </div>
              {/* Approval timeline */}
              <div className="flex items-center gap-0 flex-wrap">
                {STAGES.map((s, i) => {
                  const si = stageIndex(drawer.status);
                  const done = i < si;
                  const active = i === si;
                  return (
                    <div key={s.key} className="flex items-center">
                      <div className={`px-2 py-0.5 rounded text-[10px] font-bold ${done ? 'bg-emerald-100 text-emerald-700' : active ? 'bg-indigo-100 text-indigo-700' : 'text-slate-400'}`}
                        style={!done && !active ? { color: "var(--hrms-text-faint)" } : {}}>
                        {s.label}
                      </div>
                      {i < STAGES.length - 1 && <span className="text-[10px] mx-0.5" style={{ color: "var(--hrms-border)" }}>›</span>}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Entries */}
            {drawerMode === 'view' ? (
              <div className="overflow-hidden rounded-lg" style={{ border: "1px solid var(--hrms-border)" }}>
                <table className="w-full text-xs">
                  <thead style={{ background: "var(--hrms-surface-2)" }}>
                    <tr>
                      {['Date', 'Project', 'Task', 'Hours'].map((h) => (
                        <th key={h} className="px-2 py-2 text-left font-bold" style={{ color: "var(--hrms-text-faint)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(drawer.entries || []).map((e) => (
                      <tr key={e.id} style={{ borderTop: "1px solid var(--hrms-border)" }}>
                        <td className="px-2 py-1.5" style={{ color: "var(--hrms-text)" }}>{e.entry_date}</td>
                        <td className="px-2 py-1.5" style={{ color: "var(--hrms-text-2)" }}>{e.project_id || '—'}</td>
                        <td className="px-2 py-1.5" style={{ color: "var(--hrms-text-2)" }}>{e.task_id || '—'}</td>
                        <td className="px-2 py-1.5 font-semibold text-right" style={{ color: "var(--hrms-text)" }}>{(e.logged_hours || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                    {(!drawer.entries || drawer.entries.length === 0) && (
                      <tr><td colSpan={4} className="px-3 py-3 text-center" style={{ color: "var(--hrms-text-faint)" }}>No entries.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="overflow-hidden rounded-lg" style={{ border: "1px solid var(--hrms-border)" }}>
                  <table className="w-full text-xs">
                    <thead style={{ background: "var(--hrms-surface-2)" }}>
                      <tr>
                        {['Date', 'Project', 'Task', 'Hours', 'Desc', ''].map((h) => (
                          <th key={h} className="px-2 py-2 text-left font-bold" style={{ color: "var(--hrms-text-faint)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {editEntries.map((e) => (
                        <tr key={e._key} style={{ borderTop: "1px solid var(--hrms-border)", opacity: e._delete ? 0.5 : 1 }}>
                          <td className="px-2 py-1.5" style={{ minWidth: 100 }}>
                            {e._isNew
                              ? <input type="date" value={e.entry_date} onChange={(ev) => updateEntry(e._key, 'entry_date', ev.target.value)}
                                  className="w-full rounded border px-1.5 py-1 text-xs"
                                  style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }} />
                              : <span style={e._delete ? { textDecoration: 'line-through', color: "var(--hrms-text-faint)" } : { color: "var(--hrms-text)" }}>{e.entry_date}</span>
                            }
                          </td>
                          <td className="px-2 py-1.5" style={{ minWidth: 130 }}>
                            <select value={e.project_id} disabled={e._delete} onChange={(ev) => updateEntry(e._key, 'project_id', ev.target.value)}
                              className="w-full rounded border px-1.5 py-1 text-xs disabled:opacity-50"
                              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }}>
                              <option value="">— select —</option>
                              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                          </td>
                          <td className="px-2 py-1.5" style={{ minWidth: 110 }}>
                            <select value={e.task_id || ''} disabled={e._delete || !e.project_id} onChange={(ev) => updateEntry(e._key, 'task_id', ev.target.value)}
                              className="w-full rounded border px-1.5 py-1 text-xs disabled:opacity-50"
                              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }}>
                              <option value="">— none —</option>
                              {(tasksCache[e.project_id] || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                            </select>
                          </td>
                          <td className="px-2 py-1.5" style={{ width: 64 }}>
                            <input type="number" min="0" step="0.5" value={e.logged_hours} disabled={e._delete}
                              onChange={(ev) => updateEntry(e._key, 'logged_hours', ev.target.value)}
                              className="w-full rounded border px-1.5 py-1 text-xs disabled:opacity-50"
                              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }} />
                          </td>
                          <td className="px-2 py-1.5">
                            <input type="text" value={e.description} placeholder="optional" disabled={e._delete}
                              onChange={(ev) => updateEntry(e._key, 'description', ev.target.value)}
                              className="w-full rounded border px-1.5 py-1 text-xs disabled:opacity-50"
                              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }} />
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <button onClick={() => deleteEntry(e._key)} title={e._delete ? 'Undo' : 'Delete'}
                              className={'text-sm font-bold leading-none ' + (e._delete ? 'text-emerald-600 hover:text-emerald-700' : 'text-rose-500 hover:text-rose-700')}>
                              {e._delete ? '↩' : '×'}
                            </button>
                          </td>
                        </tr>
                      ))}
                      {editEntries.length === 0 && (
                        <tr><td colSpan={6} className="px-3 py-3 text-center" style={{ color: "var(--hrms-text-faint)" }}>No entries — add one below.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <button onClick={addEntry} className="rounded border border-dashed border-teal-400 px-4 py-1.5 text-xs font-semibold text-teal-600 hover:bg-teal-50">
                  + Add Entry
                </button>
              </div>
            )}
          </div>

          {/* Drawer footer (edit mode only) */}
          {drawerMode === 'edit' && (
            <div className="flex justify-end gap-2 px-5 py-3 flex-shrink-0" style={{ borderTop: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
              <button onClick={() => { setDrawerMode('view'); setDrawerErr(''); }} disabled={drawerBusy}
                className="rounded border px-4 py-1.5 text-xs font-semibold disabled:opacity-60"
                style={{ borderColor: "var(--hrms-border)", color: "var(--hrms-text-2)", background: "var(--hrms-surface)" }}>
                Cancel
              </button>
              <button onClick={saveEntries} disabled={drawerBusy}
                className="flex items-center gap-1.5 rounded bg-indigo-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-60">
                {drawerBusy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                {drawerBusy ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── TsMismatchesTab ──────────────────────────────────────────────────────────
function TsMismatchesTab() {
  const [rows, setRows]       = useState([]);
  const [empMap, setEmpMap]   = useState({});
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState('');
  const [resolving, setResolving] = useState(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy]       = useState(false);

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const [ts, emps] = await Promise.all([tsApi.list({}), employeesApi.list({}).catch(() => [])]);
      const mismatched = (Array.isArray(ts) ? ts : []).filter((t) => t.has_mismatch);
      setRows(mismatched);
      const m = {};
      (Array.isArray(emps) ? emps : []).forEach((e) => { m[e.id] = e.full_name || e.name || `#${e.id}`; });
      setEmpMap(m);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const resolve = async () => {
    if (!resolving) return;
    setBusy(true); setErr('');
    try {
      await api.patch(`/timesheet/${resolving.id}/review`, { decision: 'approve', review_comment: comment || null });
      setResolving(null); setComment('');
      await load();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Resolve failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      {err && <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
      <p className="text-xs" style={{ color: "var(--hrms-text-muted)" }}>{rows.length} timesheet{rows.length !== 1 ? 's' : ''} with mismatches</p>
      <div className="overflow-hidden rounded-2xl shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
        <table className="w-full text-xs">
          <thead style={{ background: "var(--hrms-surface-2)" }}>
            <tr>{['Employee', 'Period', 'Hours', 'Status', ''].map((h) => (
              <th key={h} className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--hrms-text-faint)" }}>No mismatches found.</td></tr>}
            {rows.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid var(--hrms-border)" }}>
                <td className="px-4 py-3 font-semibold text-rose-700">{empMap[t.employee_id] || `#${t.employee_id}`}</td>
                <td className="px-4 py-3" style={{ color: "var(--hrms-text-2)" }}>{t.period_start} – {t.period_end}</td>
                <td className="px-4 py-3 font-semibold" style={{ color: "var(--hrms-text)" }}>{(t.total_logged_hours || 0).toFixed(2)} h</td>
                <td className="px-4 py-3"><TsPill status={t.status} /></td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => { setResolving(t); setComment(''); }}
                    className="rounded bg-rose-500 px-3 py-1 text-[11px] font-semibold text-white hover:bg-rose-600">
                    Resolve
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {resolving && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={() => setResolving(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[480px] rounded-xl p-5 shadow-xl" style={{ background: "var(--hrms-surface)" }}>
            <h3 className="mb-2 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Resolve Mismatch — {empMap[resolving.employee_id] || `#${resolving.employee_id}`}</h3>
            <p className="mb-3 text-xs" style={{ color: "var(--hrms-text-muted)" }}>{resolving.period_start} → {resolving.period_end} · {(resolving.total_logged_hours || 0).toFixed(2)} h</p>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Resolution comment (optional)" rows={3}
              className="mb-3 w-full rounded border px-2 py-1.5 text-xs"
              style={{ background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" }} />
            <div className="flex justify-end gap-2">
              <button onClick={() => setResolving(null)} className="rounded border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--hrms-border)", color: "var(--hrms-text-2)" }}>Cancel</button>
              <button onClick={resolve} disabled={busy} className="rounded bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60">Mark Resolved</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── AdminTimesheetsTab ───────────────────────────────────────────────────────
function AdminTimesheetsTab() {
  const [sub, setSub] = useState('overview');
  return (
    <div className="space-y-4">
      <div className="inline-flex items-center gap-1 rounded-lg p-1" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
        <SubTabBtn active={sub === 'overview'}   onClick={() => setSub('overview')}>Overview</SubTabBtn>
        <SubTabBtn active={sub === 'all'}        onClick={() => setSub('all')}>All Timesheets</SubTabBtn>
        <SubTabBtn active={sub === 'mismatches'} onClick={() => setSub('mismatches')}>Mismatches</SubTabBtn>
        <SubTabBtn active={sub === 'export'}     onClick={() => setSub('export')}>Export</SubTabBtn>
      </div>
      {sub === 'overview'   && <TsOverviewTab />}
      {sub === 'all'        && <TsAllTab />}
      {sub === 'mismatches' && <TsMismatchesTab />}
      {sub === 'export'     && <AdminTimesheetExportCard />}
    </div>
  );
}

// ─── Analytics helpers ────────────────────────────────────────────────────────
const ATT_ABB = {
  present:  { label: 'P',   cls: 'text-emerald-600 font-bold' },
  late:     { label: 'L',   cls: 'text-amber-600   font-bold' },
  absent:   { label: 'A',   cls: 'text-rose-500    font-bold' },
  wfh:      { label: 'WFH', cls: 'text-teal-600    font-bold' },
  on_leave: { label: 'OL',  cls: 'text-blue-600    font-bold' },
  leave:    { label: 'OL',  cls: 'text-blue-600    font-bold' },
  half_day: { label: 'HD',  cls: 'text-amber-600   font-bold' },
  halfday:  { label: 'HD',  cls: 'text-amber-600   font-bold' },
  holiday:  { label: 'H',   cls: 'text-purple-600  font-bold' },
};
const attAbb = (s) => ATT_ABB[(s || '').toLowerCase()] || { label: '—', cls: 'text-slate-400' };

function AttStat({ label, value, sub, tone = 'emerald' }) {
  const T = {
    emerald: { wrap: 'border-emerald-200 bg-emerald-50', val: 'text-emerald-700', sub: 'text-emerald-600' },
    blue:    { wrap: 'border-blue-200    bg-blue-50',    val: 'text-blue-700',    sub: 'text-blue-600'    },
    teal:    { wrap: 'border-teal-200    bg-teal-50',    val: 'text-teal-700',    sub: 'text-teal-600'    },
    rose:    { wrap: 'border-rose-200    bg-rose-50',    val: 'text-rose-700',    sub: 'text-rose-600'    },
    amber:   { wrap: 'border-amber-200   bg-amber-50',   val: 'text-amber-700',   sub: 'text-amber-600'   },
  }[tone] || { wrap: 'border-slate-200 bg-slate-50', val: 'text-slate-700', sub: 'text-slate-500' };
  return (
    <div className={`rounded-xl border ${T.wrap} p-4 flex flex-col gap-1`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`text-3xl font-extrabold ${T.val}`}>{value}</p>
      {sub && <p className={`text-xs ${T.sub}`}>{sub}</p>}
    </div>
  );
}

const LEGEND_ROWS = [
  { condition: 'Full day present', abbr: 'P',      bg: 'bg-emerald-100', text: 'text-emerald-700' },
  { condition: 'Half day',         abbr: 'HD',     bg: 'bg-amber-100',   text: 'text-amber-700'   },
  { condition: 'Leave approved',   abbr: 'L',      bg: 'bg-blue-100',    text: 'text-blue-700'    },
  { condition: 'WFH approved',     abbr: 'WFH',    bg: 'bg-teal-100',    text: 'text-teal-700'    },
  { condition: 'Late arrival',     abbr: 'Late',   bg: 'bg-amber-100',   text: 'text-amber-700'   },
  { condition: 'Holiday',          abbr: 'H',      bg: 'bg-purple-100',  text: 'text-purple-700'  },
  { condition: 'No punch',         abbr: 'Absent', bg: 'bg-rose-100',    text: 'text-rose-700'    },
];

function AttendanceStatusLegend() {
  return (
    <div className="rounded-2xl p-4 shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
      <p className="mb-3 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Attendance Status Logic</p>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--hrms-border)" }}>
            <th className="pb-2 text-left text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>Condition</th>
            <th className="pb-2 text-right text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {LEGEND_ROWS.map((row) => (
            <tr key={row.abbr} style={{ borderTop: "1px solid var(--hrms-border)" }}>
              <td className="py-1.5" style={{ color: "var(--hrms-text-2)" }}>{row.condition}</td>
              <td className="py-1.5 text-right">
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${row.bg} ${row.text}`}>{row.abbr}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── AdminExportModal ─────────────────────────────────────────────────────────
function AdminExportModal({ onClose, weekStart, weekEnd }) {
  const [mode, setMode]             = useState('weekly');
  const [startDate, setStartDate]   = useState(weekStart || fmtIso(new Date()));
  const [endDate, setEndDate]       = useState(weekEnd   || fmtIso(new Date()));
  const today = new Date();
  const [monthVal, setMonthVal]     = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`);
  const [statusFilter, setStatusFilter] = useState('');
  const [busy, setBusy]             = useState(false);
  const [err, setErr]               = useState(null);

  const handleDownload = async () => {
    setBusy(true); setErr(null);
    try {
      let csvText, filename;
      if (mode === 'weekly') {
        const params = { start_date: startDate, end_date: endDate };
        if (statusFilter) params.attendance_status = statusFilter;
        csvText  = await managerApi.exportWeekly(params);
        filename = `attendance_${startDate}_${endDate}.csv`;
      } else {
        const [yr, mo] = monthVal.split('-');
        const params = { year: yr, month: mo };
        if (statusFilter) params.attendance_status = statusFilter;
        csvText  = await managerApi.exportMonthly(params);
        filename = `attendance_${yr}_${mo}.csv`;
      }
      triggerCsvDownload(typeof csvText === 'string' ? csvText : '', filename);
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e?.message || 'Export failed — please retry.');
    } finally { setBusy(false); }
  };

  const inputCls = 'rounded-lg border px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-teal-400';
  const inputStyle = { background: "var(--hrms-surface)", color: "var(--hrms-text)", borderColor: "var(--hrms-border)" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-[400px] max-w-[calc(100vw-2rem)] rounded-2xl p-7 shadow-2xl" onClick={(e) => e.stopPropagation()}
        style={{ background: "var(--hrms-surface)" }}>
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-bold" style={{ color: "var(--hrms-text)" }}>Export Attendance Data</h3>
          <button onClick={onClose} className="rounded p-1" style={{ color: "var(--hrms-text-faint)" }}>
            <Icon name="x" className="h-5 w-5" />
          </button>
        </div>
        {/* Mode */}
        <div className="mb-4 flex flex-col gap-2.5">
          {[['weekly', 'Weekly Attendance Data'], ['monthly', 'Monthly Attendance Data']].map(([val, lbl]) => (
            <label key={val} className="flex cursor-pointer items-center gap-2.5 text-sm" style={{ color: "var(--hrms-text-2)" }}>
              <input type="radio" name="adm-export-mode" value={val} checked={mode === val} onChange={() => setMode(val)} className="accent-teal-500" />
              {lbl}
            </label>
          ))}
        </div>
        {/* Date fields */}
        {mode === 'weekly' ? (
          <div className="mb-3 grid grid-cols-2 gap-3">
            {[['Start Date', startDate, setStartDate], ['End Date', endDate, setEndDate]].map(([lbl, val, set]) => (
              <label key={lbl} className="flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--hrms-text-muted)" }}>
                {lbl}
                <input type="date" value={val} onChange={(e) => set(e.target.value)} className={inputCls} style={inputStyle} />
              </label>
            ))}
          </div>
        ) : (
          <label className="mb-3 flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--hrms-text-muted)" }}>
            Month
            <input type="month" value={monthVal} onChange={(e) => setMonthVal(e.target.value)} className={inputCls} style={inputStyle} />
          </label>
        )}
        {/* Status filter */}
        <label className="mb-5 flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--hrms-text-muted)" }}>
          Status <span className="font-normal normal-case" style={{ color: "var(--hrms-text-faint)" }}>(optional)</span>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={inputCls} style={inputStyle}>
            <option value="">All statuses</option>
            <option value="present">Present</option>
            <option value="late">Late</option>
            <option value="absent">Absent</option>
            <option value="on_leave">On Leave</option>
            <option value="wfh">WFH</option>
            <option value="half_day">Half Day</option>
          </select>
        </label>
        {err && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border px-4 py-2 text-xs font-semibold"
            style={{ borderColor: "var(--hrms-border)", color: "var(--hrms-text-2)" }}>
            Cancel
          </button>
          <button onClick={handleDownload} disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-600 disabled:opacity-60">
            <Icon name="download" className="h-3.5 w-3.5" />
            {busy ? 'Downloading…' : 'Download CSV'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── AttendancePage (main export) ─────────────────────────────────────────────
export default function AttendancePage({ defaultTab = 'attendance' }) {
  const { role, user } = useAuth();
  const isAdminOrManager = role === 'admin' || role === 'manager';

  const [activeTab, setActiveTab]         = useState(defaultTab);
  const [employees, setEmployees]         = useState([]);
  const [rows, setRows]                   = useState([]);
  const [weekStart, setWeekStart]         = useState(() => startOfWeek(new Date()));
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState(null);
  const [busyCell, setBusyCell]           = useState(null);
  const [schedulerBusy, setSchedulerBusy] = useState(false);
  const [toast, setToast]                 = useState(null);
  const [isEditing, setIsEditing]         = useState(role === 'manager');
  const [exportModalOpen, setExportModalOpen] = useState(false);

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

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const start = fmtIso(days[0]);
      const end   = fmtIso(days[days.length - 1]);
      const [emps, atts] = await Promise.all([
        isAdminOrManager ? employeesApi.list({}) : Promise.resolve([]),
        attendanceSvc.records({ start, end }),
      ]);
      if (isAdminOrManager) {
        const all = Array.isArray(emps) ? emps : [];
        setEmployees(
          role === 'manager'
            ? all.filter((e) => e.reporting_manager_id === user?.id && (e.employment_status || '').toLowerCase() === 'active')
            : all,
        );
      }
      setRows(atts);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Failed to load.');
    } finally { setLoading(false); }
  }, [days, isAdminOrManager]);

  useEffect(() => {
    load();
    if (activeTab !== 'attendance') return;
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load, activeTab]);

  const grid = useMemo(() => {
    const m = new Map();
    for (const r of rows) m.set(r.employee_id + '-' + r.date, r.status);
    return m;
  }, [rows]);

  const visibleEmployees = isAdminOrManager ? employees : [];
  const cellStatus = (empId, dateIso) => grid.get(empId + '-' + dateIso) || 'unmarked';

  const todayIso = useMemo(() => fmtIso(new Date()), []);

  const todayStats = useMemo(() => {
    const counts = { present: 0, on_leave: 0, wfh: 0, absent: 0, late: 0, half_day: 0 };
    rows.filter((r) => r.date === todayIso).forEach((r) => {
      const s = (r.status || '').toLowerCase();
      if (s === 'present') counts.present++;
      else if (s === 'late') { counts.present++; counts.late++; }
      else if (s === 'on_leave' || s === 'leave') counts.on_leave++;
      else if (s === 'wfh') counts.wfh++;
      else if (s === 'absent') counts.absent++;
      else if (s === 'half_day' || s === 'halfday') counts.half_day++;
    });
    return { ...counts, total: visibleEmployees.length };
  }, [rows, visibleEmployees, todayIso]);

  const weekLogData = useMemo(() => visibleEmployees.map((emp) => {
    const dayStatuses = days.map((d) => {
      const iso = fmtIso(d);
      const rec = rows.find((r) => r.employee_id === emp.id && r.date === iso);
      return { date: iso, status: rec?.status || null };
    });
    const presentDays = dayStatuses.filter((d) => {
      const s = (d.status || '').toLowerCase();
      return s === 'present' || s === 'late' || s === 'wfh';
    }).length;
    return {
      employee_id: emp.id,
      name: emp.full_name || `#${emp.id}`,
      employee_code: emp.employee_code,
      days: dayStatuses,
      present_days: presentDays,
    };
  }), [visibleEmployees, rows, days]);

  const weeklyTrend = useMemo(() => days.map((d) => {
    const iso = fmtIso(d);
    const present = rows.filter((r) => r.date === iso && ['present', 'late', 'wfh'].includes((r.status || '').toLowerCase())).length;
    return { date: iso, present };
  }), [rows, days]);

  const todayCheckins = useMemo(() => {
    return rows
      .filter((r) => r.date === todayIso && r.check_in_time)
      .map((r) => {
        const emp = visibleEmployees.find((e) => e.id === r.employee_id);
        return {
          employee_id: r.employee_id,
          name: emp?.full_name || `#${r.employee_id}`,
          check_in_time: String(r.check_in_time || '').slice(0, 5),
          status: r.status,
        };
      })
      .sort((a, b) => (a.check_in_time || '').localeCompare(b.check_in_time || ''));
  }, [rows, visibleEmployees, todayIso]);

  const trendMax = useMemo(() => Math.max(...weeklyTrend.map((d) => d.present), 1), [weeklyTrend]);

  const handleCellClick = async (empId, dateIso) => {
    if (!isAdminOrManager) return;
    const current = cellStatus(empId, dateIso);
    const next    = cycleNextStatus(current);
    const cellKey = empId + '-' + dateIso;
    setRows((prev) => {
      const clone = prev.filter((r) => !(r.employee_id === empId && r.date === dateIso));
      if (next !== null) clone.push({ employee_id: empId, date: dateIso, status: next });
      return clone;
    });
    setBusyCell(cellKey);
    try {
      await attendanceSvc.adminOverride({ employee_id: empId, date: dateIso, status: next });
    } catch {
      setRows((prev) => {
        const clone = prev.filter((r) => !(r.employee_id === empId && r.date === dateIso));
        if (current !== 'unmarked') clone.push({ employee_id: empId, date: dateIso, status: current });
        return clone;
      });
      flash('rose', 'Failed to save — please retry');
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
        subtitle={
          activeTab === 'attendance' && isEditing
            ? 'Click any cell to cycle its status. Changes save immediately and auto-refresh every 60 s.'
            : 'Attendance overview — company-wide, current week. Click Edit Attendance to make changes.'
        }
        right={
          activeTab === 'attendance' ? (
            <>
              <button onClick={() => shiftWeek(-1)} className="rounded-lg border px-3 py-2 text-xs font-semibold hover:bg-slate-50"
                style={{ borderColor: "var(--hrms-border)", background: "var(--hrms-surface)", color: "var(--hrms-text-2)" }}>← Prev Week</button>
              <button onClick={() => setWeekStart(startOfWeek(new Date()))} className="rounded-lg border px-3 py-2 text-xs font-semibold hover:bg-slate-50"
                style={{ borderColor: "var(--hrms-border)", background: "var(--hrms-surface)", color: "var(--hrms-text-2)" }}>This Week</button>
              <button onClick={() => shiftWeek(1)} className="rounded-lg border px-3 py-2 text-xs font-semibold hover:bg-slate-50"
                style={{ borderColor: "var(--hrms-border)", background: "var(--hrms-surface)", color: "var(--hrms-text-2)" }}>Next Week →</button>
              {role === 'admin' && (
                <button onClick={onSchedulerRun} disabled={schedulerBusy}
                  className="flex items-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-amber-700 disabled:opacity-60">
                  <Icon name="clock" className="h-4 w-4" />
                  {schedulerBusy ? 'Running…' : 'Run Scheduler'}
                </button>
              )}
            </>
          ) : null
        }
      />

      {toast && (
        <div className={
          'rounded-lg border px-3 py-2 text-sm shadow-sm ' +
          (toast.tone === 'emerald' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-800')
        }>{toast.message}</div>
      )}

      {/* Edit mode banner */}
      {activeTab === 'attendance' && isEditing && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm">
          <Icon name="edit" className="h-4 w-4 flex-shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-bold text-amber-800">Editing Attendance Records</p>
            <p className="text-xs text-amber-600">Changes save immediately. Click Done Editing when finished.</p>
          </div>
          <button onClick={() => setIsEditing(false)}
            className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-bold text-amber-700 hover:bg-amber-50">
            Done Editing
          </button>
        </div>
      )}

      {/* Tab bar */}
      <div className="inline-flex items-center gap-1 rounded-lg p-1" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
        <TabBtn active={activeTab === 'attendance'}      onClick={() => setActiveTab('attendance')}>Attendance</TabBtn>
        <TabBtn active={activeTab === 'regularizations'} onClick={() => setActiveTab('regularizations')}>Regularizations</TabBtn>
        <TabBtn active={activeTab === 'timesheets'}      onClick={() => setActiveTab('timesheets')}>Timesheets</TabBtn>
      </div>

      {/* Attendance tab */}
      {activeTab === 'attendance' && (
        <>
          {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

          {!isEditing ? (
            <div className="space-y-5">
              {/* Stat cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <AttStat label="Present Today" value={loading ? '…' : todayStats.present}
                  sub={loading ? '' : `${Math.round((todayStats.present / Math.max(visibleEmployees.length, 1)) * 100)}% of ${visibleEmployees.length}`}
                  tone="emerald" />
                <AttStat label="On Leave"  value={loading ? '…' : todayStats.on_leave} sub="Approved leaves" tone="blue" />
                <AttStat label="WFH"       value={loading ? '…' : todayStats.wfh}      sub="Remote today"   tone="teal" />
                <AttStat label="Absent"    value={loading ? '…' : todayStats.absent}   sub="Unplanned"      tone="rose" />
              </div>

              <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
                {/* Attendance Log */}
                <div className="overflow-hidden rounded-2xl shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
                  <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3" style={{ borderBottom: "1px solid var(--hrms-border)" }}>
                    <div>
                      <p className="text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Attendance Log — This Week</p>
                      <p className="text-[11px]" style={{ color: "var(--hrms-text-faint)" }}>
                        {loading ? 'Loading…' : `${visibleEmployees.length} employee${visibleEmployees.length !== 1 ? 's' : ''}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setExportModalOpen(true)}
                        className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 transition hover:bg-emerald-100">
                        <Icon name="download" className="h-3.5 w-3.5" />
                        Export CSV
                      </button>
                      {isAdminOrManager && (
                        <button onClick={() => setIsEditing(true)}
                          className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition hover:bg-teal-600">
                          <Icon name="edit" className="h-3.5 w-3.5" />
                          Edit Attendance
                        </button>
                      )}
                    </div>
                  </div>
                  {loading ? (
                    <div className="px-5 py-12 text-center text-xs" style={{ color: "var(--hrms-text-faint)" }}>Loading…</div>
                  ) : weekLogData.length === 0 ? (
                    <div className="px-5 py-12 text-center text-xs" style={{ color: "var(--hrms-text-faint)" }}>No attendance data for this week.</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead style={{ background: "var(--hrms-surface-2)" }}>
                          <tr>
                            <th className="sticky left-0 px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider" style={{ minWidth: 180, background: "var(--hrms-surface-2)", color: "var(--hrms-text-faint)" }}>Employee</th>
                            {days.map((d) => (
                              <th key={fmtIso(d)} className="px-2 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>{fmtCol(d)}</th>
                            ))}
                            <th className="px-3 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--hrms-text-faint)" }}>Days In</th>
                          </tr>
                        </thead>
                        <tbody>
                          {weekLogData.map((emp) => (
                            <tr key={emp.employee_id} style={{ borderTop: "1px solid var(--hrms-border)" }}>
                              <td className="sticky left-0 px-4 py-2.5" style={{ background: "var(--hrms-surface)" }}>
                                <div className="flex items-center gap-2.5">
                                  <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-[10px] font-bold text-white">
                                    {emp.name.split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                                  </div>
                                  <div className="min-w-0">
                                    <p className="truncate text-xs font-semibold" style={{ color: "var(--hrms-text)" }}>{emp.name}</p>
                                    {emp.employee_code && <p className="text-[10px]" style={{ color: "var(--hrms-text-faint)" }}>{emp.employee_code}</p>}
                                  </div>
                                </div>
                              </td>
                              {emp.days.map((ds) => {
                                const a = attAbb(ds.status);
                                return (
                                  <td key={ds.date} className="px-2 py-2.5 text-center">
                                    <span className={`text-[11px] ${a.cls}`}>{a.label}</span>
                                  </td>
                                );
                              })}
                              <td className="px-3 py-2.5 text-center text-[11px] font-bold" style={{ color: "var(--hrms-text-2)" }}>{emp.present_days}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Right panel */}
                <div className="flex flex-col gap-4">
                  {/* Weekly Summary */}
                  <div className="rounded-2xl p-4 shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
                    <p className="mb-3 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Weekly Summary</p>
                    {loading ? (
                      <p className="text-xs" style={{ color: "var(--hrms-text-faint)" }}>Loading…</p>
                    ) : (
                      weeklyTrend.map((d) => {
                        const [y, m, day] = d.date.split('-').map(Number);
                        const label = new Date(y, m - 1, day).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
                        const pct = Math.round((d.present / trendMax) * 100);
                        return (
                          <div key={d.date} className="mb-2 flex items-center gap-2">
                            <span className="w-12 flex-shrink-0 text-[11px]" style={{ color: "var(--hrms-text-faint)" }}>{label}</span>
                            <div className="flex-1 h-1.5 rounded-full" style={{ background: "var(--hrms-border)" }}>
                              <div className="h-1.5 rounded-full bg-teal-500 transition-all" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="w-5 text-right text-[11px] font-bold" style={{ color: "var(--hrms-text-2)" }}>{d.present}</span>
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Today's Check-ins */}
                  <div className="rounded-2xl p-4 shadow-sm" style={{ border: "1px solid var(--hrms-border)", background: "var(--hrms-surface)" }}>
                    <p className="mb-3 text-sm font-bold" style={{ color: "var(--hrms-text)" }}>Today's Check-ins</p>
                    {loading ? (
                      <p className="text-xs" style={{ color: "var(--hrms-text-faint)" }}>Loading…</p>
                    ) : todayCheckins.length === 0 ? (
                      <p className="text-xs" style={{ color: "var(--hrms-text-faint)" }}>No check-ins recorded yet today.</p>
                    ) : (
                      todayCheckins.slice(0, 7).map((c) => (
                        <div key={c.employee_id} className="mb-2.5 flex items-center gap-2">
                          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-emerald-500 text-[10px] font-bold text-white">
                            {c.name.split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="truncate text-xs font-semibold" style={{ color: "var(--hrms-text)" }}>{c.name}</p>
                            <p className="text-[10px]" style={{ color: "var(--hrms-text-faint)" }}>{c.check_in_time || '—'}</p>
                          </div>
                          <span className={
                            'inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ' +
                            (c.status === 'late' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700')
                          }>{c.status === 'late' ? 'Late' : 'In'}</span>
                        </div>
                      ))
                    )}
                  </div>

                  <AttendanceStatusLegend />
                </div>
              </div>
            </div>
          ) : (
            /* Edit mode: full interactive grid */
            <AttendanceGrid
              employees={visibleEmployees}
              days={days}
              cellStatus={cellStatus}
              busyCell={busyCell}
              onCellClick={handleCellClick}
              loading={loading}
            />
          )}
        </>
      )}

      {/* Export modal */}
      {exportModalOpen && (
        <AdminExportModal
          onClose={() => setExportModalOpen(false)}
          weekStart={fmtIso(days[0])}
          weekEnd={fmtIso(days[6])}
        />
      )}

      {activeTab === 'regularizations' && <RegularizationsTab />}
      {activeTab === 'timesheets'      && <AdminTimesheetsTab />}
    </div>
  );
}
