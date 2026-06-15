import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/logo.png';

const ROLE_BADGE = {
  admin: 'bg-rose-100 text-rose-700 ring-rose-200',
  manager: 'bg-amber-100 text-amber-800 ring-amber-200',
  employee: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
};

export default function DashboardLayout({ title, subtitle, accent = '#1e3acb', children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <img src={logo} alt="WorkHive" className="h-8 w-8 rounded-md bg-white object-contain ring-1 ring-slate-200" />
            <div>
              <p className="text-sm font-semibold tracking-tight text-slate-900">WorkHive</p>
              <p className="text-[11px] uppercase tracking-wider text-slate-500">Employee Hub</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {user && (
              <span className={'hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 sm:inline-flex ' + (ROLE_BADGE[user.role] || 'bg-slate-100 text-slate-700 ring-slate-200')}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                {user.role}
              </span>
            )}
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-slate-900">{user?.name || 'User'}</p>
              <p className="text-xs text-slate-500">{user?.email}</p>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-10">
        <div className="rounded-2xl p-8 text-white shadow-soft" style={{ background: 'linear-gradient(135deg, ' + accent + ' 0%, #172579 100%)' }}>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/70">Dashboard</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">{title}</h1>
          {subtitle && <p className="mt-2 max-w-2xl text-sm text-white/80">{subtitle}</p>}
        </div>
        <div className="mt-8">{children}</div>
      </main>
    </div>
  );
}
