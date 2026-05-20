// Timesheet API client.
import { api } from './api';

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
  create:   (payload)               => api.post('/timesheet', payload),
  edit:     (id, payload)           => api.patch(`/timesheet/${id}`, payload),
  submit:   (id)                    => api.post(`/timesheet/${id}/submit`, {}),
  review:   (id, payload)           => api.post(`/timesheet/${id}/review`, payload),
  payrollSync: (id)                 => api.post(`/timesheet/${id}/payroll-sync`, {}),
};

export default timesheet;
