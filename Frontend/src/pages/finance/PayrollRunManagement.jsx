import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const pad2 = (value) => String(value).padStart(2, '0');
const formatDateInput = (date) => (
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
);
const parseDateInput = (value) => {
  const [year, month, day] = (value || '').split('-').map(Number);
  return year && month && day ? new Date(year, month - 1, day) : null;
};
const derivePayrollFields = (payPeriodStart) => {
  const start = parseDateInput(payPeriodStart);
  if (!start) return { month_label: '', month: null, year: null };
  return {
    month_label: start.toLocaleString('en-IN', { month: 'long', year: 'numeric' }),
    month: start.getMonth() + 1,
    year: start.getFullYear(),
  };
};
const payrollMonthValue = (payPeriodStart) => (payPeriodStart || '').slice(0, 7);
const datesForPayrollMonth = (value) => {
  const [year, month] = (value || '').split('-').map(Number);
  if (!year || !month) return {};
  const pay_period_start = formatDateInput(new Date(year, month - 1, 1));
  const pay_period_end = formatDateInput(new Date(year, month, 0));
  return {
    pay_period_start,
    pay_period_end,
    ...derivePayrollFields(pay_period_start),
  };
};

const STATUS_META = {
  draft:                  { label: 'Draft',                  color: 'bg-slate-100 text-slate-600' },
  attendance_frozen:      { label: 'Attendance Frozen',      color: 'bg-blue-100 text-blue-700' },
  processing:             { label: 'Generated',              color: 'bg-amber-100 text-amber-700' },
  under_review:           { label: 'Under Review',           color: 'bg-purple-100 text-purple-700' },
  error_found:            { label: 'Error Found',            color: 'bg-rose-100 text-rose-700' },
  pending_head_approval:  { label: 'Pending Head Approval',  color: 'bg-orange-100 text-orange-700' },
  approved:               { label: 'Approved',               color: 'bg-emerald-100 text-emerald-700' },
  payslip_generated:      { label: 'Payslips Generated',     color: 'bg-teal-100 text-teal-700' },
  bank_advice_generated:  { label: 'Bank Advice Generated',  color: 'bg-teal-100 text-teal-600' },
  published:              { label: 'Published to ESS',       color: 'bg-cyan-100 text-cyan-700' },
  completed:              { label: 'Completed',              color: 'bg-slate-100 text-slate-500' },
  closed:                 { label: 'Closed',                 color: 'bg-slate-100 text-slate-500' },
  disbursed:              { label: 'Disbursed',              color: 'bg-teal-100 text-teal-700' },
  cancelled:              { label: 'Cancelled',              color: 'bg-rose-100 text-rose-700' },
};

// Actions available at each status. Only the primary workflow actions are here;
// error-flagging / error-resolution happen inside Manage Payroll Runs and Finance Review.
// All possible action descriptors — referenced by key in getActions().
const ALL_ACTIONS = {
  freeze_attendance: { action: 'freeze_attendance', label: 'Freeze Payroll Input',     variant: 'primary' },
  generate:          { action: 'generate',          label: 'Generate Payroll',         variant: 'primary' },
  submit_review:     { action: 'submit_review',     label: 'Submit to Finance Head',   variant: 'primary' },
  recompute:         { action: 'recompute',         label: 'Recompute',                variant: 'warning' },
  cancel:            { action: 'cancel',            label: 'Cancel',                   variant: 'danger'  },
  approve:           { action: 'approve',           label: 'Send to Finance Head',     variant: 'success' },
  reject:            { action: 'reject',            label: 'Reject',                   variant: 'danger'  },
  resolve_errors:    { action: 'resolve_errors',    label: 'Mark Resolved',            variant: 'success' },
  head_approve:      { action: 'head_approve',      label: 'Final Approve',            variant: 'success' },
  head_reject:       { action: 'head_reject',       label: 'Return for Revision',      variant: 'danger'  },
  generate_payslips: { action: 'generate_payslips', label: 'Generate Payslips',        variant: 'primary' },
  publish:           { action: 'publish',           label: 'Publish to ESS',           variant: 'primary' },
  close:             { action: 'close',             label: 'Close Payroll',            variant: 'success' },
};

function pick(...keys) { return keys.map((k) => ALL_ACTIONS[k]); }

// Role-gated action resolver — each status returns only the actions the
// calling role is permitted to execute at that workflow stage.
//
// Finance flow: draft/attendance_frozen → [Generate Payroll] → processing
//   → [Submit to Finance Head] → under_review → [Send to Finance Head]
//   → pending_head_approval → [Final Approve] → approved → [Generate Payslips]
//   → payslip_generated → [Publish to ESS] → completed
//
// "Freeze Payroll Input" is an HR responsibility and is hidden from Finance.
// Admin retains it for emergency use only.
function hasPayrollRecords(run) {
  return Number(run?.total_employees || 0) > 0
    && Number(run?.total_gross || 0) > 0
    && Number(run?.total_net || 0) > 0
    && Number(run?.open_errors || 0) === 0;
}

