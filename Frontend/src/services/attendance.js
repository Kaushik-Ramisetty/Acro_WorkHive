// Attendance + regularization API client.
import { api } from './api';

function captureClientContext() {
  try {
    return {
      device_info: navigator.userAgent || 'browser',
      source: 'web',
    };
  } catch { return { source: 'web' }; }
}

async function captureLocation() {
  if (!navigator.geolocation) return {};
  // The Geolocation API's `timeout` option only applies after permission is
  // granted — not to the permission prompt itself.  A manual race-timeout
  // ensures we never block the punch request indefinitely while the browser
  // permission dialog sits unnoticed.
  const geoPromise = new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        location_lat: pos.coords.latitude,
        location_lng: pos.coords.longitude,
      }),
      () => resolve({}),
      { timeout: 3000, maximumAge: 30000 },
    );
  });
  const fallback = new Promise((resolve) => setTimeout(() => resolve({}), 4000));
  return Promise.race([geoPromise, fallback]);
}

export const attendance = {
  async checkIn() {
    const loc = await captureLocation();
    return api.post('/attendance/check-in', { ...captureClientContext(), ...loc });
  },
  async checkOut() {
    const loc = await captureLocation();
    return api.post('/attendance/check-out', { ...captureClientContext(), ...loc });
  },
  today:    () => api.get('/attendance/today'),
  records:  (params = {}) => {
    const qs = new URLSearchParams();
    if (params.employee_id) qs.set('employee_id', params.employee_id);
    if (params.start) qs.set('start', params.start);
    if (params.end)   qs.set('end',   params.end);
    return api.get('/attendance/records' + (qs.toString() ? `?${qs}` : ''));
  },
  logs:     (params = {}) => {
    const qs = new URLSearchParams();
    if (params.employee_id) qs.set('employee_id', params.employee_id);
    if (params.start) qs.set('start', params.start);
    if (params.end)   qs.set('end',   params.end);
    return api.get('/attendance/logs' + (qs.toString() ? `?${qs}` : ''));
  },
  exceptions: (only_open = true) => api.get(`/attendance/exceptions?only_open=${only_open}`),
  process:  (employee_id, on) => api.post(`/attendance/process?employee_id=${employee_id}&on=${on}`),
  adminOverride: (payload) => api.patch('/attendance/admin/override', payload),

  effectiveHours: (date) => api.get(`/attendance/effective-hours?date=${date}`),
  weeklyHours: (weekStart) => api.get(`/attendance/weekly-hours?week_start=${weekStart}`),
};

export const managerApi = {
  attendanceDashboard: (targetDate) => {
    const qs = targetDate ? `?target_date=${targetDate}` : '';
    return api.get(`/manager/attendance-dashboard${qs}`);
  },
  team: () => api.get('/manager/team'),
  leaveOverview: () => api.get('/manager/leave-overview'),
  exportWeekly: (params = {}) => {
    const qs = _buildQs(params);
    return api.get(`/manager/attendance/export/weekly${qs}`);
  },
  exportMonthly: (params = {}) => {
    const qs = _buildQs(params);
    return api.get(`/manager/attendance/export/monthly${qs}`);
  },
};

/** Save a CSV string returned by the server as a browser file download. */
export function triggerCsvDownload(csvText, filename) {
  const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function _buildQs(params) {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '');
  return entries.length ? '?' + new URLSearchParams(entries).toString() : '';
}

export const regularization = {
  submit:   (payload) => api.post('/attendance/regularization', payload),
  list:     (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.employee_id) qs.set('employee_id', params.employee_id);
    return api.get('/attendance/regularization' + (qs.toString() ? `?${qs}` : ''));
  },
  review:   (id, payload) => api.post(`/attendance/regularization/${id}/review`, payload),
};

/** Comp-off self-service (employee). */
export const compOffApi = {
  request: (payload) => api.post('/attendance/comp-off/request', payload),
  list:    () => api.get('/attendance/comp-off'),
};

/** Overtime request (employee). */
export const overtimeApi = {
  submit: (payload) => api.post('/attendance/overtime', payload),
  list:   () => api.get('/attendance/overtime'),
};

/** Weekly-off change request (employee). */
export const weeklyOffApi = {
  submit: (payload) => api.post('/attendance/weekly-off-request', payload),
  list:   () => api.get('/attendance/weekly-off-request'),
};

export default { attendance, regularization, compOffApi, overtimeApi, weeklyOffApi };
