/**
 * Salary Revision History — enterprise audit trail for all salary changes.
 *
 * Shows every salary revision across employees with:
 *  - Old CTC → New CTC diff
 *  - Effective date (which payroll month onwards the new salary applies)
 *  - Who revised and when
 *  - Revision reason
 *  - Side-by-side comparison modal with changed-component highlighting
 *  - CSV export
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function fmtL(n) {
  if (!n && n !== 0) return '—';
  const lakh = Number(n) / 100000;
  return `₹${lakh.toFixed(2)}L`;
}

function diffBadge(diff, pct) {
  if (!diff && diff !== 0) return null;
  const up = diff >= 0;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
      up ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
    }`}>
      {up ? '▲' : '▼'} {fmt(Math.abs(diff))} ({Math.abs(pct).toFixed(1)}%)
    </span>
  );
}

// ─── Comparison Modal ─────────────────────────────────────────────────────────

function ComparisonModal({ revision, onClose }) {
  const { comparison, employee_name, employee_code, department, designation,
          effective_from, revision_reason, revised_by_name, revised_at } = revision;

  const changed = (row) => Math.abs((row.new || 0) - (row.old || 0)) > 0.01;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-8 mb-8 w-full max-w-3xl bg-white rounded-2xl shadow-xl">

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Salary Revision Comparison</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {employee_name} · {employee_code} · {department}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg mt-0.5">✕</button>
        </div>

        {/* Meta strip */}
        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <p className="text-slate-400 mb-0.5">Designation</p>
            <p className="font-medium text-slate-700">{designation || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Effective From</p>
            <p className="font-mono font-semibold text-brand-700">{effective_from || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Revised By</p>
            <p className="font-medium text-slate-700">{revised_by_name || '—'}</p>
          </div>
          <div>
            <p className="text-slate-400 mb-0.5">Revised At</p>
            <p className="font-mono text-slate-600">
              {revised_at ? new Date(revised_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}
            </p>
          </div>
        </div>

        {revision_reason && (
          <div className="px-6 py-2.5 bg-amber-50 border-b border-amber-100">
            <p className="text-xs text-amber-800">
              <strong>Reason:</strong> {revision_reason}
            </p>
          </div>
        )}

        {/* Comparison table */}
        <div className="p-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                <th className="px-4 py-2.5 text-left font-semibold tracking-wider">Component</th>
                <th className="px-4 py-2.5 text-right font-semibold tracking-wider text-slate-500">Old</th>
                <th className="px-4 py-2.5 text-right font-semibold tracking-wider text-slate-500">New</th>
                <th className="px-4 py-2.5 text-right font-semibold tracking-wider">Change</th>
              </tr>
            </thead>
            <tbody>
              {comparison.components.map((row, i) => {
                const delta = (row.new || 0) - (row.old || 0);
                const isChanged = Math.abs(delta) > 0.01;
                const isHighlight = ['Annual CTC', 'Gross Monthly', 'Net Monthly'].includes(row.label);
                return (
                  <tr
                    key={i}
                    className={`border-b border-slate-50 transition ${
                      isHighlight
                        ? 'bg-brand-50 font-semibold'
                        : isChanged
                        ? 'bg-amber-50'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="px-4 py-2.5 text-slate-700">
                      {row.label}
                      {isChanged && (
                        <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-amber-500 align-middle" title="Changed" />
                      )}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-mono ${isChanged ? 'text-slate-400 line-through' : 'text-slate-600'}`}>
                      {fmt(row.old)}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-mono font-semibold ${
                      isChanged
                        ? delta > 0 ? 'text-emerald-700' : 'text-rose-700'
                        : 'text-slate-700'
                    }`}>
                      {fmt(row.new)}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {isChanged ? (
                        <span className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                          delta > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                        }`}>
                          {delta > 0 ? '+' : ''}{fmt(delta)}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <p className="mt-4 text-xs text-slate-400">
            Amber rows = changed components. Closed payrolls before {effective_from || 'this effective date'} continue to use the old salary.
          </p>
        </div>

        <div className="flex justify-end px-6 pb-6">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SalaryRevisionHistory() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [revisions, setRevisions] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEmpId, setSelectedEmpId] = useState('');
  const [search, setSearch] = useState('');
  const [comparison, setComparison] = useState(null);  // full revision detail for modal
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = async (empId) => {
    setLoading(true);
    try {
      const [revs, emps] = await Promise.all([
        financeApi.listSalaryRevisions({ employeeId: empId || undefined }),
        financeApi.listEmployees(),
      ]);
      setRevisions(revs);
      setEmployees(emps);
    } catch (e) {
      console.error('Failed to load revisions', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleEmpFilter = (e) => {
    const val = e.target.value;
    setSelectedEmpId(val);
    load(val || undefined);
  };

  const openComparison = async (revisionId) => {
    setLoadingDetail(true);
    try {
      const detail = await financeApi.getSalaryRevision(revisionId);
      setComparison(detail);
    } catch (e) {
      console.error('Failed to load revision detail', e);
    } finally {
      setLoadingDetail(false);
    }
  };

  const filtered = revisions.filter((r) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (r.employee_name || '').toLowerCase().includes(q) ||
      (r.employee_code || '').toLowerCase().includes(q) ||
      (r.department || '').toLowerCase().includes(q) ||
      (r.revision_reason || '').toLowerCase().includes(q) ||
      (r.revised_by_name || '').toLowerCase().includes(q)
    );
  });

  // Summary stats
  const totalRevisions = filtered.length;
  const avgIncrease = filtered.length
    ? Math.round(filtered.reduce((s, r) => s + (r.ctc_difference || 0), 0) / filtered.length)
    : 0;
  const increments = filtered.filter((r) => (r.ctc_difference || 0) > 0).length;
  const reductions = filtered.filter((r) => (r.ctc_difference || 0) < 0).length;

  return (
    <div className="space-y-6">
      {comparison && (
        <ComparisonModal revision={comparison} onClose={() => setComparison(null)} />
      )}

      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          if (role_ === 'admin') navigate('/admin-dashboard/payroll');
          else if (role_ === 'finance_head' || role_ === 'financehead') navigate('/employee-dashboard/finance-head-payroll');
          else navigate('/employee-dashboard/finance-payroll');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      {/* Page header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Salary Revision History</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Complete audit trail of all salary revisions. Closed payrolls are never modified.
          </p>
        </div>
        <a
          href={`/api${financeApi.salaryRevisionReportUrl(selectedEmpId || undefined)}`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition"
        >
          ↓ Export CSV
        </a>
      </div>

      {/* Summary chips */}
      <div className="flex flex-wrap gap-3">
        <div className="rounded-lg bg-white border border-slate-200 px-4 py-2 text-sm shadow-sm">
          <span className="text-slate-500">Total Revisions: </span>
          <span className="font-bold text-slate-800">{totalRevisions}</span>
        </div>
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2 text-sm">
          <span className="text-emerald-600">Increments: </span>
          <span className="font-bold text-emerald-800">{increments}</span>
        </div>
        {reductions > 0 && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-2 text-sm">
            <span className="text-rose-600">Reductions: </span>
            <span className="font-bold text-rose-800">{reductions}</span>
          </div>
        )}
        {totalRevisions > 0 && (
          <div className="rounded-lg bg-brand-50 border border-brand-200 px-4 py-2 text-sm">
            <span className="text-brand-600">Avg Change: </span>
            <span className={`font-bold ${avgIncrease >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {avgIncrease >= 0 ? '+' : ''}{fmt(avgIncrease)}
            </span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={selectedEmpId}
          onChange={handleEmpFilter}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="">All Employees</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} ({e.employee_code})
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search by name, reason, revised by…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-brand-400"
        />
        <span className="text-xs text-slate-400">{filtered.length} of {revisions.length} records</span>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-slate-600 font-medium">
            {revisions.length === 0
              ? 'No salary revisions recorded yet'
              : 'No matching revisions found'}
          </p>
          {revisions.length === 0 && (
            <p className="text-xs text-slate-400 mt-2">
              Revisions are created automatically when salary master records are updated from the Salary Master page.
            </p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                  {[
                    'Employee', 'Code', 'Dept',
                    'Old CTC', 'New CTC', 'Change',
                    'Gross (New)', 'Net (New)',
                    'Effective From', 'Revised By', 'Revised At', 'Reason', 'Actions'
                  ].map((h) => (
                    <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                    <td className="px-3 py-2.5 font-medium text-slate-800 whitespace-nowrap">{r.employee_name}</td>
                    <td className="px-3 py-2.5 font-mono text-xs text-slate-500">{r.employee_code}</td>
                    <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{r.department}</td>
                    <td className="px-3 py-2.5 font-mono text-slate-500">
                      {r.old_annual_ctc > 0 ? fmtL(r.old_annual_ctc) : '—'}
                    </td>
                    <td className="px-3 py-2.5 font-mono font-semibold text-brand-700">{fmtL(r.new_annual_ctc)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {diffBadge(r.ctc_difference, r.ctc_change_pct)}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-slate-600">{fmt(r.new_gross_monthly)}</td>
                    <td className="px-3 py-2.5 font-mono font-semibold text-emerald-700">{fmt(r.new_net_monthly)}</td>
                    <td className="px-3 py-2.5 font-mono text-slate-700 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs font-medium text-blue-800">
                        {r.effective_from || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{r.revised_by_name}</td>
                    <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap">
                      {r.revised_at
                        ? new Date(r.revised_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
                        : '—'
                      }
                    </td>
                    <td className="px-3 py-2.5 max-w-[180px]">
                      {r.revision_reason ? (
                        <span className="text-xs text-slate-500 block truncate" title={r.revision_reason}>
                          {r.revision_reason}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        onClick={() => openComparison(r.id)}
                        disabled={loadingDetail}
                        className="rounded bg-brand-50 text-brand-700 px-2.5 py-1 text-xs font-medium hover:bg-brand-100 transition disabled:opacity-50 whitespace-nowrap"
                      >
                        Compare
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Audit note */}
      <div className="rounded-xl bg-slate-50 border border-slate-200 px-5 py-4 text-xs text-slate-500 space-y-1">
        <p className="font-semibold text-slate-600">How Effective Dates Work</p>
        <p>
          Each revision has an <strong>Effective From</strong> date. Payroll for any month before that date continues
          to use the previous salary structure. Only payroll runs whose pay period ends <em>on or after</em> the
          effective date will use the new salary.
        </p>
        <p>
          Example: If Palem Mahendra's salary is revised to ₹14.49L effective 01-Jun-2026, then:
          May payroll → old salary ₹11.76L | June payroll → new salary ₹14.49L.
          Closed payrolls are <strong>never</strong> recalculated.
        </p>
      </div>
    </div>
  );
}
