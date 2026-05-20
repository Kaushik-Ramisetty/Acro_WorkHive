import { useState } from 'react';
import { useAuth, DEMO_ACCOUNTS } from '../context/AuthContext';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Step 1 of 2FA. Calls onSuccess({ email, userId }) once credentials check out;
// the parent (LoginPage) shows the OTP screen next.
export default function LoginForm({ onSuccess }) {
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({ email: '', password: '', form: '' });
  const [submitting, setSubmitting] = useState(false);

  function validate() {
    const next = { email: '', password: '', form: '' };
    if (!email.trim()) next.email = 'Email is required.';
    else if (!EMAIL_RE.test(email.trim())) next.email = 'Enter a valid email address.';
    if (!password) next.password = 'Password is required.';
    else if (password.length < 4) next.password = 'Password is too short.';
    setErrors(next);
    return !next.email && !next.password;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    setErrors((p) => ({ ...p, form: '' }));
    try {
      const result = await login({ email: email.trim(), password });
      if (!result.ok) {
        setErrors((p) => ({ ...p, form: result.error || 'Login failed.' }));
        return;
      }
      // Direct (non-2FA) login: token + user already stored. Tell the
      // parent page to navigate immediately, skipping the OTP step.
      if (result.directLogin) {
        onSuccess?.({ directLogin: true, role: result.user?.role });
        return;
      }
      // Hand off to LoginPage for the OTP step. Don't set auth state here.
      onSuccess?.({ email: result.email || email.trim(), userId: result.userId });
    } catch (err) {
      setErrors((p) => ({ ...p, form: err?.message || 'Network error - is the backend running?' }));
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo(role) {
    const u = DEMO_ACCOUNTS.find((x) => x.role === role);
    if (!u) return;
    setEmail(u.email);
    setPassword(u.password);
    setErrors({ email: '', password: '', form: '' });
  }

  return (
    <div className="flex h-full w-full flex-col bg-white p-8 md:p-10">
      <div className="flex-1">
        <h2 className="text-2xl font-bold tracking-tight text-slate-900">Sign In</h2>
        <p className="mt-1 text-sm text-slate-500">
          Use your corporate credentials. A 6-digit verification code will be sent to your email.
        </p>

        <div className="mt-7 flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-200" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Enterprise Access
          </span>
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-4">
          {errors.form && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {errors.form}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              placeholder="you@company.com"
            />
            {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password</label>
            <div className="relative mt-1">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 pr-12 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-slate-100"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="mt-2 w-full rounded-lg bg-[#1e3acb] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#1a31b3] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Sending verification code…' : 'Continue'}
          </button>
        </form>

        <div className="mt-7 border-t border-slate-100 pt-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Quick demo</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {DEMO_ACCOUNTS.map((u) => (
              <button
                key={u.role}
                type="button"
                onClick={() => fillDemo(u.role)}
                className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-100"
              >
                {u.role[0].toUpperCase() + u.role.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-6 text-center text-[11px] text-slate-400">
        © 2026 WorkHive — protected by 2-factor email verification.
      </p>
    </div>
  );
}
