/**
 * Full Self Service page layout — a header row with a search input,
 * followed by a responsive 1/2/3-column grid of SelfServiceCards.
 *
 * The page's grid responds to viewport width:
 *   - <  640px : 1 column (mobile)
 *   - <1024px  : 2 columns (tablet / split laptop)
 *   - ≥1024px  : 3 columns (desktop) — matches the reference layout
 *
 * The search input filters across every link label in every section.
 */
import { useMemo, useState } from "react";
import SelfServiceCard from "./SelfServiceCard";


export default function SelfServiceSection({ sections, title = "Self Service" }) {
  const [q, setQ] = useState("");

  // Apply the search filter to each section's link set. Sections that end
  // up empty are dropped by SelfServiceCard's own empty-state guard.
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return sections;
    return sections.map((s) => ({
      ...s,
      links: (s.links || []).filter((l) =>
        (l.label || "").toLowerCase().includes(needle),
      ),
    }));
  }, [sections, q]);

  const totalMatches = useMemo(
    () => filtered.reduce((sum, s) => sum + (s.links?.length || 0), 0),
    [filtered],
  );

  return (
    <div className="space-y-5">
      {/* Header — title + search */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{title}</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Quick links to view, edit, and manage your data.
          </p>
        </div>
        <div className="relative w-full sm:w-80">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search…"
            className="w-full border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
          />
          <svg
            aria-hidden
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            width="14" height="14" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
      </div>

      {/* Empty state */}
      {q.trim() && totalMatches === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center text-xs text-slate-400">
          No actions match “{q}”.
        </div>
      )}

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((s) => (
          <SelfServiceCard
            key={s.title}
            title={s.title}
            icon={s.icon}
            links={s.links}
          />
        ))}
      </div>
    </div>
  );
}
