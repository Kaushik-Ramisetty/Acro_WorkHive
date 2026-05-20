// Modal used by AdminPoliciesPage for two flows:
//   1. Create new policy (mode='create')          → POST /policies, then optional PDF upload
//   2. Add a new version to an existing policy    (mode='new-version')
//
// Edit-metadata is handled inline on the row (separate AdminPoliciesPage flow)
// so this modal stays focused on "content" changes that produce versions.

import { useEffect, useState } from 'react';
import { policiesApi } from '../../../services/policies';

export default function PolicyFormModal({
  open,
  mode = 'create',                  // 'create' | 'new-version'
  policy = null,                    // required when mode === 'new-version'
  categories = [],
  onClose,
  onSaved,
}) {
  const [title, setTitle]             = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId]   = useState('');
  const [changeSummary, setChangeSummary] = useState('');
  const [effectiveDate, setEffectiveDate] = useState('');
  const [expiryDate, setExpiryDate]       = useState('');
  const [publishNow, setPublishNow]       = useState(true);
  const [file, setFile]               = useState(null);
  const [busy, setBusy]               = useState(false);
  const [err, setErr]                 = useState(null);

  useEffect(() => {
    if (!open) return;
    if (mode === 'create') {
      setTitle('');
      setDescription('');
      setCategoryId('');
      setChangeSummary('');
      setEffectiveDate('');
      setExpiryDate('');
      setPublishNow(true);
      setFile(null);
    } else if (mode === 'new-version' && policy) {
      setTitle(policy.title || '');
      setDescription(policy.description || '');
      setCategoryId(policy.category_id ? String(policy.category_id) : '');
      setChangeSummary('');
      setEffectiveDate('');
      setExpiryDate('');
      setPublishNow(true);
      setFile(null);
    }
    setErr(null);
  }, [open, mode, policy]);

  if (!open) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim() && mode === 'create') {
      setErr('Title is required.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      let saved;
      if (mode === 'create') {
        saved = await policiesApi.create({
          title: title.trim(),
          description: description.trim() || null,
          category_id: categoryId ? Number(categoryId) : null,
          change_summary: changeSummary.trim() || null,
          effective_date: effectiveDate || null,
          expiry_date:    expiryDate    || null,
          publish_immediately: !!publishNow,
        });
        if (file) {
          await policiesApi.uploadPdfToLatest(saved.id, file);
        }
      } else {
        // new-version on an existing policy
        const v = await policiesApi.createVersion(policy.id, {
          change_summary: changeSummary.trim() || null,
          effective_date: effectiveDate || null,
          expiry_date:    expiryDate    || null,
          publish: !!publishNow,
        });
        if (file) {
          await policiesApi.uploadPdf(policy.id, v.id, file);
        }
        saved = await policiesApi.one(policy.id);
      }
      onSaved && onSaved(saved);
      onClose && onClose();
    } catch (e2) {
      setErr(e2?.message || 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  const isCreate = mode === 'create';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-800">
              {isCreate ? 'New Policy' : `New version of "${policy?.title}"`}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {isCreate
                ? 'Creates the policy and an initial v1. PDF is optional.'
                : 'Every change is tracked as a new version — previous versions stay in the DB.'}
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

        <form onSubmit={handleSubmit} className="space-y-4 px-6 py-5">
          {isCreate && (
            <>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Title <span className="text-rose-500">*</span>
                </label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
                  placeholder="e.g. Code of Conduct"
                />
              </div>

              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
                  placeholder="Short summary shown in the policies list"
                />
              </div>

              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Category
                </label>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
                >
                  <option value="">— Uncategorised —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Effective Date
              </label>
              <input
                type="date"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Expiry Date
              </label>
              <input
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Change Summary
            </label>
            <input
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
              placeholder='e.g. "Updated section 4 — remote work hours"'
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
              PDF (optional, max 20 MB)
            </label>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="w-full rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-600"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={publishNow}
              onChange={(e) => setPublishNow(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-400"
            />
            Publish immediately
          </label>

          {err && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {err}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-teal-500 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-600 disabled:opacity-60"
            >
              {busy ? 'Saving…' : isCreate ? 'Create policy' : 'Add new version'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
