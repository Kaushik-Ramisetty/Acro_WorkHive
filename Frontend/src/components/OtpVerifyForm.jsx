import { useState, useEffect, useRef } from 'react'
import { auth } from '../services/api'

const RESEND_SECONDS = 120
const MAX_ATTEMPTS = 3

function formatTime(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function maskEmail(email) {
  const [local, domain] = (email || '').split('@')
  if (!local || !domain) return email
  const visible = local.length > 2 ? 2 : 1
  const masked = local.slice(0, visible) + '*'.repeat(Math.max(local.length - visible, 3))
  return `${masked}@${domain}`
}

export default function OtpVerifyForm({ email, userId, onVerified, onBack }) {
  const [otp, setOtp] = useState(['', '', '', '', '', ''])
  const [error, setError] = useState('')
  const [attempts, setAttempts] = useState(0)
  const [timer, setTimer] = useState(RESEND_SECONDS)
  const [verifying, setVerifying] = useState(false)
  const inputRefs = useRef([])

  // Auto-focus first box on mount
  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  // Countdown
  useEffect(() => {
    if (timer <= 0) return
    const id = setTimeout(() => setTimer((t) => t - 1), 1000)
    return () => clearTimeout(id)
  }, [timer])

  function handleChange(index, value) {
    if (!/^\d?$/.test(value)) return
    const next = [...otp]
    next[index] = value
    setOtp(next)
    setError('')
    if (value && index < 5) inputRefs.current[index + 1]?.focus()
  }

  function handleKeyDown(index, e) {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
    if (e.key === 'Enter') handleVerify()
  }

  function handlePaste(e) {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!pasted) return
    const next = Array(6).fill('')
    for (let i = 0; i < pasted.length; i++) next[i] = pasted[i]
    setOtp(next)
    const focusIdx = Math.min(pasted.length, 5)
    inputRefs.current[focusIdx]?.focus()
  }

  async function handleVerify() {
    const entered = otp.join('')
    if (entered.length < 6) {
      setError('Please enter the complete 6-digit OTP.')
      return
    }
    setVerifying(true)
    try {
      const data = await auth.verifyOtp(userId, entered)
      onVerified({ token: data.access_token })
    } catch (err) {
      const newAttempts = attempts + 1
      setAttempts(newAttempts)
      const remaining = MAX_ATTEMPTS - newAttempts
      if (remaining <= 0) {
        setError('Too many incorrect attempts. Please go back and try again.')
      } else {
        setError(err.message || `Invalid OTP. ${remaining} attempt${remaining !== 1 ? 's' : ''} remaining.`)
      }
      setOtp(['', '', '', '', '', ''])
      setTimeout(() => inputRefs.current[0]?.focus(), 50)
    } finally {
      setVerifying(false)
    }
  }

  async function handleResend() {
    try {
      await auth.resendOtp(userId)
    } catch (err) {
      setError(err.message || 'Failed to resend OTP. Please try again.')
      return
    }
    setTimer(RESEND_SECONDS)
    setOtp(['', '', '', '', '', ''])
    setError('')
    setAttempts(0)
    setTimeout(() => inputRefs.current[0]?.focus(), 50)
  }

  const isBlocked = attempts >= MAX_ATTEMPTS
  const otpFilled = otp.join('').length === 6

  const timerDisplay = formatTime(timer)

  return (
    <div className="flex h-full w-full flex-col bg-white p-8 md:p-10">
      <div className="flex-1">
        {/* Back link */}
        <button
          type="button"
          onClick={onBack}
          className="mb-5 flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-slate-800"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" aria-hidden>
            <path d="M12 16 6 10l6-6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to login
        </button>

        <h2 className="text-2xl font-bold tracking-tight text-slate-900">Verify your identity</h2>
        <p className="mt-1.5 text-sm text-slate-500">
          OTP sent to{' '}
          <span className="font-semibold text-slate-700">{maskEmail(email)}</span>
        </p>

        {/* Divider */}
        <div className="mt-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-slate-200" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Two-Factor Authentication
          </span>
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="mt-6 space-y-5">
          {/* Error banner */}
          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              <svg viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0" fill="none" aria-hidden>
                <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10 6v4m0 3.5v.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
              {error}
            </div>
          )}

          {/* OTP boxes */}
          <div>
            <label className="mb-3 block text-sm font-medium text-slate-700">
              Enter 6-digit OTP
            </label>
            <div className="flex justify-center gap-2.5" onPaste={handlePaste}>
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => (inputRefs.current[i] = el)}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  disabled={isBlocked || verifying}
                  onChange={(e) => handleChange(i, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(i, e)}
                  className={`h-12 w-11 rounded-lg border text-center text-lg font-bold shadow-sm transition focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:opacity-40 ${
                    error && !isBlocked
                      ? 'border-red-300 text-red-700 focus:border-red-400 focus:ring-red-100'
                      : digit
                      ? 'border-brand-600 text-slate-900 focus:border-brand-600 focus:ring-brand-100'
                      : 'border-slate-200 text-slate-900 focus:border-brand-600 focus:ring-brand-100'
                  }`}
                />
              ))}
            </div>
          </div>

          {/* Timer / Resend */}
          <div className="text-center">
            {timer > 0 ? (
              <p className="text-sm text-slate-500">
                Resend OTP in{' '}
                <span className="tabular-nums font-semibold text-brand-600">{timerDisplay}</span>
              </p>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={isBlocked}
                className="text-sm font-semibold text-brand-600 transition hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Resend OTP
              </button>
            )}
          </div>

          {/* Verify button */}
          <button
            type="button"
            onClick={handleVerify}
            disabled={verifying || isBlocked || !otpFilled}
            className="group relative flex w-full items-center justify-center gap-2 rounded-lg bg-[#1e3acb] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#1a31b3] focus:outline-none focus:ring-2 focus:ring-brand-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {verifying ? (
              <>
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
                Verifying…
              </>
            ) : (
              <>
                Verify OTP
                <svg className="h-4 w-4 transition group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="none" aria-hidden>
                  <path d="M4 10h12m0 0-4-4m4 4-4 4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </>
            )}
          </button>

          {/* Change account link */}
          <p className="text-center text-xs text-slate-500">
            Wrong account?{' '}
            <button
              type="button"
              onClick={onBack}
              className="font-semibold text-brand-600 transition hover:text-brand-700"
            >
              Change credentials
            </button>
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-8 border-t border-slate-100 pt-5">
        <div className="flex items-center justify-center gap-6 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          <span className="flex items-center gap-1.5">
            <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" aria-hidden>
              <path d="M10 2 3 5v5c0 4.5 3 7.5 7 8 4-.5 7-3.5 7-8V5l-7-3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            </svg>
            Enterprise SSL
          </span>
          <span className="flex items-center gap-1.5">
            <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" aria-hidden>
              <path d="M10 2 3 5v5c0 4.5 3 7.5 7 8 4-.5 7-3.5 7-8V5l-7-3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="m7.5 10 1.8 1.8L13 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            2FA Secured
          </span>
        </div>
      </div>
    </div>
  )
}
