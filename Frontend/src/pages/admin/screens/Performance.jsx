import { useState } from 'react'

const REVIEWS = [
  { name: 'Sarah Jenkins', role: 'UX Designer', score: 92, trend: '+5', cycle: 'Q3 2026', status: 'Completed', initials: 'SJ', color: '#6366F1' },
  { name: 'Michael Chen', role: 'Data Analyst', score: 87, trend: '+2', cycle: 'Q3 2026', status: 'Completed', initials: 'MC', color: '#10B981' },
  { name: 'Emma Thompson', role: 'HR Manager', score: 78, trend: '-3', cycle: 'Q3 2026', status: 'In Progress', initials: 'ET', color: '#F59E0B' },
  { name: 'James Wilson', role: 'Backend Engineer', score: 95, trend: '+8', cycle: 'Q3 2026', status: 'Completed', initials: 'JW', color: '#3B5BDB' },
  { name: 'Priya Nair', role: 'Product Manager', score: 0, trend: '—', cycle: 'Q3 2026', status: 'Pending', initials: 'PN', color: '#EF4444' },
  { name: 'David Park', role: 'DevOps Engineer', score: 88, trend: '+4', cycle: 'Q3 2026', status: 'Completed', initials: 'DP', color: '#8B5CF6' },
]

export default function Performance() {
  const [tab, setTab] = useState('reviews')

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Performance</h1>
          <p>Track employee performance reviews and cycles</p>
        </div>
        <button className="btn btn-primary">Start New Cycle</button>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Avg Score', value: '88%', sub: 'Company-wide', color: '#3B5BDB' },
          { label: 'Reviews Done', value: '420', sub: 'This quarter', color: '#10B981' },
          { label: 'In Progress', value: '68', sub: 'Self-assessments', color: '#F59E0B' },
          { label: 'Quality of Hire', value: '+15%', sub: 'vs last quarter', color: '#8B5CF6' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: s.color, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{s.label}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['reviews', 'goals'].map(t => (
          <button key={t} onClick={() => setTab(t)} className="btn" style={{ padding: '7px 20px', fontSize: 13, background: tab === t ? 'var(--blue-bright)' : '#fff', color: tab === t ? '#fff' : 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'reviews' ? (
        <div className="card">
          <table>
            <thead>
              <tr><th>Employee</th><th>Role</th><th>Score</th><th>Trend</th><th>Cycle</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {REVIEWS.map((r, i) => (
                <tr key={i}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: '50%', background: r.color, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{r.initials}</div>
                      <span style={{ fontWeight: 600 }}>{r.name}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.role}</td>
                  <td>
                    {r.score > 0 ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ height: 6, width: 80, background: '#E5E7EB', borderRadius: 99 }}>
                          <div style={{ height: '100%', width: `${r.score}%`, background: r.score >= 90 ? '#10B981' : r.score >= 75 ? '#3B5BDB' : '#F59E0B', borderRadius: 99 }} />
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{r.score}</span>
                      </div>
                    ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                  </td>
                  <td style={{ fontWeight: 600, color: r.trend.startsWith('+') ? '#10B981' : r.trend === '—' ? 'var(--text-muted)' : '#EF4444' }}>{r.trend}</td>
                  <td style={{ fontSize: 13 }}>{r.cycle}</td>
                  <td><span className={`badge ${r.status === 'Completed' ? 'badge-green' : r.status === 'In Progress' ? 'badge-blue' : 'badge-orange'}`}>{r.status}</span></td>
                  <td><button className="btn btn-outline" style={{ padding: '5px 12px', fontSize: 12 }}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 16 }}>
          {['Engineering OKRs', 'Product Goals', 'HR Initiatives', 'Marketing Targets'].map((g, i) => (
            <div key={i} className="card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600 }}>{g}</h3>
                <span className="badge badge-blue">Q3 2026</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {['Delivery velocity', 'Code quality', 'Team satisfaction'].map((item, j) => (
                  <div key={j}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{item}</span>
                      <span style={{ fontWeight: 600 }}>{[72, 88, 95][j]}%</span>
                    </div>
                    <div style={{ height: 5, background: '#E5E7EB', borderRadius: 99 }}>
                      <div style={{ height: '100%', width: `${[72, 88, 95][j]}%`, background: 'var(--blue-bright)', borderRadius: 99 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
