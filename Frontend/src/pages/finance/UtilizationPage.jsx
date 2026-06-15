import { useEffect, useState } from 'react';
import { utilizationApi } from '../../services/utilization';
import {
  FONT, monthStart, today,
  StatCard, DateRangeBar, SectionTitle, DataTable, ErrorBanner, EmptyPrompt,
} from './_shared';

export default function UtilizationPage() {
  const [start, setStart]     = useState(monthStart);
  const [end, setEnd]         = useState(today);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try { setData(await utilizationApi.team({ start, end })); }
    catch (e) { setErr(e?.data?.detail || e.message || 'Failed to load utilization data'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div style={{ fontFamily: FONT, maxWidth: 1200 }}>
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: 'var(--hrms-text)', margin: 0 }}>Resource Utilization</h2>
        <p style={{ color: 'var(--hrms-text-muted)', fontSize: 12, marginTop: 4 }}>
          Team-wide utilization metrics — billable vs available hours per employee.
        </p>
      </div>

      <DateRangeBar start={start} end={end} onStart={setStart} onEnd={setEnd} onRefresh={load} loading={loading} />

      <ErrorBanner message={err} />

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard label="Employees"       value={data.total_employees}                              color="#1D4ED8" bg="#EFF6FF" />
            <StatCard label="Billable Hours"  value={data.billable_hours.toFixed(1) + ' h'}            color="#047857" bg="#ECFDF5" />
            <StatCard label="Non-Billable"    value={data.non_billable_hours.toFixed(1) + ' h'}        color="#B45309" bg="#FEF3C7" />
            <StatCard label="Avg Utilization" value={data.utilization_pct.toFixed(1) + '%'}            color="#6D28D9" bg="#EDE9FE"
              sub="Billable / Available" />
            <StatCard label="Underutilized"   value={data.underutilized}                               color="#B45309" bg="#FEF3C7"
              sub="< 60%" />
            <StatCard label="Overallocated"   value={data.overallocated}                               color="#B91C1C" bg="#FEE2E2"
              sub="> 100%" />
            <StatCard label="Missing TS"      value={data.missing_submissions}                         color="#9CA3AF" bg="#F1F5F9"
              sub="No submission" />
          </div>

          <SectionTitle>Employee Utilization Breakdown</SectionTitle>
          <DataTable
            cols={[
              { key: 'employee_name',      label: 'Employee' },
              { key: 'department',         label: 'Department',  render: (r) => r.department  || '—' },
              { key: 'designation',        label: 'Designation', render: (r) => r.designation || '—' },
              { key: 'available_hours',    label: 'Available',   right: true,
                render: (r) => r.available_hours.toFixed(0) + ' h' },
              { key: 'billable_hours',     label: 'Billable',    right: true, bold: true, color: '#047857',
                render: (r) => r.billable_hours.toFixed(1) + ' h' },
              { key: 'non_billable_hours', label: 'Non-Bill.',   right: true,
                render: (r) => r.non_billable_hours.toFixed(1) + ' h' },
              { key: 'overtime_hours',     label: 'Overtime',    right: true, color: '#B45309',
                render: (r) => r.overtime_hours > 0 ? '+' + r.overtime_hours.toFixed(1) + ' h' : '—' },
              {
                key: 'utilization_pct', label: 'Utilization %',
                render: (r) => {
                  const pct = r.utilization_pct;
                  const col = pct >= 80 ? '#10B981' : pct >= 60 ? '#F59E0B' : '#EF4444';
                  return (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
                      <div style={{ flex: 1, height: 6, background: 'var(--hrms-border)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, background: col, borderRadius: 3 }} />
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 700, color: col, minWidth: 36 }}>
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  );
                },
              },
              {
                key: 'missing_timesheet', label: 'TS Status',
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

      {!data && !loading && <EmptyPrompt />}
    </div>
  );
}
