// Thin API client for the Policies module.
//
// Mirrors src/services/announcements.js — wraps the fetch-based `api` helper
// from ./api so JWT and 401-handling stay consistent. Anything that talks to
// the policies endpoints should import from this file (NEVER call /policies
// directly from a component).

import { api, API_BASE_URL, getToken } from './api';

function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== ''
  );
  if (!entries.length) return '';
  return (
    '?' +
    entries
      .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
      .join('&')
  );
}

/**
 * Resolve a server-relative PDF path into a full URL the browser can fetch.
 *
 * Three flavours of pdf_path show up in the wild:
 *   1. Legacy frontend asset:   "/policies/foo.pdf"  → served by Vite (same origin)
 *   2. Backend upload:          "/uploads/policies/12/v1_foo.pdf" → backend
 *   3. Absolute URL:            "https://…"          → use as-is
 */
export function policyPdfUrl(pdfPath) {
  if (!pdfPath) return null;
  if (/^https?:\/\//i.test(pdfPath)) return pdfPath;
  if (pdfPath.startsWith('/uploads/')) return API_BASE_URL + pdfPath;
  return pdfPath;  // /policies/foo.pdf — served by the frontend dev server
}

/**
 * Upload a PDF file for a specific policy + version. Bypasses the JSON helper
 * because we need multipart/form-data with the JWT attached.
 */
async function uploadPdf(policyId, versionId, file) {
  const url =
    API_BASE_URL +
    `/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(versionId)}/upload`;
  const form = new FormData();
  form.append('file', file);
  const tok = getToken();
  const res = await fetch(url, {
    method: 'POST',
    headers: { ...(tok ? { Authorization: 'Bearer ' + tok } : {}) },
    body: form,
  });
  let data = null;
  try { data = await res.json(); } catch { /* noop */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || res.statusText || 'Upload failed');
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

/**
 * Convenience upload that targets the policy's current/latest version.
 * Used when the admin creates a brand-new policy and uploads its first PDF in
 * one go.
 */
async function uploadPdfToLatest(policyId, file) {
  const url = API_BASE_URL + `/policies/${encodeURIComponent(policyId)}/upload`;
  const form = new FormData();
  form.append('file', file);
  const tok = getToken();
  const res = await fetch(url, {
    method: 'POST',
    headers: { ...(tok ? { Authorization: 'Bearer ' + tok } : {}) },
    body: form,
  });
  let data = null;
  try { data = await res.json(); } catch { /* noop */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || res.statusText || 'Upload failed');
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const policiesApi = {
  // Listing & detail
  list:        (params) => api.get('/policies' + buildQs(params)),
  one:         (id)     => api.get(`/policies/${id}`),

  // CRUD
  create:      (payload)         => api.post('/policies', payload),
  update:      (id, payload)     => api.patch(`/policies/${id}`, payload),
  remove:      (id)              => api.delete(`/policies/${id}`),

  // Lifecycle
  publish:     (id) => api.post(`/policies/${id}/publish`),
  archive:     (id) => api.post(`/policies/${id}/archive`),
  reactivate:  (id) => api.post(`/policies/${id}/reactivate`),

  // Versions
  listVersions:   (id)               => api.get(`/policies/${id}/versions`),
  createVersion:  (id, payload)      => api.post(`/policies/${id}/versions`, payload),
  publishVersion: (id, versionId)    => api.post(`/policies/${id}/versions/${versionId}/publish`),

  // Uploads
  uploadPdf,
  uploadPdfToLatest,

  // Categories
  categories:       ()        => api.get('/policies/categories'),
  createCategory:   (payload) => api.post('/policies/categories', payload),

  // Acknowledgement
  acknowledge:      (id) => api.post(`/policies/${id}/acknowledge`),
  acknowledgements: (id, versionId) =>
    api.get(`/policies/${id}/acknowledgements` + buildQs({ version_id: versionId })),

  // Analytics
  analytics: (id) => api.get(`/policies/${id}/analytics`),
};

export default policiesApi;
