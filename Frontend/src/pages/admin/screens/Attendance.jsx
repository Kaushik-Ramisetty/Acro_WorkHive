import { useState } from 'react'

const RECORDS = [
  { name: 'Sarah Jenkins', dept: 'Product', checkIn: '09:02 AM', checkOut: '06:14 PM', hours: '9h 12m', status: 'Present', initials: 'SJ', color: '#6366F1' },
  { name: 'Michael Chen', dept: 'Analytics', checkIn: '08:47 AM', checkOut: '05:58 PM', hours: '9h 11m', status: 'Present', initials: 'MC', color: '#10B981' },
  { name: 'Emma Thompson', dept: 'HR', checkIn: '10:15 AM', checkOut: '—', hours: '—', status: 'Late', initials: 'ET', color: '#F59E0B' },
  { name: 'James Wilson', dept: 'Engineering', checkIn: '—', checkOut: '—', hours: '—', status: 'Absent', initials: 'JW', color: '#3B5BDB' },
  { name: 'Priya Nair', dept: 'Product', checkIn: '—', checkOut: '—', hours: '—', status: 'On Leave', initials: 'PN', color: '#EF4444' },
  { name: 'David Park', dept: 'Engineering', checkIn: '09:00 AM', checkOut: '06:00 PM', hours: '9h 00m', status: 'Present', initials: 'DP', color: '#8B5CF6' },
  { name: 'Anjali Mehta', dept: 'Marketing', checkIn: '09:30 AM', checkOut: '06:30 PM', hours: '9h 00m', status: 'Present', initials: 'AM', color: '#06B6D4' },
]

const STATS = [
  { label: 'Present', value: 1176, color: '#10B981', bg: '#D1FAE5' },
  { label: 'Absent', value: 42, color: '#EF4444', bg: '#FEE2E2' },
  { label: 'Late', value: 18, color: '#F59E0B', bg: '#FEF3C7' },
  { label: 'On Leave', value: 12, color: '#6366F1', bg: '#EEF2FF' },
]

export default function Attendance() {
  const [tab, setTab] = useState('today')

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Attendance</h1>
        <p>Track daily attendance and time records</p>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {STATS.map(s => (
          <div key={s.label} className="card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 44, height: 44, borderRadius: 10, background: s.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 14, height: 14, borderRadius: '50%', background: s.color }} />
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{s.value}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="card">
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
          {['today', 'week', 'month'].map(t => (
            <button key={t} onClick={() => setTab(t)} className="btn" style={{ padding: '6px 16px', fontSize: 13, background: tab === t ? 'var(--blue-bright)' : 'transparent', color: tab === t ? '#fff' : 'var(--text-secondary)', border: tab === t ? 'none' : '1px solid var(--border)' }}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
          <input type="date" style={{ marginLeft: 'auto', width: 160 }} defaultValue={new Date().toISOString().split('T')[0]} />
        </div>
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Department</th>
              <th>Check In</th>
              <th>Check Out</th>
              <th>Hours</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {RECORDS.map((r, i) => (
              <tr key={i}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: r.color, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{r.initials}</div>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</span>
                  </div>
                </td>
                <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.dept}</td>
                <td style={{ fontSize: 13 }}>{r.checkIn}</td>
                <td style={{ fontSize: 13 }}>{r.checkOut}</td>
                <td style={{ fontSize: 13, fontWeight: 500 }}>{r.hours}</td>
                <td>
                  <span className={`badge ${r.status === 'Present' ? 'badge-green' : r.status === 'Late' ? 'badge-orange' : r.status === 'On Leave' ? 'badge-blue' : 'badge-red'}`}>
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
