import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useLeaveData } from "../hooks/useLeaveData";
import { leaveApi } from "../services/leave";
import ApplyLeaveDialog from "./ApplyLeaveDialog";

/**
 * Role-agnostic "My Leave" panel — visually + behaviourally identical to the
 * Employee dashboard's Leave page (pages/employee/screens/LeavePage.jsx),
 * scoped to the current user's own leaves regardless of role. Used inside the
 * Apply Leave sub-section tab on Manager and Admin Leave Management pages so
 * those roles get the same self-service experience employees do.
 *
 * Shows: balance cards (with synthetic Comp-Off card), Apply Leave button
 * (opens the shared ApplyLeaveDialog modal), filter tabs, and a history table
 * of the user's own leave requests with cancel actions.
 */

const CircleProgress = ({ pct, color, size = 52, stroke = 5 }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
    </svg>
  );
};

const TYPE_ICONS = {
  'Annual Leave': '🏖️',
  'Casual Leave': '🎯',
  'Sick Leave': '🏥',
  'Earned Leave': '🌴',
  'Paid Leaves': '🌴',
  'WFH': '🏠',
  'Compensatory_leave': '⚡',
  'Maternity': '👶',
  'Maternity Leave': '👶',
  'Paternity': '👨‍👶',
  'Paternity Leave': '👨‍👶',
  'Bereavement': '🕊️',
  'Menstrual Leave': '🌸',
};
const TYPE_COLORS = {
  'Annual Leave': '#3b82f6',
  'Casual Leave': '#f97316',
  'Sick Leave': '#22c55e',
  'Earned Leave': '#22c55e',
  'Paid Leaves': '#22c55e',
  'WFH': '#14b8a6',
  'Compensatory_leave': '#eab308',
  'Maternity Leave': '#ec4899',
  'Paternity Leave': '#8b5cf6',
  'Menstrual Leave': '#f43f5e',
};

const STATUS_TONE = {
  pending:        { bg: '#fff7ed', color: '#f97316', label: 'Pending' },
  approved:       { bg: '#f0fdf4', color: '#22c55e', label: 'Approved' },
  rejected:       { bg: '#fef2f2', color: '#ef4444', label: 'Rejected' },
  cancel_pending: { bg: '#fff7ed', color: '#f97316', label: 'Cancel Pending' },
  cancelled:      { bg: '#f1f5f9', color: '#64748b', label: 'Cancelled' },
  consumed:       { bg: '#dbeafe', color: '#1e40af', label: 'Consumed' },
};

