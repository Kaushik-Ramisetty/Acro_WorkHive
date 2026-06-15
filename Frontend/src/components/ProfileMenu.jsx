import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Icon from './Icon';

const ROLE_TONE = {
  admin:    { avatarBg: 'bg-slate-200',   avatarColor: 'text-slate-700' },
  manager:  { avatarBg: 'bg-amber-100',   avatarColor: 'text-amber-700' },
  employee: { avatarBg: 'bg-emerald-100', avatarColor: 'text-emerald-700' },
};

/**
 * Reusable profile menu.
 *
 * Behaviour identical to the admin Navbar's profile dropdown:
 *   - Click avatar/name → dropdown opens (or closes)
 *   - Dropdown shows full name, email, role badge
 *   - "View profile" navigates to /{role}-dashboard/profile (or /myprofile for employees)
 *   - "Sign out" calls logout() + navigates to /login
 *   - Click outside or Escape closes it
 *
 * Props:
 *   role             — 'admin' | 'manager' | 'employee'  (controls tone + nav path)
 *   onLogout?        — override; defaults to AuthContext logout + /login redirect
 *   profilePath?     — override the path appended after /{role}-dashboard
 */
export default function ProfileMenu({ role, onLogout, profilePath }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const tone = ROLE_TONE[role] || ROLE_TONE.employee;
  const fullName = user?.full_name || user?.name || 'User';
  const subtitle = user?.designation || user?.role || '';
  const initials = (fullName || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'U';

  // Default profile route per role
  const defaultProfilePath = role === 'employee' ? '/myprofile' : '/profile';
  const targetProfile = '/' + role + '-dashboard' + (profilePath || defaultProfilePath);

  const handleLogout = () => {
    if (onLogout) {
      onLogout();
    } else {
      logout();
      navigate('/login', { replace: true });
    }
  };

  // Click-outside + Escape to close
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-3 rounded-full p-1 pl-2 transition hover:bg-slate-100"
      >
        <div className="hidden text-right md:block">
          <p className="whitespace-nowrap text-sm font-semibold leading-tight text-slate-900">{fullName}</p>
          <p className="whitespace-nowrap text-[11px] leading-tight text-slate-500 capitalize">{subtitle}</p>
        </div>
        <div className={'flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ' + tone.avatarBg + ' ' + tone.avatarColor}>
          {initials}
        </div>
        <Icon name="chevronDown" className="h-4 w-4 text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-56 rounded-lg border border-slate-200 bg-white p-1 shadow-lg z-40">
          <div className="border-b border-slate-100 px-3 py-2">
            <p className="text-sm font-semibold text-slate-900">{fullName}</p>
            <p className="text-xs text-slate-500 truncate">{user?.email}</p>
            <p className="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
              {user?.role || role}
            </p>
          </div>

          <button
            onClick={() => { setOpen(false); navigate(targetProfile); }}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Icon name="user" className="h-4 w-4" />
            View profile
          </button>

          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Icon name="logout" className="h-4 w-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
