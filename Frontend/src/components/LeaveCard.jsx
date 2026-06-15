// Stat card for the Leave Management header row. Mirrors the look of the
// stat tiles used on the Employees page (rounded-2xl, slate-200 border,
// shadow-sm, accent dot on the right).
export default function LeaveCard({ label, value, tone = 'slate' }) {
  const palette = {
    slate:   { text: 'text-slate-700',   bg: 'bg-slate-100' },
    amber:   { text: 'text-amber-600',   bg: 'bg-amber-50' },
    emerald: { text: 'text-emerald-600', bg: 'bg-emerald-50' },
    rose:    { text: 'text-rose-600',    bg: 'bg-rose-50' },
    blue:    { text: 'text-blue-600',    bg: 'bg-blue-50' },
  }[tone] || { text: 'text-slate-700', bg: 'bg-slate-100' };

  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
        <p className={'mt-1 text-2xl font-bold ' + palette.text}>{value}</p>
      </div>
      <div className={'h-9 w-9 rounded-xl ' + palette.bg} />
    </div>
  );
}
