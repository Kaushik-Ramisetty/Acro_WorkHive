/**
 * AdminAnnouncementsPage
 * ───────────────────────
 * Full announcement management for HR/Admin:
 *  • Stats row (total, published, drafts, archived)
 *  • Filter bar (status, category, priority, search)
 *  • Management table with per-row actions
 *  • Create / Edit modal
 *  • Publish / Archive / Delete actions
 */
import { useState, useEffect, useCallback } from 'react';
import PageHeader from '../../../components/PageHeader';
import Card from '../../../components/Card';
import PriorityBadge from '../../../components/announcements/PriorityBadge';
import CategoryBadge from '../../../components/announcements/CategoryBadge';
import AnnouncementModal from '../../../components/announcements/AnnouncementModal';
import { announcementsApi, ANNOUNCEMENT_CATEGORIES } from '../../../services/announcements';

// ---- Helpers ---------------------------------------------------------------

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function StatusBadge({ status }) {
  const s = {
    published: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    draft:     'bg-slate-100 text-slate-600 border-slate-200',
    archived:  'bg-red-50 text-red-600 border-red-200',
  }[status] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${s}`}>
      {status}
    </span>
  );
}

function ScopeBadge({ scope }) {
  const labels = { company: '🌐 All', department: '🏢 Dept', role: '👤 Role', individual: '🎯 Individual' };
  return <span className="text-xs text-slate-500">{labels[scope] ?? scope}</span>;
}

function StatCard({ label, value, accent }) {
  const colours = {
    blue:    'text-blue-600 bg-blue-50',
    emerald: 'text-emerald-600 bg-emerald-50',
    amber:   'text-amber-600 bg-amber-50',
    slate:   'text-slate-600 bg-slate-50',
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <p className="text-xs font-medium text-slate-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${colours[accent]?.split(' ')[0] ?? 'text-slate-800'}`}>{value}</p>
    </div>
  );
}

// ---- Main component -------------------------------------------------------

