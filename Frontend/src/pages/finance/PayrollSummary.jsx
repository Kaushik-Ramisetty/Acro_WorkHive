import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

function tdsNote(employee) {
  if (employee.tds > 0) return null;
  const annualGross = (employee.gross_earnings || 0) * 12;
  if (annualGross <= 0) return null;
  // Old regime threshold ₹2,50,000; New regime ₹3,00,000
  const threshold = 250000;
  if (annualGross < threshold) {
    return `Annual gross ₹${Math.round(annualGross).toLocaleString('en-IN')} is below ₹2,50,000 exemption — TDS not applicable`;
  }
  return 'TDS ₹0 — no declaration submitted; submit Form 12BB to Finance';
}

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(2)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function SummaryCard({ label, value, sub, color = 'brand' }) {
  const palette = {
    brand:   'border-l-brand-500 bg-brand-50 text-brand-700',
    emerald: 'border-l-emerald-500 bg-emerald-50 text-emerald-700',
    rose:    'border-l-rose-500 bg-rose-50 text-rose-700',
    amber:   'border-l-amber-500 bg-amber-50 text-amber-700',
    indigo:  'border-l-indigo-500 bg-indigo-50 text-indigo-700',
    purple:  'border-l-purple-500 bg-purple-50 text-purple-700',
  }[color];
  return (
    <div className={`rounded-xl border-l-4 p-4 ${palette}`}>
      <p className="text-xs font-medium opacity-70 mb-1">{label}</p>
      <p className="text-xl font-bold font-mono">{value}</p>
      {sub && <p className="text-xs opacity-60 mt-0.5">{sub}</p>}
    </div>
  );
}

function RunSelector({ runs, selectedId, onChange }) {
  return (
    <select
      value={selectedId || ''}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
    >
      <option value="" disabled>Select payroll run…</option>
      {runs.map((r) => (
        <option key={r.id} value={r.id}>{r.month_label} — {r.status}</option>
      ))}
    </select>
  );
}

