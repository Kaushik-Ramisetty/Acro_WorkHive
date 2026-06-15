/**
 * Canonical workflow status constants, step definitions, and utilities
 * for the Timesheets multi-stage approval pipeline.
 *
 * Workflow path:
 *   draft → pending_client_review → client_approved
 *         → pending_reporting_manager_review → reporting_manager_approved
 *         → pending_hr_review → hr_approved
 *         → pending_finance_review → finance_approved
 *         → processing → completed
 *
 * Rejection at any stage returns to employee (client_rejected | rejected).
 * Employee edits and resubmits to restart from client review.
 */

// ── Status constants ──────────────────────────────────────────────────────

export const WF = Object.freeze({
  DRAFT:            'draft',
  PENDING_CLIENT:   'pending_client_review',
  CLIENT_APPROVED:  'client_approved',
  CLIENT_REJECTED:  'client_rejected',
  PENDING_RM:       'pending_reporting_manager_review',
  RM_APPROVED:      'reporting_manager_approved',
  PENDING_HR:       'pending_hr_review',
  HR_APPROVED:      'hr_approved',
  PENDING_FINANCE:  'pending_finance_review',
  FINANCE_APPROVED: 'finance_approved',
  PROCESSING:       'processing',
  COMPLETED:        'completed',
  REJECTED:         'rejected',
});

// ── Progress weights (higher = further along) ────────────────────────────

export const WF_WEIGHT = {
  [WF.DRAFT]:            0,
  [WF.PENDING_CLIENT]:   1,
  [WF.CLIENT_APPROVED]:  2,
  [WF.CLIENT_REJECTED]:  -1,
  [WF.PENDING_RM]:       3,
  [WF.RM_APPROVED]:      4,
  [WF.PENDING_HR]:       5,
  [WF.HR_APPROVED]:      6,
  [WF.PENDING_FINANCE]:  7,
  [WF.FINANCE_APPROVED]: 8,
  [WF.PROCESSING]:       9,
  [WF.COMPLETED]:        10,
  [WF.REJECTED]:         -2,
};

// ── Access control ───────────────────────────────────────────────────────

/** Statuses where the employee may edit entry rows */
export const EMPLOYEE_EDITABLE = new Set([WF.DRAFT, WF.CLIENT_REJECTED, WF.REJECTED]);

/** Statuses that are safe for billing calculations */
export const BILLING_SAFE = new Set([WF.FINANCE_APPROVED, WF.COMPLETED]);

/** Statuses that are safe for payroll processing */
export const PAYROLL_SAFE = new Set([WF.COMPLETED]);

// ── Header badge display config ──────────────────────────────────────────

export const WF_DISPLAY = {
  [WF.DRAFT]:            { label: 'Draft',             color: '#64748B', bg: '#F8FAFC', border: '#E2E8F0' },
  [WF.PENDING_CLIENT]:   { label: 'Client Review',     color: '#854F0B', bg: '#FAEEDA', border: '#F3D9B5' },
  [WF.CLIENT_APPROVED]:  { label: 'Client Approved',   color: '#3B6D11', bg: '#EAF3DE', border: '#C0DCAA' },
  [WF.CLIENT_REJECTED]:  { label: 'Client Rejected',   color: '#991B1B', bg: '#FEF2F2', border: '#FECACA' },
  [WF.PENDING_RM]:       { label: 'Manager Review',    color: '#854F0B', bg: '#FAEEDA', border: '#F3D9B5' },
  [WF.RM_APPROVED]:      { label: 'Manager Approved',  color: '#3B6D11', bg: '#EAF3DE', border: '#C0DCAA' },
  [WF.PENDING_HR]:       { label: 'HR Review',         color: '#854F0B', bg: '#FAEEDA', border: '#F3D9B5' },
  [WF.HR_APPROVED]:      { label: 'HR Approved',       color: '#3B6D11', bg: '#EAF3DE', border: '#C0DCAA' },
  [WF.PENDING_FINANCE]:  { label: 'Finance Review',    color: '#854F0B', bg: '#FAEEDA', border: '#F3D9B5' },
  [WF.FINANCE_APPROVED]: { label: 'Finance Approved',  color: '#3B6D11', bg: '#EAF3DE', border: '#C0DCAA' },
  [WF.PROCESSING]:       { label: 'Processing',        color: '#1D5FA5', bg: '#EBF4FF', border: '#BFD9F7' },
  [WF.COMPLETED]:        { label: 'Completed',         color: '#3B6D11', bg: '#EAF3DE', border: '#C0DCAA' },
  [WF.REJECTED]:         { label: 'Rejected',          color: '#991B1B', bg: '#FEF2F2', border: '#FECACA' },
};
