/**
 * Payslip & Bank Advice Module
 *
 * Shows employee payslips for a selected run. Finance can:
 * - View per-employee payslip details
 * - Download PDF payslip per employee (real backend PDF)
 * - Mark payslips as generated / published
 * - Download Bank Advice CSV for bulk transfer
 * - Download PF / ESI registers
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';
import { api } from '../../services/api';

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function RunPicker({ runs, selectedId, onChange }) {
  return (
    <select
      value={selectedId || ''}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
    >
      <option value="" disabled>Select run…</option>
      {runs.map((r) => <option key={r.id} value={r.id}>{r.month_label} — {r.status}</option>)}
    </select>
  );
}

function PayslipModal({ emp, runLabel, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl overflow-hidden">
        {/* Header */}
        <div className="bg-[#0a1731] px-6 py-4 flex items-center justify-between">
          <div>
            <p className="text-white font-bold text-base">Payslip — {runLabel}</p>
            <p className="text-slate-400 text-xs mt-0.5">Acronotics WorkHive · Confidential</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-lg">✕</button>
        </div>

        {/* Employee info */}
        <div className="px-6 py-4 bg-slate-50 border-b border-slate-100 flex justify-between flex-wrap gap-3 text-sm">
          <div>
            <p className="font-bold text-slate-800">{emp.employee_name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{emp.designation} · {emp.department}</p>
          </div>
          <div className="text-right text-xs text-slate-500">
            <p>Working Days: <span className="font-medium text-slate-700">{emp.working_days}</span></p>
            <p>Present: <span className="font-medium text-slate-700">{emp.present_days}</span></p>
            <p>LOP: <span className="font-medium text-rose-600">{emp.lop_days}</span></p>
          </div>
        </div>

        {/* Earnings & Deductions */}
        <div className="p-6 grid grid-cols-2 gap-6">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Earnings</p>
            <div className="space-y-2 text-sm">
              {[
                { label: 'Basic', value: emp.basic_pay },
                { label: 'HRA',   value: emp.hra },
                { label: 'Allowances', value: emp.special_allowance },
              ].map((row) => (
                <div key={row.label} className="flex justify-between">
                  <span className="text-slate-600">{row.label}</span>
                  <span className="font-mono text-slate-700">{fmt(row.value)}</span>
                </div>
              ))}
              <div className="border-t border-slate-200 pt-2 flex justify-between font-semibold">
                <span className="text-slate-700">Gross Salary</span>
                <span className="font-mono text-slate-800">{fmt(emp.gross_earnings)}</span>
              </div>
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Deductions</p>
            <div className="space-y-2 text-sm">
              {[
                { label: 'PF (Employee)', value: emp.employee_pf },
                { label: 'ESI',          value: emp.employee_esi },
                { label: 'Prof. Tax',    value: emp.professional_tax },
                { label: 'TDS',          value: emp.tds },
              ].map((row) => (
                <div key={row.label} className="flex justify-between">
                  <span className="text-slate-600">{row.label}</span>
                  <span className="font-mono text-rose-600">{fmt(row.value)}</span>
                </div>
              ))}
              <div className="border-t border-slate-200 pt-2 flex justify-between font-semibold">
                <span className="text-slate-700">Total Deductions</span>
                <span className="font-mono text-rose-600">{fmt(emp.total_deductions)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Net pay */}
        <div className="mx-6 mb-6 rounded-xl bg-emerald-50 border border-emerald-100 p-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-emerald-800">Net Take-Home Pay</span>
          <span className="text-2xl font-bold font-mono text-emerald-700">{fmt(emp.net_pay)}</span>
        </div>

        {/* Actions */}
        <div className="px-6 pb-6 flex gap-3 flex-wrap">
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 rounded-lg bg-brand-500 text-white px-4 py-2 text-sm font-semibold hover:bg-brand-600 transition"
          >
            🖨 Print / Save PDF
          </button>
          <button
            onClick={() => alert('CSV export would trigger a backend download endpoint')}
            className="flex items-center gap-2 rounded-lg border border-slate-200 text-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-50 transition"
          >
            📥 Export CSV
          </button>
          <button onClick={onClose} className="ml-auto rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Close</button>
        </div>
      </div>
    </div>
  );
}

