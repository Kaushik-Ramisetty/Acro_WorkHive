/**
 * One grouped card on the Self Service page (e.g. "View", "Edit",
 * "Salary"). Renders an icon + title at the top and a wrapped row of
 * inline links separated by pipes.
 *
 * Empty card (after a search filter strips all links) renders nothing
 * so the grid collapses gracefully.
 */
import SelfServiceLink from "./SelfServiceLink";


export default function SelfServiceCard({ title, icon, links }) {
  if (!links || links.length === 0) return null;

  return (
    <section className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
      <div className="flex items-center gap-3 mb-3">
        <span
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: "#ccfbf1", color: "#0f766e" }}
          aria-hidden
        >
          {icon}
        </span>
        <h2 className="text-sm font-bold tracking-wide" style={{ color: "#0f766e" }}>
          {title}
        </h2>
      </div>

      {/* Inline pipe-separated link layout, mirrors the reference. The last
          item drops its trailing pipe for visual hygiene. */}
      <div className="text-[13px] leading-7 text-slate-700">
        {links.map((l, i) => (
          <SelfServiceLink
            key={l.label + i}
            label={l.label}
            onClick={l.onClick}
            pipe={i < links.length - 1}
          />
        ))}
      </div>
    </section>
  );
}
