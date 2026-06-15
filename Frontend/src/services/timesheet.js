// Timesheet API client.
import { api } from './api';

function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}

export const timesheet = {
  projects: ()                      => api.get('/timesheet/projects'),
  tasks:    (project_id)            => api.get('/timesheet/tasks' + (project_id ? `?project_id=${project_id}` : '')),
  list:     (params = {})           => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.employee_id) qs.set('employee_id', params.employee_id);
    return api.get('/timesheet' + (qs.toString() ? `?${qs}` : ''));
  },
  get:      (id)                    => api.get(`/timesheet/${id}`),
  create:   (payload, opts)          => api.post('/timesheet', payload, opts),
  edit:     (id, payload)           => api.patch(`/timesheet/${id}`, payload),
  submit:   (id)                    => api.post(`/timesheet/${id}/submit`, {}),
  review:   (id, payload)           => api.post(`/timesheet/${id}/review`, payload),
  bulkReview: (payload)             => api.post('/timesheet/bulk-review', payload),
  payrollSync: (id)                 => api.post(`/timesheet/${id}/payroll-sync`, {}),

  // Monthly T&M payroll-cycle report (client_site employees only)
  monthlyReport: {
    get: () => api.get('/timesheet/monthly-report'),
    submit: (payload) => api.post('/timesheet/monthly-report', payload),
    detail: (id) => api.get(`/timesheet/${id}/monthly-detail`),
  },

  // Client manager approval page — public, no auth token needed
  clientReview: {
    info:   (token)   => api.get(`/timesheet/client-review?token=${encodeURIComponent(token)}`),
    submit: (payload) => api.post('/timesheet/client-review', payload),
  },

  // HR Admin — client_site employees only
  hrList: (params = {}) => api.get('/hr/timesheets' + buildQs(params)),
  hrSummary: () => api.get('/hr/timesheets/summary'),
  hrProjects: ()             => api.get('/hr/projects'),
  hrTasks:    (project_id)   => api.get('/hr/tasks' + (project_id ? `?project_id=${project_id}` : '')),
  hrEditEntries: (id, payload) => api.put(`/hr/timesheets/${id}/entries`, payload),
  hrExportCsv: (params = {}) => api.get('/hr/timesheets/export/csv' + buildQs(params)),
  hrGetOne: (id) => api.get(`/hr/timesheets/${id}`),
};

export default timesheet;
