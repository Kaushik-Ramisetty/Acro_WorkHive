import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { billingApi } from '../../services/billing';
import { utilizationApi } from '../../services/utilization';
import { FONT, fmtCurrency, monthStart, today, StatCard } from './_shared';

const MODULES = [
  {
    key: 'billing',
    label: 'Client Billing',
    icon: '💰',
    desc: 'Revenue summaries, project invoicing, billable hours breakdown',
    to: '/finance-dashboard/billing',
    color: '#047857',
    bg: '#ECFDF5',
    border: '#6EE7B7',
  },
  {
    key: 'utilization',
    label: 'Resource Utilization',
    icon: '📊',
    desc: 'Team utilization rates, over/under-allocation analysis',
    to: '/finance-dashboard/utilization',
    color: '#6D28D9',
    bg: '#EDE9FE',
    border: '#C4B5FD',
  },
  {
    key: 'project-costing',
    label: 'Project Costing',
    icon: '🏗',
    desc: 'Cost vs revenue, profit margins, resource cost breakdown',
    to: '/finance-dashboard/project-costing',
    color: '#B91C1C',
    bg: '#FEE2E2',
    border: '#FCA5A5',
  },
  {
    key: 'payroll',
    label: 'Payroll',
    icon: '💳',
    desc: 'Pay cycles, salary structures, statutory filings',
    to: '/finance-dashboard/payroll',
    color: '#1D4ED8',
    bg: '#EFF6FF',
    border: '#93C5FD',
  },
  {
    key: 'reports',
    label: 'Reports & Exports',
    icon: '📋',
    desc: 'Scheduled reports, CSV exports, financial analytics',
    to: '/finance-dashboard/reports',
    color: '#B45309',
    bg: '#FEF3C7',
    border: '#FCD34D',
  },
];

export default function FinanceHome() {
  const navigate = useNavigate();
  const [billing, setBilling] = useState(null);
  const [util, setUtil]       = useState(null);
  const start = monthStart();
  const end   = today();

  useEffect(() => {
    billingApi.summary({ start, end }).then(setBilling).catch(() => {});
    utilizationApi.team({ start, end }).then(setUtil).catch(() => {});
  }, []); // eslint-disable-line

  const currentMonth = new Date().toLocaleString('default', { month: 'long', year: 'numeric' });

  return (
    <div style={{ fontFamily: FONT, maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ marginBottom: 26 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: 'var(--hrms-text)', margin: 0 }}>Finance Dashboard</h2>
        <p style={{ color: 'var(--hrms-text-muted)', fontSize: 13, marginTop: 5 }}>
          {currentMonth} — Financial overview across billing, utilization, and cost
        </p>
      </div>

      {/* KPI Strip */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 30, flexWrap: 'wrap' }}>
        <StatCard
          label="Revenue (MTD)"
          value={billing ? fmtCurrency(billing.total_revenue) : '—'}
          color="#047857" bg="#ECFDF5"
          sub="Approved timesheets"
        />
        <StatCard
          label="Billable Hours"
          value={billing ? billing.total_billable_hours.toFixed(1) + ' h' : '—'}
          color="#1D4ED8" bg="#EFF6FF"
          sub={billing ? `${billing.project_count} project${billing.project_count !== 1 ? 's' : ''}` : undefined}
        />
        <StatCard
          label="Non-Billable"
          value={billing ? billing.total_non_billable_hours.toFixed(1) + ' h' : '—'}
          color="#B45309" bg="#FEF3C7"
        />
        <StatCard
          label="Team Utilization"
          value={util ? util.utilization_pct.toFixed(1) + '%' : '—'}
          color="#6D28D9" bg="#EDE9FE"
          sub="Billable / Available"
        />
        <StatCard
          label="Underutilized"
          value={util ? util.underutilized : '—'}
          color="#B45309" bg="#FEF3C7"
          sub="< 60% utilization"
        />
        <StatCard
          label="Missing TS"
          value={util ? util.missing_submissions : '—'}
          color="#B91C1C" bg="#FEE2E2"
          sub="No submission"
        />
      </div>

      {/* Module Cards */}
      <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--hrms-text)', marginBottom: 14 }}>Modules</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 14, marginBottom: 24 }}>
        {MODULES.map((m) => (
          <button
            key={m.key}
            onClick={() => navigate(m.to)}
            style={{
              padding: '20px 18px', borderRadius: 14, background: m.bg, cursor: 'pointer',
              border: `1px solid ${m.border}`, textAlign: 'left', fontFamily: FONT,
              transition: 'box-shadow 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.10)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
          >
            <div style={{ fontSize: 26, marginBottom: 10 }}>{m.icon}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: m.color, marginBottom: 5 }}>{m.label}</div>
            <div style={{ fontSize: 11, color: 'var(--hrms-text-muted)', lineHeight: 1.5 }}>{m.desc}</div>
          </button>
        ))}
      </div>

      {/* Alert strip */}
      {util && util.missing_submissions > 0 && (
        <div style={{ padding: '12px 16px', background: '#FEF3C7', border: '1px solid #F59E0B',
          borderRadius: 10, fontSize: 12, color: '#92400E', fontWeight: 600, fontFamily: FONT }}>
          ⚠ {util.missing_submissions} employee{util.missing_submissions !== 1 ? 's have' : ' has'} not
          submitted timesheets this month.
          <button onClick={() => navigate('/finance-dashboard/utilization')}
            style={{ marginLeft: 10, fontSize: 11, color: '#92400E', fontWeight: 700,
              background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
            View details
          </button>
        </div>
      )}
    </div>
  );
}
