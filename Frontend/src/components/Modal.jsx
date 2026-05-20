/**
 * components/Modal.jsx
 *
 * Portal-based modal that renders directly on document.body, completely
 * outside the sidebar/layout tree. This prevents any ancestor overflow,
 * transform, or z-index from clipping or obscuring the overlay.
 *
 * Features:
 *  - React Portal (createPortal) — layout-independent
 *  - Fixed full-screen overlay (z-[9999])
 *  - Body scroll lock while open
 *  - Escape key to close
 *  - Click-outside backdrop to close
 *  - Scrollable content area (max-h-[90vh])
 *  - Responsive width via `width` prop
 */

import { useEffect, useRef } from 'react'
import { createPortal }      from 'react-dom'

export default function Modal({
  title,
  onClose,
  children,
  width = 'max-w-4xl',
}) {
  const overlayRef = useRef(null)

  // ── Body scroll lock ───────────────────────────────────────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  // ── Escape key ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // ── Click outside (backdrop only, not the card) ────────────────────────────
  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current) onClose()
  }

  const modal = (
    /* ── Full-screen fixed overlay ── */
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 px-4 py-6"
    >
      {/* ── Modal card ── */}
      <div
        className={`
          relative flex flex-col w-full ${width}
          max-h-[90vh]
          rounded-2xl bg-white shadow-2xl
          overflow-hidden
        `}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            {/* ✕ using SVG so we don't need an Icon import here */}
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" aria-hidden>
              <path d="M6 6l8 8M14 6l-8 8" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {children}
        </div>
      </div>
    </div>
  )

  // Render outside the entire React tree via portal
  return createPortal(modal, document.body)
}
