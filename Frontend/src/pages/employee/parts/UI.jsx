// Small reusable atoms shared across employee dashboard pages.
// Visual style matches the rest of the dashboard (rounded-xl, border-slate-100, teal #14b8a6).

export const PageTitle = ({ title, sub, right }) => (
  <div className="flex items-center justify-between mb-5">
    <div>
      <h1 className="text-xl font-bold text-slate-800">{title}</h1>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
    {right && <div className="flex items-center gap-2">{right}</div>}
  </div>
);

export const Card = ({ children, className = "", padding = "p-5" }) => (
  <div className={`bg-white rounded-xl border border-slate-100 shadow-sm ${padding} ${className}`}>
    {children}
  </div>
);

export const Badge = ({ children, tone = "slate" }) => {
  const tones = {
    slate:   "bg-slate-100 text-slate-600",
    teal:    "bg-teal-50 text-teal-700",
    green:   "bg-emerald-50 text-emerald-700",
    blue:    "bg-blue-50 text-blue-700",
    amber:   "bg-amber-50 text-amber-700",
    rose:    "bg-rose-50 text-rose-700",
    violet:  "bg-violet-50 text-violet-700",
    orange:  "bg-orange-50 text-orange-700",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${tones[tone] || tones.slate}`}>
      {children}
    </span>
  );
};

export const Pill = ({ children, tone = "slate" }) => {
  const tones = {
    slate:  "bg-slate-100 text-slate-600",
    teal:   "bg-teal-50 text-teal-700",
    green:  "bg-emerald-50 text-emerald-700",
    blue:   "bg-blue-50 text-blue-700",
    amber:  "bg-amber-50 text-amber-700",
    rose:   "bg-rose-50 text-rose-700",
    violet: "bg-violet-50 text-violet-700",
  };
  return <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-semibold ${tones[tone] || tones.slate}`}>{children}</span>;
};

export const StatCard = ({ label, value, sub, subColor = "#64748b", iconBg = "#f0fdfa", icon }) => (
  <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
    <div className="flex items-center justify-between mb-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: iconBg }}>
        {icon}
      </div>
    </div>
    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">{label}</div>
    <div className="text-2xl font-bold text-slate-800 mb-0.5">{value}</div>
    {sub && <div className="text-xs font-medium" style={{ color: subColor }}>{sub}</div>}
  </div>
);

export const PrimaryButton = ({ children, onClick, className = "", style }) => (
  <button
    onClick={onClick}
    className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white transition-colors hover:brightness-110 ${className}`}
    style={{ background: "#14b8a6", ...style }}
  >
    {children}
  </button>
);

export const OutlineButton = ({ children, onClick, className = "" }) => (
  <button
    onClick={onClick}
    className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-slate-600 border border-slate-200 hover:bg-slate-50 transition-colors ${className}`}
  >
    {children}
  </button>
);

export const TableShell = ({ headers = [], children }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-100">
    <table className="w-full text-sm">
      <thead className="bg-slate-50">
        <tr>
          {headers.map((h, i) => (
            <th key={i} className="px-4 py-3 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wider">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-slate-100">{children}</tbody>
    </table>
  </div>
);
