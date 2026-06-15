/**
 * Employee self-service payroll API client.
 * All endpoints authenticate via JWT — employee sees only their own data.
 */
import { api } from './api';

const BASE = '/employee/payroll';

function qs(params = {}) {
  const pairs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
  return pairs.length ? '?' + new URLSearchParams(pairs).toString() : '';
}

export const employeePayrollApi = {
  // ── Payslips ───────────────────────────────────────────────────────────────
  listPayslips: () => api.get(`${BASE}/payslips`),
  getPayslipDetail: (runId) => api.get(`${BASE}/payslips/${runId}/detail`),
  payslipPdfUrl: (runId) => `${BASE}/payslips/${runId}/pdf`,

  // ── YTD Summary ───────────────────────────────────────────────────────────
  getYtdSummary: (financialYear) =>
    api.get(`${BASE}/ytd-summary${qs(financialYear ? { financial_year: financialYear } : {})}`),

  // ── Reimbursements ────────────────────────────────────────────────────────
  listReimbursements: () => api.get(`${BASE}/reimbursements`),
  submitReimbursement: (body) => api.post(`${BASE}/reimbursements`, body),
  cancelReimbursement: (id) => api.delete(`${BASE}/reimbursements/${id}`),

  // ── Tax Declarations ──────────────────────────────────────────────────────
  listTaxDeclarations: () => api.get(`${BASE}/tax-declarations`),
  upsertTaxDeclaration: (body) => api.put(`${BASE}/tax-declarations`, body),

  // ── Salary Structure (read-only) ──────────────────────────────────────────
  getSalaryStructure: () => api.get(`${BASE}/salary-structure`),

  // ── Attendance Used for Payroll (read-only) ───────────────────────────────
  getAttendanceSummary: () => api.get(`${BASE}/attendance-summary`),

  // ── Payroll Status Card (header) ──────────────────────────────────────────
  getPayrollStatus: () => api.get(`${BASE}/status`),
};

export default employeePayrollApi;
