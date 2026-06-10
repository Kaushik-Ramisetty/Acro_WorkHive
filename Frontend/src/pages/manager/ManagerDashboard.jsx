import { useState, useEffect, useMemo, createContext, useContext } from 'react';
import { usePersistedState } from '../../hooks/usePersistedState';
import { useTheme } from '../../context/ThemeContext';

// Tiny context so any page's <Topbar> can open the mobile sidebar without prop-drilling.
const SidebarCtx = createContext({ openSidebar: () => {} });
import { useLeaveData } from '../../hooks/useLeaveData';
import { leaveApi } from '../../services/leave';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import logoPng from '../../assets/logo.png';
import ManagerLeavePage from './leave/ManagerLeavePage';
import ManagerApprovalsPage from './approvals/ManagerApprovalsPage';
import ManagerTimesheetReviewPage from './timesheets/ManagerTimesheetReviewPage';
import { holidays as holidaysApi } from '../../services/holidays';
import UnderConstruction from '../../components/UnderConstruction';
import { attendance as attendanceApi, managerApi, triggerCsvDownload } from '../../services/attendance';
import { utilizationApi } from '../../services/utilization';
import AttendanceGrid, { cycleNextStatus, startOfWeek, fmtIso } from '../../components/attendance/AttendanceGrid';
import { employeesApi } from '../../services/employees';
import ManagerCompOffPage from './compoff/ManagerCompOffPage';
import PoliciesPage from '../admin/policies/PoliciesPage';
import ManagerAnnouncementsPage from './announcements/ManagerAnnouncementsPage';
import SelfServicePage from '../shared/SelfServicePage';
import SharedSettingsPage from '../../components/SettingsPage';
import SharedNotificationsPage from '../shared/NotificationsPage';
import ManagerPerformancePage from './ManagerPerformancePage';
import PayrollPage from '../employee/screens/PayrollPage';
import NotificationBell from '../../components/NotificationBell';
import SearchBar from '../../components/SearchBar';
import ProfileMenu from '../../components/ProfileMenu';
import Modal from '../../components/Modal';
import {
  LayoutDashboard, Users, Calendar, FileText, CheckSquare,
  TrendingUp, Target, Clock, FolderOpen, BarChart2,
  MessageSquare, Bell, Settings, LogOut, Search,
  AlertTriangle, ArrowRight, Plus, Eye, X,
  UserCheck, Home, DollarSign, Star, Edit, Trash2,
  Filter, Download, ChevronLeft, ChevronRight,
  Send, Paperclip, Smile, Activity, Shield,
  Check, Palette, Database, Phone,
} from '../../components/lucideShim';

// ── Palette ──────────────────────────────────────────────────────
// Palette references CSS variables defined in src/index.css so the manager
// dashboard automatically follows the active Light/Dark theme. The brand
// accents (primary/blue/purple/red/yellow) stay constant for visual identity.
const C = {
  sidebar: 'var(--mgr-sidebar)', sidebarHover: 'var(--mgr-sidebar-hover)',
  primary: '#10B981', primaryDark: '#059669',
  accent: '#F97316', blue: '#1D4ED8',
  purple: '#8B5CF6', red: '#EF4444', yellow: '#F59E0B',
  bg: 'var(--hrms-bg)', card: 'var(--hrms-surface)',
  border: 'var(--hrms-border)', text: 'var(--hrms-text)',
  muted: 'var(--hrms-text-muted)', light: 'var(--hrms-surface-2)',
}

// ── Data ─────────────────────────────────────────────────────────
const MEMBERS = [
  { id:1, name:'Elena Rodriguez',  role:'UI Designer',      dept:'Design',      av:'ER', status:'On Leave', perf:92, email:'elena@workhive.com' },
  { id:2, name:'Marcus Chen',      role:'Sr. Developer',    dept:'Engineering', av:'MC', status:'Present',  perf:89, email:'marcus@workhive.com' },
  { id:3, name:'Sarah Jenkins',    role:'Product Manager',  dept:'Product',     av:'SJ', status:'WFH',      perf:86, email:'sarah@workhive.com' },
  { id:4, name:'David Miller',     role:'Backend Dev',      dept:'Engineering', av:'DM', status:'Present',  perf:55, email:'david@workhive.com' },
  { id:5, name:'Kevin O\'Brien',   role:'QA Engineer',      dept:'Engineering', av:'KO', status:'Absent',   perf:40, email:'kevin@workhive.com' },
  { id:6, name:'Arjun Gupta',      role:'DevOps Engineer',  dept:'Engineering', av:'AG', status:'On Leave', perf:78, email:'arjun@workhive.com' },
  { id:7, name:'Lucia Fernandez',  role:'UX Researcher',    dept:'Design',      av:'LF', status:'On Leave', perf:82, email:'lucia@workhive.com' },
  { id:8, name:'James Park',       role:'Frontend Dev',     dept:'Engineering', av:'JP', status:'Present',  perf:74, email:'james@workhive.com' },
]

// Stale demo array (Elena / Marcus / Sarah / …) was here. Approvals on the
// dashboard home + /approvals route are now driven entirely by live API calls
// (see DashboardHome's combinedApprovals + ManagerApprovalsPage).

const ANNOUNCEMENTS = [
  { id:1, title:'System Maintenance',    desc:'Scheduled on Oct 28, 10:00 PM – 2:00 AM. Please save your work.', date:'Oct 24', type:'system',  author:'IT Team' },
  { id:2, title:'New HR Policy Update',  desc:'WFH policy updated. Up to 3 days/week with manager approval.',      date:'Oct 23', type:'policy',  author:'HR Team' },
  { id:4, title:'Q4 All Hands Meeting',  desc:'Join us Nov 1st at 11 AM for Q3 results and Q4 roadmap.',          date:'Oct 18', type:'event',   author:'Leadership' },
  { id:5, title:'Welcome James Park',    desc:'James joins us as Frontend Developer on the Engineering team!',     date:'Oct 15', type:'people',  author:'HR Team' },
]

const ATTENDANCE_TREND = [
  { day:'18 Oct', n:18 }, { day:'19 Oct', n:19 }, { day:'20 Oct', n:20 },
  { day:'21 Oct', n:19 }, { day:'23 Oct', n:20 }, { day:'24 Oct', n:20 },
]

const GOALS = [
  { title:'Launch new design system',  owner:'Elena Rodriguez', av:'ER', due:'Oct 31', prog:92, pri:'High' },
  { title:'Complete API migration',     owner:'Marcus Chen',     av:'MC', due:'Nov 15', prog:78, pri:'High' },
  { title:'User research report Q4',   owner:'Lucia Fernandez', av:'LF', due:'Nov 30', prog:45, pri:'Medium' },
  { title:'Implement CI/CD pipeline',  owner:'Arjun Gupta',     av:'AG', due:'Nov 20', prog:60, pri:'High' },
  { title:'Q4 product roadmap',        owner:'Sarah Jenkins',   av:'SJ', due:'Oct 28', prog:88, pri:'Critical' },
  { title:'Performance testing suite', owner:'Kevin O\'Brien',  av:'KO', due:'Dec 10', prog:30, pri:'Low' },
]

const PROJECTS = [
  { name:'Design System v2',       status:'In Progress', prog:72,  team:['ER','LF'],       due:'Nov 15', pri:'High' },
  { name:'API Gateway Migration',  status:'In Progress', prog:58,  team:['MC','DM','AG'],  due:'Nov 30', pri:'Critical' },
  { name:'Q4 User Research',       status:'Planning',    prog:20,  team:['LF','SJ'],       due:'Dec 10', pri:'Medium' },
  { name:'Mobile App Redesign',    status:'Review',      prog:90,  team:['ER','JP'],       due:'Oct 31', pri:'High' },
  { name:'Performance Dashboard',  status:'Completed',   prog:100, team:['MC','DM'],       due:'Oct 20', pri:'Low' },
  { name:'DevOps Automation',      status:'In Progress', prog:45,  team:['AG','KO'],       due:'Dec 5',  pri:'High' },
]

// ── Micro components ──────────────────────────────────────────────
const AV_COLORS = { ER:'#8B5CF6', MC:'#1D4ED8', SJ:'#F97316', DM:'#10B981', KO:'#EF4444', AG:'#F59E0B', LF:'#EC4899', JP:'#06B6D4', AR:'#8B5CF6' }

function Av({ init, size=36 }) {
  return (
    <div style={{ width:size, height:size, borderRadius:'50%', background:AV_COLORS[init]||C.primary, display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:size*0.35, flexShrink:0 }}>
      {init}
    </div>
  )
}

function Badge({ children, color=C.primary, bg='#D1FAE5' }) {
  return <span style={{ padding:'2px 10px', borderRadius:20, background:bg, color, fontSize:11, fontWeight:700 }}>{children}</span>
}

function Card({ children, style={} }) {
  return <div style={{ background:C.card, borderRadius:12, border:`1px solid ${C.border}`, padding:20, ...style }}>{children}</div>
}

function Stat({ icon:Icon, label, value, sub, subColor=C.primary }) {
  return (
    <Card style={{ flex:1, minWidth:130 }}>
      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12 }}>
        <div style={{ background:C.light, borderRadius:8, padding:8 }}><Icon size={17} color={C.primary} /></div>
        <span style={{ fontSize:11, color:C.muted, fontWeight:700, textTransform:'uppercase', letterSpacing:0.5 }}>{label}</span>
      </div>
      <div style={{ fontSize:26, fontWeight:800, color:C.text, marginBottom:4 }}>{value}</div>
      {sub && <div style={{ fontSize:12, color:subColor, fontWeight:500 }}>{sub}</div>}
    </Card>
  )
}

function Btn({ children, onClick, variant='primary', size='md', style={} }) {
  const base = { border:'none', borderRadius:8, cursor:'pointer', fontWeight:600, fontFamily:"'DM Sans',sans-serif", transition:'all 0.15s', display:'inline-flex', alignItems:'center', gap:6 }
  const pad = size==='sm' ? '6px 14px' : '9px 20px'
  const fs  = size==='sm' ? 12 : 14
  const v = {
    primary: { background:C.primary, color:'#fff', padding:pad, fontSize:fs },
    blue:    { background:C.blue,    color:'#fff', padding:pad, fontSize:fs },
    outline: { background:'transparent', color:C.primary, border:`1.5px solid ${C.primary}`, padding:pad, fontSize:fs },
    danger:  { background:'#FEE2E2', color:C.red, padding:pad, fontSize:fs },
    ghost:   { background:'transparent', color:C.muted, padding:pad, fontSize:fs },
  }
  return <button style={{ ...base, ...(v[variant]||v.primary), ...style }} onClick={onClick}>{children}</button>
}

function Bar({ value, color }) {
  const c = color||(value>=80?C.primary:value>=60?C.yellow:C.red)
  return (
    <div style={{ background:C.light, borderRadius:4, height:6, flex:1 }}>
      <div style={{ width:`${value}%`, background:c, height:'100%', borderRadius:4 }} />
    </div>
  )
}

function Hdr({ title, actionLabel='View All', onAction }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
      <span style={{ fontWeight:700, fontSize:15, color:C.text }}>{title}</span>
      {onAction && <button onClick={onAction} style={{ background:'none', border:'none', color:C.primary, fontWeight:600, fontSize:13, cursor:'pointer', display:'flex', alignItems:'center', gap:4 }}>{actionLabel}<ArrowRight size={13}/></button>}
    </div>
  )
}

