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
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        location_lat: pos.coords.latitude,
        location_lng: pos.coords.longitude,
      }),
      () => resolve({}),
      { timeout: 3000, maximumAge: 30000 },
    );
  });
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
};

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

export default { attendance, regularization };
