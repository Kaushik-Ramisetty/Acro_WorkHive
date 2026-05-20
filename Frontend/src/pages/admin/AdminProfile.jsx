import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import PageHeader from '../../components/PageHeader';
import Icon from '../../components/Icon';
import ProfileCard from '../../components/ProfileCard';
import ProfileForm, { ChangePasswordForm } from '../../components/ProfileForm';

// Defaults are now derived dynamically from useAuth() inside the component.
const FALLBACK = { bio: '' };

const ACCESS = [
  'Manage all employees, roles, and permissions',
  'Configure pay cycles and statutory filings',
  'Approve org-wide announcements and policies',
  'View compliance, audit logs, and analytics',
];

const NOTIFS = [
  ['Approval reminders',     'Daily digest at 9 AM if approvals are pending', true],
  ['Compliance alerts',      'Filings, deadlines, and audit trail events',     true],
  ['Payroll cycle updates',  'When a pay cycle opens, locks, or disburses',    true],
  ['New joiner alerts',      'When HR onboards a new employee',                false],
  ['Policy acknowledgements','Weekly summary of unread policies',              true],
  ['Weekly summary',         'Monday-morning workspace digest',                false],
];

const TABS = [
  { id: 'personal',   label: 'Personal Info' },
  { id: 'access',     label: 'Access' },
];

function NotifRow({ label, desc, initial }) {
  const [on, setOn] = useState(initial);
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-3 last:border-0">
      <div>
        <p className="text-sm font-semibold text-slate-700">{label}</p>
        <p className="text-xs text-slate-500">{desc}</p>
      </div>
      <button
        onClick={() => setOn((v) => !v)}
        aria-pressed={on}
        className="relative h-[23px] w-[42px] flex-shrink-0 rounded-full transition-colors"
        style={{ background: on ? '#1e3acb' : '#e2e8f0' }}
      >
        <span
          className="absolute top-[3px] h-[17px] w-[17px] rounded-full bg-white shadow transition-all"
          style={{ left: on ? 21 : 4 }}
        />
      </button>
    </div>
  );
}

export default function AdminProfile() {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState('personal');
  const seed = () => ({
    ...FALLBACK,
    fullName:   user?.full_name
              || [user?.first_name, user?.last_name].filter(Boolean).join(' ')
              || user?.name
              || (user?.email ? user.email.split('@')[0] : ''),
    email:      user?.email || '',
    phone:      user?.phone || '',
    employeeId: user?.employee_code || ('EMP-' + (user?.id ?? '')),
    department: user?.department || '',
    position:   user?.designation || '',
    location:   user?.location || '',
    manager:    user?.manager_name || '—',
    joined:     user?.date_of_joining || '',
  });
  const [data, setData] = useState(seed);
  // Re-sync if /auth/me revalidation updates user
  useEffect(() => { setData(seed()); /* eslint-disable-next-line */ }, [user]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="My Profile"
        subtitle="View your personal information and access."
      />

      {/* Hero card */}
      <ProfileCard
        name={data.fullName}
        role="admin"
        email={data.email}
        phone={data.phone}
        position={data.position}
        department={data.department}
        location={data.location}
        joined={data.joined}
        editing={editing}
        onEdit={() => setEditing((v) => !v)}
      />

      {/* Tabbed pane (full width — the right sidebar and stat tiles were removed) */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {/* Tab strip */}
        <div className="flex gap-1 border-b border-slate-200 px-3 pt-3">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={'rounded-t-md px-4 py-2.5 text-sm font-semibold transition ' + (tab === t.id
                ? 'border-b-2 border-[#1e3acb] text-[#1e3acb]'
                : 'border-b-2 border-transparent text-slate-500 hover:text-slate-700')}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Pane body */}
        <div className="p-6">
          {tab === 'personal' && (
            <ProfileForm
              initial={data}
              editing={editing}
              onCancel={() => setEditing(false)}
              onSave={(next) => { setData(next); setEditing(false); }}
            />
          )}

          {tab === 'access' && (
            <div>
              <h3 className="text-base font-bold text-slate-900">Access &amp; Permissions</h3>
              <p className="mt-0.5 text-xs text-slate-500">As an admin, you have full access across the workspace.</p>
              <ul className="mt-4 space-y-2">
                {ACCESS.map((a) => (
                  <li key={a} className="flex items-start gap-2.5 rounded-lg border border-slate-100 px-3 py-2.5 text-sm text-slate-700">
                    <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                      <Icon name="approve" className="h-3 w-3" />
                    </span>
                    {a}
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2.5 text-xs text-blue-700">
                <Icon name="shield" className="h-4 w-4" />
                Need to request elevated access? Contact your workspace owner.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
