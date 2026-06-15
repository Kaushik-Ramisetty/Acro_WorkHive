// Version history modal for a policy.
//
// Admin/HR-only — lets you see every version, preview the PDF, and promote
// any past version back to "current" if needed (rollback).

import { useEffect, useState } from 'react';
import { policiesApi, policyPdfUrl } from '../../../services/policies';

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return '—'; }
}

export default function PolicyVersionsModal({ open, policy, onClose, onChanged }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [err, setErr]           = useState(null);
  const [busy, setBusy]         = useState(null);

  useEffect(() => {
    if (!open || !policy) return;
    let cancelled = false;
    (async () => {
      setLoading(true); setErr(null);
      try {
        const rows = await policiesApi.listVersions(policy.id);
        if (!cancelled) setVersions(Array.isArray(rows) ? rows : []);
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Failed to load versions');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, policy]);

  if (!open || !policy) return null;

  async function promote(v) {
    setBusy(v.id);
    try {
      await policiesApi.publishVersion(policy.id, v.id);
      const fresh = await policiesApi.listVersions(policy.id);
      setVersions(Array.isArray(fresh) ? fresh : []);
      onChanged && onChanged();
    } catch (e) {
      alert(e?.message || 'Failed to promote version');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold text-slate-800">
              Version history — {policy.title}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Current version: v{policy.current_version_number || '—'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          {loading && <div className="text-sm text-slate-500">Loading…</div>}
          {err && <div className="text-sm text-rose-700">{err}</div>}
          {!loading && !err && versions.length === 0 && (
            <div className="text-sm text-slate-500">No versions yet.</div>
          )}
          <ul className="space-y-2">
            {versions.map((v) => {
              const isCurrent = policy.current_version_id === v.id;
              const pdfUrl = policyPdfUrl(v.pdf_path);
              return (
                <li
                  key={v.id}
                  className={`rounded-xl border px-4 py-3 ${
                    isCurrent ? 'border-teal-300 bg-teal-50/40' : 'border-slate-200 bg-white'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-800">v{v.version_number}</span>
                        {isCurrent && (
                          <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-teal-700">
                            Current
                          </span>
                        )}
                        {v.is_published && !isCurrent && (
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                            Published before
                          </span>
                        )}
                      </div>
                      {v.change_summary && (
                        <p className="mt-1 text-xs text-slate-600">{v.change_summary}</p>
                      )}
                      <p className="mt-1 text-[11px] text-slate-400">
                        Created {fmt(v.created_at)} · Effective {v.effective_date || '—'}
                        {v.expiry_date ? ` · Expires ${v.expiry_date}` : ''}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {pdfUrl && (
                        <a
                          href={pdfUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rounded-lg border border-slate-200 px-3 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          Open PDF
                        </a>
                      )}
                      {!isCurrent && (
                        <button
                          type="button"
                          onClick={() => promote(v)}
                          disabled={busy === v.id}
                          className="rounded-lg bg-teal-500 px-3 py-1 text-[11px] font-semibold text-white hover:bg-teal-600 disabled:opacity-60"
                        >
                          {busy === v.id ? 'Promoting…' : 'Make current'}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="flex items-center justify-end border-t border-slate-100 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
