import { formatINR, formatUsdAsInr, usdToInr } from '../../../utils/formatCurrency';

export default function Dashboard({ onNavigate }) {
  return (
    <div className="dashboard fade-in">
      {/* Welcome Banner */}
      <div className="dash-banner">
        <div>
          <h1 className="dash-banner-title">Welcome back, Admin!</h1>
          <p className="dash-banner-sub">The Work Hive has processed 12 new updates since your last login. Everything looks healthy.</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="dash-kpi-row">
        <div className="card dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon dash-kpi-icon-blue">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
            </div>
            <span className="badge badge-green">+2 this week</span>
          </div>
          <div className="dash-kpi-value">1,248</div>
          <div className="dash-kpi-label">Active Employees</div>
        </div>

        <div className="card dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon dash-kpi-icon-teal">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/></svg>
            </div>
            <span className="badge badge-blue">94.2% rate</span>
          </div>
          <div className="dash-kpi-value">1,176</div>
          <div className="dash-kpi-label">Today's Attendance</div>
        </div>

        <div className="card dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon dash-kpi-icon-orange">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
            </div>
            <span className="badge badge-orange">In progress</span>
          </div>
          <div className="dash-kpi-value">{formatUsdAsInr('$4.2M')}</div>
          <div className="dash-kpi-label">Monthly Payroll Summary</div>
        </div>
      </div>

      {/* Middle Row */}
      <div className="dash-mid-row">
        {/* Open Jobs */}
        <div className="card dash-mid-card">
          <div className="dash-card-header">
            <h3>Open Jobs</h3>
            <button className="btn-link" onClick={() => onNavigate('recruitment')}>View Recruitment</button>
          </div>
          <div className="dash-job-list">
            <button className="dash-job-item" onClick={() => onNavigate('recruitment')}>
              <div className="dash-job-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
              </div>
              <div className="dash-job-info">
                <span className="dash-job-title">Senior UX Designer</span>
                <span className="dash-job-meta">12 applicants · Urgent</span>
              </div>
              <ChevronRight />
            </button>
            <button className="dash-job-item" onClick={() => onNavigate('recruitment')}>
              <div className="dash-job-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg>
              </div>
              <div className="dash-job-info">
                <span className="dash-job-title">Data Analyst</span>
                <span className="dash-job-meta">45 applicants · Remote</span>
              </div>
              <ChevronRight />
            </button>
          </div>
        </div>

        {/* Pending Claims */}
        <div className="card dash-mid-card">
          <div className="dash-card-header">
            <h3>Pending Claims</h3>
            <span className="dash-notif-badge">8</span>
          </div>
          <div className="dash-claims-list">
            {[
              { name: 'Sarah Jenkins', type: 'Medical Reimbursement', usd: 420.00, initials: 'SJ', color: '#6366F1' },
              { name: 'Michael Chen', type: 'Travel Expenses', usd: 1250.50, initials: 'MC', color: '#10B981' },
              { name: 'Emma Thompson', type: 'Equipment', usd: 2100.00, initials: 'ET', color: '#F59E0B' },
            ].map((c, i) => (
              <div key={i} className="dash-claim-item">
                <div className="dash-claim-avatar" style={{ background: c.color }}>{c.initials}</div>
                <div className="dash-claim-info">
                  <span className="dash-claim-name">{c.name}</span>
                  <span className="dash-claim-type">{c.type} · {formatINR(usdToInr(c.usd))}</span>
                </div>
                <button className="dash-review-btn" onClick={() => onNavigate('claims')}>Review</button>
              </div>
            ))}
          </div>
        </div>

        {/* Recruitment Funnel */}
        <div className="card dash-mid-card">
          <div className="dash-card-header">
            <h3>Recruitment Funnel</h3>
          </div>
          <div className="dash-funnel">
            {[
              { label: 'Applied', count: 142, width: '100%', color: '#DBEAFE', text: '#1D4ED8' },
              { label: 'Screening', count: 86, width: '60%', color: '#C7D2FE', text: '#3730A3' },
              { label: 'Interview', count: 32, width: '38%', color: '#A5B4FC', text: '#3730A3' },
              { label: 'Offered', count: 12, width: '20%', color: '#818CF8', text: '#fff' },
            ].map((f, i) => (
              <div key={i} className="dash-funnel-item">
                <div className="dash-funnel-bar" style={{ width: f.width, background: f.color }}>
                  <span style={{ color: f.text }}>{f.label} ({f.count})</span>
                </div>
              </div>
            ))}
          </div>
          <p className="dash-funnel-note">"Quality of hire is up 15% this quarter."</p>
        </div>
      </div>

      {/* System Narrative */}
      <div className="dash-narrative-section">
        <h3 className="dash-section-title">System Narrative</h3>
        <div className="dash-narrative-grid">
          {[
            {
              dot: '#10B981',
              title: 'New Policy Published',
              desc: 'The Hybrid Work Policy v2.0 was successfully distributed to all 1,248 employees. 82% read receipt rate.',
              time: '2 hours ago',
            },
            {
              dot: '#EF4444',
              title: 'Payroll Threshold Reached',
              desc: 'Monthly disbursement volume has reached 95% of projected budget. Final approvals required by EOD.',
              time: '5 hours ago',
            },
            {
              dot: '#3B5BDB',
              title: 'Performance Cycles Open',
              desc: 'Q3 Self-Assessments are now live for the Engineering and Product departments. 420 tasks generated.',
              time: 'Yesterday',
            },
          ].map((n, i) => (
            <div key={i} className="dash-narrative-card">
              <div className="dash-narrative-dot" style={{ background: n.dot }} />
              <h4 className="dash-narrative-title">{n.title}</h4>
              <p className="dash-narrative-desc">{n.desc}</p>
              <span className="dash-narrative-time">{n.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ChevronRight() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
}
