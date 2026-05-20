import { useState } from 'react'

const JOBS = [
  { title: 'Senior UX Designer', dept: 'Product', type: 'Full-time', location: 'Hybrid', applied: 12, status: 'Urgent', posted: '3 days ago' },
  { title: 'Data Analyst', dept: 'Analytics', type: 'Full-time', location: 'Remote', applied: 45, status: 'Open', posted: '1 week ago' },
  { title: 'Backend Engineer', dept: 'Engineering', type: 'Full-time', location: 'On-site', applied: 28, status: 'Open', posted: '5 days ago' },
  { title: 'Marketing Specialist', dept: 'Marketing', type: 'Contract', location: 'Remote', applied: 19, status: 'Open', posted: '2 weeks ago' },
  { title: 'Finance Manager', dept: 'Finance', type: 'Full-time', location: 'On-site', applied: 7, status: 'Draft', posted: 'Yesterday' },
]

const CANDIDATES = [
  { name: 'Arjun Sharma', role: 'Senior UX Designer', stage: 'Interview', rating: 4, initials: 'AS', color: '#6366F1' },
  { name: 'Lucia Fernandez', role: 'Data Analyst', stage: 'Screening', rating: 3, initials: 'LF', color: '#10B981' },
  { name: 'Tom Bradley', role: 'Backend Engineer', stage: 'Applied', rating: 0, initials: 'TB', color: '#F59E0B' },
  { name: 'Yuki Tanaka', role: 'Senior UX Designer', stage: 'Offered', rating: 5, initials: 'YT', color: '#3B5BDB' },
  { name: 'Ravi Kumar', role: 'Data Analyst', stage: 'Applied', rating: 0, initials: 'RK', color: '#8B5CF6' },
]

export default function Recruitment({ onNavigate }) {
  const [tab, setTab] = useState('jobs')

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Recruitment</h1>
          <p>Manage job postings and candidate pipeline</p>
        </div>
        <button className="btn btn-primary">+ Post New Job</button>
      </div>

      {/* Funnel Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Applied', value: 142, color: '#3B5BDB', bg: '#EEF2FF' },
          { label: 'Screening', value: 86, color: '#8B5CF6', bg: '#F5F3FF' },
          { label: 'Interview', value: 32, color: '#06B6D4', bg: '#ECFEFF' },
          { label: 'Offered', value: 12, color: '#10B981', bg: '#D1FAE5' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px', borderLeft: `4px solid ${s.color}` }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['jobs', 'candidates'].map(t => (
          <button key={t} onClick={() => setTab(t)} className="btn" style={{ padding: '7px 20px', fontSize: 13, background: tab === t ? 'var(--blue-bright)' : '#fff', color: tab === t ? '#fff' : 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'jobs' ? (
        <div className="card">
          <table>
            <thead>
              <tr><th>Job Title</th><th>Department</th><th>Type</th><th>Location</th><th>Applicants</th><th>Status</th><th>Posted</th><th></th></tr>
            </thead>
            <tbody>
              {JOBS.map((j, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{j.title}</td>
                  <td><span className="badge badge-blue">{j.dept}</span></td>
                  <td style={{ fontSize: 13 }}>{j.type}</td>
                  <td style={{ fontSize: 13 }}>{j.location}</td>
                  <td style={{ fontWeight: 600, color: 'var(--blue-bright)' }}>{j.applied}</td>
                  <td><span className={`badge ${j.status === 'Urgent' ? 'badge-red' : j.status === 'Open' ? 'badge-green' : 'badge-gray'}`}>{j.status}</span></td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{j.posted}</td>
                  <td><button className="btn btn-outline" style={{ padding: '5px 12px', fontSize: 12 }}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr><th>Candidate</th><th>Applied For</th><th>Stage</th><th>Rating</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {CANDIDATES.map((c, i) => (
                <tr key={i}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: '50%', background: c.color, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{c.initials}</div>
                      <span style={{ fontWeight: 600 }}>{c.name}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: 13 }}>{c.role}</td>
                  <td><span className={`badge ${c.stage === 'Offered' ? 'badge-green' : c.stage === 'Interview' ? 'badge-blue' : c.stage === 'Screening' ? 'badge-orange' : 'badge-gray'}`}>{c.stage}</span></td>
                  <td>{c.rating > 0 ? '★'.repeat(c.rating) + '☆'.repeat(5 - c.rating) : '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-outline" style={{ padding: '5px 12px', fontSize: 12 }}>Review</button>
                      <button className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 12 }}>Move</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
