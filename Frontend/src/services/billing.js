// Billing + project costing API client (PMO / Finance).
import { api } from './api';

function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}

export const billingApi = {
  /** Billing summary grouped by project (admin only). params: { start, end, project_id? } */
  summary: (params) => api.get('/billing/summary' + buildQs(params)),

  /** Download billing data as CSV. params: { start, end, project_id? } */
  exportCsv: (params) => api.get('/billing/export' + buildQs(params)),

  /** Per-employee project costing breakdown (admin only). params: { start, end, project_id?, department_id? } */
  projectCosting: (params) => api.get('/billing/project-costing' + buildQs(params)),
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

export default billingApi;
