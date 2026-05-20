// Thin API client backed by fetch. Reads JWT from localStorage and attaches it
// as the Authorization header. Surfaces network failures with a clear message.

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'hrms.auth.token';
const USER_KEY  = 'hrms.auth.user';

export const API_BASE_URL = BASE_URL;

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else   localStorage.removeItem(TOKEN_KEY);
}

async function request(method, path, { body, headers, signal } = {}) {
  const url = path.startsWith('http') ? path : BASE_URL + path;
  const tok = getToken();
  // Don't set Content-Type for FormData — the browser sets the multipart
  // boundary itself. Same for plain JSON bodies otherwise.
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const finalHeaders = {
    'Accept': 'application/json',
    ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
    ...(tok ? { 'Authorization': 'Bearer ' + tok } : {}),
    ...(headers || {}),
  };

  let res;
  try {
    res = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : (isForm ? body : JSON.stringify(body)),
      signal,
    });
  } catch (err) {
    const e = new Error(
      'Cannot reach backend at ' + BASE_URL + '. Make sure the FastAPI server is running (uvicorn app.main:app --reload --port 8000).'
    );
    e.network = true;
    e.cause = err;
    throw e;
  }

  let data = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    try { data = await res.json(); } catch { data = null; }
  } else {
    try { data = await res.text(); } catch { data = null; }
  }

  if (!res.ok) {
    const err = new Error(
      (data && data.detail) || (data && data.message) || res.statusText || ('HTTP ' + res.status)
    );
    err.status = res.status;
    err.data = data;

    // 401 on any authed endpoint (other than the auth endpoints themselves)
    // means the session is stale. Wipe localStorage and bounce to /login.
    const isAuthPath =
      path.endsWith('/auth/login') ||
      path.endsWith('/auth/verify-otp') ||
      path.endsWith('/auth/resend-otp');
    if (res.status === 401 && !isAuthPath) {
      try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      } catch { /* noop */ }
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }
    throw err;
  }
  return data;
}

export const api = {
  get:    (p, opts)        => request('GET',    p, opts),
  post:   (p, body, opts)  => request('POST',   p, { ...(opts || {}), body }),
  put:    (p, body, opts)  => request('PUT',    p, { ...(opts || {}), body }),
  patch:  (p, body, opts)  => request('PATCH',  p, { ...(opts || {}), body }),
  delete: (p, opts)        => request('DELETE', p, opts),
};

export const auth = {
  // Step 1: validate credentials. The core /auth/login endpoint is 2FA and
  // authenticates against the `employees` table only. Candidates (and legacy
  // portal users) live in the `users` table and are served by /api/v1/auth/login,
  // which issues a JWT directly (no OTP). On a 401 from the core endpoint, we
  // transparently fall back so the same form works for everyone.
  login: async (email, password) => {
    try {
      return await api.post('/auth/login', { email, password });
    } catch (err) {
      if (err?.status !== 401) throw err;
      let resp;
      try {
        resp = await api.post('/api/v1/auth/login', { email, password });
      } catch (err2) {
        // Both endpoints rejected the credentials -- surface the original 401.
        throw (err2?.status === 401) ? err : err2;
      }
      // Legacy endpoint returns { success, message, data: {...} } in two
      // shapes depending on which path matched:
      //
      //   Path A (employees) → 2FA REQUIRED. ``data`` carries
      //     { requires_2fa: true, user_id, ... }. We must NOT store a
      //     token; the OTP step is mandatory. Treat this identically to
      //     the Core /auth/login 200 response so the caller's existing
      //     OTP flow fires.
      //
      //   Path B (candidates) → direct login. ``data`` carries
      //     { access_token, role, ... } — unchanged historical behaviour.
      const payload = resp?.data || resp;

      // 2FA-required shape (employees coming through the legacy fallback).
      if (payload?.requires_2fa && payload?.user_id) {
        return {
          success:      true,
          requires_2fa: true,
          user_id:      payload.user_id,
        };
      }

      // Direct-token shape (candidate portal).
      if (!payload?.access_token) throw err;
      setToken(payload.access_token);
      const u = {
        id:           payload.employeeId ?? payload.candidateId ?? null,
        email:        payload.email || email,
        role:         payload.role,
        name:         payload.name,
        candidateId:  payload.candidateId ?? null,
        employeeId:   payload.employeeId ?? null,
        employeeCode: payload.employeeCode ?? null,
      };
      try { localStorage.setItem(USER_KEY, JSON.stringify(u)); } catch { /* noop */ }
      return { success: true, requires_2fa: false, direct_login: true, user: u };
    }
  },
  // Step 2 of 2FA: verify OTP. Server returns access_token + token_type on success.
  verifyOtp: (userId, otp)     => api.post('/auth/verify-otp', { user_id: userId, otp }),
  // Resend OTP for an in-progress 2FA flow.
  resendOtp: (userId)          => api.post('/auth/resend-otp', { user_id: userId }),
  me:        ()                => api.get('/auth/me'),
};

export default api;
