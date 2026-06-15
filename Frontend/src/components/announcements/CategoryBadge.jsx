/**
 * CategoryBadge — subtle teal pill for announcement categories.
 */
export default function CategoryBadge({ category, className = '' }) {
  if (!category) return null;
  return (
    <span className={`inline-flex items-center rounded-full bg-teal-50 px-2.5 py-0.5 text-xs font-medium text-teal-700 border border-teal-200 ${className}`}>
      {category}
    </span>
  );
}
