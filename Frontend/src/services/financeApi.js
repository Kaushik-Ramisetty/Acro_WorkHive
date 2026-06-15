/**
 * Finance / Payroll API client.
 * Uses the shared `api` named export from services/api.js which handles JWT
 * auth and error normalisation.
 */
import { api } from './api';

const BASE = '/finance';

function qs(params = {}) {
  const pairs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
  return pairs.length ? '?' + new URLSearchParams(pairs).toString() : '';
}

export const financeApi = {
  // ── Dashboard ──────────────────────────────────────────────────────────────
  getDashboard: () => api.get(`${BASE}/dashboard`),

  // ── Payroll Runs ───────────────────────────────────────────────────────────
  listRuns: ({ limit = 20, offset = 0 } = {}) =>
    api.get(`${BASE}/runs${qs({ limit, offset })}`),
  createRun: (body) => api.post(`${BASE}/runs`, body),
  getRun: (runId) => api.get(`${BASE}/runs/${runId}`),
  runAction: (runId, action, remarks = '') =>
    api.post(`${BASE}/runs/${runId}/action`, { action, remarks }),

  // ── Run Employees ──────────────────────────────────────────────────────────
  getRunEmployees: (runId) => api.get(`${BASE}/runs/${runId}/employees`),
  markPayslipGenerated: (runId, employeeId) =>
    api.post(`${BASE}/runs/${runId}/employees/${employeeId}/payslip`, {}),

  // ── Approval History ───────────────────────────────────────────────────────
  getRunApprovals: (runId) => api.get(`${BASE}/runs/${runId}/approvals`),

  // ── Variance Review ────────────────────────────────────────────────────────
  getVariance: (runId) => api.get(`${BASE}/runs/${runId}/variance`),
  acknowledgeVariance: (runId, body) =>
    api.post(`${BASE}/runs/${runId}/variance/acknowledge`, body),

  // ── Payroll Errors ─────────────────────────────────────────────────────────
  listErrors: (runId, resolved) =>
    api.get(`${BASE}/runs/${runId}/errors${qs(resolved !== undefined ? { resolved } : {})}`),
  createError: (runId, body) => api.post(`${BASE}/runs/${runId}/errors`, body),
  resolveError: (errorId, resolutionNote) =>
    api.patch(`${BASE}/errors/${errorId}/resolve`, { resolution_note: resolutionNote }),

  // ── Employees (for dropdowns) ──────────────────────────────────────────────
  listEmployees: () => api.get(`${BASE}/employees`),

  // ── Salary Structures ──────────────────────────────────────────────────────
  listSalaryStructures: () => api.get(`${BASE}/salary-structures`),
  getSalaryStructure: (employeeId) => api.get(`${BASE}/salary-structures/${employeeId}`),
  getSalaryStructureHistory: (employeeId) => api.get(`${BASE}/salary-structures/${employeeId}/history`),
  upsertSalaryStructure: (body) => api.put(`${BASE}/salary-structures`, body),
  structureFromCTC: (body) => api.post(`${BASE}/salary-structures/from-ctc`, body),
  previewCTC: (body) => api.post(`${BASE}/ctc/preview`, body),

  // ── Adjustments ────────────────────────────────────────────────────────────
  listAdjustments: (runId, employeeId) =>
    api.get(`${BASE}/runs/${runId}/adjustments${qs(employeeId ? { employee_id: employeeId } : {})}`),
  addAdjustment: (runId, body) => api.post(`${BASE}/runs/${runId}/adjustments`, body),
  deleteAdjustment: (adjId) => api.delete(`${BASE}/adjustments/${adjId}`),

  // ── Payslips ───────────────────────────────────────────────────────────────
  listPayslips: (runId) => api.get(`${BASE}/runs/${runId}/payslips`),
  payslipPdfUrl: (runId, employeeId) => `${BASE}/runs/${runId}/payslips/${employeeId}/pdf`,
  publishPayslip: (runId, employeeId) =>
    api.post(`${BASE}/runs/${runId}/payslips/${employeeId}/publish`, {}),
  publishAllPayslips: (runId) => api.post(`${BASE}/runs/${runId}/payslips/publish-all`, {}),

  // ── Bank Advice ────────────────────────────────────────────────────────────
  bankAdviceUrl: (runId) => `${BASE}/runs/${runId}/bank-advice`,

  // ── Compliance & Reports ───────────────────────────────────────────────────
  getCompliance: (runId) => api.get(`${BASE}/runs/${runId}/compliance`),
  pfRegisterUrl: (runId) => `${BASE}/runs/${runId}/compliance/pf-register`,
  esiRegisterUrl: (runId) => `${BASE}/runs/${runId}/compliance/esi-register`,
  ptRegisterUrl: (runId) => `${BASE}/runs/${runId}/compliance/pt-register`,
  tdsReportUrl: (runId) => `${BASE}/runs/${runId}/compliance/tds-report`,
  payrollRegisterUrl: (runId) => `${BASE}/runs/${runId}/payroll-register`,
  bonusReportUrl: (runId) => `${BASE}/runs/${runId}/bonus-report`,
  payrollSummaryExportUrl: (runId) => `${BASE}/runs/${runId}/payroll-summary/export`,
  variablePayReportUrl: (runId) => `${BASE}/runs/${runId}/variable-pay-report`,
  reimbursementReportUrl: (runId) => `${BASE}/runs/${runId}/reimbursement-report`,
  gratuityReportUrl: (runId) => `${BASE}/runs/${runId}/gratuity-report`,

  // ── Salary Revision Audit ─────────────────────────────────────────────────
  createSalaryRevision: (body) => api.post(`${BASE}/salary-revisions`, body),
  listSalaryRevisions: ({ employeeId, limit = 100, offset = 0 } = {}) =>
    api.get(`${BASE}/salary-revisions${qs({ employee_id: employeeId, limit, offset })}`),
  getSalaryRevision: (revisionId) => api.get(`${BASE}/salary-revisions/${revisionId}`),
  salaryRevisionReportUrl: (employeeId) =>
    `${BASE}/salary-revisions/report${employeeId ? `?employee_id=${employeeId}` : ''}`,

  // ── Missing Salary Structures ─────────────────────────────────────────────
  getMissingStructures: () => api.get(`${BASE}/employees/missing-salary-structure`),

  // ── Tax Declarations ──────────────────────────────────────────────────────
  listTaxDeclarations: ({ employeeId, financialYear } = {}) =>
    api.get(`${BASE}/tax-declarations${qs({ employee_id: employeeId, financial_year: financialYear })}`),
  upsertTaxDeclaration: (body) => api.put(`${BASE}/tax-declarations`, body),

  // ── Admin Dashboard (with optional run_id or month+year for month-specific view) ───────────
  getAdminDashboardStats: (runId, month, year) =>
    api.get(`${BASE}/admin-dashboard-stats${qs({
      ...(runId ? { run_id: runId } : {}),
      ...(month && year ? { month, year } : {}),
    })}`),

  // ── Analytics ──────────────────────────────────────────────────────────────
  getAnalyticsSummary: () => api.get(`${BASE}/analytics/summary`),

  // ── Statutory Settings ─────────────────────────────────────────────────────
  getStatutorySettings: () => api.get(`${BASE}/statutory-settings`),
  updateStatutorySettings: (body) => api.put(`${BASE}/statutory-settings`, body),

  // ── Salary Components ──────────────────────────────────────────────────────
  listSalaryComponents: (activeOnly = true) =>
    api.get(`${BASE}/salary-components${qs({ active_only: activeOnly })}`),
  upsertSalaryComponent: (body) => api.post(`${BASE}/salary-components`, body),

  // ── Employee Salary History ────────────────────────────────────────────────
  listEmployeeSalary: (employeeId) =>
    api.get(`${BASE}/employee-salary${qs(employeeId ? { employee_id: employeeId } : {})}`),
  getActiveEmployeeSalary: (employeeId) =>
    api.get(`${BASE}/employee-salary/${employeeId}/active`),

  // ── Tax Deductions ─────────────────────────────────────────────────────────
  listRunTaxDeductions: (runId) => api.get(`${BASE}/runs/${runId}/tax-deductions`),
  listTaxDeductions: ({ employeeId, financialYear } = {}) =>
    api.get(`${BASE}/tax-deductions${qs({ employee_id: employeeId, financial_year: financialYear })}`),

  // ── Reimbursements ─────────────────────────────────────────────────────────
  listReimbursements: ({ employeeId, status, runId } = {}) =>
    api.get(`${BASE}/reimbursements${qs({ employee_id: employeeId, status, run_id: runId })}`),
  createReimbursement: (body) => api.post(`${BASE}/reimbursements`, body),
  approveReimbursement: (id, body = {}) =>
    api.post(`${BASE}/reimbursements/${id}/approve`, body),
  rejectReimbursement: (id, remarks) =>
    api.post(`${BASE}/reimbursements/${id}/reject`, { remarks }),
  markReimbursementPaid: (id, payrollRunId) =>
    api.post(`${BASE}/reimbursements/${id}/mark-paid`, { payroll_run_id: payrollRunId }),
  cancelReimbursement: (id) => api.post(`${BASE}/reimbursements/${id}/cancel`, {}),
  managerApproveReimbursement: (id, remarks = '') =>
    api.post(`${BASE}/reimbursements/${id}/manager-approve`, { remarks }),
  managerRejectReimbursement: (id, remarks = '') =>
    api.post(`${BASE}/reimbursements/${id}/manager-reject`, { remarks }),

  // ── Tax Declaration Approval ──────────────────────────────────────────────
  getTaxDeclaration: (id) => api.get(`${BASE}/tax-declarations/${id}`),
  verifyTaxDeclaration: (id, body) => api.post(`${BASE}/tax-declarations/${id}/verify`, body),
  submitTaxDeclarationProof: (id) => api.post(`${BASE}/tax-declarations/${id}/submit-proof`, {}),

  // ── Payslip Emails ────────────────────────────────────────────────────────
  sendPayslipEmails: (runId) => api.post(`${BASE}/runs/${runId}/payslips/send-emails`, {}),
  sendPayslipEmailsForce: (runId) => api.post(`${BASE}/runs/${runId}/payslips/send-emails?force=true`, {}),

  // ── Attendance Management ─────────────────────────────────────────────────
  getAttendanceSummary: (runId) => api.get(`${BASE}/runs/${runId}/attendance-summary`),
  freezeAttendance: (runId) => api.post(`${BASE}/runs/${runId}/attendance-summary/freeze`, {}),
  unfreezeAttendance: (runId) => api.post(`${BASE}/runs/${runId}/attendance-summary/unfreeze`, {}),
  upsertAttendanceSummary: (runId, body) =>
    api.post(`${BASE}/runs/${runId}/attendance-summary/upsert`, body),

  // ── Salary Revision / Hike Requests ──────────────────────────────────────
  createHikeRequest: (body) => api.post(`${BASE}/hike-requests`, body),
  listHikeRequests: ({ statusFilter, employeeId, limit = 200 } = {}) =>
    api.get(`${BASE}/hike-requests${qs({ status_filter: statusFilter, employee_id: employeeId, limit })}`),
  getPendingHikeCount: () => api.get(`${BASE}/hike-requests/pending-count`),
  getHikeRequest: (id) => api.get(`${BASE}/hike-requests/${id}`),
  updateHikeRequest: (id, body) => api.put(`${BASE}/hike-requests/${id}`, body),
  cancelHikeRequest: (id) => api.post(`${BASE}/hike-requests/${id}/cancel`, {}),
  approveHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/approve`, { comment }),
  rejectHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/reject`, { comment, rejection_reason: comment }),
  headApproveHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/head-approve`, { comment }),
  headRejectHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/head-reject`, { comment, rejection_reason: comment }),

  // ── Bonus Requests ────────────────────────────────────────────────────────
  createBonusRequest: (body) => api.post(`${BASE}/bonus-requests`, body),
  listBonusRequests: ({ statusFilter, employeeId, month, year, limit = 200 } = {}) =>
    api.get(`${BASE}/bonus-requests${qs({ status_filter: statusFilter, employee_id: employeeId, month, year, limit })}`),
  getPendingBonusCount: () => api.get(`${BASE}/bonus-requests/pending-count`),
  getBonusRequest: (id) => api.get(`${BASE}/bonus-requests/${id}`),
  updateBonusRequest: (id, body) => api.put(`${BASE}/bonus-requests/${id}`, body),
  cancelBonusRequest: (id) => api.post(`${BASE}/bonus-requests/${id}/cancel`, {}),
  approveBonusRequest: (id, comment = '') =>
    api.post(`${BASE}/bonus-requests/${id}/approve`, { comment }),
  rejectBonusRequest: (id, comment = '') =>
    api.post(`${BASE}/bonus-requests/${id}/reject`, { comment }),
  headApproveBonusRequest: (id, comment = '') =>
    api.post(`${BASE}/bonus-requests/${id}/head-approve`, { comment }),
  headRejectBonusRequest: (id, comment = '') =>
    api.post(`${BASE}/bonus-requests/${id}/head-reject`, { comment, rejection_reason: comment }),
  applyBonusToRun: (id, runId) =>
    api.post(`${BASE}/bonus-requests/${id}/apply-to-run`, { run_id: runId }),

  // ── Off-Cycle Payments ────────────────────────────────────────────────────
  createOffCyclePayment: (body) => api.post(`${BASE}/off-cycle-payments`, body),
  listOffCyclePayments: ({ statusFilter, employeeId, limit = 200 } = {}) =>
    api.get(`${BASE}/off-cycle-payments${qs({ status_filter: statusFilter, employee_id: employeeId, limit })}`),
  getPendingOffCycleCount: () => api.get(`${BASE}/off-cycle-payments/pending-count`),
  getOffCyclePayment: (id) => api.get(`${BASE}/off-cycle-payments/${id}`),
  getOffCycleAuditLog: (id) => api.get(`${BASE}/off-cycle-payments/${id}/audit`),
  generateOffCyclePayslip: (id) => api.post(`${BASE}/off-cycle-payments/${id}/generate-payslip`, {}),
  offCyclePayslipUrl: (id) => `${BASE}/off-cycle-payments/${id}/payslip/pdf`,
  generateOffCycleBankAdvice: (id) => api.post(`${BASE}/off-cycle-payments/${id}/generate-bank-advice`, {}),
  offCycleBankAdviceUrl: (id) => `${BASE}/off-cycle-payments/${id}/bank-advice`,
  markOffCyclePaid: (id, body = {}) => api.post(`${BASE}/off-cycle-payments/${id}/mark-paid`, body),
  returnOffCyclePayment: (id, note = '') => api.post(`${BASE}/off-cycle-payments/${id}/return`, { note }),
  rejectOffCyclePayment: (id, note = '') => api.post(`${BASE}/off-cycle-payments/${id}/reject`, { note }),

  // ── F&F PDF ───────────────────────────────────────────────────────────────
  ffPdfUrl: (ffId) => `/finance/ff/${ffId}/pdf`,

  // ── Compliance: Advanced ─────────────────────────────────────────────────
  form16Url: (employeeId, financialYear) =>
    `${BASE}/employees/${employeeId}/form16${qs({ financial_year: financialYear })}`,
  form16BatchUrl: (runId) => `${BASE}/runs/${runId}/compliance/form16-batch`,
  pfChallanUrl: (runId) => `${BASE}/runs/${runId}/compliance/pf-challan`,
  esiFilingUrl: (runId) => `${BASE}/runs/${runId}/compliance/esi-filing`,
  tdsQuarterlyUrl: (financialYear, quarter) =>
    `${BASE}/compliance/tds-quarterly${qs({ financial_year: financialYear, quarter })}`,

  // ── Payroll Attendance Bridge (temporary — until Attendance/Timesheet integration) ──
  getPayrollAttendanceSummary: (month, year) =>
    api.get(`/payroll/attendance-summary${qs({ month, year })}`),
  validatePayrollAttendance: (month, year) =>
    api.post('/payroll/attendance-summary/validate', { month, year }),
  freezePayrollAttendance: (month, year) =>
    api.post('/payroll/attendance-summary/freeze', { month, year }),
  manualAttendanceSummary: (body) =>
    api.post('/payroll/attendance-summary/manual', body),
  // DEV ONLY — TEMPORARY FOR PAYROLL TESTING. REMOVE AFTER REAL ATT/TS INTEGRATION.
  resetPayrollAttendanceFreeze: (month, year) =>
    api.post('/payroll/attendance-summary/reset-freeze', { month, year }),

  getOpenPayrollMonth: () =>
    api.get('/payroll/attendance-summary/open-month'),

  // ── Demo Reset (clears payroll runs so demo flow can run cleanly) ──────────
  demoReset: ({ months = [5, 6, 7], year = 2026 } = {}) =>
    api.post(`${BASE}/demo-reset${(() => {
      const p = new URLSearchParams();
      months.forEach((m) => p.append('months', m));
      p.set('year', year);
      return '?' + p.toString();
    })()}`, {}),
};

export default financeApi;
