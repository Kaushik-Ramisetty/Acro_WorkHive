/**
 * onboardingApi.js — Centralised API helpers for the Onboarding module.
 *
 * Backend wraps every response in: { "success": bool, "message": str, "data": <payload> }
 * This module unwraps that envelope so callers always get the actual payload.
 *
 * Base URL: import.meta.env.VITE_API_BASE_URL  (default: http://localhost:8001)
 */

import { BASE } from '../config/api';
import { authHeaders } from '../config/auth';

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

async function request(method, path, body) {
  // authHeaders() injects `Authorization: Bearer <token>` when a session is
  // present, otherwise it returns just the Content-Type. Either way the
  // backend gets a properly-formed request.
  const opts = {
    method,
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
    const detail = json.detail;
    if (Array.isArray(detail)) {
      const msg = detail
        .map((e) => {
          const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : '';
          return field ? `${field}: ${e.msg}` : e.msg;
        })
        .join(', ');
      throw new Error(msg);
    }
    throw new Error(json.message || (typeof detail === 'string' ? detail : null) || `HTTP ${res.status}`);
  }

  return json.data !== undefined ? json.data : json;
}

// ─── Candidates ───────────────────────────────────────────────────────────────

export const getCandidates  = (status) =>
  request('GET', `/candidates${status ? `?status=${status}` : ''}`);
export const getCandidate   = (id) => request('GET', `/candidates/${id}`);
export const createCandidate = (data) => request('POST', '/candidates', data);

// ─── Offer ────────────────────────────────────────────────────────────────────

export const generateOffer  = (id)           => request('POST', `/offer/generate/${id}`);
export const sendOfferEmail = (id, payload)  => request('POST', `/offer/send/${id}`, payload || {});
export const acceptOffer    = (id)           => request('POST', `/offer/accept/${id}`);
export const rejectOffer    = (id)           => request('POST', `/offer/reject/${id}`);

// ─── Documents ────────────────────────────────────────────────────────────────

export const uploadDocuments = async (candidateId, docType, files) => {
  const form = new FormData();
  form.append('candidate_id', String(candidateId));
  form.append('doc_type', docType || 'general');
  for (const f of files) form.append('files', f);

  let res;
  try {
    // No Content-Type — the browser sets multipart/form-data with a boundary.
    // Only attach Authorization (and any extras returned by authHeaders).
    res = await fetch(`${BASE}/documents/upload`, {
      method: 'POST',
      body: form,
      headers: authHeaders(),
    });
  } catch {
    throw new Error('Cannot reach backend.');
  }
  const json = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(json.message || json.detail || 'Upload failed');
  return json.data !== undefined ? json.data : json;
};

export const getDocuments = (candidateId) => request('GET', `/documents/${candidateId}`);

/**
 * PATCH /documents/{docId}/verify
 * HR Admin verifies (approved=true) or rejects (approved=false) a candidate document.
 * Sends a JSON body — backend now accepts VerifyDocumentPayload instead of Form data.
 * Creates an audit-log row (actor, action, timestamp) on the backend.
 *
 * @param {number}       docId    - CandidateDocument.id
 * @param {boolean}      approved - true → VERIFIED, false → REJECTED
 * @param {string|null}  remarks  - optional note to store with the document
 */
export const verifyDocument = (docId, approved, remarks = null) =>
  request('PATCH', `/documents/${docId}/verify`, { approved, remarks });

// ─── BGV ──────────────────────────────────────────────────────────────────────

export const getBgvStatus  = (id)             => request('GET',   `/bgv/${id}`);
export const startBgv      = (id, vendor)     => request('POST',  `/bgv/start/${id}`, { vendor_name: vendor || null });
export const updateBgv     = (id, st, rem)    => request('PATCH', `/bgv/update/${id}`, { status: st, remarks: rem || null });
export const updateBgvStatus = (id, st, rem)  => request('PATCH', `/api/v1/bgv/${id}`, { status: st, remarks: rem || null });

// ─── Convert → Employee ───────────────────────────────────────────────────────

/**
 * POST /convert/{candidate_id}
 * Full conversion: writes to employees table with employees.Password (bcrypt).
 * Payload matches ConvertRequest schema in convert.py.
 */
export const convertToEmployee = (candidateId, payload) =>
  request('POST', `/convert/${candidateId}`, payload);

/**
 * POST /convert-to-employee/{candidate_id}  (legacy — OnboardedEmployee table)
 */
export const convertToEmployeeFull = (candidateId, payload) =>
  request('POST', `/convert-to-employee/${candidateId}`, payload);

// ─── Reference data ───────────────────────────────────────────────────────────

/** GET /departments/ */
export const getDepartments = () => request('GET', '/departments/');

/** GET /designations/?department_id=X */
export const getDesignations = (departmentId = null) =>
  request('GET', `/designations/${departmentId ? `?department_id=${encodeURIComponent(departmentId)}` : ''}`);

/**
 * GET /employees/active?q=...  — search active employees (new endpoint).
 * Falls back to legacy /employees/search?q=... if the new one is unavailable.
 */
export const searchManagers = async (q) => {
  try {
    return await request('GET', `/employees/active?q=${encodeURIComponent(q)}`);
  } catch {
    return request('GET', `/employees/search?q=${encodeURIComponent(q)}`);
  }
};

// ─── Employee lifecycle ───────────────────────────────────────────────────────

export const activateEmployee = (id) => request('POST',  `/employees/${id}/activate`);
export const markJoined       = (id) => request('POST',  `/employees/${id}/mark-joined`);
export const markNotJoined    = (id) => request('POST',  `/employees/${id}/mark-not-joined`);
export const assignManager    = (id, name, mgrid) =>
  request('PATCH', `/onboarding/employees/${id}/assign-manager`, {
    manager_name: name, manager_id: mgrid || null,
  });

// ─── Employee detail ──────────────────────────────────────────────────────────

/**
 * GET /employees/{id}  — fetch a single employee record including designation/dept.
 * Used to display employee_code and reporting_manager after conversion.
 */
export const getEmployeeDetails = (employeeId) =>
  request('GET', `/employees/${employeeId}`);

/**
 * GET /employees/{id}/leave-balances — current-year leave balances for dashboard.
 */
export const getLeaveBalances = (employeeId) =>
  request('GET', `/employees/${employeeId}/leave-balances`);

/**
 * POST /candidates/{id}/not-joined
 * Candidate-centric "Mark Not Joined" — works whether or not an OnboardedEmployee
 * or Employee row exists. No empId required, only the candidate id.
 */
export const markCandidateNotJoined = (candidateId) =>
  request('POST', `/candidates/${candidateId}/not-joined`);

// ─── BGV — token-based vendor portal flow ────────────────────────────────────

/**
 * POST /api/v1/bgv/initiate
 * HR Admin triggers BGV after all required documents are VERIFIED.
 *
 * Business rules enforced on the backend:
 *   1. Only admin / hr role may call this (JWT role check).
 *   2. All required documents (bgv_form, aadhar, pan, qualification,
 *      address_proof, cif) must be in VERIFIED state — returns 409 if not.
 *   3. Cannot initiate BGV twice for the same candidate — returns 409.
 *
 * Creates a BGVCheck record, generates a secure vendor token, and sends the
 * vendor link email. Returns { id, candidate_id, status, initiated_at,
 * vendor_link, expires_at }.
 *
 * @param {number} candidateId - Candidate DB id
 */
export const initiateBgv = (candidateId) =>
  request('POST', '/api/v1/bgv/initiate', { candidate_id: candidateId });
