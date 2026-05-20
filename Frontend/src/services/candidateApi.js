/**
 * candidateApi.js — API helpers for the Candidate self-service portal.
 *
 * All backend responses follow { success, message, data } — this module
 * unwraps that envelope automatically (same pattern as onboardingApi.js).
 *
 * Base URL: import.meta.env.VITE_API_BASE_URL (default: http://localhost:8001)
 */

import { BASE } from '../config/api';
import { authHeaders } from '../config/auth';

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

async function request(method, path, body) {
  const opts = {
    method,
    // Attach Authorization: Bearer <jwt> when the candidate is signed in.
    // The candidate-portal endpoints now require the JWT subject to match
    // the candidate id in the URL.
    headers: authHeaders({ 'Content-Type': 'application/json' }),
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch {
    throw new Error(`Cannot reach backend at ${BASE}. Is the server running?`);
  }

  const json = await res.json().catch(() => ({ detail: res.statusText }));

  if (!res.ok) {
    const msg = json.message || json.detail || `HTTP ${res.status}`;
    throw new Error(Array.isArray(msg) ? msg.map((e) => e.msg).join(', ') : msg);
  }

  return json.data !== undefined ? json.data : json;
}

// ─── Candidate Progress ───────────────────────────────────────────────────────

/**
 * GET /api/v1/candidate/status/:id
 * Returns steps[], docs_uploaded_count, all_docs_uploaded, bgv_status, name, etc.
 */
export const getCandidateStatus = (candidateId) =>
  request('GET', `/api/v1/candidate/status/${candidateId}`);

export const getCandidateProgress = getCandidateStatus;

// ─── Document Upload ──────────────────────────────────────────────────────────

/**
 * POST /api/v1/candidate/documents/upload
 *
 * @param {number}          candidateId   - candidate DB id
 * @param {string}          documentType  - 'aadhar' | 'pan' | 'degree' | 'exp' | 'photo' | 'bank'
 * @param {FileList|File[]} files         - files to upload (PDF / JPG / PNG)
 */
export const uploadCandidateDocument = async (candidateId, documentType, files) => {
  const form = new FormData();
  form.append('candidate_id', String(candidateId));
  form.append('document_type', documentType);
  // Backend accepts one file at a time; take the first file from the array
  form.append('file', files[0]);

  let res;
  try {
    res = await fetch(`${BASE}/api/v1/candidate/documents/upload`, {
      method: 'POST',
      body: form,
      headers: authHeaders(),  // bearer only; browser sets multipart boundary itself
    });
  } catch {
    throw new Error('Cannot reach backend. Is the server running?');
  }

  const json = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(json.message || json.detail || 'Upload failed');
  return json.data !== undefined ? json.data : json;
};

// ─── Document List ────────────────────────────────────────────────────────────

/**
 * GET /api/v1/candidate/documents/:candidateId
 * Returns the list of all documents uploaded by the candidate.
 */
export const getCandidateDocuments = (candidateId) =>
  request('GET', `/api/v1/candidate/documents/${candidateId}`);

// ─── Submit ──────────────────────────────────────────────────────────────────

/**
 * POST /api/v1/candidate/submit/:candidateId
 * Candidate finalizes their document submission. Returns the new status
 * (DOCS_SUBMITTED on first call; idempotent on subsequent calls).
 *
 * Backend rejects with 409 if mandatory docs are missing or BGV has
 * already started.
 *
 * @param {number} candidateId
 * @returns {{ candidate_id, status, submitted, already_submitted }}
 */
export const submitCandidateDocuments = (candidateId) =>
  request('POST', `/api/v1/candidate/submit/${candidateId}`);

// ─── BGV ─────────────────────────────────────────────────────────────────────

/**
 * GET /api/v1/bgv/:candidateId
 * Fetch the current BGV status for a candidate.
 * Returns { initiated, status, initiated_at, completed_at, remarks }
 */
export const getCandidateBgvStatus = (candidateId) =>
  request('GET', `/api/v1/bgv/${candidateId}`);

/**
 * POST /api/v1/bgv/initiate
 * Candidate self-initiates background verification once all 6 docs are uploaded.
 *
 * @param {number} candidateId
 */
export const initiateBgv = (candidateId) =>
  request('POST', '/api/v1/bgv/initiate', { candidate_id: candidateId });

// ─── Email-based Lookup ───────────────────────────────────────────────────────

/**
 * GET /api/v1/candidate/resolve?email=...
 * Resolves the candidate_id for a given email address.
 * Used when the session only has an email (no hardcoded candidateId).
 *
 * @param {string} email
 * @returns {{ candidate_id, name, status }}
 */
export const resolveCandidateByEmail = (email) =>
  request('GET', `/api/v1/candidate/resolve?email=${encodeURIComponent(email)}`);

// ─── Document Delete ──────────────────────────────────────────────────────────

/**
 * DELETE /api/v1/documents/:candidateId/:documentType
 * Removes an uploaded (not yet verified) document for the candidate.
 *
 * @param {number} candidateId
 * @param {string} documentType  - 'aadhar' | 'pan' | 'degree' | 'exp' | 'photo' | 'bank'
 */
export const deleteCandidateDocument = (candidateId, documentType) =>
  request('DELETE', `/api/v1/documents/${candidateId}/${documentType}`);

// ─── Admin: Candidate List ────────────────────────────────────────────────────

/**
 * GET /api/v1/admin/candidates
 * Returns all candidates with document_status + bgv_status.
 */
export const getAdminCandidates = () => request('GET', '/api/v1/admin/candidates');
