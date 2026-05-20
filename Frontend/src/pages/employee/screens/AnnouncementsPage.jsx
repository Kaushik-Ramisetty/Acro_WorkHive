/**
 * Employee Announcements feed.
 * Replaces the previous UnderConstruction placeholder.
 *
 * Features:
 *  • Card-based feed sorted by pinned → newest
 *  • Filter bar: All / Unread / Important / Critical / Category
 *  • Search bar
 *  • Mark-as-read on click (auto-fires when card is seen)
 *  • Acknowledge button for mandatory announcements
 *  • Unread count badge in header
 *  • Pagination
 */
import { useState, useEffect, useCallback } from 'react';
import AnnouncementCard from '../../../components/announcements/AnnouncementCard';
import { announcementsApi, ANNOUNCEMENT_CATEGORIES } from '../../../services/announcements';

// ---- Filter pill -----------------------------------------------------------
function Pill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition whitespace-nowrap
        ${active
          ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
          : 'border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-600 bg-white'
        }`}
    >
      {label}
    </button>
  );
}

// ---- Empty state -----------------------------------------------------------
function EmptyState({ filtered }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.2" className="mb-4 opacity-25">
        <path d="M3 11l18-7v17l-18-7z" /><path d="M11.6 21l-1.6-7" />
      </svg>
      <p className="text-sm font-medium text-slate-600">
        {filtered ? 'No announcements match your filters' : 'No announcements yet'}
      </p>
      <p className="text-xs mt-1 text-slate-400">
        {filtered
          ? 'Try clearing your filters to see more.'
          : 'Company and department updates will appear here.'}
      </p>
    </div>
  );
}

// ---- Main ------------------------------------------------------------------
const LIMIT = 15;

const QUICK_FILTERS = [
  { key: 'all',       label: 'All' },
  { key: 'unread',    label: 'Unread' },
  { key: 'important', label: 'Important' },
  { key: 'critical',  label: 'Critical' },
];

export default function AnnouncementsPage() {
  const [items, setItems]       = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [page, setPage]         = useState(0);

  const [quickFilter, setQuick] = useState('all');
  const [catFilter, setCat]     = useState('');
  const [search, setSearch]     = useState('');

  const isFiltered = quickFilter !== 'all' || catFilter !== '' || search !== '';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        limit:       LIMIT,
        offset:      page * LIMIT,
        search:      search   || undefined,
        category:    catFilter || undefined,
        unread_only: quickFilter === 'unread'    ? true : undefined,
        priority:    quickFilter === 'important' ? 'important'
                   : quickFilter === 'critical'  ? 'critical'
                   : undefined,
      };
      const res = await announcementsApi.list(params);
      setItems(res.items ?? []);
      setTotal(res.total ?? 0);
    } catch (e) {
      setError(e?.message || 'Failed to load announcements');
    } finally {
      setLoading(false);
    }
  }, [page, search, catFilter, quickFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(0); }, [search, catFilter, quickFilter]);

  // Mark as read silently
  const handleRead = async (id) => {
    try {
      await announcementsApi.markRead(id);
      setItems((prev) => prev.map((a) => a.id === id ? { ...a, is_read: true } : a));
    } catch { /* non-critical */ }
  };

  // Acknowledge
  const handleAck = async (id) => {
    try {
      await announcementsApi.acknowledge(id);
      setItems((prev) => prev.map((a) => a.id === id ? { ...a, is_acknowledged: true, is_read: true } : a));
    } catch { /* non-critical */ }
  };

  const unreadCount = items.filter((a) => !a.is_read).length;
  const totalPages  = Math.ceil(total / LIMIT);

  return (
    <div className="max-w-3xl mx-auto" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Announcements</h1>
          {unreadCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-bold text-white">
              {unreadCount} new
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-500">Company and department updates.</p>
      </div>

      {/* Search */}
      <div className="mb-4">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search announcements…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-white pl-9 pr-4 py-2.5 text-sm text-slate-700 placeholder-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition"
          />
        </div>
      </div>

      {/* Filter pills */}
      <div className="mb-5 flex flex-wrap gap-2">
        {QUICK_FILTERS.map((f) => (
          <Pill
            key={f.key}
            label={f.label}
            active={quickFilter === f.key}
            onClick={() => setQuick(f.key)}
          />
        ))}
        <select
          value={catFilter}
          onChange={(e) => setCat(e.target.value)}
          className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs text-slate-600 focus:border-blue-300 focus:outline-none"
        >
          <option value="">All Categories</option>
          {ANNOUNCEMENT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* Feed */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-slate-100 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-600">
          {error}
        </div>
      ) : items.length === 0 ? (
        <EmptyState filtered={isFiltered} />
      ) : (
        <>
          <div className="space-y-4">
            {items.map((ann) => (
              <AnnouncementCard
                key={ann.id}
                announcement={ann}
                onRead={handleRead}
                onAcknowledge={handleAck}
                showCounts={false}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-between">
              <span className="text-xs text-slate-400">{total} total</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium disabled:opacity-40 hover:bg-slate-50 transition"
                >
                  ← Prev
                </button>
                <span className="text-xs text-slate-500">{page + 1} / {totalPages}</span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium disabled:opacity-40 hover:bg-slate-50 transition"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
