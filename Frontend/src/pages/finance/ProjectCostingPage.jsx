import { useEffect, useState } from 'react';
import { billingApi } from '../../services/billing';
import {
  FONT, monthStart, today, fmtCurrency,
  StatCard, DateRangeBar, SectionTitle, DataTable, ErrorBanner, EmptyPrompt,
} from './_shared';

export default function ProjectCostingPage() {
  const [start, setStart]     = useState(monthStart);
  const [end, setEnd]         = useState(today);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try { setData(await billingApi.projectCosting({ start, end })); }
    catch (e) { setErr(e?.data?.detail || e.message || 'Failed to load costing data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div style={{ fontFamily: FONT, maxWidth: 1200 }}>
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: 'var(--hrms-text)', margin: 0 }}>Project Costing</h2>
        <p style={{ color: 'var(--hrms-text-muted)', fontSize: 12, marginTop: 4 }}>
          Per-resource cost breakdown with revenue and profit margin analysis.
        </p>
      </div>

      <DateRangeBar start={start} end={end} onStart={setStart} onEnd={setEnd} onRefresh={load} loading={loading} />

      <ErrorBanner message={err} />

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard label="Total Cost"    value={fmtCurrency(data.total_cost)}          color="#B91C1C" bg="#FEE2E2" />
            <StatCard label="Billable Cost" value={fmtCurrency(data.total_billable_cost)} color="#B45309" bg="#FEF3C7" />
            <StatCard label="Revenue"       value={fmtCurrency(data.total_revenue)}       color="#047857" bg="#ECFDF5" />
            <StatCard
              label="Profit Margin"
              value={data.profit_margin_pct.toFixed(1) + '%'}
              color={data.profit_margin_pct >= 0 ? '#047857' : '#B91C1C'}
              bg={data.profit_margin_pct >= 0 ? '#ECFDF5' : '#FEE2E2'}
              sub="(Revenue − Billable Cost) / Revenue"
            />
          </div>

          {/* Revenue vs Cost bar */}
          {data.total_revenue > 0 && (
            <div style={{ marginBottom: 20, padding: '14px 18px', background: 'var(--hrms-surface)',
              border: '1px solid var(--hrms-border)', borderRadius: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--hrms-text-muted)', marginBottom: 10,
                textTransform: 'uppercase', letterSpacing: '0.05em' }}>Revenue vs Cost</div>
              <div style={{ display: 'flex', height: 24, borderRadius: 6, overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${Math.min(data.total_billable_cost / data.total_revenue * 100, 100)}%`,
                    background: '#EF4444', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', minWidth: 30,
                  }}
                  title={`Cost: ${fmtCurrency(data.total_billable_cost)}`}>
                  <span style={{ fontSize: 9, fontWeight: 700, color: '#fff' }}>Cost</span>
                </div>
                <div style={{ flex: 1, background: '#10B981', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', minWidth: 30 }}
                  title={`Profit: ${fmtCurrency(data.total_revenue - data.total_billable_cost)}`}>
                  <span style={{ fontSize: 9, fontWeight: 700, color: '#fff' }}>Profit</span>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
                <span style={{ fontSize: 10, color: '#EF4444', fontWeight: 700 }}>
                  Cost: {fmtCurrency(data.total_billable_cost)}
                </span>
                <span style={{ fontSize: 10, color: '#047857', fontWeight: 700 }}>
                  Revenue: {fmtCurrency(data.total_revenue)}
                </span>
              </div>
            </div>
          )}

          <SectionTitle>Resource Cost Breakdown</SectionTitle>
          <DataTable
            cols={[
              { key: 'employee_name',   label: 'Employee' },
              { key: 'department',      label: 'Dept.',      render: (r) => r.department || '—' },
              { key: 'hourly_cost_rate', label: 'Cost Rate', right: true,
                render: (r) => r.hourly_cost_rate > 0 ? fmtCurrency(r.hourly_cost_rate) + '/h' : 'N/A' },
              { key: 'total_hours',     label: 'Total Hrs',  right: true,
                render: (r) => r.total_hours.toFixed(1) + ' h' },
              { key: 'billable_hours',  label: 'Bill. Hrs',  right: true, color: '#047857',
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'total_cost',      label: 'Total Cost', right: true, bold: true, color: '#B91C1C',
                render: (r) => fmtCurrency(r.total_cost) },
              { key: 'billable_cost',   label: 'Bill. Cost', right: true,
                render: (r) => fmtCurrency(r.billable_cost) },
              { key: 'utilization_pct', label: 'Utilization', right: true,
                render: (r) => {
                  const pct = r.utilization_pct;
                  const col = pct >= 80 ? '#10B981' : pct >= 60 ? '#F59E0B' : '#EF4444';
                  return <span style={{ fontWeight: 700, color: col }}>{pct.toFixed(0)}%</span>;
                },
              },
            ]}
            rows={data.resources}
            emptyMsg="No resource cost data for this period."
          />
        </>
      )}

      {!data && !loading && <EmptyPrompt />}
    </div>
  );
}
