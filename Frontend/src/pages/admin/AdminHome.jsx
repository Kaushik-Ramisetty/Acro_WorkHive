import { useEffect, useMemo, useState } from 'react';
import { formatINR, formatUsdAsInr, usdToInr } from '../../utils/formatCurrency';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { employeesApi } from '../../services/employees';
import { holidays as holidaysApi } from '../../services/holidays';
import { attendance as attendanceApi, regularization } from '../../services/attendance';
import { leaveApi } from '../../services/leave';
import { announcementsApi } from '../../services/announcements';
import Modal from '../../components/Modal';
import RequestWFHDialog from '../../components/RequestWFHDialog';
import './AdminHome.css';

const ADMIN_BASE = '/admin-dashboard';

const OPEN_JOBS = [
  {
    title: 'Senior UX Designer',
    meta: '12 applicants · Urgent',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="7" width="20" height="14" rx="2" />
        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
      </svg>
    ),
  },
  {
    title: 'Data Analyst',
    meta: '45 applicants · Remote',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M9 9h6M9 12h6M9 15h4" />
      </svg>
    ),
  },
];

const PENDING_CLAIMS = [
  { name: 'Sarah Jenkins',  type: 'Medical Reimbursement', usd:   420.00, initials: 'SJ', color: '#6366F1' },
  { name: 'Michael Chen',   type: 'Travel Expenses',       usd:  1250.50, initials: 'MC', color: '#10B981' },
  { name: 'Emma Thompson',  type: 'Equipment',             usd:  2100.00, initials: 'ET', color: '#F59E0B' },
];

const FUNNEL = [
  { label: 'Applied',   count: 142, width: '100%', color: '#DBEAFE', text: '#1D4ED8' },
  { label: 'Screening', count: 86,  width: '60%',  color: '#C7D2FE', text: '#3730A3' },
  { label: 'Interview', count: 32,  width: '38%',  color: '#A5B4FC', text: '#3730A3' },
  { label: 'Offered',   count: 12,  width: '20%',  color: '#818CF8', text: '#fff'    },
];

// Priority → status dot color. Matches the existing palette used elsewhere
// in the Admin shell (critical=red, important=blue, normal=emerald).
const NARRATIVE_DOT_BY_PRIORITY = {
  critical:  '#EF4444',
  important: '#3B5BDB',
  normal:    '#10B981',
};

// Server timestamps are naive UTC; force UTC parsing if there's no tz marker
// (mirrors NotificationBell's timeAgo helper).
function narrativeTimeAgo(iso) {
  if (!iso) return '';
  let s = String(iso);
  if (/T\d{2}:\d{2}/.test(s) && !/[Zz]|[+-]\d{2}:?\d{2}$/.test(s)) s = s + 'Z';
  const t = new Date(s).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'Just now';
  if (m < 60) return m + ' minute' + (m === 1 ? '' : 's') + ' ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + ' hour' + (h === 1 ? '' : 's') + ' ago';
  const d = Math.floor(h / 24);
  if (d === 1) return 'Yesterday';
  if (d < 7)   return d + ' days ago';
  return new Date(s).toLocaleDateString();
}

function ChevronRight() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

