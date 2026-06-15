import { useState } from 'react'

const COURSES = [
  { title: 'Leadership Fundamentals', category: 'Management', duration: '4h 30m', enrolled: 128, completion: 72, level: 'Intermediate' },
  { title: 'AWS Cloud Practitioner', category: 'Technology', duration: '8h 00m', enrolled: 64, completion: 45, level: 'Beginner' },
  { title: 'Data Privacy & GDPR', category: 'Compliance', duration: '2h 00m', enrolled: 1248, completion: 89, level: 'All Levels' },
  { title: 'Agile & Scrum Mastery', category: 'Project Management', duration: '6h 15m', enrolled: 92, completion: 60, level: 'Intermediate' },
  { title: 'Excel for Analytics', category: 'Technology', duration: '3h 45m', enrolled: 220, completion: 55, level: 'Beginner' },
  { title: 'Effective Communication', category: 'Soft Skills', duration: '2h 30m', enrolled: 340, completion: 82, level: 'All Levels' },
]

const MY_COURSES = [
  { title: 'Data Privacy & GDPR', progress: 100, due: 'Completed' },
  { title: 'Leadership Fundamentals', progress: 65, due: 'Due May 10' },
  { title: 'Agile & Scrum Mastery', progress: 20, due: 'Due May 31' },
]

const CATEGORY_COLORS = {
  Management: '#8B5CF6',
  Technology: '#3B5BDB',
  Compliance: '#EF4444',
  'Project Management': '#10B981',
  'Soft Skills': '#F59E0B',
}

export default function LMS() {
  const [tab, setTab] = useState('library')

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Learning Management System</h1>
          <p>Employee training, courses and development programs</p>
        </div>
        <button className="btn btn-primary">+ Add Course</button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Total Courses', value: '42', color: '#3B5BDB' },
          { label: 'Enrolled This Month', value: '286', color: '#10B981' },
          { label: 'Avg Completion', value: '67%', color: '#8B5CF6' },
          { label: 'Certifications Issued', value: '94', color: '#F59E0B' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: s.color, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* My Learning */}
      <div className="card" style={{ padding: 20, marginBottom: 24 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>My Learning Path</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {MY_COURSES.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{c.title}</span>
                  <span style={{ fontSize: 12, color: c.due === 'Completed' ? '#10B981' : 'var(--text-muted)', fontWeight: 500 }}>{c.due}</span>
                </div>
                <div style={{ height: 6, background: '#E5E7EB', borderRadius: 99 }}>
                  <div style={{ height: '100%', width: `${c.progress}%`, background: c.progress === 100 ? '#10B981' : 'var(--blue-bright)', borderRadius: 99 }} />
                </div>
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, minWidth: 36, textAlign: 'right', color: c.progress === 100 ? '#10B981' : 'var(--text-primary)' }}>{c.progress}%</span>
              <button className="btn btn-outline" style={{ padding: '5px 14px', fontSize: 12, whiteSpace: 'nowrap' }}>
                {c.progress === 100 ? 'Certificate' : 'Continue'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['library', 'enrolled'].map(t => (
          <button key={t} onClick={() => setTab(t)} className="btn" style={{ padding: '7px 20px', fontSize: 13, background: tab === t ? 'var(--blue-bright)' : '#fff', color: tab === t ? '#fff' : 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
        {COURSES.map((c, i) => (
          <div key={i} className="card" style={{ padding: 20, cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
            onMouseLeave={e => e.currentTarget.style.transform = 'none'}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span className="badge" style={{ background: `${CATEGORY_COLORS[c.category]}22`, color: CATEGORY_COLORS[c.category] }}>{c.category}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.duration}</span>
            </div>
            <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6, color: 'var(--text-primary)' }}>{c.title}</h4>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>{c.level} · {c.enrolled} enrolled</div>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                <span style={{ color: 'var(--text-muted)' }}>Completion rate</span>
                <span style={{ fontWeight: 600 }}>{c.completion}%</span>
              </div>
              <div style={{ height: 4, background: '#E5E7EB', borderRadius: 99 }}>
                <div style={{ height: '100%', width: `${c.completion}%`, background: CATEGORY_COLORS[c.category], borderRadius: 99 }} />
              </div>
            </div>
            <button className="btn btn-outline" style={{ width: '100%', justifyContent: 'center', fontSize: 13 }}>Enroll</button>
          </div>
        ))}
      </div>
    </div>
  )
}
