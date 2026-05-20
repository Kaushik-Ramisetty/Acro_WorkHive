import { NavLink, useNavigate } from 'react-router-dom';
import Icon from './Icon';
import logo from '../assets/logo.png';
import { SIDEBAR_CONFIG } from '../data/sidebarConfig';
import { useAuth } from '../context/AuthContext';

export default function Sidebar({ role, open, onClose }) {
  const cfg = SIDEBAR_CONFIG[role];
  const { logout } = useAuth();
  const navigate = useNavigate();

  if (!cfg) return null;

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={'fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity md:hidden ' + (open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none')}
        onClick={onClose}
        aria-hidden
      />

      <aside
        className={'fixed inset-y-0 left-0 z-50 flex h-screen w-60 flex-col bg-[#0a1731] text-slate-300 transition-transform md:sticky md:top-0 md:self-start md:shrink-0 md:translate-x-0 ' + (open ? 'translate-x-0' : '-translate-x-full md:translate-x-0')}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-5 py-5">
          <img src={logo} alt="WorkHive" className="h-9 w-9 rounded-md bg-white object-contain" />
          <div className="leading-tight">
            <p className="text-sm font-semibold text-white">{cfg.title}</p>
            <p className="text-[10px] uppercase tracking-wider text-slate-400">{cfg.subtitle}</p>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          <ul className="space-y-1">
            {cfg.items.map((item) => {
              const to = item.path ? cfg.base + '/' + item.path : cfg.base;
              return (
                <li key={item.label}>
                  <NavLink
                    to={to}
                    end={item.path === ''}
                    onClick={onClose}
                    className={({ isActive }) =>
                      'group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ' +
                      (isActive
                        ? 'bg-emerald-400/10 text-emerald-300'
                        : 'text-slate-400 hover:bg-white/5 hover:text-white')
                    }
                  >
                    <Icon name={item.icon} className="h-[18px] w-[18px]" />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer actions */}
        <div className="border-t border-white/5 px-3 py-4 space-y-1">
          <NavLink
            to={cfg.base + '/settings'}
            onClick={onClose}
            className={({ isActive }) =>
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ' +
              (isActive ? 'bg-emerald-400/10 text-emerald-300' : 'text-slate-400 hover:bg-white/5 hover:text-white')
            }
          >
            <Icon name="settings" className="h-[18px] w-[18px]" />
            <span>Settings</span>
          </NavLink>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white"
          >
            <Icon name="logout" className="h-[18px] w-[18px]" />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  );
}
