import { useAuth } from "../../../context/AuthContext";
const TEAMS = [
  { name: 'Engineering', lead: 'James Wilson', members: 48, projects: 6, color: '#3B5BDB', initials: 'JW' },
  { name: 'Product', lead: 'Priya Nair', members: 22, projects: 4, color: '#8B5CF6', initials: 'PN' },
  { name: 'Analytics', lead: 'Michael Chen', members: 14, projects: 3, color: '#10B981', initials: 'MC' },
  { name: 'Human Resources', lead: 'Emma Thompson', members: 18, projects: 5, color: '#F59E0B', initials: 'ET' },
  { name: 'Marketing', lead: 'Anjali Mehta', members: 12, projects: 3, color: '#06B6D4', initials: 'AM' },
  { name: 'Finance', lead: 'Robert Lee', members: 10, projects: 2, color: '#EF4444', initials: 'RL' },
]

const ORG_MEMBERS = [
  // current admin pulled in below (dynamic from useAuth)
  { name: 'James Wilson', role: 'Engineering Lead', reports: 48, initials: 'JW', color: '#3B5BDB' },
  { name: 'Priya Nair', role: 'Product Lead', reports: 22, initials: 'PN', color: '#8B5CF6' },
  { name: 'Emma Thompson', role: 'HR Lead', reports: 18, initials: 'ET', color: '#F59E0B' },
]

export default function TeamManagement() {
  const { user } = useAuth();
  const fullName = user?.full_name || user?.name || 'Admin';
  const initials = (fullName || 'A').split(' ').filter(Boolean).map((x)=>x[0]).slice(0,2).join('').toUpperCase() || 'A';
  const subtitle = user?.designation || (user?.role ? user.role.toUpperCase() : '');
  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Team Management</h1>
          <p>Manage departments, teams and reporting structures</p>
        </div>
        <button className="btn btn-primary">+ Create Team</button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Total Teams', value: '6', color: '#3B5BDB' },
          { label: 'Total Members', value: '124', color: '#10B981' },
          { label: 'Active Projects', value: '23', color: '#8B5CF6' },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: '20px 24px' }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Team Cards */}
      <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14, color: 'var(--text-primary)' }}>All Departments</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginBottom: 28 }}>
        {TEAMS.map((t, i) => (
          <div key={i} className="card" style={{ padding: 20, borderTop: `3px solid ${t.color}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
              <div>
                <h4 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{t.name}</h4>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Led by {t.lead}</p>
              </div>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: t.color, color: '#fff', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{t.initials}</div>
            </div>
            <div style={{ display: 'flex', gap: 20 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{t.members}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Members</div>
              </div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{t.projects}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Projects</div>
              </div>
            </div>
            <button className="btn btn-outline" style={{ width: '100%', marginTop: 14, justifyContent: 'center', fontSize: 13 }}>View Team</button>
          </div>
        ))}
      </div>

      {/* Org Chart Preview */}
      <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Org Structure</h3>
      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
          {/* Root */}
          <div style={{ background: 'linear-gradient(135deg,#1E3A8A,#3B5BDB)', color: '#fff', borderRadius: 10, padding: '12px 24px', textAlign: 'center', marginBottom: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{fullName}</div>
            <div style={{ fontSize: 11, opacity: 0.8 }}>{subtitle}</div>
          </div>
          <div style={{ width: 2, height: 24, background: '#E5E7EB' }} />
          {/* L2 */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
            {ORG_MEMBERS.slice(1).map((m, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
                <div style={{ width: 2, height: 20, background: '#E5E7EB' }} />
                <div style={{ background: 'var(--bg-card)', border: `2px solid ${m.color}`, borderRadius: 10, padding: '10px 18px', textAlign: 'center', minWidth: 140 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: m.color }}>{m.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{m.role}</div>
                  <div style={{ fontSize: 11, marginTop: 4, color: 'var(--text-secondary)' }}>{m.reports} reports</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
