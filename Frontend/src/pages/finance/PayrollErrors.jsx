/**
 * Payroll Error Review page.
 *
 * Finance staff can view all flagged issues per run, filter by status/type,
 * and resolve errors with a resolution note.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const SEVERITY_META = {
  error:   { label: 'Error',   color: 'bg-rose-100 text-rose-700',   dot: 'bg-rose-500' },
  warning: { label: 'Warning', color: 'bg-amber-100 text-amber-700', dot: 'bg-amber-500' },
  info:    { label: 'Info',    color: 'bg-blue-100 text-blue-700',   dot: 'bg-blue-400' },
};

const ERROR_TYPE_LABELS = {
  salary_mismatch:     'Salary Mismatch',
  missing_attendance:  'Missing Attendance',
  leave_inconsistency: 'Leave Inconsistency',
  deduction_mismatch:  'Deduction Mismatch',
  lop_mismatch:        'LOP Mismatch',
  manual_correction:   'Manual Correction',
};

function ResolveModal({ error, onClose, onResolved }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    setBusy(true);
    setErr('');
    try {
      await financeApi.resolveError(error.id, note);
      onResolved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to resolve');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">Resolve Issue</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
          <p><span className="text-slate-500">Employee:</span> <span className="font-semibold">{error.employee_name}</span></p>
          <p><span className="text-slate-500">Type:</span> {ERROR_TYPE_LABELS[error.error_type] || error.error_type}</p>
          <p><span className="text-slate-500">Issue:</span> {error.description}</p>
        </div>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Resolution Note</label>
          <textarea
            rows={3}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            placeholder="Describe how this was resolved…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <div className="flex gap-3 justify-end pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {busy ? 'Resolving…' : 'Mark Resolved'}
          </button>
        </div>
      </div>
    </div>
  );
}

function RunPicker({ runs, selectedId, onChange }) {
  return (
    <select
      value={selectedId || ''}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
    >
      <option value="" disabled>Select run…</option>
      {runs.map((r) => <option key={r.id} value={r.id}>{r.month_label}</option>)}
    </select>
  );
}

export default function PayrollErrors() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const isFinanceOnly = ['finance', 'admin'].includes((role || '').toLowerCase());
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingErrors, setLoadingErrors] = useState(false);
  const [filter, setFilter] = useState('all'); // all | open | resolved
  const [typeFilter, setTypeFilter] = useState('all');
  const [resolveTarget, setResolveTarget] = useState(null);

  useEffect(() => {
    financeApi.listRuns()
      .then((data) => {
        setRuns(data);
        const active = data.find((r) => r.status === 'under_review' || r.status === 'processing');
        setSelectedId((active || data[0])?.id);
      })
      .finally(() => setLoading(false));
  }, []);

  const loadErrors = (id) => {
    if (!id) return;
    setLoadingErrors(true);
    financeApi.listErrors(id)
      .then(setErrors)
      .finally(() => setLoadingErrors(false));
  };

  useEffect(() => { loadErrors(selectedId); }, [selectedId]);

  const filtered = errors.filter((e) => {
    if (filter === 'open' && e.is_resolved) return false;
    if (filter === 'resolved' && !e.is_resolved) return false;
    if (typeFilter !== 'all' && e.error_type !== typeFilter) return false;
    return true;
  });

  const openCount = errors.filter((e) => !e.is_resolved).length;
  const resolvedCount = errors.filter((e) => e.is_resolved).length;

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="space-y-6">
      {resolveTarget && (
        <ResolveModal
          error={resolveTarget}
          onClose={() => setResolveTarget(null)}
          onResolved={() => loadErrors(selectedId)}
        />
      )}

      <button
        onClick={() => navigate('/employee-dashboard/finance-payroll')}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <span className="text-lg leading-none">‹</span>
        <span>Back to Dashboard</span>
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Error Review</h1>
          <p className="text-sm text-slate-500 mt-0.5">Review and resolve flagged payroll issues</p>
        </div>
        <RunPicker runs={runs} selectedId={selectedId} onChange={setSelectedId} />
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-soft text-center">
          <p className="text-2xl font-bold font-mono text-rose-600">{openCount}</p>
          <p className="text-xs text-slate-500 mt-1">Open Errors</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-soft text-center">
          <p className="text-2xl font-bold font-mono text-emerald-600">{resolvedCount}</p>
          <p className="text-xs text-slate-500 mt-1">Resolved</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-soft text-center">
          <p className="text-2xl font-bold font-mono text-slate-700">{errors.length}</p>
          <p className="text-xs text-slate-500 mt-1">Total Flags</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex rounded-lg border border-slate-200 overflow-hidden">
          {[
            { key: 'all',      label: 'All' },
            { key: 'open',     label: 'Open' },
            { key: 'resolved', label: 'Resolved' },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 text-xs font-medium transition ${
                filter === f.key ? 'bg-brand-500 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="all">All Types</option>
          {Object.entries(ERROR_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Error list */}
      {loadingErrors ? (
        <div className="flex items-center justify-center h-24">
          <div className="h-6 w-6 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">✅</p>
          <p className="text-slate-600 font-medium">
            {errors.length === 0 ? 'No issues flagged for this run' : 'No matching errors'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((e) => {
            const sev = SEVERITY_META[e.severity] || SEVERITY_META.warning;
            return (
              <div
                key={e.id}
                className={`bg-white rounded-xl border shadow-soft p-5 ${
                  e.is_resolved ? 'border-emerald-100 opacity-70' : 'border-slate-200'
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className={`mt-1 h-2.5 w-2.5 rounded-full flex-shrink-0 ${sev.dot}`} />
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-semibold text-slate-800 text-sm">{e.employee_name}</p>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${sev.color}`}>
                          {sev.label}
                        </span>
                        <span className="rounded-full bg-slate-100 text-slate-600 px-2 py-0.5 text-[10px] font-semibold">
                          {ERROR_TYPE_LABELS[e.error_type] || e.error_type}
                        </span>
                      </div>
                      <p className="text-sm text-slate-600 mt-1">{e.description}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        Flagged {new Date(e.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                      </p>
                      {e.is_resolved && e.resolution_note && (
                        <div className="mt-2 rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2 text-xs text-emerald-700">
                          <span className="font-semibold">Resolution: </span>{e.resolution_note}
                        </div>
                      )}
                    </div>
                  </div>
                  {e.is_resolved && (
                    <span className="rounded-lg bg-emerald-100 text-emerald-700 px-3 py-1.5 text-xs font-semibold flex-shrink-0">
                      ✓ Resolved
                    </span>
                  )}
                  {!e.is_resolved && isFinanceOnly && (
                    <button
                      onClick={() => setResolveTarget(e)}
                      className="rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-1.5 text-xs font-semibold hover:bg-emerald-100 transition flex-shrink-0"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