function getActions(status, role, run) {
  const r = (role || '').toLowerCase();
  // Finance team: can generate, review, compute, generate payslips, publish, close
  const isFinanceTeam = r === 'finance' || r === 'admin';
  // Finance Head: can only final-approve or return to Finance
  const isFinanceHead = r === 'finance_head';
  switch (status) {
    case 'draft':
      if (r === 'admin') return pick('generate', 'freeze_attendance', 'cancel');
      return isFinanceTeam ? pick('generate', 'cancel') : [];
    case 'attendance_frozen':
      if (r === 'admin') return pick('generate', 'freeze_attendance', 'cancel');
      return isFinanceTeam ? pick('generate', 'cancel') : [];
    case 'processing':
      return isFinanceTeam
        ? (hasPayrollRecords(run) ? pick('submit_review', 'recompute', 'cancel') : pick('recompute', 'cancel'))
        : [];
    case 'under_review':
      return isFinanceTeam ? pick('submit_review', 'recompute', 'reject') : [];
    case 'error_found':
      return isFinanceTeam ? pick('recompute', 'resolve_errors') : [];
    case 'pending_head_approval':
      // Only Finance Head (and admin fallback) may final-approve or return to Finance
      return (isFinanceHead || r === 'admin') ? pick('head_approve', 'head_reject') : [];
    case 'approved':
      return isFinanceTeam ? pick('generate_payslips') : [];
    case 'payslip_generated':
    case 'bank_advice_generated':
      return isFinanceTeam ? pick('publish') : [];
    case 'published':
    case 'completed':
      return isFinanceTeam ? pick('close') : [];
    default:
      return [];
  }
}

function fmt(n) {
  if (!n) return '₹0';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(2)}Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function Badge({ status }) {
  const meta = STATUS_META[status] || { label: status, color: 'bg-slate-100 text-slate-600' };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${meta.color}`}>
      {meta.label}
    </span>
  );
}

function ActionButton({ action, label, variant, onClick, loading }) {
  const cls = {
    primary: 'bg-brand-500 text-white hover:bg-brand-600',
    success: 'bg-emerald-500 text-white hover:bg-emerald-600',
    warning: 'bg-amber-500 text-white hover:bg-amber-600',
    danger:  'bg-rose-100 text-rose-700 hover:bg-rose-200',
  }[variant] || 'bg-slate-200 text-slate-700 hover:bg-slate-300';
  return (
    <button
      onClick={() => onClick(action)}
      disabled={loading}
      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${cls}`}
    >
      {loading ? '…' : label}
    </button>
  );
}

