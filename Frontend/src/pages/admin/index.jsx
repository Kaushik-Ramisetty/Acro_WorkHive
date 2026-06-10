// Aggregator for admin sub-pages.
import PlaceholderPage from '../../components/PlaceholderPage';
import UnderConstruction from '../../components/UnderConstruction';

// Tiny inline icons for the "What's coming" feature tiles.
const _icoCalendar = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>);
const _icoMoney    = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>);
const _icoShield   = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>);
const _icoChart    = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>);
const _icoStar     = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>);
const _icoBriefcase= (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>);
const _icoUsers    = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>);
const _icoDoc      = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>);
const _icoActivity = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>);
const _icoTarget   = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>);

import SharedSettingsPage from '../../components/SettingsPage';
import EmployeesPage from './employees/EmployeesPage';
import LeaveManagementPage from './leave/LeaveManagementPage';
import AttendancePage from './attendance/AttendancePage';
import CompOffPage from './compoff/CompOffPage';
import RegularizationApprovalsPage from './regularization/RegularizationApprovalsPage';
import AdminApprovalsPage from './approvals/AdminApprovalsPage';
import OnboardingScreen from './screens/Onboarding';
import PoliciesPage from './policies/PoliciesPage';
import AdminPoliciesPage from './policies/AdminPoliciesPage';
import AdminAnnouncementsPage from './announcements/AdminAnnouncementsPage';
import BenchResourceManagementPage from './bench/BenchResourceManagementPage';
import SelfServicePage from '../shared/SelfServicePage';
import PerformanceHubPage from './performance/PerformanceHubPage';
export { EmployeesPage as Employees };
export { LeaveManagementPage as LeaveManagement };
export { AttendancePage as Attendance };
export { CompOffPage as CompOff };
export { RegularizationApprovalsPage as Regularization };
export { AdminApprovalsPage as Approvals };
// Admin gets the full CRUD page (AdminPoliciesPage); the read-only PoliciesPage
// stays exported so manager/employee dashboards keep importing it unchanged.
export { AdminPoliciesPage as Policies };
export { PoliciesPage as PoliciesReadOnly };

export const Payroll = () => (
  <UnderConstruction
    accent="amber"
    title="Payroll"
    description="Run pay cycles, manage salary structures, and handle statutory filings — all from a single console."
    features={[
      { label: 'Pay cycle runs',         icon: _icoCalendar },
      { label: 'Salary structure manager', icon: _icoMoney },
      { label: 'Statutory filings',      icon: _icoShield },
    ]}
  />
);
export { PerformanceHubPage as Performance };
export const Recruitment = () => (
  <UnderConstruction
    accent="violet"
    title="Recruitment"
    description="Manage open roles, candidates, and the hiring pipeline end-to-end."
    features={[
      { label: 'Open roles board',     icon: _icoBriefcase },
      { label: 'Candidate pipeline',   icon: _icoUsers },
      { label: 'Interview scheduling', icon: _icoCalendar },
    ]}
  />
);
export const Company = () => (
  <UnderConstruction
    accent="teal"
    title="Company"
    description="A unified view of WorkHive — org chart, departments, and global offices — is on the way."
    features={[
      { label: 'Org chart & leadership', icon: _icoUsers },
      { label: 'Departments breakdown',  icon: _icoBriefcase },
      { label: 'Global offices map',     icon: _icoCalendar },
    ]}
  />
);
export { OnboardingScreen as Onboarding };
export const Reports = () => (
  <UnderConstruction
    accent="teal"
    title="Reports & Analytics"
    description="Custom and saved reports for HR analytics with rich filters and scheduled delivery."
    features={[
      { label: 'Saved report library', icon: _icoDoc },
      { label: 'Ad-hoc query builder', icon: _icoActivity },
      { label: 'Scheduled exports',    icon: _icoCalendar },
    ]}
  />
);
export { AdminAnnouncementsPage as Announcements };
export { BenchResourceManagementPage as BenchResource };
export { SelfServicePage as SelfService };
export const Help     = () => (
  <UnderConstruction
    accent="violet"
    title="Help & Support"
    description="Raise a ticket, browse the knowledge base, and chat with the support team — coming soon."
    features={[
      { label: 'Submit a ticket',     icon: _icoDoc },
      { label: 'Knowledge base',      icon: _icoBriefcase },
      { label: 'Live chat with HR',   icon: _icoActivity },
    ]}
  />
);
export const Settings = SharedSettingsPage;
