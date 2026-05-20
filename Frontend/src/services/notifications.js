import { api } from './api';

/**
 * Notification API client.
 *
 *  - recent()        → top 10 for the navbar dropdown (cheap)
 *  - listPaged()     → full Notifications page (filters, search, pagination)
 *  - unreadCount()   → badge polling
 *  - markRead(id)    → PUT /{id}/read
 *  - markAllRead()   → PUT /read-all
 *
 * routeFor(n, rolePath)
 *   Resolves a Notification → absolute in-app URL the React Router can
 *   navigate to. Server fills `action_url` for new rows; this helper
 *   provides a fallback for legacy data and prepends the active role's
 *   dashboard base path.
 */
export const notificationsApi = {
  recent:       (limit = 10) => api.get(`/notifications/recent?limit=${limit}`),
  listPaged:    (params = {}) => {
    const qs = new URLSearchParams();
    if (params.unreadOnly) qs.set('unread_only', 'true');
    if (params.category)   qs.set('category', params.category);
    if (params.type)       qs.set('type', params.type);
    if (params.q)          qs.set('q', params.q);
    if (params.limit  != null) qs.set('limit',  String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : '';
    return api.get(`/notifications${suffix}`);
  },
  unreadCount:  ()           => api.get('/notifications/unread-count'),
  markRead:     (id)         => api.put(`/notifications/${id}/read`),
  markAllRead:  ()           => api.put('/notifications/read-all'),
};

// ── Type → page-id fallback (mirrors backend services/notification_service) ──
const TYPE_PAGE = {
  leave_applied: 'leave', leave_approved: 'leave', leave_rejected: 'leave',
  leave_cancelled: 'leave', leave_cancel_requested: 'leave', leave_cancel_rejected: 'leave',
  leave_pending_your_approval: 'approvals',
  leave_cancel_pending_your_approval: 'approvals',
  leave_escalated: 'approvals',
  attendance_anomaly: 'attendance',
  attendance_missed_checkout: 'attendance',
  regularization_submitted: 'regularization',
  regularization_approved: 'attendance',
  regularization_rejected: 'attendance',
  timesheet_submitted: 'timesheets', timesheet_approved: 'timesheets',
  timesheet_rejected: 'timesheets', timesheet_reminder: 'timesheets',
  compoff_credited: 'comp-off', compoff_expiring: 'comp-off',
  onboarding_invite: 'onboarding', onboarding_completed: 'onboarding',
  bgv_updated: 'onboarding',
  payroll_sync_failed: 'payroll', payroll_processed: 'payroll', payslip_ready: 'payroll',
  announcement: 'announcements', policy_published: 'policies',
  sla_escalation: 'approvals', hr_escalation: 'approvals',
  compliance_alert: 'reports',
};

const REF_PAGE = {
  leave_requests: 'leave',
  attendance_records: 'attendance',
  timesheets: 'timesheets',
  comp_off_credits: 'comp-off',
  onboarding: 'onboarding',
  candidates: 'onboarding',
  payroll_runs: 'payroll',
  announcements: 'announcements',
  policies: 'policies',
};

/**
 * Resolve a notification row to an in-app route the router can `navigate()` to.
 *
 * @param {object} n          Notification payload from the API
 * @param {string} basePath   Role dashboard base, e.g. "/employee-dashboard"
 * @returns {string|null}     Absolute route, or null if we can't determine one
 */
export function routeFor(n, basePath) {
  if (!n) return null;
  // 1) Server-derived hint wins.
  let page = n.action_url || null;
  // 2) Fallback to type map.
  if (!page && n.type) page = TYPE_PAGE[n.type] || null;
  // 3) Loose prefix fallback for unknown types like "leave_foo".
  if (!page && n.type) {
    for (const [pfx, p] of [
      ['leave_', 'leave'],
      ['attendance_', 'attendance'],
      ['timesheet_', 'timesheets'],
      ['compoff_', 'comp-off'],
      ['payroll_', 'payroll'],
      ['onboarding_', 'onboarding'],
    ]) {
      if (n.type.startsWith(pfx)) { page = p; break; }
    }
  }
  // 4) Fallback by reference_table.
  if (!page && n.reference_table) page = REF_PAGE[n.reference_table] || null;
  if (!page) return null;
  // Already an absolute path (server may eventually emit "/leave" or full URL)
  if (page.startsWith('/')) return page;
  const base = basePath?.replace(/\/+$/, '') || '';
  return `${base}/${page}`;
}
