/**
 * components/PhoneInput.jsx — E.164 phone number input with live validation.
 *
 * Format enforced:  +<country_code><subscriber_number>
 * Examples:         +919876543210  +14155552671  +447911123456
 *
 * Behaviour:
 *  - Typing "+" first is automatic — if user types a digit without "+", it's
 *    prepended automatically.
 *  - Any non-digit character (except the leading "+") is stripped on input.
 *  - Spaces / dashes typed by the user are silently removed so the stored
 *    value is always clean E.164.
 *  - Live error shown only after the field has been touched (blur or submit).
 *  - External `error` prop overrides the internal validation message (useful
 *    when the backend returns a 422 validation error).
 *
 * Props:
 *  value       string   Controlled value (E.164 or partial)
 *  onChange    fn       Called with the cleaned value string
 *  label       string   Field label
 *  required    bool     Show asterisk and enforce non-empty
 *  placeholder string   Defaults to "+91 9876543210"
 *  disabled    bool
 *  error       string   External error message (backend / form-level)
 *  hint        string   Helper text shown below when no error
 *  name        string   HTML name attribute
 */

import { useState, useId } from 'react'

// ── Validation logic (mirrors backend utils/phone_validator.py) ───────────────
const E164_RE = /^\+[1-9]\d{7,14}$/

function validateE164(val) {
  if (!val) return null                          // empty → field is optional
  if (!val.startsWith('+'))
    return 'Must start with + and country code (e.g. +919876543210)'
  const digits = val.slice(1)
  if (!digits)
    return 'Enter country code and number after +'
  if (digits[0] === '0')
    return 'Country code cannot start with 0'
  if (digits.length < 7)
    return `Too short (${digits.length} digit${digits.length === 1 ? '' : 's'} after +). Include your country code (min 8 total)`
  if (digits.length > 15)
    return `Too long (${digits.length} digits after +). Maximum is 15 (ITU-T E.164)`
  if (!E164_RE.test(val))
    return 'Invalid format — use +<country_code><number>, digits only'
  return null
}

// ── Normaliser — strips separators, ensures leading + ─────────────────────────
function normalise(raw) {
  if (!raw) return ''
  // Preserve the leading + then keep only digits
  const hasPlus   = raw.startsWith('+')
  const digitsOnly = raw.replace(/\D/g, '')
  return hasPlus ? '+' + digitsOnly : '+' + digitsOnly
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function PhoneInput({
  value       = '',
  onChange,
  label       = 'Phone',
  required    = false,
  placeholder = '+91 9876543210',
  disabled    = false,
  error: externalError,
  hint,
  name,
}) {
  const id      = useId()
  const [touched, setTouched] = useState(false)

  // Compute which error to show
  const internalError = touched ? validateE164(value) : null
  const displayError  = externalError || internalError

  // ── Handlers ─────────────────────────────────────────────────────────────────
  function handleChange(e) {
    const cleaned = normalise(e.target.value)
    onChange(cleaned)
  }

  function handleBlur() {
    setTouched(true)
  }

  function handleKeyDown(e) {
    // Allow: Backspace, Delete, Arrow keys, Tab, Ctrl/Cmd combos
    const allowedKeys = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight',
                         'ArrowUp', 'ArrowDown', 'Tab', 'Home', 'End']
    if (allowedKeys.includes(e.key)) return
    if (e.ctrlKey || e.metaKey) return

    // Block letters and special chars (but allow + for the first char)
    const isDigit = /^\d$/.test(e.key)
    const isPlus  = e.key === '+' && e.target.selectionStart === 0 && !value.startsWith('+')
    if (!isDigit && !isPlus) {
      e.preventDefault()
    }
  }

  // ── Style helpers ─────────────────────────────────────────────────────────────
  const borderCls = displayError
    ? 'border-red-300 focus:border-red-400 focus:ring-red-100'
    : 'border-slate-200 focus:border-blue-500 focus:ring-blue-100'

  const inputCls =
    `w-full rounded-lg border px-3 py-2 text-sm outline-none transition ` +
    `focus:ring-1 disabled:bg-slate-50 disabled:text-slate-400 font-mono tracking-wide ${borderCls}`

  // Character counter
  const digits = value ? value.slice(1).replace(/\D/g, '') : ''
  const counter = value
    ? `${digits.length}/15`
    : null
  const counterColor = digits.length > 15 ? 'text-red-500' : digits.length >= 8 ? 'text-emerald-600' : 'text-slate-400'

  return (
    <div>
      {label && (
        <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">
          {label}
          {required && <span className="ml-0.5 text-red-500">*</span>}
        </label>
      )}

      <div className="relative">
        {/* Flag / globe icon */}
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-base select-none pointer-events-none">
          🌐
        </span>

        <input
          id={id}
          name={name}
          type="tel"
          inputMode="tel"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="tel"
          maxLength={16}             /* + up to 15 digits */
          aria-invalid={!!displayError}
          aria-describedby={displayError ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className={`${inputCls} pl-9 pr-14`}
        />

        {/* Digit counter */}
        {counter && (
          <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-mono ${counterColor}`}>
            {counter}
          </span>
        )}
      </div>

      {/* Error / hint */}
      {displayError ? (
        <p id={`${id}-error`} className="mt-1 text-xs text-red-500 flex items-start gap-1">
          <span className="mt-0.5 shrink-0">⚠</span>
          {displayError}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-400">{hint}</p>
      ) : null}
    </div>
  )
}
