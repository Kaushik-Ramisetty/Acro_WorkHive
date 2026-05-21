import { useEffect, useMemo, useState } from 'react';
import { useLeaveData } from '../../../hooks/useLeaveData';
import { leaveApi } from '../../../services/leave';
import { regularization } from '../../../services/attendance';

// Admin (HR-stage) approvals page. Mirrors ManagerApprovalsPage but scopes
// queries to the HR row of the approval chain. The /leave endpoint already
// filters server-side: with role=admin + pending_my_approval=true it returns
// requests where next_approver_role === 'hr'.
// Palette uses CSS variables (see src/index.css) so the page auto-themes
// when the global Light/Dark switch is toggled. Brand accents (primary,
// status hues) stay constant for visual identity.
const C = {
  primary: '#10B981',
  yellow:  '#F59E0B',
  red:     '#EF4444',
  blue:    '#1D4ED8',
  violet:  '#8B5CF6',
  muted:   'var(--hrms-text-muted)',
  border:  'var(--hrms-border)',
  light:   'var(--hrms-surface-2)',
};

function Av({ init, size = 42 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: 'linear-gradient(135deg,#3B82F6,#6366F1)', color: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size <= 30 ? 11 : 13, fontWeight: 700, flexShrink: 0,
    }}>{init}</div>
  );
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}
function timeAgo(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}
function initialsOf(name) {
  return (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
}

const TABS = [
  { key: 'all',     label: 'All Pending' },
  { key: 'leave',   label: 'Leave' },
  { key: 'cancel',  label: 'Cancellations' },
  { key: 'compoff', label: 'Comp-Off' },
  { key: 'regular', label: 'Regularization' },
];

export default function AdminApprovalsPage() {
  // Server-scoped: with admin's JWT, the backend returns leave requests where
  // next_approver_role === 'hr'. Same hook the manager page uses.
  const { requests, loading: leaveLoading, error: leaveErr,
          approve: approveLeave, reject: rejectLeave, approveCancel } =
    useLeaveData({ pendingMyApproval: true });

  // Comp-off pending HR review + pending regularization queue.
  const [compOffs, setCompOffs] = useState([]);
  const [regs, setRegs] = useState([]);
  const [auxErr, setAuxErr] = useState('');
  const refreshAux = async () => {
    setAuxErr('');
    try {
      const [co, rg] = await Promise.all([
        leaveApi.compOffList({ status: 'pending' }).catch(() => []),
        regularization.list({ status: 'pending' }).catch(() => []),
      ]);
      // Comp-off goes through manager → hr; admin sees the hr row.
      setCompOffs(Array.isArray(co) ? co.filter((c) => c.next_approver_role === 'hr') : []);
      // Regularization is admin-only on the backend, so show all pending.
      setRegs(Array.isArray(rg) ? rg : []);
    } catch (e) {
      setAuxErr(e?.message || 'Failed to load approvals queue');
    }
  };
  useEffect(() => { refreshAux(); }, []);

  const [tab, setTab] = useState('all');
  const [busyId, setBusyId] = useState(null);
  const [toast, setToast] = useState(null);
  const flash = (tone, message) => { setToast({ tone, message }); setTimeout(() => setToast(null), 2500); };

  const counts = useMemo(() => ({
    leave:   requests.filter((r) => r.status === 'pending').length,
    cancel:  requests.filter((r) => r.status === 'cancel_pending').length,
    compoff: compOffs.length,
    regular: regs.length,
  }), [requests, compOffs, regs]);
  const allCount = counts.leave + counts.cancel + counts.compoff + counts.regular;

  const items = useMemo(() => {
    const leaveItems = requests
      .filter((r) => r.status === 'pending' || r.status === 'cancel_pending')
      .map((r) => ({
        kind: r.status === 'cancel_pending' ? 'cancel' : 'leave',
        key: 'L-' + r.id,
        id: r.id,
        name: r.employee_name,
        primary: r.leave_type_name,
        secondary: `${r.total_days} day${r.total_days !== 1 ? 's' : ''} (${fmtDate(r.start_date)} → ${fmtDate(r.end_date)})`,
        reason: r.reason,
        created_at: r.created_at,
        raw: r,
      }));
    const coItems = compOffs.map((c) => ({
      kind: 'compoff',
      key: 'C-' + c.id,
      id: c.id,
      name: c.employee_name,
      primary: 'Comp-Off',
      secondary: `${c.days} day${c.days !== 1 ? 's' : ''} · worked on ${fmtDate(c.worked_on)}`,
      reason: c.reason,
      created_at: c.created_at,
      raw: c,
    }));
    const regItems = regs.map((r) => ({
      kind: 'regular',
      key: 'R-' + r.id,
      id: r.id,
      name: r.employee?.full_name || r.employee_name || 'Unknown Employee',
      primary: 'Regularization',
      secondary: `${r.regularization_type || 'attendance'} · ${fmtDate(r.date)}`,
      reason: r.reason,
      created_at: r.created_at,
      raw: r,
    }));
    return [...leaveItems, ...coItems, ...regItems]
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  }, [requests, compOffs, regs]);

  const visible = useMemo(() => {
    if (tab === 'all') return items;
    return items.filter((it) => it.kind === tab);
  }, [items, tab]);

  const onApprove = async (it) => {
    setBusyId(it.key);
    try {
      if (it.kind === 'cancel')        await approveCancel(it.id);
      else if (it.kind === 'leave')    await approveLeave(it.id);
      else if (it.kind === 'compoff') { await leaveApi.compOffApprove(it.id); await refreshAux(); }
      else if (it.kind === 'regular') { await regularization.review(it.id, { status: 'approved', review_comment: null }); await refreshAux(); }
      flash('emerald', `${it.id} approved`);
    } catch (e) { flash('rose', e?.data?.detail || 'Approve failed'); }
    finally { setBusyId(null); }
  };
  const onReject = async (it) => {
    setBusyId(it.key);
    try {
      const reason = window.prompt('Reason for rejection (optional)?') || '';
      if (it.kind === 'cancel' || it.kind === 'leave') await rejectLeave(it.id, reason);
      else if (it.kind === 'compoff') { await leaveApi.compOffReject(it.id, reason); await refreshAux(); }
      else if (it.kind === 'regular') { await regularization.review(it.id, { status: 'rejected', review_comment: reason || null }); await refreshAux(); }
      flash('rose', `${it.id} rejected`);
    } catch (e) { flash('rose', e?.data?.detail || 'Reject failed'); }
    finally { setBusyId(null); }
  };

  const error = leaveErr || auxErr;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#0F172A' }}>Approvals</h1>
          <p style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>HR-stage queue: leave, cancellations, comp-off, and regularizations awaiting your decision.</p>
        </div>
      </div>

      {toast && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, fontSize: 13, marginBottom: 14,
          background: toast.tone === 'emerald' ? '#ECFDF5' : '#FEE2E2',
          color: toast.tone === 'emerald' ? '#065F46' : '#991B1B',
          border: `1px solid ${toast.tone === 'emerald' ? '#A7F3D0' : '#FECACA'}`,
        }}>{toast.message}</div>
      )}
      {error && (
        <div style={{ padding: 12, borderRadius: 8, background: '#FEE2E2', color: '#991B1B', fontSize: 13, marginBottom: 14 }}>{error}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 20 }}>
        {[
          ['All Pending',    allCount,        C.blue],
          ['Leave',          counts.leave,    C.yellow],
          ['Cancellations',  counts.cancel,   C.red],
          ['Comp-Off',       counts.compoff,  C.violet],
          ['Regularization', counts.regular,  C.primary],
        ].map(([l, v, c]) => (
          <div key={l} style={{ background: 'var(--hrms-surface)', border: `1px solid ${C.border}`, borderRadius: 12, padding: 14, textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: c }}>{v}</div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{l}</div>
          </div>
        ))}
      </div>

      <div style={{ background: 'var(--hrms-surface)', border: `1px solid ${C.border}`, borderRadius: 12, padding: 18 }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 18, borderBottom: `1px solid ${C.border}`, paddingBottom: 10, flexWrap: 'wrap' }}>
          {TABS.map((t) => {
            const count = t.key === 'all' ? allCount : counts[t.key];
            return (
              <button key={t.key} onClick={() => setTab(t.key)}
                style={{
                  padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                  background: tab === t.key ? C.primary : 'transparent',
                  color: tab === t.key ? '#fff' : C.muted,
                  fontSize: 12, fontWeight: tab === t.key ? 600 : 400,
                }}>
                {t.label} ({count})
              </button>
            );
          })}
        </div>

        {!leaveLoading && visible.length === 0 && (
          <div style={{ padding: '40px 0', textAlign: 'center', color: C.muted, fontSize: 13 }}>
            No HR-stage approvals waiting on you. 🎉
          </div>
        )}

        {visible.map((it) => {
          const isCancel = it.kind === 'cancel';
          return (
            <div key={it.key} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 0', borderBottom: `1px solid ${C.border}` }}>
              <Av init={initialsOf(it.name)} size={42} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: '#0F172A' }}>
                  {it.name}
                  {isCancel && <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: C.red, background: '#FEE2E2', padding: '2px 6px', borderRadius: 4 }}>CANCELLATION</span>}
                  {it.kind === 'compoff' && <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: '#6D28D9', background: '#EDE9FE', padding: '2px 6px', borderRadius: 4 }}>COMP-OFF</span>}
                  {it.kind === 'regular' && <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: '#047857', background: '#D1FAE5', padding: '2px 6px', borderRadius: 4 }}>REGULARIZATION</span>}
                </div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{it.primary} · {it.secondary}</div>
                {it.reason && <div style={{ fontSize: 11, color: C.muted, marginTop: 4, fontStyle: 'italic' }}>"{it.reason}"</div>}
              </div>
              <span style={{ fontSize: 12, color: C.muted, marginRight: 8 }}>{timeAgo(it.created_at)}</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button disabled={busyId === it.key} onClick={() => onReject(it)}
                  style={{ padding: '6px 14px', borderRadius: 6, background: '#FEE2E2', color: C.red, border: '1px solid #FECACA', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: busyId === it.key ? 0.5 : 1 }}>
                  Reject
                </button>
                <button disabled={busyId === it.key} onClick={() => onApprove(it)}
                  style={{ padding: '6px 14px', borderRadius: 6, background: C.primary, color: '#fff', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: busyId === it.key ? 0.5 : 1 }}>
                  {isCancel ? 'Approve Cancel' : 'Approve'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
