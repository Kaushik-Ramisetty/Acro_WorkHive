import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { leaveApi } from '../../../services/leave';

const C = {
  primary: '#10B981', yellow: '#F59E0B', red: '#EF4444', blue: '#1D4ED8',
  text: 'var(--hrms-text)', text2: 'var(--hrms-text-2)',
  muted: 'var(--hrms-text-muted)', border: 'var(--hrms-border)',
  light: 'var(--hrms-surface-2)', surface: 'var(--hrms-surface)',
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

function fmt(iso) {
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
  const d = Math.floor(h / 24);
  return d + 'd ago';
}

const STATUS_TONE = {
  pending:  ['#FEF3C7', '#92400E', 'Pending'],
  approved: ['#D1FAE5', '#065F46', 'Approved'],
  rejected: ['#FEE2E2', '#991B1B', 'Rejected'],
  expired:  ['#E2E8F0', '#475569', 'Expired'],
  used:     ['#DBEAFE', '#1E40AF', 'Used'],
};

// Self-request modal — lets the manager submit a comp-off for themselves.
// Same payload shape as the employee CompOffPage form; backend grants comp-off
// to whichever employee_id is supplied (managers can grant to themselves).
function RequestCompOffModal({ open, onClose, onSubmit }) {
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
    <div
      onClick={onClose}
      style={{ position:'fixed', inset:0, background:'rgba(15,28,46,0.55)', backdropFilter:'blur(3px)', zIndex:50, display:'flex', alignItems:'center', justifyContent:'center' }}
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        style={{ background:C.surface, borderRadius:16, width:'100%', maxWidth:520, margin:'0 16px', boxShadow:'0 20px 50px rgba(15,23,42,0.25)', overflow:'hidden' }}
      >
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'18px 22px', borderBottom:`1px solid ${C.border}` }}>
          <div>
            <h2 style={{ margin:0, fontSize:16, fontWeight:700, color:C.text }}>Request Comp-Off</h2>
            <p style={{ margin:'4px 0 0', fontSize:12, color:C.muted }}>For days you worked on a holiday or weekend.</p>
          </div>
          <button type="button" onClick={onClose} style={{ width:32, height:32, borderRadius:'50%', background:C.light, border:'none', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.muted} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div style={{ padding:'20px 22px', display:'flex', flexDirection:'column', gap:14 }}>
          <div style={{ background:'#F0FDFA', border:'1px solid #99F6E4', borderRadius:8, padding:'10px 14px', fontSize:12, color:'#0F766E' }}>
            Your request will be sent to HR for approval (you don't need a manager approval since you are one).
            Once approved, the days are added to your Compensatory_leave balance.
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
            <div>
              <label style={{ display:'block', fontSize:11, fontWeight:700, color:C.muted, marginBottom:6 }}>Worked On *</label>
              <input
                type="date" required max={today}
                value={form.worked_on} onChange={(e) => set({ worked_on: e.target.value })}
                style={{ width:'100%', padding:'9px 12px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', background:C.surface, color:C.text }}
              />
            </div>
            <div>
              <label style={{ display:'block', fontSize:11, fontWeight:700, color:C.muted, marginBottom:6 }}>Days *</label>
              <input
                type="number" required min="1" max="5"
                value={form.days} onChange={(e) => set({ days: e.target.value })}
                style={{ width:'100%', padding:'9px 12px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', background:C.surface, color:C.text }}
              />
            </div>
          </div>

          <div>
            <label style={{ display:'block', fontSize:11, fontWeight:700, color:C.muted, marginBottom:6 }}>Reason *</label>
            <textarea
              required rows={3}
              value={form.reason} onChange={(e) => set({ reason: e.target.value })}
              placeholder="Why you're requesting comp-off (e.g. Worked on the Diwali holiday)…"
              style={{ width:'100%', padding:'9px 12px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', resize:'vertical', background:C.surface, color:C.text }}
            />
          </div>

          <div>
            <label style={{ display:'block', fontSize:11, fontWeight:700, color:C.muted, marginBottom:6 }}>Proof URL (optional)</label>
            <input
              type="url"
              value={form.proof_url} onChange={(e) => set({ proof_url: e.target.value })}
              placeholder="https://… (link to commit, jira ticket, anything)"
              style={{ width:'100%', padding:'9px 12px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', background:C.surface, color:C.text }}
            />
          </div>

          {err && <p style={{ margin:0, padding:'8px 12px', borderRadius:6, background:'#FEE2E2', color:'#991B1B', fontSize:12, fontWeight:600 }}>{err}</p>}
        </div>

        <div style={{ display:'flex', gap:10, padding:'14px 22px', borderTop:`1px solid ${C.border}` }}>
          <button
            type="button" onClick={onClose} disabled={busy}
            style={{ flex:1, padding:'10px 0', borderRadius:8, border:`1px solid ${C.border}`, background:C.surface, color:C.text2, fontSize:13, fontWeight:600, cursor:'pointer', opacity:busy?0.6:1 }}
          >Cancel</button>
          <button
            type="submit" disabled={busy}
            style={{ flex:1, padding:'10px 0', borderRadius:8, border:'none', background:C.primary, color:'#fff', fontSize:13, fontWeight:600, cursor:'pointer', opacity:busy?0.6:1 }}
          >{busy ? 'Submitting…' : 'Submit Request'}</button>
        </div>
      </form>
    </div>
  );
}

