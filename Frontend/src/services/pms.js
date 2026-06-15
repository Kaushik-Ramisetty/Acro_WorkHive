// Performance Management (PMS Phase 1, 2, 3, 4 & 5) API wrapper.
// Mirrors the leave/announcements service style.
import { api, API_BASE_URL, getToken } from './api';

// Lock source discriminator — matches backend LOCK_TYPE_MANUAL / LOCK_TYPE_AUTO.
export const LOCK_TYPE = {
  MANUAL: 'manual',
  AUTO:   'auto',
};

/**
 * Returns true when the record was auto-locked by the system after the phase
 * deadline.  Auto-locked records are permanently immutable — no unlock, no
 * edit actions should be shown in the UI for any role.
 */
export const isAutoLocked = (record) =>
  record?.lock_type === LOCK_TYPE.AUTO;

const buildQs = (params) => {
  if (!params) return '';
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
};

export const PMS_STATUS = {
  DRAFT: 'draft',
  GOALS_SENT: 'goals_sent',
  UNDER_DISCUSSION: 'under_discussion',
  EMPLOYEE_CONFIRMED: 'employee_confirmed',
  MANAGER_APPROVED: 'manager_approved',
  HR_REVIEWED: 'hr_reviewed',
  GOALS_LOCKED: 'goals_locked',
};

export const PMS_STATUS_LABEL = {
  draft:              'Draft',
  goals_sent:         'Goals Sent',
  under_discussion:   'Under Discussion',
  employee_confirmed: 'Employee Confirmed',
  manager_approved:   'Manager Approved',
  hr_reviewed:        'HR Reviewed',
  goals_locked:       'Goals Locked',
};

// Status pill tone (matches the leave/attendance palette already in use).
export const PMS_STATUS_TONE = {
  draft:              { bg: '#F1F5F9', fg: '#475569' },
  goals_sent:         { bg: '#DBEAFE', fg: '#1E40AF' },
  under_discussion:   { bg: '#FEF3C7', fg: '#92400E' },
  employee_confirmed: { bg: '#E0E7FF', fg: '#3730A3' },
  manager_approved:   { bg: '#D1FAE5', fg: '#065F46' },
  hr_reviewed:        { bg: '#CFFAFE', fg: '#155E75' },
  goals_locked:       { bg: '#FEE2E2', fg: '#991B1B' },
};

// ── Phase 2: Mid-Cycle Review status constants ─────────────────────────────
export const MCR_STATUS = {
  DRAFT:          'draft',
  IN_PROGRESS:    'in_progress',
  SUBMITTED:      'submitted',
  MGR_REVIEWED:   'manager_reviewed',
  MGR_APPROVED:   'manager_approved',
  HR_REVIEWED:    'hr_reviewed',
  LOCKED:         'mid_cycle_locked',
};

export const MCR_STATUS_LABEL = {
  draft:            'Draft',
  in_progress:      'In Progress',
  submitted:        'Submitted',
  manager_reviewed: 'Manager Reviewed',
  manager_approved: 'Manager Approved',
  hr_reviewed:      'HR Reviewed',
  mid_cycle_locked: 'Locked',
};

export const MCR_STATUS_TONE = {
  draft:            { bg: '#F1F5F9', fg: '#475569' },
  in_progress:      { bg: '#FEF3C7', fg: '#92400E' },
  submitted:        { bg: '#DBEAFE', fg: '#1E40AF' },
  manager_reviewed: { bg: '#E0E7FF', fg: '#3730A3' },
  manager_approved: { bg: '#D1FAE5', fg: '#065F46' },
  hr_reviewed:      { bg: '#CFFAFE', fg: '#155E75' },
  mid_cycle_locked: { bg: '#FEE2E2', fg: '#991B1B' },
};

// ── Phase 3: End Cycle Assessment status constants ─────────────────────────
export const ECA_STATUS = {
  DRAFT:             'draft',
  SELF_ASSESSED:     'self_assessed',
  MGR_ASSESSED:      'manager_assessed',
  SUBMITTED_TO_HR:   'submitted_to_hr',
  HR_RECEIVED:       'hr_received',
  LOCKED:            'assessment_locked',
};

