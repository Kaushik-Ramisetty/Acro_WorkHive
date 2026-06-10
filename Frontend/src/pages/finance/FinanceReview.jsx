/**
 * Finance Review Page
 *
 * Finance review workflow:
 *   Under Review → finance examines each employee row
 *   → Flag issues (creates PayrollError)
 *   → If clean: Approve  (advance to 'approved')
 *   → If errors: Recompute (push back to 'processing')
 *   → After recompute: Submit for review again → Review again
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function RunPicker({ runs, selectedId, onChange }) {
  return (
    <select
      value={selectedId || ''}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
    >
      <option value="" disabled>Select run…</option>
      {runs.map((r) => (
        <option key={r.id} value={r.id}>{r.month_label} ({r.status.replace(/_/g, ' ')})</option>
      ))}
    </select>
  );
}

function FlagErrorModal({ employee, runId, onClose, onSaved }) {
  const [form, setForm] = useState({
    error_type: 'salary_mismatch',
    description: '',
    severity: 'warning',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const ERROR_TYPES = [
    { value: 'salary_mismatch',      label: 'Salary Mismatch' },
    { value: 'missing_attendance',   label: 'Missing Attendance' },
    { value: 'leave_inconsistency',  label: 'Leave Inconsistency' },
    { value: 'deduction_mismatch',   label: 'Deduction Mismatch' },
    { value: 'lop_mismatch',         label: 'LOP Mismatch' },
    { value: 'manual_correction',    label: 'Manual Correction Required' },
  ];

  const submit = async () => {
    if (!form.description.trim()) { setErr('Description is required'); return; }
    setBusy(true);
    setErr('');
    try {
      await financeApi.createError(runId, { ...form, employee_id: employee.employee_id });
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to flag error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">Flag Issue</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <p className="text-sm text-slate-500">
          Employee: <span className="font-semibold text-slate-700">{employee.employee_name}</span>
        </p>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Error Type</label>
            <select
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={form.error_type}
              onChange={(e) => setForm((f) => ({ ...f, error_type: e.target.value }))}
            >
              {ERROR_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Severity</label>
            <select
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={form.severity}
              onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
            >
              <option value="warning">Warning</option>
              <option value="error">Error (blocks approval)</option>
              <option value="info">Info</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
            <textarea
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              placeholder="Describe the issue in detail…"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex gap-3 justify-end pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Flag Issue'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Adjustment types: direction is inferred from type ────────────────────────
const ADJ_TYPES = [
  { value: 'bonus',            label: 'Bonus',           direction: 'addition' },
  { value: 'variable_pay',     label: 'Variable Pay',    direction: 'addition' },
  { value: 'incentive',        label: 'Incentive',       direction: 'addition' },
  { value: 'arrears',          label: 'Arrears',         direction: 'addition' },
  { value: 'other_addition',   label: 'One-time Earning',direction: 'addition' },
  { value: 'advance_recovery', label: 'Recovery',        direction: 'deduction' },
  { value: 'other_deduction',  label: 'Deduction',       direction: 'deduction' },
];

// Run states in which adjustments can still be added/removed
const EDITABLE_STATES = ['draft', 'attendance_frozen', 'processing', 'under_review', 'error_found'];

// ─── Add Adjustment Modal ─────────────────────────────────────────────────────

function AddAdjustmentModal({ run, employees, onClose, onSaved }) {
  const EMPTY = {
    employee_id: '',
    adjustment_type: 'bonus',
    amount: '',
    description: '',
    is_taxable: true,
  };
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const typeInfo = ADJ_TYPES.find((t) => t.value === form.adjustment_type) || ADJ_TYPES[0];
  const isDeduction = typeInfo.direction === 'deduction';

  const validate = () => {
    if (!form.employee_id) return 'Select an employee';
    if (!form.adjustment_type) return 'Select an adjustment type';
    if (!form.amount || isNaN(Number(form.amount))) return 'Enter a valid amount';
    if (Number(form.amount) <= 0) return 'Amount must be greater than ₹0';
    // Validate employee belongs to this run
    const inRun = employees.some((e) => e.employee_id === Number(form.employee_id));
    if (!inRun) return 'Selected employee is not part of this payroll run';
    return null;
  };

  const handleSave = async () => {
    const validationError = validate();
    if (validationError) { setErr(validationError); return; }
    setBusy(true); setErr('');
    try {
      await financeApi.addAdjustment(run.id, {
        employee_id: Number(form.employee_id),
        adjustment_type: form.adjustment_type,
        direction: typeInfo.direction,
        amount: Number(form.amount),
        description: form.description || null,
        is_taxable: form.is_taxable,
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to save adjustment');
    } finally {
      setBusy(false);
    }
  };

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden">
        {/* Header */}
        <div className="bg-[#0a1731] px-6 py-4 flex items-center justify-between">
          <div>
            <p className="text-white font-bold text-base">Add Adjustment</p>
            <p className="text-slate-400 text-xs mt-0.5">{run.month_label} — {run.status.replace(/_/g, ' ')}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-lg leading-none">✕</button>
        </div>

        {/* Form */}
        <div className="p-6 space-y-4">
          {err && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
              {err}
            </div>
          )}

          {/* Employee */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Employee <span className="text-rose-500">*</span>
            </label>
            <select
              value={form.employee_id}
              onChange={(e) => set('employee_id', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            >
              <option value="">Select employee…</option>
              {employees.map((e) => (
                <option key={e.employee_id} value={e.employee_id}>
                  {e.employee_name} {e.department ? `— ${e.department}` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Adjustment Type */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Adjustment Type <span className="text-rose-500">*</span>
            </label>
            <select
              value={form.adjustment_type}
              onChange={(e) => set('adjustment_type', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            >
              {ADJ_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className={`text-[11px] mt-1 font-medium ${isDeduction ? 'text-rose-600' : 'text-emerald-600'}`}>
              {isDeduction ? '− Reduces net pay' : '+ Increases net pay'}
            </p>
          </div>

          {/* Amount */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Amount (₹) <span className="text-rose-500">*</span>
            </label>
            <input
              type="number"
              min="1"
              step="1"
              value={form.amount}
              onChange={(e) => set('amount', e.target.value)}
              placeholder="e.g. 5000"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Description / Remarks</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="e.g. Q4 performance bonus, October arrears…"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            />
          </div>

          {/* Taxable */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-2">Taxable (affects TDS)</label>
            <div className="flex gap-4">
              {[true, false].map((v) => (
                <label key={String(v)} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="is_taxable"
                    checked={form.is_taxable === v}
                    onChange={() => set('is_taxable', v)}
                    className="accent-brand-500"
                  />
                  <span className="text-sm text-slate-700">{v ? 'Yes — taxable' : 'No — exempt'}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Payroll run (read-only) */}
          <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2 text-xs text-slate-500">
            Payroll Run: <span className="font-semibold text-slate-700">{run.month_label}</span>
            {' · '}After saving, click <strong>Recompute Payroll</strong> to reflect this adjustment in payroll figures.
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={busy}
            className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50 transition"
          >
            {busy ? 'Saving…' : 'Save Adjustment'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Bonus / Variable Pay Adjustments Panel ──────────────────────────────────

function AdjustmentsPanel({ run, employees, onRecompute }) {
  const [adjs, setAdjs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [filterEmpId, setFilterEmpId] = useState('');
  const [toast, setToast] = useState('');
  const [needsRecompute, setNeedsRecompute] = useState(false);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  const canEdit = run && EDITABLE_STATES.includes(run.status);

  const load = () => {
    if (!run?.id) return;
    setLoading(true);
    financeApi.listAdjustments(run.id, filterEmpId || undefined)
      .then(setAdjs)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [run?.id, filterEmpId]);

  const handleSaved = () => {
    load();
    setNeedsRecompute(true);
    showToast('Adjustment saved — click Recompute Payroll to update payslip figures');
  };

  const handleDelete = async (id) => {
    try {
      await financeApi.deleteAdjustment(id);
      load();
      setNeedsRecompute(true);
      showToast('Adjustment removed — recompute payroll to update figures');
    } catch (e) {
      showToast(e?.data?.detail || 'Delete failed');
    }
  };

  const empName = (id) => employees.find((e) => e.employee_id === Number(id))?.employee_name || `#${id}`;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-800 text-white text-sm rounded-xl px-4 py-3 shadow-xl">
          {toast}
        </div>
      )}

      {showModal && (
        <AddAdjustmentModal
          run={run}
          employees={employees}
          onClose={() => setShowModal(false)}
          onSaved={handleSaved}
        />
      )}

      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-700">Bonus / Variable Pay Adjustments</p>
          <p className="text-xs text-slate-400 mt-0.5">One-time bonus, variable pay, arrears, incentives, or ad-hoc deductions per employee</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={filterEmpId}
            onChange={(e) => setFilterEmpId(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
          >
            <option value="">All Employees</option>
            {employees.map((e) => (
              <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>
            ))}
          </select>
          {canEdit && (
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600 transition"
            >
              + Add Adjustment
            </button>
          )}
        </div>
      </div>

      {/* Recompute banner */}
      {needsRecompute && canEdit && (
        <div className="px-5 py-3 bg-amber-50 border-b border-amber-100 flex items-center justify-between gap-3">
          <p className="text-xs text-amber-800">
            Adjustments changed — recompute payroll to apply bonus / deduction changes to gross, TDS, and net salary.
          </p>
          {['processing', 'under_review', 'error_found'].includes(run?.status) && (
            <button
              onClick={() => { onRecompute(); setNeedsRecompute(false); }}
              className="flex-shrink-0 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600 transition"
            >
              ⚡ Recompute Payroll
            </button>
          )}
        </div>
      )}

      {/* Locked state notice */}
      {!canEdit && (
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 text-xs text-slate-500">
          Adjustments are locked — payroll run is <span className="font-semibold">{run?.status?.replace(/_/g, ' ')}</span>.
          Only runs in draft / processing / under review can be modified.
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-6 w-6 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : adjs.length === 0 ? (
        <div className="px-5 py-8 text-center">
          <p className="text-slate-400 text-sm">No adjustments for this run{filterEmpId ? ' / employee' : ''}</p>
          {canEdit && (
            <button
              onClick={() => setShowModal(true)}
              className="mt-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 transition"
            >
              + Add First Adjustment
            </button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-500 uppercase">
                {['Employee', 'Type', 'Direction', 'Amount', 'Taxable', 'Description', canEdit ? 'Remove' : ''].filter(Boolean).map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {adjs.map((a) => (
                <tr key={a.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                  <td className="px-4 py-2.5 font-medium text-slate-700 whitespace-nowrap">{a.employee_name || empName(a.employee_id)}</td>
                  <td className="px-4 py-2.5 text-slate-600 capitalize whitespace-nowrap">{a.adjustment_type.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      a.direction === 'addition' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                    }`}>
                      {a.direction === 'addition' ? '+ Addition' : '− Deduction'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono font-semibold text-slate-700">
                    ₹{Number(a.amount).toLocaleString('en-IN')}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      a.is_taxable ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
                    }`}>
                      {a.is_taxable ? 'Taxable' : 'Exempt'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-[160px] truncate">{a.description || '—'}</td>
                  {canEdit && (
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => handleDelete(a.id)}
                        className="rounded bg-rose-50 text-rose-600 border border-rose-200 px-2 py-1 text-[10px] font-medium hover:bg-rose-100 transition"
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2.5 border-t border-slate-100 text-xs text-slate-400">
            {adjs.length} adjustment{adjs.length !== 1 ? 's' : ''} total
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function FinanceReview() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [run, setRun] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [flagTarget, setFlagTarget] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [toast, setToast] = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  useEffect(() => {
    financeApi.listRuns()
      .then((data) => {
        setRuns(data);
        // Auto-select the first run under_review or processing
        const active = data.find((r) => r.status === 'under_review' || r.status === 'processing');
        setSelectedId((active || data[0])?.id);
      })
      .finally(() => setLoading(false));
  }, []);

  const loadDetails = (id) => {
    if (!id) return;
    setLoadingDetails(true);
    Promise.all([
      financeApi.getRun(id),
      financeApi.getRunEmployees(id),
      financeApi.listErrors(id),
    ])
      .then(([r, emps, errs]) => { setRun(r); setEmployees(emps); setErrors(errs); })
      .finally(() => setLoadingDetails(false));
  };

  useEffect(() => { loadDetails(selectedId); }, [selectedId]);

  const handleAction = async (action, description = '') => {
    if (!run) return;
    setActionBusy(true);
    try {
      await financeApi.runAction(run.id, action, description);
      showToast(`Action '${action}' completed`);
      loadDetails(selectedId);
    } catch (e) {
      showToast(e?.data?.detail || e.message || 'Action failed');
    } finally {
      setActionBusy(false);
    }
  };

  const openErrors = errors.filter((e) => !e.is_resolved);

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-800 text-white text-sm rounded-xl px-4 py-3 shadow-xl">
          {toast}
        </div>
      )}
      {flagTarget && (
        <FlagErrorModal
          employee={flagTarget}
          runId={run.id}
          onClose={() => setFlagTarget(null)}
          onSaved={() => loadDetails(selectedId)}
        />
      )}

      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          navigate(role_ === 'admin' ? '/admin-dashboard/payroll' : '/employee-dashboard/finance');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Finance Review</h1>
          <p className="text-sm text-slate-500 mt-0.5">Review payroll data, flag issues, and approve or recompute</p>
        </div>
        <RunPicker runs={runs} selectedId={selectedId} onChange={setSelectedId} />
      </div>

      {/* Workflow decision panel */}
      {run && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-700">{run.month_label}</p>
              <p className="text-xs text-slate-400 mt-0.5">
                Status: <span className="font-semibold text-slate-600">{run.status.replace(/_/g, ' ')}</span>
                {' · '}Open errors: <span className={`font-semibold ${openErrors.length > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{openErrors.length}</span>
              </p>
            </div>

            <div className="flex gap-2 flex-wrap">
              {run.status === 'under_review' && (
                <>
                  <button
                    disabled={actionBusy || openErrors.length > 0}
                    onClick={() => handleAction('approve')}
                    className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-50 transition"
                    title={openErrors.length > 0 ? 'Resolve all errors first' : 'Send payroll to Finance Head for final approval'}
                  >
                    ✓ Send To Finance Head
                  </button>
                  <button
                    disabled={actionBusy}
                    onClick={() => handleAction('recompute', 'Errors found during review')}
                    className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 transition"
                  >
                    ↺ Recompute
                  </button>
                  <button
                    disabled={actionBusy}
                    onClick={() => handleAction('reject', 'Rejected by finance review')}
                    className="rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-50 transition"
                  >
                    ✗ Reject
                  </button>
                </>
              )}
              {run.status === 'processing' && (
                <>
                  <button
                    disabled={actionBusy}
                    onClick={() => handleAction('recompute', 'Recompute after adjustment changes')}
                    className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 transition"
                    title="Re-run payroll engine to apply any bonus / adjustment changes"
                  >
                    ↺ Recompute
                  </button>
                  <button
                    disabled={actionBusy}
                    onClick={() => handleAction('submit_review')}
                    className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50 transition"
                  >
                    Submit for Finance Review
                  </button>
                </>
              )}
              {run.status === 'pending_head_approval' && (
                <span className="rounded-lg bg-purple-50 border border-purple-200 px-4 py-2 text-sm font-semibold text-purple-700">
                  ⏳ Sent to Finance Head — Awaiting Final Approval
                </span>
              )}
              {run.status === 'approved' && (
                <span className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm font-semibold text-emerald-700">
                  ✓ Finance Head Approved — Generate Payslips in Finance Head Approval tab
                </span>
              )}
            </div>
          </div>

          {openErrors.length > 0 && (
            <div className="mt-4 rounded-lg bg-rose-50 border border-rose-200 p-3 text-sm text-rose-800">
              <p className="font-semibold mb-1">
                Approval blocked. Resolve payroll issues before continuing.
              </p>
              <p className="text-xs text-rose-700 mb-2">
                {openErrors.length} unresolved error{openErrors.length > 1 ? 's' : ''} found — the Send To Finance Head button will remain disabled until all issues are resolved.
              </p>
              <button
                onClick={() => navigate((role || '').toLowerCase() === 'admin' ? '/admin-dashboard/payroll/errors' : '/employee-dashboard/finance/errors')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-rose-700 transition"
              >
                🔍 Review Errors
              </button>
            </div>
          )}
        </div>
      )}

      {loadingDetails ? (
        <div className="flex items-center justify-center h-32">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : (
        <>
          {/* Errors summary */}
          {errors.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
                <p className="text-sm font-semibold text-slate-700">
                  Flagged Issues ({errors.length})
                </p>
                <button
                  onClick={() => navigate((role || '').toLowerCase() === 'admin' ? '/admin-dashboard/payroll/errors' : '/employee-dashboard/finance/errors')}
                  className="text-xs text-brand-600 font-medium hover:underline"
                >
                  Manage all →
                </button>
              </div>
              <div className="divide-y divide-slate-50">
                {errors.slice(0, 5).map((e) => (
                  <div key={e.id} className="flex items-start gap-3 px-5 py-3">
                    <span className={`mt-0.5 h-2 w-2 rounded-full flex-shrink-0 ${
                      e.is_resolved ? 'bg-emerald-400' : e.severity === 'error' ? 'bg-rose-500' : 'bg-amber-400'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-700">{e.employee_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{e.error_type.replace(/_/g, ' ')} — {e.description}</p>
                    </div>
                    {e.is_resolved && <span className="text-xs text-emerald-600 font-medium">Resolved</span>}
                  </div>
                ))}
                {errors.length > 5 && (
                  <div className="px-5 py-3 text-xs text-slate-400">+{errors.length - 5} more errors</div>
                )}
              </div>
            </div>
          )}

          {/* Bonus / Variable Pay Adjustments */}
          {run && (
            <AdjustmentsPanel
              run={run}
              employees={employees}
              onRecompute={() => handleAction('recompute', 'Recompute after adjustment change')}
            />
          )}

          {/* Employee review table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
            <div className="px-5 py-4 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">
                Employee Review ({employees.length} employees)
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 uppercase">
                    {['Employee', 'Dept', 'Days', 'LOP', 'Gross', 'Deductions', 'Net Pay', 'Status', 'Action'].map((h) => (
                      <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {employees.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-8 text-slate-400">
                        {run?.status === 'draft' ? 'Generate payroll first' : 'No employee data'}
                      </td>
                    </tr>
                  ) : (
                    employees.map((e) => (
                      <tr key={e.id} className={`border-b border-slate-50 hover:bg-slate-50 transition ${e.has_error ? 'bg-rose-50/40' : ''}`}>
                        <td className="px-3 py-2.5 font-medium text-slate-700 whitespace-nowrap">{e.employee_name}</td>
                        <td className="px-3 py-2.5 text-slate-500">{e.department}</td>
                        <td className="px-3 py-2.5 text-slate-500">{e.present_days}/{e.working_days}</td>
                        <td className="px-3 py-2.5 text-rose-600 font-medium">{e.lop_days}</td>
                        <td className="px-3 py-2.5 font-mono text-slate-700">{fmt(e.gross_earnings)}</td>
                        <td className="px-3 py-2.5 font-mono text-rose-600">{fmt(e.total_deductions)}</td>
                        <td className="px-3 py-2.5 font-mono font-semibold text-emerald-700">{fmt(e.net_pay)}</td>
                        <td className="px-3 py-2.5">
                          {e.has_error ? (
                            <span className="rounded-full bg-rose-100 text-rose-700 px-2 py-0.5 text-[10px] font-semibold">Error</span>
                          ) : (
                            <span className="rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 text-[10px] font-semibold">OK</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          {(run?.status === 'under_review' || run?.status === 'processing') && (
                            <button
                              onClick={() => setFlagTarget(e)}
                              className="rounded bg-rose-50 text-rose-600 border border-rose-200 px-2 py-1 text-[10px] font-medium hover:bg-rose-100 transition"
                            >
                              Flag Issue
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