export default function AdminAnnouncementsPage() {
  const [items, setItems]           = useState([]);
  const [total, setTotal]           = useState(0);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState('');

  // Filters
  const [statusFilter, setStatus]   = useState('');
  const [catFilter, setCat]         = useState('');
  const [priFilter, setPri]         = useState('');
  const [search, setSearch]         = useState('');
  const [page, setPage]             = useState(0);
  const LIMIT = 20;

  // Modal
  const [modalOpen, setModalOpen]   = useState(false);
  const [editing, setEditing]       = useState(null);

  // Ref data for modal
  const [departments, setDepts]     = useState([]);
  const [roles, setRoles]           = useState([]);

  // Stats
  const [stats, setStats]           = useState({ total: 0, published: 0, draft: 0, archived: 0 });

  // ---- Load departments & roles for modal --------------------------------
  useEffect(() => {
    // Using onboarding API for departments (already in the project)
    fetch('/api/v1/departments', { headers: { Authorization: 'Bearer ' + (localStorage.getItem('hrms.auth.token') || '') } })
      .then((r) => r.json())
      .then((d) => setDepts(Array.isArray(d?.data) ? d.data : []))
      .catch(() => {});

    fetch('/roles', { headers: { Authorization: 'Bearer ' + (localStorage.getItem('hrms.auth.token') || '') } })
      .then((r) => r.json())
      .then((d) => setRoles(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  // ---- Load stats (rough counts from full list) --------------------------
  const loadStats = useCallback(async () => {
    try {
      const [all, pub, dft, arc] = await Promise.all([
        announcementsApi.list({ mode: 'manage', limit: 1, offset: 0 }),
        announcementsApi.list({ mode: 'manage', status: 'published', limit: 1, offset: 0 }),
        announcementsApi.list({ mode: 'manage', status: 'draft',     limit: 1, offset: 0 }),
        announcementsApi.list({ mode: 'manage', status: 'archived',  limit: 1, offset: 0 }),
      ]);
      setStats({
        total:     all.total     ?? 0,
        published: pub.total     ?? 0,
        draft:     dft.total     ?? 0,
        archived:  arc.total     ?? 0,
      });
    } catch { /* non-critical */ }
  }, []);

  // ---- Load table data ---------------------------------------------------
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await announcementsApi.list({
        mode:     'manage',
        status:   statusFilter || undefined,
        category: catFilter    || undefined,
        priority: priFilter    || undefined,
        search:   search       || undefined,
        limit:    LIMIT,
        offset:   page * LIMIT,
      });
      setItems(res.items ?? []);
      setTotal(res.total ?? 0);
    } catch (e) {
      setError(e?.message || 'Failed to load announcements');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, catFilter, priFilter, search, page]);

  useEffect(() => { load(); loadStats(); }, [load, loadStats]);
  useEffect(() => { setPage(0); }, [statusFilter, catFilter, priFilter, search]);

  // ---- Actions -----------------------------------------------------------
  const handleCreate = () => { setEditing(null); setModalOpen(true); };
  const handleEdit   = (ann) => { setEditing(ann); setModalOpen(true); };

  const handleSave = async (payload) => {
    if (editing) {
      await announcementsApi.update(editing.id, payload);
    } else {
      await announcementsApi.create(payload);
    }
    load(); loadStats();
  };

  const handlePublish = async (id) => {
    try { await announcementsApi.publish(id); load(); loadStats(); }
    catch (e) { alert(e?.message || 'Publish failed'); }
  };

  const handleArchive = async (id) => {
    if (!window.confirm('Archive this announcement?')) return;
    try { await announcementsApi.archive(id); load(); loadStats(); }
    catch (e) { alert(e?.message || 'Archive failed'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Permanently delete this announcement?')) return;
    try { await announcementsApi.remove(id); load(); loadStats(); }
    catch (e) { alert(e?.message || 'Delete failed'); }
  };

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div>
      <PageHeader
        title="Announcements"
        subtitle="Create, manage, and track company announcements."
        right={
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Announcement
          </button>
        }
      />

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total"     value={stats.total}     accent="blue"    />
        <StatCard label="Published" value={stats.published} accent="emerald" />
        <StatCard label="Drafts"    value={stats.draft}     accent="amber"   />
        <StatCard label="Archived"  value={stats.archived}  accent="slate"   />
      </div>

      {/* Filters */}
      <Card className="mb-4">
        <div className="flex flex-wrap gap-3 p-4">
          <input
            type="text"
            placeholder="Search title or content…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[180px] rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-blue-400 focus:outline-none"
          >
            <option value="">All Status</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
          <select
            value={catFilter}
            onChange={(e) => setCat(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-blue-400 focus:outline-none"
          >
            <option value="">All Categories</option>
            {ANNOUNCEMENT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={priFilter}
            onChange={(e) => setPri(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-blue-400 focus:outline-none"
          >
            <option value="">All Priorities</option>
            <option value="normal">Normal</option>
            <option value="important">Important</option>
            <option value="critical">Critical</option>
          </select>
        </div>
      </Card>

      {/* Table */}
      <Card>
        {loading ? (
          <div className="flex items-center justify-center py-16 text-slate-400 text-sm">Loading…</div>
        ) : error ? (
          <div className="flex items-center justify-center py-16 text-red-500 text-sm">{error}</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-400">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mb-3 opacity-40">
              <path d="M3 11l18-7v17l-18-7z" /><path d="M11.6 21l-1.6-7" />
            </svg>
            <p className="text-sm">No announcements found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {['Title', 'Category', 'Priority', 'Status', 'Audience', 'Reads', 'Created', 'Actions'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((ann) => (
                  <tr key={ann.id} className="border-b border-slate-50 hover:bg-slate-50/50 transition">
                    <td className="px-4 py-3 max-w-[220px]">
                      <div className="flex items-center gap-2">
                        {ann.is_pinned && (
                          <span title="Pinned" className="text-amber-500">📌</span>
                        )}
                        <span className="font-medium text-slate-900 truncate">{ann.title}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <CategoryBadge category={ann.category} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <PriorityBadge priority={ann.priority} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusBadge status={ann.status} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <ScopeBadge scope={ann.target_scope} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                      {ann.read_count ?? 0} / {ann.acknowledgement_count ?? 0} ✅
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-400 text-xs">
                      {formatDate(ann.created_at)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleEdit(ann)}
                          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 transition"
                        >
                          Edit
                        </button>
                        {ann.status === 'draft' && (
                          <button
                            onClick={() => handlePublish(ann.id)}
                            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 transition"
                          >
                            Publish
                          </button>
                        )}
                        {ann.status === 'published' && (
                          <button
                            onClick={() => handleArchive(ann.id)}
                            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-amber-600 hover:bg-amber-50 transition"
                          >
                            Archive
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(ann.id)}
                          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 transition"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
                <span className="text-xs text-slate-400">{total} total</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40 hover:bg-slate-50 transition"
                  >
                    ← Prev
                  </button>
                  <span className="text-xs text-slate-600">{page + 1} / {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40 hover:bg-slate-50 transition"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Modal */}
      <AnnouncementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        initial={editing}
        onSave={handleSave}
        departments={departments}
        roles={roles}
        isManagerMode={false}
      />
    </div>
  );
}
