/**
 * Finance Head Approval Page
 *
 * Role-based actions:
 *   Finance / Admin:
 *     - under_review  → "Send To Finance Head" (approve) | Recompute | Reject
 *     - approved      → Generate Payslips
 *     - payslip_generated → Publish to ESS
 *     - completed     → Finalized
 *
 *   Finance Head / Admin:
 *     - pending_head_approval → Final Approve | Return To Finance (head_reject)
 *
 * Finance Head CANNOT: Generate Payslips, Publish, Recompute.
 * Finance CANNOT: perform Final Approval actions.
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

function AuditEntry({ entry }) {
  const ACTION_COLORS = {
    initiate:         'bg-slate-100 text-slate-600',
    freeze_attendance:'bg-blue-100 text-blue-700',
    generate:         'bg-amber-100 text-amber-700',
    submit_review:    'bg-purple-100 text-purple-700',
    recompute:        'bg-orange-100 text-orange-700',
    approve:          'bg-emerald-100 text-emerald-700',
    reject:           'bg-rose-100 text-rose-700',
    disburse:         'bg-teal-100 text-teal-700',
    cancel:           'bg-gray-100 text-gray-600',
  };
  const cls = ACTION_COLORS[entry.action] || 'bg-slate-100 text-slate-600';
  return (
    <div className="flex items-start gap-3 py-3">
      <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold flex-shrink-0 mt-0.5 ${cls}`}>
        {entry.action.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-700">
          <span className="font-medium">{entry.actor_name}</span>
          {entry.from_status && (
            <span className="text-slate-400 text-xs ml-2">{entry.from_status} → {entry.to_status}</span>
          )}
        </p>
        {entry.remarks && <p className="text-xs text-slate-500 mt-0.5">"{entry.remarks}"</p>}
        <p className="text-xs text-slate-400 mt-0.5">
          {new Date(entry.created_at).toLocaleString('en-IN', {
            day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
          })}
        </p>
      </div>
    </div>
  );
}

function ConfirmModal({ title, message, variant, actionLabel = 'Confirm', requireRemarks = false, onConfirm, onClose }) {
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const remarksMissing = requireRemarks && !remarks.trim();
  const btnCls = variant === 'danger'
    ? 'bg-rose-500 hover:bg-rose-600'
    : variant === 'success'
    ? 'bg-emerald-500 hover:bg-emerald-600'
    : 'bg-brand-500 hover:bg-brand-600';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
        <h2 className="text-base font-bold text-slate-800">{title}</h2>
        <p className="text-sm text-slate-500">{message}</p>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Remarks{requireRemarks ? ' *' : ''}
          </label>
          <textarea
            rows={3}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
          />
          {remarksMissing && <p className="mt-1 text-xs text-rose-500">A reason is required.</p>}
        </div>
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button
            disabled={busy || remarksMissing}
            onClick={async () => { setBusy(true); await onConfirm(remarks.trim()); setBusy(false); }}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-50 ${btnCls}`}
          >
            {busy ? '...' : actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function PayrollBreakdownModal({ employee, run, onClose }) {
  if (!employee) return null;

  const money = (value) =>
    value != null
      ? `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : '—';
  const days = (value) => (value != null ? Number(value).toFixed(1) : '—');
  const hasValue = (value) => Number(value || 0) !== 0;
  const otherEarnings = [
    ['Bonus', employee.bonus ?? employee.bonus_total],
    ['Variable Pay', employee.variable_pay ?? employee.variable_pay_total],
    ['Overtime', employee.overtime_amount],
    ['Arrears', employee.arrears_total],
  ].filter(([, value]) => hasValue(value));

  function Section({ title, children }) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-4">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">{title}</p>
        <div className="space-y-2">{children}</div>
      </div>
    );
  }

  function Row({ label, value, mono, strong, accent }) {
    const valueCls = [
      'text-xs text-right',
      mono ? 'font-mono' : 'font-medium',
      strong ? 'font-bold' : '',
      accent === 'green' ? 'text-emerald-700'
        : accent === 'red' ? 'text-rose-600'
        : 'text-slate-700',
    ].filter(Boolean).join(' ');
    return (
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-slate-500">{label}</span>
        <span className={valueCls}>{value ?? '—'}</span>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-800">Payroll Breakdown</h2>
            <p className="mt-0.5 text-xs text-slate-400">
              {employee.employee_code || '—'} · {employee.employee_name || '—'}
              {run?.month_label ? ` · ${run.month_label}` : ''}
            </p>
          </div>
          <button onClick={onClose} className="text-xl leading-none text-slate-400 hover:text-slate-600">×</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="grid gap-3 md:grid-cols-2">
            <Section title="Employee Information">
              <Row label="Employee Code" value={employee.employee_code} />
              <Row label="Employee Name" value={employee.employee_name} />
              <Row label="Department" value={employee.department} />
              <Row label="Designation" value={employee.designation} />
            </Section>

            <Section title="CTC Information">
              <Row label="Annual CTC" value={money(employee.annual_ctc)} mono strong />
              <Row label="Monthly Gross" value={money(employee.gross_salary ?? employee.gross_earnings)} mono />
            </Section>

            <Section title="Earnings Breakdown">
              <Row label="Basic" value={money(employee.basic_pay ?? employee.basic)} mono />
              <Row label="HRA" value={money(employee.hra)} mono />
              <Row label="LTA" value={money(employee.lta)} mono />
              <Row label="Conveyance" value={money(employee.conveyance)} mono />
              <Row label="Special Allowance" value={money(employee.special_allowance ?? employee.allowances)} mono />
              {otherEarnings.length > 0 && (
                <div className="mt-2 space-y-2 border-t border-slate-200 pt-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Other Earnings</p>
                  {otherEarnings.map(([label, value]) => (
                    <Row key={label} label={label} value={money(value)} mono accent="green" />
                  ))}
                </div>
              )}
            </Section>

            <Section title="Attendance Breakdown">
              <Row label="Working Days" value={days(employee.total_working_days ?? employee.working_days)} />
              <Row label="Present Days" value={days(employee.present_days)} />
              <Row label="Leave Days" value={days(employee.leave_days)} />
              <Row label="LOP Days" value={days(employee.lop_days)} />
              <Row label="Payable Days" value={days(employee.payable_days)} strong />
            </Section>

            <Section title="Deductions">
              <Row label="Employee PF" value={money(employee.employee_pf ?? employee.pf_employee)} mono accent="red" />
              <Row label="Employee ESI" value={money(employee.employee_esi ?? employee.esi_employee)} mono accent="red" />
              <Row label="Professional Tax" value={money(employee.professional_tax)} mono accent="red" />
              <Row label="TDS" value={money(employee.tds)} mono accent="red" />
              <Row label="LOP Deduction" value={money(employee.lop_deduction)} mono accent="red" />
              <Row label="Other Deductions" value={money(employee.other_deductions)} mono accent="red" />
            </Section>

            <Section title="Employer Contributions">
              <Row label="Employer PF" value={money(employee.employer_pf ?? employee.pf_employer)} mono />
              <Row label="Employer ESI" value={money(employee.employer_esi ?? employee.esi_employer)} mono />
            </Section>
          </div>

          <div className="mt-3 rounded-xl border-2 border-emerald-200 bg-emerald-50/60 p-4">
            <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Final Payroll Summary</p>
            <div className="grid gap-3 md:grid-cols-3">
              <Row label="Gross Earnings" value={money(employee.gross_earnings ?? employee.gross_salary)} mono strong />
              <Row label="Total Deductions" value={money(employee.total_deductions)} mono strong accent="red" />
              <Row label="Net Pay" value={money(employee.net_pay ?? employee.net_salary)} mono strong accent="green" />
            </div>
          </div>
        </div>

        <div className="flex justify-end border-t border-slate-100 px-6 py-3">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default function FinalApproval() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [run, setRun] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [modal, setModal] = useState(null);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [toast, setToast] = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  useEffect(() => {
    financeApi.listRuns()
      .then((data) => {
        setRuns(data);
        const active = data.find((r) =>
          ['under_review', 'error_found', 'pending_head_approval', 'approved', 'processing'].includes(r.status)
        );
        setSelectedId((active || data[0])?.id);
      })
      .finally(() => setLoading(false));
  }, []);

  const loadDetails = (id) => {
    if (!id) return;
    setSelectedEmployee(null);
    setLoadingDetails(true);
    Promise.all([
      financeApi.getRun(id),
      financeApi.getRunApprovals(id),
      financeApi.getRunEmployees(id),
    ])
      .then(([r, a, e]) => { setRun(r); setApprovals(a); setEmployees(e || []); })
      .finally(() => setLoadingDetails(false));
  };

  useEffect(() => { loadDetails(selectedId); }, [selectedId]);

  const openErrors = Number(
    run?.open_errors ?? run?.open_error_count ?? employees.filter((emp) => emp.has_error).length ?? 0
  );
  const financeReviewed = Boolean(
    run?.finance_reviewed
    ?? ['approved', 'payslip_generated', 'published', 'completed', 'closed', 'disbursed'].includes(run?.status)
  );
  const canFinalApprove = Boolean(
    run?.status === 'pending_head_approval' && financeReviewed && openErrors === 0
  );
  const finalApprovalBlockReason = !run
    ? ''
    : run.status !== 'pending_head_approval'
    ? 'Run must be Pending Finance Head Approval.'
    : !financeReviewed
    ? 'Finance review must be completed before final approval.'
    : openErrors > 0
    ? `Resolve ${openErrors} open payroll error(s) before final approval.`
    : '';

  const doAction = async (action, remarks) => {
    try {
      const cleanRemarks = (remarks || '').trim();
      if (action === 'head_reject' && !cleanRemarks) {
        showToast('A reason is required to return payroll to Finance');
        return;
      }
      if ((action === 'head_approve' || action === 'finance_head_approve') && !canFinalApprove) {
        showToast(finalApprovalBlockReason || 'Final approval is not available for this run');
        return;
      }
      await financeApi.runAction(run.id, action, cleanRemarks);
      showToast(`${action.replace(/_/g, ' ')} successful`);
      loadDetails(selectedId);
      setModal(null);
    } catch (e) {
      showToast(e?.data?.detail || e.message || 'Action failed');
      setModal(null);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-800 text-white text-sm rounded-xl px-4 py-3 shadow-xl">
          {toast}
        </div>
      )}
      {modal && (
        <ConfirmModal
          {...modal}
          onClose={() => setModal(null)}
          onConfirm={(r) => doAction(modal.action, r)}
        />
      )}
      {selectedEmployee && (
        <PayrollBreakdownModal
          employee={selectedEmployee}
          run={run}
          onClose={() => setSelectedEmployee(null)}
        />
      )}

      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          if (role_ === 'admin') {
            navigate('/admin-dashboard/payroll');
          } else if (role_ === 'finance_head' || role_ === 'financehead') {
            navigate('/employee-dashboard/finance-head-payroll');
          } else {
            navigate('/employee-dashboard/finance-payroll');
          }
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Finance Head Approval</h1>
          <p className="text-sm text-slate-500 mt-0.5">Role-based payroll approval and payslip distribution</p>
        </div>
        <select
          value={selectedId || ''}
          onChange={(e) => setSelectedId(Number(e.target.value))}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="" disabled>Select run…</option>
          {runs.map((r) => <option key={r.id} value={r.id}>{r.month_label}</option>)}
        </select>
      </div>

      {loadingDetails ? (
        <div className="flex items-center justify-center h-32">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : run ? (
        <>
          {/* Run overview */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-soft">
            <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
              <div>
                <h2 className="text-lg font-bold text-slate-800">{run.month_label}</h2>
                <p className="text-xs text-slate-400 mt-0.5">{run.pay_period_start} → {run.pay_period_end}</p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                run.status === 'approved' || run.status === 'disbursed' || run.status === 'payslip_generated'
                  ? 'bg-emerald-100 text-emerald-700'
                  : run.status === 'under_review'
                  ? 'bg-blue-100 text-blue-700'
                  : run.status === 'pending_head_approval'
                  ? 'bg-purple-100 text-purple-700'
                  : run.status === 'published' || run.status === 'closed'
                  ? 'bg-teal-100 text-teal-700'
                  : 'bg-slate-100 text-slate-600'
              }`}>
                {run.status === 'pending_head_approval'
                  ? 'Pending Finance Head Approval'
                  : run.status === 'approved'
                  ? 'Final Approved — Ready for Payslips'
                  : run.status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </span>
            </div>

            {/* Payroll summary */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-5">
              {[
                { label: 'Payroll Month',    value: run.month_label },
                { label: 'Employee Count',   value: run.total_employees },
                { label: 'Gross Payroll',    value: fmt(run.total_gross) },
                { label: 'Total Deductions', value: fmt(run.total_deductions) },
                { label: 'Net Payroll',      value: fmt(run.total_net) },
              ].map((item) => (
                <div key={item.label} className="bg-slate-50 rounded-xl p-4 text-center">
                  <p className="text-xs text-slate-500">{item.label}</p>
                  <p className="font-mono font-bold text-lg text-slate-800 mt-1">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              {[
                { label: 'Total PF',  value: fmt(run.total_pf),  color: 'text-indigo-700' },
                { label: 'Total ESI', value: fmt(run.total_esi), color: 'text-purple-700' },
                { label: 'Total TDS', value: fmt(run.total_tds), color: 'text-rose-700' },
                { label: 'Finance Reviewed', value: financeReviewed ? 'Yes' : 'No', color: financeReviewed ? 'text-emerald-700' : 'text-amber-700' },
                { label: 'Open Errors', value: openErrors, color: openErrors === 0 ? 'text-emerald-700' : 'text-rose-700' },
              ].map((item) => (
                <div key={item.label} className="bg-slate-50 rounded-xl p-4 text-center">
                  <p className="text-xs text-slate-500">{item.label}</p>
                  <p className={`font-mono font-bold text-lg mt-1 ${item.color}`}>{item.value}</p>
                </div>
              ))}
            </div>

            {/* Employee-wise payroll records */}
            <div className="mb-6">
              <div className="mb-3 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Employee Payroll Records</p>
                <span className="text-xs text-slate-400">{employees.length} record(s)</span>
              </div>
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="min-w-[1380px] w-full text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-3 py-3 text-left font-semibold">Employee Code</th>
                      <th className="px-3 py-3 text-left font-semibold">Employee Name</th>
                      <th className="px-3 py-3 text-left font-semibold">Department</th>
                      <th className="px-3 py-3 text-right font-semibold">Annual CTC</th>
                      <th className="px-3 py-3 text-right font-semibold">LOP Days</th>
                      <th className="px-3 py-3 text-right font-semibold">Gross Pay</th>
                      <th className="px-3 py-3 text-right font-semibold">LOP Deduction</th>
                      <th className="px-3 py-3 text-right font-semibold">PF</th>
                      <th className="px-3 py-3 text-right font-semibold">ESI</th>
                      <th className="px-3 py-3 text-right font-semibold">Prof Tax</th>
                      <th className="px-3 py-3 text-right font-semibold">TDS</th>
                      <th className="px-3 py-3 text-right font-semibold">Total Deductions</th>
                      <th className="px-3 py-3 text-right font-semibold">Net Pay</th>
                      <th className="px-3 py-3 text-left font-semibold">Status</th>
                      <th className="px-3 py-3 text-left font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {employees.length === 0 ? (
                      <tr>
                        <td colSpan={15} className="px-3 py-6 text-center text-slate-400">
                          No employee payroll records found for this run
                        </td>
                      </tr>
                    ) : employees.map((emp) => {
                      const recStatus = (emp.record_status || 'COMPUTED').toUpperCase();
                      const statusCls =
                        recStatus === 'COMPUTED' ? 'bg-emerald-100 text-emerald-700'
                        : recStatus === 'ERROR' || recStatus === 'FAILED' ? 'bg-rose-100 text-rose-700'
                        : 'bg-amber-100 text-amber-700';
                      return (
                        <tr key={emp.id} className={emp.has_error ? 'bg-rose-50/60' : 'hover:bg-slate-50/60'}>
                          <td className="px-3 py-3 font-mono text-xs text-slate-600 whitespace-nowrap">{emp.employee_code || '—'}</td>
                          <td className="px-3 py-3 font-medium text-slate-800 whitespace-nowrap">{emp.employee_name || '—'}</td>
                          <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{emp.department || '—'}</td>
                          <td className="px-3 py-3 text-right font-mono text-slate-700 whitespace-nowrap font-semibold">
                            {fmt(emp.annual_ctc)}
                          </td>
                          <td className={`px-3 py-3 text-right font-mono whitespace-nowrap font-semibold ${(emp.lop_days ?? 0) > 0 ? 'text-rose-600' : 'text-slate-500'}`}>
                            {emp.lop_days ?? 0}
                          </td>
                          <td className="px-3 py-3 text-right font-mono text-slate-700 whitespace-nowrap">{fmt(emp.gross_earnings ?? emp.gross_salary)}</td>
                          <td className={`px-3 py-3 text-right font-mono whitespace-nowrap ${(emp.lop_deduction ?? 0) > 0 ? 'text-rose-600' : 'text-slate-500'}`}>
                            {fmt(emp.lop_deduction)}
                          </td>
                          <td className="px-3 py-3 text-right font-mono text-slate-600 whitespace-nowrap">{fmt(emp.employee_pf ?? emp.pf_employee)}</td>
                          <td className="px-3 py-3 text-right font-mono text-slate-600 whitespace-nowrap">{fmt(emp.employee_esi ?? emp.esi_employee)}</td>
                          <td className="px-3 py-3 text-right font-mono text-slate-600 whitespace-nowrap">{fmt(emp.professional_tax)}</td>
                          <td className="px-3 py-3 text-right font-mono text-slate-600 whitespace-nowrap">{fmt(emp.tds)}</td>
                          <td className="px-3 py-3 text-right font-mono text-slate-700 whitespace-nowrap">{fmt(emp.total_deductions)}</td>
                          <td className="px-3 py-3 text-right font-mono font-bold text-emerald-700 whitespace-nowrap">{fmt(emp.net_pay ?? emp.net_salary)}</td>
                          <td className="px-3 py-3 whitespace-nowrap">
                            <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${statusCls}`}>
                              {emp.record_status || 'COMPUTED'}
                            </span>
                          </td>
                          <td className="px-3 py-3 whitespace-nowrap">
                            <button
                              onClick={() => setSelectedEmployee(emp)}
                              className="rounded-lg border border-brand-100 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-600 hover:bg-brand-100 transition"
                            >
                              View Details
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Action buttons - role-based visibility */}
            <div className="border-t border-slate-100 pt-5">
              {(() => {
                const r = (role || '').toLowerCase();
                const isFinanceHead = r === 'finance_head' || r === 'financehead';
                const isFinance = r === 'finance' || r === 'admin';

                return (
                  <>
                    {/* ── Finance / Admin actions ── */}
                    {isFinance && (
                      <>
                        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Finance Actions</p>
                        <div className="flex gap-3 flex-wrap mb-4">

                          {/* Finance: Send To Finance Head (from under_review) */}
                          {run.status === 'under_review' && (
                            <>
                              <button
                                onClick={() => setModal({
                                  title: 'Send To Finance Head',
                                  message: `Send the ${run.month_label} payroll (${fmt(run.total_net)}) to the Finance Head for final approval.`,
                                  variant: 'success',
                                  action: 'approve',
                                })}
                                className="flex items-center gap-2 rounded-lg bg-brand-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 transition"
                              >
                                ✓ Send To Finance Head
                              </button>
                              <button
                                onClick={() => setModal({
                                  title: 'Recompute Payroll',
                                  message: 'Push the run back to processing for recomputation.',
                                  variant: 'warning',
                                  action: 'recompute',
                                })}
                                className="flex items-center gap-2 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-600 transition"
                              >
                                ↺ Recompute
                              </button>
                              <button
                                onClick={() => setModal({
                                  title: 'Reject Payroll Run',
                                  message: 'Reset this run to Draft. Please provide a reason.',
                                  variant: 'danger',
                                  action: 'reject',
                                  requireRemarks: true,
                                })}
                                className="flex items-center gap-2 rounded-lg bg-rose-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-rose-600 transition"
                              >
                                ✗ Reject
                              </button>
                            </>
                          )}

                          {/* Finance: waiting on Finance Head */}
                          {run.status === 'pending_head_approval' && (
                            <div className="flex items-center gap-2 rounded-lg bg-purple-50 border border-purple-200 px-5 py-2.5 text-sm font-semibold text-purple-700">
                              ⏳ Awaiting Finance Head Final Approval
                            </div>
                          )}

                          {/* Finance: Generate Payslips — only after Finance Head approved */}
                          {run.status === 'approved' && (
                            <button
                              onClick={() => setModal({
                                title: 'Generate Payslips',
                                message: `Generate payslip records for all ${run.total_employees} employees in this run.`,
                                variant: 'success',
                                action: 'generate_payslips',
                              })}
                              className="flex items-center gap-2 rounded-lg bg-teal-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-600 transition"
                            >
                              📄 Generate Payslips
                            </button>
                          )}

                          {/* Finance: Publish to ESS */}
                          {run.status === 'payslip_generated' && (
                            <button
                              onClick={() => setModal({
                                title: 'Publish to ESS Portal',
                                message: 'Publish all payslips to the Employee Self-Service portal. Employees will be notified.',
                                variant: 'success',
                                action: 'publish',
                              })}
                              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 transition"
                            >
                              🚀 Publish to ESS
                            </button>
                          )}

                          {/* Finance: Complete Run */}
                          {(run.status === 'published' || run.status === 'completed') && (
                            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-2.5 text-sm font-semibold text-emerald-700">
                              ✓ Payroll run complete
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {/* ── Finance Head actions ── */}
                    {isFinanceHead && (
                      <>
                        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Finance Head Actions</p>
                        <div className="flex gap-3 flex-wrap mb-4">

                          {/* Finance Head: Final Approval */}
                          {run.status === 'pending_head_approval' && (
                            <>
                              <button
                                disabled={!canFinalApprove}
                                title={!canFinalApprove ? finalApprovalBlockReason : undefined}
                                onClick={() => {
                                  if (!canFinalApprove) {
                                    showToast(finalApprovalBlockReason || 'Final approval is not available for this run');
                                    return;
                                  }
                                  setModal({
                                    title: 'Finance Head Final Approval',
                                    message: `You are about to give final approval for the ${run.month_label} payroll of ${fmt(run.total_net)} for ${run.total_employees} employees. This action locks payroll permanently.`,
                                    variant: 'success',
                                    action: 'head_approve',
                                    actionLabel: 'Final Approve',
                                  });
                                }}
                                className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition ${
                                  canFinalApprove
                                    ? 'bg-emerald-500 hover:bg-emerald-600'
                                    : 'bg-slate-300 cursor-not-allowed'
                                }`}
                              >
                                ✓ Final Approve
                              </button>
                              <button
                                onClick={() => setModal({
                                  title: 'Return To Finance',
                                  message: 'Return this payroll run to Finance for review. Please provide a reason.',
                                  variant: 'danger',
                                  action: 'head_reject',
                                  requireRemarks: true,
                                })}
                                className="flex items-center gap-2 rounded-lg bg-rose-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-rose-600 transition"
                              >
                                ↩ Return To Finance
                              </button>
                            </>
                          )}

                          {run.status === 'pending_head_approval' && !canFinalApprove && finalApprovalBlockReason && (
                            <p className="basis-full text-xs font-medium text-rose-600">
                              {finalApprovalBlockReason}
                            </p>
                          )}

                          {/* Finance Head: informational states */}
                          {run.status === 'under_review' && (
                            <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-5 py-2.5 text-sm font-semibold text-blue-700">
                              ℹ Finance is reviewing payroll — awaiting submission
                            </div>
                          )}
                          {run.status === 'approved' && (
                            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-2.5 text-sm font-semibold text-emerald-700">
                              ✓ Final Approved — Finance is generating payslips
                            </div>
                          )}
                          {run.status === 'payslip_generated' && (
                            <div className="flex items-center gap-2 rounded-lg bg-teal-50 border border-teal-200 px-5 py-2.5 text-sm font-semibold text-teal-700">
                              📄 Payslips generated — Finance will publish shortly
                            </div>
                          )}
                          {(run.status === 'published' || run.status === 'completed' || run.status === 'closed') && (
                            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-2.5 text-sm font-semibold text-emerald-700">
                              ✓ Payroll cycle complete
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {/* Shared terminal states */}
                    {run.status === 'closed' && (
                      <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-2.5 text-sm font-semibold text-emerald-700">
                        ✓ Run Closed
                      </div>
                    )}
                    {run.status === 'disbursed' && (
                      <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-2.5 text-sm font-semibold text-emerald-700">
                        ✓ Disbursed on {run.disbursed_at ? new Date(run.disbursed_at).toLocaleDateString('en-IN') : '—'}
                      </div>
                    )}

                    {!['under_review','pending_head_approval','approved','payslip_generated','published','completed','closed','disbursed'].includes(run.status) && (
                      <p className="text-sm text-slate-400">
                        Run must reach <strong>Finance Review</strong> status before approval actions are available.
                        Current: <span className="font-medium">{run.status.replace(/_/g,' ')}</span>
                      </p>
                    )}
                  </>
                );
              })()}
            </div>
          </div>

          {/* Audit trail */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
            <div className="px-5 py-4 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">Approval Audit Trail</p>
            </div>
            <div className="px-5 divide-y divide-slate-100">
              {approvals.length === 0 ? (
                <p className="py-6 text-center text-slate-400 text-sm">No actions recorded yet</p>
              ) : (
                approvals.map((a) => <AuditEntry key={a.id} entry={a} />)
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-slate-600 font-medium">No payroll run selected</p>
        </div>
      )}
    </div>
  );
}
