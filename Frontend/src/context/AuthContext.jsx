import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { auth as authApi, getToken, setToken } from '../services/api';

const STORAGE_USER = 'hrms.auth.user';

const AuthContext = createContext(null);

// Demo accounts — used as quick-fill chips on the login form.
export const DEMO_ACCOUNTS = [
  { role: 'admin',     email: 'Santhoshkumar.N@acronotics.com', password: 'Santhosh@1998', name: 'Santhosh N' },
  { role: 'manager',   email: 'Palem.Mahendra@acronotics.com',  password: 'Palem@2001',    name: 'Palem Mahendra' },
  { role: 'employee',  email: 'Kaushik.Ramisetty@acronotics.com', password: 'Kaushik@2003', name: 'Kaushik Ramisetty' },
  // Candidate portal — default password matches the onboarding email template
  // (utils/email_service.send_candidate_onboarding_email). The login form falls
  // back to /api/v1/auth/login for this role (see services/api.js).
  { role: 'candidate', email: 'kaushikramisetty@gmail.com',     password: 'candidate123', name: 'Kaushik Ramisetty' },
];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_USER);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);

  // On mount, refetch /auth/me so the cached user shape stays current.
  // Candidates authenticate via /api/v1/auth/login (legacy JWT shape),
  // which the core /auth/me cannot decode -- skip it for them.
  useEffect(() => {
    let cancelled = false;
    if (getToken()) {
      const cachedRole = (user?.role || '').toLowerCase();
      if (cachedRole === 'candidate') {
        return () => { cancelled = true; };
      }
      authApi.me()
        .then((u) => {
          if (cancelled) return;
          setUser(u);
          localStorage.setItem(STORAGE_USER, JSON.stringify(u));
        })
        .catch(() => {
          setToken(null);
          localStorage.removeItem(STORAGE_USER);
          if (!cancelled) setUser(null);
        });
    } else if (user) {
      localStorage.removeItem(STORAGE_USER);
      setUser(null);
    }
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Step 1 of 2FA: validate credentials. Server returns user_id + requires_2fa.
  // We don't set token/user yet -- that happens after /verify-otp.
  const login = useCallback(async ({ email, password }) => {
    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      // Candidates / legacy users are authenticated directly by the api
      // client -- token + user are already in localStorage. Just hydrate
      // the in-memory user state and skip the OTP step.
      if (res?.direct_login && res?.user) {
        setUser(res.user);
        return { ok: true, otpRequired: false, directLogin: true, user: res.user, email };
      }
      return {
        ok: true,
        otpRequired: !!res?.requires_2fa,
        userId: res?.user_id,
        email,
      };
    } catch (e) {
      const msg = e?.network ? e.message : (e?.data?.detail || e?.message || 'Login failed.');
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  // Step 2: verify OTP. On success, store token, fetch /auth/me, populate user.
  const verifyOtp = useCallback(async ({ userId, otp }) => {
    setLoading(true);
    try {
      const res = await authApi.verifyOtp(userId, otp);
      setToken(res.access_token);
      // Now that we have the token, /auth/me will give us the full user shape.
      const me = await authApi.me();
      setUser(me);
      localStorage.setItem(STORAGE_USER, JSON.stringify(me));
      return { ok: true, user: me };
    } catch (e) {
      // If /auth/me failed, drop the token to avoid a half-authed state.
      setToken(null);
      localStorage.removeItem(STORAGE_USER);
      const msg = e?.network ? e.message : (e?.data?.detail || e?.message || 'OTP verification failed.');
      return { ok: false, error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  const resendOtp = useCallback(async ({ userId }) => {
    try {
      const res = await authApi.resendOtp(userId);
      return { ok: true, message: res?.message };
    } catch (e) {
      return { ok: false, error: e?.data?.detail || e?.message || 'Could not resend OTP.' };
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    localStorage.removeItem(STORAGE_USER);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: !!user,
      role: user?.role || null,
      loading,
      login,
      verifyOtp,
      resendOtp,
      logout,
    }),
    [user, loading, login, verifyOtp, resendOtp, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}

export function dashboardPathForRole(role) {
  // Normalise so any casing / leading whitespace from legacy backends works.
  const r = (role || '').toString().trim().toLowerCase();
  switch (r) {
    case 'admin':     return '/admin-dashboard';
    case 'manager':   return '/manager-dashboard';
    case 'employee':  return '/employee-dashboard';
    // Candidate portal route was added during the Onboarding-module merge.
    case 'candidate': return '/candidate-dashboard';
    // Fallback: a user with no role (e.g. an older converted employee whose
    // role_id was never set) should still land on the employee dashboard
    // rather than bouncing back to /login. The backend now self-heals this
    // on login, but the FE default keeps already-issued sessions usable.
    default:          return '/employee-dashboard';
  }
}
