import Icon from './Icon';

// Filter card: search + status + leave type. Matches the Employees page
// filter card (rounded-2xl border + 12-col grid).
export default function LeaveFilters({ filters, setFilter, leaveTypes = [] }) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-12">
      <div className="relative sm:col-span-6">
        <Icon name="search" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          value={filters.q}
          onChange={(e) => setFilter({ q: e.target.value })}
          placeholder="Search by employee name…"
          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
        />
      </div>

      <select
        value={filters.status}
        onChange={(e) => setFilter({ status: e.target.value })}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 sm:col-span-3"
      >
        <option value="">All statuses</option>
        <option value="pending">Pending</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
      </select>

      <select
        value={filters.leaveType}
        onChange={(e) => setFilter({ leaveType: e.target.value })}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 sm:col-span-3"
      >
        <option value="">All leave types</option>
        {leaveTypes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
    </div>
  );
}
