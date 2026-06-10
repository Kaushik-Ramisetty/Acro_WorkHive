/**
 * Finance Head Payroll — Home / Dashboard Page
 *
 * Entry page for finance_head users at:
 *   /employee-dashboard/finance-head-payroll
 *
 * Shows:
 *   - Pending-approval alert (when a run is pending_head_approval)
 *   - Payroll workflow progress stepper
 *   - Current-run KPI cards (employees, gross, net, errors)
 *   - Action cards:  Final Approval · Summary · Payslips & Bank · Analytics
 *   - Recent payroll runs table
 *   - Empty state when no runs exist
 *
 * Does NOT rebuild any calculation logic — it only reuses financeApi
 * data already consumed by FinanceHome / FinalApproval.
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import financeApi from '../../services/financeApi';

// ── Base route ────────────────────────────────────────────────────────────────
const BASE = '/employee-dashboard/finance-head-payroll';

// ── Shared workflow steps (identical to FinanceHome) ─────────────────────────
const WORKFLOW_STEPS = [
  { key: 'draft',                 label: 'Initiated',             short: 'Init' },
  { key: 'attendance_frozen',     label: 'Attendance Frozen',      short: 'Frozen' },
  { key: 'processing',            label: 'Generated',              short: 'Generated' },
  { key: 'under_review',          label: 'Finance Review',         short: 'Review' },
  { key: 'error_found',           label: 'Error Found',            short: 'Error' },
  { key: 'pending_head_approval', label: 'Finance Head Approval',  short: 'Head Appr.' },
  { key: 'approved',              label: 'Final Approved — Ready', short: 'Approved' },
  { key: 'payslip_generated',     label: 'Payslips Generated',     short: 'Payslips' },
  { key: 'published',             label: 'Published to ESS',       short: 'Published' },
  { key: 'closed',                label: 'Closed',                 short: 'Closed' },
];

const STATUS_ORDER = WORKFLOW_STEPS.map((s) => s.key);

function statusIndex(status) {
  const i = STATUS_ORDER.indexOf(status);
  return i === -1 ? 0 : i;
}

function fmt(n) {
  if (!n) return '₹0';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(2)}Cr`;
  if (n >= 100_000)    return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

// ── Workflow progress stepper (same visual as FinanceHome) ───────────────────
function WorkflowProgress({ status }) {
  const current = statusIndex(status);
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
        Payroll Workflow Progress
      </p>
      <div className="flex items-center gap-0 overflow-x-auto pb-1">
        {WORKFLOW_STEPS.map((step, idx) => {
          const done   = idx < current;
          const active = idx === current;
          return (
            <div key={step.key} className="flex items-center min-w-0">
              <div className="flex flex-col items-center gap-1 px-1">
                <div
                  className={`h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                    done
                      ? 'bg-emerald-500 border-emerald-500 text-white'
                      : active
                      ? 'bg-brand-500 border-brand-500 text-white ring-4 ring-brand-500/20'
                      : 'bg-white border-slate-300 text-slate-400'
                  }`}
                >
                  {done ? '✓' : idx + 1}
                </div>
                <span
                  className={`text-[10px] font-medium whitespace-nowrap ${
                    active ? 'text-brand-600' : done ? 'text-emerald-600' : 'text-slate-400'
                  }`}
                >
                  {step.short}
                </span>
              </div>
              {idx < WORKFLOW_STEPS.length - 1 && (
                <div
                  className={`h-0.5 w-8 flex-shrink-0 mx-0.5 ${
                    idx < current ? 'bg-emerald-400' : 'bg-slate-200'
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Action cards definition ───────────────────────────────────────────────────
const ACTION_CARDS = [
  {
    id:        'final-approval',
    title:     'Final Approval',
    desc:      'Review, approve or return the payroll run before disbursement',
    icon:      '✅',
    gradient:  'from-emerald-50 to-emerald-100/60',
    border:    'border-emerald-200',
    iconBg:    'bg-emerald-100 text-emerald-700',
    titleClr:  'text-emerald-800',
    isPrimary: true,
  },
  {
    id:       'salary-revision',
    title:    'Salary Revision',
    desc:     'Final approve or reject salary revision requests recommended by Finance',
    icon:     '✏️',
    gradient: 'from-amber-50 to-amber-100/60',
    border:   'border-amber-200',
    iconBg:   'bg-amber-100 text-amber-700',
    titleClr: 'text-amber-800',
  },
  {
    id:       'bonus-requests',
    title:    'Bonus Requests',
    desc:     'Final approve or reject one-time bonus requests recommended by Finance',
    icon:     '🎁',
    gradient: 'from-violet-50 to-violet-100/60',
    border:   'border-violet-200',
    iconBg:   'bg-violet-100 text-violet-700',
    titleClr: 'text-violet-800',
  },
  {
    id:       'off-cycle-payments',
    title:    'Off-Cycle Payments',
    desc:     'Review off-cycle bonus payments — return for rework or reject if not in order',
    icon:     '💳',
    gradient: 'from-amber-50 to-amber-100/60',
    border:   'border-amber-200',
    iconBg:   'bg-amber-100 text-amber-700',
    titleClr: 'text-amber-800',
  },
  {
    id:       'summary',
    title:    'Payroll Summary',
    desc:     'Total payroll cost, department breakdown and per-employee details',
    icon:     '📊',
    gradient: 'from-blue-50 to-blue-100/60',
    border:   'border-blue-200',
    iconBg:   'bg-blue-100 text-blue-700',
    titleClr: 'text-blue-800',
  },
  {
    id:       'payslips',
    title:    'Payslips & Bank',
    desc:     'Payslip generation, bank transfer advice and compliance registers',
    icon:     '🏦',
    gradient: 'from-indigo-50 to-indigo-100/60',
    border:   'border-indigo-200',
    iconBg:   'bg-indigo-100 text-indigo-700',
    titleClr: 'text-indigo-800',
  },
  {
    id:       'analytics',
    title:    'Payroll Analytics',
    desc:     'Monthly trends, gross/net breakdown and salary distribution charts',
    icon:     '📈',
    gradient: 'from-purple-50 to-purple-100/60',
    border:   'border-purple-200',
    iconBg:   'bg-purple-100 text-purple-700',
    titleClr: 'text-purple-800',
  },
];

// ── Run status badge styling ──────────────────────────────────────────────────
function runStatusStyle(status) {
  if (status === 'pending_head_approval') return 'bg-amber-100 text-amber-700';
  if (['approved', 'published', 'closed', 'payslip_generated'].includes(status))
    return 'bg-emerald-100 text-emerald-700';
  if (status === 'under_review') return 'bg-blue-100 text-blue-700';
  if (status === 'processing')   return 'bg-orange-100 text-orange-700';
  if (status === 'error_found')  return 'bg-rose-100 text-rose-700';
  return 'bg-slate-100 text-slate-600';
}

function runStatusLabel(status) {
  if (status === 'pending_head_approval') return '⏳ Awaiting Finance Head Approval';
  if (status === 'processing')            return 'Generated — Awaiting Finance Review';
  if (status === 'under_review')          return 'Finance Review in Progress';
  if (status === 'error_found')           return 'Errors Found — Awaiting Finance Resolution';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Main component ────────────────────────────────────────────────────────────
export default function FinanceHeadHome() {
  const navigate = useNavigate();
  const [stats, setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);
  const [notice, setNotice] = useState(null);
  const [hikeRequests, setHikeRequests] = useState([]);
  const [hikePendingCount, setHikePendingCount] = useState(0);
  const [bonusPendingCount, setBonusPendingCount] = useState(0);
  const [hikeReviewingId, setHikeReviewingId] = useState(null);
  const [rejectingHikeId, setRejectingHikeId] = useState(null);
  const [hikeRejectComment, setHikeRejectComment] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    setNotice(null);
    financeApi.getAdminDashboardStats()
      .then(setStats)
      .catch((e) => setError(e?.data?.detail || e.message || 'Failed to load dashboard'))
      .finally(() => setLoading(false));
    financeApi.listHikeRequests({ statusFilter: 'pending_finance_head_approval', limit: 10 })
      .then((data) => {
        const rows = Array.isArray(data) ? data : [];
        setHikeRequests(rows);
        setHikePendingCount(rows.length);
      })
      .catch(() => { setHikeRequests([]); setHikePendingCount(0); });
    financeApi.getPendingBonusCount()
      .then((data) => setBonusPendingCount(data?.head_count ?? data?.pending_count ?? 0))
      .catch(() => setBonusPendingCount(0));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl bg-rose-50 border border-rose-200 p-6 text-rose-700 text-sm flex items-start gap-3">
        <span className="text-xl mt-0.5">⚠</span>
        <div>
          <strong>Error loading dashboard:</strong> {error}
          <button
            onClick={load}
            className="ml-3 underline text-rose-600 hover:text-rose-800"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const run               = stats?.current_run;
  const runStatus         = run?.status || 'none';
  const recentRuns        = stats?.recent_runs || [];
  const isPendingApproval = runStatus === 'pending_head_approval';

  const finalApprovalMessage = (status) => {
    if (status === 'processing') {
      return 'Payroll has been generated. Finance is reviewing employee-wise breakdown before submitting for your approval.';
    }
    if (status === 'under_review') {
      return 'Finance team has submitted a correction. Awaiting Finance re-submission to your approval queue.';
    }
    if (status === 'error_found') {
      return 'Payroll errors have been flagged by Finance. Awaiting resolution before submission.';
    }
    if (['approved', 'payslip_generated', 'published', 'closed'].includes(status)) {
      return 'Finance Head approval is already complete for this payroll run.';
    }
    return 'Final approval opens after Finance submits the payroll run for Finance Head Approval.';
  };

  const APPROVAL_NAVIGABLE = [
    'pending_head_approval', 'approved', 'payslip_generated', 'published', 'closed',
  ];

  const openFinalApproval = (status = runStatus) => {
    if (APPROVAL_NAVIGABLE.includes(status)) {
      setNotice(null);
      navigate(`${BASE}/final-approval`);
      return;
    }
    setNotice(finalApprovalMessage(status));
  };

  const openActionCard = (id) => {
    if (id === 'final-approval') {
      openFinalApproval();
      return;
    }
    setNotice(null);
    navigate(`${BASE}/${id}`);
  };

  const handleHeadApproveHike = async (id) => {
    setHikeReviewingId(id);
    try {
      await financeApi.headApproveHikeRequest(id);
      setNotice('Salary hike approved. New salary structure version created.');
      load();
    } catch (e) {
      setNotice(e?.data?.detail || e.message || 'Failed to approve salary hike.');
    } finally {
      setHikeReviewingId(null);
    }
  };

  const handleHeadRejectHike = async () => {
    if (!rejectingHikeId) return;
    setHikeReviewingId(rejectingHikeId);
    try {
      await financeApi.headRejectHikeRequest(rejectingHikeId, hikeRejectComment);
      setRejectingHikeId(null);
      setHikeRejectComment('');
      setNotice('Salary hike rejected.');
      load();
    } catch (e) {
      setNotice(e?.data?.detail || e.message || 'Failed to reject salary hike.');
    } finally {
      setHikeReviewingId(null);
    }
  };

  return (
    <div className="space-y-6">

      {rejectingHikeId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h3 className="text-sm font-bold text-slate-800 mb-1">Final Reject — Salary Hike Request</h3>
            <p className="text-xs text-slate-500 mb-3">This is the final rejection. The request will be closed.</p>
            <textarea
              value={hikeRejectComment}
              onChange={e => setHikeRejectComment(e.target.value)}
              rows={3}
              placeholder="Reason for final rejection (required)..."
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => { setRejectingHikeId(null); setHikeRejectComment(''); }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={handleHeadRejectHike}
                disabled={!hikeRejectComment.trim() || hikeReviewingId === rejectingHikeId}
                className="rounded-lg bg-rose-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-600 disabled:opacity-50"
              >
                {hikeReviewingId === rejectingHikeId ? 'Rejecting...' : 'Final Reject'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Finance Head Payroll</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {run
              ? `${run.month_label} · ${runStatusLabel(runStatus)}`
              : 'No active payroll run — awaiting Finance team to initiate'}
          </p>
        </div>
        {isPendingApproval && (
          <button
            onClick={() => openFinalApproval()}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 transition shadow-sm"
          >
            <span>✅</span>
            <span>Review Approval</span>
          </button>
        )}
      </div>

      {notice && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          {notice}
        </div>
      )}

      {/* ── Pending-approval banner ───────────────────────────────────────── */}
      {isPendingApproval && (
        <div className="flex items-start gap-4 rounded-xl border border-emerald-300 bg-emerald-50 p-4">
          <span className="text-2xl flex-shrink-0 mt-0.5">🔔</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-emerald-900">
              Payroll run &ldquo;{run.month_label}&rdquo; is awaiting your final approval
            </p>
            <p className="text-xs text-emerald-700 mt-0.5">
              The Finance team has completed their review. Please approve or return for corrections.
              {run.total_employees != null && (
                <> · <strong>{run.total_employees}</strong> employees · Net <strong>{fmt(run.total_net)}</strong></>
              )}
            </p>
          </div>
          <button
            onClick={() => openFinalApproval()}
            className="flex-shrink-0 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 transition"
          >
            Review →
          </button>
        </div>
      )}

      {/* ── Workflow progress ─────────────────────────────────────────────── */}
      {run && <WorkflowProgress status={runStatus} />}

      {/* ── Current run KPI cards ─────────────────────────────────────────── */}
      {run && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            {
              label: 'Employees',
              value: run.total_employees ?? '—',
              color: 'text-blue-700',
              icon:  '👥',
              bg:    'bg-blue-50',
            },
            {
              label: 'Gross Payroll',
              value: fmt(run.total_gross),
              color: 'text-slate-800',
              icon:  '💰',
              bg:    'bg-slate-50',
            },
            {
              label: 'Net Payroll',
              value: fmt(run.total_net),
              color: 'text-emerald-700',
              icon:  '✅',
              bg:    'bg-emerald-50',
            },
            {
              label: 'Open Errors',
              value: run.open_errors ?? 0,
              color: (run.open_errors ?? 0) > 0 ? 'text-rose-600' : 'text-emerald-600',
              icon:  (run.open_errors ?? 0) > 0 ? '⚠' : '✓',
              bg:    (run.open_errors ?? 0) > 0 ? 'bg-rose-50' : 'bg-emerald-50',
            },
          ].map((c) => (
            <div
              key={c.label}
              className="bg-white rounded-xl border border-slate-200 p-4 shadow-soft"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  {c.label}
                </span>
                <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-base ${c.bg}`}>
                  {c.icon}
                </span>
              </div>
              <p className={`text-xl font-bold font-mono ${c.color}`}>{c.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Action cards ──────────────────────────────────────────────────── */}
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Payroll Actions
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {ACTION_CARDS.map((card) => (
            <button
              key={card.id}
              onClick={() => openActionCard(card.id)}
              className={`relative text-left rounded-xl border p-5 bg-gradient-to-br transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 active:scale-[0.98] ${card.gradient} ${card.border}`}
            >
              {/* Pending badges */}
              {card.id === 'final-approval' && isPendingApproval && (
                <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold shadow">
                  !
                </span>
              )}
              {card.id === 'salary-revision' && hikePendingCount > 0 && (
                <span className="absolute -top-2 -right-2 flex h-5 min-w-[20px] px-1 items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-bold shadow">
                  {hikePendingCount}
                </span>
              )}
              {card.id === 'bonus-requests' && bonusPendingCount > 0 && (
                <span className="absolute -top-2 -right-2 flex h-5 min-w-[20px] px-1 items-center justify-center rounded-full bg-violet-500 text-white text-[10px] font-bold shadow">
                  {bonusPendingCount}
                </span>
              )}

              <div
                className={`inline-flex h-10 w-10 items-center justify-center rounded-lg text-xl mb-3 ${card.iconBg}`}
              >
                {card.icon}
              </div>

              <h3 className={`text-sm font-semibold mb-1 ${card.titleClr}`}>
                {card.title}
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">{card.desc}</p>

              <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 group-hover:text-slate-700">
                Open
                <svg
                  className="h-3 w-3"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Approval summary card (current run details) ───────────────────── */}
      {run && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-slate-700">
              Current Run: {run.month_label}
            </p>
            <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${runStatusStyle(runStatus)}`}>
              {runStatusLabel(runStatus)}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {[
              { label: 'Employees',         value: run.total_employees },
              { label: 'Gross Payroll',      value: fmt(run.total_gross) },
              { label: 'Total Deductions',   value: fmt(run.total_deductions) },
              { label: 'Net Payroll',        value: fmt(run.total_net) },
            ].map((item) => (
              <div key={item.label} className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">{item.label}</p>
                <p className="font-mono font-bold text-slate-800 mt-0.5">{item.value}</p>
              </div>
            ))}
          </div>
          {(run.total_pf || run.total_esi || run.total_tds) && (
            <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
              {[
                { label: 'PF Total',  value: fmt(run.total_pf),  color: 'text-indigo-700' },
                { label: 'ESI Total', value: fmt(run.total_esi), color: 'text-purple-700' },
                { label: 'TDS Total', value: fmt(run.total_tds), color: 'text-rose-700' },
              ].map((item) => (
                <div key={item.label} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{item.label}</p>
                  <p className={`font-mono font-semibold mt-0.5 ${item.color}`}>{item.value}</p>
                </div>
              ))}
            </div>
          )}
          {/* Finance Head approval status */}
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <div className="text-xs text-slate-500">
              Finance Reviewed:
              <span className={`ml-1 font-semibold ${run.finance_reviewed ? 'text-emerald-600' : 'text-amber-600'}`}>
                {run.finance_reviewed ? '✓ Yes' : 'Pending'}
              </span>
            </div>
            <div className="text-xs text-slate-500">
              Head Approved:
              <span className={`ml-1 font-semibold ${run.finance_head_approved ? 'text-emerald-600' : 'text-slate-400'}`}>
                {run.finance_head_approved ? '✓ Yes' : '—'}
              </span>
            </div>
            {run.payslips_published != null && (
              <div className="text-xs text-slate-500">
                Payslips Published:
                <span className={`ml-1 font-semibold ${run.payslips_published ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {run.payslips_published ? '✓ Yes' : '—'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Recent payroll runs ───────────────────────────────────────────── */}
      {hikeRequests.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-slate-700">Salary Revision Requests</p>
              <span className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 px-2.5 py-0.5 text-xs font-bold">
                {hikeRequests.length} Pending Final Approval
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate(`${BASE}/bonus-requests`)}
                className="text-xs text-violet-600 font-medium hover:underline"
              >
                Bonus Requests →
              </button>
              <button
                onClick={() => navigate(`${BASE}/salary-revision`)}
                className="text-xs text-brand-600 font-medium hover:underline"
              >
                Manage all revisions →
              </button>
            </div>
          </div>
          <div className="divide-y divide-slate-50">
            {hikeRequests.map((req) => (
              <div key={req.id} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-800 truncate">{req.employee_name || '—'}</p>
                    {req.employee_code && (
                      <span className="text-xs text-slate-400 font-mono">{req.employee_code}</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {fmt(req.old_ctc)}
                    {' → '}
                    <span className="text-emerald-700 font-medium">{fmt(req.new_ctc)}</span>
                    {' · Effective '}
                    {req.effective_from || '—'}
                  </p>
                  {req.reviewed_by_name && (
                    <p className="text-xs text-slate-400 truncate max-w-xs">
                      Finance Reviewed by {req.reviewed_by_name}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {req.finance_recommendation && (
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      req.finance_recommendation === 'recommend_approval'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-rose-100 text-rose-800'
                    }`}>
                      Finance: {req.finance_recommendation === 'recommend_approval' ? 'Recommends Approval' : 'Recommends Rejection'}
                    </span>
                  )}
                  <button
                    onClick={() => handleHeadApproveHike(req.id)}
                    disabled={hikeReviewingId === req.id}
                    className="rounded bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 text-xs font-medium hover:bg-emerald-100 transition disabled:opacity-50"
                    title="Give final approval and activate salary revision"
                  >
                    {hikeReviewingId === req.id ? '...' : 'Final Approve'}
                  </button>
                  <button
                    onClick={() => { setRejectingHikeId(req.id); setHikeRejectComment(''); }}
                    className="rounded bg-rose-50 text-rose-700 border border-rose-200 px-2.5 py-1 text-xs font-medium hover:bg-rose-100 transition"
                    title="Reject this salary hike request"
                  >
                    Final Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {recentRuns.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Recent Payroll Runs</p>
            <button
              onClick={() => openFinalApproval()}
              className="text-xs text-brand-600 font-medium hover:underline"
            >
              Open Approval →
            </button>
          </div>
          <div className="divide-y divide-slate-50">
            {recentRuns.slice(0, 6).map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition cursor-pointer"
                onClick={() => openFinalApproval(r.status)}
              >
                <div>
                  <p className="text-sm font-semibold text-slate-800">{r.month_label}</p>
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">
                    Net {fmt(r.total_net)} · {r.total_employees} emp
                  </p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${runStatusStyle(r.status)}`}>
                  {runStatusLabel(r.status)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state — no runs at all ──────────────────────────────────── */}
      {!run && recentRuns.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-12 text-center">
          <p className="text-5xl mb-4">📋</p>
          <p className="text-sm font-semibold text-slate-700 mb-1">No payroll runs yet</p>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            The Finance team will initiate a payroll run and notify you when your approval is required.
            All action cards above are available once a run is active.
          </p>
        </div>
      )}

    </div>
  );
}
