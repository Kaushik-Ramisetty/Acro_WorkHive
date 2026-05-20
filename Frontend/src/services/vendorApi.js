/**
 * vendorApi.js — API helpers for the BGV vendor review portal.
 *
 * These endpoints are public (token-based auth — no user login required).
 * Token validation, expiry, and one-time-use enforcement happen on the backend.
 *
 * Base URL: import.meta.env.VITE_API_BASE_URL (default: http://localhost:8001)
 */

import { BASE } from '../config/api';

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
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
    const msg = json.detail || json.message || `HTTP ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }

  return json.data !== undefined ? json.data : json;
}

/**
 * GET /api/v1/bgv/vendor/:token
 * Load candidate details and document URLs for the vendor review portal.
 * Validates that the token is valid, unexpired, and unused.
 *
 * @param {string} token  Secure token from the email link.
 * @returns {{ candidate, documents, token_expires_at }}
 */
export const getVendorBgvDetails = (token) =>
  request('GET', `/api/v1/bgv/vendor/${encodeURIComponent(token)}`);

/**
 * POST /api/v1/bgv/vendor/:token/submit
 * Vendor submits their BGV decision. Token is consumed after this call.
 *
 * @param {string}      token    Secure token from the email link.
 * @param {'CLEAR'|'FAILED'} status  BGV result.
 * @param {string|null} remarks  Optional notes from the vendor.
 * @returns {{ bgv_status, completed_at, remarks }}
 */
export const submitVendorBgvResult = (token, status, remarks = null) =>
  request('POST', `/api/v1/bgv/vendor/${encodeURIComponent(token)}/submit`, {
    status,
    remarks: remarks || null,
  });
