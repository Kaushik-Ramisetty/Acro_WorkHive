import Icon from './Icon';

const TONES = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-600' },
  green:   { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  red:     { bg: 'bg-rose-50',    text: 'text-rose-600' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-600' },
  purple:  { bg: 'bg-violet-50',  text: 'text-violet-600' },
  teal:    { bg: 'bg-teal-50',    text: 'text-teal-600' },
  slate:   { bg: 'bg-slate-100',  text: 'text-slate-600' },
};

export default function StatCard({ label, value, icon, tone = 'blue', delta, deltaTone = 'green', sub }) {
  const t = TONES[tone] || TONES.blue;
  const deltaT = deltaTone === 'red' ? 'text-rose-600' : deltaTone === 'slate' ? 'text-slate-500' : 'text-emerald-600';
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between">
        <div className={'flex h-9 w-9 items-center justify-center rounded-lg ' + t.bg + ' ' + t.text}>
          {icon && <Icon name={icon} className="h-5 w-5" />}
        </div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 text-right max-w-[140px]">
          {label}
        </p>
      </div>
      <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
      {(delta || sub) && (
        <p className={'mt-1 text-xs ' + (delta ? deltaT : 'text-slate-500')}>
          {delta && <span className="font-semibold">{delta}</span>}
          {delta && sub && <span className="ml-1 text-slate-500">{sub}</span>}
          {!delta && sub}
        </p>
      )}
    </div>
  );
}
