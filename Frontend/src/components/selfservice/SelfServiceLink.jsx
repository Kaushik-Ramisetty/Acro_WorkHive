/**
 * A single link inside a Self Service card.
 *
 * Renders as an inline anchor-style button. When `onClick` is provided the
 * link is interactive; otherwise it's a placeholder (the brief says
 * "dummy links" / "frontend only"). The look matches the project's
 * existing slate/teal palette — no new colors are introduced.
 *
 * Optional `pipe` boolean renders a trailing pipe separator so a row
 * of inline links can use the same compact look as the reference image
 * without baking the pipe character into the label.
 */
export default function SelfServiceLink({ label, onClick, pipe = true }) {
  const isInteractive = typeof onClick === "function";

  return (
    <span className="inline whitespace-nowrap">
      {isInteractive ? (
        <button
          type="button"
          onClick={onClick}
          className="text-[13px] text-slate-700 hover:text-teal-600 hover:underline transition-colors"
        >
          {label}
        </button>
      ) : (
        <span className="text-[13px] text-slate-700 cursor-default">
          {label}
        </span>
      )}
      {pipe && <span className="text-slate-300 mx-1.5">|</span>}
    </span>
  );
}
