import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const BONUS_TYPES = [
  'Joining Bonus',
  'Annual Bonus',
  'Performance Bonus',
  'Incentive',
  'Arrears',
  'Special Bonus',
  'Other',
];

const MONTH_NAMES = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const STATUS_META = {
  pending_finance_review:           { label: 'Pending Finance Review',        bg: 'bg-amber-100 text-amber-800' },
  pending_finance_head_approval:    { label: 'Pending Finance Head',          bg: 'bg-blue-100 text-blue-800' },
  waiting_for_payroll_application:  { label: 'Waiting for Payroll',           bg: 'bg-violet-100 text-violet-800' },
  approved:                         { label: 'Approved (Off-Cycle)',           bg: 'bg-emerald-100 text-emerald-800' },
  applied:                          { label: 'Applied to Payroll',            bg: 'bg-teal-100 text-teal-800' },
  rejected:                         { label: 'Rejected',                      bg: 'bg-rose-100 text-rose-800' },
};

const STATUS_FILTERS = [
  { value: '',                                label: 'All' },
  { value: 'pending_finance_review',          label: 'Pending Finance' },
  { value: 'pending_finance_head_approval',   label: 'Pending Head' },
  { value: 'waiting_for_payroll_application', label: 'Waiting for Payroll' },
  { value: 'approved',                        label: 'Approved (Off-Cycle)' },
  { value: 'applied',                         label: 'Applied' },
  { value: 'rejected',                        label: 'Rejected' },
];

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - 2 + i);


// ─── StatusBadge ──────────────────────────────────────────────────────────────

