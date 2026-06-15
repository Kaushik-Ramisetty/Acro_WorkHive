import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const MONTH_NAMES = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const STATUS_META = {
  approved_off_cycle: { label: 'Approved — Pending Docs',  bg: 'bg-blue-100 text-blue-800' },
  payment_ready:      { label: 'Payment Ready',            bg: 'bg-violet-100 text-violet-800' },
  paid:               { label: 'Paid',                     bg: 'bg-emerald-100 text-emerald-800' },
  rejected:           { label: 'Rejected',                 bg: 'bg-rose-100 text-rose-800' },
};

const STATUS_FILTERS = [
  { value: '',                  label: 'All' },
  { value: 'approved_off_cycle', label: 'Pending Docs' },
  { value: 'payment_ready',     label: 'Payment Ready' },
  { value: 'paid',              label: 'Paid' },
  { value: 'rejected',          label: 'Rejected' },
];

function fmt(n) {
  return `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ─── StatusBadge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const m = STATUS_META[status] || { label: status, bg: 'bg-slate-100 text-slate-600' };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${m.bg}`}>
      {m.label}
    </span>
  );
}

// ─── DocBadge ─────────────────────────────────────────────────────────────────

function DocBadge({ generated, label }) {
  return generated
    ? <span className="inline-flex items-center rounded-full bg-teal-100 text-teal-700 px-2 py-0.5 text-[10px] font-semibold">✓ {label}</span>
    : <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-500 px-2 py-0.5 text-[10px]">— {label}</span>;
}

// ─── AuditModal ───────────────────────────────────────────────────────────────

