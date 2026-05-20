/**
 * ChangePasswordPage.jsx
 * Shown immediately after first login when forcePasswordChange = true.
 * Employee cannot access the dashboard until they change their temp password.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

import { BASE } from '../../config/api';
import { authHeaders } from '../../config/auth';

async function changePassword(officialEmail, currentPassword, newPassword) {
  // Logged-in employee changing their own password — include JWT bearer so
  // the backend can authorise the call.
  const res = await fetch(`${BASE}/api/v1/auth/change-password`, {
    method:  'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body:    JSON.stringify({
      official_email:   officialEmail,
      current_password: currentPassword,
      new_password:     newPassword,
    }),
  })
  const json = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(json.detail || json.message || `HTTP ${res.status}`)
  return json.data ?? json
}

export default function ChangePasswordPage() {
  const { user, setUser, logout } = useAuth()
  const navigate = useNavigate()

  const [current,  setCurrent]  = useState('')
  const [next,     setNext]     = useState('')
  const [confirm,  setConfirm]  = useState('')
  const [showPwd,  setShowPwd]  = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  const validate = () => {
    if (!current)                    return 'Current password is required.'
    if (next.length < 8)             return 'New password must be at least 8 characters.'
    if (next === current)            return 'New password must be different from the current one.'
    if (next !== confirm)            return 'Passwords do not match.'
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const err = validate()
    if (err) { setError(err); return }

    setError('')
    setLoading(true)
    try {
      // Backend's /api/v1/auth/change-password looks up by official_email only.
      // Use officialEmail when present; fall back to email so legacy sessions
      // still work even if they don't have officialEmail set.
      const lookupEmail = user.officialEmail || user.email
      await changePassword(lookupEmail, current, next)
      // Clear forcePasswordChange in session
      setUser((prev) => ({ ...prev, forcePasswordChange: false }))
      navigate('/employee-dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Failed to change password. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const inputCls =
    'w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 ' +
    'focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition'

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="mb-6 text-center">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white text-2xl mb-3">
            🔐
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Change Your Password</h1>
          <p className="mt-1.5 text-sm text-slate-500">
            You're required to set a new password before accessing the portal.
          </p>
        </div>

        {/* Notice */}
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex gap-2">
          <span className="shrink-0">⚠️</span>
          <span>
            Your account was set up with a temporary password by IT.
            Please create a strong personal password to continue.
          </span>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl bg-white border border-slate-100 shadow-sm px-6 py-6 space-y-4"
        >
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Current (Temporary) Password
            </label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                className={inputCls + ' pr-14'}
                placeholder="Enter temporary password"
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPwd((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-slate-400 hover:text-slate-600"
              >
                {showPwd ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              New Password <span className="text-slate-400">(min 8 characters)</span>
            </label>
            <input
              type={showPwd ? 'text' : 'password'}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className={inputCls}
              placeholder="Create a strong password"
              autoComplete="new-password"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Confirm New Password
            </label>
            <input
              type={showPwd ? 'text' : 'password'}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={inputCls}
              placeholder="Re-enter new password"
              autoComplete="new-password"
            />
          </div>

          {/* Password strength indicator */}
          {next.length > 0 && (
            <div className="flex gap-1">
              {[...Array(4)].map((_, i) => {
                const strength =
                  next.length >= 12 ? 4 :
                  next.length >= 10 ? 3 :
                  next.length >= 8  ? 2 : 1
                return (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full ${
                      i < strength
                        ? strength === 1 ? 'bg-red-400'
                        : strength === 2 ? 'bg-amber-400'
                        : strength === 3 ? 'bg-blue-400'
                        : 'bg-emerald-500'
                        : 'bg-slate-200'
                    }`}
                  />
                )
              })}
              <span className="ml-2 text-xs text-slate-400">
                {next.length < 8  ? 'Too short' :
                 next.length < 10 ? 'Weak' :
                 next.length < 12 ? 'Good' : 'Strong'}
              </span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition mt-2"
          >
            {loading ? 'Updating…' : 'Set New Password & Continue'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => { logout(); navigate('/login', { replace: true }) }}
          className="mt-4 w-full text-center text-xs text-slate-400 hover:text-slate-600"
        >
          Sign out and log in as a different user
        </button>
      </div>
    </div>
  )
}
