import { useState } from 'react'

const REPORTS = [
  { title: 'Monthly Headcount Report', category: 'HR', date: '2026-04-01', format: 'PDF', size: '2.4 MB' },
  { title: 'Q1 Payroll Summary', category: 'Payroll', date: '2026-04-05', format: 'Excel', size: '1.8 MB' },
  { title: 'Attendance Overview - April', category: 'Attendance', date: '2026-04-22', format: 'PDF', size: '890 KB' },
  { title: 'Recruitment Pipeline Report', category: 'Recruitment', date: '2026-04-18', format: 'PDF', size: '1.2 MB' },
  { title: 'Performance Review Cycle Q3', category: 'Performance', date: '2026-04-15', format: 'Excel', size: '3.1 MB' },
  { title: 'Claims & Reimbursements Log', category: 'Claims', date: '2026-04-20', format: 'PDF', size: '560 KB' },
]

const METRICS = [
  { label: 'Employee Turnover', value: '4.2%', change: '-1.1%', positive: true },
  { label: 'Avg Time to Hire', value: '18 days', change: '-3 days', positive: true },
  { label: 'Training Completion', value: '78%', change: '+12%', positive: true },
  { label: 'Benefits Utilization', value: '62%', change: '-4%', positive: false },
]

export default function Reports() {
  const [activeCategory, setActiveCategory] = useState('All')
  const categories = ['All', 'HR', 'Payroll', 'Attendance', 'Recruitment', 'Performance', 'Claims']
  const filtered = activeCategory === 'All' ? REPORTS : REPORTS.filter(r => r.category === activeCategory)

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Reports</h1>
          <p>Analytics, exports and insights across all modules</p>
        </div>
        <button className="btn btn-primary">Generate Report</button>
      </div>

      {/* Key Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {METRICS.map(m => (
          <div key={m.label} className="card" style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{m.value}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>{m.label}</div>
            <span style={{ fontSize: 12, fontWeight: 600, color: m.positive ? '#10B981' : '#EF4444' }}>{m.change} vs last period</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
        {categories.map(c => (
          <button key={c} onClick={() => setActiveCategory(c)} className="btn" style={{ padding: '6px 14px', fontSize: 12, background: activeCategory === c ? 'var(--blue-bright)' : '#fff', color: activeCategory === c ? '#fff' : 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {c}
          </button>
        ))}
      </div>

      <div className="card">
        <table>
          <thead>
            <tr><th>Report Name</th><th>Category</th><th>Generated</th><th>Format</th><th>Size</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--blue-pale)', color: 'var(--blue-bright)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>📊</div>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{r.title}</span>
                  </div>
                </td>
                <td><span className="badge badge-blue">{r.category}</span></td>
                <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.date}</td>
                <td><span className={`badge ${r.format === 'PDF' ? 'badge-red' : 'badge-green'}`}>{r.format}</span></td>
                <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>{r.size}</td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-outline" style={{ padding: '5px 12px', fontSize: 12 }}>View</button>
                    <button className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 12 }}>Download</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