export const ECA_STATUS_LABEL = {
  draft:             'Draft',
  self_assessed:     'Self Assessed',
  manager_assessed:  'Manager Assessed',
  submitted_to_hr:   'Submitted to HR',
  hr_received:       'HR Received',
  assessment_locked: 'Locked',
};

export const ECA_STATUS_TONE = {
  draft:             { bg: '#F1F5F9', fg: '#475569' },
  self_assessed:     { bg: '#DBEAFE', fg: '#1E40AF' },
  manager_assessed:  { bg: '#E0E7FF', fg: '#3730A3' },
  submitted_to_hr:   { bg: '#FEF3C7', fg: '#92400E' },
  hr_received:       { bg: '#CFFAFE', fg: '#155E75' },
  assessment_locked: { bg: '#FEE2E2', fg: '#991B1B' },
};

// ── Phase 4: Normalization status constants ────────────────────────────────
export const NORM_STATUS = {
  DRAFT:          'draft',
  NORMALIZED:     'normalized',
  FROZEN:         'frozen',
  HIKE_GENERATED: 'hike_generated',
  HIKE_APPROVED:  'hike_approved',
};

export const NORM_STATUS_LABEL = {
  draft:          'Draft',
  normalized:     'Normalized',
  frozen:         'Frozen',
  hike_generated: 'Hike Generated',
  hike_approved:  'Hike Approved',
};

export const NORM_STATUS_TONE = {
  draft:          { bg: '#F1F5F9', fg: '#475569' },
  normalized:     { bg: '#DBEAFE', fg: '#1E40AF' },
  frozen:         { bg: '#E0E7FF', fg: '#3730A3' },
  hike_generated: { bg: '#FEF3C7', fg: '#92400E' },
  hike_approved:  { bg: '#D1FAE5', fg: '#065F46' },
};

// Rating labels (1–5 scale used in Phase 3 & 4).
export const RATING_LABELS = {
  1: 'Below Expectations',
  2: 'Needs Improvement',
  3: 'Meets Expectations',
  4: 'Exceeds Expectations',
  5: 'Outstanding',
};