// ── Create Run Modal ───────────────────────────────────────────────────────────
function CreateRunModal({ onClose, onCreate }) {
  const today = new Date();
  const firstDay = formatDateInput(new Date(today.getFullYear(), today.getMonth(), 1));
  const lastDay  = formatDateInput(new Date(today.getFullYear(), today.getMonth() + 1, 0));

  const [form, setForm] = useState({
    pay_period_start: firstDay,
    pay_period_end:   lastDay,
    ...derivePayrollFields(firstDay),
    notes:            '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (!form.pay_period_start || !form.pay_period_end) { setErr('Pay period dates are required'); return; }
    if (form.pay_period_start > form.pay_period_end) { setErr('Period start must be before end'); return; }
    setBusy(true); setErr('');
    try {
      await onCreate({ ...form, ...derivePayrollFields(form.pay_period_start) });
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to create run');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-800">New Payroll Run</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg">✕</button>
        </div>
        {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Payroll Month</label>
            <input type="month"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={payrollMonthValue(form.pay_period_start)}
              onChange={(e) => setForm((f) => ({ ...f, ...datesForPayrollMonth(e.target.value) }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Period Start</label>
              <input type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.pay_period_start}
                onChange={(e) => setForm((f) => ({
                  ...f,
                  pay_period_start: e.target.value,
                  ...derivePayrollFields(e.target.value),
                }))} />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Period End</label>
              <input type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.pay_period_end}
                onChange={(e) => setForm((f) => ({
                  ...f,
                  pay_period_end: e.target.value,
                  ...derivePayrollFields(f.pay_period_start),
                }))} />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Notes (optional)</label>
            <textarea rows={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Any notes for this pay run…" />
          </div>
        </div>
        <p className="text-xs text-slate-400">Creating a new run does not affect existing closed payroll runs.</p>
        <div className="flex gap-3 justify-end pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={busy}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
            {busy ? 'Creating…' : 'Create Run'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Action Confirmation Modal (enterprise-style, action-aware) ─────────────────
function ActionConfirmModal({ action, run, onClose, onConfirm }) {
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);

  const na = <span className="text-slate-400 italic">—</span>;

  const CFG = {
    freeze_attendance: {
      title: 'Freeze Payroll Input',
      icon: '🔒', iconBg: 'bg-blue-50 text-blue-600',
      btnLabel: 'Freeze Payroll Input', btnCls: 'bg-brand-500 hover:bg-brand-600',
      requiresRemarks: false,
    },
    generate: {
      title: 'Generate Payroll',
      icon: '⚙️', iconBg: 'bg-amber-50 text-amber-700',
      btnLabel: 'Generate Payroll', btnCls: 'bg-amber-500 hover:bg-amber-600',
      requiresRemarks: false,
    },
    submit_review: {
      title: 'Submit to Finance Head',
      icon: '📋', iconBg: 'bg-purple-50 text-purple-600',
      btnLabel: 'Submit to Finance Head', btnCls: 'bg-brand-500 hover:bg-brand-600',
      requiresRemarks: false,
    },
    approve: {
      title: 'Send to Finance Head for Final Approval',
      icon: '✅', iconBg: 'bg-emerald-50 text-emerald-600',
      btnLabel: 'Send to Finance Head', btnCls: 'bg-emerald-500 hover:bg-emerald-600',
      requiresRemarks: false,
    },
    recompute: {
      title: 'Recompute Payroll',
      icon: '🔄', iconBg: 'bg-amber-50 text-amber-700',
      btnLabel: 'Recompute Payroll', btnCls: 'bg-amber-500 hover:bg-amber-600',
      requiresRemarks: true,
    },
    reject: {
      title: 'Reject & Return to Draft',
      icon: '↩️', iconBg: 'bg-rose-50 text-rose-600',
      btnLabel: 'Reject Run', btnCls: 'bg-rose-500 hover:bg-rose-600',
      requiresRemarks: true,
    },
    resolve_errors: {
      title: 'Mark Errors Resolved',
      icon: '✔️', iconBg: 'bg-emerald-50 text-emerald-600',
      btnLabel: 'Mark Resolved', btnCls: 'bg-emerald-500 hover:bg-emerald-600',
      requiresRemarks: true,
    },
    head_approve: {
      title: 'Finance Head — Final Approval',
      icon: '🏆', iconBg: 'bg-emerald-50 text-emerald-700',
      btnLabel: 'Final Approve', btnCls: 'bg-emerald-600 hover:bg-emerald-700',
      requiresRemarks: false,
    },
    head_reject: {
      title: 'Finance Head — Reject (Return to Review)',
      icon: '⛔', iconBg: 'bg-rose-50 text-rose-600',
      btnLabel: 'Reject & Return', btnCls: 'bg-rose-500 hover:bg-rose-600',
      requiresRemarks: true,
    },
    generate_payslips: {
      title: 'Generate Payslip Records',
      icon: '📄', iconBg: 'bg-teal-50 text-teal-600',
      btnLabel: 'Generate Payslips', btnCls: 'bg-teal-500 hover:bg-teal-600',
      requiresRemarks: false,
    },
    publish: {
      title: 'Publish Payslips to ESS',
      icon: '📢', iconBg: 'bg-cyan-50 text-cyan-600',
      btnLabel: 'Publish to ESS', btnCls: 'bg-cyan-500 hover:bg-cyan-600',
      requiresRemarks: false,
    },
    close: {
      title: 'Close Payroll Run',
      icon: '🔐', iconBg: 'bg-slate-50 text-slate-600',
      btnLabel: 'Close Payroll', btnCls: 'bg-slate-600 hover:bg-slate-700',
      requiresRemarks: false,
    },
    cancel: {
      title: 'Cancel Payroll Run',
      icon: '🗑', iconBg: 'bg-rose-50 text-rose-600',
      btnLabel: 'Cancel Run', btnCls: 'bg-rose-500 hover:bg-rose-600',
      requiresRemarks: true,
    },
  };

  const cfg = CFG[action] || {
    title: action.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    icon: '▶', iconBg: 'bg-slate-50 text-slate-600',
    btnLabel: 'Confirm', btnCls: 'bg-brand-500 hover:bg-brand-600',
    requiresRemarks: false,
  };

  function InfoRow({ label, value, mono, highlight }) {
    return (
      <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
        <span className="text-xs text-slate-500 flex-shrink-0 mr-3">{label}</span>
        <span className={`text-sm text-right ${highlight ? 'font-bold text-slate-800' : 'text-slate-700'} ${mono ? 'font-mono' : ''}`}>
          {value ?? na}
        </span>
      </div>
    );
  }

  function Strip({ color, icon, title, body }) {
    const palette = {
      amber:   'bg-amber-50 border-amber-200 text-amber-800',
      blue:    'bg-blue-50 border-blue-200 text-blue-800',
      emerald: 'bg-emerald-50 border-emerald-200 text-emerald-800',
      teal:    'bg-teal-50 border-teal-200 text-teal-800',
      slate:   'bg-slate-50 border-slate-200 text-slate-700',
      rose:    'bg-rose-50 border-rose-200 text-rose-800',
    };
    return (
      <div className={`rounded-lg border p-3 mt-3 ${palette[color] || palette.slate}`}>
        <p className="text-xs font-semibold flex items-center gap-1.5">{icon} {title}</p>
        {body && <p className="text-xs mt-1 opacity-90">{body}</p>}
      </div>
    );
  }

  function StatutoryBadges() {
    return (
      <div className="flex flex-wrap gap-2 mt-1">
        {['PF (Employee + Employer)', 'ESI', 'Professional Tax', 'TDS'].map((d) => (
          <span key={d} className="rounded-md bg-brand-50 border border-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">{d}</span>
        ))}
      </div>
    );
  }

  function ModalBody() {
    switch (action) {
      case 'freeze_attendance':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Pay Period" value={run?.pay_period_start && run?.pay_period_end ? `${run.pay_period_start} → ${run.pay_period_end}` : undefined} />
              <InfoRow label="Employees in Run" value={run?.total_employees || 'All active employees'} />
            </div>
            <Strip color="amber" icon="⚠" title="Attendance will be locked after this step"
              body="Once frozen, attendance records cannot be modified for this period. Ensure all attendance data is finalised before proceeding." />
          </>
        );

      case 'generate':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Attendance Status" value={<span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">✓ Frozen</span>} />
              <InfoRow label="Computation Scope" value="All active employees with salary structures" />
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 mt-3">
              <p className="text-xs font-semibold text-slate-700 mb-1">Statutory deductions included</p>
              <StatutoryBadges />
            </div>
            <Strip color="blue" icon="ℹ" title="LOP will be applied automatically"
              body="Loss of Pay days from attendance summaries will reduce gross pay proportionally." />
          </>
        );

      case 'submit_review':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Total Employees" value={run?.total_employees} />
              <InfoRow label="Gross Payroll" value={run?.total_gross != null ? fmt(run.total_gross) : undefined} mono highlight />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
              <InfoRow label="Total Deductions" value={run?.total_deductions != null ? fmt(run.total_deductions) : undefined} mono />
              <InfoRow label="PF Total" value={run?.total_pf != null ? fmt(run.total_pf) : undefined} mono />
              <InfoRow label="TDS Total" value={run?.total_tds != null ? fmt(run.total_tds) : undefined} mono />
            </div>
            <Strip color="blue" icon="ℹ" title="Payroll will be submitted for Finance Head review"
              body="After submission, Finance Head will review the payroll summary and give final approval before payslip generation." />
          </>
        );

      case 'approve':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Gross Payroll" value={run?.total_gross != null ? fmt(run.total_gross) : undefined} mono highlight />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
              <InfoRow label="Total Employees" value={run?.total_employees} />
              <InfoRow label="PF Total" value={run?.total_pf != null ? fmt(run.total_pf) : undefined} mono />
              <InfoRow label="ESI Total" value={run?.total_esi != null ? fmt(run.total_esi) : undefined} mono />
              <InfoRow label="TDS Total" value={run?.total_tds != null ? fmt(run.total_tds) : undefined} mono />
            </div>
            <Strip color="emerald" icon="✅" title="Sending to Finance Head for final approval"
              body="Approving forwards this run to the Finance Head for final authorization before payslip generation." />
          </>
        );

      case 'head_approve':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Gross Payroll" value={run?.total_gross != null ? fmt(run.total_gross) : undefined} mono highlight />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
              <InfoRow label="Total Employees" value={run?.total_employees} />
              <InfoRow label="PF + ESI" value={run?.total_pf != null && run?.total_esi != null ? fmt((run.total_pf || 0) + (run.total_esi || 0)) : undefined} mono />
              <InfoRow label="TDS" value={run?.total_tds != null ? fmt(run.total_tds) : undefined} mono />
            </div>
            <Strip color="emerald" icon="🏆" title="This is the final authorization"
              body="After Finance Head approval, payslips can be generated and published to employees. This action cannot be undone." />
          </>
        );

      case 'head_reject':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Current Status" value="Pending Head Approval" />
            </div>
            <Strip color="rose" icon="⛔" title="Run will return to Finance Review"
              body="Rejecting sends the run back to the Finance team for corrections. A rejection reason is required." />
          </>
        );

      case 'recompute':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Employees to Recompute" value={run?.total_employees} />
            </div>
            <Strip color="amber" icon="⚠" title="All payroll values will be recalculated"
              body="Gross pay, deductions, net pay, PF, ESI, PT, and TDS will be recomputed. Adjustments are retained and applied again." />
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 mt-2">
              <p className="text-xs text-slate-600">✓ Existing payroll rows are <strong>updated in-place</strong> — no duplicate entries.</p>
              <p className="text-xs text-slate-600 mt-1">✓ Approved reimbursements are <strong>not duplicated</strong> during recompute.</p>
            </div>
          </>
        );

      case 'resolve_errors':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Action" value="Mark all errors as resolved" />
            </div>
            <Strip color="emerald" icon="✔️" title="Run will return to Under Review status"
              body="Ensure all flagged errors in Finance Review have been addressed before marking as resolved." />
          </>
        );

      case 'generate_payslips':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Employees" value={run?.total_employees} />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
            </div>
            <Strip color="teal" icon="📄" title="Payslip records will be created"
              body="A payslip record is created for each employee. PDFs are generated on demand when downloaded." />
          </>
        );

      case 'publish':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Employees" value={run?.total_employees} />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
            </div>
            <Strip color="teal" icon="📢" title="Payslips will be visible to employees on ESS"
              body="Published payslips appear in each employee's self-service portal immediately." />
          </>
        );

      case 'close':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Net Disbursement" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
              <InfoRow label="Employees Paid" value={run?.total_employees} />
            </div>
            <Strip color="slate" icon="🔐" title="Payroll run will be permanently closed"
              body="Closing marks the payroll as complete and immutable. No further changes or recomputation will be possible." />
          </>
        );

      case 'cancel':
        return (
          <>
            <div className="divide-y divide-slate-50">
              <InfoRow label="Payroll Month" value={run?.month_label} />
              <InfoRow label="Current Status" value={STATUS_META[run?.status]?.label || run?.status} />
            </div>
            <Strip color="rose" icon="🗑" title="This payroll run will be cancelled"
              body="Cancelled runs cannot be resumed. You will need to create a new payroll run for this period." />
          </>
        );

      default:
        return (
          <div className="divide-y divide-slate-50">
            <InfoRow label="Action" value={action.replace(/_/g, ' ')} />
            <InfoRow label="Payroll Month" value={run?.month_label} />
          </div>
        );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className={`h-9 w-9 rounded-xl flex items-center justify-center text-lg ${cfg.iconBg}`}>{cfg.icon}</span>
            <div>
              <h2 className="text-base font-bold text-slate-800">{cfg.title}</h2>
              {run?.month_label && <p className="text-xs text-slate-400 mt-0.5">{run.month_label}</p>}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg ml-2">✕</button>
        </div>

        <div className="px-6 py-4 overflow-y-auto flex-1">
          <ModalBody />
          <div className="mt-4">
            <label className="block text-xs font-medium text-slate-600 mb-1">
              {cfg.requiresRemarks ? 'Reason / Remarks *' : 'Remarks (optional)'}
            </label>
            <textarea rows={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              placeholder={cfg.requiresRemarks ? 'Required — briefly describe the reason…' : 'Add any notes or remarks…'}
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)} />
            {cfg.requiresRemarks && !remarks.trim() && (
              <p className="text-xs text-rose-500 mt-1">A reason is required for this action.</p>
            )}
          </div>
        </div>

        <div className="flex gap-3 justify-end px-6 py-4 border-t border-slate-100 flex-shrink-0">
          <button onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 transition">
            Cancel
          </button>
          <button
            disabled={busy || (cfg.requiresRemarks && !remarks.trim())}
            onClick={async () => {
              setBusy(true);
              await onConfirm(remarks);
              setBusy(false);
            }}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-50 ${cfg.btnCls}`}
          >
            {busy ? 'Processing…' : cfg.btnLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Employee Payroll Breakdown Modal ──────────────────────────────────────────
function EmployeeBreakdownModal({ emp, run, onClose }) {
  if (!emp) return null;

  const na = <span className="text-slate-400">—</span>;

  const fmtINR = (val) =>
    val != null
      ? `₹${Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : '—';

  const fmtDays = (val) => (val != null ? Number(val).toFixed(1) : '—');

  // Full-month gross before LOP (annual_ctc / 12 is authoritative for CTC-only structures)
  const monthGross =
    emp.annual_ctc > 0
      ? Math.round((emp.annual_ctc / 12) * 100) / 100
      : (emp.gross_earnings || 0) + (emp.lop_deduction || 0);

  function Section({ icon, title, children, className }) {
    return (
      <div className={`rounded-xl border border-slate-200 bg-slate-50/40 p-4 space-y-2 ${className || ''}`}>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
          <span>{icon}</span>{title}
        </p>
        <div className="space-y-1.5">{children}</div>
      </div>
    );
  }

  function Row({ label, value, mono, bold, accent, borderTop }) {
    const valCls = [
      'text-xs text-right',
      bold ? 'font-bold' : 'font-medium',
      mono ? 'font-mono' : '',
      accent === 'green'  ? 'text-emerald-700'
        : accent === 'red'  ? 'text-rose-600'
        : accent === 'blue' ? 'text-blue-700'
        : 'text-slate-700',
    ].filter(Boolean).join(' ');
    return (
      <div className={`flex items-center justify-between gap-2 ${borderTop ? 'border-t border-slate-200 pt-2 mt-0.5' : ''}`}>
        <span className="text-xs text-slate-500 flex-shrink-0">{label}</span>
        <span className={valCls}>{value ?? na}</span>
      </div>
    );
  }

  const recStatus = (emp.record_status || 'COMPUTED').toUpperCase();
  const statusBadgeCls =
    recStatus === 'COMPUTED'  ? 'bg-emerald-100 text-emerald-700'
    : recStatus === 'ERROR'   ? 'bg-rose-100 text-rose-700'
    : 'bg-amber-100 text-amber-700';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-2xl flex flex-col max-h-[92vh]">

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600 font-bold text-sm flex-shrink-0 select-none">
              {(emp.employee_name || '?').slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800">{emp.employee_name}</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                {emp.employee_code}
                {emp.department  && ` · ${emp.department}`}
                {emp.designation && ` · ${emp.designation}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 ml-3">
            {run?.month_label && (
              <span className="rounded-full bg-brand-50 border border-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-700">
                {run.month_label}
              </span>
            )}
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none ml-1">✕</button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="px-6 py-4 overflow-y-auto flex-1 space-y-4">

          {/* Alerts */}
          {emp.has_error && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700 flex items-center gap-2">
              <span className="font-bold">⚠ Payroll Error</span>
              {emp.variance_reason && <span>— {emp.variance_reason}</span>}
            </div>
          )}
          {emp.variance_flag && !emp.has_error && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700 flex items-center gap-2">
              <span className="font-bold">⚡ Variance Flagged</span>
              {emp.variance_reason && <span>— {emp.variance_reason}</span>}
            </div>
          )}

          {/* CTC Information + Attendance side by side */}
          <div className="grid grid-cols-2 gap-3">
            <Section icon="💼" title="CTC Information">
              <Row label="Annual CTC"       value={fmtINR(emp.annual_ctc)} mono />
              <Row label="Monthly Gross"    value={fmtINR(monthGross)} mono />
              {(emp.lop_deduction || 0) > 0 && (
                <Row label="LOP Deduction" value={`−${fmtINR(emp.lop_deduction)}`} mono accent="red" />
              )}
              <Row label="Payable Gross" value={fmtINR(emp.gross_earnings || emp.gross_salary)}
                mono bold accent="blue" borderTop />
            </Section>

            <Section icon="📅" title="Attendance">
              <Row label="Working Days"  value={emp.total_working_days ?? emp.working_days} />
              <Row label="Present Days"  value={emp.present_days} />
              <Row label="Leave Days"    value={emp.leave_days ?? 0} />
              <Row label="LOP Days"      value={emp.lop_days || 0}
                accent={(emp.lop_days || 0) > 0 ? 'red' : ''} />
              <Row label="Payable Days"  value={fmtDays(emp.payable_days)} bold borderTop />
            </Section>
          </div>

          {/* Earnings */}
          <Section icon="💰" title="Earnings Breakdown">
            <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
              <Row label="Basic"                value={fmtINR(emp.basic_pay || emp.basic)} mono />
              <Row label="HRA"                  value={fmtINR(emp.hra)} mono />
              {(emp.da || 0) > 0 && (
                <Row label="Dearness Allowance" value={fmtINR(emp.da)} mono />
              )}
              {(emp.lta || 0) > 0 && (
                <Row label="LTA"                value={fmtINR(emp.lta)} mono />
              )}
              <Row label="Conveyance"           value={fmtINR(emp.conveyance)} mono />
              <Row label="Special Allowance"    value={fmtINR(emp.special_allowance)} mono />
              {(emp.bonus || 0) > 0 && (
                <Row label="Bonus"              value={fmtINR(emp.bonus)} mono accent="green" />
              )}
              {(emp.variable_pay || 0) > 0 && (
                <Row label="Variable Pay"       value={fmtINR(emp.variable_pay)} mono accent="green" />
              )}
              {(emp.overtime_amount || 0) > 0 && (
                <Row label="Overtime"           value={fmtINR(emp.overtime_amount)} mono accent="green" />
              )}
            </div>
            <Row label="Gross Earnings"
              value={fmtINR(emp.gross_earnings || emp.gross_salary)}
              mono bold accent="blue" borderTop />
          </Section>

          {/* Deductions + Employer Contributions side by side */}
          <div className="grid grid-cols-2 gap-3">
            <Section icon="📉" title="Deductions">
              <Row label="Employee PF"      value={`−${fmtINR(emp.employee_pf || emp.pf_employee)}`} mono accent="red" />
              <Row label="Employee ESI"     value={`−${fmtINR(emp.employee_esi || emp.esi_employee)}`} mono accent="red" />
              <Row label="Professional Tax" value={`−${fmtINR(emp.professional_tax)}`} mono accent="red" />
              <Row label="TDS"              value={`−${fmtINR(emp.tds)}`} mono accent="red" />
              {(emp.other_deductions || 0) > 0 && (
                <Row label="Other Deductions" value={`−${fmtINR(emp.other_deductions)}`} mono accent="red" />
              )}
              <Row label="Total Deductions"
                value={`−${fmtINR(emp.total_deductions)}`}
                mono bold accent="red" borderTop />
            </Section>

            <Section icon="🏢" title="Employer Contributions">
              <Row label="Employer PF"  value={fmtINR(emp.employer_pf || emp.pf_employer)} mono />
              <Row label="Employer ESI" value={fmtINR(emp.employer_esi || emp.esi_employer)} mono />
              <p className="text-[10px] text-slate-400 leading-relaxed pt-1">
                Part of CTC. Not deducted from employee take-home pay.
              </p>
            </Section>
          </div>

          {/* Net Pay */}
          <div className="rounded-xl border-2 border-emerald-200 bg-gradient-to-br from-emerald-50 to-white p-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Final Salary</p>
            <div className="space-y-1.5 mb-3">
              <Row label="Gross Earnings"       value={fmtINR(emp.gross_earnings)} mono />
              <Row label="(−) Total Deductions" value={`−${fmtINR(emp.total_deductions)}`} mono accent="red" />
            </div>
            <div className="border-t-2 border-emerald-300 pt-3 flex items-center justify-between">
              <span className="text-sm font-bold text-slate-800">Net Pay</span>
              <span className="text-2xl font-bold font-mono text-emerald-700">
                {fmtINR(emp.net_pay || emp.net_salary)}
              </span>
            </div>
          </div>

          {/* Validation */}
          <Section icon="✅" title="Validation & Status">
            <Row label="Attendance Source"   value="Monthly Attendance Summary (Frozen)" />
            <Row label="LOP Source"          value="Leave Management" />
            <Row label="Calculation Status"  value={
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusBadgeCls}`}>
                {emp.record_status || 'COMPUTED'}
              </span>
            } />
            <Row label="Errors"              value={
              emp.has_error
                ? <span className="font-semibold text-rose-600">⚠ Review Required</span>
                : <span className="text-emerald-600">✓ None</span>
            } />
            {emp.variance_flag && (
              <Row label="Variance" value={
                <span className="font-semibold text-amber-600">⚡ Flagged for review</span>
              } />
            )}
            {emp.salary_structure_id && (
              <Row label="Salary Structure" value={`SS-${emp.salary_structure_id}`} mono />
            )}
          </Section>

        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-slate-100 flex-shrink-0">
          <p className="text-[10px] text-slate-400">
            Values reflect the actual computed payroll for this period. Generated from frozen attendance data.
          </p>
          <button onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 transition ml-4 flex-shrink-0">
            Close
          </button>
        </div>

      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function PayrollRunManagement() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const FINANCE_BASE = (role || '').toLowerCase() === 'admin' ? '/admin-dashboard/payroll' : '/employee-dashboard/finance-payroll';
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runEmployees, setRunEmployees] = useState([]);
  const [empLoading, setEmpLoading] = useState(false);
  const [empError, setEmpError] = useState(null);
  const [selectedEmp, setSelectedEmp] = useState(null);

  const load = () => {
    setLoading(true);
    financeApi.listRuns()
      .then(setRuns)
      .catch((e) => setError(e?.data?.detail || e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (form) => {
    await financeApi.createRun(form);
    await load();
  };

  const handleAction = async (runId, action, remarks = '') => {
    setActionLoading(runId + action);
    try {
      await financeApi.runAction(runId, action, remarks);
      await load();
    } catch (e) {
      setError(e?.data?.detail || e.message || 'Action failed');
    } finally {
      setActionLoading(null);
      setPendingAction(null);
    }
  };

  async function loadEmployees(runId) {
    setSelectedRunId(runId);
    setEmpLoading(true);
    setEmpError(null);
    try {
      const data = await financeApi.getRunEmployees(runId);
      setRunEmployees(Array.isArray(data) ? data : []);
    } catch (e) {
      setEmpError(e?.data?.detail || 'Failed to load employee records');
      setRunEmployees([]);
    } finally {
      setEmpLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {showCreate && (
        <CreateRunModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}
      {pendingAction && (
        <ActionConfirmModal
          action={pendingAction.action}
          run={pendingAction.run}
          onClose={() => setPendingAction(null)}
          onConfirm={(remarks) => handleAction(pendingAction.runId, pendingAction.action, remarks)}
        />
      )}
      {selectedEmp && (
        <EmployeeBreakdownModal
          emp={selectedEmp}
          run={runs.find((r) => r.id === selectedRunId)}
          onClose={() => setSelectedEmp(null)}
        />
      )}

      {/* Back nav */}
      <button
        onClick={() => navigate(FINANCE_BASE)}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Dashboard
      </button>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Payroll Run Management</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage payroll cycles from initiation to disbursement</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 transition"
        >
          <span>+</span> New Run
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 p-4 text-rose-700 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-rose-400 hover:text-rose-600">✕</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : runs.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-slate-600 font-medium">No payroll runs yet</p>
          <p className="text-slate-400 text-sm mt-1">Create a new payroll run to get started</p>
          <button onClick={() => setShowCreate(true)}
            className="mt-4 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600">
            Create First Run
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const actions = getActions(run.status, role, run);
            const isReadOnly = ['completed', 'closed', 'cancelled'].includes(run.status);
            return (
              <div key={run.id} className={`bg-white rounded-xl border shadow-soft p-5 ${isReadOnly ? 'border-slate-100 opacity-80' : 'border-slate-200'}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-brand-50 flex items-center justify-center text-brand-600 font-bold text-sm">
                      {run.month_label?.slice(0, 3).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-slate-800">{run.month_label}</p>
                        <Badge status={run.status} />
                        {isReadOnly && <span className="text-xs text-slate-400">🔒</span>}
                      </div>
                      <p className="text-xs text-slate-400">{run.pay_period_start} → {run.pay_period_end}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-5 text-sm">
                    <div className="text-right">
                      <p className="text-xs text-slate-500">Employees</p>
                      <p className="font-bold text-slate-700">{run.total_employees ?? '—'}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-500">Gross</p>
                      <p className="font-mono font-bold text-slate-700">{fmt(run.total_gross)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-500">Net Pay</p>
                      <p className="font-mono font-bold text-emerald-700">{fmt(run.total_net)}</p>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {actions.map((act) => (
                        <ActionButton
                          key={act.action}
                          {...act}
                          loading={actionLoading === run.id + act.action}
                          onClick={(a) => setPendingAction({ runId: run.id, action: a, run })}
                        />
                      ))}
                      {isReadOnly && (
                        <span className="text-xs text-slate-400 italic py-1">Immutable</span>
                      )}
                      <button
                        onClick={() => loadEmployees(run.id)}
                        className="rounded-lg px-3 py-1.5 text-xs font-semibold transition bg-slate-200 text-slate-700 hover:bg-slate-300"
                      >
                        View Details
                      </button>
                    </div>
                  </div>
                </div>

                {/* Error/pending alerts inline */}
                {run.status === 'error_found' && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
                    <span>⚠</span>
                    <span>Errors flagged — go to <button onClick={() => navigate(`${FINANCE_BASE}/review`)} className="underline font-medium">Finance Review</button> to review and recompute after correction.</span>
                  </div>
                )}
                {run.status === 'pending_head_approval' && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-orange-50 border border-orange-200 px-3 py-2 text-xs text-orange-700">
                    <span>⏳</span>
                    <span>Awaiting Finance Head final authorization.</span>
                  </div>
                )}

                {/* Status-only message when no actions are available for this role */}
                {actions.length === 0 && !isReadOnly && ['under_review','pending_head_approval'].includes(run.status) && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700">
                    <span>ℹ</span>
                    <span>
                      {run.status === 'under_review'
                        ? 'Submitted for Finance review — awaiting Finance team action.'
                        : 'Pending Finance Head final authorization.'}
                    </span>
                  </div>
                )}

                {run.notes && (
                  <p className="mt-3 text-xs text-slate-400 border-t border-slate-100 pt-3">{run.notes}</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Employee Payroll Detail Panel */}
      {selectedRunId !== null && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-800">
              Employee Payroll Records — Run #{selectedRunId}
            </h2>
            <button
              onClick={() => { setSelectedRunId(null); setRunEmployees([]); }}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 transition"
            >
              Close
            </button>
          </div>

          {empLoading && (
            <div className="flex items-center justify-center h-24">
              <div className="h-7 w-7 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
            </div>
          )}

          {empError && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
              {empError}
            </div>
          )}

          {!empLoading && !empError && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap">Emp Code</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap">Employee Name</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap">Department</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">Annual CTC</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-center">Working Days</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-center">Payable Days</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-center">LOP Days</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">Gross Pay</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">LOP Deduction</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">PF</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">ESI</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">Prof Tax</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">TDS</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">Total Deductions</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap text-right">Net Pay</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap">Status</th>
                    <th className="px-3 py-2 font-semibold text-slate-600 whitespace-nowrap"></th>
                  </tr>
                </thead>
                <tbody>
                  {runEmployees.length === 0 ? (
                    <tr>
                      <td colSpan={17} className="px-3 py-8 text-center text-slate-400">
                        No employee records found for this run.
                        {' '}Click <strong>Generate Payroll</strong> to compute payroll for this period.
                      </td>
                    </tr>
                  ) : (
                    runEmployees.map((emp, idx) => {
                      const fmtCur = (val) =>
                        `₹${(val ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                      const recStatus = (emp.record_status || '').toUpperCase();
                      const statusCls = (() => {
                        if (emp.has_error) return 'bg-rose-100 text-rose-700';
                        if (['APPROVED', 'PROCESSED', 'COMPUTED'].includes(recStatus)) return 'bg-emerald-100 text-emerald-700';
                        if (['PENDING', 'DRAFT'].includes(recStatus)) return 'bg-amber-100 text-amber-700';
                        if (['ERROR', 'FAILED'].includes(recStatus)) return 'bg-rose-100 text-rose-700';
                        return 'bg-slate-100 text-slate-600';
                      })();
                      return (
                        <tr key={emp.id ?? idx} className={`border-b border-slate-100 hover:bg-slate-50 ${emp.has_error ? 'bg-rose-50' : emp.variance_flag ? 'bg-amber-50' : ''}`}>
                          <td className="px-3 py-2 font-mono text-slate-600 whitespace-nowrap">{emp.employee_code ?? '—'}</td>
                          <td className="px-3 py-2 font-medium text-slate-800 whitespace-nowrap">
                            <button
                              onClick={() => setSelectedEmp(emp)}
                              className="text-left hover:text-brand-600 hover:underline transition-colors"
                            >
                              {emp.employee_name ?? '—'}
                            </button>
                            {emp.has_error && (
                              <div className="mt-0.5 max-w-[260px] whitespace-normal text-[10px] font-semibold leading-snug text-rose-600">
                                error{emp.variance_reason ? ` - ${emp.variance_reason}` : ''}
                              </div>
                            )}
                            {emp.variance_flag && !emp.has_error && (
                              <span className="ml-1.5 text-[10px] text-amber-600 font-semibold">⚠ variance</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{emp.department ?? '—'}</td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.annual_ctc)}</td>
                          <td className="px-3 py-2 font-mono text-slate-600 whitespace-nowrap text-center">{emp.total_working_days ?? emp.working_days ?? '—'}</td>
                          <td className="px-3 py-2 font-mono text-slate-600 whitespace-nowrap text-center">{emp.payable_days != null ? Number(emp.payable_days).toFixed(1) : '—'}</td>
                          <td className={`px-3 py-2 font-mono whitespace-nowrap text-center font-semibold ${(emp.lop_days ?? 0) > 0 ? 'text-rose-600' : 'text-slate-600'}`}>
                            {emp.lop_days ?? 0}
                          </td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.gross_earnings ?? emp.gross_salary)}</td>
                          <td className={`px-3 py-2 font-mono whitespace-nowrap text-right ${(emp.lop_deduction ?? 0) > 0 ? 'text-rose-600' : 'text-slate-600'}`}>
                            {fmtCur(emp.lop_deduction)}
                          </td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.employee_pf ?? emp.pf_employee)}</td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.employee_esi ?? emp.esi_employee)}</td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.professional_tax)}</td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.tds)}</td>
                          <td className="px-3 py-2 font-mono text-slate-700 whitespace-nowrap text-right">{fmtCur(emp.total_deductions)}</td>
                          <td className="px-3 py-2 font-mono font-bold text-emerald-700 whitespace-nowrap text-right">{fmtCur(emp.net_pay ?? emp.net_salary)}</td>
                          <td className="px-3 py-2 whitespace-nowrap">
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusCls}`}>
                              {emp.has_error ? 'ERROR' : (emp.record_status ?? '—')}
                            </span>
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap">
                            <button
                              onClick={() => setSelectedEmp(emp)}
                              className="rounded px-2.5 py-1 text-[10px] font-semibold text-brand-600 bg-brand-50 hover:bg-brand-100 transition border border-brand-100"
                            >
                              Details
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
