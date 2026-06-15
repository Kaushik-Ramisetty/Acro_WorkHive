/**
 * Salary Revision Workflow — role-aware single page.
 *
 * HR / Admin:
 *   - Create a new salary revision (new annual CTC + effective date + reason)
 *   - Edit a pending-finance-review revision
 *   - Cancel a pending-finance-review revision
 *   - View full history of all revisions
 *
 * Finance:
 *   - View all revisions in pending_finance_review status
 *   - Recommend Approval → forwards to Finance Head
 *   - Recommend Rejection → forwards to Finance Head with note
 *   - Cannot edit CTC
 *
 * Finance Head:
 *   - View all revisions in pending_finance_head_approval status
 *   - Final Approve → applies salary revision in DB
 *   - Final Reject
 *   - Cannot edit CTC
 *
 * Approved revisions are read-only. Old salary version remains in DB.
 * Payroll uses the latest approved version where effective_from <= pay period end.
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

// ─── Constants ────────────────────────────────────────────────────────────────

const REASONS = [
  'Annual Appraisal',
  'Promotion',
  'Confirmation',
  'Market Correction',
  'Retention Hike',
  'Other',
];

const STATUS_META = {
  pending_finance_review: {
    label: 'Pending Finance Review',
    bg: 'bg-amber-100 text-amber-800',
  },
  pending_finance_head_approval: {
    label: 'Pending Finance Head Approval',
    bg: 'bg-blue-100 text-blue-800',
  },
  approved: { label: 'Approved', bg: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Rejected', bg: 'bg-rose-100 text-rose-800' },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function fmtL(n) {
  if (n === undefined || n === null || n === '' || Number(n) <= 0) return '—';
  return `₹${(Number(n) / 100000).toFixed(2)}L`;
}

function StatusBadge({ status }) {
  const m = STATUS_META[status] || { label: status, bg: 'bg-slate-100 text-slate-600' };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${m.bg}`}>
      {m.label}
    </span>
  );
}

function ChangeBadge({ amount, pct }) {
  if (!amount && amount !== 0) return <span className="text-slate-400 text-xs">—</span>;
  const up = amount >= 0;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${up ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
      {up ? '▲' : '▼'} {fmt(Math.abs(amount))}
      {pct !== undefined && ` (${Math.abs(pct).toFixed(1)}%)`}
    </span>
  );
}

// ─── Comparison Modal (applied revision detail) ───────────────────────────────

function ComparisonModal({ revision, onClose }) {
  const { comparison, employee_name, employee_code, department, designation,
          effective_from, revision_reason, revised_by_name, revised_at } = revision;

  const changed = (row) => Math.abs((row.new || 0) - (row.old || 0)) > 0.01;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-8 mb-8 w-full max-w-3xl bg-white rounded-2xl shadow-xl">
        <div className="flex items-start justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Salary Revision Comparison</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {employee_name} · {employee_code} · {department}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg mt-0.5">✕</button>
        </div>

        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <p className="text-slate-400 mb-0.5">Designation</p>
            <p className="font-medium text-slate-700">{designation || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Effective From</p>
            <p className="font-mono font-semibold text-brand-700">{effective_from || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Revised By</p>
            <p className="font-medium text-slate-700">{revised_by_name || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Revised At</p>
            <p className="font-mono text-slate-600">
              {revised_at
                ? new Date(revised_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
                : '—'}
            </p>
          </div>
        </div>

        {revision_reason && (
          <div className="px-6 py-2.5 bg-amber-50 border-b border-amber-100">
            <p className="text-xs text-amber-800"><strong>Reason:</strong> {revision_reason}</p>
          </div>
        )}

        <div className="p-6">
          {comparison?.components?.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                  <th className="px-4 py-2.5 text-left font-semibold tracking-wider">Component</th>
                  <th className="px-4 py-2.5 text-right font-semibold tracking-wider">Old</th>
                  <th className="px-4 py-2.5 text-right font-semibold tracking-wider">New</th>
                  <th className="px-4 py-2.5 text-right font-semibold tracking-wider">Change</th>
                </tr>
              </thead>
              <tbody>
                {comparison.components.map((row, i) => {
                  const delta = (row.new || 0) - (row.old || 0);
                  const isChanged = Math.abs(delta) > 0.01;
                  const isHighlight = ['Annual CTC', 'Gross Monthly', 'Net Monthly'].includes(row.label);
                  return (
                    <tr key={i} className={`border-b border-slate-50 transition ${isHighlight ? 'bg-brand-50 font-semibold' : isChanged ? 'bg-amber-50' : 'hover:bg-slate-50'}`}>
                      <td className="px-4 py-2.5 text-slate-700">
                        {row.label}
                        {isChanged && <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-amber-500 align-middle" />}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono ${isChanged ? 'text-slate-400 line-through' : 'text-slate-600'}`}>
                        {fmt(row.old)}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono font-semibold ${isChanged ? (delta > 0 ? 'text-emerald-700' : 'text-rose-700') : 'text-slate-700'}`}>
                        {fmt(row.new)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {isChanged ? (
                          <span className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${delta > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                            {delta > 0 ? '+' : ''}{fmt(delta)}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-400 text-center py-6">No component breakdown available.</p>
          )}
          <p className="mt-4 text-xs text-slate-400">
            Amber rows = changed components. Closed payrolls before {effective_from || 'this date'} use the old salary.
          </p>
        </div>

        <div className="flex justify-end px-6 pb-6">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Create / Edit Modal ──────────────────────────────────────────────────────

function RevisionFormModal({ employees, onClose, onSaved, editRevision = null }) {
  const isEdit = !!editRevision;

  const [empId, setEmpId] = useState(isEdit ? String(editRevision.employee_id) : '');
  const [empSearch, setEmpSearch] = useState('');
  const [currentCtc, setCurrentCtc] = useState(isEdit ? editRevision.old_ctc : null);
  const [newCtc, setNewCtc] = useState(isEdit ? String(editRevision.new_ctc) : '');
  const [effectiveFrom, setEffectiveFrom] = useState(isEdit ? editRevision.effective_from : '');
  const [reason, setReason] = useState(isEdit ? (editRevision.reason || '') : '');
  const [joiningDate, setJoiningDate] = useState(isEdit ? editRevision.joining_date : null);
  const [loadingCtc, setLoadingCtc] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});

  const filteredEmps = useMemo(() => {
    if (!empSearch) return employees;
    const q = empSearch.toLowerCase();
    return employees.filter(
      (e) =>
        (e.name || '').toLowerCase().includes(q) ||
        (e.employee_code || '').toLowerCase().includes(q),
    );
  }, [employees, empSearch]);

  const handleEmpChange = useCallback(async (id) => {
    setEmpId(id);
    setCurrentCtc(null);
    setJoiningDate(null);
    if (!id) return;
    setLoadingCtc(true);
    try {
      const found = employees.find((e) => String(e.id) === String(id));
      setJoiningDate(found?.date_of_joining || null);
      const struct = await financeApi.getSalaryStructure(id);
      setCurrentCtc(struct?.annual_ctc ?? 0);
    } catch {
      setCurrentCtc(0);
    } finally {
      setLoadingCtc(false);
    }
  }, [employees]);

  const newCtcNum = parseFloat(newCtc);
  const changeAmount = currentCtc !== null && !isNaN(newCtcNum) ? newCtcNum - currentCtc : null;
  const changePct = currentCtc > 0 && changeAmount !== null ? (changeAmount / currentCtc) * 100 : null;

  const validate = () => {
    const e = {};
    if (!isEdit && !empId) e.empId = 'Employee is required.';
    if (!newCtc || isNaN(newCtcNum) || newCtcNum <= 0) e.newCtc = 'New Annual CTC must be a positive number.';
    if (!effectiveFrom) e.effectiveFrom = 'Effective date is required.';
    if (!reason) e.reason = 'Reason is required.';
    return e;
  };

  const handleSubmit = async () => {
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setSubmitting(true);
    setErrors({});
    try {
      if (isEdit) {
        await financeApi.updateHikeRequest(editRevision.id, {
          new_ctc: newCtcNum,
          effective_from: effectiveFrom,
          reason,
        });
      } else {
        await financeApi.createHikeRequest({
          employee_id: parseInt(empId),
          new_ctc: newCtcNum,
          effective_from: effectiveFrom,
          reason,
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setErrors({ submit: err?.data?.detail || err?.message || 'Failed to submit revision.' });
    } finally {
      setSubmitting(false);
    }
  };

  const cls = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white';
  const errCls = 'text-xs text-rose-600 mt-1';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-8 mb-8 w-full max-w-lg bg-white rounded-2xl shadow-xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">
              {isEdit ? 'Edit Salary Revision' : 'Create Salary Revision'}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {isEdit ? 'Update pending revision — Finance review not yet started.' : 'Submit for Finance → Finance Head approval.'}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">

          {/* Employee picker (create only) */}
          {!isEdit && (
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Employee *</label>
              <input
                type="text"
                placeholder="Search by name or code…"
                value={empSearch}
                onChange={(e) => setEmpSearch(e.target.value)}
                className={cls + ' mb-1.5'}
              />
              <select
                value={empId}
                onChange={(e) => handleEmpChange(e.target.value)}
                className={cls}
              >
                <option value="">— Select employee —</option>
                {filteredEmps.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} ({e.employee_code || `EMP${e.id}`})
                  </option>
                ))}
              </select>
              {errors.empId && <p className={errCls}>{errors.empId}</p>}
            </div>
          )}

          {/* Edit: show employee name read-only */}
          {isEdit && (
            <div className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-400">Employee</p>
              <p className="font-semibold text-slate-800 mt-0.5">
                {editRevision.employee_name}
                <span className="ml-2 text-xs font-mono text-slate-400">{editRevision.employee_code}</span>
              </p>
            </div>
          )}

          {/* Current CTC read-only */}
          {(empId || isEdit) && (
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-400">Current Annual CTC</p>
                <p className="font-mono font-bold text-slate-800 mt-0.5 text-sm">
                  {loadingCtc ? '…' : fmtL(currentCtc)}
                </p>
              </div>
              {joiningDate && (
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs text-slate-400">Joining Date</p>
                  <p className="font-mono font-semibold text-slate-600 mt-0.5 text-sm">{joiningDate}</p>
                </div>
              )}
            </div>
          )}

          {/* New Annual CTC */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">New Annual CTC (₹) *</label>
            <input
              type="number"
              value={newCtc}
              onChange={(e) => setNewCtc(e.target.value)}
              placeholder="e.g. 800000"
              min="1"
              step="1"
              className={cls}
            />
            {errors.newCtc && <p className={errCls}>{errors.newCtc}</p>}
          </div>

          {/* Change preview */}
          {changeAmount !== null && !isNaN(newCtcNum) && newCtcNum > 0 && (
            <div className={`rounded-lg p-3 border ${changeAmount >= 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-rose-50 border-rose-100'}`}>
              <p className={`text-xs font-semibold mb-1 ${changeAmount >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                Revised Annual CTC Preview
              </p>
              <p className={`font-mono font-bold text-lg ${changeAmount >= 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                {fmtL(newCtcNum)}
              </p>
              {currentCtc > 0 && (
                <p className={`text-xs mt-0.5 ${changeAmount >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {changeAmount >= 0 ? '+' : ''}{fmt(changeAmount)}
                  {changePct !== null && ` (${changePct >= 0 ? '+' : ''}${changePct.toFixed(1)}%)`}
                </p>
              )}
            </div>
          )}

          {/* Effective date */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Effective Date *</label>
            <input
              type="date"
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
              min={joiningDate || undefined}
              className={cls}
            />
            {joiningDate && (
              <p className="text-xs text-slate-400 mt-1">Cannot be before joining date ({joiningDate}).</p>
            )}
            {errors.effectiveFrom && <p className={errCls}>{errors.effectiveFrom}</p>}
          </div>

          {/* Reason */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Reason *</label>
            <select value={reason} onChange={(e) => setReason(e.target.value)} className={cls}>
              <option value="">— Select reason —</option>
              {REASONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            {errors.reason && <p className={errCls}>{errors.reason}</p>}
          </div>

          {errors.submit && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
              {errors.submit}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {submitting ? 'Submitting…' : isEdit ? 'Save Changes' : 'Submit for Approval'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Finance / FinanceHead Action Modal ───────────────────────────────────────

function ActionModal({ revision, action, onClose, onDone }) {
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const needsReason = ['reject', 'head-reject'].includes(action);
  const isFinanceHead = action.startsWith('head-');

  const LABELS = {
    approve: 'Recommend Approval',
    reject: 'Recommend Rejection',
    'head-approve': 'Final Approve',
    'head-reject': 'Final Reject',
  };

  const handle = async () => {
    if (needsReason && !comment.trim()) {
      setError('A rejection reason is required.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      if (action === 'approve') await financeApi.approveHikeRequest(revision.id, comment);
      else if (action === 'reject') await financeApi.rejectHikeRequest(revision.id, comment);
      else if (action === 'head-approve') await financeApi.headApproveHikeRequest(revision.id, comment);
      else if (action === 'head-reject') await financeApi.headRejectHikeRequest(revision.id, comment);
      onDone();
      onClose();
    } catch (err) {
      setError(err?.data?.detail || err?.message || 'Action failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const isApprove = action === 'approve' || action === 'head-approve';

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-16 mb-8 w-full max-w-md bg-white rounded-2xl shadow-xl">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">{LABELS[action]}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl">✕</button>
        </div>
        <div className="px-6 py-5 space-y-4">
          {/* Summary */}
          <div className="rounded-lg bg-slate-50 p-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Employee</span>
              <span className="font-medium text-slate-800">{revision.employee_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Current CTC</span>
              <span className="font-mono text-slate-600">{fmtL(revision.old_ctc)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">New CTC</span>
              <span className="font-mono font-bold text-brand-700">{fmtL(revision.new_ctc)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Change</span>
              <ChangeBadge amount={revision.change_amount} pct={revision.change_pct} />
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Effective From</span>
              <span className="font-mono text-slate-700">{revision.effective_from}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Reason</span>
              <span className="text-slate-700">{revision.reason || '—'}</span>
            </div>
            {revision.finance_recommendation && (
              <div className="flex justify-between">
                <span className="text-slate-500">Finance Recommendation</span>
                <span className={`text-xs font-semibold ${revision.finance_recommendation === 'recommend_approval' ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {revision.finance_recommendation === 'recommend_approval' ? 'Recommend Approval' : 'Recommend Rejection'}
                </span>
              </div>
            )}
          </div>

          {isFinanceHead && !isApprove && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
              Rejecting this request will keep the employee's current salary unchanged.
            </div>
          )}

          {isFinanceHead && isApprove && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-800">
              Approving will create a new salary version in the DB. Payroll from {revision.effective_from} onwards will use the new CTC. Old salary history is preserved.
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              {needsReason ? 'Rejection Reason *' : 'Comment (optional)'}
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              placeholder={needsReason ? 'State the reason for rejection…' : 'Add any remarks…'}
            />
          </div>

          {error && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button
            onClick={handle}
            disabled={submitting}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${isApprove ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'}`}
          >
            {submitting ? 'Processing…' : LABELS[action]}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Revision Row ─────────────────────────────────────────────────────────────

function RevisionRow({ rev, role, onEdit, onCancel, onAction }) {
  const r = (role || '').toLowerCase();
  const isHr = r === 'admin' || r === 'hr';
  const isFinance = r === 'finance';
  const isFinanceHead = r === 'finance_head' || r === 'financehead';

  const canEdit = isHr && rev.status === 'pending_finance_review';
  const canCancel = isHr && rev.status === 'pending_finance_review';
  const canFinanceReview = isFinance && rev.status === 'pending_finance_review';
  const canHeadDecide = isFinanceHead && rev.status === 'pending_finance_head_approval';

  return (
    <tr className="border-b border-slate-50 hover:bg-slate-50 transition">
      <td className="px-3 py-2.5 whitespace-nowrap">
        <p className="font-medium text-slate-800 text-sm">{rev.employee_name}</p>
        <p className="font-mono text-xs text-slate-400">{rev.employee_code}</p>
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{rev.department || '—'}</td>
      <td className="px-3 py-2.5 font-mono text-sm text-slate-500">{fmtL(rev.old_ctc)}</td>
      <td className="px-3 py-2.5 font-mono font-semibold text-sm">
        {(!rev.new_ctc || Number(rev.new_ctc) <= 0) && isFinanceHead
          ? <span className="text-rose-600 font-semibold" title="New CTC is missing — approval is blocked">⚠ Missing CTC</span>
          : <span className="text-brand-700">{fmtL(rev.new_ctc)}</span>
        }
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap">
        <ChangeBadge amount={rev.change_amount} pct={rev.change_pct} />
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap">
        <span className="inline-flex items-center rounded-full bg-blue-50 border border-blue-100 px-2 py-0.5 text-xs font-mono text-blue-800">
          {rev.effective_from || '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-600 max-w-[140px] truncate" title={rev.reason}>
        {rev.reason || '—'}
      </td>
      <td className="px-3 py-2.5"><StatusBadge status={rev.status} /></td>
      <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{rev.requested_by_name || '—'}</td>
      {/* Finance recommendation (shown only for Finance/FinanceHead) */}
      <td className="px-3 py-2.5 text-xs whitespace-nowrap">
        {rev.finance_recommendation ? (
          <span className={`font-semibold ${rev.finance_recommendation === 'recommend_approval' ? 'text-emerald-700' : 'text-rose-600'}`}>
            {rev.finance_recommendation === 'recommend_approval' ? 'Recommends Approval' : 'Recommends Rejection'}
          </span>
        ) : (
          <span className="text-slate-300">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap">
        {rev.approved_by_name || '—'}
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap">
        {rev.created_at
          ? new Date(rev.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
          : '—'}
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap">
        <div className="flex gap-1.5">
          {canEdit && (
            <button
              onClick={() => onEdit(rev)}
              className="rounded bg-brand-50 text-brand-700 px-2 py-1 text-xs font-medium hover:bg-brand-100"
            >
              Edit
            </button>
          )}
          {canCancel && (
            <button
              onClick={() => onCancel(rev)}
              className="rounded bg-rose-50 text-rose-700 px-2 py-1 text-xs font-medium hover:bg-rose-100"
            >
              Cancel
            </button>
          )}
          {canFinanceReview && (
            <>
              <button
                onClick={() => onAction(rev, 'approve')}
                className="rounded bg-emerald-50 text-emerald-700 px-2 py-1 text-xs font-medium hover:bg-emerald-100"
              >
                Recommend
              </button>
              <button
                onClick={() => onAction(rev, 'reject')}
                className="rounded bg-rose-50 text-rose-700 px-2 py-1 text-xs font-medium hover:bg-rose-100"
              >
                Reject
              </button>
            </>
          )}
          {canHeadDecide && (
            <>
              {(!rev.new_ctc || Number(rev.new_ctc) <= 0) ? (
                <span
                  className="rounded bg-slate-100 text-slate-400 px-2 py-1 text-xs font-semibold cursor-not-allowed"
                  title="Cannot approve: new CTC is missing or zero. Ask HR to update the request."
                >
                  Approve
                </span>
              ) : (
                <button
                  onClick={() => onAction(rev, 'head-approve')}
                  className="rounded bg-emerald-500 text-white px-2 py-1 text-xs font-semibold hover:bg-emerald-600"
                >
                  Approve
                </button>
              )}
              <button
                onClick={() => onAction(rev, 'head-reject')}
                className="rounded bg-rose-50 text-rose-700 px-2 py-1 text-xs font-medium hover:bg-rose-100"
              >
                Reject
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SalaryRevision() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const r = (role || '').toLowerCase();
  const isHr = r === 'admin' || r === 'hr';
  const isFinance = r === 'finance';
  const isFinanceHead = r === 'finance_head' || r === 'financehead';

  const [revisions, setRevisions] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Revision History (applied SalaryRevisionLog records)
  const [revisionLogs, setRevisionLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(true);
  const [logSearch, setLogSearch] = useState('');
  const [logEmpFilter, setLogEmpFilter] = useState('');
  const [comparison, setComparison] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editRevision, setEditRevision] = useState(null);
  const [actionRevision, setActionRevision] = useState(null);
  const [actionType, setActionType] = useState('');
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [toast, setToast] = useState('');

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setLogsLoading(true);
    try {
      const [revs, emps, logs] = await Promise.all([
        financeApi.listHikeRequests({ limit: 200 }),
        isHr ? financeApi.listEmployees() : Promise.resolve([]),
        financeApi.listSalaryRevisions({ limit: 200 }),
      ]);
      setRevisions(revs);
      setEmployees(emps);
      setRevisionLogs(Array.isArray(logs) ? logs : []);
    } catch (e) {
      console.error('Failed to load salary revisions', e);
    } finally {
      setLoading(false);
      setLogsLoading(false);
    }
  }, [isHr]);

  const openComparison = async (revisionId) => {
    setLoadingDetail(true);
    try {
      const detail = await financeApi.getSalaryRevision(revisionId);
      setComparison(detail);
    } catch (e) {
      console.error('Failed to load revision detail', e);
    } finally {
      setLoadingDetail(false);
    }
  };

  const filteredLogs = useMemo(() => {
    return revisionLogs.filter((r) => {
      if (logEmpFilter && String(r.employee_id) !== String(logEmpFilter)) return false;
      if (!logSearch) return true;
      const q = logSearch.toLowerCase();
      return (
        (r.employee_name || '').toLowerCase().includes(q) ||
        (r.employee_code || '').toLowerCase().includes(q) ||
        (r.department || '').toLowerCase().includes(q) ||
        (r.revision_reason || '').toLowerCase().includes(q) ||
        (r.revised_by_name || '').toLowerCase().includes(q)
      );
    });
  }, [revisionLogs, logEmpFilter, logSearch]);

  useEffect(() => { load(); }, [load]);

  const handleCancel = async () => {
    if (!cancelTarget) return;
    setCancelLoading(true);
    try {
      await financeApi.cancelHikeRequest(cancelTarget.id);
      showToast('Revision request cancelled.');
      setCancelTarget(null);
      load();
    } catch (err) {
      showToast(err?.data?.detail || 'Failed to cancel revision.');
      setCancelTarget(null);
    } finally {
      setCancelLoading(false);
    }
  };

  // Default status filter per role
  const defaultFilter = useMemo(() => {
    if (isFinance) return 'pending_finance_review';
    if (isFinanceHead) return 'pending_finance_head_approval';
    return '';
  }, [isFinance, isFinanceHead]);

  useEffect(() => {
    setStatusFilter(defaultFilter);
  }, [defaultFilter]);

  const filtered = useMemo(() => {
    return revisions.filter((rev) => {
      if (statusFilter && rev.status !== statusFilter) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        (rev.employee_name || '').toLowerCase().includes(q) ||
        (rev.employee_code || '').toLowerCase().includes(q) ||
        (rev.department || '').toLowerCase().includes(q) ||
        (rev.reason || '').toLowerCase().includes(q)
      );
    });
  }, [revisions, statusFilter, search]);

  // Counts for status filter pills
  const counts = useMemo(() => {
    const c = {};
    revisions.forEach((r) => { c[r.status] = (c[r.status] || 0) + 1; });
    return c;
  }, [revisions]);

  const backPath = isHr
    ? '/admin-dashboard/payroll'
    : isFinanceHead
    ? '/employee-dashboard/finance-head-payroll'
    : '/employee-dashboard/finance-payroll';

  const TABLE_HEADERS = [
    'Employee', 'Dept', 'Current CTC', 'New CTC', 'Change',
    'Effective From', 'Reason', 'Status', 'Requested By',
    'Finance Rec.', 'Approved By', 'Created', 'Actions',
  ];

  return (
    <div className="space-y-6">

      {/* Comparison modal */}
      {comparison && (
        <ComparisonModal revision={comparison} onClose={() => setComparison(null)} />
      )}

      {/* Modals */}
      {(showCreateModal || editRevision) && (
        <RevisionFormModal
          employees={employees}
          editRevision={editRevision}
          onClose={() => { setShowCreateModal(false); setEditRevision(null); }}
          onSaved={() => { load(); showToast(editRevision ? 'Revision updated.' : 'Revision submitted for approval.'); }}
        />
      )}

      {actionRevision && (
        <ActionModal
          revision={actionRevision}
          action={actionType}
          onClose={() => { setActionRevision(null); setActionType(''); }}
          onDone={() => { load(); showToast('Action completed.'); }}
        />
      )}

      {/* Cancel confirm */}
      {cancelTarget && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full space-y-4">
            <h3 className="font-bold text-slate-800">Cancel Salary Revision?</h3>
            <p className="text-sm text-slate-600">
              Cancel the revision request for <strong>{cancelTarget.employee_name}</strong>?
              This will permanently delete the pending request.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setCancelTarget(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Keep It
              </button>
              <button
                onClick={handleCancel}
                disabled={cancelLoading}
                className="rounded-lg bg-rose-600 text-white px-4 py-2 text-sm font-medium hover:bg-rose-700 disabled:opacity-50"
              >
                {cancelLoading ? 'Cancelling…' : 'Yes, Cancel Request'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl bg-slate-800 text-white px-4 py-3 text-sm shadow-lg">
          {toast}
        </div>
      )}

      {/* Back */}
      <button
        onClick={() => navigate(backPath)}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to Payroll Dashboard
      </button>

      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Salary Revision</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isHr && 'Create and manage salary revisions. Approved revisions are final and cannot be edited.'}
            {isFinance && 'Review pending salary revisions and recommend approval or rejection to Finance Head.'}
            {isFinanceHead && 'Final approve or reject salary revisions recommended by Finance.'}
          </p>
        </div>
        {isHr && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 transition"
          >
            + New Salary Revision
          </button>
        )}
      </div>

      {/* Status filter pills */}
      <div className="flex flex-wrap gap-2">
        {[
          { value: '', label: 'All' },
          { value: 'pending_finance_review', label: 'Pending Finance Review' },
          { value: 'pending_finance_head_approval', label: 'Pending Finance Head Approval' },
          { value: 'approved', label: 'Approved' },
          { value: 'rejected', label: 'Rejected' },
        ].map((opt) => (
          <button
            key={opt.value}
            onClick={() => setStatusFilter(opt.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium border transition ${
              statusFilter === opt.value
                ? 'bg-brand-500 text-white border-brand-500'
                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
            }`}
          >
            {opt.label}
            {counts[opt.value] !== undefined && (
              <span className="ml-1.5 font-bold">{counts[opt.value]}</span>
            )}
          </button>
        ))}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search employee, reason…"
          className="ml-auto rounded-lg border border-slate-200 px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 w-64"
        />
      </div>

      {/* Info banner for Finance */}
      {isFinance && (
        <div className="rounded-xl bg-blue-50 border border-blue-200 px-5 py-3 text-xs text-blue-800">
          Finance can review and <strong>recommend</strong> approval or rejection. The Finance Head makes the final decision and applies the salary change.
          Finance cannot edit the CTC amount.
        </div>
      )}

      {/* Info banner for Finance Head */}
      {isFinanceHead && (
        <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-5 py-3 text-xs text-emerald-800">
          Final approval creates a new salary version in the database effective from the revision date.
          Closed payroll runs are never modified. Finance Head cannot edit the CTC amount.
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-slate-600 font-medium">
            {revisions.length === 0
              ? 'No salary revisions yet.'
              : 'No matching revisions found.'}
          </p>
          {isHr && revisions.length === 0 && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              Create First Revision
            </button>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                  {TABLE_HEADERS.map((h) => (
                    <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((rev) => (
                  <RevisionRow
                    key={rev.id}
                    rev={rev}
                    role={role}
                    onEdit={(r) => setEditRevision(r)}
                    onCancel={(r) => setCancelTarget(r)}
                    onAction={(r, act) => { setActionRevision(r); setActionType(act); }}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-400">
            {filtered.length} of {revisions.length} revision{revisions.length !== 1 ? 's' : ''}
          </div>
        </div>
      )}

      {/* ── Revision History (Applied SalaryRevisionLog) ──────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-slate-700">Revision History</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Audit trail of all applied salary changes. Closed payrolls are never modified.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Employee filter */}
            {(isHr || isFinance || isFinanceHead) && revisionLogs.length > 0 && (
              <select
                value={logEmpFilter}
                onChange={(e) => setLogEmpFilter(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
              >
                <option value="">All Employees</option>
                {[...new Map(revisionLogs.map((r) => [r.employee_id, r])).values()].map((r) => (
                  <option key={r.employee_id} value={r.employee_id}>
                    {r.employee_name} ({r.employee_code})
                  </option>
                ))}
              </select>
            )}
            <input
              type="text"
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
              placeholder="Search name, reason…"
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-400 w-52"
            />
            <a
              href={`/api${financeApi.salaryRevisionReportUrl(logEmpFilter || undefined)}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
            >
              ↓ Export CSV
            </a>
          </div>
        </div>

        {logsLoading ? (
          <div className="flex items-center justify-center h-32">
            <div className="h-6 w-6 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-slate-400">
            {revisionLogs.length === 0
              ? 'No salary revisions have been applied yet. Applied revisions appear here after Finance Head approval.'
              : 'No matching records.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                  {['Employee', 'Code', 'Dept', 'Old CTC', 'New CTC', 'Change', 'Effective From', 'Reason', 'Revised By', 'Revised At', 'Actions'].map((h) => (
                    <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((r) => {
                  const diff = (r.ctc_difference ?? (r.new_annual_ctc - r.old_annual_ctc)) || 0;
                  const pct = r.ctc_change_pct ?? (r.old_annual_ctc > 0 ? (diff / r.old_annual_ctc) * 100 : 0);
                  return (
                    <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                      <td className="px-3 py-2.5 font-medium text-slate-800 whitespace-nowrap">{r.employee_name}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-slate-400">{r.employee_code}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{r.department || '—'}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-500">
                        {r.old_annual_ctc > 0 ? fmtL(r.old_annual_ctc) : '—'}
                      </td>
                      <td className="px-3 py-2.5 font-mono font-semibold text-brand-700">{fmtL(r.new_annual_ctc)}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <ChangeBadge amount={diff} pct={pct} />
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className="inline-flex items-center rounded-full bg-blue-50 border border-blue-100 px-2 py-0.5 text-xs font-mono text-blue-800">
                          {r.effective_from || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 max-w-[160px]">
                        {r.revision_reason ? (
                          <span className="text-xs text-slate-500 block truncate" title={r.revision_reason}>
                            {r.revision_reason}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-300">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{r.revised_by_name || '—'}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap">
                        {r.revised_at
                          ? new Date(r.revised_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
                          : '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        <button
                          onClick={() => openComparison(r.id)}
                          disabled={loadingDetail}
                          className="rounded bg-brand-50 text-brand-700 px-2.5 py-1 text-xs font-medium hover:bg-brand-100 transition disabled:opacity-50 whitespace-nowrap"
                        >
                          Compare
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {filteredLogs.length > 0 && (
          <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-400">
            {filteredLogs.length} of {revisionLogs.length} applied revision{revisionLogs.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      {/* How it works */}
      <div className="rounded-xl bg-slate-50 border border-slate-200 px-5 py-4 text-xs text-slate-500 space-y-2">
        <p className="font-semibold text-slate-600">How Salary Revision Works</p>
        <p>
          <strong>1. HR</strong> submits a revision with the new Annual CTC and effective date.
          Current CTC auto-loads from the latest active salary structure.
        </p>
        <p>
          <strong>2. Finance</strong> reviews and recommends approval or rejection (forwarded to Finance Head either way).
        </p>
        <p>
          <strong>3. Finance Head</strong> gives the final decision. Approval creates a new salary version in the database —
          the old version is retained. Payroll uses the latest approved version where effective date &le; pay period end.
        </p>
        <p>
          Example: CTC revised to ₹8,00,000 effective 01-Apr-2027 →
          March 2027 payroll uses old CTC. April 2027 onwards uses ₹8,00,000.
          A further revision in 2028 creates another version and replaces from its effective date.
        </p>
      </div>
    </div>
  );
}
