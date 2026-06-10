import { useEffect, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';
import SalaryHikeModal from '../../components/SalaryHikeModal';

const WORKFLOW_STEPS = [
  { key: 'draft',                   label: 'Initiated',                     short: 'Init' },
  { key: 'attendance_frozen',       label: 'Payroll Input Frozen',          short: 'Frozen' },
  { key: 'processing',              label: 'Generated',                     short: 'Generated' },
  { key: 'under_review',            label: 'Finance Review',                short: 'Review' },
  { key: 'error_found',             label: 'Error Found',                   short: 'Error' },
  { key: 'pending_head_approval',   label: 'Finance Head Approval',         short: 'Head Appr.' },
  { key: 'approved',                label: 'Final Approved — Ready',        short: 'Approved' },
  { key: 'payslip_generated',       label: 'Payslips Generated',            short: 'Payslips' },
  { key: 'published',               label: 'Published to ESS',              short: 'Published' },
  { key: 'closed',                  label: 'Closed',                        short: 'Closed' },
];

const STATUS_ORDER = WORKFLOW_STEPS.map((s) => s.key);

function statusIndex(status) {
  const i = STATUS_ORDER.indexOf(status);
  return i === -1 ? 0 : i;
}

function fmt(n) {
  if (!n) return '₹0';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(2)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function StatCard({ label, value, sub, accent, icon }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">{label}</span>
        <span className={`flex h-9 w-9 items-center justify-center rounded-lg text-lg ${accent}`}>{icon}</span>
      </div>
      <p className="text-2xl font-bold text-slate-800 font-mono">{value}</p>
      {sub && <p className="text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

function WorkflowProgress({ status }) {
  const current = statusIndex(status);
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Payroll Workflow Progress</p>
      <div className="flex items-center gap-0 overflow-x-auto pb-1">
        {WORKFLOW_STEPS.map((step, idx) => {
          const done = idx < current;
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
                <span className={`text-[10px] font-medium whitespace-nowrap ${active ? 'text-brand-600' : done ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {step.short}
                </span>
              </div>
              {idx < WORKFLOW_STEPS.length - 1 && (
                <div className={`h-0.5 w-8 flex-shrink-0 mx-0.5 ${idx < current ? 'bg-emerald-400' : 'bg-slate-200'}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DeptTable({ rows }) {
  if (!rows?.length) {
    return (
      <div className="text-center py-8 text-slate-400 text-sm">
        No department data yet — generate a payroll run to see breakdowns.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100">
            {['Department', 'Headcount', 'Gross', 'Deductions', 'Net Pay'].map((h) => (
              <th key={h} className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-slate-50 hover:bg-slate-50 transition">
              <td className="py-2.5 px-3 font-medium text-slate-700">{r.department}</td>
              <td className="py-2.5 px-3 text-slate-500">{r.headcount}</td>
              <td className="py-2.5 px-3 font-mono text-slate-700">{fmt(r.gross)}</td>
              <td className="py-2.5 px-3 font-mono text-rose-600">{fmt(r.deductions)}</td>
              <td className="py-2.5 px-3 font-mono font-semibold text-emerald-700">{fmt(r.net)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const HIKE_STATUS_STYLES = {
  pending_finance_review: { bg: 'bg-amber-100 text-amber-800', label: 'Pending Finance Review' },
  pending_finance_head_approval: { bg: 'bg-blue-100 text-blue-800', label: 'Finance Reviewed / Pending Finance Head Approval' },
  approved: { bg: 'bg-emerald-100 text-emerald-800', label: 'Approved' },
  rejected: { bg: 'bg-rose-100 text-rose-800', label: 'Rejected' },
};

function HikeStatusBadge({ status }) {
  const s = HIKE_STATUS_STYLES[status] || { bg: 'bg-slate-100 text-slate-600', label: status };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.bg}`}>
      {s.label}
    </span>
  );
}

const formatPayrollMonth = (month, year) => (
  new Date(year, month - 1, 1).toLocaleString('en-IN', { month: 'long', year: 'numeric' })
);

export default function FinanceHome() {
  const navigate = useNavigate();
  const location = useLocation();
  const { role } = useAuth();
  // Base path for admin payroll navigation.
  const r = (role || '').toLowerCase();
  const isAdminOrHr = r === 'admin' || r === 'hr';
  const FINANCE_BASE = (r === 'admin' || r === 'hr') ? '/admin-dashboard/payroll' : '/employee-dashboard/finance-payroll';
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const restoredDashboardState = location.state?.payrollDashboardState || {};
  const [selectedRunId, setSelectedRunId] = useState(restoredDashboardState.selectedRunId ?? null);

  // Salary hike state
  const [showHikeModal, setShowHikeModal] = useState(false);
  const [hikeRequests, setHikeRequests] = useState([]);
  const [pendingHikeCount, setPendingHikeCount] = useState(0);
  const [hikeNotification, setHikeNotification] = useState('');
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectComment, setRejectComment] = useState('');
  const [reviewingId, setReviewingId] = useState(null);

  // ── Payroll Input Readiness (temporary bridge) ────────────────────────────
  // Temporary payroll bridge until Attendance/Timesheet modules integrate.
  const [attSummary, setAttSummary]           = useState(null);
  const [attLoading, setAttLoading]           = useState(false);
  const [attActionLoading, setAttActionLoading] = useState(null); // 'validate'|'freeze'|'reset'
  const [attNotification, setAttNotification] = useState(null);  // {type:'success'|'warning'|'error', msg}
  const [attMonth, setAttMonth]               = useState(restoredDashboardState.attMonth ?? null);
  const [attYear, setAttYear]                 = useState(restoredDashboardState.attYear ?? null);
  const [availableMonths, setAvailableMonths] = useState([]);

  const load = useCallback((runId, month, year) => {
    setLoading(true);
    setError(null);
    financeApi.getAdminDashboardStats(runId, month, year)
      .then((data) => {
        setStats(data);
        // Always sync selectedRunId to whatever the backend returned.
        // When month+year were passed and no run exists, current_run is null →
        // selectedRunId becomes null so the workflow shows the "no run" state.
        if (!runId) {
          setSelectedRunId(data.current_run?.id ?? null);
        }
      })
      .catch((e) => setError(e?.data?.detail || e.message || 'Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, []);

  const loadHikeData = useCallback(() => {
    financeApi.listHikeRequests({ limit: 10 })
      .then(setHikeRequests)
      .catch(() => setHikeRequests([]));
    financeApi.getPendingHikeCount()
      .then(data => setPendingHikeCount(data?.count ?? 0))
      .catch(() => setPendingHikeCount(0));
  }, []);

  // Temporary payroll bridge until Attendance/Timesheet modules integrate.
  const loadAttendanceSummary = useCallback((month, year) => {
    if (!month || !year) return;
    setAttLoading(true);
    financeApi.getPayrollAttendanceSummary(month, year)
      .then(setAttSummary)
      .catch(() => setAttSummary(null))
      .finally(() => setAttLoading(false));
  }, []);

  useEffect(() => {
    const restored = location.state?.payrollDashboardState || {};
    const restoredRunId = restored.selectedRunId ?? null;
    loadHikeData();

    const initDashboard = (month, year) => {
      loadAttendanceSummary(month, year);
      if (restoredRunId) {
        // Restored navigation state: honour the specific run the user was viewing.
        setSelectedRunId(restoredRunId);
        load(restoredRunId);
      } else {
        // Normal entry: load the workflow run that belongs to the selected month.
        // Backend returns current_run=null when no run exists for that month.
        load(null, month, year);
      }
    };

    financeApi.getOpenPayrollMonth()
      .then(data => {
        const month = restored.attMonth ?? data.month;
        const year = restored.attYear ?? data.year;
        setAttMonth(month);
        setAttYear(year);
        setAvailableMonths(data.available_months || []);
        initDashboard(month, year);
      })
      .catch(() => {
        const n = new Date();
        const m = restored.attMonth ?? (n.getMonth() + 1);
        const y = restored.attYear ?? n.getFullYear();
        setAttMonth(m);
        setAttYear(y);
        initDashboard(m, y);
      });
  }, [load, loadHikeData, loadAttendanceSummary, location.state]);

  const handleRunChange = (e) => {
    const val = e.target.value ? parseInt(e.target.value, 10) : null;
    setSelectedRunId(val);
    load(val);
    // Keep attendance month in sync with the selected run.
    const selectedRun = recentRuns.find((r) => r.id === val);
    if (selectedRun?.month && selectedRun?.year) {
      setAttMonth(selectedRun.month);
      setAttYear(selectedRun.year);
      loadAttendanceSummary(selectedRun.month, selectedRun.year);
    }
  };

  const handleHikeSubmitted = (result) => {
    const empName = result?.employee_name || 'employee';
    setHikeNotification(`Salary hike request created for ${empName} and sent to Finance`);
    loadHikeData();
    setTimeout(() => setHikeNotification(''), 6000);
  };

  const handleApprove = async (reqId) => {
    setReviewingId(reqId);
    try {
      await financeApi.approveHikeRequest(reqId);
      loadHikeData();
    } catch (err) {
      console.error('Recommend approval failed:', err);
    } finally {
      setReviewingId(null);
    }
  };

  const handleReject = async () => {
    if (!rejectingId) return;
    setReviewingId(rejectingId);
    try {
      await financeApi.rejectHikeRequest(rejectingId, rejectComment);
      setRejectingId(null);
      setRejectComment('');
      loadHikeData();
    } catch (err) {
      console.error('Recommend rejection failed:', err);
    } finally {
      setReviewingId(null);
    }
  };

  // ── Payroll Input Readiness handlers — Temporary payroll bridge ───────────
  // Temporary payroll bridge until Attendance/Timesheet modules integrate.
  const handleValidateSummary = async () => {
    setAttActionLoading('validate');
    setAttNotification(null);
    try {
      const res = await financeApi.validatePayrollAttendance(attMonth, attYear);
      loadAttendanceSummary(attMonth, attYear);
      const msg = res?.can_freeze
        ? `Validation passed — all ${res.validation_passed} employees ready for payroll.`
        : `Validation done — ${res.validation_failed || 0} issue(s) found.`;
      setAttNotification({ type: res?.can_freeze ? 'success' : 'warning', msg });
    } catch (e) {
      setAttNotification({ type: 'error', msg: e?.data?.detail || 'Validation failed.' });
    } finally {
      setAttActionLoading(null);
    }
  };

  const handleFreezeAttendance = async () => {
    setAttActionLoading('freeze');
    setAttNotification(null);
    try {
      await financeApi.freezePayrollAttendance(attMonth, attYear);
      loadAttendanceSummary(attMonth, attYear);
      setAttNotification({ type: 'success', msg: 'Payroll input frozen. Finance team has been notified.' });
    } catch (e) {
      setAttNotification({ type: 'error', msg: e?.data?.detail || 'Freeze failed.' });
    } finally {
      setAttActionLoading(null);
    }
  };

  // DEV ONLY — TEMPORARY FOR PAYROLL TESTING. REMOVE AFTER REAL ATT/TS INTEGRATION.
  const handleResetFreeze = async () => {
    setAttActionLoading('reset');
    setAttNotification(null);
    try {
      await financeApi.resetPayrollAttendanceFreeze(attMonth, attYear);
      loadAttendanceSummary(attMonth, attYear);
      setAttNotification({ type: 'warning', msg: '[DEV] Freeze reset — rows are ready for re-testing. Validate and freeze again.' });
    } catch (e) {
      setAttNotification({ type: 'error', msg: e?.data?.detail || 'Reset failed.' });
    } finally {
      setAttActionLoading(null);
    }
  };

  // DEMO ONLY — clears payroll runs for May/June/July 2026 so demo can run from scratch.
  const [demoResetBusy, setDemoResetBusy] = useState(false);
  const [demoResetMsg, setDemoResetMsg]   = useState('');
  const handleDemoReset = async () => {
    if (!window.confirm('Reset ALL payroll data for May, June, July 2026?\n\nThis will delete payroll runs and unfreeze attendance summary rows. Employee data, salary structures and attendance records are preserved.')) return;
    setDemoResetBusy(true);
    setDemoResetMsg('');
    try {
      const res = await financeApi.demoReset({ months: [5, 6, 7], year: 2026 });
      setDemoResetMsg(`Demo reset complete — ${res.deleted?.payroll_runs ?? 0} run(s) deleted. Page will reload.`);
      setTimeout(() => window.location.reload(), 1500);
    } catch (e) {
      setDemoResetMsg(`Reset failed: ${e?.data?.detail || e?.message || 'Unknown error'}`);
    } finally {
      setDemoResetBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl bg-rose-50 border border-rose-200 p-6 text-rose-700 text-sm">
        <strong>Error loading dashboard:</strong> {error}
      </div>
    );
  }

  const run = stats?.current_run;
  const runStatus = run?.status || 'none';
  // Deduplicate recent_runs client-side as a safety net (backend already deduplicates)
  const _rawRecentRuns = stats?.recent_runs || [];
  const _STATUS_RANK_HOME = {
    draft: 0, attendance_frozen: 1, processing: 2,
    under_review: 3, pending_head_approval: 4, approved: 5,
    payslip_generated: 6, bank_advice_generated: 7, published: 8, closed: 9,
  };
  const _dedupHome = {};
  for (const _r of _rawRecentRuns) {
    const _m = _r.month || (_r.pay_period_start ? new Date(_r.pay_period_start + 'T00:00:00').getMonth() + 1 : 0);
    const _y = _r.year || (_r.pay_period_start ? new Date(_r.pay_period_start + 'T00:00:00').getFullYear() : 0);
    const _k = `${_y}-${_m}`;
    if (!_dedupHome[_k] || (_STATUS_RANK_HOME[_r.status] ?? -1) > (_STATUS_RANK_HOME[_dedupHome[_k].status] ?? -1)) {
      _dedupHome[_k] = _r;
    }
  }
  const recentRuns = Object.values(_dedupHome).sort((a, b) => {
    const ay = a.year || 0, by2 = b.year || 0, am = a.month || 0, bm = b.month || 0;
    return by2 !== ay ? by2 - ay : bm - am;
  });
  const isReadOnly = run?.is_read_only;

  // ── Payroll Input Readiness computed values — Temporary payroll bridge ────
  // Temporary payroll bridge until Attendance/Timesheet modules integrate.
  const attNoSummary    = !attSummary || attSummary.with_summary === 0;
  const attIsFrozen     = attSummary?.all_frozen ?? false;
  const attIsReady      = !attIsFrozen && attSummary?.attendance_overall === 'ready';
  // Issues = sum of row issues + employees with no row at all
  const attDisplayIssues = attSummary
    ? (attSummary.issues_count || 0) + (attSummary.missing_summary || 0)
    : null;
  const attTotalEmp    = attSummary?.total_employees ?? stats?.total_active_employees ?? '—';
  const attReadyCount  = attSummary?.ready_count ?? 0;
  // Can freeze when every active employee has is_ready_for_payroll=true (attendance_overall='ready')
  const attCanFreeze   = attIsReady;
  const attMonthLabel  = attSummary?.month_label
    || (attMonth && attYear ? formatPayrollMonth(attMonth, attYear) : '…');

  const attHasMismatch = (attSummary?.rows ?? []).some(
    row => row.total_working_days != null && (
      (row.present_days ?? 0) > row.total_working_days ||
      (row.leave_days ?? 0) + (row.lop_days ?? 0) > row.total_working_days
    )
  );

  return (
    <div className="space-y-6">
      {/* Salary Hike Modal */}
      {showHikeModal && (
        <SalaryHikeModal
          onClose={() => setShowHikeModal(false)}
          onSubmitted={handleHikeSubmitted}
        />
      )}

      {/* Reject Dialog */}
      {rejectingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h3 className="text-sm font-bold text-slate-800 mb-1">Recommend Rejection to Finance Head</h3>
            <p className="text-xs text-slate-500 mb-3">
              Your recommendation will be forwarded to Finance Head for final decision.
            </p>
            <textarea
              value={rejectComment}
              onChange={e => setRejectComment(e.target.value)}
              rows={3}
              placeholder="Reason for recommending rejection (required)..."
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => { setRejectingId(null); setRejectComment(''); }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={!rejectComment.trim() || reviewingId === rejectingId}
                className="rounded-lg bg-rose-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-600 disabled:opacity-50"
              >
                {reviewingId === rejectingId ? 'Submitting…' : 'Recommend Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-slate-800">
            {r === 'admin' ? 'Admin Payroll Dashboard' : r === 'hr' ? 'HR Payroll Dashboard' : 'Payroll Review'}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isAdminOrHr
              ? attMonthLabel
              : run
              ? `${isReadOnly ? '🔒 ' : ''}${run.month_label}${isReadOnly ? ' · Read-only' : ' · Active'}`
              : 'No active payroll run'}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Payroll Run Selector — Finance / Finance Head only */}
          {['finance', 'finance_head'].includes((role || '').toLowerCase()) && (
            <select
              value={selectedRunId || ''}
              onChange={handleRunChange}
              disabled={loading}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              style={{ minWidth: 200 }}
            >
              <option value="">— Select Payroll Run —</option>
              {recentRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.month_label} · {r.status.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          )}
          {isReadOnly && (
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500">
              🔒 Closed — Read Only
            </span>
          )}
          {(role || '').toLowerCase() !== 'admin' && (
            <button
              onClick={() => navigate(`${FINANCE_BASE}/payroll-runs`)}
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition"
            >
              <span>Manage Payroll Runs</span>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          )}
          {isAdminOrHr && (
            <button
              onClick={() => setShowHikeModal(true)}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 transition"
            >
              <span>+</span>
              <span>Give Salary Hike</span>
            </button>
          )}
          {isAdminOrHr && (
            <button
              onClick={() => navigate('/admin-dashboard/my-payroll', {
                state: {
                  fromPayrollDashboard: true,
                  backTo: location.pathname + location.search,
                  payrollDashboardState: { selectedRunId, attMonth, attYear },
                },
              })}
              className="flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 transition"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="5" width="20" height="14" rx="2" />
                <line x1="2" y1="10" x2="22" y2="10" />
                <path d="M7 15h4" /><path d="M15 14h2" />
              </svg>
              <span>My Payroll</span>
            </button>
          )}
        </div>
      </div>

      {/* Hike creation confirmation */}
      {hikeNotification && (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <span className="text-emerald-500 text-lg mt-0.5">✓</span>
          <p className="text-sm font-medium text-emerald-800">{hikeNotification}</p>
        </div>
      )}

      {/* Admin: pending hike review count */}
      {(role || '').toLowerCase() === 'admin' && pendingHikeCount > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <span className="text-amber-500 text-lg mt-0.5">📋</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              Finance Pending Hike Review: {pendingHikeCount}
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              Salary hike request{pendingHikeCount > 1 ? 's are' : ' is'} awaiting finance review
            </p>
          </div>
        </div>
      )}

      {/* Finance: pending hike review count */}
      {(role || '').toLowerCase() === 'finance' && pendingHikeCount > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <span className="text-blue-500 text-lg mt-0.5">📋</span>
          <div>
            <p className="text-sm font-semibold text-blue-800">
              {pendingHikeCount} salary hike request{pendingHikeCount > 1 ? 's' : ''} pending your review
            </p>
            <p className="text-xs text-blue-700 mt-0.5">Review and recommend approval or rejection — Finance Head will give the final decision</p>
          </div>
        </div>
      )}

      {/* Alerts */}
      {run?.open_errors > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <span className="text-amber-500 text-lg mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              {run.open_errors} unresolved payroll error{run.open_errors > 1 ? 's' : ''} require attention
            </p>
            <button
              onClick={() => navigate(`${FINANCE_BASE}/review`)}
              className="mt-1 text-xs text-amber-700 underline"
            >
              Open Finance Review →
            </button>
          </div>
        </div>
      )}

      {stats?.pending_approval_count > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <span className="text-blue-500 text-lg mt-0.5">ℹ</span>
          <div>
            <p className="text-sm font-semibold text-blue-800">
              Payroll run is pending final approval
            </p>
            <button
              onClick={() => navigate(r === 'admin' ? `${FINANCE_BASE}/approval` : `${FINANCE_BASE}/head-approval`)}
              className="mt-1 text-xs text-blue-700 underline"
            >
              Go to approval →
            </button>
          </div>
        </div>
      )}

      {run && runStatus === 'approved' && (
        <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
          <span className="text-teal-500 text-lg mt-0.5">📄</span>
          <div>
            <p className="text-sm font-semibold text-teal-800">
              Finance Head has approved — Generate payslips to continue
            </p>
            <button
              onClick={() => navigate(r === 'admin' ? `${FINANCE_BASE}/approval` : `${FINANCE_BASE}/head-approval`)}
              className="mt-1 text-xs text-teal-700 underline"
            >
              Open Approval →
            </button>
          </div>
        </div>
      )}

      {run && runStatus === 'payslip_generated' && (
        <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
          <span className="text-teal-500 text-lg mt-0.5">🚀</span>
          <div>
            <p className="text-sm font-semibold text-teal-800">
              Payslips generated — Publish to ESS to complete the cycle
            </p>
            <button
              onClick={() => navigate(r === 'admin' ? `${FINANCE_BASE}/approval` : `${FINANCE_BASE}/head-approval`)}
              className="mt-1 text-xs text-teal-700 underline"
            >
              Open Approval →
            </button>
          </div>
        </div>
      )}

      {/* ── Payroll Input Readiness ─────────────────────────────────────────── */}
      {/* Temporary payroll bridge until Attendance/Timesheet modules integrate. */}
      {isAdminOrHr && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          {/* Card header */}
          <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Payroll Input Readiness — {attMonthLabel}
            </p>
            <div className="flex items-center gap-2">
              {availableMonths.length > 1 && attMonth && attYear && (
                <select
                  value={`${attYear}-${attMonth}`}
                  onChange={e => {
                    const [y, m] = e.target.value.split('-').map(Number);
                    setAttMonth(m);
                    setAttYear(y);
                    loadAttendanceSummary(m, y);
                    // Reload workflow progress for the selected month.
                    // Backend returns current_run=null when no run exists.
                    load(null, m, y);
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-400"
                >
                  {availableMonths.map(opt => (
                    <option key={`${opt.year}-${opt.month}`} value={`${opt.year}-${opt.month}`}>
                      {opt.month_label}{opt.is_fully_frozen ? ' · Frozen' : ''}
                    </option>
                  ))}
                </select>
              )}
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                attIsFrozen   ? 'bg-emerald-100 text-emerald-700'
                : attNoSummary ? 'bg-rose-100   text-rose-700'
                : attIsReady   ? 'bg-blue-100   text-blue-700'
                :                'bg-amber-100  text-amber-700'
              }`}>
                {attIsFrozen   ? '🔒 Frozen'
                 : attNoSummary ? '⚠ Not Created'
                 : attIsReady   ? '✓ Ready'
                 :                '⚠ Partial'}
              </span>
            </div>
          </div>

          {/* Loading spinner */}
          {attLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-400 py-2">
              <div className="h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              Loading readiness data…
            </div>
          ) : (
            <>
              {/* Info grid */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm mb-4">
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Attendance Summary</p>
                  <p className={`font-semibold mt-0.5 ${
                    attNoSummary ? 'text-rose-600' : 'text-emerald-700'
                  }`}>
                    {attNoSummary ? 'Not Created' : attIsFrozen ? 'Finalized' : 'Ready'}
                  </p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Timesheet Summary</p>
                  <p className={`font-semibold mt-0.5 ${
                    attNoSummary ? 'text-rose-600' : 'text-emerald-700'
                  }`}>
                    {attNoSummary ? 'Not Created' : 'Ready'}
                  </p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Employees Ready</p>
                  <p className="font-mono font-bold text-slate-800 mt-0.5">
                    {attReadyCount} / {attTotalEmp}
                  </p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Issues</p>
                  <p className={`font-mono font-bold mt-0.5 ${
                    (attDisplayIssues ?? 0) > 0 || attHasMismatch ? 'text-rose-600' : 'text-emerald-700'
                  }`}>
                    {attDisplayIssues ?? '—'}
                  </p>
                  {attHasMismatch && (
                    <p className="mt-0.5 text-[10px] text-rose-500">+ day-count errors</p>
                  )}
                </div>
                <div className="bg-slate-50 rounded-lg p-3 md:col-span-2">
                  <p className="text-xs text-slate-500">Status</p>
                  <p className={`font-semibold mt-0.5 ${
                    attIsFrozen   ? 'text-emerald-700'
                    : attIsReady   ? 'text-blue-700'
                    : attNoSummary ? 'text-slate-400'
                    :                'text-amber-700'
                  }`}>
                    {attIsFrozen   ? 'Frozen for Payroll'
                     : attIsReady   ? 'Ready for Input Freeze'
                     : attNoSummary ? 'Not Created'
                     :                'Partial — Validate Required'}
                  </p>
                </div>
              </div>

              {/* ── Payroll Input Details (read-only, pre-freeze) ─────────── */}
              {!attNoSummary && attSummary?.rows?.length > 0 && (
                <details className="group mb-4">
                  <summary className="flex cursor-pointer list-none select-none items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800">
                    <span className="inline-block text-slate-400 transition-transform group-open:rotate-90">▶</span>
                    Payroll Input Details — {attMonthLabel}
                    <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                      {attSummary.rows.length} employees
                    </span>
                  </summary>
                  <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50">
                          <th className="whitespace-nowrap px-3 py-2 font-semibold text-slate-500">Emp Code</th>
                          <th className="whitespace-nowrap px-3 py-2 font-semibold text-slate-500">Employee Name</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">Working Days</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">Present Days</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">Paid Leave Days</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">LOP Days</th>
                          <th className="whitespace-nowrap px-3 py-2 font-semibold text-slate-500">LOP Source</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">LOP Status</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">Payable Days</th>
                          <th className="whitespace-nowrap px-3 py-2 text-center font-semibold text-slate-500">Validation Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {attSummary.rows.map((row) => {
                          const mismatch =
                            row.total_working_days != null && (
                              (row.present_days ?? 0) > row.total_working_days ||
                              (row.leave_days ?? 0) + (row.lop_days ?? 0) > row.total_working_days
                            );
                          return (
                            <tr
                              key={row.employee_id}
                              className={`transition ${mismatch ? 'bg-rose-50' : 'hover:bg-slate-50'}`}
                            >
                              <td className="whitespace-nowrap px-3 py-2 font-mono text-slate-600">
                                {row.employee_code ?? '—'}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">
                                {row.employee_name}
                                {mismatch && (
                                  <span className="ml-1.5 text-[10px] text-rose-500">⚠ day count mismatch</span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-center font-mono text-slate-700">
                                {row.total_working_days ?? '—'}
                              </td>
                              <td className="px-3 py-2 text-center font-mono text-slate-700">
                                {row.present_days ?? '—'}
                              </td>
                              <td className="px-3 py-2 text-center font-mono text-slate-700">
                                {row.leave_days ?? '—'}
                              </td>
                              <td className={`px-3 py-2 text-center font-mono font-semibold ${
                                (row.lop_days ?? 0) > 0 ? 'text-rose-600' : 'text-slate-700'
                              }`}>
                                {row.lop_days ?? '—'}
                              </td>
                              <td className="whitespace-nowrap px-3 py-2 text-slate-700">
                                {row.lop_source || 'Leave Management'}
                              </td>
                              <td className="px-3 py-2 text-center">
                                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${
                                  (row.lop_status || 'ready') === 'ready'
                                    ? 'bg-emerald-100 text-emerald-700'
                                    : 'bg-amber-100 text-amber-700'
                                }`}>
                                  {(row.lop_status || 'ready').replace(/_/g, ' ')}
                                </span>
                                {row.lop_warning && (
                                  <p className="mt-1 max-w-[220px] text-left text-[10px] font-medium text-amber-700">
                                    {row.lop_warning}
                                  </p>
                                )}
                              </td>
                              <td className="px-3 py-2 text-center font-mono font-semibold text-slate-800">
                                {row.payable_days ?? '—'}
                              </td>
                              <td className="px-3 py-2 text-center">
                                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${
                                  row.validation_status === 'passed'  ? 'bg-emerald-100 text-emerald-700'
                                  : row.validation_status === 'failed' ? 'bg-rose-100 text-rose-700'
                                  :                                       'bg-amber-100 text-amber-700'
                                }`}>
                                  {row.validation_status ?? 'pending'}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                        {/* Totals row */}
                        <tr className="border-t-2 border-slate-300 bg-slate-100 font-semibold">
                          <td className="px-3 py-2" />
                          <td className="whitespace-nowrap px-3 py-2 text-slate-600">Totals</td>
                          <td className="px-3 py-2 text-center font-mono text-slate-800">
                            {attSummary.rows.reduce((s, r) => s + (r.total_working_days ?? 0), 0)}
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-slate-800">
                            {attSummary.rows.reduce((s, r) => s + (r.present_days ?? 0), 0)}
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-slate-800">
                            {attSummary.rows.reduce((s, r) => s + (r.leave_days ?? 0), 0)}
                          </td>
                          <td className={`px-3 py-2 text-center font-mono font-semibold ${
                            attSummary.rows.reduce((s, r) => s + (r.lop_days ?? 0), 0) > 0
                              ? 'text-rose-600' : 'text-slate-800'
                          }`}>
                            {attSummary.rows.reduce((s, r) => s + (r.lop_days ?? 0), 0)}
                          </td>
                          <td className="px-3 py-2 text-slate-600">Leave Management</td>
                          <td className="px-3 py-2 text-center text-slate-600">
                            {attSummary.rows.some(r => r.lop_status === 'reopen_required') ? 'Review' : 'Ready'}
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-slate-800">
                            {attSummary.rows.reduce((s, r) => s + (r.payable_days ?? 0), 0).toFixed(1)}
                          </td>
                          <td className="px-3 py-2 text-center text-slate-600">
                            {attSummary.rows.filter(r => r.validation_status === 'passed').length}
                            {' / '}
                            {attSummary.rows.length}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </details>
              )}

              {/* Inline notification */}
              {attNotification && (
                <div className={`flex items-start gap-2 rounded-lg p-3 mb-3 text-xs border ${
                  attNotification.type === 'success' ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : attNotification.type === 'warning' ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : 'bg-rose-50 text-rose-800 border-rose-200'
                }`}>
                  <span className="mt-0.5 flex-shrink-0">
                    {attNotification.type === 'success' ? '✓' : '⚠'}
                  </span>
                  <span>{attNotification.msg}</span>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                {/* No summary yet — wait for attendance/manual input; no dummy payroll input */}
                {attNoSummary && (
                  <span className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-500">
                    Attendance summary pending
                  </span>
                )}

                {/* Summary exists, not frozen — Validate + Freeze */}
                {!attNoSummary && !attIsFrozen && (
                  <>
                    <button
                      onClick={handleValidateSummary}
                      disabled={!!attActionLoading}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
                    >
                      {attActionLoading === 'validate' ? 'Validating…' : 'Validate Summary'}
                    </button>
                    <button
                      onClick={handleFreezeAttendance}
                      disabled={!!attActionLoading || !attCanFreeze || attHasMismatch}
                      className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 transition disabled:opacity-50"
                      title={
                        attHasMismatch ? 'Fix attendance day-count mismatches before freezing'
                        : !attCanFreeze ? 'Run Validate Summary first to unlock freeze'
                        : ''
                      }
                    >
                      {attActionLoading === 'freeze' ? 'Freezing…' : 'Freeze Payroll Input'}
                    </button>
                  </>
                )}

                {/* Frozen — confirmation message + DEV reset button */}
                {attIsFrozen && (
                  <>
                    <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                      <span>🔒</span>
                      <span>Payroll input frozen — payroll generation unlocked. Finance notified.</span>
                    </span>
                    {/* ── DEV ONLY ──────────────────────────────────────────────────────────
                        TEMPORARY FOR PAYROLL TESTING.
                        REMOVE AFTER REAL ATTENDANCE/TIMESHEET INTEGRATION.
                        ──────────────────────────────────────────────────────────────────── */}
                    <button
                      onClick={handleResetFreeze}
                      disabled={!!attActionLoading}
                      className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 transition disabled:opacity-50"
                      title="DEV ONLY — resets freeze for re-testing. Not available in production."
                    >
                      {attActionLoading === 'reset' ? 'Resetting…' : '🔧 Reset Payroll Input Freeze'}
                    </button>
                    <span className="text-xs text-rose-400 font-medium">[DEV ONLY]</span>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Payroll Input Status (Finance / Finance Head view) ────────────────── */}
      {/* Temporary payroll bridge until Attendance/Timesheet modules integrate. */}
      {['finance', 'finance_head'].includes((role || '').toLowerCase()) && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          {/* Card header */}
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Payroll Input Status — {attMonthLabel}
            </p>
            {attLoading ? (
              <div className="h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
            ) : (
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                attIsFrozen    ? 'bg-emerald-100 text-emerald-700'
                : attNoSummary ? 'bg-slate-100   text-slate-500'
                : attIsReady   ? 'bg-blue-100    text-blue-700'
                :                'bg-amber-100   text-amber-700'
              }`}>
                {attIsFrozen    ? '🔒 Frozen'
                 : attNoSummary ? '— Not Created'
                 : attIsReady   ? '✓ Ready'
                 :                '⚠ Partial'}
              </span>
            )}
          </div>

          {/* Status grid — read-only for finance */}
          {attLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-400 py-2">
              <div className="h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              Loading status…
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">Payroll Input Status</p>
                <p className={`font-semibold mt-0.5 ${
                  attIsFrozen    ? 'text-emerald-700'
                  : attNoSummary ? 'text-slate-400'
                  : attIsReady   ? 'text-blue-700'
                  :                'text-amber-700'
                }`}>
                  {attIsFrozen    ? 'Frozen'
                   : attNoSummary ? 'Not Created'
                   : attIsReady   ? 'Ready'
                   :                'Partial'}
                </p>
              </div>

              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">Attendance</p>
                <p className={`font-semibold mt-0.5 ${
                  attIsFrozen    ? 'text-emerald-700'
                  : attNoSummary ? 'text-slate-400'
                  :                'text-blue-700'
                }`}>
                  {attIsFrozen    ? 'Finalized'
                   : attNoSummary ? 'Not Created'
                   :                'Ready'}
                </p>
              </div>

              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">Timesheet</p>
                <p className={`font-semibold mt-0.5 ${
                  attNoSummary ? 'text-slate-400' : 'text-emerald-700'
                }`}>
                  {attNoSummary ? 'Not Created' : 'Ready'}
                </p>
              </div>

              {!attNoSummary && (
                <div className="bg-slate-50 rounded-lg p-3 md:col-span-3">
                  <p className="text-xs text-slate-500">Employees</p>
                  <p className="font-mono font-bold text-slate-800 mt-0.5">
                    {attIsFrozen
                      ? `${attTotalEmp} / ${attTotalEmp} — all finalized`
                      : `${attReadyCount} / ${attTotalEmp} ready`}
                  </p>
                </div>
              )}

              {attIsFrozen && (
                <div className="bg-emerald-50 rounded-lg p-3 md:col-span-3 flex items-center gap-2">
                  <span className="text-emerald-600 text-base">🔒</span>
                  <p className="text-xs font-medium text-emerald-800">
                    Payroll input frozen for {attMonthLabel}. Payroll is ready for processing.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Workflow Progress */}
      {run
        ? <WorkflowProgress status={runStatus} />
        : (attMonth && attYear) && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Payroll Workflow Progress
            </p>
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span>📋</span>
              No payroll run found for {attMonthLabel}. Finance can create one from{' '}
              <button
                onClick={() => navigate(`${FINANCE_BASE}/payroll-runs`)}
                className="text-brand-500 underline hover:text-brand-700"
              >
                Manage Payroll Runs
              </button>
              .
            </div>
          </div>
        )
      }

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Net Payroll (Last Run)"
          value={fmt(stats?.last_run_net)}
          sub="Previous cycle disbursed"
          accent="bg-emerald-50 text-emerald-600"
          icon="💰"
        />
        <StatCard
          label="Total Employees"
          value={stats?.total_active_employees ?? '—'}
          sub="Active on payroll"
          accent="bg-blue-50 text-blue-600"
          icon="👥"
        />
        <StatCard
          label="Open Errors"
          value={run?.open_errors ?? 0}
          sub={run?.open_errors > 0 ? 'Needs resolution' : 'All clear'}
          accent={run?.open_errors > 0 ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'}
          icon="🔍"
        />
        <StatCard
          label="Completion"
          value={`${run?.payroll_completion_pct ?? 0}%`}
          sub="Current run progress"
          accent="bg-brand-50 text-brand-600"
          icon="📊"
        />
      </div>

      {/* Current Run Summary */}
      {run && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-slate-700">Current Run: {run.month_label}</p>
            <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${
              runStatus === 'approved' || runStatus === 'disbursed' || runStatus === 'payslip_generated'
                ? 'bg-emerald-100 text-emerald-700'
                : runStatus === 'under_review'
                ? 'bg-blue-100 text-blue-700'
                : runStatus === 'pending_head_approval'
                ? 'bg-purple-100 text-purple-700'
                : runStatus === 'processing'
                ? 'bg-amber-100 text-amber-700'
                : runStatus === 'published' || runStatus === 'closed'
                ? 'bg-teal-100 text-teal-700'
                : 'bg-slate-100 text-slate-600'
            }`}>
              {runStatus === 'pending_head_approval'
                ? 'Pending Finance Head Approval'
                : runStatus === 'approved'
                ? 'Final Approved — Ready for Payslips'
                : runStatus.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {[
              { label: 'Employees', value: run.total_employees },
              { label: 'Gross Payroll', value: fmt(run.total_gross) },
              { label: 'Total Deductions', value: fmt(run.total_deductions) },
              { label: 'Net Payroll', value: fmt(run.total_net) },
            ].map((item) => (
              <div key={item.label} className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">{item.label}</p>
                <p className="font-mono font-bold text-slate-800 mt-0.5">{item.value}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
            {[
              { label: 'PF Total', value: fmt(run.total_pf), color: 'text-indigo-700' },
              { label: 'ESI Total', value: fmt(run.total_esi), color: 'text-purple-700' },
              { label: 'TDS Total', value: fmt(run.total_tds), color: 'text-rose-700' },
            ].map((item) => (
              <div key={item.label} className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">{item.label}</p>
                <p className={`font-mono font-semibold mt-0.5 ${item.color}`}>{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Department Summary */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <p className="text-sm font-semibold text-slate-700">Department-wise Payroll</p>
          <button
            onClick={() => navigate(`${FINANCE_BASE}/summary`)}
            className="text-xs text-brand-600 font-medium hover:underline"
          >
            Full summary →
          </button>
        </div>
        <div className="p-5">
          <DeptTable rows={stats?.department_summary} />
        </div>
      </div>

      {/* Quick Actions — role-based */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Quick Actions</p>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {/* Admin actions (shared items scoped to admin so finance order is unaffected) */}
          {(role || '').toLowerCase() === 'admin' && [
            { label: 'Salary Revision',     path: 'salary-revision',    icon: '✏️', color: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
            { label: 'Bonus Request',        path: 'bonus-requests',      icon: '🎁', color: 'bg-violet-50 text-violet-700 hover:bg-violet-100' },
            { label: 'Off-Cycle Payments',   path: 'off-cycle-payments',  icon: '💳', color: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
            { label: 'Salary Master',        path: 'salary-structures',   icon: '💼', color: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100' },
            { label: 'Reimbursements',       path: 'reimbursements',      icon: '💸', color: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
            { label: 'Final Settlement',    path: 'ff',                 icon: '📋', color: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
            { label: 'Payslips & ESS',      path: 'payslips',           icon: '📄', color: 'bg-teal-50 text-teal-700 hover:bg-teal-100' },
          ].map((a) => (
            <button key={a.path} onClick={() => navigate(`${FINANCE_BASE}/${a.path}`)}
              className={`flex items-center gap-2.5 rounded-lg px-4 py-3 text-sm font-medium transition ${a.color}`}>
              <span>{a.icon}</span><span>{a.label}</span>
            </button>
          ))}

          {/* Admin: Demo Reset button */}
          {(role || '').toLowerCase() === 'admin' && (
            <button
              onClick={handleDemoReset}
              disabled={demoResetBusy}
              className="flex items-center gap-2.5 rounded-lg px-4 py-3 text-sm font-medium transition bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50"
              title="Delete all payroll runs for May/June/July 2026 — demo cleanup"
            >
              <span>🔄</span>
              <span>{demoResetBusy ? 'Resetting…' : 'Demo Reset'}</span>
            </button>
          )}

          {/* Finance-specific actions — ordered to match sidebar */}
          {(role || '').toLowerCase() !== 'admin' && [
            { label: 'Salary Master',      path: 'salary-structures', icon: '💼', color: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100' },
            { label: 'Salary Revision',    path: 'salary-revision',   icon: '✏️', color: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
            { label: 'Bonus Request',        path: 'bonus-requests',      icon: '🎁', color: 'bg-violet-50 text-violet-700 hover:bg-violet-100' },
            { label: 'Off-Cycle Payments',  path: 'off-cycle-payments',  icon: '💳', color: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
            { label: 'Manage Payroll Runs', path: 'payroll-runs',        icon: '▶',  color: 'bg-brand-500 text-white hover:bg-brand-600' },
            { label: 'Finance Review',     path: 'review',            icon: '🔎', color: 'bg-purple-50 text-purple-700 hover:bg-purple-100' },
            { label: 'Payslips & Bank',    path: 'payslips',          icon: '🏦', color: 'bg-teal-50 text-teal-700 hover:bg-teal-100' },
            { label: 'Payroll Summary',    path: 'summary',           icon: '📊', color: 'bg-blue-50 text-blue-700 hover:bg-blue-100' },
            { label: 'Analytics',          path: 'analytics',         icon: '📈', color: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
            { label: 'Reimbursements',     path: 'reimbursements',    icon: '💸', color: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
            { label: 'Final Settlement',   path: 'ff',                icon: '📋', color: 'bg-slate-100 text-slate-700 hover:bg-slate-200' },
          ].map((a) => (
            <button key={a.path} onClick={() => navigate(`${FINANCE_BASE}/${a.path}`)}
              className={`flex items-center gap-2.5 rounded-lg px-4 py-3 text-sm font-medium transition ${a.color}`}>
              <span>{a.icon}</span><span>{a.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Demo reset result message */}
      {demoResetMsg && (
        <div className={`rounded-xl border p-4 text-sm ${demoResetMsg.startsWith('Reset failed') ? 'bg-rose-50 border-rose-200 text-rose-700' : 'bg-emerald-50 border-emerald-200 text-emerald-800'}`}>
          {demoResetMsg}
        </div>
      )}

      {/* Admin: HR-specific stats */}
      {(role || '').toLowerCase() === 'admin' && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">HR Setup Status</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Salary Master</p>
              <p className="font-mono font-bold text-slate-800 mt-0.5">{stats?.salary_structure_count ?? '—'}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Payroll Input Status</p>
              <p className={`font-bold mt-0.5 ${run?.attendance_frozen ? 'text-emerald-600' : 'text-amber-600'}`}>
                {run?.attendance_frozen ? '✓ Frozen' : 'Not Frozen'}
              </p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Finance Approval</p>
              <p className={`font-bold mt-0.5 ${run?.finance_head_approved ? 'text-emerald-600' : run?.finance_reviewed ? 'text-amber-600' : 'text-slate-400'}`}>
                {run?.finance_head_approved ? '✓ Approved' : run?.finance_reviewed ? 'Under Review' : 'Pending'}
              </p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">ESS Published</p>
              <p className={`font-bold mt-0.5 ${run?.payslips_published ? 'text-emerald-600' : 'text-slate-400'}`}>
                {run?.payslips_published ? '✓ Published' : 'Not Published'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Salary Revision Requests */}
      {hikeRequests.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-slate-700">Salary Revision Requests</p>
              {pendingHikeCount > 0 && (
                <span className="inline-flex items-center rounded-full bg-amber-100 text-amber-800 px-2.5 py-0.5 text-xs font-bold">
                  {pendingHikeCount} Pending
                </span>
              )}
            </div>
            <button
              onClick={() => navigate(`${FINANCE_BASE}/salary-revision`)}
              className="text-xs text-brand-600 font-medium hover:underline"
            >
              Manage salary revisions →
            </button>
          </div>
          <div className="divide-y divide-slate-50">
            {hikeRequests.slice(0, 8).map(req => (
              <div key={req.id} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-800 truncate">{req.employee_name || '—'}</p>
                    {req.employee_code && (
                      <span className="text-xs text-slate-400 font-mono">{req.employee_code}</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {req.old_ctc > 0 ? `₹${(req.old_ctc / 100000).toFixed(2)}L` : '—'}
                    {' → '}
                    <span className="text-emerald-700 font-medium">
                      ₹{(req.new_ctc / 100000).toFixed(2)}L
                    </span>
                    {' · Effective '}
                    {req.effective_from || '—'}
                    {req.hike_type === 'percentage'
                      ? ` · ${req.hike_value}% hike`
                      : ` · ₹${Number(req.hike_value).toLocaleString('en-IN')} fixed`
                    }
                  </p>
                  {req.reason && (
                    <p className="text-xs text-slate-400 truncate max-w-xs" title={req.reason}>{req.reason}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <HikeStatusBadge status={req.status} />
                  {(role || '').toLowerCase() === 'finance' && req.status === 'pending_finance_review' && (
                    <>
                      <button
                        onClick={() => handleApprove(req.id)}
                        disabled={reviewingId === req.id}
                        className="rounded bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 text-xs font-medium hover:bg-emerald-100 transition disabled:opacity-50"
                        title="Recommend approval to Finance Head"
                      >
                        {reviewingId === req.id ? '…' : 'Recommend Approval'}
                      </button>
                      <button
                        onClick={() => { setRejectingId(req.id); setRejectComment(''); }}
                        className="rounded bg-rose-50 text-rose-700 border border-rose-200 px-2.5 py-1 text-xs font-medium hover:bg-rose-100 transition"
                        title="Recommend rejection to Finance Head"
                      >
                        Recommend Rejection
                      </button>
                    </>
                  )}
                  {req.review_comment && (
                    <span
                      className="text-xs text-slate-400 max-w-[120px] truncate hidden md:block"
                      title={req.review_comment}
                    >
                      {req.review_comment}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