export default function AdminHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const goto = (slug) => navigate(ADMIN_BASE + (slug ? '/' + slug : ''));

  const adminName = (user?.full_name || user?.name || 'Admin').split(' ')[0];

  // Real employee headcount + this-week new hires
  const [employees, setEmployees] = useState([]);
  const [upcomingHolidays, setUpcomingHolidays] = useState([]);
  const [todayPresent, setTodayPresent] = useState(null);

  // Holidays-calendar modal (triggered by "Open Calendar" link)
  const [holidaysModalOpen, setHolidaysModalOpen] = useState(false);
  const [allHolidays, setAllHolidays] = useState([]);
  const [holidaysModalLoading, setHolidaysModalLoading] = useState(false);
  const currentYear = new Date().getFullYear();

  // Quick approvals panel: HR-stage pending leave + cancellations +
  // regularizations + comp-off (HR row of the chain). Loaded from /leave/list,
  // /attendance/regularization, and /leave/comp-off/list.
  const [pendingLeaves, setPendingLeaves] = useState([]);
  const [pendingRegs, setPendingRegs]     = useState([]);
  const [pendingCompOffs, setPendingCompOffs] = useState([]);
  const [approvalBusy, setApprovalBusy] = useState(null);

  // Quick Actions panel — drives the WFH modal + acts as a hub for the
  // most common admin tasks (Apply Leave, View Approvals, etc.).
  const [wfhOpen, setWfhOpen] = useState(false);

  // System Narrative — live announcement feed (latest published items,
  // role-filtered server-side). Loading + empty states are handled in JSX.
  const [narrative, setNarrative] = useState([]);
  const [narrativeLoading, setNarrativeLoading] = useState(true);

  const openHolidaysCalendar = () => {
    setHolidaysModalOpen(true);
    setHolidaysModalLoading(true);
    holidaysApi.list(currentYear)
      .then((rows) => setAllHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setAllHolidays([]))
      .finally(() => setHolidaysModalLoading(false));
  };
  const reloadAll = () => {
    employeesApi.list({}).then(setEmployees).catch(() => {});
    holidaysApi.upcoming({ days: 365, limit: 5 })
      .then((rows) => setUpcomingHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setUpcomingHolidays([]));
    const ymd = new Date().toISOString().slice(0, 10);
    attendanceApi.records({ start: ymd, end: ymd })
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        setTodayPresent(arr.filter((r) => r.status === 'present' || r.status === 'late').length);
      })
      .catch(() => setTodayPresent(null));
    // Quick approvals data: server filters with admin's JWT to HR-stage queue.
    leaveApi.list({ pending_my_approval: true })
      .then((rows) => setPendingLeaves(Array.isArray(rows) ? rows : []))
      .catch(() => setPendingLeaves([]));
    regularization.list({ status: 'pending' })
      .then((rows) => setPendingRegs(Array.isArray(rows) ? rows : []))
      .catch(() => setPendingRegs([]));
    leaveApi.compOffList({ status: 'pending' })
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        setPendingCompOffs(arr.filter((c) => c.next_approver_role === 'hr'));
      })
      .catch(() => setPendingCompOffs([]));
    // System Narrative — latest 5 announcements visible to this admin.
    setNarrativeLoading(true);
    announcementsApi.latest(5)
      .then((rows) => setNarrative(Array.isArray(rows) ? rows : []))
      .catch(() => setNarrative([]))
      .finally(() => setNarrativeLoading(false));
  };
  useEffect(() => {
    reloadAll();
    const id = setInterval(reloadAll, 60_000); // refresh every minute
    return () => clearInterval(id);
  }, []);

  // Build the unified quick-approvals list (HR-stage). Limit to 5 most recent
  // so the panel stays compact. Full queue lives at /admin-dashboard/approvals.
  const quickApprovals = useMemo(() => {
    const lv = (pendingLeaves || []).map((r) => ({
      kind: r.status === 'cancel_pending' ? 'cancel' : 'leave',
      key: 'L-' + r.id, id: r.id,
      name: r.employee_name || 'Unknown Employee',
      type: r.status === 'cancel_pending' ? 'Cancellation' : (r.leave_type_name || 'Leave'),
      detail: `${r.total_days || 0}d · ${r.start_date || ''} → ${r.end_date || ''}`,
      created_at: r.created_at,
    }));
    const co = (pendingCompOffs || []).map((c) => ({
      kind: 'compoff',
      key: 'C-' + c.id, id: c.id,
      name: c.employee_name || 'Unknown Employee',
      type: 'Comp-Off',
      detail: `${c.days || 0}d · worked ${c.worked_on || ''}`,
      created_at: c.created_at,
    }));
    const rg = (pendingRegs || []).map((r) => ({
      kind: 'regular',
      key: 'R-' + r.id, id: r.id,
      name: r.employee?.full_name || r.employee_name || 'Unknown Employee',
      type: 'Regularization',
      detail: `${r.regularization_type || 'attendance'} · ${r.date || ''}`,
      created_at: r.created_at,
    }));
    return [...lv, ...co, ...rg]
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      .slice(0, 5);
  }, [pendingLeaves, pendingCompOffs, pendingRegs]);
  const totalApprovals = pendingLeaves.length + pendingCompOffs.length + pendingRegs.length;

  const handleApprove = async (it) => {
    setApprovalBusy(it.key);
    try {
      if (it.kind === 'cancel')        await leaveApi.approveCancel(it.id);
      else if (it.kind === 'leave')    await leaveApi.approve(it.id);
      else if (it.kind === 'compoff')  await leaveApi.compOffApprove(it.id);
      else if (it.kind === 'regular')  await regularization.review(it.id, { status: 'approved', review_comment: null });
      reloadAll();
    } catch (e) {
      alert(e?.data?.detail || e?.message || 'Approve failed');
    } finally { setApprovalBusy(null); }
  };
  const handleReject = async (it) => {
    setApprovalBusy(it.key);
    try {
      const reason = window.prompt('Reason for rejection (optional)?') || '';
      if (it.kind === 'cancel' || it.kind === 'leave') await leaveApi.reject(it.id, reason);
      else if (it.kind === 'compoff') await leaveApi.compOffReject(it.id, reason);
      else if (it.kind === 'regular') await regularization.review(it.id, { status: 'rejected', review_comment: reason || null });
      reloadAll();
    } catch (e) {
      alert(e?.data?.detail || e?.message || 'Reject failed');
    } finally { setApprovalBusy(null); }
  };

  const initialsOf = (n) => (n || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase();

  const { activeCount, newThisWeek } = useMemo(() => {
    const active = employees.filter((e) => (e.employment_status || '').toLowerCase() === 'active');
    const sevenDaysAgo = new Date(); sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const newOnes = active.filter((e) => {
      if (!e.date_of_joining) return false;
      const d = new Date(e.date_of_joining);
      return !Number.isNaN(d.getTime()) && d >= sevenDaysAgo;
    });
    return { activeCount: active.length, newThisWeek: newOnes.length };
  }, [employees]);

  return (
    <div className="hr-dash-root">
      <div className="dashboard fade-in">
        {/* Welcome Banner */}
        <div className="dash-banner">
          <div>
            <h1 className="dash-banner-title">Welcome back, {adminName}!</h1>
            <p className="dash-banner-sub">
              Everything you need is right here.
            </p>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="dash-kpi-row">
          <div className="card dash-kpi-card">
            <div className="dash-kpi-top">
              <div className="dash-kpi-icon dash-kpi-icon-blue">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <line x1="19" y1="8" x2="19" y2="14" />
                  <line x1="22" y1="11" x2="16" y2="11" />
                </svg>
              </div>
              <span className="badge badge-green">
                {newThisWeek > 0 ? `+${newThisWeek} this week` : 'No new hires this week'}
              </span>
            </div>
            <div className="dash-kpi-value">{activeCount.toLocaleString('en-IN')}</div>
            <div className="dash-kpi-label">Active Employees</div>
          </div>

          <div className="card dash-kpi-card">
            <div className="dash-kpi-top">
              <div className="dash-kpi-icon dash-kpi-icon-teal">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                  <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
                </svg>
              </div>
              <span className="badge badge-blue">{activeCount > 0 && todayPresent != null ? Math.round((todayPresent / activeCount) * 100) + "% rate" : "—"}</span>
            </div>
            <div className="dash-kpi-value">{todayPresent == null ? "..." : todayPresent.toLocaleString("en-IN")}</div>
            <div className="dash-kpi-label">Today's Attendance</div>
          </div>

          <div className="card dash-kpi-card">
            <div className="dash-kpi-top">
              <div className="dash-kpi-icon dash-kpi-icon-orange">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="5" width="20" height="14" rx="2" />
                  <line x1="2" y1="10" x2="22" y2="10" />
                </svg>
              </div>
              <span className="badge badge-orange">In progress</span>
            </div>
            <div className="dash-kpi-value">{formatUsdAsInr('$0.1M')}</div>
            <div className="dash-kpi-label">Monthly Payroll Summary</div>
          </div>
        </div>

        {/* Quick Actions — admin-relevant shortcuts. WFH used to live on the
            Leave Management page; it now opens from here. */}
        <div className="card" style={{ padding: '18px 20px', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>Quick Actions</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            {[
              {
                label: 'Apply Leave', tint: '#ECFDF5', color: '#059669',
                onClick: () => navigate(ADMIN_BASE + '/leave?section=apply'),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" />
                    <line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                    <path d="M9 16l2 2 4-4" />
                  </svg>
                ),
              },
              {
                label: 'Request WFH', tint: '#EFF6FF', color: '#1D4ED8',
                onClick: () => setWfhOpen(true),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                    <polyline points="9 22 9 12 15 12 15 22" />
                  </svg>
                ),
              },
              {
                label: 'Manage Employees', tint: '#F5F3FF', color: '#6D28D9',
                onClick: () => goto('employees'),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                ),
              },
              {
                label: 'Onboarding', tint: '#FAF5FF', color: '#7C3AED',
                onClick: () => goto('onboarding'),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                    <path d="M6 12v5c3 3 9 3 12 0v-5" />
                  </svg>
                ),
              },
              {
                label: 'Payroll', tint: '#FEFCE8', color: '#A16207',
                onClick: () => goto('payroll'),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="5" width="20" height="14" rx="2" />
                    <line x1="2" y1="10" x2="22" y2="10" />
                    <circle cx="12" cy="14.5" r="1.6" />
                  </svg>
                ),
              },
              {
                label: 'Reports', tint: '#ECFEFF', color: '#0E7490',
                onClick: () => goto('reports'),
                icon: (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="20" x2="18" y2="10" />
                    <line x1="12" y1="20" x2="12" y2="4" />
                    <line x1="6"  y1="20" x2="6"  y2="14" />
                  </svg>
                ),
              },
            ].map((a) => (
              <button
                key={a.label}
                type="button"
                onClick={a.onClick}
                className="card"
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '12px 14px', cursor: 'pointer', border: '1px solid var(--border)',
                  background: 'var(--bg-card)', textAlign: 'left',
                }}
              >
                <span style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: a.tint, color: a.color,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  {a.icon}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{a.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Quick Approvals — HR-stage queue surfaced on the dashboard */}
        <div className="card" style={{ padding: '18px 20px', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>Quick Approvals</h3>
              <span style={{ background: '#1E3A8A', color: '#fff', borderRadius: 999, padding: '2px 9px', fontSize: 11, fontWeight: 700 }}>
                {totalApprovals}
              </span>
            </div>
            <button
              type="button"
              onClick={() => goto('approvals')}
              style={{ background: 'none', border: 'none', color: '#3B5BDB', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
            >
              View All →
            </button>
          </div>
          {quickApprovals.length === 0 && (
            <p style={{ color: '#94A3B8', fontSize: 13, padding: '8px 4px', margin: 0 }}>
              Nothing waiting on you right now.
            </p>
          )}
          {quickApprovals.map((it) => {
            const tagBg = it.kind === 'cancel'  ? '#FEE2E2' :
                          it.kind === 'compoff' ? '#EDE9FE' :
                          it.kind === 'regular' ? '#D1FAE5' : '#DBEAFE';
            const tagFg = it.kind === 'cancel'  ? '#991B1B' :
                          it.kind === 'compoff' ? '#6D28D9' :
                          it.kind === 'regular' ? '#047857' : '#1E40AF';
            return (
              <div key={it.key}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderTop: '1px solid #E5E7EB' }}>
                <div style={{
                  width: 36, height: 36, borderRadius: '50%',
                  background: 'linear-gradient(135deg,#3B82F6,#6366F1)', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700, flexShrink: 0,
                }}>{initialsOf(it.name)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                    {it.name}
                    <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: tagBg, color: tagFg }}>
                      {it.type}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>{it.detail}</div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    disabled={approvalBusy === it.key}
                    onClick={() => handleReject(it)}
                    style={{ padding: '5px 12px', borderRadius: 6, background: '#FEE2E2', color: '#991B1B', border: '1px solid #FECACA', fontSize: 11, fontWeight: 600, cursor: 'pointer', opacity: approvalBusy === it.key ? 0.5 : 1 }}
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    disabled={approvalBusy === it.key}
                    onClick={() => handleApprove(it)}
                    style={{ padding: '5px 12px', borderRadius: 6, background: '#10B981', color: '#fff', border: 'none', fontSize: 11, fontWeight: 600, cursor: 'pointer', opacity: approvalBusy === it.key ? 0.5 : 1 }}
                  >
                    {it.kind === 'cancel' ? 'Approve Cancel' : 'Approve'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Middle Row: Upcoming Holidays + System Narrative side-by-side */}
        <div className="dash-mid-row">
          {/* Upcoming Holidays */}
          <div className="card dash-mid-card">
            <div className="dash-card-header">
              <h3>Upcoming Holidays</h3>
              <button className="btn-link" onClick={openHolidaysCalendar}>Open Calendar</button>
            </div>
            <div className="dash-job-list">
              {upcomingHolidays.length === 0 && (
                <p style={{ color: '#94A3B8', fontSize: 13, padding: '8px 4px' }}>No upcoming holidays in the next 12 months.</p>
              )}
              {upcomingHolidays.map((h) => {
                const d = new Date(h.date);
                const day = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
                const wk = d.toLocaleDateString('en-IN', { weekday: 'long' });
                return (
                  <div key={h.id} className="dash-job-item" style={{ cursor: 'default' }}>
                    <div className="dash-job-icon" style={{ background: '#FAF5FF', color: '#7C3AED' }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2" />
                        <line x1="16" y1="2" x2="16" y2="6" />
                        <line x1="8" y1="2" x2="8" y2="6" />
                        <line x1="3" y1="10" x2="21" y2="10" />
                      </svg>
                    </div>
                    <div className="dash-job-info">
                      <span className="dash-job-title">{h.name}</span>
                      <span className="dash-job-meta">{day} - {wk} - {h.holiday_type || 'public'}{h.applicable_locations ? ' - ' + h.applicable_locations : ''}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* System Narrative — latest announcements (live) */}
          <div className="card dash-mid-card">
            <div className="dash-card-header">
              <h3>System Narrative</h3>
              <button
                type="button"
                className="btn-link"
                onClick={() => goto('announcements')}
              >
                Manage
              </button>
            </div>
            <div className="dash-narrative-list">
              {narrativeLoading && narrative.length === 0 && (
                <p className="dash-narrative-desc" style={{ padding: '8px 0' }}>
                  Loading announcements…
                </p>
              )}
              {!narrativeLoading && narrative.length === 0 && (
                <p className="dash-narrative-desc" style={{ padding: '8px 0' }}>
                  No announcements yet.
                </p>
              )}
              {narrative.map((n) => (
                <div
                  key={n.id}
                  className="dash-narrative-item"
                  role="button"
                  tabIndex={0}
                  onClick={() => goto('announcements')}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') goto('announcements'); }}
                  style={{ cursor: 'pointer' }}
                >
                  <div
                    className="dash-narrative-dot"
                    style={{ background: NARRATIVE_DOT_BY_PRIORITY[n.priority] || NARRATIVE_DOT_BY_PRIORITY.normal }}
                  />
                  <h4 className="dash-narrative-title">{n.title}</h4>
                  <p className="dash-narrative-desc">{n.content || n.description || ''}</p>
                  <span className="dash-narrative-time">{narrativeTimeAgo(n.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <RequestWFHDialog open={wfhOpen} onClose={() => setWfhOpen(false)} onSubmitted={() => {}} />

      {holidaysModalOpen && (
        <Modal
          title={`Holidays — ${currentYear}`}
          onClose={() => setHolidaysModalOpen(false)}
          width="max-w-2xl"
        >
          {holidaysModalLoading && (
            <p className="text-sm text-slate-500">Loading…</p>
          )}
          {!holidaysModalLoading && allHolidays.length === 0 && (
            <p className="text-sm text-slate-500">No holidays found for {currentYear}.</p>
          )}
          {!holidaysModalLoading && allHolidays.length > 0 && (
            <ul className="divide-y divide-slate-100">
              {allHolidays.map((h) => {
                const d = new Date(h.date);
                const day = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
                const wk = d.toLocaleDateString('en-IN', { weekday: 'long' });
                return (
                  <li key={h.id} className="flex items-center gap-3 py-3">
                    <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2"/>
                        <line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/>
                        <line x1="3" y1="10" x2="21" y2="10"/>
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-800">{h.name}</p>
                      <p className="text-xs text-slate-500">
                        {day} · {wk}
                        {h.holiday_type ? ' · ' + h.holiday_type : ''}
                        {h.applicable_locations ? ' · ' + h.applicable_locations : ''}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Modal>
      )}
    </div>
  );
}
