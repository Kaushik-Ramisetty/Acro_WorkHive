/**
 * AnnouncementModal
 * ──────────────────
 * Create / Edit modal for admin and manager dashboards.
 *
 * Timezone handling
 * -----------------
 * The browser's <input type="datetime-local"> always works in the user's
 * LOCAL timezone.  The backend stores and compares everything in naive UTC.
 *
 * Two pure helpers bridge the gap:
 *
 *   localToUtcIso(localStr)
 *     "2026-05-14T18:30"  →  "2026-05-14T13:00:00.000Z"   (UTC ISO)
 *     Called in handleSave before sending to the API.
 *
 *   utcIsoToLocal(utcStr)
 *     "2026-05-14T13:00:00.000Z"  →  "2026-05-14T18:30"   (local)
 *     Called in the useEffect (edit mode) when populating the picker.
 *
 * When publishImmediately is true the publish_at field is sent as null
 * regardless of what the picker contains, so there is never an accidental
 * schedule override.
 *
 * Props:
 *   open         — bool
 *   onClose      — fn()
 *   initial      — existing announcement object (edit mode) or null (create)
 *   onSave       — async fn(payload) → called with form data
 *   departments  — array of { id, name } for the target selector
 *   roles        — array of { id, name }
 *   isManagerMode— bool: restrict to department scope only
 */
import { useState, useEffect } from 'react';
import { ANNOUNCEMENT_CATEGORIES, ANNOUNCEMENT_PRIORITIES, ANNOUNCEMENT_SCOPES } from '../../services/announcements';

// ---------------------------------------------------------------------------
// Timezone conversion helpers
// ---------------------------------------------------------------------------

/**
 * Convert a datetime-local string (interpreted as the browser's local time)
 * to a UTC ISO-8601 string suitable for the backend.
 *
 * "2026-05-14T18:30"  →  new Date(...)  →  "2026-05-14T13:00:00.000Z"
 *
 * Returns null on empty / invalid input.
 */
function localToUtcIso(localStr) {
  if (!localStr) return null;
  const d = new Date(localStr); // browser interprets as local time
  return isNaN(d.getTime()) ? null : d.toISOString();
}

/**
 * Convert a UTC ISO-8601 string (from the backend) to a datetime-local
 * string in the browser's local timezone for display in the picker.
 *
 * "2026-05-14T13:00:00.000Z"  →  "2026-05-14T18:30"  (IST example)
 *
 * Returns '' on empty / invalid input.
 */
function utcIsoToLocal(utcStr) {
  if (!utcStr) return '';
  const d = new Date(utcStr);
  if (isNaN(d.getTime())) return '';
  // Build "YYYY-MM-DDTHH:MM" using local-time getters
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getFullYear() + '-' +
    pad(d.getMonth() + 1) + '-' +
    pad(d.getDate()) + 'T' +
    pad(d.getHours()) + ':' +
    pad(d.getMinutes())
  );
}

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

