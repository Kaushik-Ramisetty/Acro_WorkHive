/**
 * Compatibility shim. Onboarding-side services import authHeaders / getAccessToken
 * from this file. Both now delegate to Core's services/api.js token store, so
 * the unified app has a SINGLE token in localStorage (`hrms.auth.token`) used
 * by every HTTP call from either module.
 */
import { getToken } from '../services/api';

export function getAccessToken() {
  return getToken();
}

export function authHeaders(extra = {}) {
  const token = getAccessToken();
  return token
    ? { ...extra, Authorization: `Bearer ${token}` }
    : { ...extra };
}

export function getStoredSession() {
  // Kept for back-compat with any code that called this helper. The full
  // user blob lives in localStorage['hrms.auth.user'] (written by Core's
  // AuthContext after /auth/me).
  try {
    const raw = localStorage.getItem('hrms.auth.user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
