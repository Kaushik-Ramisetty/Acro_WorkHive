import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const STATUS_META = {
  pending:          { label: 'Pending',          color: 'bg-amber-100 text-amber-700' },
  manager_approved: { label: 'Mgr Approved',     color: 'bg-violet-100 text-violet-700' },
  approved:         { label: 'Finance Approved', color: 'bg-emerald-100 text-emerald-700' },
  paid:             { label: 'Paid',             color: 'bg-blue-100 text-blue-700' },
  rejected:         { label: 'Rejected',         color: 'bg-rose-100 text-rose-700' },
  cancelled:        { label: 'Cancelled',        color: 'bg-slate-100 text-slate-500' },
};

const CLAIM_TYPES = ['Travel', 'Internet', 'Medical', 'Food', 'Equipment', 'Training', 'Other'];

function fmt(n) {
  return Number(n || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
}

// ── New Claim Modal ────────────────────────────────────────────────────────────
function NewClaimModal({ employees, onClose, onSaved }) {
  const [form, setForm] = useState({
    employee_id: '',
    claim_type: 'Travel',
    claim_amount: '',
    remarks: '',
  });
  const [receiptFile, setReceiptFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.employee_id) { setErr('Please select an employee'); return; }
    if (!form.claim_amount || Number(form.claim_amount) <= 0) { setErr('Enter a valid claim amount'); return; }
    setBusy(true); setErr('');
    try {
      await financeApi.createReimbursement({
        employee_id: Number(form.employee_id),
        claim_type: form.claim_type,
        claim_amount: Number(form.claim_amount),
        remarks: form.remarks || undefined,
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to submit claim');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">New Reimbursement Claim</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-xs font-medium text-slate-600 mb-1">Employee *</label>
            <select value={form.employee_id} onChange={e => set('employee_id', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white">
              <option value="">Select employee…</option>
              {employees.map(emp => (
                <option key={emp.id} value={emp.id}>
                  {emp.employee_code} — {emp.name} ({emp.department})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Claim Type</label>
            <select value={form.claim_type} onChange={e => set('claim_type', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white">
              {CLAIM_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Amount (₹) *</label>
            <input type="number" min="1" step="0.01" value={form.claim_amount}
              onChange={e => set('claim_amount', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              placeholder="0.00" />
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-slate-600 mb-1">Receipt / Supporting Document</label>
            <input type="file" accept=".pdf,.jpg,.jpeg,.png"
              onChange={e => setReceiptFile(e.target.files[0])}
              className="w-full text-sm text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-brand-50 file:text-brand-700 file:text-xs file:font-medium hover:file:bg-brand-100" />
            {receiptFile && <p className="text-xs text-emerald-600 mt-1">📎 {receiptFile.name} attached</p>}
            <p className="text-xs text-slate-400 mt-1">PDF, JPG, or PNG accepted (for auditor reference).</p>
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-slate-600 mb-1">Remarks</label>
            <textarea rows={2} value={form.remarks} onChange={e => set('remarks', e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              placeholder="Purpose / description of the expense…" />
          </div>
        </div>
        <div className="flex gap-3 justify-end pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={busy}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
            {busy ? 'Submitting…' : 'Submit Claim'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Finance Approve Modal ──────────────────────────────────────────────────────
function ApproveModal({ claim, onClose, onDone }) {
  const [amount, setAmount] = useState(claim.claim_amount);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (Number(amount) <= 0) { setErr('Approved amount must be > 0'); return; }
    setBusy(true); setErr('');
    try {
      await financeApi.approveReimbursement(claim.id, { approved_amount: Number(amount) });
      onDone(); onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to approve');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">Finance Approve Claim</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <div className="bg-slate-50 rounded-lg p-3 space-y-1 text-sm">
          <p><span className="text-slate-500">Employee:</span> <span className="font-semibold">{claim.employee_name}</span></p>
          <p><span className="text-slate-500">Type:</span> <span className="font-medium">{claim.claim_type}</span></p>
          <p><span className="text-slate-500">Claimed:</span> <span className="font-semibold">{fmt(claim.claim_amount)}</span></p>
        </div>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Approved Amount (₹) *</label>
          <input type="number" min="0.01" step="0.01" value={amount} onChange={e => setAmount(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400" />
          <p className="text-xs text-slate-400 mt-1">May differ from claimed amount after review.</p>
        </div>
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={busy}
            className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-50">
            {busy ? 'Approving…' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Reject Modal ───────────────────────────────────────────────────────────────
function RejectModal({ claim, onClose, onDone }) {
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (!remarks.trim()) { setErr('Rejection reason is required'); return; }
    setBusy(true); setErr('');
    try {
      await financeApi.rejectReimbursement(claim.id, remarks);
      onDone(); onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to reject');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">Reject Claim</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <p className="text-sm text-slate-600">Employee: <span className="font-semibold">{claim.employee_name}</span></p>
        <p className="text-sm text-slate-600">Claimed: <span className="font-semibold">{fmt(claim.claim_amount)}</span></p>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Rejection Reason *</label>
          <textarea rows={3} value={remarks} onChange={e => setRemarks(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            placeholder="Reason for rejection…" />
        </div>
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={busy}
            className="rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-50">
            {busy ? 'Rejecting…' : 'Reject Claim'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function Reimbursements() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [approveTarget, setApproveTarget] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [actionBusy, setActionBusy] = useState(null);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await financeApi.listReimbursements({ status: filterStatus || undefined });
      setRows(data);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load');
    } finally { setLoading(false); }
  }, [filterStatus]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    financeApi.listEmployees().then(setEmployees).catch(() => {});
  }, []);

  const doAction = async (id, action) => {
    setActionBusy(id + action); setErr('');
    try {
      if (action === 'mark-paid')   await financeApi.markReimbursementPaid(id);
      if (action === 'cancel')      await financeApi.cancelReimbursement(id);
      if (action === 'mgr-approve') await financeApi.managerApproveReimbursement(id, '');
      load();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Action failed');
    } finally { setActionBusy(null); }
  };

  const exportCSV = () => {
    const lines = [
      ['Employee', 'Department', 'Claim Type', 'Claimed', 'Approved', 'Status', 'Remarks'].join(','),
      ...rows.map(r => [
        `"${r.employee_name || ''}"`,
        `"${r.department || ''}"`,
        r.claim_type,
        r.claim_amount,
        r.approved_amount != null ? r.approved_amount : '',
        r.status,
        `"${(r.remarks || '').replace(/"/g, '""')}"`,
      ].join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reimbursements_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const totals = rows.reduce((acc, r) => {
    acc.claimed += r.claim_amount || 0;
    acc.approved += r.approved_amount || 0;
    if (['pending', 'manager_approved'].includes(r.status)) acc.pending++;
    if (r.status === 'paid') acc.paid += r.approved_amount || 0;
    return acc;
  }, { claimed: 0, approved: 0, pending: 0, paid: 0 });

  return (
    <div className="space-y-6">
      <button onClick={() => {
          const role_ = (role || '').toLowerCase();
          navigate(role_ === 'admin' ? '/admin-dashboard/payroll' : '/employee-dashboard/finance-payroll');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors">
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Dashboard
      </button>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Reimbursements</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage expense reimbursement claims</p>
        </div>
        <div className="flex gap-3">
          <button onClick={exportCSV}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 shadow-sm flex items-center gap-2">
            ⬇ Export CSV
          </button>
          <button onClick={() => setShowNew(true)}
            className="rounded-xl bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 shadow-sm">
            + New Claim
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Claimed',  value: fmt(totals.claimed),  color: 'text-slate-800' },
          { label: 'Total Approved', value: fmt(totals.approved), color: 'text-emerald-600' },
          { label: 'Pending Review', value: totals.pending,       color: 'text-amber-600' },
          { label: 'Total Paid',     value: fmt(totals.paid),     color: 'text-blue-600' },
        ].map(card => (
          <div key={card.label} className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
            <p className="text-xs text-slate-500 font-medium">{card.label}</p>
            <p className={`text-xl font-bold mt-1 ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-xl p-3 border border-rose-200">{err}</p>}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm text-slate-500 font-medium">Filter:</span>
        {['', 'pending', 'manager_approved', 'approved', 'paid', 'rejected', 'cancelled'].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              filterStatus === s ? 'bg-brand-500 text-white border-brand-500' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
            }`}>
            {s === '' ? 'All' : STATUS_META[s]?.label || s}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">No reimbursement claims found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {['Employee', 'Type', 'Claimed', 'Approved', 'Status', 'Remarks', 'Actions'].map(h => (
                    <th key={h} className={`${h === 'Claimed' || h === 'Approved' ? 'text-right' : 'text-left'} px-4 py-3 font-semibold text-slate-600`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map(r => {
                  const meta = STATUS_META[r.status] || { label: r.status, color: 'bg-slate-100 text-slate-500' };
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/50">
                      <td className="px-4 py-3 font-medium text-slate-800">
                        <div>{r.employee_name || `#${r.employee_id}`}</div>
                        {r.department && <div className="text-xs text-slate-400">{r.department}</div>}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{r.claim_type}</td>
                      <td className="px-4 py-3 text-right text-slate-800 font-mono">{fmt(r.claim_amount)}</td>
                      <td className="px-4 py-3 text-right text-emerald-700 font-mono">
                        {r.approved_amount != null ? fmt(r.approved_amount) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${meta.color}`}>
                          {meta.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500 max-w-[160px] truncate">{r.remarks || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2 flex-wrap">
                          {r.status === 'pending' && (
                            <>
                              <button onClick={() => doAction(r.id, 'mgr-approve')}
                                disabled={actionBusy === r.id + 'mgr-approve'}
                                className="px-2.5 py-1 rounded-lg bg-violet-500 text-white text-xs font-medium hover:bg-violet-600 disabled:opacity-50">
                                Mgr Approve
                              </button>
                              <button onClick={() => setApproveTarget(r)}
                                className="px-2.5 py-1 rounded-lg bg-emerald-500 text-white text-xs font-medium hover:bg-emerald-600">
                                Finance Approve
                              </button>
                              <button onClick={() => setRejectTarget(r)}
                                className="px-2.5 py-1 rounded-lg bg-rose-100 text-rose-700 text-xs font-medium hover:bg-rose-200">
                                Reject
                              </button>
                            </>
                          )}
                          {r.status === 'manager_approved' && (
                            <>
                              <button onClick={() => setApproveTarget(r)}
                                className="px-2.5 py-1 rounded-lg bg-emerald-500 text-white text-xs font-medium hover:bg-emerald-600">
                                Finance Approve
                              </button>
                              <button onClick={() => setRejectTarget(r)}
                                className="px-2.5 py-1 rounded-lg bg-rose-100 text-rose-700 text-xs font-medium hover:bg-rose-200">
                                Reject
                              </button>
                            </>
                          )}
                          {r.status === 'approved' && (
                            <button onClick={() => doAction(r.id, 'mark-paid')}
                              disabled={actionBusy === r.id + 'mark-paid'}
                              className="px-2.5 py-1 rounded-lg bg-blue-100 text-blue-700 text-xs font-medium hover:bg-blue-200 disabled:opacity-50">
                              Mark Paid
                            </button>
                          )}
                          {['pending', 'manager_approved', 'approved'].includes(r.status) && (
                            <button onClick={() => doAction(r.id, 'cancel')}
                              disabled={actionBusy === r.id + 'cancel'}
                              className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 text-xs font-medium hover:bg-slate-200 disabled:opacity-50">
                              Cancel
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
        )}
        {rows.length > 0 && (
          <div className="px-4 py-3 border-t border-slate-100 flex justify-between text-xs text-slate-500">
            <span>{rows.length} claim{rows.length !== 1 ? 's' : ''}</span>
            <span>Total approved: <strong className="text-emerald-700">{fmt(totals.approved)}</strong></span>
          </div>
        )}
      </div>

      {showNew && <NewClaimModal employees={employees} onClose={() => setShowNew(false)} onSaved={load} />}
      {approveTarget && <ApproveModal claim={approveTarget} onClose={() => setApproveTarget(null)} onDone={load} />}
      {rejectTarget && <RejectModal claim={rejectTarget} onClose={() => setRejectTarget(null)} onDone={load} />}
    </div>
  );
}
