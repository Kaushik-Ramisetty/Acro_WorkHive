/**
 * Final Settlement (FF) API client.
 */
import { api } from './api';

const BASE = '/finance/ff';

export const ffApi = {
  list: (params = {}) => {
    const pairs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
    const qs = pairs.length ? '?' + new URLSearchParams(pairs).toString() : '';
    return api.get(`${BASE}${qs}`);
  },

  create: (body) => api.post(BASE, body),

  get: (ffId) => api.get(`${BASE}/${ffId}`),

  calculate: (ffId, body) => api.post(`${BASE}/${ffId}/calculate`, body),

  submit: (ffId) => api.post(`${BASE}/${ffId}/submit`, {}),

  approve: (ffId, remarks = '') => api.post(`${BASE}/${ffId}/approve`, { remarks }),

  reject: (ffId) => api.post(`${BASE}/${ffId}/reject`, {}),

  markPaid: (ffId, paid_date, payment_reference = '') =>
    api.post(`${BASE}/${ffId}/mark-paid`, { paid_date, payment_reference }),

  cancel: (ffId) => api.post(`${BASE}/${ffId}/cancel`, {}),

  statementUrl: (ffId) => `${BASE}/${ffId}/statement`,

  // PDF download
  pdfUrl: (ffId) => `${BASE}/${ffId}/pdf`,
};

export default ffApi;
