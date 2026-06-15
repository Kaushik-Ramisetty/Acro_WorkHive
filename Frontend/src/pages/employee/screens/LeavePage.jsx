import { useEffect, useMemo, useState } from "react";
import { useApp } from "../AppContext";
import { useLeaveData } from "../../../hooks/useLeaveData";
import { useAuth } from "../../../context/AuthContext";
import { leaveApi } from "../../../services/leave";
import CompOffPage from "./CompOffPage";

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
  draft:          { bg: '#f1f5f9', color: '#475569', label: 'Draft' },
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

const LeavePage = () => {
  const { openModal } = useApp();
  const { user } = useAuth();
  const { requests, balances, loading, error, refresh, cancel } = useLeaveData({});
  const [tab, setTab] = useState('All');
  // Top-level section tab: 'leave' (default) or 'compoff'.
  // Comp-Off used to be its own sidebar page; it now lives here as a sub-tab.
  const [section, setSection] = useState('leave');

  // Fetch comp-off credits to power the tracker card rendered next to the
  // Paternity balance card. Comp-off isn't a regular LeaveBalance row — it's
  // tracked in CompOffCredit, so we summarise it ourselves.
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
    const earned    = available + used; // total approved credits ever earned
    return { available, used, pending, earned };
  }, [compOffCredits]);

  const filtered = useMemo(() => {
    if (tab === 'All') return requests;
    if (tab === 'Pending') return requests.filter((r) => r.status === 'pending' || r.status === 'cancel_pending');
    if (tab === 'Approved') return requests.filter((r) => r.status === 'approved');
    if (tab === 'Rejected') return requests.filter((r) => r.status === 'rejected');
    if (tab === 'Cancelled') return requests.filter((r) => r.status === 'cancelled');
    return requests;
  }, [requests, tab]);

  const handleCancel = async (id) => {
    if (!confirm('Cancel this leave request?')) return;
    try { await cancel(id); }
    catch (e) { alert(e?.data?.detail || 'Cancel failed'); }
  };

  const handleSubmitDraft = async (id) => {
    if (!confirm('Submit this draft for approval? You will not be able to edit it after submission.')) return;
    try {
      await leaveApi.draftSubmit(id);
      await refresh();
    } catch (e) {
      alert(e?.data?.detail || 'Submit failed');
    }
  };

  const handleDiscardDraft = async (id) => {
    if (!confirm('Discard this draft? This cannot be undone.')) return;
    try {
      await leaveApi.draftDelete(id);
      await refresh();
    } catch (e) {
      alert(e?.data?.detail || 'Discard failed');
    }
  };

  // When the user picks the comp-off tab, just render CompOffPage in-place.
  // It owns its own data fetching and modal, so no additional wiring is needed.
  const SectionTabs = (
    <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
      {[
        { id: 'leave',   label: 'Leave Requests' },
        { id: 'compoff', label: 'Comp-Off' },
      ].map((t) => {
        const active = section === t.id;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => setSection(t.id)}
            className={'rounded-lg px-3 py-1.5 text-xs font-semibold transition ' +
              (active
                ? 'bg-[#1e3acb] text-white shadow-sm'
                : 'text-slate-500 hover:bg-slate-100')}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );

  if (section === 'compoff') {
    return (
      <div className="space-y-5">
        {SectionTabs}
        <CompOffPage />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {SectionTabs}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Leave Management</h1>
          <p className="text-xs text-slate-400 mt-0.5">Track and manage your leave requests.</p>
        </div>
        <button
          onClick={() => openModal('applyLeave')}
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
          // Render the regular balances; immediately after the Paternity
          // Leave card we splice in a synthetic Comp-Off tracker card so the
          // user sees their comp-off credits alongside the rest of their
          // leave balance picture. If Paternity isn't present, the card is
          // appended at the end of the grid instead.
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
            // The synthetic Comp-Off card below already represents this — skip
            // the duplicate Compensatory_leave LeaveBalance row.
            const ltName = (b.leave_type_name || '').toLowerCase();
            if (ltName.includes('comp')) return;

            // Phase 5D fix: derive the arc from the canonical Phase 5A
            // columns. `allocated_balance` is the grant pool; the arc shows
            // the LOCKED portion = used + reserved + pending, which is
            // exactly (allocated - available). This makes pending requests
            // visible on the indicator (they were previously invisible).
            const allocated = b.allocated_balance || b.opening_balance || 0;
            const reserved  = b.reserved || 0;
            const pending   = b.pending_balance || 0;
            const used      = b.used || 0;
            const available = (typeof b.available === 'number') ? b.available : Math.max(0, allocated - reserved - pending);
            const locked    = Math.max(0, allocated - available);
            const total     = allocated || 1;
            const lockedPct = Math.min(100, Math.round((locked / total) * 100));
            const color = TYPE_COLORS[b.leave_type_name] || '#3b82f6';
            const icon = TYPE_ICONS[b.leave_type_name] || '🗓️';

            // Sub-text: surface both reserved and pending so the user can
            // see why their balance is locked even before approval.
            const subBits = [];
            if (reserved > 0) subBits.push(`${reserved} approved`);
            if (pending  > 0) subBits.push(`${pending} pending`);
            const subText = subBits.join(' · ');

            cards.push(
              <div key={b.id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-lg">{icon}</span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: color + '18', color }}>
                    {available} left
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <CircleProgress pct={lockedPct} color={color} size={48} stroke={5} />
                  <div>
                    <p className="text-[11px] text-slate-500">{b.leave_type_name}</p>
                    <p className="text-base font-bold text-slate-800">{used} / {allocated}</p>
                    <p className="text-[10px] text-slate-400">{subText}</p>
                  </div>
                </div>
              </div>
            );
            // Once we've just rendered Paternity, splice the comp-off card next.
            const isPaternity = (b.leave_type_name || '').toLowerCase().startsWith('paternity');
            if (isPaternity && !compOffInserted) {
              cards.push(compOffCard);
              compOffInserted = true;
            }
          });
          // Fallback: if there's no Paternity card (e.g. female employees,
          // who don't get a paternity balance), append comp-off at the end.
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
                      {r.status === 'draft' ? (
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => handleSubmitDraft(r.id)}
                            className="rounded-md border border-teal-200 bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700 hover:bg-teal-100">
                            Submit
                          </button>
                          <button onClick={() => handleDiscardDraft(r.id)}
                            className="rounded-md border border-rose-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-rose-600 hover:bg-rose-50">
                            Discard
                          </button>
                        </div>
                      ) : canCancel ? (
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
    </div>
  );
};

export default LeavePage;
