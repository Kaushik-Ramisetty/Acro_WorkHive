import { formatINR, formatUsdAsInr, usdToInr } from '../../../utils/formatCurrency';
import { useState } from 'react'

const CLAIMS = [
  { id: 'CLM-001', name: 'Sarah Jenkins', type: 'Medical Reimbursement', usd: 420.00, submitted: '2026-04-22', status: 'Pending', initials: 'SJ', color: '#6366F1', desc: 'Annual health checkup and medication costs' },
  { id: 'CLM-002', name: 'Michael Chen', type: 'Travel Expenses', usd: 1250.50, submitted: '2026-04-20', status: 'Pending', initials: 'MC', color: '#10B981', desc: 'Client visit to Mumbai - flights and hotel' },
  { id: 'CLM-003', name: 'Emma Thompson', type: 'Equipment', usd: 2100.00, submitted: '2026-04-18', status: 'Approved', initials: 'ET', color: '#F59E0B', desc: 'Standing desk and ergonomic chair' },
  { id: 'CLM-004', name: 'James Wilson', type: 'Training & Certification', usd: 750.00, submitted: '2026-04-15', status: 'Approved', initials: 'JW', color: '#3B5BDB', desc: 'AWS Solutions Architect certification fee' },
  { id: 'CLM-005', name: 'David Park', type: 'Internet & Utilities', usd: 180.00, submitted: '2026-04-12', status: 'Rejected', initials: 'DP', color: '#8B5CF6', desc: 'Home internet allowance - Q1 2026' },
  { id: 'CLM-006', name: 'Anjali Mehta', type: 'Conference', usd: 3200.00, submitted: '2026-04-10', status: 'Pending', initials: 'AM', color: '#06B6D4', desc: 'Marketing Summit 2026 registration and travel' },
]

export default function Claims() {
  const [filter, setFilter] = useState('All')
  const [showModal, setShowModal] = useState(false)

  const filtered = filter === 'All' ? CLAIMS : CLAIMS.filter(c => c.status === filter)

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Claims</h1>
          <p>Review and manage employee expense claims</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ New Claim</button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Pending', value: 8, color: '#F59E0B', bg: '#FEF3C7' },
          { label: 'Approved', value: 24, color: '#10B981', bg: '#D1FAE5' },
          { label: 'Rejected', value: 3, color: '#EF4444', bg: '#FEE2E2' },
          { label: 'Total Value', value: formatUsdAsInr('$28.4K'), color: '#3B5BDB', bg: '#EEF2FF' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 44, height: 44, borderRadius: 10, background: s.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700, color: s.color }}>{typeof s.value === 'number' ? s.value : ''}</div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['All', 'Pending', 'Approved', 'Rejected'].map(f => (
          <button key={f} onClick={() => setFilter(f)} className="btn" style={{ padding: '7px 18px', fontSize: 13, background: filter === f ? 'var(--blue-bright)' : '#fff', color: filter === f ? '#fff' : 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {f}
          </button>
        ))}
      </div>

      <div className="card">
        <table>
          <thead>
            <tr><th>Claim ID</th><th>Employee</th><th>Type</th><th>Description</th><th>Amount</th><th>Submitted</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {filtered.map((c, i) => (
              <tr key={i}>
                <td style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{c.id}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 30, height: 30, borderRadius: '50%', background: c.color, color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{c.initials}</div>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{c.name}</span>
                  </div>
                </td>
                <td><span className="badge badge-blue" style={{ fontSize: 11 }}>{c.type}</span></td>
                <td style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 180 }}>{c.desc}</td>
                <td style={{ fontWeight: 700 }}>{formatINR(usdToInr(c.usd))}</td>
                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.submitted}</td>
                <td><span className={`badge ${c.status === 'Approved' ? 'badge-green' : c.status === 'Pending' ? 'badge-orange' : 'badge-red'}`}>{c.status}</span></td>
                <td>
                  {c.status === 'Pending' ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: 11 }}>Approve</button>
                      <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--accent-red)' }}>Reject</button>
                    </div>
                  ) : (
                    <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}>View</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card fade-in" style={{ width: 480, padding: 32 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700 }}>Submit New Claim</h2>
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => setShowModal(false)}>✕</button>
            </div>
            <div className="form-group"><label>Claim Type</label><select><option>Medical Reimbursement</option><option>Travel Expenses</option><option>Equipment</option><option>Training & Certification</option><option>Conference</option><option>Internet & Utilities</option></select></div>
            <div className="form-group"><label>Amount</label><input type="number" placeholder="0.00" /></div>
            <div className="form-group"><label>Description</label><textarea rows={3} placeholder="Brief description of the expense..." style={{ resize: 'vertical' }} /></div>
            <div className="form-group"><label>Date of Expense</label><input type="date" /></div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn btn-outline" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setShowModal(false)}>Submit Claim</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