function Field({ label, children, required }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-semibold text-slate-600">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition';

const EMPTY_FORM = {
  title: '',
  content: '',
  category: 'Company Updates',
  priority: 'normal',
  target_scope: 'company',
  targets: [],
  is_pinned: false,
  allow_acknowledgement: false,
  attachment_path: '',
  // Stored as datetime-local strings (local time) for the picker.
  // Converted to/from UTC ISO at the API boundary (see handleSave / useEffect).
  publish_at: '',
  expires_at: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AnnouncementModal({
  open,
  onClose,
  initial = null,
  onSave,
  departments = [],
  roles = [],
  isManagerMode = false,
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  // Default to publish-immediately for admins; managers always save as draft.
  const [publishImmediately, setPublishImmediately] = useState(!isManagerMode);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;

    if (initial) {
      // ── Edit mode ──────────────────────────────────────────────────────────
      // The backend returns publish_at / expires_at as naive-UTC ISO strings
      // (e.g. "2026-05-14T13:00:00").  We must convert them to local datetime-
      // local format so the picker shows the admin's intended local time.
      setForm({
        title:                 initial.title || '',
        content:               initial.content || '',
        category:              initial.category || 'Company Updates',
        priority:              initial.priority || 'normal',
        target_scope:          initial.target_scope || 'company',
        targets:               initial.targets || [],
        is_pinned:             initial.is_pinned || false,
        allow_acknowledgement: initial.allow_acknowledgement || false,
        attachment_path:       initial.attachment_path || '',
        // Convert stored UTC → local for the picker
        publish_at: utcIsoToLocal(initial.publish_at),
        expires_at: utcIsoToLocal(initial.expires_at),
      });
      // When editing, don't auto-publish — preserve the existing status.
      setPublishImmediately(false);
    } else {
      // ── Create mode ────────────────────────────────────────────────────────
      setForm({
        ...EMPTY_FORM,
        target_scope: isManagerMode ? 'department' : 'company',
      });
      setPublishImmediately(!isManagerMode);
    }
    setError('');
  }, [open, initial, isManagerMode]);

  if (!open) return null;

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  // ---- Target selector helpers --------------------------------------------
  const toggleDeptTarget = (deptId) => {
    const existing = form.targets.filter((t) => t.department_id === deptId);
    if (existing.length) {
      set('targets', form.targets.filter((t) => t.department_id !== deptId));
    } else {
      set('targets', [...form.targets, { department_id: deptId }]);
    }
  };

  const toggleRoleTarget = (roleId) => {
    const existing = form.targets.filter((t) => t.role_id === roleId);
    if (existing.length) {
      set('targets', form.targets.filter((t) => t.role_id !== roleId));
    } else {
      set('targets', [...form.targets, { role_id: roleId }]);
    }
  };

  const isTargetedDept = (id) => form.targets.some((t) => t.department_id === id);
  const isTargetedRole = (id) => form.targets.some((t) => t.role_id === id);

  // ---- Save ---------------------------------------------------------------
  const handleSave = async () => {
    if (!form.title.trim())   { setError('Title is required');   return; }
    if (!form.content.trim()) { setError('Content is required'); return; }

    // Convert local picker values → UTC ISO strings for the backend.
    // When publishImmediately is true, always send publish_at = null so the
    // backend's "NULL → immediately visible" path fires and no accidental
    // schedule override can happen.
    const publishAtUtc =
      publishImmediately
        ? null
        : localToUtcIso(form.publish_at);   // null if field is empty

    const expiresAtUtc = localToUtcIso(form.expires_at);   // null if empty

    const payload = {
      title:                 form.title.trim(),
      content:               form.content.trim(),
      category:              form.category,
      priority:              form.priority,
      target_scope:          isManagerMode ? 'department' : form.target_scope,
      targets:               form.targets,
      is_pinned:             form.is_pinned,
      allow_acknowledgement: form.allow_acknowledgement,
      attachment_path:       form.attachment_path || null,
      publish_at:            publishAtUtc,
      expires_at:            expiresAtUtc,
      publish_immediately:   publishImmediately,
    };

    setSaving(true);
    setError('');
    try {
      await onSave(payload);
      onClose();
    } catch (e) {
      setError(e?.message || 'Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const scopeOptions = isManagerMode
    ? ANNOUNCEMENT_SCOPES.filter((s) => s.value === 'department')
    : ANNOUNCEMENT_SCOPES;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-base font-semibold text-slate-900">
            {initial ? 'Edit Announcement' : 'New Announcement'}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <Field label="Title" required>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="Announcement title"
              maxLength={200}
            />
          </Field>

          <Field label="Content" required>
            <textarea
              className={inputCls + ' min-h-[120px] resize-y'}
              value={form.content}
              onChange={(e) => set('content', e.target.value)}
              placeholder="Write the announcement content…"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Category">
              <select className={inputCls} value={form.category} onChange={(e) => set('category', e.target.value)}>
                {ANNOUNCEMENT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>

            <Field label="Priority">
              <select className={inputCls} value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                {ANNOUNCEMENT_PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </Field>
          </div>

          {!isManagerMode && (
            <Field label="Audience Scope">
              <select
                className={inputCls}
                value={form.target_scope}
                onChange={(e) => { set('target_scope', e.target.value); set('targets', []); }}
              >
                {scopeOptions.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </Field>
          )}

          {/* Department selector */}
          {(form.target_scope === 'department' || isManagerMode) && departments.length > 0 && (
            <Field label="Target Departments">
              <div className="flex flex-wrap gap-2 mt-1">
                {departments.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => !isManagerMode && toggleDeptTarget(d.id)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition
                      ${isTargetedDept(d.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200 text-slate-600 hover:border-blue-300'}
                      ${isManagerMode ? 'cursor-default opacity-70' : 'cursor-pointer'}
                    `}
                  >
                    {d.name}
                  </button>
                ))}
              </div>
            </Field>
          )}

          {/* Role selector */}
          {form.target_scope === 'role' && !isManagerMode && roles.length > 0 && (
            <Field label="Target Roles">
              <div className="flex flex-wrap gap-2 mt-1">
                {roles.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => toggleRoleTarget(r.id)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition cursor-pointer
                      ${isTargetedRole(r.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200 text-slate-600 hover:border-blue-300'}
                    `}
                  >
                    {r.name}
                  </button>
                ))}
              </div>
            </Field>
          )}

          {/* Schedule fields — hidden when publishing immediately */}
          <div className="grid grid-cols-2 gap-4">
            <Field label={publishImmediately ? 'Publish At (ignored — publishing now)' : 'Publish At (optional, your local time)'}>
              <input
                type="datetime-local"
                className={inputCls + (publishImmediately ? ' opacity-40 cursor-not-allowed' : '')}
                value={form.publish_at}
                onChange={(e) => set('publish_at', e.target.value)}
                disabled={publishImmediately}
                title={publishImmediately ? 'Disabled: announcement will publish immediately' : 'Schedule a future publish time (your local timezone)'}
              />
            </Field>
            <Field label="Expires At (optional, your local time)">
              <input
                type="datetime-local"
                className={inputCls}
                value={form.expires_at}
                onChange={(e) => set('expires_at', e.target.value)}
                title="Announcement stops showing after this local time"
              />
            </Field>
          </div>

          <Field label="Attachment URL (optional)">
            <input
              className={inputCls}
              value={form.attachment_path}
              onChange={(e) => set('attachment_path', e.target.value)}
              placeholder="https://... or /uploads/..."
            />
          </Field>

          <div className="flex flex-wrap gap-5">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                checked={form.is_pinned}
                onChange={(e) => set('is_pinned', e.target.checked)}
              />
              <span className="text-sm text-slate-700">Pin to top</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                checked={form.allow_acknowledgement}
                onChange={(e) => set('allow_acknowledgement', e.target.checked)}
              />
              <span className="text-sm text-slate-700">Require acknowledgement</span>
            </label>
          </div>

          {/* Publish immediately — only shown in create mode for non-managers */}
          {!initial && !isManagerMode && (
            <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3">
              <label className="flex items-start gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                  checked={publishImmediately}
                  onChange={(e) => setPublishImmediately(e.target.checked)}
                />
                <div>
                  <span className="text-sm font-medium text-slate-800">Publish immediately</span>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {publishImmediately
                      ? 'Announcement will be live for all targeted employees right away. Any scheduled publish time above is ignored.'
                      : 'Announcement will be saved as a draft (or scheduled if you set a publish time). Use the Publish button in the table to make a draft live.'}
                  </p>
                </div>
              </label>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {saving
              ? 'Saving…'
              : initial
                ? 'Save Changes'
                : publishImmediately && !isManagerMode
                  ? 'Publish Now'
                  : form.publish_at
                    ? 'Schedule'
                    : 'Save as Draft'
            }
          </button>
        </div>
      </div>
    </div>
  );
}
