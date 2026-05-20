import { formatUsdAsInr } from '../../../utils/formatCurrency';
import { useEffect, useState } from 'react'
import { leaveApi } from '../../../services/leave';

const SERVICES = [
  { icon: '📋', title: 'Leave Request', desc: 'Apply for annual, sick or emergency leave', action: 'Apply Now', color: '#3B5BDB' },
  { icon: '💰', title: 'Salary Slip', desc: 'Download monthly payslips and tax documents', action: 'Download', color: '#10B981' },
  { icon: '🏥', title: 'Benefits Portal', desc: 'Manage health, dental and life insurance', action: 'View Benefits', color: '#8B5CF6' },
  { icon: '📝', title: 'Self Assessment', desc: 'Complete your Q3 performance self-review', action: 'Start Review', color: '#F59E0B' },
  { icon: '🎓', title: 'Learning & Dev', desc: 'Access training programs and certifications', action: 'Browse Courses', color: '#06B6D4' },
  { icon: '🧾', title: 'Submit Claim', desc: 'Reimburse work-related expenses quickly', action: 'Submit', color: '#EF4444' },
]

// Per-leave-type accent colour. Live balances come from /leave/balance/me — see
// the useEffect inside SelfServices(). The static array used to be hard-coded.
const LEAVE_TYPE_COLOR = {
  'Annual Leave':       '#3B5BDB',
  'Casual Leave':       '#F97316',
  'Sick Leave':         '#10B981',
  'Earned Leave':       '#10B981',
  'Paid Leaves':        '#10B981',
  'Compensatory_leave': '#EAB308',
  'Maternity Leave':    '#EC4899',
  'Paternity Leave':    '#8B5CF6',
  'Menstrual Leave':    '#F43F5E',
};
function ssColor(name) { return LEAVE_TYPE_COLOR[name] || '#3B5BDB'; }
function ssLabel(name) {
  if (!name) return '';
  if (name === 'LOP_leaves')         return 'LOPs';
  if (name === 'Compensatory_leave') return 'Comp-Off';
  return String(name).replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const RECENT_ACTIVITY = [
  { action: 'Leave approved', detail: '2 days Annual Leave — Apr 28-29', time: '1 hour ago', icon: '✅' },
  { action: 'Payslip available', detail: 'March 2026 salary slip', time: 'Yesterday', icon: '💰' },
  { action: 'Claim submitted', detail: 'Medical Reimbursement ' + formatUsdAsInr('$420'), time: '3 days ago', icon: '🧾' },
]

export default function SelfServices() {
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  // Live leave balances pulled from /leave/balance/me. Replaces the previous
  // hard-coded mock array.
  const [balances, setBalances] = useState([])
  const [balancesLoading, setBalancesLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    leaveApi.myBalance()
      .then((rows) => {
        if (cancelled) return
        const arr = Array.isArray(rows) ? rows : []
        setBalances(arr.filter((b) => (b.opening_balance || 0) > 0))
      })
      .catch(() => { if (!cancelled) setBalances([]) })
      .finally(() => { if (!cancelled) setBalancesLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Self Services</h1>
        <p>Your personal HR portal — manage leave, benefits and more</p>
      </div>

      {/* Leave Balance */}
      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Leave Balance</h3>
        {balancesLoading && (
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading…</div>
        )}
        {!balancesLoading && balances.length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            No leave balances configured for this year.
          </div>
        )}
        {!balancesLoading && balances.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
            {balances.map((b) => {
              const total = b.opening_balance || 0
              const used  = b.used || 0
              const pct   = total > 0 ? Math.min(100, (used / total) * 100) : 0
              const color = ssColor(b.leave_type_name)
              const remaining = Math.max(0, total - used)
              return (
                <div key={b.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{ssLabel(b.leave_type_name)}</span>
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{used}/{total} days</span>
                  </div>
                  <div style={{ height: 8, background: '#E5E7EB', borderRadius: 99 }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 99 }} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{remaining} days remaining</div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Quick Services Grid */}
      <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Quick Actions</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginBottom: 24 }}>
        {SERVICES.map((s, i) => (
          <div key={i} className="card" style={{ padding: 20, cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
            onMouseLeave={e => e.currentTarget.style.transform = 'none'}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>{s.icon}</div>
            <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{s.title}</h4>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.5 }}>{s.desc}</p>
            <button className="btn" style={{ background: `${s.color}15`, color: s.color, border: `1px solid ${s.color}30`, fontSize: 12, padding: '6px 14px' }}
              onClick={() => s.title === 'Leave Request' && setShowLeaveModal(true)}>
              {s.action}
            </button>
          </div>
        ))}
      </div>

      {/* Recent Activity */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Recent Activity</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {RECENT_ACTIVITY.map((a, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--bg-main)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>{a.icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{a.action}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{a.detail}</div>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{a.time}</span>
            </div>
          ))}
        </div>
      </div>

      {showLeaveModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card fade-in" style={{ width: 460, padding: 32 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700 }}>Apply for Leave</h2>
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => setShowLeaveModal(false)}>✕</button>
            </div>
            <div className="form-group"><label>Leave Type</label><select><option>Annual Leave</option><option>Sick Leave</option><option>Emergency Leave</option></select></div>
            <div className="form-row">
              <div className="form-group"><label>From Date</label><input type="date" /></div>
              <div className="form-group"><label>To Date</label><input type="date" /></div>
            </div>
            <div className="form-group"><label>Reason</label><textarea rows={3} placeholder="Briefly describe the reason..." style={{ resize: 'vertical' }} /></div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-outline" onClick={() => setShowLeaveModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setShowLeaveModal(false)}>Submit Request</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
