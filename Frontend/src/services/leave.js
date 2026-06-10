import { api } from './api';

// IDs of leave types we want to hide from the UI even if they're still
// present in the database. Currently used to suppress the legacy
// "Earned Leave" row (LT005) — its quota was folded into LT002, which has
// since been renamed to "Paid Leaves". Pre-existing balances/types for
// LT005 are filtered out here so dropdowns and balance grids don't show a
// stale duplicate. Existing LeaveRequest history that referenced LT005 is
// NOT filtered (history remains intact).
const LEAVE_TYPE_HIDDEN_IDS = new Set(['LT005']);

const filterTypes    = (rows) => Array.isArray(rows) ? rows.filter((t) => !LEAVE_TYPE_HIDDEN_IDS.has(t?.id)) : rows;
const filterBalances = (rows) => Array.isArray(rows) ? rows.filter((b) => !LEAVE_TYPE_HIDDEN_IDS.has(b?.leave_type_id)) : rows;

export const leaveApi = {
  types:        ()                          => api.get('/leave/types').then(filterTypes),
  list:         (params)                    => api.get('/leave/list' + buildQs(params)),
  one:          (id)                        => api.get('/leave/' + id),
  apply:        (payload)                   => api.post('/leave/apply', payload),
  validate:     (payload)                   => api.post('/leave/validate', payload),
  applyLop:     (payload)                   => api.post('/leave/apply-lop', payload),

  // Drafts — saved but not yet submitted. Validation runs only on submit.
  draftCreate:  (payload)                   => api.post('/leave/draft', payload),
  draftList:    ()                          => api.get('/leave/drafts'),
  draftUpdate:  (id, payload)               => api.put('/leave/' + id + '/draft', payload),
  draftSubmit:  (id)                        => api.post('/leave/' + id + '/submit'),
  draftDelete:  (id)                        => api.delete('/leave/' + id + '/draft'),

  approve:      (id)                        => api.post('/leave/' + id + '/approve'),
  reject:       (id, reason)                => api.post('/leave/' + id + '/reject', { reason }),
  cancel:       (id)                        => api.post('/leave/' + id + '/cancel'),
  approveCancel:(id)                        => api.post('/leave/' + id + '/approve-cancel'),
  myBalance:    ()                          => api.get('/leave/balance/me').then(filterBalances),
  balanceFor:   (employeeId)                => api.get('/leave/balance/' + employeeId).then(filterBalances),

  // Comp-off
  compOffList:    (params)                  => api.get('/leave/comp-off/list' + buildQs(params)),
  compOffGrant:   (payload)                 => api.post('/leave/comp-off/grant', payload),
  compOffApprove: (id)                      => api.post('/leave/comp-off/' + id + '/approve'),
  compOffReject:  (id, reason)              => api.post('/leave/comp-off/' + id + '/reject', { reason }),

  // Manual scheduler trigger (admin only)
  schedulerRun:   ()                        => api.post('/leave/scheduler/run'),

  // Admin maintenance: wipe all leave activity
  adminCleanup:   ()                        => api.post('/leave/admin/cleanup'),
};

// Delegate assignments + SLA admin (Phase 2).
export const delegateApi = {
  list:        (params)            => api.get('/delegates' + buildQs(params)),
  create:      (payload)           => api.post('/delegates', payload),
  deactivate:  (id)                => api.delete('/delegates/' + id),
  runSla:      ()                  => api.post('/delegates/sla/run'),
};

// SLA level helper — used by leave row UI to colour-tag escalation state.
// Levels mirror sla_escalation_level on the backend:
//   0 = fresh, 1 = 24h reminder, 2 = 48h skip-level, 3 = 72h HR intervention.
export function describeSlaLevel(level) {
  switch (Number(level || 0)) {
    case 1: return { label: 'Reminder sent (24h)',     tone: 'amber' };
    case 2: return { label: 'Escalated (48h)',         tone: 'orange' };
    case 3: return { label: 'HR intervention (72h)',   tone: 'rose'  };
    default: return null;
  }
}

// Payroll-sync admin API + status helper (Phase 3).
export const payrollSyncApi = {
  pending:  ()                          => api.get('/leave/payroll/pending'),
  retry:    ()                          => api.post('/leave/payroll/retry'),
  reset:    (id, payload)               => api.post('/leave/' + id + '/payroll/reset', payload || {}),
};

// Document upload + admin policy APIs (Phase 4).
export const leaveDocsApi = {
  list:     (requestId)            => api.get('/leave/' + requestId + '/documents'),
  upload:   (requestId, file)      => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/leave/' + requestId + '/documents', fd);
  },
  remove:   (docId)                => api.delete('/leave/documents/' + docId),
  downloadUrl: (docId)             => '/leave/documents/' + docId + '/download',
};

export const leavePolicyApi = {
  capacityList:    (params)        => api.get('/leave/policies/team-capacity' + buildQs(params)),
  capacityUpsert:  (payload)       => api.post('/leave/policies/team-capacity', payload),
  capacityDelete:  (id)            => api.delete('/leave/policies/team-capacity/' + id),
  blackoutList:    (params)        => api.get('/leave/policies/blackout' + buildQs(params)),
  blackoutCreate:  (payload)       => api.post('/leave/policies/blackout', payload),
  blackoutDelete:  (id)            => api.delete('/leave/policies/blackout/' + id),
};

export function describeScanStatus(status) {
  switch ((status || '').toLowerCase()) {
    case 'clean':       return { label: 'Scanned clean',     tone: 'emerald' };
    case 'pending':     return { label: 'Scanning…',          tone: 'slate'   };
    case 'infected':    return { label: 'Infected (blocked)', tone: 'rose'    };
    case 'scan_failed': return { label: 'Scan failed',        tone: 'amber'   };
    default: return null;
  }
}

export function describePayrollSync(status) {
  switch ((status || 'na').toLowerCase()) {
    case 'pending': return { label: 'Payroll sync pending', tone: 'amber' };
    case 'failed':  return { label: 'Payroll sync failed',  tone: 'rose'  };
    case 'synced':  return { label: 'Payroll synced',       tone: 'emerald' };
    default:        return null;
  }
}

export const attendanceApi = {
  list: (params)  => api.get('/attendance' + buildQs(params)),
  mark: (payload) => api.post('/attendance', payload),
};

function buildQs(params) {
  if (!params) return '';
  const e = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== false);
  if (!e.length) return '';
  return '?' + e.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}
