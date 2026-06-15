/**
 * PriorityBadge — small coloured pill for announcement priority levels.
 * Matches the existing project's Tailwind utility style.
 */
const STYLES = {
  critical:  'bg-red-100 text-red-700 border border-red-200',
  important: 'bg-amber-100 text-amber-700 border border-amber-200',
  normal:    'bg-slate-100 text-slate-600 border border-slate-200',
};

const LABELS = {
  critical:  '🔴 Critical',
  important: '🟡 Important',
  normal:    'Normal',
};

export default function PriorityBadge({ priority = 'normal', className = '' }) {
  const style = STYLES[priority] ?? STYLES.normal;
  const label = LABELS[priority] ?? priority;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style} ${className}`}>
      {label}
    </span>
  );
}
