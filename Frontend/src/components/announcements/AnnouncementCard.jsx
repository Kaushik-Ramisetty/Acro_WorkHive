/**
 * AnnouncementCard
 * ─────────────────
 * Shared card used across employee, manager, and admin feeds.
 *
 * Props:
 *   announcement  — the announcement object from the API
 *   onRead        — callback(id) when "Mark as read" is clicked
 *   onAcknowledge — callback(id) when "Acknowledge" is clicked
 *   showCounts    — bool: show read/ack counts (admin/manager analytics view)
 *   compact       — bool: compact layout for dashboard widgets
 */
import PriorityBadge from './PriorityBadge';
import CategoryBadge from './CategoryBadge';

function PinIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <line x1="12" y1="17" x2="12" y2="22" />
      <path d="M5 17h14l-2-7H7z" />
      <path d="M12 2v8" />
    </svg>
  );
}

function AttachmentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function AnnouncementCard({
  announcement: ann,
  onRead,
  onAcknowledge,
  showCounts = false,
  compact = false,
  className = '',
}) {
  const isUnread = !ann.is_read;
  const isAcked  = ann.is_acknowledged;

  return (
    <div
      className={`
        relative rounded-2xl border bg-white transition
        ${isUnread ? 'border-blue-200 shadow-[0_1px_4px_rgba(59,130,246,0.12)]' : 'border-slate-200 shadow-[0_1px_2px_rgba(15,23,42,0.04)]'}
        hover:shadow-md
        ${className}
      `}
    >
      {/* Left accent for critical/important */}
      {ann.priority === 'critical' && (
        <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl bg-red-500" />
      )}
      {ann.priority === 'important' && (
        <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl bg-amber-400" />
      )}

      <div className={`${compact ? 'px-4 py-3' : 'px-5 py-4'} ${ann.priority !== 'normal' ? 'pl-6' : ''}`}>
        {/* Header row */}
        <div className="flex flex-wrap items-start gap-2 mb-2">
          {ann.is_pinned && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-amber-600">
              <PinIcon /> Pinned
            </span>
          )}
          <PriorityBadge priority={ann.priority} />
          <CategoryBadge category={ann.category} />
          {isUnread && (
            <span className="ml-auto inline-flex items-center rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-bold text-white">
              NEW
            </span>
          )}
          {isAcked && (
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-semibold">
              <CheckIcon /> Acknowledged
            </span>
          )}
        </div>

        {/* Title */}
        <h3 className={`font-semibold text-slate-900 ${compact ? 'text-sm' : 'text-base'} leading-snug mb-1`}>
          {ann.title}
        </h3>

        {/* Content preview */}
        {!compact && (
          <p className="text-sm text-slate-600 leading-relaxed line-clamp-3 whitespace-pre-line">
            {ann.content}
          </p>
        )}

        {/* Footer */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <span>{ann.creator_name && `By ${ann.creator_name} · `}{formatDate(ann.created_at)}</span>
            {ann.expires_at && (
              <span>Expires {formatDate(ann.expires_at)}</span>
            )}
            {showCounts && (
              <span className="text-slate-500">
                👁 {ann.read_count ?? 0} read · ✅ {ann.acknowledgement_count ?? 0} ack'd
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {ann.attachment_path && (
              <a
                href={ann.attachment_path}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 transition"
              >
                <AttachmentIcon /> Attachment
              </a>
            )}
            {!ann.is_read && onRead && (
              <button
                onClick={() => onRead(ann.id)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
              >
                Mark as read
              </button>
            )}
            {ann.allow_acknowledgement && !isAcked && onAcknowledge && (
              <button
                onClick={() => onAcknowledge(ann.id)}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 transition"
              >
                Acknowledge
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
