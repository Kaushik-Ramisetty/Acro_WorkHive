// Admin/HR Policies management page.
//
// Sits behind /admin-dashboard/policies and uses the database-backed API
// exclusively. Managers and Employees keep using the read-only PoliciesPage.
//
// Capabilities:
//   - List all policies (any status) with search + category filter
//   - Create a new policy + optional PDF upload + initial v1
//   - Edit metadata (title / description / category) inline
//   - Create a new version (every edit → audit trail)
//   - View version history + roll back to a previous version
//   - Publish / archive / reactivate / soft-delete (drafts only)

import { useEffect, useMemo, useState } from 'react';
import PageHeader from '../../../components/PageHeader';
import Card from '../../../components/Card';
import { policiesApi, policyPdfUrl } from '../../../services/policies';
import PolicyFormModal from './PolicyFormModal';
import PolicyVersionsModal from './PolicyVersionsModal';

function StatusPill({ status }) {
  const cls = {
    draft:     'bg-amber-50 text-amber-700 border-amber-200',
    published: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    archived:  'bg-slate-100 text-slate-600 border-slate-200',
  }[status] || 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {status}
    </span>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(); } catch { return '—'; }
}

export default function AdminPoliciesPage() {
  const [items, setItems]           = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const [statusFilter, setStatusFilter] = useState('');     // '' | draft | published | archived
  const [catFilter, setCatFilter]       = useState('');
  const [search, setSearch]             = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const [formOpen, setFormOpen]       = useState(false);
  const [formMode, setFormMode]       = useState('create');
  const [formPolicy, setFormPolicy]   = useState(null);

  const [versionsFor, setVersionsFor] = useState(null);
  const [busyId, setBusyId]           = useState(null);
  const [editingId, setEditingId]     = useState(null);
  const [editDraft, setEditDraft]     = useState({ title: '', description: '', category_id: '' });

  useEffect(() => {
    const h = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(h);
  }, [search]);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const params = { mode: 'manage', limit: 200 };
      if (statusFilter) params.status = statusFilter;
      if (catFilter)    params.category_id = catFilter;
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await policiesApi.list(params);
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e) {
      setError(e?.message || 'Failed to load policies');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cats = await policiesApi.categories();
        if (!cancelled) setCategories(Array.isArray(cats) ? cats : []);
      } catch { /* non-fatal */ }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, catFilter, debouncedSearch]);

  const counts = useMemo(() => {
    const c = { all: items.length, draft: 0, published: 0, archived: 0 };
    items.forEach((p) => { if (c[p.status] !== undefined) c[p.status] += 1; });
    return c;
  }, [items]);

  function startEdit(p) {
    setEditingId(p.id);
    setEditDraft({
      title: p.title || '',
      description: p.description || '',
      category_id: p.category_id ? String(p.category_id) : '',
    });
  }

  async function saveEdit(p) {
    setBusyId(p.id);
    try {
      await policiesApi.update(p.id, {
        title: editDraft.title,
        description: editDraft.description || null,
        category_id: editDraft.category_id ? Number(editDraft.category_id) : null,
      });
      setEditingId(null);
      await refresh();
    } catch (e) {
      alert(e?.message || 'Save failed');
    } finally {
      setBusyId(null);
    }
  }

  async function doAction(p, action) {
    if (action === 'delete' && !confirm(`Delete draft "${p.title}"? This cannot be undone.`)) return;
    setBusyId(p.id);
    try {
      if (action === 'publish')    await policiesApi.publish(p.id);
      if (action === 'archive')    await policiesApi.archive(p.id);
      if (action === 'reactivate') await policiesApi.reactivate(p.id);
      if (action === 'delete')     await policiesApi.remove(p.id);
      await refresh();
    } catch (e) {
      alert(e?.message || `${action} failed`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Policies"
        subtitle="Create, version, publish and archive company policies."
        right={
          <button
            onClick={() => { setFormMode('create'); setFormPolicy(null); setFormOpen(true); }}
            className="rounded-lg bg-teal-500 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-600"
          >
            + New Policy
          </button>
        }
      />

      {/* Filter strip */}
      <Card padding="p-4" className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          {[
            ['',          `All (${counts.all})`],
            ['draft',     `Draft (${counts.draft})`],
            ['published', `Published (${counts.published})`],
            ['archived',  `Archived (${counts.archived})`],
          ].map(([val, label]) => {
            const active = statusFilter === val;
            return (
              <button
                key={val || 'all'}
                onClick={() => setStatusFilter(val)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  active
                    ? 'bg-teal-500 text-white'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {label}
              </button>
            );
          })}

          <span className="mx-2 hidden h-6 w-px bg-slate-200 sm:inline-block" />

          <select
            value={catFilter}
            onChange={(e) => setCatFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>

          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search policies…"
            className="ml-auto w-56 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
          />
        </div>
      </Card>

      <Card padding="p-0">
        {loading && (
          <div className="p-8 text-center text-sm text-slate-500">Loading policies…</div>
        )}
        {!loading && error && (
          <div className="p-6 text-sm text-rose-700">{error}</div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="p-8 text-center text-sm text-slate-500">
            No policies match your filters. Click <strong>+ New Policy</strong> to create one.
          </div>
        )}
        {!loading && !error && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-left">Title</th>
                  <th className="px-4 py-3 text-left">Category</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Current</th>
                  <th className="px-4 py-3 text-left">Updated</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((p) => {
                  const pdfUrl = policyPdfUrl(p.current_pdf_path);
                  const isEditing = editingId === p.id;
                  return (
                    <tr key={p.id} className="hover:bg-slate-50/60">
                      <td className="px-4 py-3 align-top">
                        {isEditing ? (
                          <div className="space-y-2">
                            <input
                              value={editDraft.title}
                              onChange={(e) => setEditDraft({ ...editDraft, title: e.target.value })}
                              className="w-full rounded-lg border border-slate-200 px-2 py-1 text-sm"
                            />
                            <textarea
                              value={editDraft.description}
                              onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
                              rows={2}
                              className="w-full rounded-lg border border-slate-200 px-2 py-1 text-xs"
                              placeholder="Description"
                            />
                          </div>
                        ) : (
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-800">{p.title}</span>
                              {p.current_version_number ? (
                                <span className="text-[10px] font-semibold text-slate-400">
                                  v{p.current_version_number}
                                </span>
                              ) : null}
                            </div>
                            {p.description && (
                              <div className="mt-0.5 truncate text-xs text-slate-500">
                                {p.description}
                              </div>
                            )}
                            {p.acknowledgement_count != null && (
                              <div className="mt-1 text-[10px] text-slate-400">
                                {p.acknowledgement_count} acknowledgement{p.acknowledgement_count === 1 ? '' : 's'} · {p.versions_count} version{p.versions_count === 1 ? '' : 's'}
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {isEditing ? (
                          <select
                            value={editDraft.category_id}
                            onChange={(e) => setEditDraft({ ...editDraft, category_id: e.target.value })}
                            className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                          >
                            <option value="">— Uncategorised —</option>
                            {categories.map((c) => (
                              <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-xs text-slate-600">{p.category_name || '—'}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <StatusPill status={p.status} />
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-slate-600">
                        {pdfUrl ? (
                          <a
                            href={pdfUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-700 hover:underline"
                          >
                            View PDF
                          </a>
                        ) : (
                          <span className="text-slate-400">No PDF</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-slate-500">
                        {fmt(p.updated_at)}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <div className="flex flex-wrap items-center justify-end gap-1.5">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => saveEdit(p)}
                                disabled={busyId === p.id}
                                className="rounded-md bg-teal-500 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-teal-600 disabled:opacity-60"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingId(null)}
                                className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                              >
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => startEdit(p)}
                                disabled={p.status === 'archived'}
                                className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                                title={p.status === 'archived' ? 'Reactivate first' : ''}
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => { setFormMode('new-version'); setFormPolicy(p); setFormOpen(true); }}
                                disabled={p.status === 'archived'}
                                className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                              >
                                + Version
                              </button>
                              <button
                                onClick={() => setVersionsFor(p)}
                                className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                              >
                                History
                              </button>
                              {p.status === 'draft' && (
                                <button
                                  onClick={() => doAction(p, 'publish')}
                                  disabled={busyId === p.id}
                                  className="rounded-md bg-emerald-500 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-emerald-600 disabled:opacity-60"
                                >
                                  Publish
                                </button>
                              )}
                              {p.status === 'published' && (
                                <button
                                  onClick={() => doAction(p, 'archive')}
                                  disabled={busyId === p.id}
                                  className="rounded-md bg-amber-500 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-amber-600 disabled:opacity-60"
                                >
                                  Archive
                                </button>
                              )}
                              {p.status === 'archived' && (
                                <button
                                  onClick={() => doAction(p, 'reactivate')}
                                  disabled={busyId === p.id}
                                  className="rounded-md bg-slate-700 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                                >
                                  Reactivate
                                </button>
                              )}
                              {p.status === 'draft' && (
                                <button
                                  onClick={() => doAction(p, 'delete')}
                                  disabled={busyId === p.id}
                                  className="rounded-md border border-rose-200 px-2.5 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                                >
                                  Delete
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PolicyFormModal
        open={formOpen}
        mode={formMode}
        policy={formPolicy}
        categories={categories}
        onClose={() => setFormOpen(false)}
        onSaved={() => refresh()}
      />

      <PolicyVersionsModal
        open={!!versionsFor}
        policy={versionsFor}
        onClose={() => setVersionsFor(null)}
        onChanged={() => refresh()}
      />
    </div>
  );
}
