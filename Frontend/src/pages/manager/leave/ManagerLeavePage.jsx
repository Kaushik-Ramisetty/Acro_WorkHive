import { useMemo, useState } from 'react';
import { useLeaveData } from '../../../hooks/useLeaveData';
import LeaveModal from '../../../components/LeaveModal';
import MyLeavePanel from '../../../components/MyLeavePanel';
import { useAuth } from '../../../context/AuthContext';
import ManagerCompOffPage from '../compoff/ManagerCompOffPage';

function fmt(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

function StatusBadge({ status }) {
  const tone = {
    pending:        ['#FEF3C7', '#92400E', 'Pending'],
    cancel_pending: ['#FEF3C7', '#92400E', 'Cancel Pending'],
    approved:       ['#D1FAE5', '#065F46', 'Approved'],
    rejected:       ['#FEE2E2', '#991B1B', 'Rejected'],
    cancelled:      ['#E2E8F0', '#475569', 'Cancelled'],
    consumed:       ['#DBEAFE', '#1E40AF', 'Consumed'],
  }[status] || ['#E2E8F0', '#475569', status];
  return (
    <span style={{ background: tone[0], color: tone[1], padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
      {tone[2]}
    </span>
  );
}

export default function ManagerLeavePage() {
  const { user } = useAuth();
  const { requests, loading, error, refresh, approve, reject, approveCancel, cancel } = useLeaveData({});
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState('all'); // all | pending | approved | rejected
  // Sub-section: 'leave' (default) or 'compoff' -- Comp-Off used to be a
  // separate sidebar page; it now lives inside this Leave page as a tab.
  const [section, setSection] = useState('leave');
  // Note: Apply Leave + WFH are no longer modal buttons on this page. Apply
  // Leave lives as a sub-section tab below; WFH moved to the Quick Actions
  // panel on the manager dashboard home (see ManagerDashboard.jsx).

  const visible = useMemo(() => {
    return requests.filter((r) => {
      if (tab === 'pending') return r.status === 'pending' || r.status === 'cancel_pending';
      if (tab === 'approved') return r.status === 'approved';
      if (tab === 'rejected') return r.status === 'rejected';
      return true;
    });
  }, [requests, tab]);

  const counts = useMemo(() => ({
    total: requests.length,
    pending: requests.filter((r) => r.status === 'pending' || r.status === 'cancel_pending').length,
    approved: requests.filter((r) => r.status === 'approved').length,
    rejected: requests.filter((r) => r.status === 'rejected').length,
  }), [requests]);

  const onApprove = async (r) => {
    try {
      if (r.status === 'cancel_pending') await approveCancel(r.id);
      else await approve(r.id);
    } catch (e) { alert(e?.data?.detail || 'Failed'); }
  };
  const onReject = async (r, reason) => {
    try { await reject(r.id, reason); }
    catch (e) { alert(e?.data?.detail || 'Failed'); }
  };

  const C = {
    primary: '#10B981',
    yellow: '#F59E0B',
    red: '#EF4444',
    blue: '#1D4ED8',
    text: 'var(--hrms-text)',
    text2: 'var(--hrms-text-2)',
    muted: 'var(--hrms-text-muted)',
    border: 'var(--hrms-border)',
    light: 'var(--hrms-surface-2)',
    surface: 'var(--hrms-surface)',
  };

  const selectedFull = selected ? requests.find((x) => x.id === selected.id) || selected : null;
  const isMineSelected = selectedFull ? selectedFull.employee_id === user?.id : false;
  const capabilities = selectedFull ? {
    canApprove: !isMineSelected && selectedFull.status === 'pending',
    canReject: !isMineSelected && selectedFull.status === 'pending',
    canApproveCancel: !isMineSelected && selectedFull.status === 'cancel_pending',
    canCancel: false,
  } : {};

  // Tab strip rendered above whichever section is active.
  const SectionTabs = (
    <div style={{ display: 'flex', gap: 8, marginBottom: 18, borderBottom: `1px solid ${C.border}`, paddingBottom: 8 }}>
      {[
        { id: 'leave',   label: 'Leave Requests' },
        { id: 'apply',   label: 'Apply Leave' },
        { id: 'compoff', label: 'Comp-Off' },
      ].map((t) => {
        const active = section === t.id;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => setSection(t.id)}
            style={{
              padding: '6px 14px', borderRadius: 8, border: 'none',
              background: active ? '#1e3acb' : 'transparent',
              color: active ? '#fff' : C.text2,
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );

  if (section === 'compoff') {
    return (
      <div>
        {SectionTabs}
        <ManagerCompOffPage />
      </div>
    );
  }

  if (section === 'apply') {
    return (
      <div>
        {SectionTabs}
        <MyLeavePanel />
      </div>
    );
  }

  return (
    <div>
      {SectionTabs}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text }}>Leave Requests</h1>
          <p style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>Manage team leave applications</p>
        </div>
        {/* Apply Leave moved to its own sub-section tab; WFH lives on the
            dashboard's Quick Actions panel. */}
      </div>

      {/* stat strip */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
        {[
          ['Total', counts.total, C.blue],
          ['Pending', counts.pending, C.yellow],
          ['Approved', counts.approved, C.primary],
          ['Rejected', counts.rejected, C.red],
        ].map(([l, v, c]) => (
          <div key={l} style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14, textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: c }}>{v}</div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{l}</div>
          </div>
        ))}
      </div>

      {error && (
        <div style={{ background: '#FEE2E2', border: '1px solid #FCA5A5', color: '#991B1B', padding: 10, borderRadius: 8, fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ display: 'flex', gap: 4, padding: '14px 18px', borderBottom: `1px solid ${C.border}` }}>
          {['all', 'pending', 'approved', 'rejected'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              style={{
                padding: '6px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                background: tab === t ? C.primary : 'transparent',
                color: tab === t ? '#fff' : C.muted,
                fontSize: 12, fontWeight: tab === t ? 600 : 400, textTransform: 'capitalize',
              }}>
              {t}
            </button>
          ))}
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: C.light }}>
              {['Employee', 'Type', 'Duration', 'Days', 'Reason', 'Status', 'Actions'].map((h) => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: C.muted, textTransform: 'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!loading && visible.length === 0 && (
              <tr><td colSpan="7" style={{ padding: 30, textAlign: 'center', color: C.muted, fontSize: 13 }}>
                No leave requests in this view.
              </td></tr>
            )}
            {visible.map((r) => (
              <tr key={r.id}
                onClick={() => setSelected(r)}
                style={{ borderTop: `1px solid ${C.border}`, cursor: 'pointer' }}>
                <td style={{ padding: '12px 14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'linear-gradient(135deg,#3B82F6,#6366F1)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>
                      {(r.employee_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{r.employee_name}</div>
                      {r.employee_code && <div style={{ fontSize: 10, color: C.muted }}>{r.employee_code}</div>}
                    </div>
                  </div>
                </td>
                <td style={{ padding: '12px 14px', fontSize: 12, color: C.text }}>{r.leave_type_name}</td>
                <td style={{ padding: '12px 14px', fontSize: 12, color: C.muted }}>{fmt(r.start_date)} → {fmt(r.end_date)}</td>
                <td style={{ padding: '12px 14px', fontSize: 12, fontWeight: 700, color: C.text }}>{r.total_days}d</td>
                <td style={{ padding: '12px 14px', fontSize: 12, color: C.muted, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.reason || '—'}</td>
                <td style={{ padding: '12px 14px' }}><StatusBadge status={r.status} /></td>
                <td style={{ padding: '12px 14px' }} onClick={(e) => e.stopPropagation()}>
                  {(r.status === 'pending' || r.status === 'cancel_pending') ? (
                    r.next_approver_role === 'manager' ? (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => onApprove(r)}
                          style={{ padding: '4px 10px', borderRadius: 6, background: C.primary, color: '#fff', border: 'none', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>
                          {r.status === 'cancel_pending' ? 'Approve Cancel' : 'Approve'}
                        </button>
                        <button onClick={() => onReject(r, '')}
                          style={{ padding: '4px 10px', borderRadius: 6, background: '#FEE2E2', color: C.red, border: '1px solid #FECACA', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>
                          Reject
                        </button>
                      </div>
                    ) : (
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#92400E', background: '#FEF3C7', padding: '2px 8px', borderRadius: 4 }}>
                        Awaiting HR
                      </span>
                    )
                  ) : (
                    <span style={{ fontSize: 11, color: C.muted }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>        </table>
      </div>

      <LeaveModal
        open={!!selected}
        leave={selectedFull}
        capabilities={capabilities}
        onClose={() => setSelected(null)}
        onApprove={onApprove}
        onReject={onReject}
        onCancel={() => {}}
        onApproveCancel={(r) => onApprove(r)}
      />
    </div>
  );
}
