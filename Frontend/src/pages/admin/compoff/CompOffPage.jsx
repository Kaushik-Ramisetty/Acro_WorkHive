import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { leaveApi } from '../../../services/leave';
import { employeesApi } from '../../../services/employees';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';
import LeaveCard from '../../../components/LeaveCard';

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function StatusPill({ status }) {
  const tone = {
    pending:  { bg: 'bg-amber-50',   text: 'text-amber-700',   label: 'Pending' },
    approved: { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'Approved' },
    rejected: { bg: 'bg-rose-50',    text: 'text-rose-700',    label: 'Rejected' },
    expired:  { bg: 'bg-slate-100',  text: 'text-slate-600',   label: 'Expired' },
    used:     { bg: 'bg-blue-50',    text: 'text-blue-700',    label: 'Used' },
  }[status] || { bg: 'bg-slate-100', text: 'text-slate-600', label: status };
  return (
    <span className={'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' + tone.bg + ' ' + tone.text}>
      {tone.label}
    </span>
  );
}

function GrantModal({ open, employees, onClose, onSubmit }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ employee_id: '', worked_on: today, days: 1, reason: '', proof_url: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => { if (open) { setForm({ employee_id: '', worked_on: today, days: 1, reason: '', proof_url: '' }); setErr(''); } }, [open, today]);

  if (!open) return null;
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try {
      await onSubmit({
        employee_id: Number(form.employee_id),
        worked_on: form.worked_on,
        days: Number(form.days),
        reason: form.reason || null,
        proof_url: form.proof_url || null,
      });
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Failed to grant comp-off.');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" onClick={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-6 py-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Grant Comp-Off</h3>
            <p className="mt-0.5 text-xs text-slate-500">Credit days to an employee who worked on a non-working day.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-slate-500 hover:bg-slate-100">
            <Icon name="reject" className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Employee</label>
            <select required value={form.employee_id} onChange={(e) => set({ employee_id: e.target.value })}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100">
              <option value="">Select…</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name} {e.employee_code ? '(' + e.employee_code + ')' : ''}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Worked On</label>
              <input type="date" required max={today} value={form.worked_on} onChange={(e) => set({ worked_on: e.target.value })}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Days</label>
              <input type="number" required min="1" max="5" value={form.days} onChange={(e) => set({ days: e.target.value })}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
            </div>
          </div>

          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Reason</label>
            <textarea rows={2} value={form.reason} onChange={(e) => set({ reason: e.target.value })}
              placeholder="Why comp-off is being granted (e.g. Worked Diwali holiday)…"
              className="mt-1 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
          </div>

          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Proof URL (optional)</label>
            <input type="url" value={form.proof_url} onChange={(e) => set({ proof_url: e.target.value })}
              placeholder="https://…"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
          </div>

          {err && <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{err}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/40 px-6 py-3">
          <button type="button" disabled={busy} onClick={onClose}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
            Cancel
          </button>
          <button type="submit" disabled={busy}
            className="rounded-lg bg-[#1e3acb] px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#1a31b3] disabled:opacity-60">
            {busy ? 'Granting…' : 'Grant Comp-Off'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function CompOffPage() {
  const { role } = useAuth();
  const isAdminOrManager = role === 'admin' || role === 'manager';

  const [credits, setCredits] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('all');
  const [grantOpen, setGrantOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const flash = (tone, message) => { setToast({ tone, message }); setTimeout(() => setToast(null), 2500); };

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const rows = await leaveApi.compOffList({});
      setCredits(rows);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Failed to load.');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!isAdminOrManager) return;
    employeesApi.list({}).then(setEmployees).catch(() => {});
  }, [isAdminOrManager]);

  const filtered = useMemo(() => {
    if (tab === 'all') return credits;
    return credits.filter((c) => c.status === tab);
  }, [credits, tab]);

  const counts = useMemo(() => ({
    total:    credits.length,
    pending:  credits.filter((c) => c.status === 'pending').length,
    approved: credits.filter((c) => c.status === 'approved').length,
    rejected: credits.filter((c) => c.status === 'rejected').length,
  }), [credits]);

  const onGrant = async (payload) => {
    await leaveApi.compOffGrant(payload);
    flash('emerald', 'Comp-off request submitted.');
    load();
  };

  const onApprove = async (id) => {
    try { await leaveApi.compOffApprove(id); flash('emerald', 'Comp-off approved.'); load(); }
    catch (e) { flash('rose', e?.data?.detail || 'Approve failed.'); }
  };
  const onReject = async (id) => {
    const reason = window.prompt('Reason for rejection (optional)?') || '';
    try { await leaveApi.compOffReject(id, reason); flash('rose', 'Comp-off rejected.'); load(); }
    catch (e) { flash('rose', e?.data?.detail || 'Reject failed.'); }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Comp-Off Credits"
        subtitle="Grant or review compensatory-off credits for employees who worked on non-working days."
        right={
          <>
            {isAdminOrManager && (
              <button onClick={() => setGrantOpen(true)}
                className="flex items-center gap-2 rounded-lg bg-[#1e3acb] px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#1a31b3]">
                <Icon name="plus" className="h-4 w-4" />
                Grant Comp-Off
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <LeaveCard label="Total Credits" value={counts.total}    tone="slate" />
        <LeaveCard label="Pending"       value={counts.pending}  tone="amber" />
        <LeaveCard label="Approved"      value={counts.approved} tone="emerald" />
        <LeaveCard label="Rejected"      value={counts.rejected} tone="rose" />
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-1 border-b border-slate-100 px-4 py-3">
          {['all', 'pending', 'approved', 'rejected', 'expired', 'used'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={
                'rounded-md px-3 py-1 text-xs font-semibold capitalize ' +
                (tab === t ? 'bg-[#1e3acb] text-white' : 'text-slate-500 hover:bg-slate-50')
              }>{t}</button>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {['Employee', 'Worked On', 'Days', 'Reason', 'Expires', 'Status', 'Stage', 'Actions'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {!loading && filtered.length === 0 && (
                <tr><td colSpan="8" className="px-4 py-10 text-center text-xs text-slate-400">No credits in this view.</td></tr>
              )}
              {filtered.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-semibold text-slate-700">{c.employee_name || ('#' + c.employee_id)}</td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(c.worked_on)}</td>
                  <td className="px-4 py-3 font-bold text-slate-700">{c.days}</td>
                  <td className="px-4 py-3 max-w-xs truncate text-slate-500">{c.reason || '—'}</td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(c.expires_on)}</td>
                  <td className="px-4 py-3"><StatusPill status={c.status} /></td>
                  <td className="px-4 py-3 text-[11px] text-slate-500">
                    {c.status === 'pending' ? (c.next_approver_role || '—').toUpperCase() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {c.status === 'pending' && isAdminOrManager ? (
                      <div className="flex items-center gap-1">
                        <button onClick={() => onApprove(c.id)}
                          className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100">
                          Approve
                        </button>
                        <button onClick={() => onReject(c.id)}
                          className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100">
                          Reject
                        </button>
                      </div>
                    ) : <span className="text-[11px] text-slate-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <GrantModal open={grantOpen} employees={employees} onClose={() => setGrantOpen(false)} onSubmit={onGrant} />
    </div>
  );
}
