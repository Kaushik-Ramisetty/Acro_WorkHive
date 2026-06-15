/**
 * Payroll Analytics
 *
 * Shows cross-run trend analytics, department cost breakdown, and salary
 * distribution. Uses plain SVG/CSS bar charts to avoid adding Recharts
 * as a new dependency to the existing HRMS project.
 * (If Recharts is already installed, components can be swapped in easily.)
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

function fmt(n) {
  if (!n) return '₹0';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(2)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

// Simple CSS bar chart
function BarChart({ data, valueKey, labelKey, colorClass = 'bg-brand-500', height = 140 }) {
  if (!data?.length) return <div className="text-center text-slate-400 text-sm py-6">No data</div>;
  const max = Math.max(...data.map((d) => d[valueKey]));
  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {data.map((item, i) => {
        const pct = max > 0 ? (item[valueKey] / max) * 100 : 0;
        return (
          <div key={i} className="flex flex-col items-center gap-1 flex-1 min-w-0">
            <span className="text-[9px] text-slate-500 font-mono truncate w-full text-center">
              {fmt(item[valueKey])}
            </span>
            <div
              className={`w-full rounded-t-md transition-all ${colorClass}`}
              style={{ height: `${Math.max(pct * (height - 30) / 100, 4)}px` }}
              title={`${item[labelKey]}: ${fmt(item[valueKey])}`}
            />
            <span className="text-[9px] text-slate-400 truncate w-full text-center">{item[labelKey]}</span>
          </div>
        );
      })}
    </div>
  );
}

// Horizontal bar
function HBar({ label, value, max, color = '#2541d6' }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-600 font-medium">{label}</span>
        <span className="font-mono text-slate-700">{fmt(value)}</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function PayrollAnalytics() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    financeApi.listRuns({ limit: 12 })
      .then((data) => setRuns(data.filter((r) => r.status !== 'draft' && r.total_gross > 0)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
    </div>
  );

  // Trend data (chronological)
  const trendData = [...runs]
    .sort((a, b) => new Date(a.pay_period_start) - new Date(b.pay_period_start))
    .slice(-6)
    .map((r) => ({
      label: r.month_label?.slice(0, 3),
      gross: r.total_gross,
      net:   r.total_net,
      deductions: r.total_deductions,
    }));

  // Deduction breakdown (from most recent run)
  const latest = trendData[trendData.length - 1];
  const latestRun = runs.find((r) => r.month_label?.slice(0, 3) === latest?.label);
  const deductionBreakdown = latestRun ? [
    { label: 'PF', value: latestRun.total_pf },
    { label: 'ESI', value: latestRun.total_esi },
    { label: 'TDS', value: latestRun.total_tds },
    { label: 'PT', value: latestRun.total_pt },
  ] : [];
  const maxDeduction = Math.max(...deductionBreakdown.map((d) => d.value), 1);

  // Stats from most recent run
  const mostRecent = runs[runs.length - 1];
  const avgNet = mostRecent?.total_net && mostRecent.total_employees
    ? mostRecent.total_net / mostRecent.total_employees
    : 0;

  // Month-over-month growth
  const mom = runs.length >= 2
    ? ((runs[runs.length - 1].total_net - runs[runs.length - 2].total_net) / runs[runs.length - 2].total_net * 100).toFixed(1)
    : null;

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

      <div>
        <h1 className="text-xl font-bold text-slate-800">Payroll Analytics</h1>
        <p className="text-sm text-slate-500 mt-0.5">Trends, breakdowns, and cost analysis across payroll runs</p>
      </div>

      {runs.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">📈</p>
          <p className="text-slate-600 font-medium">No processed payroll runs yet</p>
          <p className="text-slate-400 text-sm mt-1">Analytics will appear once payroll runs are generated</p>
        </div>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Runs',     value: runs.length,         sub: 'Processed', color: 'bg-brand-50 text-brand-700' },
              { label: 'Latest Net Pay', value: fmt(mostRecent?.total_net), sub: mostRecent?.month_label, color: 'bg-emerald-50 text-emerald-700' },
              { label: 'Avg. Net / Emp', value: fmt(avgNet),         sub: 'Per employee', color: 'bg-blue-50 text-blue-700' },
              {
                label: 'MoM Growth',
                value: mom !== null ? `${mom > 0 ? '+' : ''}${mom}%` : '—',
                sub: 'Net payroll change',
                color: mom > 0 ? 'bg-emerald-50 text-emerald-700' : mom < 0 ? 'bg-rose-50 text-rose-700' : 'bg-slate-50 text-slate-700',
              },
            ].map((card) => (
              <div key={card.label} className="bg-white rounded-xl border border-slate-200 p-4 shadow-soft">
                <p className="text-xs text-slate-500 mb-1">{card.label}</p>
                <p className={`text-xl font-bold font-mono rounded px-1 ${card.color}`}>{card.value}</p>
                <p className="text-xs text-slate-400 mt-1">{card.sub}</p>
              </div>
            ))}
          </div>

          {/* Monthly trend charts */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
                Monthly Gross Payroll Trend
              </p>
              <BarChart data={trendData} valueKey="gross" labelKey="label" colorClass="bg-brand-500" height={150} />
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
                Monthly Net Payroll Trend
              </p>
              <BarChart data={trendData} valueKey="net" labelKey="label" colorClass="bg-emerald-500" height={150} />
            </div>
          </div>

          {/* Deduction breakdown */}
          {deductionBreakdown.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
                Deduction Breakdown — {latestRun?.month_label}
              </p>
              <div className="space-y-4">
                {[
                  { label: 'Provident Fund (PF)', value: latestRun.total_pf,  color: '#4F46E5' },
                  { label: 'ESI',                 value: latestRun.total_esi, color: '#7C3AED' },
                  { label: 'TDS',                 value: latestRun.total_tds, color: '#DC2626' },
                  { label: 'Professional Tax',    value: latestRun.total_pt,  color: '#D97706' },
                ].map((d) => (
                  <HBar key={d.label} label={d.label} value={d.value} max={maxDeduction} color={d.color} />
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-100 flex justify-between text-sm">
                <span className="text-slate-600 font-medium">Total Deductions</span>
                <span className="font-mono font-bold text-rose-600">{fmt(latestRun?.total_deductions)}</span>
              </div>
            </div>
          )}

          {/* Payroll history table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
            <div className="px-5 py-4 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Payroll Run History</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                    {['Period', 'Employees', 'Gross', 'Deductions', 'Net Pay', 'PF', 'TDS', 'Status'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...runs].reverse().map((r) => (
                    <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-700">{r.month_label}</p>
                        <p className="text-xs text-slate-400">{r.pay_period_start}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{r.total_employees}</td>
                      <td className="px-4 py-3 font-mono text-slate-700">{fmt(r.total_gross)}</td>
                      <td className="px-4 py-3 font-mono text-rose-600">{fmt(r.total_deductions)}</td>
                      <td className="px-4 py-3 font-mono font-semibold text-emerald-700">{fmt(r.total_net)}</td>
                      <td className="px-4 py-3 font-mono text-indigo-700">{fmt(r.total_pf)}</td>
                      <td className="px-4 py-3 font-mono text-rose-600">{fmt(r.total_tds)}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
                          r.status === 'disbursed' ? 'bg-teal-100 text-teal-700'
                          : r.status === 'approved' ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-slate-100 text-slate-600'
                        }`}>
                          {r.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
