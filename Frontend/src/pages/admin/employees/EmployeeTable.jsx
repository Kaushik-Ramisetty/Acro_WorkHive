import { useMemo, useState } from 'react';

const PAGE_SIZE = 8;

function StatusPill({ status }) {
  const ok = (status || '').toLowerCase() === 'active';
  return (
    <span className={
      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
      (ok ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')
    }>
      <span className={'h-1.5 w-1.5 rounded-full ' + (ok ? 'bg-emerald-500' : 'bg-slate-400')} />
      {status || 'inactive'}
    </span>
  );
}

function RolePill({ role }) {
  const tone = {
    admin:    'bg-rose-50 text-rose-700',
    manager:  'bg-amber-50 text-amber-700',
    employee: 'bg-blue-50 text-blue-700',
  }[role] || 'bg-slate-100 text-slate-600';
  return <span className={'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold capitalize ' + tone}>{role || '—'}</span>;
}

function initialsOf(name) {
  return (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'U';
}

export default function EmployeeTable({ employees, loading, onEdit, onDelete }) {
  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(employees.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const slice = useMemo(
    () => employees.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [employees, safePage]
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              {['Name', 'Email', 'Role', 'Department', 'Designation', 'Status', 'Actions'].map((h) => (
                <th key={h} className="px-4 py-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr><td colSpan="7" className="px-4 py-8 text-center text-sm text-slate-400">Loading employees…</td></tr>
            )}
            {!loading && slice.length === 0 && (
              <tr><td colSpan="7" className="px-4 py-8 text-center text-sm text-slate-400">No employees match these filters.</td></tr>
            )}
            {!loading && slice.map((e) => (
              <tr key={e.id} className="hover:bg-slate-50/60">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-xs font-bold text-white">
                      {initialsOf(e.full_name)}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-900">{e.full_name}</p>
                      {e.employee_code && <p className="text-[11px] text-slate-500">{e.employee_code}</p>}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-700">{e.email}</td>
                <td className="px-4 py-3"><RolePill role={e.role} /></td>
                <td className="px-4 py-3 text-slate-700">{e.department || '—'}</td>
                <td className="px-4 py-3 text-slate-700">{e.designation || '—'}</td>
                <td className="px-4 py-3"><StatusPill status={e.employment_status} /></td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onEdit?.(e)}
                      className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-700 transition hover:border-brand-500 hover:text-brand-600"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete?.(e)}
                      className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 transition hover:bg-rose-100"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
        <p className="text-xs text-slate-500">
          {employees.length === 0
            ? '0 employees'
            : `Showing ${(safePage - 1) * PAGE_SIZE + 1}–${Math.min(safePage * PAGE_SIZE, employees.length)} of ${employees.length}`}
        </p>
        <div className="flex items-center gap-1">
          <button
            disabled={safePage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
          >
            Prev
          </button>
          <span className="px-2 text-xs text-slate-500">{safePage} / {totalPages}</span>
          <button
            disabled={safePage >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
