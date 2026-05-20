import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../../context/AuthContext";
import { leaveApi } from "../../../services/leave";

const STATUS_TONE = {
  pending:  { bg: '#fff7ed', color: '#f97316', label: 'Pending' },
  approved: { bg: '#f0fdf4', color: '#22c55e', label: 'Approved' },
  rejected: { bg: '#fef2f2', color: '#ef4444', label: 'Rejected' },
  expired:  { bg: '#f1f5f9', color: '#64748b', label: 'Expired' },
  used:     { bg: '#dbeafe', color: '#1e40af', label: 'Used' },
};

function fmt(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function RequestModal({ open, onClose, onSubmit }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ worked_on: today, days: 1, reason: '', proof_url: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open) { setForm({ worked_on: today, days: 1, reason: '', proof_url: '' }); setErr(''); }
  }, [open, today]);

  if (!open) return null;
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try {
      await onSubmit({
        worked_on: form.worked_on,
        days: Number(form.days),
        reason: form.reason || null,
        proof_url: form.proof_url || null,
      });
      onClose();
    } catch (ex) {
      setErr(ex?.data?.detail || ex?.message || 'Failed to submit.');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(15,28,46,0.55)", backdropFilter: "blur(3px)" }}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="bg-white rounded-2xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Request Comp-Off</h2>
            <p className="text-xs text-slate-400 mt-0.5">For days you worked on a holiday or weekend.</p>
          </div>
          <button type="button" onClick={onClose} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center hover:bg-slate-200">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div className="bg-teal-50 border border-teal-100 rounded-lg px-4 py-3 text-xs text-teal-700">
            Your request will be sent to your manager for review and then to HR for final approval.
            Once approved, the days are added to your Compensatory_leave balance.
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Worked On <span className="text-red-400">*</span></label>
              <input type="date" required max={today} value={form.worked_on} onChange={(e) => set({ worked_on: e.target.value })}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Days <span className="text-red-400">*</span></label>
              <input type="number" required min="1" max="5" value={form.days} onChange={(e) => set({ days: e.target.value })}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Reason <span className="text-red-400">*</span></label>
            <textarea required rows={3} value={form.reason} onChange={(e) => set({ reason: e.target.value })}
              placeholder="Why you're requesting comp-off (e.g. Worked on the Diwali holiday)…"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent resize-none" />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Proof URL (optional)</label>
            <input type="url" value={form.proof_url} onChange={(e) => set({ proof_url: e.target.value })}
              placeholder="https://… (link to commit, jira, ticket, anything)"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent" />
          </div>

          {err && <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{err}</p>}
        </div>

        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button type="button" onClick={onClose} disabled={busy}
            className="flex-1 py-2.5 rounded-lg border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-60">
            Cancel
          </button>
          <button type="submit" disabled={busy}
            className="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: "#14b8a6" }}>
            {busy ? 'Submitting…' : 'Submit Request'}
          </button>
        </div>
      </form>
    </div>
  );
}

const CompOffPage = () => {
  const { user } = useAuth();
  const [credits, setCredits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [requestOpen, setRequestOpen] = useState(false);
  const [tab, setTab] = useState('All');

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

  const filtered = useMemo(() => {
    if (tab === 'All') return credits;
    return credits.filter((c) => c.status === tab.toLowerCase());
  }, [credits, tab]);

  const totals = useMemo(() => {
    const approvedRemaining = credits
      .filter((c) => c.status === 'approved')
      .reduce((s, c) => s + (c.days || 0), 0);
    return {
      total:    credits.length,
      pending:  credits.filter((c) => c.status === 'pending').length,
      approved: credits.filter((c) => c.status === 'approved').length,
      available: approvedRemaining, // sum of approved (still in balance until used/expired)
    };
  }, [credits]);

  const onSubmit = async (form) => {
    await leaveApi.compOffGrant({ employee_id: user.id, ...form });
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Comp-Off</h1>
          <p className="text-xs text-slate-400 mt-0.5">Request comp-off for days you worked on holidays or weekends.</p>
        </div>
        <button onClick={() => setRequestOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white hover:opacity-90"
          style={{ background: "#14b8a6" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Request Comp-Off
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ['Total', totals.total, '#64748b', '#f1f5f9'],
          ['Pending', totals.pending, '#f97316', '#fff7ed'],
          ['Approved', totals.approved, '#22c55e', '#f0fdf4'],
          ['Available days', totals.available, '#14b8a6', '#f0fdfa'],
        ].map(([label, value, color, bg]) => (
          <div key={label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
            <p className="mt-1 text-2xl font-bold" style={{ color }}>{value}</p>
            <div className="mt-2 h-1 w-12 rounded-full" style={{ background: bg }} />
          </div>
        ))}
      </div>

      {/* History */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="text-sm font-bold text-slate-800">My comp-off requests</h2>
        </div>

        {error && <div className="m-4 rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</div>}

        <div className="flex items-center gap-1 px-5 py-3 border-b border-slate-100">
          {['All', 'Pending', 'Approved', 'Rejected', 'Expired'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={
                'px-3 py-1.5 rounded-md text-xs font-semibold ' +
                (tab === t ? 'bg-teal-50 text-teal-700' : 'text-slate-500 hover:bg-slate-50')
              }>
              {t}
            </button>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {['Worked On', 'Days', 'Reason', 'Stage', 'Status', 'Expires', 'Submitted'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {!loading && filtered.length === 0 && (
                <tr><td colSpan="7" className="px-4 py-8 text-center text-xs text-slate-400">No comp-off requests in this view.</td></tr>
              )}
              {filtered.map((c) => {
                const tone = STATUS_TONE[c.status] || { bg: '#f1f5f9', color: '#64748b', label: c.status };
                return (
                  <tr key={c.id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-3 font-semibold text-slate-700">{fmt(c.worked_on)}</td>
                    <td className="px-4 py-3 font-bold text-slate-700">{c.days}</td>
                    <td className="px-4 py-3 text-slate-500 max-w-xs truncate">{c.reason || '—'}</td>
                    <td className="px-4 py-3 text-[11px] uppercase tracking-wider text-slate-500">
                      {c.status === 'pending' ? (c.next_approver_role === 'manager' ? 'Awaiting Manager' : 'Awaiting HR') : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold" style={{ background: tone.bg, color: tone.color }}>
                        {tone.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{fmt(c.expires_on)}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{fmt(c.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <RequestModal open={requestOpen} onClose={() => setRequestOpen(false)} onSubmit={onSubmit} />
    </div>
  );
};

export default CompOffPage;