function StatusBadge({ status, req }) {
  const m = STATUS_META[status] || { label: status, bg: 'bg-slate-100 text-slate-600' };
  let label = m.label;
  if (status === 'waiting_for_payroll_application' && req) {
    label = `Approved — Waiting for ${MONTH_NAMES[req.payroll_month] || ''} ${req.payroll_year} Payroll`;
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${m.bg}`}>
      {label}
    </span>
  );
}


// ─── BonusFormModal — create / edit ──────────────────────────────────────────

function BonusFormModal({ employees, initial, onClose, onSaved }) {
  const isEdit = !!initial;
  const now = new Date();

  const [employeeId, setEmployeeId]   = useState(initial?.employee_id ?? '');
  const [month, setMonth]             = useState(initial?.payroll_month ?? (now.getMonth() + 1));
  const [year, setYear]               = useState(initial?.payroll_year ?? now.getFullYear());
  const [bonusType, setBonusType]     = useState(initial?.bonus_type ?? '');
  const [amount, setAmount]           = useState(initial?.amount ?? '');
  const [reason, setReason]           = useState(initial?.reason ?? '');
  const [paymentMode, setPaymentMode] = useState(initial?.payment_mode ?? 'regular_payroll');
  const [saving, setSaving]           = useState(false);
  const [err, setErr]                 = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!employeeId && !isEdit) { setErr('Select an employee'); return; }
    if (!bonusType)   { setErr('Select bonus type'); return; }
    if (!amount || Number(amount) <= 0) { setErr('Amount must be greater than 0'); return; }
    setSaving(true);
    setErr('');
    try {
      if (isEdit) {
        await financeApi.updateBonusRequest(initial.id, {
          payroll_month: Number(month),
          payroll_year:  Number(year),
          bonus_type: bonusType,
          amount: Number(amount),
          reason: reason || null,
          payment_mode: paymentMode,
        });
      } else {
        await financeApi.createBonusRequest({
          employee_id:   Number(employeeId),
          payroll_month: Number(month),
          payroll_year:  Number(year),
          bonus_type: bonusType,
          amount: Number(amount),
          reason: reason || null,
          payment_mode: paymentMode,
        });
      }
      onSaved();
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-bold text-slate-800">
            {isEdit ? 'Edit Bonus Request' : 'New Bonus Request'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isEdit && (
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Employee <span className="text-rose-500">*</span></label>
              <select
                value={employeeId}
                onChange={e => setEmployeeId(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
                required
              >
                <option value="">— Select employee —</option>
                {employees.map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name} ({emp.employee_code})
                  </option>
                ))}
              </select>
            </div>
          )}
          {isEdit && (
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
              Employee: <strong>{initial.employee_name}</strong>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Payroll Month <span className="text-rose-500">*</span></label>
              <select
                value={month}
                onChange={e => setMonth(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
              >
                {MONTH_NAMES.slice(1).map((m, i) => (
                  <option key={i + 1} value={i + 1}>{m}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Year <span className="text-rose-500">*</span></label>
              <select
                value={year}
                onChange={e => setYear(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
              >
                {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Bonus Type <span className="text-rose-500">*</span></label>
            <select
              value={bonusType}
              onChange={e => setBonusType(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
              required
            >
              <option value="">— Select type —</option>
              {BONUS_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Amount (₹) <span className="text-rose-500">*</span></label>
            <input
              type="number"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              min="1"
              step="1"
              placeholder="e.g. 50000"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Reason</label>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={3}
              placeholder="Optional reason or notes…"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            />
          </div>

          {/* Payment Mode */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-2">Payment Mode <span className="text-rose-500">*</span></label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setPaymentMode('regular_payroll')}
                className={`rounded-lg border px-3 py-2.5 text-left text-xs transition ${
                  paymentMode === 'regular_payroll'
                    ? 'border-brand-400 bg-brand-50 text-brand-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                <div className="font-semibold mb-0.5">Regular Payroll</div>
                <div className="text-[11px] text-slate-500 leading-tight">Automatically included when payroll is processed for the selected month. Future months are allowed.</div>
              </button>
              <button
                type="button"
                onClick={() => setPaymentMode('off_cycle')}
                className={`rounded-lg border px-3 py-2.5 text-left text-xs transition ${
                  paymentMode === 'off_cycle'
                    ? 'border-amber-400 bg-amber-50 text-amber-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                <div className="font-semibold mb-0.5">Off-Cycle Payment</div>
                <div className="text-[11px] text-slate-500 leading-tight">Processed as a standalone payment. Allowed even if payroll is closed.</div>
              </button>
            </div>
            {paymentMode === 'off_cycle' && (
              <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Off-cycle payments are processed separately and do not affect the payroll run or Annual CTC.
              </p>
            )}
          </div>

          {err && (
            <p className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">{err}</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Submit Request'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ─── ActionModal — Finance approve/reject, Finance Head final decision ────────

function ActionModal({ req, mode, onClose, onDone }) {
  const [comment, setComment] = useState('');
  const [saving, setSaving]   = useState(false);
  const [err, setErr]         = useState('');

  const isFinanceApprove   = mode === 'finance-approve';
  const isFinanceReject    = mode === 'finance-reject';
  const isHeadApprove      = mode === 'head-approve';
  const isHeadReject       = mode === 'head-reject';
  const requiresComment    = isFinanceReject || isHeadReject;

  const title = isFinanceApprove ? 'Recommend Approval'
    : isFinanceReject ? 'Recommend Rejection'
    : isHeadApprove   ? 'Final Approve'
    : 'Final Reject';

  const desc = isFinanceApprove
    ? 'Recommend this bonus for Finance Head approval. Finance Head will make the final decision.'
    : isFinanceReject
    ? 'Recommend rejection to Finance Head. Finance Head will make the final decision.'
    : isHeadApprove
    ? 'This will give final approval. For regular payroll bonuses, the amount will be automatically included when payroll is processed for the selected month.'
    : 'This will permanently reject the bonus request.';

  const handleSubmit = async () => {
    if (requiresComment && !comment.trim()) { setErr('Comment is required'); return; }
    setSaving(true); setErr('');
    try {
      if (isFinanceApprove)   await financeApi.approveBonusRequest(req.id, comment);
      else if (isFinanceReject) await financeApi.rejectBonusRequest(req.id, comment);
      else if (isHeadApprove)   await financeApi.headApproveBonusRequest(req.id, comment);
      else                      await financeApi.headRejectBonusRequest(req.id, comment);
      onDone();
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Action failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <h3 className="text-sm font-bold text-slate-800 mb-1">{title}</h3>
        <p className="text-xs text-slate-500 mb-4">{desc}</p>

        <div className="rounded-lg bg-slate-50 px-3 py-3 mb-4 text-xs space-y-1">
          <p><span className="text-slate-400">Employee:</span> <strong className="text-slate-700">{req.employee_name}</strong></p>
          <p><span className="text-slate-400">Month:</span> <span className="text-slate-700">{req.payroll_month_label}</span></p>
          <p><span className="text-slate-400">Type:</span> <span className="text-slate-700">{req.bonus_type}</span></p>
          <p><span className="text-slate-400">Amount:</span> <span className="font-mono font-semibold text-emerald-700">₹{Number(req.amount).toLocaleString('en-IN')}</span></p>
          {req.reason && <p><span className="text-slate-400">Reason:</span> <span className="text-slate-700">{req.reason}</span></p>}
          {req.finance_recommendation && (
            <p><span className="text-slate-400">Finance Recommendation:</span> <span className={`font-semibold ${req.finance_recommendation === 'approve' ? 'text-emerald-700' : 'text-rose-600'}`}>{req.finance_recommendation === 'approve' ? 'Approve' : 'Reject'}</span></p>
          )}
        </div>

        <textarea
          value={comment}
          onChange={e => setComment(e.target.value)}
          rows={3}
          placeholder={requiresComment ? 'Reason is required…' : 'Optional comment…'}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none mb-3"
        />

        {err && <p className="text-xs text-rose-600 mb-3">{err}</p>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={saving || (requiresComment && !comment.trim())}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${
              isFinanceApprove || isHeadApprove
                ? 'bg-emerald-600 hover:bg-emerald-700'
                : 'bg-rose-500 hover:bg-rose-600'
            }`}
          >
            {saving ? 'Saving…' : title}
          </button>
        </div>
      </div>
    </div>
  );
}




// ─── BonusRow ─────────────────────────────────────────────────────────────────

function BonusRow({ req, role, onEdit, onCancel, onAction }) {
  const r = (role || '').toLowerCase();
  const isHr      = r === 'admin' || r === 'hr';
  const isFinance = r === 'finance';
  const isHead    = r === 'finance_head';

  return (
    <tr className="border-b border-slate-50 hover:bg-slate-50 transition text-sm">
      <td className="py-3 px-4">
        <p className="font-medium text-slate-800">{req.employee_name}</p>
        <p className="text-xs text-slate-400 font-mono">{req.employee_code}</p>
      </td>
      <td className="py-3 px-4 text-slate-600">{req.payroll_month_label}</td>
      <td className="py-3 px-4 text-slate-600">{req.bonus_type}</td>
      <td className="py-3 px-4 font-mono font-semibold text-emerald-700">
        ₹{Number(req.amount).toLocaleString('en-IN')}
      </td>
      <td className="py-3 px-4 text-slate-500 max-w-[180px] truncate" title={req.reason}>{req.reason || '—'}</td>
      <td className="py-3 px-4">
        <StatusBadge status={req.status} req={req} />
        {req.payment_mode === 'off_cycle' && (
          <span className="mt-1 block rounded-full bg-amber-100 text-amber-700 px-2 py-0.5 text-[10px] font-semibold w-fit">Off-Cycle</span>
        )}
        {req.payment_mode === 'regular_payroll' && req.status === 'waiting_for_payroll_application' && (
          <span className="mt-1 block rounded-full bg-violet-100 text-violet-700 px-2 py-0.5 text-[10px] font-semibold w-fit">Regular Payroll</span>
        )}
      </td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* HR: edit/cancel while pending finance review */}
          {isHr && req.status === 'pending_finance_review' && (
            <>
              <button
                onClick={() => onEdit(req)}
                className="rounded bg-slate-100 text-slate-700 px-2.5 py-1 text-xs font-medium hover:bg-slate-200 transition"
              >
                Edit
              </button>
              <button
                onClick={() => onCancel(req)}
                className="rounded bg-rose-50 text-rose-600 border border-rose-200 px-2.5 py-1 text-xs font-medium hover:bg-rose-100 transition"
              >
                Cancel
              </button>
            </>
          )}

          {/* Finance: recommend approve/reject when pending review */}
          {isFinance && req.status === 'pending_finance_review' && (
            <>
              <button
                onClick={() => onAction(req, 'finance-approve')}
                className="rounded bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 text-xs font-medium hover:bg-emerald-100 transition"
              >
                Recommend Approval
              </button>
              <button
                onClick={() => onAction(req, 'finance-reject')}
                className="rounded bg-rose-50 text-rose-600 border border-rose-200 px-2.5 py-1 text-xs font-medium hover:bg-rose-100 transition"
              >
                Recommend Rejection
              </button>
            </>
          )}

          {/* Finance Head: final decision when pending head approval */}
          {isHead && req.status === 'pending_finance_head_approval' && (
            <>
              <button
                onClick={() => onAction(req, 'head-approve')}
                className="rounded bg-emerald-600 text-white px-2.5 py-1 text-xs font-medium hover:bg-emerald-700 transition"
              >
                Final Approve
              </button>
              <button
                onClick={() => onAction(req, 'head-reject')}
                className="rounded bg-rose-500 text-white px-2.5 py-1 text-xs font-medium hover:bg-rose-600 transition"
              >
                Final Reject
              </button>
            </>
          )}

          {/* Finance recommendation label on pending-head rows */}
          {req.status === 'pending_finance_head_approval' && req.finance_recommendation && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              req.finance_recommendation === 'approve'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-rose-50 text-rose-600'
            }`}>
              Finance: {req.finance_recommendation === 'approve' ? 'Recommended Approval' : 'Recommended Rejection'}
            </span>
          )}

          {req.status === 'rejected' && req.rejection_reason && (
            <span className="text-xs text-slate-400 truncate max-w-[140px]" title={req.rejection_reason}>
              {req.rejection_reason}
            </span>
          )}

          {req.status === 'applied' && req.payroll_adjustment_id && (
            <span className="text-xs text-teal-600 font-medium">Adj #{req.payroll_adjustment_id}</span>
          )}
        </div>
      </td>
    </tr>
  );
}


// ─── Main Component ───────────────────────────────────────────────────────────

export default function BonusRequest() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const r = (role || '').toLowerCase();
  const isHr      = r === 'admin' || r === 'hr';
  const isFinance = r === 'finance';
  const isHead    = r === 'finance_head';

  const backPath = r === 'admin' || r === 'hr'
    ? '/admin-dashboard/payroll'
    : r === 'finance_head'
    ? '/employee-dashboard/finance-head-payroll'
    : '/employee-dashboard/finance-payroll';

  const [requests, setRequests]     = useState([]);
  const [employees, setEmployees]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const defaultFilter = useMemo(() => {
    if (isFinance) return 'pending_finance_review';
    if (isHead)    return 'pending_finance_head_approval';
    return '';
  }, [isFinance, isHead]);

  const [statusFilter, setFilter]   = useState(defaultFilter);
  const [toast, setToast]           = useState('');

  useEffect(() => { setFilter(defaultFilter); }, [defaultFilter]);

  // Modals
  const [showCreate, setShowCreate] = useState(false);
  const [editReq, setEditReq]       = useState(null);
  const [actionReq, setActionReq]   = useState(null);
  const [actionMode, setActionMode] = useState('');
  const [cancelConfirm, setCancelConfirm] = useState(null);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 5000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reqs, emps] = await Promise.all([
        financeApi.listBonusRequests({ limit: 200 }),
        isHr ? financeApi.listEmployees() : Promise.resolve([]),
      ]);
      setRequests(Array.isArray(reqs) ? reqs : []);
      setEmployees(Array.isArray(emps) ? emps : []);
    } catch {
      setRequests([]);
    } finally {
      setLoading(false);
    }
  }, [isHr]);

  useEffect(() => { load(); }, [load]);

  const filtered = statusFilter
    ? requests.filter(r => r.status === statusFilter)
    : requests;

  const pendingCount = requests.filter(r =>
    (isFinance && r.status === 'pending_finance_review') ||
    (isHead    && r.status === 'pending_finance_head_approval') ||
    (isHr      && r.status === 'waiting_for_payroll_application')
  ).length;

  const handleCancel = async () => {
    if (!cancelConfirm) return;
    try {
      await financeApi.cancelBonusRequest(cancelConfirm.id);
      showToast('Bonus request cancelled');
      load();
    } catch (ex) {
      showToast(ex?.data?.detail || 'Cancel failed');
    } finally {
      setCancelConfirm(null);
    }
  };

  return (
    <div className="space-y-6">

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl bg-slate-800 text-white text-sm px-4 py-3 shadow-lg max-w-sm">
          {toast}
        </div>
      )}

      {/* Modals */}
      {(showCreate || editReq) && (
        <BonusFormModal
          employees={employees}
          initial={editReq || null}
          onClose={() => { setShowCreate(false); setEditReq(null); }}
          onSaved={() => { load(); showToast(editReq ? 'Bonus request updated' : 'Bonus request submitted'); }}
        />
      )}

      {actionReq && (
        <ActionModal
          req={actionReq}
          mode={actionMode}
          onClose={() => { setActionReq(null); setActionMode(''); }}
          onDone={() => { load(); showToast('Action completed'); }}
        />
      )}

      {cancelConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Cancel Bonus Request?</h3>
            <p className="text-xs text-slate-500 mb-4">
              This will permanently delete the bonus request for{' '}
              <strong>{cancelConfirm.employee_name}</strong> — {cancelConfirm.bonus_type} ({cancelConfirm.payroll_month_label}).
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setCancelConfirm(null)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Keep</button>
              <button onClick={handleCancel} className="rounded-lg bg-rose-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-600">Cancel Request</button>
            </div>
          </div>
        </div>
      )}

      {/* Back navigation */}
      <button
        onClick={() => navigate(backPath)}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        Back to Payroll Dashboard
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Bonus Requests</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            One-time bonus payments — separate from Annual CTC
          </p>
        </div>
        {isHr && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 transition"
          >
            <span>+</span>
            <span>New Bonus Request</span>
          </button>
        )}
      </div>

      {/* Pending alert */}
      {pendingCount > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <span className="text-amber-500 text-lg mt-0.5">🎁</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              {pendingCount} bonus request{pendingCount > 1 ? 's' : ''} awaiting your action
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              {isFinance
                ? 'Review and recommend approval or rejection — Finance Head makes the final decision'
                : 'Give your final approval or rejection for bonus requests recommended by Finance'}
            </p>
          </div>
        </div>
      )}

      {/* Status filter pills */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              statusFilter === f.value
                ? 'bg-slate-800 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {f.label}
            {f.value === '' && requests.length > 0 && (
              <span className="ml-1.5 rounded-full bg-white/20 px-1">{requests.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-soft overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-7 w-7 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-slate-400">
            <span className="text-4xl mb-3">🎁</span>
            <p className="text-sm font-medium">
              {statusFilter ? `No ${STATUS_META[statusFilter]?.label?.toLowerCase() || statusFilter} requests` : 'No bonus requests yet'}
            </p>
            {isHr && !statusFilter && (
              <p className="text-xs mt-1">Click "New Bonus Request" to get started</p>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Employee', 'Payroll Month', 'Bonus Type', 'Amount', 'Reason', 'Status', 'Actions'].map(h => (
                    <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(req => (
                  <BonusRow
                    key={req.id}
                    req={req}
                    role={role}
                    onEdit={setEditReq}
                    onCancel={setCancelConfirm}
                    onAction={(req, mode) => { setActionReq(req); setActionMode(mode); }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Info box */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">How Bonus Requests Work</p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs text-slate-600">
          {[
            { step: '1', title: 'HR Creates', desc: 'HR selects employee, payroll month, bonus type and amount. Submitted for Finance review.' },
            { step: '2', title: 'Finance Reviews', desc: 'Finance recommends approval or rejection. Both outcomes go to Finance Head for final decision.' },
            { step: '3', title: 'Finance Head Decides', desc: 'Finance Head gives final approval or rejection. Regular payroll bonuses are queued; off-cycle are processed separately.' },
            { step: '4', title: 'Payslip', desc: 'Regular payroll bonus is automatically included when payroll runs for the selected month. Annual CTC is not changed.' },
          ].map(({ step, title, desc }) => (
            <div key={step} className="flex gap-2">
              <span className="flex-shrink-0 h-5 w-5 rounded-full bg-slate-300 text-white text-[10px] font-bold flex items-center justify-center mt-0.5">{step}</span>
              <div>
                <p className="font-semibold text-slate-700">{title}</p>
                <p>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