// ── Topbar ────────────────────────────────────────────────────────
function initialsOf(name) {
  return (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'U';
}

function Topbar({ title, sub, onNav }) {
  const { openSidebar } = useContext(SidebarCtx);
  // Two-layer header (mirrors the admin pattern):
  //   Row 1 — sticky white utility bar with search + bell + profile.
  //   Row 2 — gradient welcome banner with the page title + subtitle (uses
  //           the manager palette: deep emerald → emerald gradient).
  // Both layers bleed to the edges of <main>'s 26px/30px padding via
  // negative margins.
  return (
    <>
      {/* Row 1 — utility bar */}
      <div
        style={{
          position:'sticky',
          top:0,
          zIndex:30,
          display:'flex',
          alignItems:'center',
          justifyContent:'space-between',
          gap:20,
          padding:'12px 30px',
          marginLeft:-30,
          marginRight:-30,
          marginTop:-26,
          marginBottom:18,
          background: C.card,
          borderBottom:`1px solid ${C.border}`,
        }}
      >
        <button
          onClick={openSidebar}
          className="md:hidden rounded-md p-2 text-slate-500 hover:bg-slate-100"
          aria-label="Open sidebar"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div className="hidden md:block" style={{ flex:1, maxWidth:560 }}>
          <SearchBar variant="manager" />
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12, flexShrink:0, marginLeft:'auto' }}>
          <NotificationBell />
          <ProfileMenu role="manager" />
        </div>
      </div>

      {/* Row 2 — welcome banner */}
      <div
        style={{
          position:'relative',
          overflow:'hidden',
          padding:'30px 34px',
          borderRadius:16,
          marginBottom:24,
          color:'#FFFFFF',
          background:`linear-gradient(135deg, #064E3B 0%, ${C.primaryDark} 60%, ${C.primary} 100%)`,
          boxShadow:'0 4px 14px rgba(6, 78, 59, 0.18)',
        }}
      >
        {/* Soft radial glow in the top-right corner — same trick as the
            admin welcome banner so the gradient feels alive. */}
        <div
          aria-hidden
          style={{
            position:'absolute',
            right:-40,
            top:-40,
            width:220,
            height:220,
            background:'radial-gradient(circle, rgba(255,255,255,0.10) 0%, transparent 70%)',
            pointerEvents:'none',
          }}
        />
        <h1 style={{
          margin:0,
          fontSize:26,
          fontWeight:700,
          letterSpacing:'-0.4px',
          lineHeight:1.2,
          color:'#FFFFFF',
        }}>{title}</h1>
        {sub && (
          <p style={{
            margin:'8px 0 0',
            fontSize:14,
            lineHeight:1.6,
            color:'rgba(255, 255, 255, 0.82)',
            maxWidth:640,
          }}>{sub}</p>
        )}
      </div>
    </>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────
const NAV = [
  { id:'dashboard',     label:'Dashboard',      icon:LayoutDashboard },
  { id:'profile',       label:'My Profile',     icon:UserCheck },
  { id:'self-service',  label:'Self Service',   icon:FolderOpen },
  { id:'team',          label:'My Team',        icon:Users },
  // Attendance hosts both attendance + timesheets via internal sub-tabs
  // (Timesheets is no longer a top-level sidebar item).
  { id:'attendance',    label:'Attendance',     icon:Calendar },
  { id:'leave',         label:'Leave Management', icon:FileText },
  { id:'approvals',     label:'Approvals',      icon:CheckSquare },
  { id:'performance',   label:'Performance',    icon:TrendingUp },
  { id:'projects',      label:'Projects',       icon:FolderOpen },
  { id:'reports',       label:'Reports',        icon:BarChart2 },
  { id:'announcements', label:'Announcements',  icon:Bell },
  { id:'company',       label:'Company',        icon:Home },
  { id:'payroll',       label:'Payroll',        icon:DollarSign },
  { id:'policies',      label:'Policies',       icon:FileText },
]

function Sidebar({ active, onNav, onLogout, open, onClose }) {
  return (
    <>
      {/* Mobile backdrop */}
      <div
        onClick={onClose}
        className={'fixed inset-0 z-40 bg-black/40 transition-opacity md:hidden ' + (open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none')}
        aria-hidden
      />
      <div
        className={'transition-transform md:translate-x-0 ' + (open ? 'translate-x-0' : '-translate-x-full md:translate-x-0')}
        style={{ width:240, minHeight:'100vh', background:C.sidebar, display:'flex', flexDirection:'column', position:'fixed', left:0, top:0, bottom:0, zIndex:100 }}
      >
      {/* Logo */}
      <div style={{ padding:'20px 20px 16px', borderBottom:'1px solid #1E293B' }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:36, height:36, borderRadius:10, background:'rgba(255,255,255,0.12)', display:'flex', alignItems:'center', justifyContent:'center', padding:4 }}>
            <img src={logoPng} alt="WorkHive" style={{ width:26, height:26, objectFit:'contain' }} />
          </div>
          <div>
            <div style={{ color:'#fff', fontWeight:800, fontSize:15, letterSpacing:'-0.3px' }}>Acronotics WorkHive</div>
            <div style={{ color:'#475569', fontSize:9, fontWeight:500 }}>Human Intelligence In Action</div>
          </div>
        </div>
      </div>

      {/* Nav items */}
      <nav style={{ flex:1, padding:'12px 10px', overflowY:'auto' }}>
        {NAV.map(({ id, label, icon:Icon }) => (
          <button key={id} onClick={() => onNav(id)} style={{ width:'100%', display:'flex', alignItems:'center', gap:12, padding:'9px 12px', borderRadius:8, border:'none', cursor:'pointer', marginBottom:2, background:active===id?'#1E293B':'transparent', color:active===id?'#fff':'#94A3B8', fontWeight:active===id?600:400, fontSize:13, textAlign:'left', transition:'all 0.15s', fontFamily:"'DM Sans',sans-serif" }}>
            <Icon size={16} color={active===id?C.primary:'#64748B'} />
            {label}
          </button>
        ))}
      </nav>

      {/* Bottom */}
      <div style={{ padding:'10px 10px 16px', borderTop:'1px solid #1E293B' }}>
        <button onClick={() => onNav('settings')} style={{ width:'100%', display:'flex', alignItems:'center', gap:12, padding:'9px 12px', borderRadius:8, border:'none', cursor:'pointer', background:active==='settings'?'#1E293B':'transparent', color:'#94A3B8', fontSize:13, marginBottom:2, fontFamily:"'DM Sans',sans-serif" }}>
          <Settings size={16} color="#64748B" /> Settings
        </button>
        <button onClick={onLogout} style={{ width:'100%', display:'flex', alignItems:'center', gap:12, padding:'9px 12px', borderRadius:8, border:'none', cursor:'pointer', background:'transparent', color:'#94A3B8', fontSize:13, fontFamily:"'DM Sans',sans-serif" }}>
          <LogOut size={16} color="#64748B" /> Logout
        </button>
      </div>
    </div>
    </>
  )
}

// ══════════════════════════════════════════════════════════════════
// PAGE COMPONENTS
// ══════════════════════════════════════════════════════════════════

// ── Dashboard Home ────────────────────────────────────────────────
function DashboardHome({ onNav }) {
  const { user: _authUser } = useAuth();
  const _firstName = (_authUser?.first_name) || ((_authUser?.full_name || _authUser?.name || '').split(' ')[0]) || 'there';
  const _greet = (() => { const h = new Date().getHours(); if (h < 12) return 'Good morning'; if (h < 17) return 'Good afternoon'; return 'Good evening'; })();
  const [upcomingHolidays, setUpcomingHolidays] = useState([]);
  useEffect(() => {
    holidaysApi.upcoming({ days: 180, limit: 3 })
      .then((rows) => setUpcomingHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setUpcomingHolidays([]));
  }, []);

  // Holidays-calendar modal — triggered by the "View Calendar" action on the
  // Upcoming Holidays card. Shows the entire holiday list for the current year
  // instead of redirecting to the Attendance section.
  const [holidaysModalOpen, setHolidaysModalOpen] = useState(false);
  const [allHolidays, setAllHolidays] = useState([]);
  const [holidaysModalLoading, setHolidaysModalLoading] = useState(false);
  const currentYear = new Date().getFullYear();
  const openHolidaysCalendar = () => {
    setHolidaysModalOpen(true);
    setHolidaysModalLoading(true);
    holidaysApi.list(currentYear)
      .then((rows) => setAllHolidays(Array.isArray(rows) ? rows : []))
      .catch(() => setAllHolidays([]))
      .finally(() => setHolidaysModalLoading(false));
  };
  // Live attendance counts for the current week (Mon..Sun) and last 7 days.
  const [weekCounts, setWeekCounts] = useState([]);   // [['MON','18'], ...]
  const [trend7d, setTrend7d]       = useState([]);    // [{day, n}, ...]
  const [teamSize, setTeamSize]     = useState(null);
  const [presentToday, setPresentToday] = useState(null);
  // List of direct reports (id + display name) — used by Today's Team Status.
  const [teamMembers, setTeamMembers] = useState([]);
  // Today's attendance records for the manager's reports.
  const [todayRecords, setTodayRecords] = useState([]);
  useEffect(() => {
    const me = _authUser?.id;
    if (!me) return;
    employeesApi.list({}).then((rows) => {
      const arr = Array.isArray(rows) ? rows : [];
      const team = arr.filter((e) => e.reporting_manager_id === me && (e.employment_status || '').toLowerCase() === 'active');
      setTeamSize(team.length);
      setTeamMembers(
        team.map((e) => ({
          id: e.id,
          name: e.full_name
            || [e.first_name, e.last_name].filter(Boolean).join(' ').trim()
            || e.email
            || ('Employee #' + e.id),
        }))
      );
    }).catch(() => { setTeamSize(null); setTeamMembers([]); });
    const today = new Date();
    const ymd = (d) => d.toISOString().slice(0, 10);
    attendanceApi.records({ start: ymd(today), end: ymd(today) })
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        setTodayRecords(arr);
        setPresentToday(arr.filter((r) => r.status === 'present' || r.status === 'late').length);
      })
      .catch(() => { setPresentToday(null); setTodayRecords([]); });
  }, [_authUser?.id]);
  useEffect(() => {
    const loadAttn = () => {
    const today = new Date();
    const dow = (today.getDay() + 6) % 7;        // Mon=0
    const monday = new Date(today); monday.setDate(today.getDate() - dow);
    const sunday = new Date(monday); sunday.setDate(monday.getDate() + 6);
    const ymd = (d) => d.toISOString().slice(0, 10);
    attendanceApi.records({ start: ymd(monday), end: ymd(sunday) })
      .then((rows) => {
        const arr = Array.isArray(rows) ? rows : [];
        const labels = ['MON','TUE','WED','THU','FRI','SAT','SUN'];
        const counts = labels.map((label, i) => {
          const d = new Date(monday); d.setDate(monday.getDate() + i);
          const iso = ymd(d);
          const present = arr.filter((r) => r.date === iso && (r.status === 'present' || r.status === 'late')).length;
          return [label, String(present)];
        });
        setWeekCounts(counts);
        // Trend = last 7 calendar days (oldest -> newest)
        const trend = [];
        for (let i = 6; i >= 0; i--) {
          const d = new Date(today); d.setDate(today.getDate() - i);
          const iso = ymd(d);
          const present = arr.filter((r) => r.date === iso && (r.status === 'present' || r.status === 'late')).length;
          trend.push({ day: d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }), n: present });
        }
        setTrend7d(trend);
      })
      .catch(() => { setWeekCounts([]); setTrend7d([]); });
    };
    loadAttn();
    const id = setInterval(loadAttn, 60_000);
    return () => clearInterval(id);
  }, []);
  const announcementsWithHolidays = [
    ...upcomingHolidays.map((h, i) => ({
      id: `H-${h.id || i}`,
      title: `${h.name} — Office Closure`,
      desc: `Holiday on ${new Date(h.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}`,
      date: new Date(h.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }),
      type: 'holiday',
      author: 'HR',
    })),
    ...ANNOUNCEMENTS,
  ];
  // Pending leave approvals waiting on this manager (server-scoped to manager-stage of direct reports)
  const { requests: pendingLeaves, approve: approveLeave, reject: rejectLeave, approveCancel } = useLeaveData({ pendingMyApproval: true });
  // All team leaves (for On-Leave-today and overlap calculation) + pending comp-offs
  const [allTeamLeaves, setAllTeamLeaves] = useState([]);
  const [pendingCompOffs, setPendingCompOffs] = useState([]);
  const [busyId, setBusyId] = useState(null);

  const reloadAux = () => {
    leaveApi.list({}).then(setAllTeamLeaves).catch(() => {});
    leaveApi.compOffList({ status: 'pending' }).then(setPendingCompOffs).catch(() => {});
  };
  useEffect(() => { reloadAux(); }, []);

  const todayIso = new Date().toISOString().slice(0, 10);

  const onLeaveTodayCount = useMemo(() => {
    const set = new Set();
    for (const r of allTeamLeaves) {
      if (r.status !== 'approved') continue;
      if (r.start_date <= todayIso && r.end_date >= todayIso) set.add(r.employee_id);
    }
    return set.size;
  }, [allTeamLeaves, todayIso]);

  const compOffsForMe = useMemo(
    () => pendingCompOffs.filter((c) => c.next_approver_role === 'manager'),
    [pendingCompOffs],
  );
  const pendingApprovalsTotal = pendingLeaves.length + compOffsForMe.length;

  // Filter for the Approvals Panel tabs: 'all' | 'leave' | 'compoff'.
  const [approvalsFilter, setApprovalsFilter] = useState('all');

  // Today's Team Status — derived from team members + leaves + attendance.
  const todayGroups = useMemo(() => {
    const teamIds  = new Set(teamMembers.map((t) => t.id));
    const nameById = Object.fromEntries(teamMembers.map((t) => [t.id, t.name]));
    // ON LEAVE today — approved leaves where today is within [start, end].
    const onLeave = new Set();
    for (const r of allTeamLeaves) {
      if (r.status !== 'approved' && r.status !== 'consumed') continue;
      if (!teamIds.has(r.employee_id)) continue;
      if (r.start_date <= todayIso && r.end_date >= todayIso) onLeave.add(r.employee_id);
    }
    const onLeaveList = [...onLeave].map((id) => nameById[id] || ('Employee #' + id));
    // ABSENT today — explicit absent status in attendance records.
    const absentList = todayRecords
      .filter((r) => teamIds.has(r.employee_id) && r.status === 'absent')
      .map((r) => nameById[r.employee_id] || ('Employee #' + r.employee_id));
    // WFH today — wfh status / source. Best-effort: backend may use any of
    // these spellings depending on shift policy.
    const wfhList = todayRecords
      .filter((r) => teamIds.has(r.employee_id) && (
        r.status === 'wfh' || r.status === 'work_from_home' ||
        (typeof r.source === 'string' && r.source.toLowerCase() === 'wfh')
      ))
      .map((r) => nameById[r.employee_id] || ('Employee #' + r.employee_id));
    return [
      { key:'on_leave', label:'ON LEAVE', count:onLeaveList.length, color:C.yellow, members:onLeaveList },
      { key:'absent',   label:'ABSENT',   count:absentList.length,  color:C.red,    members:absentList },
      { key:'wfh',      label:'WFH',      count:wfhList.length,     color:C.blue,   members:wfhList },
    ];
  }, [teamMembers, allTeamLeaves, todayRecords, todayIso]);

  // Combined approvals list (leaves + comp-offs) for the panel.
  // Honors `approvalsFilter` so the All/Leave/Comp-Off tabs only show matches.
  const combinedApprovals = useMemo(() => {
    const leaveItems = pendingLeaves.map((r) => ({
      key: 'L-' + r.id,
      kind: 'leave',
      id: r.id,
      name: r.employee_name,
      av: (r.employee_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase(),
      type: r.status === 'cancel_pending' ? 'Cancellation' : 'Leave',
      detail: `${r.leave_type_name} · ${r.total_days}d · ${r.start_date} → ${r.end_date}`,
      created_at: r.created_at,
      raw: r,
    }));
    const coItems = compOffsForMe.map((c) => ({
      key: 'C-' + c.id,
      kind: 'compoff',
      id: c.id,
      name: c.employee_name,
      av: (c.employee_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase(),
      type: 'Comp-Off',
      detail: `${c.days}d · worked on ${c.worked_on}`,
      created_at: c.created_at,
      raw: c,
    }));
    const merged = (
      approvalsFilter === 'leave'   ? leaveItems :
      approvalsFilter === 'compoff' ? coItems    :
      [...leaveItems, ...coItems]
    );
    return merged
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      .slice(0, 4);
  }, [pendingLeaves, compOffsForMe, approvalsFilter]);

  const handleApprove = async (item) => {
    setBusyId(item.key);
    try {
      if (item.kind === 'compoff') await leaveApi.compOffApprove(item.id);
      else if (item.raw.status === 'cancel_pending') await approveCancel(item.id);
      else await approveLeave(item.id);
      reloadAux();
    } catch (e) { alert(e?.data?.detail || 'Approve failed'); }
    finally { setBusyId(null); }
  };
  const handleReject = async (item) => {
    const reason = window.prompt('Reason for rejection (optional)?') || '';
    setBusyId(item.key);
    try {
      if (item.kind === 'compoff') await leaveApi.compOffReject(item.id, reason);
      else await rejectLeave(item.id, reason);
      reloadAux();
    } catch (e) { alert(e?.data?.detail || 'Reject failed'); }
    finally { setBusyId(null); }
  };

  // Upcoming approved leaves over next 14 days, grouped by start date
  const upcomingByDay = useMemo(() => {
    const fortnight = new Date(); fortnight.setDate(fortnight.getDate() + 14);
    const fortnightIso = fortnight.toISOString().slice(0, 10);
    const byDay = new Map();
    for (const r of allTeamLeaves) {
      if (r.status !== 'approved') continue;
      if (r.start_date < todayIso || r.start_date > fortnightIso) continue;
      if (!byDay.has(r.start_date)) byDay.set(r.start_date, []);
      byDay.get(r.start_date).push(r);
    }
    return Array.from(byDay.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(0, 5);
  }, [allTeamLeaves, todayIso]);

  const overlapDays = upcomingByDay.filter(([, list]) => list.length > 1);

  const fmtDay = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
  };

  return (
    <div>
      <Topbar title="Manager Dashboard" sub={`${_greet}, ${_firstName}! Your workspace is all set.`} onNav={onNav} />

      {/* Stats */}
      <div style={{ display:'flex', gap:14, marginBottom:24, flexWrap:'wrap' }}>
        <Stat icon={Users}        label="Team Size"         value={teamSize == null ? "..." : String(teamSize)}  sub={teamSize == null ? "Loading" : "Active reports"} />
        <Stat icon={UserCheck}    label="Present Today"     value={presentToday == null || teamSize == null ? "..." : presentToday + "/" + teamSize} sub={teamSize ? Math.round((presentToday/teamSize)*100) + "% of team" : "Loading"} />
        <Stat icon={Home}         label="On Leave"          value={String(onLeaveTodayCount)}      sub={onLeaveTodayCount === 1 ? '1 person on approved leave' : onLeaveTodayCount + ' people on approved leave'} subColor={C.accent} />
        <Stat icon={CheckSquare}  label="Pending Approvals" value={String(pendingApprovalsTotal)}  sub={pendingApprovalsTotal ? 'Needs your action' : 'All clear 🎉'}        subColor={C.red} />
      </div>

      {/* Quick Actions — top-level, full width (matches the employee layout). */}
      <Card style={{ marginBottom:20 }}>
        <div style={{ fontWeight:700, fontSize:15, marginBottom:14 }}>Quick Actions</div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4, minmax(0, 1fr))', gap:12 }}>
          {[
            ['Approve Leave',     CheckSquare, 'leave'],
            ['Approve Timesheet', Clock,       'timesheets'],
            ['Announcement',      Bell,        'announcements'],
            ['Team Reports',      BarChart2,   'reports'],
          ].map(([label, Icon, page]) => (
            <button
              key={label}
              type="button"
              onClick={() => onNav(page)}
              style={{
                display:'flex', flexDirection:'column', alignItems:'center', gap:10,
                padding:'14px 12px', borderRadius:12,
                border:`1px solid ${C.border}`, background: C.card,
                cursor:'pointer', transition:'border-color 0.15s, box-shadow 0.15s',
                fontFamily:"'DM Sans', sans-serif",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.04)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <span style={{ width:44, height:44, borderRadius:12, background:C.light, display:'flex', alignItems:'center', justifyContent:'center' }}>
                <Icon size={20} color={C.primary} />
              </span>
              <span style={{ fontSize:11, fontWeight:600, color:C.text, textAlign:'center', lineHeight:1.3 }}>{label}</span>
            </button>
          ))}
        </div>
      </Card>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 320px', gap:20 }}>
        {/* Left */}
        <div style={{ display:'flex', flexDirection:'column', gap:20 }}>

          {/* Approvals panel — live data from /leave/list and /leave/comp-off/list */}
          <Card>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <span style={{ fontWeight:700, fontSize:15 }}>Approvals Panel</span>
                <Badge color="#fff" bg={C.primary}>{pendingApprovalsTotal}</Badge>
              </div>
              
            </div>
            <div style={{ display:'flex', gap:4, marginBottom:16, borderBottom:`1px solid ${C.border}`, paddingBottom:10 }}>
              {[
                ['all',     'All',      pendingApprovalsTotal],
                ['leave',   'Leave',    pendingLeaves.length],
                ['compoff', 'Comp-Off', compOffsForMe.length],
              ].map(([key, label, count]) => {
                const active = approvalsFilter === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setApprovalsFilter(key)}
                    style={{
                      padding:'4px 12px',
                      borderRadius:6,
                      border:'none',
                      cursor:'pointer',
                      background: active ? C.primary : 'transparent',
                      color: active ? '#fff' : C.muted,
                      fontSize:12,
                      fontWeight: active ? 600 : 400,
                      fontFamily:"'DM Sans',sans-serif",
                      transition:'background 0.15s, color 0.15s',
                    }}
                  >
                    {label} ({count})
                  </button>
                );
              })}
            </div>
            {combinedApprovals.length === 0 && (
              <div style={{ padding:'24px 0', textAlign:'center', color:C.muted, fontSize:13 }}>
                Nothing waiting on you right now. 🎉
              </div>
            )}
            {combinedApprovals.map(a => (
              <div key={a.key} style={{ display:'flex', alignItems:'center', gap:12, padding:'12px 0', borderBottom:`1px solid ${C.border}` }}>
                <Av init={a.av} size={38} />
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontWeight:600, fontSize:13 }}>{a.name}</div>
                  <div style={{ fontSize:12, color:C.muted }}>{a.type} · {a.detail}</div>
                </div>
                <div style={{ display:'flex', gap:6 }}>
                  <Btn variant="danger" size="sm" onClick={() => handleReject(a)} style={{ opacity: busyId===a.key ? 0.5 : 1 }}>Reject</Btn>
                  <Btn variant="primary" size="sm" onClick={() => handleApprove(a)} style={{ opacity: busyId===a.key ? 0.5 : 1 }}>Approve</Btn>
                </div>
              </div>
            ))}
            <button onClick={() => onNav('approvals')} style={{ marginTop:12, background:'none', border:'none', color:C.primary, fontWeight:600, fontSize:13, cursor:'pointer', display:'flex', alignItems:'center', gap:4, fontFamily:"'DM Sans',sans-serif" }}>View All Requests <ArrowRight size={13}/></button>
          </Card>

          {/* Attendance */}
          <Card>
            <Hdr title="Team Attendance Overview" actionLabel="View Calendar" onAction={() => onNav('attendance')} />
            <div style={{ display:'flex', gap:12, marginBottom:16 }}>
              {(weekCounts.length === 7 ? weekCounts : [['MON','-'],['TUE','-'],['WED','-'],['THU','-'],['FRI','-'],['SAT','-'],['SUN','-']]).map(([d,n],i) => (
                <div key={d} style={{ textAlign:'center', flex:1 }}>
                  <div style={{ fontSize:10, color:C.muted, fontWeight:700, marginBottom:6 }}>{d}</div>
                  <div style={{ width:34, height:34, borderRadius:'50%', background:i===4?C.primary:C.light, color:i===4?'#fff':C.text, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:14, margin:'0 auto' }}>{n}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop:16 }}>
              <div style={{ fontSize:13, fontWeight:600, marginBottom:10 }}>Attendance Trend</div>
              <div style={{ display:'flex', alignItems:'flex-end', gap:8, height:72 }}>
                {(trend7d.length ? trend7d : ATTENDANCE_TREND).map(d => (
                  <div key={d.day} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:4 }}>
                    <div style={{ width:'100%', background:C.primary, borderRadius:'4px 4px 0 0', height:`${(d.n/24)*72}px`, opacity:0.8 }} />
                    <span style={{ fontSize:9, color:C.muted }}>{d.day}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* Upcoming Holidays — replaces the old performance snapshot */}
          <Card>
            <Hdr title="Upcoming Holidays" actionLabel="View Calendar" onAction={openHolidaysCalendar} />
            {upcomingHolidays.length === 0 && (
              <div style={{ padding:'12px 0', fontSize:12, color:C.muted }}>No upcoming holidays in the next 6 months.</div>
            )}
            {upcomingHolidays.map((h, i) => {
              const d = new Date(h.date);
              const dayLabel = d.toLocaleDateString('en-IN', { day:'2-digit', month:'short' });
              const weekday  = d.toLocaleDateString('en-IN', { weekday:'long' });
              return (
                <div key={(h.id || i)} style={{ display:'flex', alignItems:'center', gap:12, padding:'12px 0', borderBottom: i === upcomingHolidays.length - 1 ? 'none' : `1px solid ${C.border}` }}>
                  <div style={{ width:40, height:40, borderRadius:10, background:'#FAF5FF', color:'#7C3AED', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                    <Calendar size={18} />
                  </div>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontWeight:600, fontSize:13 }}>{h.name}</div>
                    <div style={{ fontSize:11, color:C.muted }}>{dayLabel} · {weekday}{h.holiday_type ? ' · ' + h.holiday_type : ''}</div>
                  </div>
                </div>
              );
            })}
          </Card>

        </div>

        {/* Right */}
        <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
          <Card>
            <Hdr title="Today's Team Status" actionLabel="View Calendar" onAction={() => onNav('attendance')} />
            {todayGroups.every((g) => g.count === 0) && (
              <div style={{ padding:'12px 0', fontSize:12, color:C.muted }}>
                Everyone's accounted for today. ✅
              </div>
            )}
            {todayGroups.map((g) => (
              g.count === 0 ? null : (
                <div key={g.key} style={{ marginBottom:12 }}>
                  <div style={{ fontSize:10, fontWeight:700, color:g.color, letterSpacing:0.5, marginBottom:5 }}>● {g.label} ({g.count})</div>
                  {g.members.map((m, i) => (
                    <div key={g.key + '-' + i} style={{ fontSize:12, color:C.muted, paddingLeft:10, marginBottom:3 }}>· {m}</div>
                  ))}
                </div>
              )
            ))}
          </Card>

          <Card>
            <Hdr title="Leave Planning & Overlap" />
            {overlapDays.length > 0 && (
              <div style={{ background:'#FEF3C7', border:`1px solid ${C.yellow}`, borderRadius:8, padding:10, marginBottom:14, display:'flex', gap:8 }}>
                <AlertTriangle size={14} color={C.accent} style={{ flexShrink:0, marginTop:2 }} />
                <div>
                  <div style={{ fontSize:12, fontWeight:700, color:C.accent }}>Overlap Risk Detected</div>
                  <div style={{ fontSize:11, color:'#92400E' }}>
                    {overlapDays.length === 1
                      ? `${overlapDays[0][1].length} team members on leave on ${fmtDay(overlapDays[0][0])}.`
                      : `${overlapDays.length} day(s) with overlapping leaves in the next 14 days.`
                    }
                  </div>
                </div>
              </div>
            )}
            <div style={{ fontSize:12, fontWeight:700, color:C.muted, marginBottom:8 }}>Upcoming Leaves (next 14 days)</div>
            {upcomingByDay.length === 0 && (
              <div style={{ padding:'12px 0', fontSize:12, color:C.muted }}>No upcoming approved leaves.</div>
            )}
            {upcomingByDay.map(([day, list]) => {
              const overlap = list.length > 1;
              return (
                <div key={day} style={{ display:'flex', justifyContent:'space-between', marginBottom:6, fontSize:12 }}>
                  <span style={{ color:C.text }}>{fmtDay(day)}</span>
                  <span style={{ color: overlap ? C.red : C.muted, fontWeight:600 }}>
                    {list.length} {list.length === 1 ? 'leave' : 'leaves'}{overlap ? ' (overlap)' : ''}
                  </span>
                </div>
              );
            })}
            <Btn variant="outline" size="sm" style={{ marginTop:8, width:'100%', justifyContent:'center' }} onClick={() => onNav('leave')}>View Leave Calendar</Btn>
          </Card>

          <Card>
            <Hdr title="Timesheet Summary" actionLabel={(() => { const t = new Date(); const oneJan = new Date(t.getFullYear(),0,1); const wk = Math.ceil((((t - oneJan) / 86400000) + oneJan.getDay()+1)/7); return `Week ${wk}`; })()} onAction={() => onNav('timesheets')} />
            <div style={{ display:'flex', alignItems:'center', gap:16 }}>
              <div style={{ position:'relative', width:76, height:76 }}>
                <svg viewBox="0 0 76 76"><circle cx="38" cy="38" r="30" fill="none" stroke={C.light} strokeWidth="7"/><circle cx="38" cy="38" r="30" fill="none" stroke={C.primary} strokeWidth="7" strokeDasharray={`${0.85*188} ${188}`} strokeLinecap="round" transform="rotate(-90 38 38)"/></svg>
                <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
                  <span style={{ fontSize:14, fontWeight:800 }}>85%</span>
                  <span style={{ fontSize:8, color:C.muted }}>Submitted</span>
                </div>
              </div>
              <div style={{ flex:1 }}>
                {[['Expected','960h'],['Logged','816h'],['Pending','4']].map(([l,v]) => (
                  <div key={l} style={{ display:'flex', justifyContent:'space-between', marginBottom:6, fontSize:12 }}>
                    <span style={{ color:C.muted }}>{l}</span>
                    <span style={{ fontWeight:700 }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
            <Btn variant="outline" size="sm" style={{ marginTop:10, width:'100%', justifyContent:'center' }} onClick={() => onNav('timesheets')}>View Details</Btn>
          </Card>

        </div>
      </div>

      {/* Full-year holidays modal triggered by "View Calendar" on the
          Upcoming Holidays card. */}
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
                      <Calendar size={18} />
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
  )
}

// ── My Team ───────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────
// Extend-project modal — receives the FULL row object (`project`) so
// the project_id passed to onExtend is the one from THIS allocation,
// not whatever's keyed by employee_id elsewhere.
// ─────────────────────────────────────────────────────────────────
function ExtendProjectModal({ project, onClose, onExtend }) {
  const today = new Date().toISOString().slice(0, 10);
  const [newEnd, setNewEnd] = useState(
    project?.proj_end ? String(project.proj_end).slice(0, 10) : ""
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!project) return null;

  async function submit() {
    if (!newEnd) { setError("Pick a new end date"); return; }
    setBusy(true); setError("");
    try {
      await onExtend(project.id, project.project_id, newEnd);
      onClose?.();
    } catch (ex) {
      setError(ex?.data?.detail || ex?.message || "Extend failed");
    } finally { setBusy(false); }
  }

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(15,28,46,0.55)', zIndex:50, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div onClick={(e)=>e.stopPropagation()} style={{ background: C.card, borderRadius:14, width:'min(440px, 90vw)', boxShadow:'0 25px 50px rgba(15,23,42,0.25)', overflow:'hidden' }}>
        <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}` }}>
          <div style={{ fontSize:14, fontWeight:700, color:C.text }}>Extend project</div>
          <div style={{ fontSize:11, color:C.muted }}>{project.project_name} ({project.project_id})</div>
        </div>
        <div style={{ padding:'14px 18px', display:'grid', gap:10, fontSize:12 }}>
          <div>Current start: <b>{project.proj_start ? String(project.proj_start).slice(0,10) : '—'}</b></div>
          <div>Current end: <b>{project.proj_end ? String(project.proj_end).slice(0,10) : '—'}</b></div>
          <label style={{ display:'block', fontWeight:600, color:C.muted, fontSize:11, marginTop:6 }}>New end date</label>
          <input type="date" value={newEnd} min={today} onChange={(e)=>setNewEnd(e.target.value)}
                 style={{ width:'100%', padding:'8px 10px', border:`1px solid ${C.border}`, borderRadius:6, fontSize:13 }} />
          {error && <div style={{ color:C.red, fontSize:11, fontWeight:600 }}>{error}</div>}
        </div>
        <div style={{ padding:'12px 18px', borderTop:`1px solid ${C.border}`, display:'flex', justifyContent:'flex-end', gap:8 }}>
          <Btn variant="outline" size="sm" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" size="sm" onClick={submit} disabled={busy}>{busy?'Extending…':'Extend'}</Btn>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// MyTeam — wired to /manager/team. Each row is an ALLOCATION, so an
// employee appearing on N projects gets N rows. The row key is
// `${employee_id}-${project_id}` so React reconciles correctly.
//
// IMPORTANT: do NOT collapse this back into a `memberProjects` Map
// keyed by employee_id; that breaks the per-row Release/Extend actions
// when an employee is on more than one project.
// ─────────────────────────────────────────────────────────────────
function MyTeam({ onNav }) {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [extendModal, setExtendModal] = useState(null);
  const [toast, setToast] = useState(null);  // { msg, tone }

  function showToast(msg, tone = 'success') {
    setToast({ msg, tone });
    setTimeout(() => setToast(null), 2400);
  }

  async function load() {
    setLoading(true);
    try {
      const mod = await import('../../services/resourceApi');
      const data = await mod.resourceApi.getTeam();
      // Backend returns one row per allocation — map straight to the FE shape.
      const mapped = (Array.isArray(data) ? data : []).map((m) => ({
        id: m.id,                                     // employee_id
        name: m.name,
        role: m.role,
        dept: m.dept,
        email: m.email,
        project_id: m.project_id,
        project_name: m.project_name,
        proj_start: m.proj_start,
        proj_end: m.proj_end,
      }));
      setRows(mapped);
    } catch (ex) {
      showToast(ex?.data?.detail || ex?.message || 'Failed to load team', 'error');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Rows with a project_id are "allocated" team members; rows without are
  // direct reports who don't have an active resource allocation yet. Both
  // belong in the team view — the FE just hides allocation-specific actions
  // for the unallocated rows.
  const allocatedTeam = useMemo(
    () => rows.filter((m) => !!m.project_id),
    [rows],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((m) =>
      (m.name || '').toLowerCase().includes(needle)
      || (m.project_name || '').toLowerCase().includes(needle)
    );
  }, [rows, q]);

  async function handleRelease(memberId, projectId) {
    if (!projectId) return;
    if (!window.confirm('Release this employee from the project?')) return;
    try {
      const mod = await import('../../services/resourceApi');
      await mod.resourceApi.releaseEmployee({
        employee_id: memberId,
        project_id: projectId,
      });
      showToast('Released successfully');
      load();
    } catch (ex) {
      showToast(ex?.data?.detail || ex?.message || 'Release failed', 'error');
    }
  }

  async function handleExtend(memberId, projectId, newEnd) {
    const mod = await import('../../services/resourceApi');
    await mod.resourceApi.extendProject({
      project_id: projectId,
      new_end_date: newEnd,
    });
    showToast('Project extended');
    load();
  }

  return (
    <div>
      <Topbar title="My Team" sub="Manage and view your team members" onNav={onNav} />

      {toast && (
        <div style={{
          position:'fixed', top:80, right:20, zIndex:60,
          padding:'10px 14px', borderRadius:8, fontSize:12, fontWeight:600,
          background: toast.tone === 'error' ? '#fef2f2' : '#f0fdf4',
          color: toast.tone === 'error' ? '#b91c1c' : '#15803d',
          border: toast.tone === 'error' ? '1px solid #fecaca' : '1px solid #bbf7d0',
          boxShadow:'0 6px 12px rgba(0,0,0,0.06)'
        }}>{toast.msg}</div>
      )}

      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
        <div style={{ position:'relative' }}>
          <Search size={14} style={{ position:'absolute', left:12, top:'50%', transform:'translateY(-50%)', color:C.muted }} />
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search members or projects…"
                 style={{ paddingLeft:34, height:36, border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', width:280, fontFamily:"'DM Sans',sans-serif" }} />
        </div>
      </div>

      <div style={{ display:'flex', gap:12, marginBottom:20 }}>
        <Card style={{ flex:1, textAlign:'center', padding:14 }}>
          <div style={{ fontSize:20, fontWeight:800, color:C.blue }}>{rows.length}</div>
          <div style={{ fontSize:11, color:C.muted }}>Total allocations</div>
        </Card>
        <Card style={{ flex:1, textAlign:'center', padding:14 }}>
          <div style={{ fontSize:20, fontWeight:800, color:C.primary }}>{new Set(allocatedTeam.map(m=>m.id)).size}</div>
          <div style={{ fontSize:11, color:C.muted }}>Unique team members</div>
        </Card>
        <Card style={{ flex:1, textAlign:'center', padding:14 }}>
          <div style={{ fontSize:20, fontWeight:800, color:C.yellow }}>{new Set(allocatedTeam.map(m=>m.project_id)).size}</div>
          <div style={{ fontSize:11, color:C.muted }}>Active projects</div>
        </Card>
      </div>

      <Card style={{ padding:0, overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ background:C.light }}>
              {['Member','Project','Dept','Role','Start','End','Actions'].map(h => (
                <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize:11, fontWeight:700, color:C.muted, textTransform:'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} style={{ padding:18, textAlign:'center', color:C.muted, fontSize:12 }}>Loading…</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={7} style={{ padding:18, textAlign:'center', color:C.muted, fontSize:12 }}>No team members in this view.</td></tr>
            )}
            {!loading && filtered.map((m, i) => {
              // Composite key handles two cases:
              //   - allocated row → `${id}-${project_id}` (per-allocation)
              //   - unallocated direct report → `${id}-none` (one per employee)
              const rowKey = `${m.id}-${m.project_id || 'none'}`;
              const isAllocated = !!m.project_id;
              return (
                <tr key={rowKey} style={{ borderTop:`1px solid ${C.border}`, background:i%2===0?'#fff':C.bg }}>
                  <td style={{ padding:'12px 14px' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                      <Av init={(m.name||'').split(' ').map(s=>s[0]).slice(0,2).join('').toUpperCase()} size={34}/>
                      <div>
                        <div style={{ fontWeight:600, fontSize:13 }}>{m.name}</div>
                        <div style={{ fontSize:11, color:C.muted }}>{m.email || '—'}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding:'12px 14px', fontSize:13 }}>
                    {isAllocated ? (
                      <>
                        <div style={{ fontWeight:600 }}>{m.project_name || '—'}</div>
                        <div style={{ fontSize:11, color:C.muted }}>{m.project_id}</div>
                      </>
                    ) : (
                      <Badge color={C.muted} bg={`${C.muted}18`}>Unallocated</Badge>
                    )}
                  </td>
                  <td style={{ padding:'12px 14px', fontSize:13 }}>{m.dept || '—'}</td>
                  <td style={{ padding:'12px 14px', fontSize:13 }}>{m.role || '—'}</td>
                  <td style={{ padding:'12px 14px', fontSize:12, color:C.muted }}>{m.proj_start ? String(m.proj_start).slice(0,10) : '—'}</td>
                  <td style={{ padding:'12px 14px', fontSize:12, color:C.muted }}>{m.proj_end ? String(m.proj_end).slice(0,10) : '—'}</td>
                  <td style={{ padding:'12px 14px' }}>
                    {isAllocated ? (
                      <div style={{ display:'flex', gap:6 }}>
                        {/* Pass the row's own project_id directly — NOT from a
                            shared employee->project map. */}
                        <Btn variant="outline" size="sm" onClick={() => handleRelease(m.id, m.project_id)}>
                          Release
                        </Btn>
                        <Btn variant="primary" size="sm" onClick={() => setExtendModal(m)}>
                          Extend
                        </Btn>
                      </div>
                    ) : (
                      <span style={{ fontSize:11, color:C.muted }}>No active project</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {extendModal && (
        <ExtendProjectModal
          project={extendModal}
          onClose={() => setExtendModal(null)}
          onExtend={handleExtend}
        />
      )}
    </div>
  );
}

// ── Export Attendance Modal ────────────────────────────────────────
function managerWeekRangeFromLog(weekLog) {
  const firstWeek = Array.isArray(weekLog) && weekLog.length > 0 ? weekLog[0]?.days || [] : [];
  if (firstWeek.length >= 7) {
    return { startDate: firstWeek[0].date, endDate: firstWeek[firstWeek.length - 1].date };
  }
  const today = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const toIso = (value) => value.toISOString().slice(0, 10);
  return { startDate: toIso(monday), endDate: toIso(sunday) };
}

function ExportAttendanceModal({ onClose, defaultWeekRange }) {
  const today = new Date();
  const [mode, setMode] = useState('weekly');
  const [startDate, setStartDate]   = useState(defaultWeekRange?.startDate || today.toISOString().slice(0, 10));
  const [endDate, setEndDate]       = useState(defaultWeekRange?.endDate   || today.toISOString().slice(0, 10));
  const [monthVal, setMonthVal]     = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`);
  const [statusFilter, setStatusFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr]   = useState(null);

  const handleDownload = async () => {
    setBusy(true); setErr(null);
    try {
      let csvText, filename;
      if (mode === 'weekly') {
        const params = { start_date: startDate, end_date: endDate };
        if (statusFilter) params.attendance_status = statusFilter;
        csvText  = await managerApi.exportWeekly(params);
        filename = `attendance_${startDate}_${endDate}.csv`;
      } else {
        const [yr, mo] = monthVal.split('-');
        const params = { year: yr, month: mo };
        if (statusFilter) params.attendance_status = statusFilter;
        csvText  = await managerApi.exportMonthly(params);
        filename = `attendance_${yr}_${mo}.csv`;
      }
      triggerCsvDownload(typeof csvText === 'string' ? csvText : '', filename);
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e?.message || 'Export failed, please retry.');
    } finally { setBusy(false); }
  };

  return (
    <div
      style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.45)', display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={onClose}
    >
      <div
        style={{ background:'var(--hrms-surface)', borderRadius:12, padding:28, width:400, maxWidth:'calc(100vw - 32px)', boxShadow:'0 20px 60px rgba(0,0,0,0.18)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
          <h3 style={{ fontSize:16, fontWeight:700, color:'var(--hrms-text)', margin:0 }}>Export Attendance Data</h3>
          <button onClick={onClose} style={{ background:'none', border:'none', cursor:'pointer', color:C.muted, padding:4 }}><X size={18}/></button>
        </div>
        <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:18 }}>
          {[['weekly','Weekly Attendance Data'],['monthly','Monthly Attendance Data']].map(([val, label]) => (
            <label key={val} style={{ display:'flex', alignItems:'center', gap:10, cursor:'pointer', fontSize:13, color:'var(--hrms-text)' }}>
              <input type="radio" name="export-mode" value={val} checked={mode === val} onChange={() => setMode(val)}
                style={{ accentColor:C.primary, width:16, height:16 }} />
              {label}
            </label>
          ))}
        </div>
        {mode === 'weekly' ? (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
            {[['Start Date', startDate, setStartDate],['End Date', endDate, setEndDate]].map(([lbl, val, setter]) => (
              <label key={lbl} style={{ display:'flex', flexDirection:'column', gap:4, fontSize:12, color:C.muted, fontWeight:600 }}>
                {lbl}
                <input type="date" value={val} onChange={(e) => setter(e.target.value)}
                  style={{ padding:'7px 10px', border:`1px solid ${C.border}`, borderRadius:7, fontSize:13, color:'var(--hrms-text)', background:'var(--hrms-surface)', fontFamily:"'DM Sans',sans-serif" }} />
              </label>
            ))}
          </div>
        ) : (
          <label style={{ display:'flex', flexDirection:'column', gap:4, fontSize:12, color:C.muted, fontWeight:600, marginBottom:14 }}>
            Month
            <input type="month" value={monthVal} onChange={(e) => setMonthVal(e.target.value)}
              style={{ padding:'7px 10px', border:`1px solid ${C.border}`, borderRadius:7, fontSize:13, color:'var(--hrms-text)', background:'var(--hrms-surface)', fontFamily:"'DM Sans',sans-serif" }} />
          </label>
        )}
        <label style={{ display:'flex', flexDirection:'column', gap:4, fontSize:12, color:C.muted, fontWeight:600, marginBottom:20 }}>
          Attendance Status <span style={{ fontWeight:400, color:'#94a3b8' }}>(optional)</span>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding:'7px 10px', border:`1px solid ${C.border}`, borderRadius:7, fontSize:13, color:'var(--hrms-text)', background:'var(--hrms-surface)', fontFamily:"'DM Sans',sans-serif" }}>
            <option value="">All statuses</option>
            <option value="present">Present</option>
            <option value="late">Late</option>
            <option value="absent">Absent</option>
            <option value="on_leave">On Leave</option>
            <option value="wfh">WFH</option>
            <option value="half_day">Half Day</option>
          </select>
        </label>
        {err && (
          <div style={{ background:'#FEE2E2', color:'#991b1b', padding:'8px 12px', borderRadius:6, fontSize:12, marginBottom:14 }}>{err}</div>
        )}
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <button onClick={onClose}
            style={{ padding:'9px 18px', borderRadius:8, border:`1px solid ${C.border}`, background:'var(--hrms-surface)', fontSize:13, fontWeight:600, color:C.muted, cursor:'pointer', fontFamily:"'DM Sans',sans-serif" }}>
            Cancel
          </button>
          <button onClick={handleDownload} disabled={busy}
            style={{ padding:'9px 18px', borderRadius:8, border:'none', background: busy ? '#A7F3D0' : C.primary, fontSize:13, fontWeight:700, color:'#fff', cursor: busy ? 'wait' : 'pointer', display:'inline-flex', alignItems:'center', gap:8, fontFamily:"'DM Sans',sans-serif" }}>
            <Download size={14} />
            {busy ? 'Downloading…' : 'Download CSV'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Attendance (now hosts both Attendance + Timesheets via sub-tabs) ──
function Attendance({ onNav, defaultTab = 'attendance' }) {
  const [tab, setTab] = useState(defaultTab);
  useEffect(() => { setTab(defaultTab); }, [defaultTab]);

  // ── Dashboard analytics (summary stats, check-ins, trend) ────────
  const [dashData, setDashData]       = useState(null);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError]     = useState(null);
  const [exportModalOpen, setExportModalOpen] = useState(false);

  // Read-only analytics view by default; edit mode unlocked by button
  const [isEditing, setIsEditing] = useState(false);

  const loadDashboard = () => {
    setDashLoading(true);
    setDashError(null);
    managerApi.attendanceDashboard()
      .then((data) => setDashData(data))
      .catch((err) => setDashError(err?.data?.detail || err?.message || 'Failed to load attendance data'))
      .finally(() => setDashLoading(false));
  };

  // ── Interactive grid state ────────────────────────────────────────
  const [employees, setEmployees]     = useState([]);
  const [gridRows, setGridRows]       = useState([]);
  const [weekStart, setWeekStart]     = useState(() => startOfWeek(new Date()));
  const [gridLoading, setGridLoading] = useState(false);
  const [gridError, setGridError]     = useState(null);
  const [busyCell, setBusyCell]       = useState(null);
  const [toast, setToast]             = useState(null);

  // Team utilization
  const [util, setUtil]               = useState(null);
  const [utilLoading, setUtilLoading] = useState(false);
  const [utilStart, setUtilStart]     = useState(() => { const d = new Date(); d.setDate(1); return fmtIso(d); });
  const [utilEnd, setUtilEnd]         = useState(() => fmtIso(new Date()));

  const flash = (ok, msg) => { setToast({ ok, msg }); setTimeout(() => setToast(null), 2500); };

  const days = useMemo(() => {
    const out = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      out.push(d);
    }
    return out;
  }, [weekStart]);

  const loadGrid = async () => {
    setGridLoading(true);
    setGridError(null);
    try {
      const start = fmtIso(days[0]);
      const end   = fmtIso(days[6]);
      const [team, atts] = await Promise.all([
        managerApi.team(),
        attendanceApi.records({ start, end }),
      ]);
      setEmployees(
        Array.isArray(team)
          ? team.map((m) => ({
              id: m.id,
              full_name: m.full_name || m.name,
              employee_code: m.employee_code,
              employment_status: m.employment_status || 'active',
            }))
          : []
      );
      setGridRows(Array.isArray(atts) ? atts : []);
    } catch (e) {
      setGridError(e?.data?.detail || e?.message || 'Failed to load grid data.');
    } finally {
      setGridLoading(false);
    }
  };

  const loadUtilization = async () => {
    if (!utilStart || !utilEnd) return;
    setUtilLoading(true);
    try {
      const data = await utilizationApi.team({ start: utilStart, end: utilEnd });
      setUtil(data);
    } catch (e) {
      flash(false, e?.data?.detail || e?.message || 'Could not load utilization');
    } finally { setUtilLoading(false); }
  };

  const gridMap = useMemo(() => {
    const m = new Map();
    for (const r of gridRows) m.set(r.employee_id + '-' + r.date, r.status);
    return m;
  }, [gridRows]);

  const cellStatus = (empId, dateIso) => gridMap.get(empId + '-' + dateIso) || 'unmarked';

  const handleCellClick = async (empId, dateIso) => {
    const current = cellStatus(empId, dateIso);
    const next    = cycleNextStatus(current);
    const cellKey = empId + '-' + dateIso;
    setGridRows((prev) => {
      const clone = prev.filter((r) => !(r.employee_id === empId && r.date === dateIso));
      if (next !== null) clone.push({ employee_id: empId, date: dateIso, status: next });
      return clone;
    });
    setBusyCell(cellKey);
    try {
      await attendanceApi.adminOverride({ employee_id: empId, date: dateIso, status: next });
    } catch {
      setGridRows((prev) => {
        const clone = prev.filter((r) => !(r.employee_id === empId && r.date === dateIso));
        if (current !== 'unmarked') clone.push({ employee_id: empId, date: dateIso, status: current });
        return clone;
      });
      flash(false, 'Failed to save — please retry');
    } finally {
      setBusyCell(null);
    }
  };

  const shiftWeek = (delta) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + 7 * delta);
    setWeekStart(d);
  };

  useEffect(() => {
    if (tab === 'attendance') {
      loadDashboard();
      loadGrid();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  useEffect(() => {
    if (tab === 'attendance') loadGrid();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekStart]);

  useEffect(() => {
    if (tab !== 'attendance') return;
    const id = setInterval(loadDashboard, 60_000);
    return () => clearInterval(id);
  }, [tab]);

  useEffect(() => {
    if (tab === 'attendance') loadUtilization();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // ── Derived dashboard values ──────────────────────────────────────
  const summary  = dashData?.summary         || {};
  const checkins = dashData?.todays_checkins || [];
  const trend    = dashData?.weekly_trend    || [];
  const weekLog  = dashData?.week_log        || [];
  const teamSize = summary.team_size ?? 0;
  const weekRange = managerWeekRangeFromLog(weekLog);
  const trendMax  = Math.max(...trend.map((t) => t.present), 1);

  const ATT_ABB = {
    present:  { label: 'P',   title: 'Present',   color: '#047857', bg: '#D1FAE5' },
    late:     { label: 'L',   title: 'Late',      color: '#B45309', bg: '#FEF3C7' },
    wfh:      { label: 'WFH', title: 'WFH',       color: '#0369A1', bg: '#E0F2FE' },
    on_leave: { label: 'OL',  title: 'On Leave',  color: '#6D28D9', bg: '#EDE9FE' },
    half_day: { label: 'HD',  title: 'Half Day',  color: '#C2410C', bg: '#FFEDD5' },
    holiday:  { label: 'H',   title: 'Holiday',   color: '#0E7490', bg: '#CFFAFE' },
    absent:   { label: 'A',   title: 'Absent',    color: '#B91C1C', bg: '#FEE2E2' },
  };
  const attAbb = (s) => ATT_ABB[(s || '').toLowerCase()] || { label: '–', title: 'Unknown', color: '#94A3B8', bg: 'var(--hrms-surface-2)' };

  const STATUS_META = {
    present:  { label:'P',  color: C.primary },
    late:     { label:'L',  color: C.yellow  },
    half_day: { label:'HD', color: C.accent  },
    on_leave: { label:'OL', color: C.purple  },
    holiday:  { label:'H',  color: C.blue    },
    wfh:      { label:'WF', color: C.blue    },
    absent:   { label:'A',  color: C.red     },
  };
  const statusMeta = (s) => STATUS_META[s] || { label:'—', color: C.muted };

  return (
    <div>
      <Topbar
        title="Attendance"
        sub={tab === 'timesheets'
          ? "Review your team's submitted timesheets"
          : isEditing
            ? "Editing team attendance — click any cell to cycle its status"
            : "Team attendance overview — your direct reports only"}
        onNav={onNav}
      />

      {/* Sub-tab strip */}
      <div style={{ display:'flex', gap:4, marginBottom:18, borderBottom:`1px solid ${C.border}` }}>
        {[['attendance','Attendance'],['timesheets','Timesheets']].map(([id, label]) => {
          const active = tab === id;
          return (
            <button key={id} type="button" onClick={() => setTab(id)}
              style={{ padding:'10px 18px', fontSize:13, fontWeight:600, background:'transparent', border:'none',
                borderBottom: active ? `2px solid ${C.primary}` : '2px solid transparent',
                color: active ? C.primary : C.muted, cursor:'pointer', fontFamily:"'DM Sans',sans-serif", marginBottom:-1 }}>
              {label}
            </button>
          );
        })}
      </div>

      {tab === 'timesheets' && <ManagerTimesheetReviewPage />}

      {tab === 'attendance' && (
      <>
        {/* Edit mode banner */}
        {isEditing && (
          <div data-testid="edit-mode-banner" style={{
            background: 'linear-gradient(135deg,#FFFBEB,#FEF3C7)',
            border: '1px solid #FDE68A', borderRadius: 10,
            padding: '12px 18px', marginBottom: 20, color: '#92400E',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
              width:28, height:28, borderRadius:8, background:'#FDE68A', flexShrink:0 }}>
              <Edit size={14} />
            </div>
            <div>
              <div style={{ fontWeight:700, fontSize:13 }}>Editing Team Attendance</div>
              <div style={{ fontSize:11, color:'#B45309', marginTop:1 }}>
                Click any cell to cycle its status · changes apply to your direct reports only
              </div>
            </div>
          </div>
        )}

        {/* Dashboard error */}
        {dashError && (
          <div style={{ background:'#FEE2E2', color:C.red, padding:'10px 16px', borderRadius:8, marginBottom:16, fontSize:13 }}>
            {dashError} — <button onClick={loadDashboard} style={{ background:'none', border:'none', color:C.red, cursor:'pointer', fontWeight:600, textDecoration:'underline' }}>Retry</button>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div style={{ background: toast.ok ? '#ECFDF5' : '#FEE2E2', color: toast.ok ? '#065F46' : C.red,
            padding:'10px 16px', borderRadius:8, marginBottom:16, fontSize:13 }}>
            {toast.msg}
          </div>
        )}

        {/* Summary stats */}
        <div style={{ display:'flex', gap:16, marginBottom:28, flexWrap:'wrap' }}>
          <Stat icon={UserCheck} label="Present Today"
            value={dashLoading ? '…' : `${summary.present ?? 0}/${teamSize}`}
            sub={teamSize ? `${Math.round(((summary.present??0)/Math.max(teamSize,1))*100)}% of team` : 'Loading…'} />
          <Stat icon={Home} label="On Leave"
            value={dashLoading ? '…' : String(summary.on_leave ?? 0)}
            sub="Approved leaves" subColor={C.yellow} />
          <Stat icon={Activity} label="WFH"
            value={dashLoading ? '…' : String(summary.wfh ?? 0)}
            sub="Working remotely" subColor={C.blue} />
          <Stat icon={X} label="Absent"
            value={dashLoading ? '…' : String(summary.absent ?? 0)}
            sub="Unplanned absence" subColor={C.red} />
          {(summary.half_day ?? 0) > 0 && (
            <Stat icon={Clock} label="Half Day"
              value={String(summary.half_day)}
              sub="Short sessions" subColor={C.accent} />
          )}
        </div>

        {/* Week navigation + Edit toggle + Export */}
        <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:20, flexWrap:'wrap' }}>
          <div style={{ display:'flex', alignItems:'center', gap:6 }}>
            <button type="button" onClick={() => shiftWeek(-1)}
              style={{ display:'inline-flex', alignItems:'center', gap:4, height:36,
                padding:'0 14px', fontSize:12, fontWeight:600, border:`1px solid ${C.border}`,
                borderRadius:8, background:'var(--hrms-surface)', cursor:'pointer', color:C.text,
                fontFamily:"'DM Sans',sans-serif", whiteSpace:'nowrap' }}>
              ← Prev
            </button>
            <button type="button" onClick={() => setWeekStart(startOfWeek(new Date()))}
              style={{ display:'inline-flex', alignItems:'center', height:36,
                padding:'0 14px', fontSize:12, fontWeight:700, border:`1px solid ${C.primary}`,
                borderRadius:8, background:`${C.primary}10`, cursor:'pointer', color:C.primary,
                fontFamily:"'DM Sans',sans-serif" }}>
              Today
            </button>
            <button type="button" onClick={() => shiftWeek(1)}
              style={{ display:'inline-flex', alignItems:'center', gap:4, height:36,
                padding:'0 14px', fontSize:12, fontWeight:600, border:`1px solid ${C.border}`,
                borderRadius:8, background:'var(--hrms-surface)', cursor:'pointer', color:C.text,
                fontFamily:"'DM Sans',sans-serif", whiteSpace:'nowrap' }}>
              Next →
            </button>
          </div>
          <span style={{ fontSize:12, color:C.muted, fontWeight:500, paddingLeft:4 }}>
            {days[0] && days[6] && (
              <>
                {days[0].toLocaleDateString('en-IN', { day:'2-digit', month:'short' })}
                {' — '}
                {days[6].toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}
              </>
            )}
          </span>
          <div style={{ flex:1 }} />
          {(dashLoading || gridLoading) && (
            <span style={{ fontSize:11, color:C.muted, fontStyle:'italic' }}>Refreshing…</span>
          )}
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <button type="button" data-testid="edit-attendance-toggle"
              onClick={() => setIsEditing((v) => !v)}
              style={{ display:'inline-flex', alignItems:'center', gap:6, height:36,
                border: isEditing ? `1px solid ${C.red}` : `1px solid ${C.primary}`,
                borderRadius:8, background: isEditing ? '#FEF2F2' : '#ECFDF5',
                color: isEditing ? C.red : C.primaryDark,
                padding:'0 16px', fontSize:12, fontWeight:700,
                cursor:'pointer', fontFamily:"'DM Sans',sans-serif", whiteSpace:'nowrap' }}>
              <Edit size={13} />
              {isEditing ? 'Done Editing' : 'Edit Attendance'}
            </button>
            <button type="button" onClick={() => setExportModalOpen(true)}
              aria-label="Export attendance data as CSV"
              style={{ display:'inline-flex', alignItems:'center', gap:6, height:36,
                border:'1px solid #A7F3D0', borderRadius:8, background:'#ECFDF5',
                color:'#065F46', padding:'0 14px', fontSize:12, fontWeight:700,
                cursor:'pointer', fontFamily:"'DM Sans',sans-serif", whiteSpace:'nowrap' }}>
              <Download size={14} />
              Export CSV
            </button>
          </div>
        </div>

        {/* Read-only analytics: week attendance log */}
        {!isEditing && (
          <div data-testid="analytics-view">
            <Card style={{ padding:0, overflow:'hidden', marginBottom:20 }}>
              <div style={{ padding:'14px 20px', borderBottom:`1px solid ${C.border}`,
                display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <div>
                  <div style={{ fontWeight:700, fontSize:15, color:C.text }}>Week Attendance Log</div>
                  <div style={{ fontSize:11, color:C.muted, marginTop:2 }}>
                    Your direct reports · read-only view
                  </div>
                </div>
                {!dashLoading && weekLog.length > 0 && (
                  <span style={{ fontSize:11, color:C.muted, background:C.light,
                    padding:'3px 10px', borderRadius:999, fontWeight:600 }}>
                    {weekLog.length} member{weekLog.length !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              {dashLoading && weekLog.length === 0 ? (
                <div style={{ padding:'24px 20px', color:C.muted, fontSize:13 }}>Loading…</div>
              ) : weekLog.length === 0 ? (
                <div style={{ padding:'24px 20px', color:C.muted, fontSize:13 }}>No team members found.</div>
              ) : (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                    <thead>
                      <tr style={{ background:C.light, borderBottom:`1px solid ${C.border}` }}>
                        <th style={{ padding:'10px 20px', textAlign:'left', fontWeight:700,
                          fontSize:10, color:C.muted, textTransform:'uppercase', letterSpacing:'0.05em',
                          minWidth:160 }}>Employee</th>
                        {weekLog[0]?.days.map((d) => {
                          const dt = new Date(d.date + 'T00:00:00');
                          const isToday = d.date === new Date().toISOString().slice(0,10);
                          return (
                            <th key={d.date} style={{ padding:'8px 6px', textAlign:'center',
                              minWidth:60, background: isToday ? '#F0FDF4' : 'transparent' }}>
                              <div style={{ fontWeight:700, fontSize:10, color: isToday ? C.primary : C.muted,
                                textTransform:'uppercase', letterSpacing:'0.04em' }}>
                                {dt.toLocaleDateString('en-IN', { weekday:'short' })}
                              </div>
                              <div style={{ fontWeight:500, fontSize:10, color: isToday ? C.primaryDark : '#94A3B8',
                                marginTop:1 }}>
                                {dt.toLocaleDateString('en-IN', { day:'2-digit', month:'short' })}
                              </div>
                            </th>
                          );
                        })}
                        <th style={{ padding:'10px 20px', textAlign:'right', fontWeight:700,
                          fontSize:10, color:C.muted, textTransform:'uppercase', letterSpacing:'0.05em' }}>Hrs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {weekLog.map((row) => (
                        <tr key={row.employee_id} style={{ borderTop:`1px solid ${C.border}` }}>
                          <td style={{ padding:'10px 20px', fontWeight:600, fontSize:13, color:C.text }}>{row.name}</td>
                          {row.days.map((d) => {
                            const a = attAbb(d.status);
                            const isToday = d.date === new Date().toISOString().slice(0,10);
                            return (
                              <td key={d.date} style={{ padding:'8px 6px', textAlign:'center',
                                background: isToday ? '#F0FDF4' : 'transparent' }}>
                                <span title={a.title}
                                  style={{
                                    display:'inline-flex', alignItems:'center', justifyContent:'center',
                                    minWidth:32, padding:'3px 7px', borderRadius:6, fontSize:10, fontWeight:700,
                                    color: a.color, background: a.bg,
                                    letterSpacing:'0.02em', cursor:'default',
                                  }}>{a.label}</span>
                              </td>
                            );
                          })}
                          <td style={{ padding:'10px 20px', textAlign:'right', fontWeight:700,
                            fontSize:12, color:C.text }}>{row.total_hours}h</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* Edit mode: interactive attendance grid */}
        {isEditing && (
          <>
            {gridError && (
              <div style={{ background:'#FEE2E2', color:C.red, padding:'10px 16px', borderRadius:8, marginBottom:16, fontSize:13 }}>
                {gridError} — <button onClick={loadGrid} style={{ background:'none', border:'none', color:C.red, cursor:'pointer', fontWeight:600, textDecoration:'underline' }}>Retry</button>
              </div>
            )}
            <AttendanceGrid
              employees={employees}
              days={days}
              cellStatus={cellStatus}
              busyCell={busyCell}
              onCellClick={handleCellClick}
              loading={gridLoading}
              readOnly={false}
            />
          </>
        )}

        {/* Below: Weekly trend + Today's check-ins */}
        <div style={{ display:'flex', gap:16, marginTop:24, flexWrap:'wrap' }}>
          <Card style={{ flex:1, minWidth:240, padding:20 }}>
            <div style={{ fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Weekly Summary</div>
            <div style={{ fontSize:11, color:C.muted, marginBottom:16 }}>Daily present count — last 7 days</div>
            {trend.length === 0 && dashLoading
              ? <div style={{ color:C.muted, fontSize:12 }}>Loading…</div>
              : trend.length === 0
                ? <div style={{ color:C.muted, fontSize:12 }}>No trend data available.</div>
                : trend.map((d) => {
                    const label = new Date(d.date).toLocaleDateString('en-IN', { day:'2-digit', month:'short' });
                    const pct   = Math.round((d.present / trendMax) * 100);
                    return (
                      <div key={d.date} style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
                        <span style={{ fontSize:11, color:C.muted, width:56, flexShrink:0, fontWeight:500 }}>{label}</span>
                        <div style={{ flex:1, height:8, background:C.light, borderRadius:99, overflow:'hidden' }}>
                          <div style={{ width:`${pct}%`, height:'100%',
                            background:`linear-gradient(90deg,${C.primary},${C.primaryDark})`,
                            borderRadius:99, transition:'width 0.4s ease' }} />
                        </div>
                        <span style={{ fontSize:11, fontWeight:700, color:C.text, width:24, textAlign:'right' }}>{d.present}</span>
                      </div>
                    );
                  })
            }
          </Card>

          <Card style={{ flex:1, minWidth:240, padding:20 }}>
            <div style={{ fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Today's Check-ins</div>
            <div style={{ fontSize:11, color:C.muted, marginBottom:16 }}>
              {checkins.length > 0 ? `${checkins.length} checked in so far` : 'Check-in activity'}
            </div>
            {checkins.length === 0 && !dashLoading && (
              <div style={{ color:C.muted, fontSize:12, padding:'12px 0' }}>No check-ins recorded yet today.</div>
            )}
            {dashLoading && checkins.length === 0 && (
              <div style={{ color:C.muted, fontSize:12 }}>Loading…</div>
            )}
            {checkins.slice(0, 6).map((c) => {
              const initials = c.name.split(' ').filter(Boolean).map((s) => s[0]).slice(0,2).join('').toUpperCase();
              const m = statusMeta(c.status);
              return (
                <div key={c.employee_id} style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12,
                  paddingBottom:12, borderBottom:`1px solid ${C.border}` }}>
                  <Av init={initials} size={32} />
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:C.text, overflow:'hidden',
                      textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{c.name}</div>
                    <div style={{ fontSize:10, color:C.muted, marginTop:1 }}>Checked in at {c.check_in_time}</div>
                  </div>
                  <Badge color={m.color} bg={`${m.color}18`}>{c.status === 'late' ? 'Late' : 'Present'}</Badge>
                </div>
              );
            })}
            {checkins.length > 6 && (
              <div style={{ fontSize:11, color:C.muted, textAlign:'center', paddingTop:4 }}>
                +{checkins.length - 6} more
              </div>
            )}
          </Card>
        </div>

        {/* Team Utilization */}
        <Card style={{ padding:0, overflow:'hidden', marginTop:20 }}>
          <div style={{ padding:'14px 20px', borderBottom:`1px solid ${C.border}`,
            display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:10 }}>
            <div>
              <div style={{ fontWeight:700, fontSize:15, color:C.text }}>Team Utilization</div>
              <div style={{ fontSize:11, color:C.muted, marginTop:2 }}>Billable hours and availability for your direct reports</div>
            </div>
            <div style={{ display:'flex', gap:8, alignItems:'flex-end', flexWrap:'wrap' }}>
              <div>
                <label style={{ fontSize:10, fontWeight:700, color:C.muted, display:'block', marginBottom:4,
                  textTransform:'uppercase', letterSpacing:'0.05em' }}>From</label>
                <input type="date" value={utilStart} onChange={(e) => setUtilStart(e.target.value)}
                  style={{ padding:'6px 10px', border:`1px solid ${C.border}`, borderRadius:8,
                    fontSize:12, background:'var(--hrms-surface)', color:C.text, fontFamily:"'DM Sans',sans-serif" }} />
              </div>
              <div>
                <label style={{ fontSize:10, fontWeight:700, color:C.muted, display:'block', marginBottom:4,
                  textTransform:'uppercase', letterSpacing:'0.05em' }}>To</label>
                <input type="date" value={utilEnd} onChange={(e) => setUtilEnd(e.target.value)}
                  style={{ padding:'6px 10px', border:`1px solid ${C.border}`, borderRadius:8,
                    fontSize:12, background:'var(--hrms-surface)', color:C.text, fontFamily:"'DM Sans',sans-serif" }} />
              </div>
              <button onClick={loadUtilization} disabled={utilLoading}
                style={{ padding:'7px 16px', background:C.blue, color:'#fff', border:'none',
                  borderRadius:8, fontSize:12, fontWeight:700, cursor:'pointer',
                  fontFamily:"'DM Sans',sans-serif", height:34 }}>
                {utilLoading ? 'Loading…' : 'Refresh'}
              </button>
            </div>
          </div>

          {util ? (
            <>
              <div style={{ display:'flex', gap:12, padding:'16px 20px', flexWrap:'wrap', borderBottom:`1px solid ${C.border}` }}>
                {[
                  { label:'Employees',      value: util.total_employees,                   color:C.blue,    bg:'#EFF6FF' },
                  { label:'Billable Hours', value: util.billable_hours.toFixed(1) + ' h',  color:'#047857', bg:'#ECFDF5' },
                  { label:'Utilization %',  value: util.utilization_pct.toFixed(1) + '%',  color:C.purple,  bg:'#EDE9FE' },
                  { label:'Underutilized',  value: util.underutilized,                      color:C.yellow,  bg:'#FEF3C7' },
                  { label:'Missing TS',     value: util.missing_submissions,                color:C.red,     bg:'#FEE2E2' },
                ].map((s) => (
                  <div key={s.label} style={{ flex:1, minWidth:100, padding:'12px 14px', borderRadius:10,
                    background:s.bg, textAlign:'center' }}>
                    <div style={{ fontSize:20, fontWeight:800, color:s.color }}>{s.value}</div>
                    <div style={{ fontSize:10, color:C.muted, marginTop:2, fontWeight:600 }}>{s.label}</div>
                  </div>
                ))}
              </div>
              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead>
                    <tr style={{ background:C.light, borderBottom:`1px solid ${C.border}` }}>
                      {['Employee','Department','Available','Logged','Billable','Non-Bill','Utilization','Status'].map((h) => (
                        <th key={h} style={{ padding:'10px 14px', textAlign:'left',
                          fontSize:10, fontWeight:700, color:C.muted,
                          textTransform:'uppercase', letterSpacing:'0.04em', whiteSpace:'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(util.employees || []).map((emp) => {
                      const pct      = emp.utilization_pct;
                      const barColor = pct >= 80 ? C.primary : pct >= 60 ? C.yellow : C.red;
                      const alert    = pct > 100 ? '🔴 Overallocated' : pct < 60 ? '🟡 Underutilized' : '🟢 On track';
                      return (
                        <tr key={emp.employee_id} style={{ borderTop:`1px solid ${C.border}` }}>
                          <td style={{ padding:'10px 14px' }}>
                            <div style={{ fontWeight:600, fontSize:13, color:C.text }}>{emp.employee_name}</div>
                            {emp.designation && <div style={{ fontSize:10, color:'#94A3B8', marginTop:1 }}>{emp.designation}</div>}
                            {emp.missing_timesheet && (
                              <span style={{ fontSize:9, fontWeight:700, background:'#FEE2E2', color:C.red,
                                padding:'1px 5px', borderRadius:4, display:'inline-block', marginTop:2 }}>No TS</span>
                            )}
                          </td>
                          <td style={{ padding:'10px 14px', fontSize:12, color:C.muted }}>{emp.department || '—'}</td>
                          <td style={{ padding:'10px 14px', fontSize:12, color:C.muted }}>{emp.available_hours.toFixed(0)}h</td>
                          <td style={{ padding:'10px 14px', fontSize:12, fontWeight:600, color:C.text }}>{emp.total_logged_hours.toFixed(1)}h</td>
                          <td style={{ padding:'10px 14px', fontSize:12, fontWeight:700, color:'#047857' }}>{emp.billable_hours.toFixed(1)}h</td>
                          <td style={{ padding:'10px 14px', fontSize:12, color:'#B45309' }}>{emp.non_billable_hours.toFixed(1)}h</td>
                          <td style={{ padding:'10px 14px', minWidth:120 }}>
                            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                              <div style={{ flex:1, height:6, background:C.light, borderRadius:3, overflow:'hidden' }}>
                                <div style={{ height:'100%', width:`${Math.min(pct,100)}%`,
                                  background:barColor, borderRadius:3, transition:'width 0.4s' }} />
                              </div>
                              <span style={{ fontSize:11, fontWeight:700, color:barColor, minWidth:36 }}>
                                {pct.toFixed(0)}%
                              </span>
                            </div>
                          </td>
                          <td style={{ padding:'10px 14px', fontSize:11 }}>{alert}</td>
                        </tr>
                      );
                    })}
                    {(util.employees || []).length === 0 && (
                      <tr>
                        <td colSpan={8} style={{ padding:24, textAlign:'center', color:C.muted, fontSize:13 }}>
                          No employees found for this period.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : utilLoading ? (
            <div style={{ padding:'32px 20px', textAlign:'center', color:C.muted, fontSize:13 }}>
              Loading utilization data…
            </div>
          ) : (
            <div style={{ padding:'32px 20px', textAlign:'center', color:C.muted, fontSize:13 }}>
              Select a date range and click Refresh to load team utilization data.
            </div>
          )}
        </Card>
      </>
      )}

      {exportModalOpen && (
        <ExportAttendanceModal
          onClose={() => setExportModalOpen(false)}
          defaultWeekRange={weekRange}
        />
      )}
    </div>
  );
}

// ── Leave Requests ────────────────────────────────────────────────
function LeaveRequests({ onNav }) {
  const leaves = [
    { ...MEMBERS[0], type:'Sick Leave',    from:'Oct 25', to:'Oct 26', days:2, reason:'Fever and rest',    status:'Pending' },
    { ...MEMBERS[2], type:'Work From Home',from:'Oct 27', to:'Oct 27', days:1, reason:'Home renovation',   status:'Approved' },
    { ...MEMBERS[5], type:'Medical Leave', from:'Oct 28', to:'Oct 30', days:3, reason:'Dental surgery',    status:'Approved' },
    { ...MEMBERS[6], type:'Personal Day',  from:'Oct 25', to:'Oct 25', days:1, reason:'Family event',      status:'Pending' },
    { ...MEMBERS[1], type:'Annual Leave',  from:'Nov 5',  to:'Nov 8',  days:4, reason:'Vacation trip',     status:'Pending' },
  ]
  const sc = { Pending:C.yellow, Approved:C.primary, Rejected:C.red }
  return (
    <div>
      <Topbar title="Leave Requests" sub="Manage team leave applications" onNav={onNav} />
      <div style={{ display:'flex', gap:14, marginBottom:20 }}>
        {[['Total','12',C.blue],['Pending','5',C.yellow],['Approved','6',C.primary],['Rejected','1',C.red]].map(([l,v,c])=>(
          <Card key={l} style={{ flex:1, textAlign:'center', padding:14 }}><div style={{ fontSize:20, fontWeight:800, color:c }}>{v}</div><div style={{ fontSize:11, color:C.muted }}>{l}</div></Card>
        ))}
      </div>
      <Card style={{ marginBottom:16, background:'linear-gradient(135deg,#ECFDF5,#D1FAE5)', border:'1px solid #A7F3D0' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <div><div style={{ fontWeight:700, fontSize:14 }}>⚠️ Overlap Alert: Nov 12–15</div><div style={{ fontSize:12, color:C.muted, marginTop:4 }}>3 team members have overlapping leaves. May impact Nov 14 delivery.</div></div>
          <Btn variant="primary" onClick={() => onNav('attendance')}>View Calendar</Btn>
        </div>
      </Card>
      <Card style={{ padding:0, overflow:'hidden' }}>
        <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between' }}>
          <span style={{ fontWeight:700, fontSize:15 }}>Leave Applications</span>
          <Btn variant="primary" size="sm"><Plus size={13}/>New Leave</Btn>
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ background:C.light }}>{['Employee','Type','Duration','Days','Reason','Status','Actions'].map(h=><th key={h} style={{ padding:'9px 14px', textAlign:'left', fontSize:11, fontWeight:700, color:C.muted }}>{h}</th>)}</tr></thead>
          <tbody>
            {leaves.map((l,i)=>(
              <tr key={i} style={{ borderTop:`1px solid ${C.border}` }}>
                <td style={{ padding:'11px 14px' }}><div style={{ display:'flex', alignItems:'center', gap:8 }}><Av init={l.av} size={30}/><span style={{ fontSize:12, fontWeight:600 }}>{l.name}</span></div></td>
                <td style={{ padding:'11px 14px', fontSize:12 }}>{l.type}</td>
                <td style={{ padding:'11px 14px', fontSize:12, color:C.muted }}>{l.from} → {l.to}</td>
                <td style={{ padding:'11px 14px', fontSize:12, fontWeight:700 }}>{l.days}d</td>
                <td style={{ padding:'11px 14px', fontSize:12, color:C.muted }}>{l.reason}</td>
                <td style={{ padding:'11px 14px' }}><Badge color={sc[l.status]} bg={`${sc[l.status]}18`}>{l.status}</Badge></td>
                <td style={{ padding:'11px 14px' }}>{l.status==='Pending'?<div style={{ display:'flex', gap:5 }}><Btn variant="danger" size="sm">Reject</Btn><Btn variant="primary" size="sm">Approve</Btn></div>:<Btn variant="ghost" size="sm"><Eye size={12}/></Btn>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

// The previous local `ApprovalsPage` (hard-coded with Elena / Marcus / Sarah
// rows) was deleted. The /approvals route is served by the live
// ManagerApprovalsPage component imported at the top of this file — it pulls
// pending leave / cancellation / comp-off / regularization items straight from
// the API.

// Tiny inline icons used by the Under-Construction sub-pages below.
const __mgrIcoChart = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>);
const __mgrIcoStar  = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>);
const __mgrIcoTarget= (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>);
const __mgrIcoFolder= (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>);
const __mgrIcoUsers = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>);
const __mgrIcoActivity = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>);
const __mgrIcoCal   = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>);
const __mgrIcoDoc   = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>);

// ── Performance ───────────────────────────────────────────────────
function Performance({ onNav: _onNav }) {
  return <ManagerPerformancePage />;
}

// ── Timesheets ────────────────────────────────────────────────────
function Timesheets({ onNav }) {
  return (
    <div>
      <Topbar title="Timesheets" sub={(() => { const t = new Date(); const dow = (t.getDay()+6)%7; const m = new Date(t); m.setDate(t.getDate()-dow); const s = new Date(m); s.setDate(m.getDate()+6); const fmt = (d) => d.toLocaleDateString("en-IN", { month: "short", day: "numeric" }); const oneJan = new Date(t.getFullYear(),0,1); const wk = Math.ceil((((t - oneJan) / 86400000) + oneJan.getDay()+1)/7); return `Week ${wk} · ${fmt(m)} - ${fmt(s)}, ${s.getFullYear()}`; })()} onNav={onNav} />
      <div style={{ display:'flex', gap:14, marginBottom:24 }}>
        <Stat icon={Clock}    label="Expected" value="960h"/>
        <Stat icon={Activity} label="Logged"   value="816h" sub="85% submitted"/>
        <Stat icon={AlertTriangle} label="Pending" value="4" subColor={C.yellow}/>
        <Stat icon={Check}    label="Approved" value="18"/>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 260px', gap:20 }}>
        <Card style={{ padding:0, overflow:'hidden' }}>
          <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between' }}>
            <span style={{ fontWeight:700, fontSize:15 }}>Timesheet Submissions</span>
            <div style={{ display:'flex', gap:8 }}><Btn variant="outline" size="sm"><ChevronLeft size={12}/>Prev</Btn><Btn variant="outline" size="sm">Next<ChevronRight size={12}/></Btn><Btn variant="outline" size="sm"><Download size={12}/></Btn></div>
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ background:C.light }}>{['Employee','Mon','Tue','Wed','Thu','Fri','Total','Status',''].map(h=><th key={h} style={{ padding:'9px 12px', textAlign:'center', fontSize:11, fontWeight:700, color:C.muted }}>{h}</th>)}</tr></thead>
            <tbody>
              {MEMBERS.map((m,i)=>(
                <tr key={m.id} style={{ borderTop:`1px solid ${C.border}`, background:i%2===0?'#fff':C.bg }}>
                  <td style={{ padding:'10px 12px' }}><div style={{ display:'flex', alignItems:'center', gap:8 }}><Av init={m.av} size={28}/><span style={{ fontSize:12, fontWeight:600 }}>{m.name}</span></div></td>
                  {[8,8,8,8,8].map((h,j)=><td key={j} style={{ padding:'10px 12px', textAlign:'center', fontSize:12 }}>{h}h</td>)}
                  <td style={{ padding:'10px 12px', textAlign:'center', fontWeight:700, fontSize:12 }}>40h</td>
                  <td style={{ padding:'10px 12px', textAlign:'center' }}><Badge color={i<5?C.primary:C.yellow} bg={i<5?'#D1FAE5':'#FEF3C7'}>{i<5?'Submitted':'Pending'}</Badge></td>
                  <td style={{ padding:'10px 12px', textAlign:'center' }}><div style={{ display:'flex', gap:4, justifyContent:'center' }}><Btn variant="ghost" size="sm"><Eye size={12}/></Btn>{i>=5&&<Btn variant="primary" size="sm">Approve</Btn>}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          <Card>
            <div style={{ fontWeight:700, fontSize:14, marginBottom:4 }}>Submission</div>
            <div style={{ position:'relative', width:90, height:90, margin:'12px auto' }}>
              <svg viewBox="0 0 90 90"><circle cx="45" cy="45" r="36" fill="none" stroke={C.light} strokeWidth="8"/><circle cx="45" cy="45" r="36" fill="none" stroke={C.primary} strokeWidth="8" strokeDasharray={`${0.85*226} ${226}`} strokeLinecap="round" transform="rotate(-90 45 45)"/></svg>
              <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
                <span style={{ fontSize:18, fontWeight:800 }}>85%</span>
                <span style={{ fontSize:9, color:C.muted }}>Submitted</span>
              </div>
            </div>
          </Card>
          <Card>
            <div style={{ fontWeight:700, fontSize:14, marginBottom:12 }}>By Department</div>
            {[['Design','120h',C.purple,62],['Engineering','480h',C.blue,100],['Product','216h',C.primary,44]].map(([d,h,c,p])=>(
              <div key={d} style={{ marginBottom:12 }}>
                <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:4 }}><span>{d}</span><span style={{ fontWeight:700, color:c }}>{h}</span></div>
                <div style={{ background:C.light, borderRadius:4, height:6 }}><div style={{ width:`${p}%`, background:c, height:'100%', borderRadius:4 }}/></div>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  )
}

// ── Projects ──────────────────────────────────────────────────────
function Projects({ onNav: _onNav }) {
  return (
    <UnderConstruction
      accent="violet"
      title="Projects"
      description="Track ongoing and completed projects with team allocation, progress, and deadlines."
      features={[
        { label: 'Project pipeline view',   icon: __mgrIcoFolder },
        { label: 'Team allocation tracker', icon: __mgrIcoUsers },
        { label: 'Progress reports',        icon: __mgrIcoActivity },
      ]}
    />
  );
}

// ── Reports ───────────────────────────────────────────────────────
function Reports({ onNav: _onNav }) {
  return (
    <UnderConstruction
      accent="amber"
      title="Team Reports"
      description="Analytics across attendance, leave, timesheets, and team productivity — all exportable."
      features={[
        { label: 'Attendance & leave reports', icon: __mgrIcoCal },
        { label: 'Timesheet analytics',        icon: __mgrIcoActivity },
        { label: 'Custom export builder',      icon: __mgrIcoDoc },
      ]}
    />
  );
}

// ── Team Chat ─────────────────────────────────────────────────────
function TeamChat({ onNav }) {
  const [msg, setMsg] = useState('')
  const [chan, setChan] = useState('# general')
  const msgs = [
    { av:'ER', name:'Elena Rodriguez', time:'9:12 AM', text:"Morning! Just pushed new design system components. Can someone review?" },
    { av:'MC', name:'Marcus Chen',     time:'9:15 AM', text:'On it! Looks great so far. I\'ll check the API integration too.' },
    { av:'SJ', name:'Sarah Jenkins',   time:'9:20 AM', text:'Amazing work Elena! Let\'s schedule a quick review call this afternoon?' },
    { av:'AG', name:'Arjun Gupta',     time:'9:35 AM', text:'CI pipeline updated. All tests passing ✅' },
    { av:'AR', name:'You',             time:'9:40 AM', text:'Great progress team! Let\'s sync at 3pm for standup.', me:true },
  ]
  return (
    <div>
      <Topbar title="Team Chat" sub="Collaborate with your team in real-time" onNav={onNav} />
      <div style={{ display:'grid', gridTemplateColumns:'200px 1fr 240px', gap:0, height:'68vh', borderRadius:12, overflow:'hidden', border:`1px solid ${C.border}` }}>
        <div style={{ background:C.sidebar, padding:'14px 0' }}>
          <div style={{ padding:'0 14px 10px', fontSize:10, color:'#64748B', fontWeight:700, textTransform:'uppercase' }}>Channels</div>
          {['# general','# design','# engineering','# announcements'].map(c=>(
            <button key={c} onClick={()=>setChan(c)} style={{ width:'100%', padding:'7px 14px', background:c===chan?'#1E293B':'transparent', color:c===chan?'#fff':'#94A3B8', border:'none', cursor:'pointer', textAlign:'left', fontSize:12, fontFamily:"'DM Sans',sans-serif" }}>{c}</button>
          ))}
          <div style={{ padding:'14px 14px 8px', fontSize:10, color:'#64748B', fontWeight:700, textTransform:'uppercase' }}>Direct</div>
          {MEMBERS.slice(0,5).map(m=>(
            <button key={m.id} style={{ width:'100%', padding:'5px 14px', background:'transparent', color:'#94A3B8', border:'none', cursor:'pointer', textAlign:'left', fontSize:12, display:'flex', alignItems:'center', gap:6, fontFamily:"'DM Sans',sans-serif" }}>
              <div style={{ width:7, height:7, borderRadius:'50%', background:m.status==='Present'?C.primary:C.muted }}/>
              {m.name.split(' ')[0]}
            </button>
          ))}
        </div>
        <div style={{ display:'flex', flexDirection:'column', background: C.card }}>
          <div style={{ padding:'12px 18px', borderBottom:`1px solid ${C.border}`, fontWeight:700, fontSize:14 }}>{chan}</div>
          <div style={{ flex:1, overflowY:'auto', padding:'14px 18px', display:'flex', flexDirection:'column', gap:14 }}>
            {msgs.map((m,i)=>(
              <div key={i} style={{ display:'flex', gap:10, flexDirection:m.me?'row-reverse':'row' }}>
                <Av init={m.av} size={32}/>
                <div style={{ maxWidth:'64%' }}>
                  <div style={{ fontSize:11, color:C.muted, marginBottom:3, textAlign:m.me?'right':'left' }}>{m.name} · {m.time}</div>
                  <div style={{ background:m.me?C.primary:C.light, color:m.me?'#fff':C.text, borderRadius:10, padding:'9px 13px', fontSize:13 }}>{m.text}</div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ padding:'10px 18px', borderTop:`1px solid ${C.border}`, display:'flex', gap:8 }}>
            <input value={msg} onChange={e=>setMsg(e.target.value)} placeholder="Type a message…" style={{ flex:1, padding:'9px 13px', border:`1px solid ${C.border}`, borderRadius:9, fontSize:13, outline:'none', fontFamily:"'DM Sans',sans-serif" }}/>
            <Btn variant="ghost" size="sm"><Paperclip size={14}/></Btn>
            <Btn variant="ghost" size="sm"><Smile size={14}/></Btn>
            <Btn variant="primary" size="sm"><Send size={13}/>Send</Btn>
          </div>
        </div>
        <div style={{ background:C.light, padding:14, borderLeft:`1px solid ${C.border}` }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.muted, marginBottom:10 }}>TEAM MEMBERS</div>
          {MEMBERS.map(m=>(
            <div key={m.id} style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
              <div style={{ position:'relative' }}>
                <Av init={m.av} size={30}/>
                <div style={{ position:'absolute', bottom:0, right:0, width:9, height:9, borderRadius:'50%', background:m.status==='Present'?C.primary:m.status==='WFH'?C.blue:C.muted, border:'2px solid #F1F5F9' }}/>
              </div>
              <div><div style={{ fontSize:12, fontWeight:600 }}>{m.name.split(' ')[0]}</div><div style={{ fontSize:10, color:C.muted }}>{m.status}</div></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Settings ──────────────────────────────────────────────────────
function SettingsPage({ onNav }) {
  const [tab, setTab] = useState('profile')
  // Theme preference persisted across sessions via localStorage. The actual
  // global theme switching isn't wired to the rest of the app yet — this
  // stores the user's choice so Settings is no longer a placeholder.
  const { theme, setTheme } = useTheme()
  const tabs = [
    { id:'profile',       label:'Profile',       icon:Users },
    { id:'security',      label:'Security',      icon:Shield },
    { id:'notifications', label:'Notifications', icon:Bell },
    { id:'appearance',    label:'Appearance',    icon:Palette },
  ]
  return (
    <div>
      <Topbar title="Settings" sub="Manage your account and preferences" onNav={onNav} />
      <div style={{ display:'grid', gridTemplateColumns:'200px 1fr', gap:20 }}>
        <Card style={{ padding:'8px 0', alignSelf:'start' }}>
          {tabs.map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id)} style={{ width:'100%', display:'flex', alignItems:'center', gap:10, padding:'9px 14px', background:tab===t.id?`${C.primary}18`:'transparent', color:tab===t.id?C.primary:C.muted, border:'none', cursor:'pointer', fontSize:13, fontWeight:tab===t.id?600:400, fontFamily:"'DM Sans',sans-serif" }}>
              <t.icon size={15}/>{t.label}
            </button>
          ))}
        </Card>
        <Card>
          {tab==='profile' && (
            <div>
              <div style={{ fontWeight:700, fontSize:15, marginBottom:18 }}>Profile Settings</div>
              <div style={{ display:'flex', gap:16, marginBottom:22 }}>
                <div style={{ position:'relative' }}>
                  <Av init={(() => { const u = (typeof window !== "undefined" && JSON.parse(localStorage.getItem("hrms.auth.user") || "null")) || {}; return initialsOf(u.full_name || u.name || "User"); })()} size={72}/>
                  <div style={{ position:'absolute', bottom:2, right:2, width:20, height:20, borderRadius:'50%', background:C.primary, display:'flex', alignItems:'center', justifyContent:'center' }}><Edit size={10} color="#fff"/></div>
                </div>
                <div style={{ display:'flex', flexDirection:'column', gap:6, justifyContent:'center' }}>
                  <Btn variant="primary" size="sm">Upload Photo</Btn>
                  <Btn variant="outline" size="sm">Remove</Btn>
                </div>
              </div>
              {(() => {
                const u = (typeof window !== 'undefined' && JSON.parse(localStorage.getItem('hrms.auth.user') || 'null')) || {};
                return [
                  ['Full Name', u.full_name || ''],
                  ['Email',     u.email || ''],
                  ['Job Title', u.designation || ''],
                  ['Department', u.department || ''],
                  ['Phone',     u.phone || ''],
                  ['Employee Code', u.employee_code || ''],
                ];
              })().map(([l,v])=>(
                <div key={l} style={{ marginBottom:14 }}>
                  <label style={{ display:'block', fontSize:12, fontWeight:700, color:C.muted, marginBottom:5 }}>{l}</label>
                  <input defaultValue={v} style={{ width:'100%', padding:'9px 13px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', fontFamily:"'DM Sans',sans-serif" }}/>
                </div>
              ))}
              <Btn variant="primary">Save Changes</Btn>
            </div>
          )}
          {tab==='notifications' && <ManagerNotifList/>}
          {tab==='security' && (
            <div>
              <div style={{ fontWeight:700, fontSize:15, marginBottom:18 }}>Security Settings</div>
              {['Current Password','New Password','Confirm Password'].map(l=>(
                <div key={l} style={{ marginBottom:14 }}>
                  <label style={{ display:'block', fontSize:12, fontWeight:700, color:C.muted, marginBottom:5 }}>{l}</label>
                  <input type="password" placeholder="••••••••" style={{ width:'100%', padding:'9px 13px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, outline:'none', fontFamily:"'DM Sans',sans-serif" }}/>
                </div>
              ))}
              <Btn variant="primary" style={{ marginBottom:20 }}>Update Password</Btn>
              <div style={{ padding:14, background:C.light, borderRadius:8 }}>
                <div style={{ fontWeight:600, fontSize:13, marginBottom:6 }}>Two-Factor Authentication</div>
                <div style={{ fontSize:12, color:C.muted, marginBottom:10 }}>Add an extra layer of security to your account.</div>
                <Btn variant="outline">Enable 2FA</Btn>
              </div>
            </div>
          )}
          {tab==='appearance' && (
            <div>
              <div style={{ fontWeight:700, fontSize:15, marginBottom:6 }}>Appearance</div>
              <div style={{ fontSize:12, color:C.muted, marginBottom:18 }}>
                Choose how WorkHive looks for you. Your choice is saved to this browser.
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(2, minmax(0, 1fr))', gap:14 }}>
                {[
                  {
                    id: 'light',
                    label: 'Light',
                    description: 'Clean, bright surface — best for daytime.',
                    preview: { surface:'#FFFFFF', card:'#F8FAFC', accent:C.primary, text:'#0F172A', mutedText:'#94A3B8' },
                  },
                  {
                    id: 'dark',
                    label: 'Dark',
                    description: 'Easy on the eyes in low-light environments.',
                    preview: { surface:'#0F172A', card:'#1E293B', accent:C.primary, text:'#F8FAFC', mutedText:'#94A3B8' },
                  },
                ].map((opt) => {
                  const active = theme === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setTheme(opt.id)}
                      aria-pressed={active}
                      style={{
                        textAlign:'left',
                        padding:14,
                        borderRadius:12,
                        border: active ? `2px solid ${C.primary}` : `1px solid ${C.border}`,
                        background: C.card,
                        cursor:'pointer',
                        transition:'border-color 0.15s, box-shadow 0.15s',
                        boxShadow: active ? `0 0 0 4px ${C.primary}1A` : 'none',
                        fontFamily:"'DM Sans',sans-serif",
                      }}
                    >
                      {/* Mini preview of the theme — surface + a card + an accent dot */}
                      <div style={{
                        position:'relative',
                        height:96,
                        borderRadius:10,
                        background: opt.preview.surface,
                        border:`1px solid ${C.border}`,
                        overflow:'hidden',
                        marginBottom:12,
                      }}>
                        <div style={{ position:'absolute', top:10, left:10, right:10, height:14, borderRadius:4, background: opt.preview.card }} />
                        <div style={{ position:'absolute', top:32, left:10, width:'60%', height:8, borderRadius:3, background: opt.preview.text, opacity:0.85 }} />
                        <div style={{ position:'absolute', top:46, left:10, width:'40%', height:6, borderRadius:3, background: opt.preview.mutedText }} />
                        <div style={{ position:'absolute', bottom:12, right:12, width:18, height:18, borderRadius:'50%', background: opt.preview.accent }} />
                      </div>

                      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                        <div>
                          <div style={{ fontWeight:700, fontSize:13, color:C.text }}>{opt.label}</div>
                          <div style={{ fontSize:11, color:C.muted, marginTop:3 }}>{opt.description}</div>
                        </div>
                        <span style={{
                          width:20, height:20, borderRadius:'50%',
                          border: active ? `6px solid ${C.primary}` : `2px solid ${C.border}`,
                          background:'#fff',
                          flexShrink:0,
                        }} />
                      </div>
                    </button>
                  );
                })}
              </div>
              <p style={{ fontSize:11, color:C.muted, marginTop:14 }}>
                Currently selected: <strong style={{ color:C.text }}>{theme === 'dark' ? 'Dark' : 'Light'}</strong> theme.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}


function buildProfileData(user) {
  return {
    fullName:   user?.full_name
              || [user?.first_name, user?.last_name].filter(Boolean).join(' ')
              || user?.name
              || (user?.email ? user.email.split('@')[0] : ''),
    email:      user?.email || '',
    phone:      user?.phone || '',
    employeeId: user?.employee_code || (user?.id ? ('EMP-' + user.id) : ''),
    department: user?.department || '',
    position:   user?.designation || '',
    location:   user?.location || '',
    manager:    user?.manager_name || '—',
    bio:        '',
    joined:     user?.date_of_joining || '',
  };
}

function Field({ label, value, onChange, type='text', disabled=false }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
      <label style={{ fontSize:11, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4 }}>{label}</label>
      <input
        type={type}
        value={value || ''}
        onChange={onChange}
        disabled={disabled}
        style={{
          padding:'9px 12px',
          border:`1px solid ${C.border}`,
          borderRadius:8,
          fontSize:13,
          color:C.text,
          background: disabled ? C.light : '#fff',
          outline:'none',
          fontFamily:"'DM Sans',sans-serif",
        }}
      />
    </div>
  );
}

function ProfilePage({ onNav }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState('personal');
  const [data, setData] = useState(() => buildProfileData(user));
  // Re-seed whenever the user reference changes (e.g. /auth/me lands)
  useEffect(() => { setData(buildProfileData(user)); }, [user]);
  const [pwd, setPwd] = useState({ current:'', next:'', confirm:'' });
  const [pwdError, setPwdError] = useState('');
  const [saved, setSaved] = useState(false);
  const [pwdSaved, setPwdSaved] = useState(false);

  const upd  = (k) => (e) => setData({ ...data, [k]: e.target.value });
  const updP = (k) => (e) => setPwd({ ...pwd, [k]: e.target.value });

  const onSave = (e) => {
    e?.preventDefault?.();
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const onPwdSubmit = (e) => {
    e?.preventDefault?.();
    setPwdError('');
    if (!pwd.current || !pwd.next || !pwd.confirm) { setPwdError('Please fill in every field.'); return; }
    if (pwd.next.length < 6)        { setPwdError('New password must be at least 6 characters.'); return; }
    if (pwd.next !== pwd.confirm)   { setPwdError('Passwords do not match.'); return; }
    setPwd({ current:'', next:'', confirm:'' });
    setPwdSaved(true);
    setTimeout(() => setPwdSaved(false), 2000);
  };


  const StatTile = ({ icon:Icon, label, value, tint }) => (
    <div style={{ background:C.card, border:`1px solid ${C.border}`, borderRadius:12, padding:'14px 16px', display:'flex', alignItems:'center', gap:12 }}>
      <div style={{ background:tint||C.light, width:38, height:38, borderRadius:10, display:'flex', alignItems:'center', justifyContent:'center' }}>
        <Icon size={18} color={C.primary}/>
      </div>
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:11, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4 }}>{label}</div>
        <div style={{ marginTop:2, fontSize:14, fontWeight:700, color:C.text }}>{value}</div>
      </div>
    </div>
  );

  return (
    <div>
      <Topbar title="My Profile" sub="View and update your personal information." onNav={onNav}/>

      {/* Hero card with gradient cover */}
      <Card style={{ padding:0, overflow:'hidden', marginBottom:20 }}>
        <div style={{
          height:120,
          background:'linear-gradient(135deg, #0F172A 0%, #1E3A8A 50%, '+C.primary+' 100%)',
          position:'relative', overflow:'hidden',
        }}>
          <div style={{ position:'absolute', right:-40, top:-40, width:220, height:220, background:'radial-gradient(circle, rgba(255,255,255,0.10) 0%, transparent 70%)', pointerEvents:'none' }}/>
        </div>
        <div style={{ padding:'0 26px 24px' }}>
          {/* Hero header: avatar overlaps the banner via its own negative
              margin while the text block sits cleanly in the white area
              below the gradient (so the name isn't clipped by the banner). */}
          <div style={{ display:'flex', alignItems:'flex-end', gap:20, paddingTop:14, flexWrap:'wrap' }}>
            <div style={{ position:'relative', marginTop:-52, flexShrink:0 }}>
              <Av init={initialsOf(data.fullName)} size={104}/>
              <div style={{ position:'absolute', bottom:4, right:4, width:18, height:18, borderRadius:'50%', background:'#22C55E', border:'3px solid #fff' }}/>
            </div>
            <div style={{ paddingBottom:6, minWidth:0, flex:1 }}>
              <div style={{ fontWeight:800, fontSize:22, color:C.text, letterSpacing:'-0.3px', lineHeight:1.2 }}>{data.fullName}</div>
              <div style={{ fontSize:13, color:C.muted, marginTop:4 }}>{data.position} · {data.department}</div>
              <div style={{ fontSize:11, color:C.muted, marginTop:4 }}>Joined {data.joined}</div>
              <div style={{ display:'flex', gap:8, marginTop:10, flexWrap:'wrap' }}>
                <Badge color="#fff" bg={C.primary}>Manager</Badge>
                <Badge color={C.primary} bg='#D1FAE5'>● Active</Badge>
                <Badge color={C.muted} bg={C.light}>{data.employeeId}</Badge>
              </div>
            </div>
          </div>

          {/* Quick contact strip */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:14, borderTop:`1px solid ${C.border}`, marginTop:18, paddingTop:14 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, color:C.text }}>
              <div style={{ background:'#EEF2FF', width:32, height:32, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:C.blue }}>
                <Bell size={14}/>
              </div>
              {data.email}
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, color:C.text }}>
              <div style={{ background:'#D1FAE5', width:32, height:32, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:C.primary }}>
                <Phone size={14}/>
              </div>
              {data.phone}
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, color:C.text }}>
              <div style={{ background:'#FEF3C7', width:32, height:32, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:C.yellow }}>
                <Home size={14}/>
              </div>
              {data.location}
            </div>
          </div>
        </div>
      </Card>

      {/* Tabbed pane (full width — stat tiles and right sidebar removed) */}
      <div>
        <Card style={{ padding:0 }}>
          {/* Tab strip */}
          <div style={{ display:'flex', gap:4, padding:'10px 12px 0', borderBottom:`1px solid ${C.border}` }}>
            {[['personal','Personal Info']].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{
                  padding:'10px 16px',
                  fontSize:13, fontWeight:600,
                  background:'transparent', border:'none',
                  borderBottom: tab===id ? `2px solid ${C.primary}` : '2px solid transparent',
                  color: tab===id ? C.primary : C.muted,
                  cursor:'pointer',
                  fontFamily:"'DM Sans',sans-serif",
                }}
              >
                {label}
              </button>
            ))}
          </div>

          <div style={{ padding:22 }}>
            {tab === 'personal' && (
              <>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:18 }}>
                  <div>
                    <div style={{ fontWeight:700, fontSize:15 }}>Personal Information</div>
                    <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>Update your details — changes are saved locally for this preview.</div>
                  </div>
                  {saved && <Badge color={C.primary} bg='#D1FAE5'>Saved</Badge>}
                </div>
                <form onSubmit={onSave}>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
                    <Field label="Full Name"   value={data.fullName}   onChange={upd('fullName')}   disabled={!editing} />
                    <Field label="Email"       value={data.email}      onChange={upd('email')}      disabled={!editing} type="email" />
                    <Field label="Phone"       value={data.phone}      onChange={upd('phone')}      disabled={!editing} type="tel" />
                    <Field label="Employee ID" value={data.employeeId} onChange={upd('employeeId')} disabled />
                    <Field label="Department"  value={data.department} onChange={upd('department')} disabled={!editing} />
                    <Field label="Position"    value={data.position}   onChange={upd('position')}   disabled={!editing} />
                    <Field label="Location"    value={data.location}   onChange={upd('location')}   disabled={!editing} />
                    <Field label="Manager"     value={data.manager}    onChange={upd('manager')}    disabled />
                  </div>
                  <div style={{ marginTop:16 }}>
                    <label style={{ display:'block', fontSize:11, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:6 }}>Bio</label>
                    <textarea
                      rows={3}
                      value={data.bio}
                      onChange={upd('bio')}
                      disabled={!editing}
                      style={{ width:'100%', padding:'9px 12px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, color:C.text, background: editing ? '#fff' : C.light, outline:'none', fontFamily:"'DM Sans',sans-serif", resize:'vertical' }}
                    />
                  </div>
                  {editing && (
                    <div style={{ display:'flex', gap:8, justifyContent:'flex-end', marginTop:18 }}>
                      <Btn variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Btn>
                      <Btn variant="primary" size="sm" onClick={onSave}>Save Changes</Btn>
                    </div>
                  )}
                </form>
              </>
            )}

          </div>
        </Card>
      </div>
    </div>
  );
}

const __mgrNotifs = [
  ['Leave Requests',     'Get notified when team members submit leaves',  true],
  ['Approvals',          'Reminders for pending approvals',                true],
  ['Performance Reviews','Alerts for upcoming and due reviews',            false],
  ['Team Announcements', 'Company-wide announcements',                     true],
  ['Weekly Summary',     'Weekly team performance digest',                 false],
];

function ManagerNotifList() {
  const [flags, setFlags] = usePersistedState('hrms.settings.manager.notifs', __mgrNotifs.map((n) => n[2]));
  const list = flags.length === __mgrNotifs.length ? flags : __mgrNotifs.map((n) => n[2]);
  return (
    <div>
      <div style={{ fontWeight:700, fontSize:15, marginBottom:18 }}>Notification Preferences</div>
      {__mgrNotifs.map(([l, d], i) => (
        <div key={l} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 0', borderBottom:`1px solid ${C.border}` }}>
          <div><div style={{ fontWeight:600, fontSize:13 }}>{l}</div><div style={{ fontSize:12, color:C.muted }}>{d}</div></div>
          <button
            type="button"
            onClick={() => setFlags(list.map((v, j) => (j === i ? !v : v)))}
            aria-pressed={list[i]}
            style={{ width:42, height:23, borderRadius:12, background:list[i]?C.primary:C.border, position:'relative', cursor:'pointer', border:'none', padding:0 }}
          >
            <span style={{ width:17, height:17, borderRadius:'50%', background:'#fff', position:'absolute', top:3, left:list[i]?21:4, transition:'left 0.2s' }}/>
          </button>
        </div>
      ))}
    </div>
  );
}

function NotifRow({ label, desc, initial }) {
  const [on, setOn] = useState(initial);
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 0', borderBottom:`1px solid ${C.border}` }}>
      <div>
        <div style={{ fontWeight:600, fontSize:13 }}>{label}</div>
        <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>{desc}</div>
      </div>
      <button
        onClick={() => setOn((v) => !v)}
        style={{ width:42, height:23, borderRadius:12, background: on ? C.primary : C.border, position:'relative', cursor:'pointer', border:'none', flexShrink:0 }}
        aria-pressed={on}
      >
        <div style={{ width:17, height:17, borderRadius:'50%', background:'#fff', position:'absolute', top:3, left: on ? 21 : 4, transition:'left 0.2s' }}/>
      </button>
    </div>
  );
}

// ── Company (Under Construction) ──────────────────────────────────
function CompanyPage({ onNav }) {
  return (
    <div>
      <Topbar title="Company" sub="Org chart, departments, and offices — coming soon." onNav={onNav} />
      <UnderConstruction
        accent="teal"
        title="Company"
        description="A unified view of WorkHive — org chart, departments, and global offices — is on the way."
        features={[
          { label: 'Org chart & leadership', icon: <Users size={16} /> },
          { label: 'Departments breakdown',  icon: <Activity size={16} /> },
          { label: 'Global offices map',     icon: <Home size={16} /> },
        ]}
      />
    </div>
  );
}

export default function ManagerDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Derive active page from URL: /manager-dashboard/<page>
  const segs = location.pathname.replace(/^\/+|\/+$/g, '').split('/');
  const urlPage = (segs[1] || 'dashboard');

  const setPage = (id) => {
    setSidebarOpen(false);
    navigate('/manager-dashboard' + (id === 'dashboard' ? '' : '/' + id));
  };

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const PAGE_MAP = {
    dashboard:      <DashboardHome    onNav={setPage}/>,
    profile:        <ProfilePage     onNav={setPage}/>,
    'self-service': <SelfServicePage />,
    team:           <MyTeam          onNav={setPage}/>,
    attendance:    <Attendance      onNav={setPage}/>,
    leave:         <ManagerLeavePage />,
    'comp-off':    <ManagerCompOffPage />,
    approvals:     <ManagerApprovalsPage />,
    performance:   <Performance     onNav={setPage}/>,
    // Timesheets is no longer a top-level sidebar item; it lives as a
    // sub-tab inside Attendance. The /timesheets URL keeps working as a
    // deep link to that tab so the Approve Timesheet quick action still
    // lands on the right place.
    timesheets:    <Attendance      onNav={setPage} defaultTab="timesheets" />,
    projects:      <Projects        onNav={setPage}/>,
    reports:       <Reports         onNav={setPage}/>,
    announcements: <ManagerAnnouncementsPage />,
    company:       <CompanyPage     onNav={setPage}/>,
    payroll:       <PayrollPage />,
    policies:      <PoliciesPage />,
    settings:      <SharedSettingsPage />,
    notifications: <SharedNotificationsPage />,
  };

  return (
    <div style={{ fontFamily:"'DM Sans', sans-serif", background:C.bg, minHeight:'100vh' }}>
      <Sidebar active={urlPage} onNav={setPage} onLogout={handleLogout} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <SidebarCtx.Provider value={{ openSidebar: () => setSidebarOpen(true) }}>
        <main className="md:ml-60" style={{ padding:'26px 30px', minHeight:'100vh' }}>
          {PAGE_MAP[urlPage] || PAGE_MAP.dashboard}
        </main>
      </SidebarCtx.Provider>
    </div>
  );
}