export default function ManagerCompOffPage() {
  const { user } = useAuth();
  const [credits, setCredits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [tab, setTab] = useState('pending'); // pending | all
  const [requestOpen, setRequestOpen] = useState(false);

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

  // Pending tab: only credits awaiting THIS manager (next_approver_role === 'manager').
  // The /leave/comp-off/list endpoint already scopes by role to direct reports.
  const visible = useMemo(() => {
    if (tab === 'pending') {
      return credits.filter((c) => c.status === 'pending' && c.next_approver_role === 'manager');
    }
    return credits;
  }, [credits, tab]);

  const counts = useMemo(() => ({
    awaitingMe: credits.filter((c) => c.status === 'pending' && c.next_approver_role === 'manager').length,
    awaitingHr: credits.filter((c) => c.status === 'pending' && c.next_approver_role === 'hr').length,
    approved:   credits.filter((c) => c.status === 'approved').length,
    rejected:   credits.filter((c) => c.status === 'rejected').length,
  }), [credits]);

  const onApprove = async (c) => {
    setBusyId(c.id);
    try { await leaveApi.compOffApprove(c.id); await load(); }
    catch (e) { alert(e?.data?.detail || 'Approve failed'); }
    finally { setBusyId(null); }
  };
  const onReject = async (c) => {
    const reason = window.prompt('Reason for rejection (optional)?') || '';
    setBusyId(c.id);
    try { await leaveApi.compOffReject(c.id, reason); await load(); }
    catch (e) { alert(e?.data?.detail || 'Reject failed'); }
    finally { setBusyId(null); }
  };

  // Manager self-request: post the form using the manager's own employee id.
  const onSubmitRequest = async (form) => {
    await leaveApi.compOffGrant({ employee_id: user.id, ...form });
    await load();
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, gap: 14, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text }}>Comp-Off</h1>
          <p style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>Review your team's comp-off requests, or submit your own.</p>
        </div>
        <button
          type="button"
          onClick={() => setRequestOpen(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 16px', borderRadius: 8,
            background: C.primary, color: '#fff',
            border: 'none', cursor: 'pointer',
            fontSize: 13, fontWeight: 600,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5"  y1="12" x2="19" y2="12" />
          </svg>
          Request Comp-Off
        </button>
      </div>

      <RequestCompOffModal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        onSubmit={onSubmitRequest}
      />

      {error && (
        <div style={{ padding: 12, borderRadius: 8, background: '#FEE2E2', color: '#991B1B', fontSize: 13, marginBottom: 14 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
        {[
          ['Awaiting Me',   counts.awaitingMe, C.yellow],
          ['Awaiting HR',   counts.awaitingHr, C.blue],
          ['Approved',      counts.approved,   C.primary],
          ['Rejected',      counts.rejected,   C.red],
        ].map(([l, v, c]) => (
          <div key={l} style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14, textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: c }}>{v}</div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{l}</div>
          </div>
        ))}
      </div>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 18 }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 18, borderBottom: `1px solid ${C.border}`, paddingBottom: 10 }}>
          {['pending', 'all'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              style={{
                padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                background: tab === t ? C.primary : 'transparent',
                color: tab === t ? '#fff' : C.muted,
                fontSize: 12, fontWeight: tab === t ? 600 : 400, textTransform: 'capitalize',
              }}>
              {t === 'pending' ? `Awaiting me (${counts.awaitingMe})` : `All team (${credits.length})`}
            </button>
          ))}
        </div>

        {!loading && visible.length === 0 && (
          <div style={{ padding: '40px 0', textAlign: 'center', color: C.muted, fontSize: 13 }}>
            {tab === 'pending' ? 'No comp-off requests waiting on you. 🎉' : 'No comp-off requests from your team.'}
          </div>
        )}

        {visible.map((c) => {
          const initials = (c.employee_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
          const tone = STATUS_TONE[c.status] || ['#E2E8F0', '#475569', c.status];
          const showActions = c.status === 'pending' && c.next_approver_role === 'manager';
          return (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 0', borderBottom: `1px solid ${C.border}` }}>
              <Av init={initials} size={42} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: C.text }}>
                  {c.employee_name}
                  <span style={{
                    marginLeft: 8, fontSize: 10, fontWeight: 700, padding: '2px 8px',
                    borderRadius: 4, background: tone[0], color: tone[1],
                  }}>{tone[2].toUpperCase()}</span>
                </div>
                <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>
                  {c.days} day{c.days !== 1 ? 's' : ''} · worked on {fmt(c.worked_on)} · expires {fmt(c.expires_on)}
                </div>
                {c.reason && <div style={{ fontSize: 11, color: C.muted, marginTop: 4, fontStyle: 'italic' }}>"{c.reason}"</div>}
                {c.proof_url && (
                  <div style={{ marginTop: 4 }}>
                    <a href={c.proof_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: C.blue, textDecoration: 'underline' }}>View proof</a>
                  </div>
                )}
              </div>
              <span style={{ fontSize: 12, color: C.muted, marginRight: 8 }}>{timeAgo(c.created_at)}</span>
              {showActions ? (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button disabled={busyId === c.id} onClick={() => onReject(c)}
                    style={{ padding: '6px 14px', borderRadius: 6, background: '#FEE2E2', color: C.red, border: '1px solid #FECACA', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: busyId === c.id ? 0.5 : 1 }}>
                    Reject
                  </button>
                  <button disabled={busyId === c.id} onClick={() => onApprove(c)}
                    style={{ padding: '6px 14px', borderRadius: 6, background: C.primary, color: '#fff', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: busyId === c.id ? 0.5 : 1 }}>
                    Approve
                  </button>
                </div>
              ) : (
                <span style={{ fontSize: 11, color: C.muted, fontStyle: 'italic' }}>
                  {c.status === 'pending' ? 'Awaiting HR' : ''}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
