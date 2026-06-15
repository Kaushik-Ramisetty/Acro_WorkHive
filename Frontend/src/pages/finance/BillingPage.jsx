import { useEffect, useState } from 'react';
import { billingApi, triggerCsvDownload } from '../../services/billing';
import {
  FONT, monthStart, today, fmtCurrency,
  StatCard, DateRangeBar, SectionTitle, DataTable, ErrorBanner, EmptyPrompt,
} from './_shared';

export default function BillingPage() {
  const [start, setStart]         = useState(monthStart);
  const [end, setEnd]             = useState(today);
  const [data, setData]           = useState(null);
  const [loading, setLoading]     = useState(false);
  const [exporting, setExporting] = useState(false);
  const [err, setErr]             = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try { setData(await billingApi.summary({ start, end })); }
    catch (e) { setErr(e?.data?.detail || e.message || 'Failed to load billing data'); }
    finally { setLoading(false); }
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
    <div style={{ fontFamily: FONT, maxWidth: 1200 }}>
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: 'var(--hrms-text)', margin: 0 }}>Client Billing</h2>
        <p style={{ color: 'var(--hrms-text-muted)', fontSize: 12, marginTop: 4 }}>
          Revenue and billable hours from approved timesheets, grouped by project.
        </p>
      </div>

      <DateRangeBar
        start={start} end={end}
        onStart={setStart} onEnd={setEnd}
        onRefresh={load} loading={loading}
        extra={
          <button onClick={handleExport} disabled={exporting}
            style={{ padding: '8px 14px', background: '#10B981', color: '#fff', border: 'none',
              borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: FONT,
              opacity: exporting ? 0.6 : 1 }}>
            {exporting ? 'Exporting…' : '↓ Export CSV'}
          </button>
        }
      />

      <ErrorBanner message={err} />

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard label="Billable Hours"     value={data.total_billable_hours.toFixed(1) + ' h'}     color="#047857" bg="#ECFDF5" />
            <StatCard label="Non-Billable Hours" value={data.total_non_billable_hours.toFixed(1) + ' h'} color="#B45309" bg="#FEF3C7" />
            <StatCard label="Total Revenue"      value={fmtCurrency(data.total_revenue)}                 color="#1D4ED8" bg="#EFF6FF"
              sub={`${data.project_count} project${data.project_count !== 1 ? 's' : ''}`} />
          </div>

          <SectionTitle>Project Billing Breakdown</SectionTitle>
          <DataTable
            cols={[
              { key: 'project_name',       label: 'Project' },
              { key: 'client_name',        label: 'Client' },
              { key: 'is_billable',        label: 'Billable', render: (r) => r.is_billable ? '✓ Yes' : 'No' },
              { key: 'billing_rate',       label: 'Rate / hr', right: true,
                render: (r) => r.billing_rate != null ? fmtCurrency(r.billing_rate) : '—' },
              { key: 'billable_hours',     label: 'Bill. Hrs', right: true, bold: true,
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'non_billable_hours', label: 'Non-Bill.',  right: true,
                render: (r) => r.non_billable_hours.toFixed(1) + ' h' },
              { key: 'headcount',          label: 'Headcount',  right: true },
              { key: 'revenue',            label: 'Revenue',    right: true, bold: true, color: '#047857',
                render: (r) => fmtCurrency(r.revenue) },
            ]}
            rows={data.projects}
            emptyMsg="No billing data for this period."
          />
        </>
      )}

      {!data && !loading && <EmptyPrompt />}
    </div>
  );
}