export default function PayrollSummary() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [run, setRun] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    financeApi.listRuns()
      .then((data) => {
        setRuns(data);
        if (data.length > 0) setSelectedRunId(data[0].id);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    setLoadingDetails(true);
    Promise.all([
      financeApi.getRun(selectedRunId),
      financeApi.getRunEmployees(selectedRunId),
    ])
      .then(([r, emps]) => { setRun(r); setEmployees(emps); })
      .finally(() => setLoadingDetails(false));
  }, [selectedRunId]);

  const filtered = employees.filter((e) =>
    !search || e.employee_name?.toLowerCase().includes(search.toLowerCase())
      || e.department?.toLowerCase().includes(search.toLowerCase())
  );

  // Department aggregation
  const deptMap = {};
  employees.forEach((e) => {
    const dept = e.department || 'Unknown';
    if (!deptMap[dept]) deptMap[dept] = { headcount: 0, gross: 0, deductions: 0, net: 0, pf: 0, tds: 0 };
    deptMap[dept].headcount++;
    deptMap[dept].gross += e.gross_earnings;
    deptMap[dept].deductions += e.total_deductions;
    deptMap[dept].net += e.net_pay;
    deptMap[dept].pf += e.employee_pf;
    deptMap[dept].tds += e.tds;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
        <p className="text-4xl mb-3">📄</p>
        <p className="text-slate-600 font-medium">No payroll runs found</p>
        <p className="text-slate-400 text-sm mt-1">Create a payroll run first from the Payroll Runs section</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Payroll Summary</h1>
          <p className="text-sm text-slate-500 mt-0.5">Full salary breakdown by run, department, and employee</p>
        </div>
        <RunSelector runs={runs} selectedId={selectedRunId} onChange={setSelectedRunId} />
      </div>

      {loadingDetails ? (
        <div className="flex items-center justify-center h-32">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : run ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SummaryCard label="Total Gross Salary" value={fmt(run.total_gross)} sub={`${run.total_employees} employees`} color="brand" />
            <SummaryCard label="Total Net Salary"   value={fmt(run.total_net)}   sub="After all deductions"          color="emerald" />
            <SummaryCard label="Total Deductions"   value={fmt(run.total_deductions)} sub="PF + ESI + PT + TDS"       color="rose" />
            <SummaryCard label="Total Employees"    value={run.total_employees}  sub={run.month_label}               color="amber" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SummaryCard label="PF (Total)"  value={fmt(run.total_pf)}  color="indigo" />
            <SummaryCard label="ESI (Total)" value={fmt(run.total_esi)} color="purple" />
            <SummaryCard label="TDS (Total)" value={fmt(run.total_tds)} color="rose" />
            <SummaryCard label="PT (Total)"  value={fmt(run.total_pt)}  color="amber" />
          </div>

          {/* TDS information banner */}
          {run.total_tds === 0 && employees.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm">
              <p className="font-semibold text-amber-800">TDS is ₹0 for this payroll run</p>
              <p className="text-amber-700 mt-1">
                This is correct if all employees' annual gross salary is below ₹2,50,000 (Old Regime) or ₹3,00,000 (New Regime).
                Current employees have annual gross between ₹{Math.round(Math.min(...employees.map(e => e.gross_earnings * 12))).toLocaleString('en-IN')} –
                ₹{Math.round(Math.max(...employees.map(e => e.gross_earnings * 12))).toLocaleString('en-IN')}.
                To enable TDS, go to <strong>Salary Structures → Tax Declarations</strong> and submit employee tax declarations.
              </p>
            </div>
          )}

          {/* Department breakdown */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
            <div className="px-5 py-4 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Department-wise Summary</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                    {['Department', 'Headcount', 'Gross', 'Deductions', 'Net Pay', 'PF', 'TDS'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left font-semibold tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(deptMap).map(([dept, d]) => (
                    <tr key={dept} className="border-b border-slate-100 hover:bg-slate-50 transition">
                      <td className="px-4 py-3 font-medium text-slate-700">{dept}</td>
                      <td className="px-4 py-3 text-slate-500">{d.headcount}</td>
                      <td className="px-4 py-3 font-mono text-slate-700">{fmt(d.gross)}</td>
                      <td className="px-4 py-3 font-mono text-rose-600">{fmt(d.deductions)}</td>
                      <td className="px-4 py-3 font-mono font-semibold text-emerald-700">{fmt(d.net)}</td>
                      <td className="px-4 py-3 font-mono text-indigo-700">{fmt(d.pf)}</td>
                      <td className="px-4 py-3 font-mono text-rose-600">{fmt(d.tds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Employee table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Employee Payroll Table</p>
              <input
                type="text"
                placeholder="Search employee or department…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-brand-400"
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 uppercase">
                    {['Employee', 'Department', 'Designation', 'Days', 'LOP', 'Gross', 'PF', 'TDS', 'PT', 'Deductions', 'Net Pay', 'Status'].map((h) => (
                      <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="text-center py-8 text-slate-400">No employees found</td>
                    </tr>
                  ) : (
                    filtered.map((e) => (
                      <tr key={e.id} className={`border-b border-slate-50 hover:bg-slate-50 transition ${e.has_error ? 'bg-rose-50/30' : ''}`}>
                        <td className="px-3 py-2.5 font-medium text-slate-700 whitespace-nowrap">{e.employee_name}</td>
                        <td className="px-3 py-2.5 text-slate-500 whitespace-nowrap">{e.department}</td>
                        <td className="px-3 py-2.5 text-slate-500 whitespace-nowrap max-w-[120px] truncate">{e.designation}</td>
                        <td className="px-3 py-2.5 text-slate-500">{e.present_days}/{e.working_days}</td>
                        <td className="px-3 py-2.5 text-rose-600">{e.lop_days}</td>
                        <td className="px-3 py-2.5 font-mono text-slate-700">{fmt(e.gross_earnings)}</td>
                        <td className="px-3 py-2.5 font-mono text-indigo-700">{fmt(e.employee_pf)}</td>
                        <td className="px-3 py-2.5 font-mono text-rose-600">
                          <span title={tdsNote(e) || undefined}>{fmt(e.tds)}</span>
                          {e.tds === 0 && e.gross_earnings > 0 && (
                            <span className="block text-[10px] text-slate-400 font-normal mt-0.5 max-w-[120px] leading-tight" title={tdsNote(e)}>
                              {(e.gross_earnings * 12) < 250000 ? 'Below limit' : 'No declaration'}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-amber-700">{fmt(e.professional_tax)}</td>
                        <td className="px-3 py-2.5 font-mono text-rose-600">{fmt(e.total_deductions)}</td>
                        <td className="px-3 py-2.5 font-mono font-semibold text-emerald-700">{fmt(e.net_pay)}</td>
                        <td className="px-3 py-2.5">
                          {e.has_error ? (
                            <span className="rounded-full bg-rose-100 text-rose-700 px-2 py-0.5 text-[10px] font-semibold">Error</span>
                          ) : e.payslip_generated ? (
                            <span className="rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 text-[10px] font-semibold">Payslip ✓</span>
                          ) : (
                            <span className="rounded-full bg-slate-100 text-slate-500 px-2 py-0.5 text-[10px] font-semibold">Pending</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-5 py-3 border-t border-slate-100 text-xs text-slate-400">
              Showing {filtered.length} of {employees.length} employees
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
