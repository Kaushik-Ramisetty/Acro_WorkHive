/**
 * Shared Notifications page — mounted under all three role dashboards:
 *   /admin-dashboard/notifications
 *   /manager-dashboard/notifications
 *   /employee-dashboard/notifications
 *
 * Backend pagination via GET /notifications?limit&offset&category&unread_only&q.
 * Clicking a notification marks it read and redirects to the relevant module.
 *
 * Visual style intentionally matches the rest of the HRMS shell (white cards,
 * slate-100 borders, teal-500 accent) so it drops into any dashboard without
 * extra wiring.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth, dashboardPathForRole } from '../../context/AuthContext';
import { notificationsApi, routeFor } from '../../services/notifications';

// ── Filters — role-agnostic. Backend ignores categories with no matching rows. ──
const FILTERS = [
  { id: 'all',          label: 'All' },
  { id: 'unread',       label: 'Unread' },
  { id: 'leave',        label: 'Leave' },
  { id: 'attendance',   label: 'Attendance' },
  { id: 'timesheet',    label: 'Timesheet' },
  { id: 'payroll',      label: 'Payroll' },
  { id: 'onboarding',   label: 'Onboarding' },
  { id: 'approvals',    label: 'Approvals' },
  { id: 'announcements', label: 'Announcements' },
];

const PAGE_SIZE = 25;

function timeAgo(iso) {
  if (!iso) return '';
  let s = String(iso);
  if (/T\d{2}:\d{2}/.test(s) && !/[Zz]|[+-]\d{2}:?\d{2}$/.test(s)) s = s + 'Z';
  const t = new Date(s).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(s).toLocaleDateString();
}

// Group notifications by Today / Yesterday / Earlier this week / older date.
function bucketFor(iso) {
  if (!iso) return 'Earlier';
  let s = String(iso);
  if (/T\d{2}:\d{2}/.test(s) && !/[Zz]|[+-]\d{2}:?\d{2}$/.test(s)) s = s + 'Z';
  const d = new Date(s);
  const now = new Date();
  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, now)) return 'Today';
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (sameDay(d, y)) return 'Yesterday';
  const weekAgo = new Date(now); weekAgo.setDate(now.getDate() - 7);
  if (d >= weekAgo) return 'Earlier this week';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

const TYPE_TONE = {
  leave_pending_your_approval:        { dot: 'bg-amber-500',   chip: 'bg-amber-50 text-amber-700' },
  leave_cancel_pending_your_approval: { dot: 'bg-amber-500',   chip: 'bg-amber-50 text-amber-700' },
  leave_applied:                      { dot: 'bg-blue-500',    chip: 'bg-blue-50 text-blue-700' },
  leave_approved:                     { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  leave_rejected:                     { dot: 'bg-rose-500',    chip: 'bg-rose-50 text-rose-700' },
  leave_cancelled:                    { dot: 'bg-slate-400',   chip: 'bg-slate-100 text-slate-600' },
  attendance_anomaly:                 { dot: 'bg-orange-500',  chip: 'bg-orange-50 text-orange-700' },
  attendance_missed_checkout:         { dot: 'bg-orange-500',  chip: 'bg-orange-50 text-orange-700' },
  regularization_submitted:           { dot: 'bg-blue-500',    chip: 'bg-blue-50 text-blue-700' },
  regularization_approved:            { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  regularization_rejected:            { dot: 'bg-rose-500',    chip: 'bg-rose-50 text-rose-700' },
  timesheet_submitted:                { dot: 'bg-blue-500',    chip: 'bg-blue-50 text-blue-700' },
  timesheet_approved:                 { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  timesheet_rejected:                 { dot: 'bg-rose-500',    chip: 'bg-rose-50 text-rose-700' },
  payslip_ready:                      { dot: 'bg-teal-500',    chip: 'bg-teal-50 text-teal-700' },
  payroll_sync_failed:                { dot: 'bg-red-500',     chip: 'bg-red-50 text-red-700' },
  onboarding_invite:                  { dot: 'bg-violet-500',  chip: 'bg-violet-50 text-violet-700' },
  onboarding_completed:               { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  bgv_updated:                        { dot: 'bg-violet-500',  chip: 'bg-violet-50 text-violet-700' },
  announcement:                       { dot: 'bg-sky-500',     chip: 'bg-sky-50 text-sky-700' },
  sla_escalation:                     { dot: 'bg-red-500',     chip: 'bg-red-50 text-red-700' },
  hr_escalation:                      { dot: 'bg-red-500',     chip: 'bg-red-50 text-red-700' },
};

function prettifyType(t) {
  if (!t) return 'Notification';
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function NotificationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const basePath = dashboardPathForRole(user?.role);

  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [items, setItems]   = useState([]);
  const [total, setTotal]   = useState(0);
  const [unread, setUnread] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);

  // Debounced search → reset to page 0 whenever input or filter changes.
  useEffect(() => {
    const id = setTimeout(() => setOffset(0), 250);
    return () => clearTimeout(id);
  }, [search, filter]);

  const fetchPage = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset };
      if (filter === 'unread') params.unreadOnly = true;
      else if (filter !== 'all') params.category = filter;
      if (search.trim()) params.q = search.trim();
      const res = await notificationsApi.listPaged(params);
      // Response is the paginated envelope { items, total, unread, ... }
      // — but we also tolerate a bare array for forward/backwards safety.
      const rows  = Array.isArray(res) ? res : (res?.items || []);
      const tot   = Array.isArray(res) ? rows.length : (res?.total  ?? rows.length);
      const unr   = Array.isArray(res) ? rows.filter((n) => !n.is_read).length : (res?.unread ?? 0);
      // When offset === 0 we replace; otherwise we append (load-more pattern).
      setItems((prev) => (offset === 0 ? rows : [...prev, ...rows]));
      setTotal(tot);
      setUnread(unr);
    } catch {
      if (offset === 0) setItems([]);
    } finally {
      setLoading(false);
    }
  }, [filter, search, offset]);

  useEffect(() => { fetchPage(); }, [fetchPage]);

  const grouped = useMemo(() => {
    const g = new Map();
    for (const n of items) {
      const b = bucketFor(n.created_at);
      if (!g.has(b)) g.set(b, []);
      g.get(b).push(n);
    }
    return [...g.entries()];
  }, [items]);

  const handleClick = async (n) => {
    if (!n.is_read) {
      try { await notificationsApi.markRead(n.id); } catch { /* silent */ }
      setItems((p) => p.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      setUnread((c) => Math.max(0, c - 1));
    }
    const target = routeFor(n, basePath);
    if (target) navigate(target);
  };

  const handleMarkAllRead = async () => {
    try { await notificationsApi.markAllRead(); } catch { /* silent */ }
    setItems((p) => p.map((n) => ({ ...n, is_read: true })));
    setUnread(0);
  };

  const canLoadMore = items.length < total;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Notifications</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {total} total · <span className="font-semibold text-slate-700">{unread}</span> unread
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search notifications…"
            className="w-full sm:w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent"
          />
          <button
            onClick={handleMarkAllRead}
            disabled={!unread}
            className={
              'whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold transition ' +
              (unread
                ? 'bg-teal-500 text-white hover:brightness-110'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed')
            }
          >
            Mark all read
          </button>
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={
              'rounded-full px-3 py-1.5 text-xs font-semibold transition ' +
              (filter === f.id
                ? 'bg-teal-500 text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50')
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Grouped list */}
      <div className="rounded-xl border border-slate-100 bg-white shadow-sm overflow-hidden">
        {grouped.length === 0 && !loading && (
          <p className="px-6 py-16 text-center text-sm text-slate-400">
            No notifications match your filters.
          </p>
        )}
        {grouped.map(([bucket, rows]) => (
          <div key={bucket}>
            <div className="bg-slate-50 px-5 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100">
              {bucket}
            </div>
            <ul className="divide-y divide-slate-100">
              {rows.map((n) => {
                const tone = TYPE_TONE[n.type] || { dot: 'bg-slate-400', chip: 'bg-slate-100 text-slate-600' };
                return (
                  <li key={n.id}>
                    <button
                      onClick={() => handleClick(n)}
                      className={
                        'flex w-full items-start gap-3 px-5 py-3.5 text-left transition hover:bg-slate-50 ' +
                        (n.is_read ? 'opacity-80' : 'bg-white')
                      }
                    >
                      <span className={'mt-2 h-2 w-2 flex-shrink-0 rounded-full ' + tone.dot} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className={'text-sm font-semibold ' + (n.is_read ? 'text-slate-600' : 'text-slate-900')}>
                            {n.title}
                          </p>
                          <span className={'rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' + tone.chip}>
                            {prettifyType(n.type)}
                          </span>
                          {!n.is_read && (
                            <span className="rounded-full bg-red-500 px-1.5 text-[9px] font-bold uppercase tracking-wider text-white">
                              New
                            </span>
                          )}
                        </div>
                        {n.body && <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{n.body}</p>}
                        <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-400">
                          {timeAgo(n.created_at)}
                        </p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {loading && (
          <p className="px-6 py-6 text-center text-xs text-slate-400">Loading…</p>
        )}
        {canLoadMore && !loading && (
          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="block w-full border-t border-slate-100 bg-white px-4 py-3 text-center text-xs font-semibold text-teal-600 hover:bg-slate-50 transition-colors"
          >
            Load more
          </button>
        )}
      </div>
    </div>
  );
}
