import { useEffect } from 'react';
import { createPortal } from 'react-dom';

export default function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    if (type === 'success') {
      const t = setTimeout(onClose, 3000);
      return () => clearTimeout(t);
    }
  }, [type, onClose]);

  const cfg =
    type === 'success'
      ? { bg: '#ECFDF5', border: '#A7F3D0', text: '#065F46', icon: '✓' }
      : { bg: '#FEF2F2', border: '#FECACA', text: '#991B1B', icon: '!' };

  return createPortal(
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '12px 16px',
        borderRadius: 10,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
        fontSize: 13,
        fontWeight: 600,
        color: cfg.text,
        minWidth: 240,
        maxWidth: 380,
        animation: 'tsToastIn 0.2s ease',
      }}
    >
      <span
        style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: cfg.text,
          color: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          fontWeight: 800,
          flexShrink: 0,
        }}
      >
        {cfg.icon}
      </span>
      <span style={{ flex: 1 }}>{message}</span>
      <button
        onClick={onClose}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: cfg.text,
          fontSize: 18,
          lineHeight: 1,
          padding: 0,
          opacity: 0.6,
          flexShrink: 0,
        }}
      >
        ×
      </button>
      <style>{`
        @keyframes tsToastIn {
          from { opacity: 0; transform: translateX(16px); }
          to   { opacity: 1; transform: none; }
        }
      `}</style>
    </div>,
    document.body
  );
}
