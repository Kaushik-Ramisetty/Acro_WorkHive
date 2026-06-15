import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import LeftPanel from '../components/LeftPanel';
import LoginForm from '../components/LoginForm';
import OtpVerifyForm from '../components/OtpVerifyForm';
import { useAuth, dashboardPathForRole } from '../context/AuthContext';


function StepIndicator({ step }) {
  const steps = [
    { id: 'credentials', label: 'Sign In', num: 1 },
    { id: 'otp',         label: 'Verify',  num: 2 },
  ];
  const activeIndex = steps.findIndex((s) => s.id === step);

  return (
    <div className="flex items-center justify-center gap-3 border-b border-slate-100 bg-slate-50/70 px-6 py-3">
      {steps.map((s, i) => {
        const isDone   = i < activeIndex;
        const isActive = i === activeIndex;
        return (
          <div key={s.id} className="flex items-center gap-2">
            {i > 0 && (
              <div className={'h-px w-8 transition-colors duration-500 ' + ((isDone || isActive) ? 'bg-[#1e3acb]' : 'bg-slate-200')} />
            )}
            <div className="flex items-center gap-1.5">
              <div className={'flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition-all duration-300 ' +
                (isDone ? 'bg-emerald-500 text-white' : isActive ? 'bg-[#1e3acb] text-white' : 'bg-slate-200 text-slate-500')}>
                {isDone ? (
                  <svg viewBox="0 0 12 12" className="h-3.5 w-3.5" fill="none" aria-hidden>
                    <path d="m2 6 2.5 2.5L10 3" stroke="white" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : s.num}
              </div>
              <span className={'text-xs font-medium transition-colors duration-300 ' +
                (isActive ? 'text-slate-700' : isDone ? 'text-emerald-600' : 'text-slate-400')}>
                {s.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}


export default function LoginPage() {
  const { isAuthenticated, role, verifyOtp } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState('credentials');
  const [pendingUser, setPendingUser] = useState(null); // { email, userId }
  const [verifyError, setVerifyError] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      navigate(dashboardPathForRole(role), { replace: true });
    }
  }, [isAuthenticated, role, navigate]);

  function handleCredentialsSuccess({ email, userId, directLogin, role }) {
    if (directLogin) {
      // Token + user already in localStorage; AuthContext.user is set.
      // Bounce straight to the role's dashboard (e.g. /candidate-dashboard).
      navigate(dashboardPathForRole(role), { replace: true });
      return;
    }
    setPendingUser({ email, userId });
    setVerifyError('');
    setStep('otp');
  }

  // OtpVerifyForm calls onVerified({ token }) after a successful /verify-otp.
  // Here we hand the token to AuthContext.verifyOtp which fetches /auth/me and
  // populates the user, then redirect by role.
  async function handleOtpVerified() {
    if (!pendingUser) return;
    // OtpVerifyForm already calls /auth/verify-otp; we just need the auth
    // context to fetch /auth/me with that token and finish the session.
    // We re-call verifyOtp here using stored userId+otp would mean double
    // verification, so instead we expose a lighter setter: the OtpVerifyForm
    // does the API call, we just bootstrap the session from the token.
    // (Already handled inline in OtpVerifyForm via the wrapped onVerified.)
  }

  function handleBack() {
    setStep('credentials');
    setPendingUser(null);
    setVerifyError('');
  }

  // Wrapper passed to OtpVerifyForm. The form itself calls /auth/verify-otp,
  // gets the JWT, and invokes onVerified({ token }) -- we need to push that
  // token into the AuthContext + fetch /auth/me + redirect.
  async function onOtpFormVerified({ token }) {
    // setToken + /auth/me round-trip is encapsulated in AuthContext.verifyOtp,
    // but that function takes (userId, otp) and re-calls the verify endpoint.
    // To avoid a double call, store the token directly and trigger /auth/me.
    const { setToken } = await import('../services/api');
    setToken(token);
    try {
      const { auth } = await import('../services/api');
      const me = await auth.me();
      // Hydrate AuthContext via localStorage + reload-friendly path.
      localStorage.setItem('hrms.auth.user', JSON.stringify(me));
      // Bounce to the role-specific dashboard. The AuthContext mount-effect
      // will pick up the token + user from localStorage on the next render.
      navigate(dashboardPathForRole(me.role), { replace: true });
      // Force a full reload so the AuthProvider re-initialises with the user.
      // Without this, the in-memory user state is still null even though
      // localStorage and the JWT are set.
      window.location.reload();
    } catch (e) {
      setVerifyError('Could not load profile after verification. Please try again.');
      setToken(null);
      localStorage.removeItem('hrms.auth.user');
    }
  }

  return (
    <div className="bg-ambient flex min-h-screen items-center justify-center px-4 py-10">
      <div className="relative z-10 w-full max-w-5xl overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-slate-200/60">
        <StepIndicator step={step} />

        <div className="grid grid-cols-1 md:grid-cols-2">
          <div className="min-h-[460px] md:min-h-[600px]">
            <LeftPanel />
          </div>

          <div className="relative min-h-[460px] overflow-hidden md:min-h-[600px]">
            <div className={'absolute inset-0 transition-transform duration-300 ease-in-out ' +
              (step === 'credentials' ? 'translate-x-0' : '-translate-x-full')}>
              <LoginForm onSuccess={handleCredentialsSuccess} />
            </div>

            <div className={'absolute inset-0 transition-transform duration-300 ease-in-out ' +
              (step === 'otp' ? 'translate-x-0' : 'translate-x-full')}>
              {pendingUser && (
                <OtpVerifyForm
                  email={pendingUser.email}
                  userId={pendingUser.userId}
                  onVerified={onOtpFormVerified}
                  onBack={handleBack}
                />
              )}
              {verifyError && (
                <div className="absolute inset-x-6 bottom-6 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {verifyError}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <p className="absolute bottom-4 left-0 right-0 z-10 text-center text-xs text-slate-500">
        © 2026 WorkHive Systems. Licensed to Acronotics Limited. All rights reserved.{' '}
        <a className="underline-offset-2 hover:underline" href="#">Privacy Policy</a>
        {' | '}
        <a className="underline-offset-2 hover:underline" href="#">Terms of Service</a>
      </p>
    </div>
  );
}
