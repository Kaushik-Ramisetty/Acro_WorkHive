import { createPortal } from 'react-dom';

export default function SubmitModal({ weekLabel, totalHours, onCancel, onConfirm }) {
  return createPortal(
    <div
      onClick={onCancel}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 440,
          background: 'var(--hrms-surface)',
          borderRadius: 16,
          overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,0.2)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px 16px',
            borderBottom: '1px solid var(--hrms-border)',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span style={{ fontSize: 22 }}>📋</span>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--hrms-text)' }}>
              Submit Timesheet?
            </div>
            <div style={{ fontSize: 12, color: 'var(--hrms-text-faint)', marginTop: 2 }}>
              This action cannot be undone
            </div>
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: '20px 24px' }}>
          <div
            style={{
              background: 'var(--hrms-surface-2)',
              border: '1px solid var(--hrms-border)',
              borderRadius: 10,
              padding: '14px 16px',
              marginBottom: 14,
            }}
          >
            <div style={{ fontSize: 13, color: 'var(--hrms-text-2)', marginBottom: 6 }}>
              <span style={{ fontWeight: 700, color: 'var(--hrms-text)' }}>Week of</span>{' '}
              {weekLabel}
            </div>
            <div style={{ fontSize: 13, color: 'var(--hrms-text-2)' }}>
              <span style={{ fontWeight: 800, color: '#14b8a6', fontSize: 15 }}>
                {totalHours}h
              </span>{' '}
              logged this week
            </div>
          </div>
          <p style={{ fontSize: 13, color: 'var(--hrms-text-muted)', margin: 0, lineHeight: 1.6 }}>
            Once submitted, entries are locked for editing. Your manager will be
            notified to review and approve.
          </p>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid var(--hrms-border)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
            background: 'var(--hrms-surface-2)',
          }}
        >
          <button
            onClick={onCancel}
            style={{
              padding: '9px 20px',
              borderRadius: 8,
              border: '1px solid var(--hrms-border)',
              background: 'var(--hrms-surface)',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--hrms-text-2)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '9px 22px',
              borderRadius: 8,
              border: 'none',
              background: '#14b8a6',
              fontSize: 13,
              fontWeight: 700,
              color: '#fff',
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(20,184,166,0.3)',
            }}
          >
            Submit →
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
