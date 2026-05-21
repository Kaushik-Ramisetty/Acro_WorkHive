/**
 * PMO / Finance — Timesheet Management
 *
 * Three tabs:
 *   1. Billing Dashboard   — project-level revenue breakdown
 *   2. Resource Utilization — per-employee utilization metrics
 *   3. Project Costing     — per-resource cost vs revenue
 */
import { useEffect, useState } from 'react';
import { billingApi, triggerCsvDownload } from '../../../services/billing';
import { utilizationApi } from '../../../services/utilization';

const FONT = "'DM Sans', system-ui, sans-serif";

// ── Date helpers ──────────────────────────────────────────────────────────────
function fmtIso(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
function monthStart() { const d = new Date(); d.setDate(1); return fmtIso(d); }
function today()      { return fmtIso(new Date()); }

function fmtCurrency(n) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);
}

// ── Shared sub-components ─────────────────────────────────────────────────────
function SectionTitle({ children }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--hrms-text)', marginBottom: 14 }}>
      {children}
    </div>
  );
}

function StatCard({ label, value, sub, color = '#1D4ED8', bg = '#EFF6FF' }) {
  return (
    <div style={{ flex: 1, minWidth: 130, padding: '16px 18px', borderRadius: 12,
      background: bg, textAlign: 'center', fontFamily: FONT }}>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--hrms-text-muted)', marginTop: 3, fontWeight: 600 }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--hrms-text-faint)', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function DateRangeBar({ start, end, onStart, onEnd, onRefresh, loading, extra }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 18, flexWrap: 'wrap' }}>
      <div>
        <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)', display: 'block', marginBottom: 4,
          textTransform: 'uppercase', letterSpacing: '0.05em' }}>From</label>
        <input type="date" value={start} onChange={(e) => onStart(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--hrms-border)', borderRadius: 8, fontSize: 12,
            fontFamily: FONT, background: 'var(--hrms-surface)', color: 'var(--hrms-text)' }} />
      </div>
      <div>
        <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)', display: 'block', marginBottom: 4,
          textTransform: 'uppercase', letterSpacing: '0.05em' }}>To</label>
        <input type="date" value={end} onChange={(e) => onEnd(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--hrms-border)', borderRadius: 8, fontSize: 12,
            fontFamily: FONT, background: 'var(--hrms-surface)', color: 'var(--hrms-text)' }} />
      </div>
      {extra}
      <button onClick={onRefresh} disabled={loading}
        style={{ padding: '8px 18px', background: '#0F172A', color: '#fff', border: 'none',
          borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: FONT,
          opacity: loading ? 0.6 : 1 }}>
        {loading ? 'Loading…' : 'Apply'}
      </button>
    </div>
  );
}

