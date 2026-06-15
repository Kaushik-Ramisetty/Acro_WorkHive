import { api } from './api';

export const employeesApi = {
  list:   (params)         => api.get('/admin/employees' + buildQs(params)),
  one:    (id)             => api.get('/admin/employees/' + id),
  create: (payload)        => api.post('/admin/employees', payload),
  update: (id, payload)    => api.put('/admin/employees/' + id, payload),
  remove: (id)             => api.delete('/admin/employees/' + id),
  reference: ()            => api.get('/admin/reference'),
  /** Candidates for the Reporting Manager dropdown — managers + admins only. */
  managers:  ()            => api.get('/admin/managers'),
};

function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}
