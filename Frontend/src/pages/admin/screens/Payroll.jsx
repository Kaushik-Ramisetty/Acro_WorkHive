import { formatINR, formatUsdAsInr, usdToInr } from '../../../utils/formatCurrency';
import { useState } from 'react'

const PAYROLL_DATA = [
  { name: 'Sarah Jenkins', role: 'UX Designer', dept: 'Product', gross: 8500, deductions: 1200, net: 7300, status: 'Processed', initials: 'SJ', color: '#6366F1' },
  { name: 'Michael Chen', role: 'Data Analyst', dept: 'Analytics', gross: 9200, deductions: 1380, net: 7820, status: 'Processed', initials: 'MC', color: '#10B981' },
  { name: 'Emma Thompson', role: 'HR Manager', dept: 'HR', gross: 10000, deductions: 1600, net: 8400, status: 'Pending', initials: 'ET', color: '#F59E0B' },
  { name: 'James Wilson', role: 'Backend Engineer', dept: 'Engineering', gross: 12500, deductions: 2100, net: 10400, status: 'Processed', initials: 'JW', color: '#3B5BDB' },
  { name: 'Priya Nair', role: 'Product Manager', dept: 'Product', gross: 11000, deductions: 1800, net: 9200, status: 'On Hold', initials: 'PN', color: '#EF4444' },
  { name: 'David Park', role: 'DevOps Engineer', dept: 'Engineering', gross: 11800, deductions: 1950, net: 9850, status: 'Processed', initials: 'DP', color: '#8B5CF6' },
]

export default function Payroll() {
  const [month, setMonth] = useState('April 2026')

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Payroll</h1>
          <p>Manage monthly payroll processing and disbursements</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <select value={month} onChange={e => setMonth(e.target.value)} style={{ width: 160 }}>
            <option>April 2026</option><option>March 2026</option><option>February 2026</option>
          </select>
          <button className="btn btn-primary">Run Payroll</button>
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Total Gross', value: formatUsdAsInr('$4.2M'), sub: 'This month', color: '#3B5BDB', bg: '#EEF2FF' },
          { label: 'Total Deductions', value: formatUsdAsInr('$680K'), sub: 'Tax & benefits', color: '#EF4444', bg: '#FEE2E2' },
          { label: 'Net Disbursement', value: formatUsdAsInr('$3.52M'), sub: 'To employees', color: '#10B981', bg: '#D1FAE5' },
          { label: 'Pending Approvals', value: '3', sub: 'Require action', color: '#F59E0B', bg: '#FEF3C7' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: s.color, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Progress */}
      <div className="card" style={{ padding: '20px 24px', marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Budget Utilization</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--blue-bright)' }}>95%</span>
        </div>
        <div style={{ height: 8, background: '#E5E7EB', borderRadius: 99 }}>
          <div style={{ height: '100%', width: '95%', background: 'linear-gradient(90deg,#3B5BDB,#06B6D4)', borderRadius: 99 }} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--accent-orange)', marginTop: 8 }}>⚠ Approaching monthly threshold — final approvals required by EOD</div>
      </div>

      {/* Table */}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Department</th>
              <th>Gross Pay</th>
              <th>Deductions</th>
              <th>Net Pay</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {PAYROLL_DATA.map((p, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: p.color, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{p.initials}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{p.role}</div>
                    </div>
                  </div>
                </td>
                <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{p.dept}</td>
                <td style={{ fontWeight: 600 }}>{formatINR(usdToInr(p.gross))}</td>
                <td style={{ color: 'var(--accent-red)' }}>{formatINR(usdToInr(p.deductions))}</td>
                <td style={{ fontWeight: 700, color: '#10B981' }}>{formatINR(usdToInr(p.net))}</td>
                <td>
                  <span className={`badge ${p.status === 'Processed' ? 'badge-green' : p.status === 'Pending' ? 'badge-orange' : 'badge-red'}`}>{p.status}</span>
                </td>
                <td>
                  <button className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 12 }}>View Slip</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
