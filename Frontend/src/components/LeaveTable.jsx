import { useMemo, useState } from 'react';

const PAGE_SIZE = 8;

function StatusPill({ status }) {
  const tone = {
    pending:  { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-500' },
    approved: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
    rejected: { bg: 'bg-rose-50',    text: 'text-rose-700',    dot: 'bg-rose-500' },
  }[status] || { bg: 'bg-slate-100', text: 'text-slate-600', dot: 'bg-slate-400' };

  return (
    <span className={'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' + tone.bg + ' ' + tone.text}>
      <span className={'h-1.5 w-1.5 rounded-full ' + tone.dot} />
      {status || 'unknown'}
    </span>
  );
}

function LeaveTypeChip({ type }) {
  const tone = {
    'Casual':      'bg-blue-50 text-blue-700',
    'Sick':        'bg-rose-50 text-rose-700',
    'Earned':      'bg-emerald-50 text-emerald-700',
    'Maternity':   'bg-pink-50 text-pink-700',
    'Paternity':   'bg-indigo-50 text-indigo-700',
    'Bereavement': 'bg-slate-100 text-slate-600',
    'WFH':         'bg-amber-50 text-amber-700',
  }[type] || 'bg-slate-100 text-slate-600';
  return <span className={'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ' + tone}>{type}</span>;
}

function initialsOf(name) {
  return (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'U';
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function LeaveTable({ rows = [], loading = false, onRowClick, onApprove, onReject, selfId }) {
  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const slice = useMemo(
    () => rows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [rows, safePage]
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              {['Employee', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Actions'].map((h) => (
                <th key={h} className="px-4 py-3 text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr><td colSpan="7" className="px-4 py-8 text-center text-sm text-slate-400">Loading leave requests…</td></tr>
            )}
            {!loading && slice.length === 0 && (
              <tr><td colSpan="7" className="px-4 py-8 text-center text-sm text-slate-400">No leave requests match these filters.</td></tr>
            )}
            {!loading && slice.map((r) => (
              <tr
                key={r.id}
                className="cursor-pointer hover:bg-slate-50/60"
                onClick={() => onRowClick?.(r)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-xs font-bold text-white">
                      {initialsOf(r.employeeName)}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-900">{r.employeeName}</p>
                      {r.employeeCode && <p className="text-[11px] text-slate-500">{r.employeeCode}</p>}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3"><LeaveTypeChip type={r.leaveType} /></td>
                <td className="px-4 py-3 text-slate-700">{fmtDate(r.startDate)}</td>
                <td className="px-4 py-3 text-slate-700">{fmtDate(r.endDate)}</td>
                <td className="px-4 py-3 text-slate-700">{r.days}</td>
                <td className="px-4 py-3"><StatusPill status={r.status} /></td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  {r.status === 'pending' && (!selfId || r.employee_id !== selfId) ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => onApprove?.(r)}
                        className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 transition hover:bg-emerald-100"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => onReject?.(r)}
                        className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 transition hover:bg-rose-100"
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <span className="text-[11px] text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
        <p className="text-xs text-slate-500">
          {rows.length === 0
            ? '0 requests'
            : `Showing ${(safePage - 1) * PAGE_SIZE + 1}–${Math.min(safePage * PAGE_SIZE, rows.length)} of ${rows.length}`}
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