function AuditModal({ ocp, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    financeApi.getOffCycleAuditLog(ocp.id)
      .then(data => setLogs(Array.isArray(data) ? data : []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [ocp.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-800">Audit History — {ocp.employee_name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
        </div>
        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="h-6 w-6 rounded-full border-4 border-violet-500 border-t-transparent animate-spin" />
            </div>
          ) : logs.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-6">No audit entries yet.</p>
          ) : (
            <ol className="relative border-l border-slate-200 ml-3 space-y-4">
              {logs.map((lg, i) => (
                <li key={lg.id || i} className="ml-4">
                  <span className="absolute -left-1.5 h-3 w-3 rounded-full bg-violet-400 border-2 border-white" />
                  <p className="text-xs font-semibold text-slate-700 capitalize">{lg.action.replace(/_/g, ' ')}</p>
                  {(lg.from_status || lg.to_status) && (
                    <p className="text-[11px] text-slate-500">
                      {lg.from_status && <span className="line-through mr-1">{lg.from_status}</span>}
                      {lg.to_status && <span className="font-medium text-violet-700">{lg.to_status}</span>}
                    </p>
                  )}
                  {lg.note && <p className="text-[11px] text-slate-500 mt-0.5 italic">{lg.note}</p>}
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    {lg.actor_name || 'System'} · {lg.created_at ? new Date(lg.created_at).toLocaleString() : ''}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
        <div className="flex justify-end mt-4">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Close</button>
        </div>
      </div>
    </div>
  );
}

// ─── MarkPaidModal ────────────────────────────────────────────────────────────

function MarkPaidModal({ ocp, onClose, onDone }) {
  const [remarks, setRemarks] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    setSaving(true); setErr('');
    try {
      await financeApi.markOffCyclePaid(ocp.id, { remarks: remarks || undefined });
      onDone(); onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Failed');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <h3 className="text-sm font-bold text-slate-800 mb-1">Confirm Payment</h3>
        <p className="text-xs text-slate-500 mb-4">
          Confirm that the off-cycle payment has been processed manually via bank upload.
        </p>
        <div className="rounded-lg bg-slate-50 px-3 py-2 mb-4 text-xs space-y-1">
          <p><span className="text-slate-400">Employee:</span> <strong className="text-slate-700">{ocp.employee_name}</strong></p>
          <p><span className="text-slate-400">Bonus Type:</span> <span className="text-slate-700">{ocp.bonus_type}</span></p>
          <p><span className="text-slate-400">Amount:</span> <span className="font-mono font-semibold text-emerald-700">{fmt(ocp.amount)}</span></p>
          <p><span className="text-slate-400">Ref:</span> <span className="font-mono text-slate-600">{ocp.reference_number}</span></p>
        </div>
        <textarea
          value={remarks}
          onChange={e => setRemarks(e.target.value)}
          rows={2}
          placeholder="Remarks (optional)…"
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-none mb-3"
        />
        {err && <p className="text-xs text-rose-600 mb-2">{err}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            onClick={submit}
            disabled={saving}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? 'Confirming…' : 'Mark as Paid'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── ReturnRejectModal ────────────────────────────────────────────────────────

function ReturnRejectModal({ ocp, mode, onClose, onDone }) {
  const isReturn = mode === 'return';
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    setSaving(true); setErr('');
    try {
      if (isReturn) await financeApi.returnOffCyclePayment(ocp.id, note);
      else          await financeApi.rejectOffCyclePayment(ocp.id, note);
      onDone(); onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Failed');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <h3 className="text-sm font-bold text-slate-800 mb-1">
          {isReturn ? 'Return for Rework' : 'Reject Payment'}
        </h3>
        <p className="text-xs text-slate-500 mb-4">
          {isReturn
            ? 'This will reset the payment to Approved status and clear any generated documents. Finance can regenerate them.'
            : 'This will permanently reject the off-cycle payment. This cannot be undone.'}
        </p>
        <div className="rounded-lg bg-slate-50 px-3 py-2 mb-4 text-xs">
          <p><span className="text-slate-400">Employee:</span> <strong>{ocp.employee_name}</strong></p>
          <p><span className="text-slate-400">Amount:</span> <span className="font-mono font-semibold">{fmt(ocp.amount)}</span></p>
        </div>
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          rows={3}
          placeholder={`Reason for ${isReturn ? 'return' : 'rejection'}…`}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-rose-400 resize-none mb-3"
        />
        {err && <p className="text-xs text-rose-600 mb-2">{err}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            onClick={submit}
            disabled={saving}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${
              isReturn ? 'bg-amber-500 hover:bg-amber-600' : 'bg-rose-500 hover:bg-rose-600'
            }`}
          >
            {saving ? 'Saving…' : isReturn ? 'Return' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── OCPRow ───────────────────────────────────────────────────────────────────

function OCPRow({ ocp, role, onMarkPaid, onReturn, onReject, onAudit }) {
  const r = (role || '').toLowerCase();
  const isFinance = r === 'finance';
  const isHead    = r === 'finance_head';
  const isHr      = r === 'admin' || r === 'hr';

  const [genPayslip, setGenPayslip]   = useState(false);
  const [genAdvice, setGenAdvice]     = useState(false);
  const [toast, setToast]             = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  const handleGenPayslip = async () => {
    setGenPayslip(true);
    try {
      await financeApi.generateOffCyclePayslip(ocp.id);
      showToast('Payslip generated');
      // Reload is triggered by parent via onMarkPaid callback (which reloads list)
      onMarkPaid(); // re-use to trigger list refresh
    } catch (ex) {
      showToast(ex?.data?.detail || ex?.message || 'Failed to generate payslip');
    } finally { setGenPayslip(false); }
  };

  const handleGenAdvice = async () => {
    setGenAdvice(true);
    try {
      await financeApi.generateOffCycleBankAdvice(ocp.id);
      showToast('Bank advice generated');
      onMarkPaid();
    } catch (ex) {
      showToast(ex?.data?.detail || ex?.message || 'Failed to generate bank advice');
    } finally { setGenAdvice(false); }
  };

  const canManage = isFinance && ['approved_off_cycle', 'payment_ready'].includes(ocp.payment_status);
  const canHead   = isHead    && ['approved_off_cycle', 'payment_ready'].includes(ocp.payment_status);

  return (
    <tr className="border-b border-slate-50 hover:bg-slate-50 transition text-sm">
      {toast && (
        <td colSpan={8} className="p-0">
          <div className="fixed bottom-6 right-6 z-50 rounded-xl bg-slate-800 text-white text-sm px-4 py-3 shadow-lg">
            {toast}
          </div>
        </td>
      )}
      <td className="py-3 px-4">
        <p className="font-medium text-slate-800">{ocp.employee_name}</p>
        <p className="text-xs text-slate-400 font-mono">{ocp.employee_code}</p>
      </td>
      <td className="py-3 px-4 text-slate-600">{ocp.bonus_type}</td>
      <td className="py-3 px-4 font-mono font-semibold text-emerald-700">{fmt(ocp.amount)}</td>
      <td className="py-3 px-4"><StatusBadge status={ocp.payment_status} /></td>
      <td className="py-3 px-4 text-xs text-slate-500">
        {ocp.approved_date ? new Date(ocp.approved_date).toLocaleDateString('en-IN') : '—'}
      </td>
      <td className="py-3 px-4 text-xs text-slate-500">
        {ocp.paid_date ? new Date(ocp.paid_date).toLocaleDateString('en-IN') : '—'}
      </td>
      <td className="py-3 px-4">
        <div className="flex flex-col gap-0.5">
          <DocBadge generated={ocp.payslip_generated}     label="Payslip" />
          <DocBadge generated={ocp.bank_advice_generated} label="Bank Advice" />
        </div>
      </td>
      <td className="py-3 px-4">
        <div className="flex flex-wrap items-center gap-1.5">
          {/* Finance: generate docs */}
          {canManage && !ocp.payslip_generated && (
            <button
              onClick={handleGenPayslip}
              disabled={genPayslip}
              className="rounded bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 text-xs font-medium hover:bg-violet-100 transition disabled:opacity-50"
            >
              {genPayslip ? '…' : 'Gen Payslip'}
            </button>
          )}
          {canManage && ocp.payslip_generated && (
            <a
              href={financeApi.offCyclePayslipUrl(ocp.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded bg-teal-50 text-teal-700 border border-teal-200 px-2.5 py-1 text-xs font-medium hover:bg-teal-100 transition"
            >
              Payslip ↗
            </a>
          )}
          {canManage && !ocp.bank_advice_generated && (
            <button
              onClick={handleGenAdvice}
              disabled={genAdvice}
              className="rounded bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 text-xs font-medium hover:bg-violet-100 transition disabled:opacity-50"
            >
              {genAdvice ? '…' : 'Gen Bank Advice'}
            </button>
          )}
          {canManage && ocp.bank_advice_generated && (
            <a
              href={financeApi.offCycleBankAdviceUrl(ocp.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded bg-teal-50 text-teal-700 border border-teal-200 px-2.5 py-1 text-xs font-medium hover:bg-teal-100 transition"
            >
              Bank Advice ↗
            </a>
          )}
          {canManage && (
            <button
              onClick={() => onMarkPaid(ocp)}
              className="rounded bg-emerald-600 text-white px-2.5 py-1 text-xs font-medium hover:bg-emerald-700 transition"
            >
              Mark Paid
            </button>
          )}

          {/* Finance Head: return / reject */}
          {canHead && (
            <>
              <button
                onClick={() => onReturn(ocp)}
                className="rounded bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 text-xs font-medium hover:bg-amber-100 transition"
              >
                Return
              </button>
              <button
                onClick={() => onReject(ocp)}
                className="rounded bg-rose-500 text-white px-2.5 py-1 text-xs font-medium hover:bg-rose-600 transition"
              >
                Reject
              </button>
            </>
          )}

          {/* HR / paid: download docs read-only */}
          {(isHr || ocp.payment_status === 'paid') && ocp.payslip_generated && (
            <a
              href={financeApi.offCyclePayslipUrl(ocp.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded bg-slate-100 text-slate-700 px-2.5 py-1 text-xs font-medium hover:bg-slate-200 transition"
            >
              Payslip
            </a>
          )}

          {/* Audit */}
          <button
            onClick={() => onAudit(ocp)}
            className="rounded bg-slate-50 text-slate-500 border border-slate-200 px-2.5 py-1 text-xs hover:bg-slate-100 transition"
          >
            History
          </button>

          {/* Paid info */}
          {ocp.payment_status === 'paid' && ocp.paid_by_name && (
            <span className="text-[10px] text-slate-400">by {ocp.paid_by_name}</span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function OffCyclePayments() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const r = (role || '').toLowerCase();
  const isFinance = r === 'finance';
  const isHead    = r === 'finance_head';
  const isHr      = r === 'admin' || r === 'hr';

  const backPath = isHr
    ? '/admin-dashboard/payroll'
    : isHead
    ? '/employee-dashboard/finance-head-payroll'
    : '/employee-dashboard/finance-payroll';

  const [payments, setPayments]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [toast, setToast]         = useState('');
  const defaultFilter = useMemo(() => {
    if (isFinance) return 'approved_off_cycle';
    if (isHead)    return 'approved_off_cycle';
    return '';
  }, [isFinance, isHead]);
  const [statusFilter, setFilter] = useState(defaultFilter);
  useEffect(() => { setFilter(defaultFilter); }, [defaultFilter]);

  // Modals
  const [markPaidTarget, setMarkPaidTarget]     = useState(null);
  const [returnTarget, setReturnTarget]         = useState(null);
  const [rejectTarget, setRejectTarget]         = useState(null);
  const [auditTarget, setAuditTarget]           = useState(null);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 4000); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await financeApi.listOffCyclePayments({ limit: 200 });
      setPayments(Array.isArray(data) ? data : []);
    } catch {
      setPayments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = statusFilter
    ? payments.filter(p => p.payment_status === statusFilter)
    : payments;

  const pendingCount = payments.filter(p =>
    p.payment_status === 'approved_off_cycle' || p.payment_status === 'payment_ready'
  ).length;

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl bg-slate-800 text-white text-sm px-4 py-3 shadow-lg max-w-sm">
          {toast}
        </div>
      )}

      {/* Modals */}
      {markPaidTarget && (
        <MarkPaidModal
          ocp={markPaidTarget}
          onClose={() => setMarkPaidTarget(null)}
          onDone={() => { load(); showToast('Payment marked as paid'); }}
        />
      )}
      {returnTarget && (
        <ReturnRejectModal
          ocp={returnTarget}
          mode="return"
          onClose={() => setReturnTarget(null)}
          onDone={() => { load(); showToast('Payment returned for rework'); }}
        />
      )}
      {rejectTarget && (
        <ReturnRejectModal
          ocp={rejectTarget}
          mode="reject"
          onClose={() => setRejectTarget(null)}
          onDone={() => { load(); showToast('Payment rejected'); }}
        />
      )}
      {auditTarget && (
        <AuditModal ocp={auditTarget} onClose={() => setAuditTarget(null)} />
      )}

      {/* Back */}
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
      <div>
        <h1 className="text-xl font-bold text-slate-800">Off-Cycle Payments</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Standalone bonus disbursements — completely separate from monthly payroll
        </p>
      </div>

      {/* Pending alert */}
      {pendingCount > 0 && (isFinance || isHead) && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <span className="text-amber-500 text-lg mt-0.5">💳</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              {pendingCount} off-cycle payment{pendingCount > 1 ? 's' : ''} awaiting action
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              {isFinance
                ? 'Generate payslips, bank advice, and mark payments as paid once processed'
                : 'Review and return or reject if documents are not in order'}
            </p>
          </div>
        </div>
      )}

      {/* Filter pills */}
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
            {f.value === '' && payments.length > 0 && (
              <span className="ml-1.5 rounded-full bg-white/20 px-1">{payments.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-soft overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-7 w-7 rounded-full border-4 border-violet-500 border-t-transparent animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-slate-400">
            <span className="text-4xl mb-3">💳</span>
            <p className="text-sm font-medium">
              {statusFilter ? `No ${STATUS_META[statusFilter]?.label?.toLowerCase() || statusFilter} payments` : 'No off-cycle payments yet'}
            </p>
            <p className="text-xs mt-1">
              Off-cycle payments are created automatically when Finance Head approves an off-cycle bonus request
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {['Employee', 'Bonus Type', 'Amount', 'Status', 'Approved Date', 'Paid Date', 'Documents', 'Actions'].map(h => (
                    <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(ocp => (
                  <OCPRow
                    key={ocp.id}
                    ocp={ocp}
                    role={role}
                    onMarkPaid={(target) => target ? setMarkPaidTarget(target) : load()}
                    onReturn={setReturnTarget}
                    onReject={setRejectTarget}
                    onAudit={setAuditTarget}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Info box */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">How Off-Cycle Payments Work</p>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs text-slate-600">
          {[
            { step: '1', title: 'Finance Head Approves',   desc: 'Off-cycle bonus request approved — payment record created automatically here.' },
            { step: '2', title: 'Finance Generates Docs',  desc: 'Finance generates the payslip PDF and bank advice PDF for the employee.' },
            { step: '3', title: 'Finance Uploads to Bank', desc: 'Finance downloads the bank advice and uploads it to the bank portal manually. System does not transfer money.' },
            { step: '4', title: 'Finance Marks Paid',      desc: 'After bank confirms transfer, Finance marks the payment as Paid here.' },
            { step: '5', title: 'Payroll Unaffected',      desc: 'Monthly payroll, Annual CTC, PF, ESI, PT, TDS — none are modified by off-cycle payments.' },
          ].map(({ step, title, desc }) => (
            <div key={step} className="flex gap-2">
              <span className="flex-shrink-0 h-5 w-5 rounded-full bg-violet-400 text-white text-[10px] font-bold flex items-center justify-center mt-0.5">{step}</span>
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
