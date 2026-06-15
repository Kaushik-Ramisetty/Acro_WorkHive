// Admin Settings — visually + structurally matches the Manager Settings:
// 200px tab rail on the left (Profile / Security / Notifications / Appearance),
// card-style content panes on the right, persisted theme + notification flags.
import { useEffect, useState } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { useTheme } from '../../../context/ThemeContext';
import { usePersistedState } from '../../../hooks/usePersistedState';

// Palette references the global theme variables from src/index.css so the
// page automatically follows the active Light/Dark theme.
const C = {
  primary: '#10B981', primaryDark: '#059669',
  text:    'var(--hrms-text)',         muted: 'var(--hrms-text-muted)',
  border:  'var(--hrms-border)',       light: 'var(--hrms-surface-2)',
  card:    'var(--hrms-surface)',      bg:    'var(--hrms-bg)',
};

function initialsOf(name) {
  return (name || 'AU')
    .split(' ').filter(Boolean)
    .map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'AU';
}

// Lightweight inline icons matching the manager Settings icons.
const I = {
  user: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  ),
  shield: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  bell: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  ),
  palette: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="13.5" cy="6.5" r=".5" /><circle cx="17.5" cy="10.5" r=".5" />
      <circle cx="8.5" cy="7.5" r=".5" /><circle cx="6.5" cy="12.5" r=".5" />
      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.5 0 1-.5 1-1v-1c0-.5.5-1 1-1h2c2.8 0 5-2.2 5-5 0-5.5-4-12-9-12z" />
    </svg>
  ),
  edit: (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  ),
};

