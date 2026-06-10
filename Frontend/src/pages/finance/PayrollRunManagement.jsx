import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

const STATUS_META = {
  draft:                  { label: 'Draft',                  color: 'bg-slate-100 text-slate-600' },
  attendance_frozen:      { label: 'Attendance Frozen',      color: 'bg-blue-100 text-blue-700' },
  processing:             { label: 'Processing',             color: 'bg-amber-100 text-amber-700' },
  under_review:           { label: 'Under Review',           color: 'bg-purple-100 text-purple-700' },
  error_found:            { label: 'Error Found',            color: 'bg-rose-100 text-rose-700' },
  pending_head_approval:  { label: 'Pending Head Approval',  color: 'bg-orange-100 text-orange-700' },
  approved:               { label: 'Approved',               color: 'bg-emerald-100 text-emerald-700' },
  payslip_generated:      { label: 'Payslips Generated',     color: 'bg-teal-100 text-teal-700' },
  published:              { label: 'Published to ESS',       color: 'bg-cyan-100 text-cyan-700' },
  closed:                 { label: 'Closed',                 color: 'bg-slate-100 text-slate-500' },
  disbursed:              { label: 'Disbursed',              color: 'bg-teal-100 text-teal-700' },
  cancelled:              { label: 'Cancelled',              color: 'bg-rose-100 text-rose-700' },
};

