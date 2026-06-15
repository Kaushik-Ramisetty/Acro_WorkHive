import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from './Icon';
import { useNotifications } from '../hooks/useNotifications';
import { useAuth, dashboardPathForRole } from '../context/AuthContext';
import { routeFor } from '../services/notifications';

function timeAgo(iso) {
  if (!iso) return '';
  // Backend writes naive UTC datetimes; force UTC interpretation when
  // the string has no timezone marker.
  let s = String(iso);
  if (/T\d{2}:\d{2}/.test(s) && !/[Zz]|[+-]\d{2}:?\d{2}$/.test(s)) {
    s = s + 'Z';
  }
  const t = new Date(s).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  const d = Math.floor(h / 24);
  return d + 'd ago';
}

const TYPE_TONE = {
  leave_pending_your_approval:        { dot: 'bg-amber-500',   tone: 'text-amber-700'   },
  leave_cancel_pending_your_approval: { dot: 'bg-amber-500',   tone: 'text-amber-700'   },
  leave_applied:                      { dot: 'bg-blue-500',    tone: 'text-blue-700'    },
  leave_approved:                     { dot: 'bg-emerald-500', tone: 'text-emerald-700' },
  leave_rejected:                     { dot: 'bg-rose-500',    tone: 'text-rose-700'    },
  leave_cancelled:                    { dot: 'bg-slate-400',   tone: 'text-slate-600'   },
  leave_cancel_rejected:              { dot: 'bg-rose-500',    tone: 'text-rose-700'    },
  attendance_anomaly:                 { dot: 'bg-orange-500',  tone: 'text-orange-700'  },
  attendance_missed_checkout:         { dot: 'bg-orange-500',  tone: 'text-orange-700'  },
  regularization_submitted:           { dot: 'bg-blue-500',    tone: 'text-blue-700'    },
  regularization_approved:            { dot: 'bg-emerald-500', tone: 'text-emerald-700' },
  regularization_rejected:            { dot: 'bg-rose-500',    tone: 'text-rose-700'    },
  timesheet_submitted:                { dot: 'bg-blue-500',    tone: 'text-blue-700'    },
  timesheet_approved:                 { dot: 'bg-emerald-500', tone: 'text-emerald-700' },
  timesheet_rejected:                 { dot: 'bg-rose-500',    tone: 'text-rose-700'    },
  payslip_ready:                      { dot: 'bg-teal-500',    tone: 'text-teal-700'    },
  payroll_sync_failed:                { dot: 'bg-red-500',     tone: 'text-red-700'     },
  onboarding_invite:                  { dot: 'bg-violet-500',  tone: 'text-violet-700'  },
  onboarding_completed:               { dot: 'bg-emerald-500', tone: 'text-emerald-700' },
  bgv_updated:                        { dot: 'bg-violet-500',  tone: 'text-violet-700'  },
  announcement:                       { dot: 'bg-sky-500',     tone: 'text-sky-700'     },
  sla_escalation:                     { dot: 'bg-red-500',     tone: 'text-red-700'     },
  hr_escalation:                      { dot: 'bg-red-500',     tone: 'text-red-700'     },
};

export default function NotificationBell() {
  const { items, unread, refreshList, markRead, markAllRead } = useNotifications({ limit: 10 });
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();
  const { user } = useAuth();
  const basePath = dashboardPathForRole(user?.role);

  useEffect(() => {
    if (!open) return undefined;
    refreshList();
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open, refreshList]);

  // Click handler: (1) mark read, (2) navigate to action target if any.
  const handleClick = (n) => {
    if (!n.is_read) markRead(n.id);
    const target = routeFor(n, basePath);
    setOpen(false);
    if (target) navigate(target);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-full p-2 text-slate-500 transition hover:bg-slate-100"
        aria-label="Notifications"
      >
        <Icon name="bell" />
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg z-50">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-slate-900">Notifications</p>
              <p className="text-[11px] text-slate-500">{unread} unread</p>
            </div>
            {unread > 0 && (
              <button
                onClick={markAllRead}
                className="rounded-md px-2 py-1 text-[11px] font-semibold text-blue-600 hover:bg-blue-50"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 && (
              <p className="px-4 py-10 text-center text-xs text-slate-400">No notifications yet.</p>
            )}
            {items.map((n) => {
              const tone = TYPE_TONE[n.type] || { dot: 'bg-slate-400', tone: 'text-slate-600' };
              return (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={
                    'flex w-full items-start gap-3 border-b border-slate-100 px-4 py-3 text-left transition hover:bg-slate-50 ' +
                    (n.is_read ? 'opacity-70' : 'bg-white')
                  }
                >
                  <span className={'mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ' + tone.dot} />
                  <div className="min-w-0 flex-1">
                    <p className={'text-sm font-semibold ' + (n.is_read ? 'text-slate-600' : 'text-slate-900')}>{n.title}</p>
                    {n.body && <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{n.body}</p>}
                    <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-400">{timeAgo(n.created_at)}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Footer: deep-link to the full Notifications page */}
          <button
            onClick={() => { setOpen(false); navigate(`${basePath}/notifications`); }}
            className="block w-full border-t border-slate-100 bg-white px-4 py-2.5 text-center text-xs font-semibold text-teal-600 hover:bg-slate-50 transition-colors"
          >
            View all notifications
          </button>
        </div>
      )}
    </div>
  );
}
