// Response normalizer — used **only when explicitly opted into**.
//
// The backend currently emits two response shapes:
//   * Core HRMS  → raw payload (e.g. { id, name, ... })
//   * Onboarding → envelope    ({ success, message, data })
//
// This module exposes pure functions that accept either shape and return
// a consistent representation. Existing services already cope with both
// styles; this helper just gives new code a single place to do the
// unwrapping without re-implementing the conditional each time.
//
// IMPORTANT: do not adopt this helper into call sites that currently
// depend on raw envelope access (e.g. checking `resp.success`). It is
// strictly an additive convenience for new modules.

/**
 * @typedef {Object} EnvelopeMeta
 * @property {boolean} success
 * @property {string|null} message
 * @property {string|null} code
 */

/**
 * Extract the meaningful payload from any backend response.
 *
 * - Onboarding envelope: returns the inner `.data`.
 * - Core raw payload: returns the response unchanged.
 * - Null / undefined: returns the input as-is.
 *
 * @template T
 * @param {T | { success?: boolean, data?: T, message?: string }} resp
 * @returns {T}
 */
export function unwrap(resp) {
  if (resp && typeof resp === 'object' && 'data' in resp && 'success' in resp) {
    return /** @type {T} */ (resp.data);
  }
  return /** @type {T} */ (resp);
}

/**
 * Return metadata about the response. For raw Core payloads, `success`
 * defaults to true and `message` / `code` are null.
 *
 * @param {*} resp
 * @returns {EnvelopeMeta}
 */
export function meta(resp) {
  if (resp && typeof resp === 'object' && 'success' in resp) {
    return {
      success: !!resp.success,
      message: resp.message || null,
      code:    resp.code    || null,
    };
  }
  return { success: true, message: null, code: null };
}

/**
 * Extract a user-readable error message from a thrown fetch error.
 * Mirrors how the existing `api.js` builds error messages, but exposes
 * the logic so components/services can reuse it without duplicating it.
 *
 * @param {unknown} err
 * @returns {string}
 */
export function errorMessage(err) {
  if (!err) return 'Unknown error.';
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object') {
    // Network-layer error from services/api.js
    if (err.network && err.message) return err.message;
    // FastAPI HTTPException — server returns { detail: "..." }
    if (err.data && err.data.detail) return err.data.detail;
    // Onboarding envelope — server returns { success:false, message:"..." }
    if (err.data && err.data.message) return err.data.message;
    if (err.message) return err.message;
  }
  return 'Request failed.';
}

/**
 * Lift `status` off a fetch error, returning null when unavailable.
 *
 * @param {unknown} err
 * @returns {number | null}
 */
export function errorStatus(err) {
  if (err && typeof err === 'object' && typeof err.status === 'number') {
    return err.status;
  }
  return null;
}

export default { unwrap, meta, errorMessage, errorStatus };
