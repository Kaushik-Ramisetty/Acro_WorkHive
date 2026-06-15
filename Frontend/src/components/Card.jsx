export default function Card({ title, right, children, className = '', padding = 'p-5' }) {
  return (
    <div className={'rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] ' + className}>
      {(title || right) && (
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          {title && <h3 className="text-sm font-semibold text-slate-900">{title}</h3>}
          {right && <div className="text-xs">{right}</div>}
        </div>
      )}
      <div className={padding}>{children}</div>
    </div>
  );
}