// Actions available at each status. Only the primary workflow actions are here;
// error-flagging / error-resolution happen in dedicated pages (PayrollErrors, FinanceReview).
const ACTIONS = {
  draft: [
    { action: 'freeze_attendance', label: 'Freeze Attendance', variant: 'primary' },
    { action: 'cancel',            label: 'Cancel',            variant: 'danger' },
  ],
  attendance_frozen: [
    { action: 'generate', label: 'Generate Payroll', variant: 'primary' },
    { action: 'cancel',   label: 'Cancel',           variant: 'danger' },
  ],
  processing: [
    { action: 'submit_review', label: 'Submit for Review', variant: 'primary' },
    { action: 'recompute',     label: 'Recompute',         variant: 'warning' },
    { action: 'cancel',        label: 'Cancel',            variant: 'danger' },
  ],
  under_review: [
    { action: 'approve',   label: 'Approve',   variant: 'success' },
    { action: 'recompute', label: 'Recompute', variant: 'warning' },
    { action: 'reject',    label: 'Reject',    variant: 'danger' },
  ],
  error_found: [
    { action: 'recompute',      label: 'Recompute',      variant: 'warning' },
    { action: 'resolve_errors', label: 'Mark Resolved',  variant: 'success' },
  ],
  pending_head_approval: [
    { action: 'head_approve', label: 'Head Approve', variant: 'success' },
    { action: 'head_reject',  label: 'Head Reject',  variant: 'danger' },
  ],
  approved: [
    { action: 'generate_payslips', label: 'Generate Payslips', variant: 'primary' },
  ],
  payslip_generated: [
    { action: 'publish', label: 'Publish to ESS', variant: 'primary' },
  ],
  published: [
    { action: 'close', label: 'Close Payroll', variant: 'success' },
  ],
  closed:    [],
  disbursed: [],
  cancelled: [],
};

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
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
  const lastDay  = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().slice(0, 10);
  const monthLabel = today.toLocaleString('en-IN', { month: 'long', year: 'numeric' });

  const [form, setForm] = useState({
    pay_period_start: firstDay,
    pay_period_end:   lastDay,
    month_label:      monthLabel,
    notes:            '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (!form.month_label.trim()) { setErr('Month label is required'); return; }
    if (form.pay_period_start > form.pay_period_end) { setErr('Period start must be before end'); return; }
    setBusy(true); setErr('');
    try {
      await onCreate(form);
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
            <label className="block text-xs font-medium text-slate-600 mb-1">Month Label</label>
            <input
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={form.month_label}
              onChange={(e) => setForm((f) => ({ ...f, month_label: e.target.value }))}
              placeholder="e.g. May 2025"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Period Start</label>
              <input type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.pay_period_start}
                onChange={(e) => setForm((f) => ({ ...f, pay_period_start: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Period End</label>
              <input type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.pay_period_end}
                onChange={(e) => setForm((f) => ({ ...f, pay_period_end: e.target.value }))} />
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
      title: 'Freeze Attendance',
      icon: '🔒', iconBg: 'bg-blue-50 text-blue-600',
      btnLabel: 'Freeze Attendance', btnCls: 'bg-brand-500 hover:bg-brand-600',
      requiresRemarks: false,
    },
    generate: {
      title: 'Generate Payroll',
      icon: '⚙️', iconBg: 'bg-amber-50 text-amber-700',
      btnLabel: 'Generate Payroll', btnCls: 'bg-amber-500 hover:bg-amber-600',
      requiresRemarks: false,
    },
    submit_review: {
      title: 'Submit for Finance Review',
      icon: '📋', iconBg: 'bg-purple-50 text-purple-600',
      btnLabel: 'Submit for Review', btnCls: 'bg-brand-500 hover:bg-brand-600',
      requiresRemarks: false,
    },
    approve: {
      title: 'Approve — Send to Finance Head',
      icon: '✅', iconBg: 'bg-emerald-50 text-emerald-600',
      btnLabel: 'Approve Payroll', btnCls: 'bg-emerald-500 hover:bg-emerald-600',
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
              <InfoRow label="Gross Payroll" value={run?.total_gross != null ? fmt(run.total_gross) : undefined} mono highlight />
              <InfoRow label="Net Payroll" value={run?.total_net != null ? fmt(run.total_net) : undefined} mono highlight />
              <InfoRow label="Total Deductions" value={run?.total_deductions != null ? fmt(run.total_deductions) : undefined} mono />
              <InfoRow label="Total Employees" value={run?.total_employees} />
            </div>
            <Strip color="blue" icon="ℹ" title="Finance review will begin"
              body="The payroll run will be handed to Finance for review. They can flag errors, recompute, or approve for head authorization." />
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
              body="Ensure all flagged errors in the Payroll Errors page have been addressed before marking as resolved." />
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

  const load = () => {
    setLoading(true);
    financeApi.listRuns()
      .then(setRuns)
      .catch((e) => setError(e?.data?.detail || e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (form) => {
    const run = await financeApi.createRun(form);
    setRuns((prev) => [run, ...prev]);
  };

  const handleAction = async (runId, action, remarks = '') => {
    setActionLoading(runId + action);
    try {
      const updated = await financeApi.runAction(runId, action, remarks);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updated : r)));
    } catch (e) {
      setError(e?.data?.detail || e.message || 'Action failed');
    } finally {
      setActionLoading(null);
      setPendingAction(null);
    }
  };

  const WORKFLOW_STEPS = [
    'Initiate', '→', 'Freeze', '→', 'Generate',
    '→', 'Review', '→', 'Head Approval', '→',
    'Payslips', '→', 'Publish', '→', 'Close',
  ];

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

      {/* Workflow guide */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Enterprise Payroll Workflow</p>
        <div className="flex flex-wrap gap-2 text-xs">
          {WORKFLOW_STEPS.map((step, i) => (
            <span key={i} className={step === '→' ? 'text-slate-400' : 'rounded-md bg-slate-100 px-2 py-1 text-slate-600 font-medium'}>
              {step}
            </span>
          ))}
        </div>
      </div>

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
            const actions = ACTIONS[run.status] || [];
            const isReadOnly = ['closed', 'cancelled'].includes(run.status);
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
                    </div>
                  </div>
                </div>

                {/* Error/pending alerts inline */}
                {run.status === 'error_found' && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
                    <span>⚠</span>
                    <span>Errors flagged — go to <button onClick={() => navigate(`${FINANCE_BASE}/errors`)} className="underline font-medium">Payroll Errors</button> to review and resolve before recomputing.</span>
                  </div>
                )}
                {run.status === 'pending_head_approval' && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-orange-50 border border-orange-200 px-3 py-2 text-xs text-orange-700">
                    <span>⏳</span>
                    <span>Awaiting Finance Head final authorization.</span>
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
    </div>
  );
}
