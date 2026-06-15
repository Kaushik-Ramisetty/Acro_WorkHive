// Policies — read-only view used by Manager + Employee dashboards (and by
// the Admin dashboard's "Policies" route as a public preview).
//
// Database-driven now: fetches from GET /policies?mode=feed which returns
// ONLY published policies. The category filter and search box hit the same
// endpoint with query params so the backend does the filtering (and admins
// can publish a brand-new policy and have it appear here on next refresh).
//
// PDFs come back as URL paths in `current_pdf_path`:
//   - "/policies/foo.pdf"             — legacy, served by Vite's public/
//   - "/uploads/policies/12/v1_x.pdf" — new, served by the FastAPI backend
// `policyPdfUrl()` from services/policies.js resolves both flavours.

import { useEffect, useMemo, useState } from 'react';

import PageHeader from '../../../components/PageHeader';
import Card from '../../../components/Card';
import { policiesApi, policyPdfUrl } from '../../../services/policies';

// ── Tiny presentational atoms (kept inline so the file stays self-contained) ─

function PdfBadge() {
  return (
    <div className="relative flex h-12 w-10 shrink-0 items-center justify-center rounded-md bg-red-600 text-[10px] font-bold tracking-wide text-white shadow-sm">
      <span>PDF</span>
      <div className="absolute right-0 top-0 h-2 w-2 border-b border-l border-red-300 bg-red-200" />
    </div>
  );
}

function ClockIcon() {
  return (
    <svg
      width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="shrink-0" aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function fmtDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = d.toLocaleString('en-US', { month: 'short' });
    const yy = String(d.getFullYear()).slice(-2);
    return `${dd}-${mm}-${yy}`;
  } catch {
    return '';
  }
}

function PolicyRow({ policy, onAck, ackBusy }) {
  const pdfUrl = policyPdfUrl(policy.current_pdf_path);
  const updated = fmtDate(policy.current_version_created_at || policy.updated_at);
  const acked = !!policy.is_acknowledged;

  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 transition hover:border-slate-300 hover:shadow-sm">
      <div className="flex min-w-0 items-center gap-4">
        <PdfBadge />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {pdfUrl ? (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-sm font-semibold tracking-wide text-blue-700 hover:underline"
              >
                {policy.title}
              </a>
            ) : (
              <span className="truncate text-sm font-semibold tracking-wide text-slate-700">
                {policy.title}
              </span>
            )}
            {pdfUrl && (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-amber-600 underline-offset-2 hover:underline"
              >
                Preview
              </a>
            )}
            {policy.category_name && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                {policy.category_name}
              </span>
            )}
            {policy.current_version_number ? (
              <span className="text-[10px] font-semibold text-slate-400">
                v{policy.current_version_number}
              </span>
            ) : null}
          </div>
          {policy.description && (
            <p className="mt-1 truncate text-sm text-slate-600">{policy.description}</p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <ClockIcon />
          <span>Last Updated : {updated || '—'}</span>
        </div>
        {acked ? (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 border border-emerald-200">
            ✓ Acknowledged
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onAck(policy)}
            disabled={ackBusy === policy.id}
            className="rounded-full border border-teal-300 px-3 py-1 text-[11px] font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-60"
          >
            {ackBusy === policy.id ? 'Saving…' : 'Acknowledge'}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function PoliciesPage() {
  const [items, setItems]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [categories, setCategories] = useState([]);
  const [filterCat, setFilterCat] = useState('');
  const [search, setSearch]       = useState('');
  const [ackBusy, setAckBusy]     = useState(null);

  // Debounce search so we don't hammer the API on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const h = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(h);
  }, [search]);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const params = { mode: 'feed', limit: 200 };
      if (filterCat) params.category_id = filterCat;
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

  // Load categories once.
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

  // Reload when filters change.
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterCat, debouncedSearch]);

  async function handleAck(policy) {
    setAckBusy(policy.id);
    try {
      await policiesApi.acknowledge(policy.id);
      setItems((prev) => prev.map((p) => (p.id === policy.id ? { ...p, is_acknowledged: true } : p)));
    } catch (e) {
      alert(e?.message || 'Failed to acknowledge');
    } finally {
      setAckBusy(null);
    }
  }

  const grouped = useMemo(() => {
    if (!filterCat) return [['Corporate guidelines', items]];
    const cat = categories.find((c) => String(c.id) === String(filterCat));
    return [[cat?.name || 'Policies', items]];
  }, [items, filterCat, categories]);

  return (
    <div>
      <PageHeader
        title="Policies"
        subtitle="Company policies, handbooks, and acknowledgements."
      />

      <Card padding="p-5">
        {/* Filter row */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium text-slate-700">Corporate guidelines</h2>
          <div className="flex items-center gap-2">
            <select
              value={filterCat}
              onChange={(e) => setFilterCat(e.target.value)}
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
              className="w-48 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
        </div>

        <div className="border-t border-orange-200/60" />

        <div className="mt-4 space-y-3">
          {loading && (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
              Loading policies…
            </div>
          )}
          {!loading && error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
              No policies have been published yet.
            </div>
          )}
          {!loading && !error && grouped.map(([heading, rows]) => (
            <div key={heading} className="space-y-3">
              {rows.map((p) => (
                <PolicyRow key={p.id} policy={p} onAck={handleAck} ackBusy={ackBusy} />
              ))}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