const TABS = ['All', 'Pending', 'Approved', 'Rejected', 'Cancelled'];

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function MyLeavePanel() {
  const { user } = useAuth();
  // Scope to the current user's own leaves regardless of role. The backend's
  // /leave/list correctly filters by employee_id when provided.
  const { requests, balances, loading, error, refresh, cancel } = useLeaveData(
    user?.id ? { employeeId: user.id } : {}
  );
  const [tab, setTab] = useState('All');
  const [applyOpen, setApplyOpen] = useState(false);

  // Comp-off credits power the synthetic Comp-Off balance card next to the
  // regular balances. Same logic the Employee LeavePage uses.
  const [compOffCredits, setCompOffCredits] = useState([]);
  useEffect(() => {
    let cancelled = false;
    leaveApi.compOffList({})
      .then((rows) => { if (!cancelled) setCompOffCredits(Array.isArray(rows) ? rows : []); })
      .catch(() => { if (!cancelled) setCompOffCredits([]); });
    return () => { cancelled = true; };
  }, []);
  const compOffSummary = useMemo(() => {
    const sumDays = (status) => compOffCredits
      .filter((c) => c.status === status)
      .reduce((s, c) => s + (c.days || 0), 0);
    const available = sumDays('approved');
    const used      = sumDays('used');
    const pending   = sumDays('pending');
    const earned    = available + used;
    return { available, used, pending, earned };
  }, [compOffCredits]);

  const filtered = useMemo(() => {
    if (tab === 'All') return requests;
    if (tab === 'Pending')   return requests.filter((r) => r.status === 'pending' || r.status === 'cancel_pending');
    if (tab === 'Approved')  return requests.filter((r) => r.status === 'approved');
    if (tab === 'Rejected')  return requests.filter((r) => r.status === 'rejected');
    if (tab === 'Cancelled') return requests.filter((r) => r.status === 'cancelled');
    return requests;
  }, [requests, tab]);

  const handleCancel = async (id) => {
    if (!confirm('Cancel this leave request?')) return;
    try { await cancel(id); }
    catch (e) { alert(e?.data?.detail || 'Cancel failed'); }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Leave Management</h1>
          <p className="text-xs text-slate-400 mt-0.5">Track and manage your leave requests.</p>
        </div>
        <button
          onClick={() => setApplyOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white transition-colors hover:opacity-90"
          style={{ background: '#14b8a6' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Apply Leave
        </button>
      </div>

      {/* Balance cards (live) */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {balances.length === 0 && (
          <div className="col-span-full rounded-xl border border-dashed border-slate-200 bg-white p-6 text-center text-xs text-slate-400">
            {loading ? 'Loading balances…' : 'No leave balances configured for this year.'}
          </div>
        )}
        {(() => {
          const cards = [];
          let compOffInserted = false;
          const compOffColor = TYPE_COLORS['Compensatory_leave'] || '#eab308';
          const compOffIcon  = TYPE_ICONS['Compensatory_leave']  || '⚡';
          const compOffEarned = compOffSummary.earned || 0;
          const compOffUsedPct = compOffEarned > 0
            ? Math.round((compOffSummary.used / compOffEarned) * 100)
            : 0;
          const compOffCard = (
            <div key="__compoff__" className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-lg">{compOffIcon}</span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                  style={{ background: compOffColor + '18', color: compOffColor }}>
                  {compOffSummary.available} left
                </span>
              </div>
              <div className="flex items-center gap-3">
                <CircleProgress pct={compOffUsedPct} color={compOffColor} size={48} stroke={5} />
                <div>
                  <p className="text-[11px] text-slate-500">Comp-Off</p>
                  <p className="text-base font-bold text-slate-800">
                    {compOffSummary.used} / {compOffEarned}
                  </p>
                  <p className="text-[10px] text-slate-400">
                    {compOffSummary.pending > 0 ? compOffSummary.pending + ' pending' : ''}
                  </p>
                </div>
              </div>
            </div>
          );

          balances.forEach((b) => {
            // Skip the Compensatory_leave LeaveBalance row — the synthetic
            // card above already represents comp-off accurately.
            const ltName = (b.leave_type_name || '').toLowerCase();
            if (ltName.includes('comp')) return;
            const total = b.opening_balance || 1;
            const usedPct = Math.round(((b.used + b.reserved) / total) * 100);
            const color = TYPE_COLORS[b.leave_type_name] || '#3b82f6';
            const icon = TYPE_ICONS[b.leave_type_name] || '🗓️';
            cards.push(
              <div key={b.id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-lg">{icon}</span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: color + '18', color }}>
                    {b.available} left
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <CircleProgress pct={usedPct} color={color} size={48} stroke={5} />
                  <div>
                    <p className="text-[11px] text-slate-500">{b.leave_type_name}</p>
                    <p className="text-base font-bold text-slate-800">{b.used} / {b.opening_balance}</p>
                    <p className="text-[10px] text-slate-400">{b.reserved > 0 ? b.reserved + ' reserved' : ''}</p>
                  </div>
                </div>
              </div>
            );
            const isPaternity = (b.leave_type_name || '').toLowerCase().startsWith('paternity');
            if (isPaternity && !compOffInserted) {
              cards.push(compOffCard);
              compOffInserted = true;
            }
          });
          if (!compOffInserted) cards.push(compOffCard);
          return cards;
        })()}
      </div>

      {/* History */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="text-sm font-bold text-slate-800">Leave history</h2>
        </div>

        {error && <div className="m-4 rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</div>}

        <div className="flex items-center gap-1 px-5 py-3 border-b border-slate-100">
          {TABS.map((t) => (
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
                {['Type', 'From', 'To', 'Days', 'Reason', 'Status', 'Applied', 'Actions'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {!loading && filtered.length === 0 && (
                <tr><td colSpan="8" className="px-4 py-8 text-center text-xs text-slate-400">No requests in this view.</td></tr>
              )}
              {filtered.map((r) => {
                const tone = STATUS_TONE[r.status] || { bg: '#f1f5f9', color: '#64748b', label: r.status };
                const canCancel = r.status === 'pending' || r.status === 'approved';
                return (
                  <tr key={r.id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-3 font-semibold text-slate-700">{r.leave_type_name}</td>
                    <td className="px-4 py-3 text-slate-600">{fmtDate(r.start_date)}</td>
                    <td className="px-4 py-3 text-slate-600">{fmtDate(r.end_date)}</td>
                    <td className="px-4 py-3 font-bold text-slate-700">{r.total_days}</td>
                    <td className="px-4 py-3 text-slate-500 max-w-xs truncate">{r.reason || '—'}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold" style={{ background: tone.bg, color: tone.color }}>
                        {tone.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{fmtDate(r.created_at)}</td>
                    <td className="px-4 py-3">
                      {canCancel ? (
                        <button onClick={() => handleCancel(r.id)}
                          className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
                          {r.status === 'approved' ? 'Request cancel' : 'Cancel'}
                        </button>
                      ) : <span className="text-[11px] text-slate-400">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Apply Leave modal — same dialog the employee dashboard uses. */}
      <ApplyLeaveDialog
        open={applyOpen}
        onClose={() => setApplyOpen(false)}
        onSubmitted={refresh}
      />
    </div>
  );
}