function Card({ children, style = {} }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 22, ...style }}>
      {children}
    </div>
  );
}
function Btn({ children, variant = 'primary', size = 'md', style = {}, ...rest }) {
  const sz = size === 'sm' ? { padding: '6px 12px', fontSize: 12 } : { padding: '9px 16px', fontSize: 13 };
  const bg = variant === 'primary' ? C.primary : '#fff';
  const color = variant === 'primary' ? '#fff' : C.text;
  const border = variant === 'primary' ? 'none' : `1px solid ${C.border}`;
  return (
    <button {...rest}
      style={{ ...sz, background: bg, color, border, borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", ...style }}>
      {children}
    </button>
  );
}
function Av({ init, size = 72 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: 'linear-gradient(135deg,#1E3A8A,#3B5BDB)',
      color: '#fff', fontSize: size * 0.32, fontWeight: 700,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>{init}</div>
  );
}

const ADMIN_NOTIFS = [
  ['New Employee Onboarding', 'When a new employee joins the system',          true],
  ['Leave Requests',          'When employees submit leave applications',      true],
  ['Claims Submitted',        'When new expense claims are awaiting review',   false],
  ['Payroll Alerts',          'Monthly payroll processing reminders',          true],
  ['Performance Cycles',      'When new review cycles are initiated',          true],
  ['System Announcements',    'Important system updates and maintenance',      false],
];

function AdminNotifList() {
  const [flags, setFlags] = usePersistedState('hrms.settings.admin.notifs', ADMIN_NOTIFS.map((n) => n[2]));
  const list = flags.length === ADMIN_NOTIFS.length ? flags : ADMIN_NOTIFS.map((n) => n[2]);
  return (
    <div>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 18 }}>Notification Preferences</div>
      {ADMIN_NOTIFS.map(([l, d], i) => (
        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0', borderBottom: `1px solid ${C.border}` }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{l}</div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{d}</div>
          </div>
          <button
            type="button"
            onClick={() => setFlags(list.map((v, j) => (j === i ? !v : v)))}
            aria-pressed={list[i]}
            style={{ width: 42, height: 23, borderRadius: 12, background: list[i] ? C.primary : C.border, position: 'relative', cursor: 'pointer', border: 'none', padding: 0 }}
          >
            <span style={{ width: 17, height: 17, borderRadius: '50%', background: '#fff', position: 'absolute', top: 3, left: list[i] ? 21 : 4, transition: 'left 0.2s' }} />
          </button>
        </div>
      ))}
    </div>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const fullName = user?.full_name || user?.name || '';
  const initials = initialsOf(fullName || 'Admin User');
  const [tab, setTab] = useState('profile');
  const { theme, setTheme } = useTheme();
  const [saved, setSaved] = useState(false);

  // Re-seed defaults when /auth/me lands.
  const [profile, setProfile] = useState({});
  useEffect(() => {
    setProfile({
      'Full Name':      user?.full_name || '',
      'Email':          user?.email || '',
      'Job Title':      user?.designation || (user?.role || ''),
      'Department':     user?.department || '',
      'Phone':          user?.phone || '',
      'Employee Code':  user?.employee_code || '',
    });
  }, [user]);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const TABS = [
    { id: 'profile',       label: 'Profile',       icon: I.user },
    { id: 'security',      label: 'Security',      icon: I.shield },
    { id: 'notifications', label: 'Notifications', icon: I.bell },
    { id: 'appearance',    label: 'Appearance',    icon: I.palette },
  ];

  return (
    <div className="fade-in" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {/* Header */}
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: '-0.3px' }}>Settings</h1>
        <p style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>Manage your account and preferences.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Tab rail */}
        <Card style={{ padding: '8px 0' }}>
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 14px',
                  background: active ? `${C.primary}18` : 'transparent',
                  color: active ? C.primary : C.muted,
                  border: 'none', cursor: 'pointer',
                  fontSize: 13, fontWeight: active ? 600 : 400, textAlign: 'left',
                  fontFamily: "'DM Sans', sans-serif",
                }}
              >
                {t.icon}{t.label}
              </button>
            );
          })}
        </Card>

        {/* Content */}
        <Card>
          {tab === 'profile' && (
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 18 }}>Profile Settings</div>
              <div style={{ display: 'flex', gap: 16, marginBottom: 22 }}>
                <div style={{ position: 'relative' }}>
                  <Av init={initials} size={72} />
                  <div style={{ position: 'absolute', bottom: 2, right: 2, width: 20, height: 20, borderRadius: '50%', background: C.primary, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {I.edit}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, justifyContent: 'center' }}>
                  <Btn variant="primary" size="sm">Upload Photo</Btn>
                  <Btn variant="outline" size="sm">Remove</Btn>
                </div>
              </div>
              {Object.entries(profile).map(([l, v]) => (
                <div key={l} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: C.muted, marginBottom: 5 }}>{l}</label>
                  <input
                    defaultValue={v}
                    style={{ width: '100%', padding: '9px 13px', border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, outline: 'none', fontFamily: "'DM Sans', sans-serif" }}
                  />
                </div>
              ))}
              <Btn variant="primary" onClick={handleSave}>{saved ? '✓ Saved' : 'Save Changes'}</Btn>
            </div>
          )}

          {tab === 'notifications' && <AdminNotifList />}

          {tab === 'security' && (
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 18 }}>Security Settings</div>
              {['Current Password', 'New Password', 'Confirm Password'].map((l) => (
                <div key={l} style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: C.muted, marginBottom: 5 }}>{l}</label>
                  <input type="password" placeholder="••••••••"
                    style={{ width: '100%', padding: '9px 13px', border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, outline: 'none', fontFamily: "'DM Sans', sans-serif" }} />
                </div>
              ))}
              <Btn variant="primary" onClick={handleSave} style={{ marginBottom: 20 }}>{saved ? '✓ Updated' : 'Update Password'}</Btn>
              <div style={{ padding: 14, background: C.light, borderRadius: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>Two-Factor Authentication</div>
                <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>Add an extra layer of security to your account.</div>
                <Btn variant="outline">Enable 2FA</Btn>
              </div>
            </div>
          )}

          {tab === 'appearance' && (
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>Appearance</div>
              <div style={{ fontSize: 12, color: C.muted, marginBottom: 18 }}>
                Choose how WorkHive looks for you. Your choice is saved to this browser.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
                {[
                  {
                    id: 'light',
                    label: 'Light',
                    description: 'Clean, bright surface — best for daytime.',
                    preview: { surface: '#FFFFFF', card: '#F8FAFC', accent: C.primary, text: '#0F172A', mutedText: '#94A3B8' },
                  },
                  {
                    id: 'dark',
                    label: 'Dark',
                    description: 'Easy on the eyes in low-light environments.',
                    preview: { surface: '#0F172A', card: '#1E293B', accent: C.primary, text: '#F8FAFC', mutedText: '#94A3B8' },
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
                        textAlign: 'left',
                        padding: 14,
                        borderRadius: 12,
                        border: active ? `2px solid ${C.primary}` : `1px solid ${C.border}`,
                        background: C.card,
                        cursor: 'pointer',
                        transition: 'border-color 0.15s, box-shadow 0.15s',
                        boxShadow: active ? `0 0 0 4px ${C.primary}1A` : 'none',
                        fontFamily: "'DM Sans', sans-serif",
                      }}
                    >
                      <div style={{
                        position: 'relative', height: 96, borderRadius: 10,
                        background: opt.preview.surface, border: `1px solid ${C.border}`,
                        overflow: 'hidden', marginBottom: 12,
                      }}>
                        <div style={{ position: 'absolute', top: 10, left: 10, right: 10, height: 14, borderRadius: 4, background: opt.preview.card }} />
                        <div style={{ position: 'absolute', top: 32, left: 10, width: '60%', height: 8, borderRadius: 3, background: opt.preview.text, opacity: 0.85 }} />
                        <div style={{ position: 'absolute', top: 46, left: 10, width: '40%', height: 6, borderRadius: 3, background: opt.preview.mutedText }} />
                        <div style={{ position: 'absolute', bottom: 12, right: 12, width: 18, height: 18, borderRadius: '50%', background: opt.preview.accent }} />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, color: C.text }}>{opt.label}</div>
                          <div style={{ fontSize: 11, color: C.muted, marginTop: 3 }}>{opt.description}</div>
                        </div>
                        <span style={{
                          width: 20, height: 20, borderRadius: '50%',
                          border: active ? `6px solid ${C.primary}` : `2px solid ${C.border}`,
                          background: '#fff', flexShrink: 0,
                        }} />
                      </div>
                    </button>
                  );
                })}
              </div>
              <p style={{ fontSize: 11, color: C.muted, marginTop: 14 }}>
                Currently selected: <strong style={{ color: C.text }}>{theme === 'dark' ? 'Dark' : 'Light'}</strong> theme.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
