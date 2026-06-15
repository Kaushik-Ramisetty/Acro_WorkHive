/**
 * ManagerAnnouncementsPage
 * ─────────────────────────
 * Feed + create panel for managers.
 *  • Displays all announcements visible to the manager
 *  • Team read/ack counts visible on each card
 *  • "New Department Announcement" button (department scope only)
 *  • Filter by category, unread, pinned
 *
 * Styled to match the manager dashboard's dark-sidebar + light-content pattern
 * used throughout ManagerDashboard.jsx.
 */
import { useState, useEffect, useCallback } from 'react';
import AnnouncementCard from '../../../components/announcements/AnnouncementCard';
import AnnouncementModal from '../../../components/announcements/AnnouncementModal';
import { announcementsApi, ANNOUNCEMENT_CATEGORIES } from '../../../services/announcements';

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.5" className="mb-4 opacity-30">
        <path d="M3 11l18-7v17l-18-7z" /><path d="M11.6 21l-1.6-7" />
      </svg>
      <p className="text-sm font-medium">No announcements found</p>
      <p className="text-xs mt-1">New company and department announcements will appear here.</p>
    </div>
  );
}

export default function ManagerAnnouncementsPage() {
  const [items, setItems]       = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [page, setPage]         = useState(0);
  const LIMIT = 15;

  // Filters
  const [catFilter, setCat]     = useState('');
  const [unreadOnly, setUnread] = useState(false);
  const [search, setSearch]     = useState('');

  // Modal
  const [modalOpen, setModalOpen] = useState(false);

  // Departments (loaded for the modal — manager sees only their own dept)
  const [departments, setDepts] = useState([]);

  useEffect(() => {
    fetch('/api/v1/departments', {
      headers: { Authorization: 'Bearer ' + (localStorage.getItem('hrms.auth.token') || '') }
    })
      .then((r) => r.json())
      .then((d) => setDepts(Array.isArray(d?.data) ? d.data : []))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await announcementsApi.list({
        unread_only: unreadOnly || undefined,
        category:    catFilter  || undefined,
        search:      search     || undefined,
        limit:       LIMIT,
        offset:      page * LIMIT,
      });
      setItems(res.items ?? []);
      setTotal(res.total ?? 0);
    } catch (e) {
      setError(e?.message || 'Failed to load announcements');
    } finally {
      setLoading(false);
    }
  }, [unreadOnly, catFilter, search, page]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(0); }, [unreadOnly, catFilter, search]);

  const handleRead = async (id) => {
    try {
      await announcementsApi.markRead(id);
      setItems((prev) => prev.map((a) => a.id === id ? { ...a, is_read: true } : a));
    } catch { /* non-critical */ }
  };

  const handleAck = async (id) => {
    try {
      await announcementsApi.acknowledge(id);
      setItems((prev) => prev.map((a) => a.id === id ? { ...a, is_acknowledged: true, is_read: true } : a));
    } catch { /* non-critical */ }
  };

  const handleSave = async (payload) => {
    await announcementsApi.create(payload);
    load();
  };

  const totalPages = Math.ceil(total / LIMIT);
  const unreadCount = items.filter((a) => !a.is_read).length;

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {/* Page title */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Announcements</h1>
          <p className="mt-1 text-sm text-slate-500">
            Company and department updates for your team.
            {unreadCount > 0 && (
              <span className="ml-2 inline-flex items-center rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-bold text-white">
                {unreadCount} unread
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Department Announcement
        </button>
      </div>

      {/* Filters */}
      <div className="mb-5 flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[160px] rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
        />
        <select
          value={catFilter}
          onChange={(e) => setCat(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-blue-400 focus:outline-none"
        >
          <option value="">All Categories</option>
          {ANNOUNCEMENT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 cursor-pointer select-none">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600"
            checked={unreadOnly}
            onChange={(e) => setUnread(e.target.checked)}
          />
          <span className="text-sm text-slate-600">Unread only</span>
        </label>
      </div>

      {/* Feed */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-400 text-sm">Loading…</div>
      ) : error ? (
        <div className="flex items-center justify-center py-20 text-red-500 text-sm">{error}</div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <div className="space-y-4">
            {items.map((ann) => (
              <AnnouncementCard
                key={ann.id}
                announcement={ann}
                onRead={handleRead}
                onAcknowledge={handleAck}
                showCounts={true}
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
                <span className="text-xs text-slate-600">{page + 1} / {totalPages}</span>
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

      {/* Create modal (dept-scope only for managers) */}
      <AnnouncementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        initial={null}
        onSave={handleSave}
        departments={departments}
        roles={[]}
        isManagerMode={true}
      />
    </div>
  );
}
