// Utilization engine API client.
import { api } from './api';

function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}

export const utilizationApi = {
  /** Employee's own utilization for a date range. */
  me: (params) => api.get('/utilization/me' + buildQs(params)),

  /** Team utilization summary (manager/admin). params: { start, end, department_id?, employee_id? } */
  team: (params) => api.get('/utilization/team' + buildQs(params)),
};

export default utilizationApi;