function Table({ cols, rows, emptyMsg = 'No data.' }) {
  return (
    <div style={{ border: '1px solid var(--hrms-border)', borderRadius: 10, overflow: 'hidden',
      background: 'var(--hrms-surface)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: FONT }}>
        <thead>
          <tr style={{ background: 'var(--hrms-surface-2)', borderBottom: '1px solid var(--hrms-border)' }}>
            {cols.map((c) => (
              <th key={c.key} style={{
                padding: '10px 14px',
                textAlign: c.right ? 'right' : 'left',
                fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)',
                textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap',
              }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={cols.length} style={{ padding: 28, textAlign: 'center',
                color: 'var(--hrms-text-faint)', fontSize: 13 }}>
                {emptyMsg}
              </td>
            </tr>
          )}
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderTop: '1px solid var(--hrms-border)' }}>
              {cols.map((c) => (
                <td key={c.key} style={{
                  padding: '11px 14px',
                  textAlign: c.right ? 'right' : 'left',
                  fontWeight: c.bold ? 700 : 400,
                  color: c.color || 'var(--hrms-text-2)',
                  whiteSpace: 'nowrap',
                }}>
                  {c.render ? c.render(row) : (row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Tab 1: Billing Dashboard ──────────────────────────────────────────────────
function BillingTab() {
  const [start, setStart]   = useState(monthStart);
  const [end, setEnd]       = useState(today);
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]       = useState('');
  const [exporting, setExporting] = useState(false);

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const d = await billingApi.summary({ start, end });
      setData(d);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load billing data');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  const handleExport = async () => {
    setExporting(true);
    try {
      const csv = await billingApi.exportCsv({ start, end });
      triggerCsvDownload(csv, `billing_${start}_${end}.csv`);
    } catch (e) {
      setErr('Export failed: ' + (e?.data?.detail || e.message));
    } finally { setExporting(false); }
  };

  return (
    <div>
      <DateRangeBar
        start={start} end={end}
        onStart={setStart} onEnd={setEnd}
        onRefresh={load} loading={loading}
        extra={
          <button onClick={handleExport} disabled={exporting}
            style={{ padding: '8px 14px', background: '#10B981', color: '#fff', border: 'none',
              borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: FONT,
              display: 'flex', alignItems: 'center', gap: 6, opacity: exporting ? 0.6 : 1 }}>
            {exporting ? 'Exporting…' : '↓ Export CSV'}
          </button>
        }
      />

      {err && (
        <div style={{ background: '#FEE2E2', color: '#B91C1C', padding: '10px 14px',
          borderRadius: 8, fontSize: 12, marginBottom: 16 }}>{err}</div>
      )}

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard label="Billable Hours"     value={data.total_billable_hours.toFixed(1) + ' h'} color="#047857" bg="#ECFDF5" />
            <StatCard label="Non-Billable Hours" value={data.total_non_billable_hours.toFixed(1) + ' h'} color="#B45309" bg="#FEF3C7" />
            <StatCard label="Total Revenue"      value={fmtCurrency(data.total_revenue)} color="#1D4ED8" bg="#EFF6FF"
              sub={`${data.project_count} project${data.project_count !== 1 ? 's' : ''}`} />
          </div>

          <SectionTitle>Project Billing Breakdown</SectionTitle>
          <Table
            cols={[
              { key: 'project_name',     label: 'Project'       },
              { key: 'client_name',      label: 'Client'        },
              { key: 'is_billable',      label: 'Billable',     render: (r) => r.is_billable ? '✓ Yes' : 'No' },
              { key: 'billing_rate',     label: 'Rate/hr',      right: true,
                render: (r) => r.billing_rate != null ? fmtCurrency(r.billing_rate) : '—' },
              { key: 'billable_hours',   label: 'Bill. Hrs',    right: true, bold: true,
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'non_billable_hours', label: 'Non-Bill.',  right: true,
                render: (r) => r.non_billable_hours.toFixed(1) + ' h' },
              { key: 'headcount',        label: 'Headcount',    right: true },
              { key: 'revenue',          label: 'Revenue',      right: true, bold: true, color: '#047857',
                render: (r) => fmtCurrency(r.revenue) },
            ]}
            rows={data.projects}
            emptyMsg="No billing data for this period."
          />
        </>
      )}

      {!data && !loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--hrms-text-faint)', fontSize: 13 }}>
          Click Apply to load billing data.
        </div>
      )}
    </div>
  );
}

// ── Tab 2: Resource Utilization ───────────────────────────────────────────────
function UtilizationTab() {
  const [start, setStart]   = useState(monthStart);
  const [end, setEnd]       = useState(today);
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]       = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const d = await utilizationApi.team({ start, end });
      setData(d);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load utilization data');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div>
      <DateRangeBar start={start} end={end} onStart={setStart} onEnd={setEnd} onRefresh={load} loading={loading} />

      {err && (
        <div style={{ background: '#FEE2E2', color: '#B91C1C', padding: '10px 14px',
          borderRadius: 8, fontSize: 12, marginBottom: 16 }}>{err}</div>
      )}

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard label="Employees"      value={data.total_employees}                      color="#1D4ED8" bg="#EFF6FF" />
            <StatCard label="Billable Hours" value={data.billable_hours.toFixed(1) + ' h'}    color="#047857" bg="#ECFDF5" />
            <StatCard label="Non-Billable"   value={data.non_billable_hours.toFixed(1) + ' h'} color="#B45309" bg="#FEF3C7" />
            <StatCard label="Avg Utilization" value={data.utilization_pct.toFixed(1) + '%'}  color="#6D28D9" bg="#EDE9FE"
              sub="Billable / Available" />
            <StatCard label="Underutilized"  value={data.underutilized}                        color="#B45309" bg="#FEF3C7"
              sub="< 60%" />
            <StatCard label="Overallocated"  value={data.overallocated}                        color="#B91C1C" bg="#FEE2E2"
              sub="> 100%" />
            <StatCard label="Missing TS"     value={data.missing_submissions}                  color="#9CA3AF" bg="#F1F5F9"
              sub="No submission" />
          </div>

          <SectionTitle>Employee Utilization Breakdown</SectionTitle>
          <Table
            cols={[
              { key: 'employee_name', label: 'Employee' },
              { key: 'department',    label: 'Department', render: (r) => r.department || '—' },
              { key: 'designation',   label: 'Designation', render: (r) => r.designation || '—' },
              { key: 'available_hours', label: 'Available', right: true,
                render: (r) => r.available_hours.toFixed(0) + ' h' },
              { key: 'billable_hours', label: 'Billable', right: true, bold: true, color: '#047857',
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'non_billable_hours', label: 'Non-Bill.', right: true,
                render: (r) => r.non_billable_hours.toFixed(1) + ' h' },
              { key: 'overtime_hours', label: 'Overtime', right: true, color: '#B45309',
                render: (r) => r.overtime_hours > 0 ? '+' + r.overtime_hours.toFixed(1) + ' h' : '—' },
              { key: 'utilization_pct', label: 'Utilization %', right: false,
                render: (r) => {
                  const pct = r.utilization_pct;
                  const col = pct >= 80 ? '#10B981' : pct >= 60 ? '#F59E0B' : '#EF4444';
                  return (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
                      <div style={{ flex: 1, height: 6, background: 'var(--hrms-border)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`,
                          background: col, borderRadius: 3 }} />
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 700, color: col, minWidth: 36 }}>
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  );
                },
              },
              { key: 'missing_timesheet', label: 'TS Status',
                render: (r) => r.missing_timesheet
                  ? <span style={{ fontSize: 10, fontWeight: 700, background: '#FEE2E2', color: '#B91C1C',
                      padding: '2px 7px', borderRadius: 4 }}>Missing</span>
                  : <span style={{ fontSize: 10, fontWeight: 700, background: '#ECFDF5', color: '#047857',
                      padding: '2px 7px', borderRadius: 4 }}>Submitted</span>,
              },
            ]}
            rows={data.employees}
            emptyMsg="No employees found for this period."
          />
        </>
      )}

      {!data && !loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--hrms-text-faint)', fontSize: 13 }}>
          Click Apply to load utilization data.
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Project Costing ────────────────────────────────────────────────────
function ProjectCostingTab() {
  const [start, setStart]   = useState(monthStart);
  const [end, setEnd]       = useState(today);
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]       = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const d = await billingApi.projectCosting({ start, end });
      setData(d);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to load costing data');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div>
      <DateRangeBar start={start} end={end} onStart={setStart} onEnd={setEnd} onRefresh={load} loading={loading} />

      {err && (
        <div style={{ background: '#FEE2E2', color: '#B91C1C', padding: '10px 14px',
          borderRadius: 8, fontSize: 12, marginBottom: 16 }}>{err}</div>
      )}

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

          {data.total_revenue > 0 && (
            <div style={{ marginBottom: 20, padding: '14px 18px', background: 'var(--hrms-surface)',
              border: '1px solid var(--hrms-border)', borderRadius: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--hrms-text-muted)', marginBottom: 10,
                textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Revenue vs Cost
              </div>
              <div style={{ display: 'flex', gap: 0, height: 24, borderRadius: 6, overflow: 'hidden' }}>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
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
          <Table
            cols={[
              { key: 'employee_name', label: 'Employee' },
              { key: 'department',    label: 'Dept.',   render: (r) => r.department || '—' },
              { key: 'hourly_cost_rate', label: 'Cost Rate', right: true,
                render: (r) => r.hourly_cost_rate > 0 ? fmtCurrency(r.hourly_cost_rate) + '/h' : 'N/A' },
              { key: 'total_hours',   label: 'Total Hrs', right: true,
                render: (r) => r.total_hours.toFixed(1) + ' h' },
              { key: 'billable_hours', label: 'Bill. Hrs', right: true, color: '#047857',
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'total_cost',    label: 'Total Cost', right: true, bold: true, color: '#B91C1C',
                render: (r) => fmtCurrency(r.total_cost) },
              { key: 'billable_cost', label: 'Bill. Cost', right: true,
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

      {!data && !loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--hrms-text-faint)', fontSize: 13 }}>
          Click Apply to load project costing data.
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
const TABS = [
  { key: 'billing',     label: '💰 Billing Dashboard'    },
  { key: 'utilization', label: '📊 Resource Utilization'  },
  { key: 'costing',     label: '🏗 Project Costing'       },
];

export default function TimesheetManagementPage() {
  const [tab, setTab] = useState('billing');

  return (
    <div style={{ fontFamily: FONT, maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: 'var(--hrms-text)', margin: 0 }}>
          PMO / Finance — Timesheet Management
        </h2>
        <p style={{ color: 'var(--hrms-text-muted)', fontSize: 12, marginTop: 4 }}>
          Billing summaries, resource utilization, and project costing for approved timesheets.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24,
        borderBottom: '2px solid var(--hrms-border)', paddingBottom: 0 }}>
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            style={{
              padding: '9px 18px', border: 'none', cursor: 'pointer', fontFamily: FONT,
              fontSize: 13, fontWeight: tab === t.key ? 700 : 500,
              color: tab === t.key ? '#1D4ED8' : 'var(--hrms-text-muted)',
              background: 'transparent',
              borderBottom: tab === t.key ? '3px solid #1D4ED8' : '3px solid transparent',
              marginBottom: -2, borderRadius: 0,
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'billing'     && <BillingTab />}
      {tab === 'utilization' && <UtilizationTab />}
      {tab === 'costing'     && <ProjectCostingTab />}
    </div>
  );
}