export const pmsApi = {
  // Templates
  templates:      (params)        => api.get('/pms/templates' + buildQs(params)),
  template:       (id)            => api.get('/pms/templates/' + id),
  createTemplate: (payload)       => api.post('/pms/templates', payload),
  updateTemplate: (id, payload)   => api.put('/pms/templates/' + id, payload),
  deleteTemplate: (id)            => api.delete('/pms/templates/' + id),

  // Assignments
  assign:         (payload)       => api.post('/pms/assignments', payload),
  assignments:    (params)        => api.get('/pms/assignments' + buildQs(params)),
  assignment:     (id)            => api.get('/pms/assignments/' + id),

  // Transitions
  managerDiscuss:    (id, payload) => api.post('/pms/assignments/' + id + '/discuss',          payload || {}),
  employeeConfirm:   (id, payload) => api.post('/pms/assignments/' + id + '/employee-confirm', payload || {}),
  managerApprove:    (id, payload) => api.post('/pms/assignments/' + id + '/manager-approve',  payload || {}),
  hrReview:          (id, payload) => api.post('/pms/assignments/' + id + '/hr-review',        payload || {}),
  lock:              (id, payload) => api.post('/pms/assignments/' + id + '/lock',             payload || {}),
  unlock:            (id, payload) => api.post('/pms/assignments/' + id + '/unlock',           payload || {}),

  // Comments
  comment:        (id, body)      => api.post('/pms/assignments/' + id + '/comments', { body }),

  // Excel Import — Step 1: parse workbook, return preview structure (N designations).
  importPreview: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/pms/templates/import', fd);
  },

  // Excel Import — Step 2: commit the (possibly HR-edited) parsed structure.
  importCommit: (payload) => api.post('/pms/templates/import/commit', payload),

  // ── Phase 2: Mid-Cycle Review ──────────────────────────────────────────────

  // HR: create a mid-cycle review for an assignment.
  createMidCycleReview:  (payload)      => api.post('/pms/mid-cycle', payload),

  // List / Get.
  midCycleReviews:       (params)       => api.get('/pms/mid-cycle' + buildQs(params)),
  midCycleReview:        (id)           => api.get('/pms/mid-cycle/' + id),

  // Employee: save progress (partial update, stays in_progress).
  saveProgress:          (id, payload)  => api.put('/pms/mid-cycle/' + id + '/progress', payload),
  // Employee: final submit (advances to 'submitted').
  submitProgress:        (id, payload)  => api.post('/pms/mid-cycle/' + id + '/submit',  payload),

  // Manager transitions.
  // Save draft notes without advancing the state machine (allowed in 'submitted' and 'manager_reviewed').
  managerSaveMidCycleNotes: (id, payload) => api.put('/pms/mid-cycle/' + id + '/manager-notes', payload),
  managerReviewMidCycle: (id, payload)  => api.post('/pms/mid-cycle/' + id + '/manager-review',  payload || {}),
  managerApproveMidCycle:(id, payload)  => api.post('/pms/mid-cycle/' + id + '/manager-approve', payload || {}),

  // HR transitions.
  hrReviewMidCycle:      (id, payload)  => api.post('/pms/mid-cycle/' + id + '/hr-review', payload || {}),
  lockMidCycle:          (id, payload)  => api.post('/pms/mid-cycle/' + id + '/lock',      payload || {}),
  unlockMidCycle:        (id, payload)  => api.post('/pms/mid-cycle/' + id + '/unlock',    payload || {}),

  // Evidence.
  addEvidence:           (id, payload)  => api.post('/pms/mid-cycle/' + id + '/evidence',        payload),
  deleteEvidence:        (id, evId)     => api.delete('/pms/mid-cycle/' + id + '/evidence/' + evId),

  // Excel Export — GET the template as an .xlsx blob and trigger browser download.
  // Uses raw fetch so we can handle the blob response; api.js cannot return blobs.
  exportTemplate: async (id, filenameHint) => {
    const tok = getToken();
    const res = await fetch(API_BASE_URL + '/pms/templates/' + id + '/export', {
      method: 'GET',
      headers: {
        'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ...(tok ? { 'Authorization': 'Bearer ' + tok } : {}),
      },
    });
    if (!res.ok) {
      const msg = await res.text().catch(() => 'Export failed');
      throw new Error(msg || 'Export failed (HTTP ' + res.status + ')');
    }
    // Read filename from Content-Disposition, fall back to caller-supplied hint.
    let filename = filenameHint || ('template_' + id + '.xlsx');
    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename[^;=\n]*=([^;\n"]+)/i);
    if (match) filename = match[1].trim().replace(/^["']|["']$/g, '');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);
  },

  // ── Phase 3: End Cycle Assessment ─────────────────────────────────────────

  createAssessment:       (payload)     => api.post('/pms/end-cycle', payload),
  assessments:            (params)      => api.get('/pms/end-cycle' + buildQs(params)),
  assessment:             (id)          => api.get('/pms/end-cycle/' + id),
  selfAssess:             (id, payload) => api.post('/pms/end-cycle/' + id + '/self-assess',    payload),
  managerAssess:          (id, payload) => api.post('/pms/end-cycle/' + id + '/manager-assess', payload),
  submitAssessmentToHR:   (id, payload) => api.post('/pms/end-cycle/' + id + '/submit-to-hr',  payload || {}),
  hrReceiveAssessment:    (id, payload) => api.post('/pms/end-cycle/' + id + '/hr-receive',    payload || {}),
  lockAssessment:         (id, payload) => api.post('/pms/end-cycle/' + id + '/lock',          payload || {}),
  unlockAssessment:       (id, payload) => api.post('/pms/end-cycle/' + id + '/unlock',        payload || {}),
  updateHrNotes:          (id, notes)   => api.patch('/pms/end-cycle/' + id + '/hr-notes',    { notes: notes || '' }),

  // ── Phase 4: Normalization ────────────────────────────────────────────────

  // ── Phase 4: Normalization ────────────────────────────────────────────────
  // Eligible employees / periods — used to populate the create-session form.
  eligibleEmployees:      (params)                 => api.get('/pms/normalization/eligible-employees' + buildQs(params)),
  eligiblePeriods:        ()                       => api.get('/pms/normalization/eligible-periods'),

  createNormSession:      (payload)                => api.post('/pms/normalization', payload),
  normSessions:           ()                       => api.get('/pms/normalization'),
  normSession:            (id)                     => api.get('/pms/normalization/' + id),
  updateNormSession:      (id, payload)            => api.put('/pms/normalization/' + id, payload),
  deleteNormSession:      (id)                     => api.delete('/pms/normalization/' + id),
  addNormRecords:         (id)                     => api.post('/pms/normalization/' + id + '/add-records'),
  updateNormRecord:       (sessId, recId, payload) => api.put('/pms/normalization/' + sessId + '/records/' + recId, payload),
  normalizeSession:       (id, payload)            => api.post('/pms/normalization/' + id + '/normalize',    payload || {}),
  freezeSession:          (id, payload)            => api.post('/pms/normalization/' + id + '/freeze',       payload || {}),
  generateHike:           (id, payload)            => api.post('/pms/normalization/' + id + '/generate-hike', payload || {}),
  approveHike:            (id, payload)            => api.post('/pms/normalization/' + id + '/approve-hike', payload || {}),

  // ── Phase 5: Compensation ─────────────────────────────────────────────────

  generateRevisions:      (sessId, payload) => api.post('/pms/compensation/' + sessId + '/generate', payload),
  revisions:              (params)          => api.get('/pms/compensation' + buildQs(params)),
  revision:               (id)              => api.get('/pms/compensation/' + id),
  acknowledgeRevision:    (id)              => api.post('/pms/compensation/' + id + '/acknowledge'),
  archiveCycle:           (sessId, payload) => api.post('/pms/compensation/' + sessId + '/archive', payload || {}),

  // ── PMS Phase Settings (CHANGE 9) ────────────────────────────────────────────
  phaseSettings:      ()                      => api.get('/pms/settings/phases'),
  phaseSetting:       (phaseKey)              => api.get('/pms/settings/phases/' + phaseKey),
  updatePhaseSetting: (phaseKey, defaultDays) => api.put('/pms/settings/phases/' + phaseKey, { default_days: defaultDays }),
  computeDeadline:    (phaseKey)              => api.get('/pms/settings/phases/' + phaseKey + '/deadline'),

  // ── Bulk Phase-1 (CHANGE 8) ───────────────────────────────────────────────
  bulkHrReview:       (ids, comment) => api.post('/pms/assignments/bulk/hr-review', { ids, comment }),
  bulkLock:           (ids, comment) => api.post('/pms/assignments/bulk/lock',      { ids, comment }),
  bulkUnlock:         (ids)          => api.post('/pms/assignments/bulk/unlock',    { ids }),

  // ── Bulk Phase-2 (CHANGE 8) ───────────────────────────────────────────────
  bulkCreateMidCycle: (payload)      => api.post('/pms/mid-cycle/bulk/create',   payload),
  bulkLockMidCycle:   (ids)          => api.post('/pms/mid-cycle/bulk/hr-lock',  { ids }),

  // ── Bulk Phase-3 (CHANGE 8) ───────────────────────────────────────────────
  bulkCreateECA:      (payload)      => api.post('/pms/end-cycle/bulk/create',   payload),
  bulkLockECA:        (ids)          => api.post('/pms/end-cycle/bulk/lock',     { ids }),
};