export default function PayslipBankAdvice() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [run, setRun] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [viewEmp, setViewEmp] = useState(null);
  const [generating, setGenerating] = useState(null);
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 2500); };

  // Uses api.downloadBlob which reads the token from the correct localStorage key
  // (hrms.auth.token) via getToken() — same as all other authenticated requests.
  const downloadWithAuth = async (apiPath, filename) => {
    try {
      const { blob, contentType, filename: serverName } = await api.downloadBlob(apiPath);
      const objectUrl = URL.createObjectURL(new Blob([blob], { type: contentType }));
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = serverName || filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch (e) {
      showToast(e.status === 403 ? 'Access denied' : e.message || 'Download error');
    }
  };

  useEffect(() => {
    financeApi.listRuns()
      .then((data) => {
        setRuns(data);
        const approved = data.find((r) =>
          ['approved', 'payslip_generated', 'published', 'disbursed', 'closed'].includes(r.status)
        );
        setSelectedId((approved || data[0])?.id);
      })
      .finally(() => setLoading(false));
  }, []);

  const loadDetails = (id) => {
    if (!id) return;
    setLoadingDetails(true);
    Promise.all([financeApi.getRun(id), financeApi.getRunEmployees(id)])
      .then(([r, emps]) => { setRun(r); setEmployees(emps); })
      .finally(() => setLoadingDetails(false));
  };

  useEffect(() => { loadDetails(selectedId); }, [selectedId]);

  const handleMarkGenerated = async (emp) => {
    setGenerating(emp.employee_id);
    try {
      await financeApi.markPayslipGenerated(run.id, emp.employee_id);
      setEmployees((prev) => prev.map((e) =>
        e.employee_id === emp.employee_id ? { ...e, payslip_generated: true } : e
      ));
      showToast(`Payslip marked as generated for ${emp.employee_name}`);
    } catch (e) {
      showToast(e?.data?.detail || e.message || 'Failed');
    } finally {
      setGenerating(null);
    }
  };

  const filtered = employees.filter((e) =>
    !search || e.employee_name?.toLowerCase().includes(search.toLowerCase())
      || e.department?.toLowerCase().includes(search.toLowerCase())
  );

  const generatedCount = employees.filter((e) => e.payslip_generated).length;

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
      {viewEmp && (
        <PayslipModal
          emp={viewEmp}
          runLabel={run?.month_label}
          onClose={() => setViewEmp(null)}
        />
      )}

      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          if (role_ === 'admin') navigate('/admin-dashboard/payroll');
          else if (role_ === 'finance_head' || role_ === 'financehead') navigate('/employee-dashboard/finance-head-payroll');
          else navigate('/employee-dashboard/finance-payroll');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Payslips & Bank Advice</h1>
          <p className="text-sm text-slate-500 mt-0.5">Generate and manage employee payslips</p>
        </div>
        <RunPicker runs={runs} selectedId={selectedId} onChange={setSelectedId} />
      </div>

      {/* Progress bar */}
      {employees.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-slate-700">Payslip Generation Progress</p>
            <p className="text-sm font-bold text-slate-700">{generatedCount} / {employees.length}</p>
          </div>
          <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all"
              style={{ width: `${employees.length > 0 ? (generatedCount / employees.length) * 100 : 0}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-xs text-slate-400">
            <span>{generatedCount} generated</span>
            <span>{employees.length - generatedCount} pending</span>
          </div>
        </div>
      )}

      {/* Export actions */}
      {selectedId && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-soft">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Bulk Export</p>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/bank-advice`,
                `bank_advice_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Bank transfer CSV for salary disbursement"
            >
              <span>🏦</span>
              <span>Bank Advice (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/pf-register`,
                `pf_register_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="PF register for statutory compliance"
            >
              <span>🏛</span>
              <span>PF Register (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/esi-register`,
                `esi_register_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="ESI register for statutory compliance"
            >
              <span>📊</span>
              <span>ESI Register (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/pt-register`,
                `pt_register_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Professional Tax register"
            >
              <span>📋</span>
              <span>PT Register (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/tds-report`,
                `tds_report_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="TDS report with regime and declaration details"
            >
              <span>🧾</span>
              <span>TDS Report (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/form16-batch`,
                `form16_batch_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Form 16 annual TDS summary for all employees"
            >
              <span>📄</span>
              <span>Form 16 Batch (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/pf-challan`,
                `pf_challan_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="PF challan for deposit with EPFO"
            >
              <span>🏦</span>
              <span>PF Challan (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/compliance/esi-filing`,
                `esi_filing_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="ESI filing format for ESIC portal"
            >
              <span>🏥</span>
              <span>ESI Filing (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/payroll-register`,
                `payroll_register_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Full payroll register with all components"
            >
              <span>📑</span>
              <span>Payroll Register (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/bonus-report`,
                `bonus_report_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Bonus adjustments for this run"
            >
              <span>🎁</span>
              <span>Bonus Report (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/variable-pay-report`,
                `variable_pay_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Variable pay and incentives for this run"
            >
              <span>💹</span>
              <span>Variable Pay (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/reimbursement-report`,
                `reimbursements_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Approved reimbursements for this run"
            >
              <span>🧳</span>
              <span>Reimbursements (CSV)</span>
            </button>
            <button
              onClick={() => downloadWithAuth(
                `/finance/runs/${selectedId}/gratuity-report`,
                `gratuity_provision_run${selectedId}.csv`
              )}
              className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
              title="Annual gratuity provision per employee"
            >
              <span>🏦</span>
              <span>Gratuity Provision (CSV)</span>
            </button>
            {run && ['approved','payslip_generated','published','closed','disbursed'].includes(run.status) && (
              <button
                onClick={async () => {
                  try {
                    await financeApi.publishAllPayslips(selectedId);
                    showToast('All payslips published to ESS portal');
                    loadDetails(selectedId);
                  } catch (e) { showToast(e?.data?.detail || 'Publish failed'); }
                }}
                className="flex items-center gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-medium text-emerald-700 hover:bg-emerald-100 transition"
              >
                <span>🚀</span>
                <span>Publish All to ESS</span>
              </button>
            )}
            {run && ['published','closed','disbursed'].includes(run.status) && (
              <button
                onClick={async () => {
                  try {
                    await financeApi.sendPayslipEmails(selectedId);
                    showToast('Payslip emails sent successfully');
                  } catch (e) { showToast(e?.data?.detail || 'Email send failed'); }
                }}
                className="flex items-center gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-medium text-blue-700 hover:bg-blue-100 transition"
              >
                <span>✉️</span>
                <span>Send Payslip Emails</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Employee list */}
      {loadingDetails ? (
        <div className="flex items-center justify-center h-32">
          <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Employee Payslips ({employees.length})</p>
            <input
              type="text"
              placeholder="Search employee…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-brand-400"
            />
          </div>

          {employees.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-4xl mb-3">📄</p>
              <p className="text-slate-600 font-medium">No payroll data for this run</p>
              <p className="text-slate-400 text-sm mt-1">Generate payroll first</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                    {['Employee', 'Department', 'Gross', 'Deductions', 'Net Pay', 'Status', 'Actions'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((e) => (
                    <tr key={e.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-700">{e.employee_name}</p>
                        <p className="text-xs text-slate-400">{e.designation}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{e.department}</td>
                      <td className="px-4 py-3 font-mono text-slate-700">{fmt(e.gross_earnings)}</td>
                      <td className="px-4 py-3 font-mono text-rose-600">{fmt(e.total_deductions)}</td>
                      <td className="px-4 py-3 font-mono font-semibold text-emerald-700">{fmt(e.net_pay)}</td>
                      <td className="px-4 py-3">
                        {e.payslip_generated ? (
                          <span className="rounded-full bg-emerald-100 text-emerald-700 px-2.5 py-0.5 text-xs font-semibold">Generated ✓</span>
                        ) : (
                          <span className="rounded-full bg-amber-100 text-amber-700 px-2.5 py-0.5 text-xs font-semibold">Pending</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2 flex-wrap">
                          <button
                            onClick={() => setViewEmp(e)}
                            className="rounded bg-brand-50 text-brand-600 border border-brand-200 px-2.5 py-1 text-xs font-medium hover:bg-brand-100 transition"
                          >
                            View
                          </button>
                          <button
                            onClick={() => downloadWithAuth(
                              `/finance/runs/${run?.id}/payslips/${e.employee_id}/pdf`,
                              `payslip_${(e.employee_name || 'emp').replace(/\s+/g,'_')}_run${run?.id}.pdf`
                            )}
                            className="rounded bg-slate-50 text-slate-700 border border-slate-200 px-2.5 py-1 text-xs font-medium hover:bg-slate-100 transition"
                            title="Download payslip PDF"
                          >
                            PDF ↓
                          </button>
                          {!e.payslip_generated && (
                            <button
                              onClick={() => handleMarkGenerated(e)}
                              disabled={generating === e.employee_id}
                              className="rounded bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 text-xs font-medium hover:bg-emerald-100 transition disabled:opacity-50"
                            >
                              {generating === e.employee_id ? '…' : 'Mark Generated'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
