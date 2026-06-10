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

  // ── Admin Dashboard (with optional run_id for historical view) ───────────
  getAdminDashboardStats: (runId) =>
    api.get(`${BASE}/admin-dashboard-stats${qs(runId ? { run_id: runId } : {})}`),

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

  // ── Attendance Management ─────────────────────────────────────────────────
  getAttendanceSummary: (runId) => api.get(`${BASE}/runs/${runId}/attendance-summary`),
  freezeAttendance: (runId) => api.post(`${BASE}/runs/${runId}/attendance-summary/freeze`, {}),
  unfreezeAttendance: (runId) => api.post(`${BASE}/runs/${runId}/attendance-summary/unfreeze`, {}),
  upsertAttendanceSummary: (runId, body) =>
    api.post(`${BASE}/runs/${runId}/attendance-summary/upsert`, body),

  // ── Salary Hike Requests ──────────────────────────────────────────────────
  createHikeRequest: (body) => api.post(`${BASE}/hike-requests`, body),
  listHikeRequests: ({ statusFilter, employeeId, limit = 50 } = {}) =>
    api.get(`${BASE}/hike-requests${qs({ status_filter: statusFilter, employee_id: employeeId, limit })}`),
  getPendingHikeCount: () => api.get(`${BASE}/hike-requests/pending-count`),
  approveHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/approve`, { comment }),
  rejectHikeRequest: (id, comment = '') =>
    api.post(`${BASE}/hike-requests/${id}/reject`, { comment }),

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
  // Seed dummy data for all active employees — TEMPORARY BRIDGE
  seedPayrollAttendanceDummy: (month, year) =>
    api.post(`/payroll/attendance-summary/seed-dummy${qs({ month, year })}`),
  validatePayrollAttendance: (month, year) =>
    api.post('/payroll/attendance-summary/validate', { month, year }),
  freezePayrollAttendance: (month, year) =>
    api.post('/payroll/attendance-summary/freeze', { month, year }),
  // DEV ONLY — TEMPORARY FOR PAYROLL TESTING. REMOVE AFTER REAL ATT/TS INTEGRATION.
  resetPayrollAttendanceFreeze: (month, year) =>
    api.post('/payroll/attendance-summary/reset-freeze', { month, year }),
};

export default financeApi;
