import { EMPLOYEE_EDITABLE, WF } from './workflow/statuses';

const CARD = {
  background: 'var(--hrms-surface)', border: '0.5px solid var(--hrms-border)',
  borderRadius: 8, padding: '0.625rem 0.875rem', marginBottom: '0.5rem',
};

const TITLE = {
  fontSize: 11, fontWeight: 600, color: 'var(--hrms-text-faint)',
  textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 0.4rem',
};

const BTN = {
  fontSize: 12, padding: '5px 12px', borderRadius: 5,
  border: '0.5px solid var(--hrms-border)', background: 'transparent',
  color: 'var(--hrms-text-2)', cursor: 'pointer', display: 'inline-flex',
  alignItems: 'center', gap: 5, fontFamily: 'inherit',
};

const BTN_PRIMARY = {
  ...BTN,
  background: '#0F172A', color: '#fff',
  border: '0.5px solid #0F172A',
};

// ── Status badge shown when workflow is in-flight ────────────────────────────

const STATUS_LABELS = {
  [WF.PENDING_CLIENT]:   'Awaiting Client Manager approval',
  [WF.PENDING_RM]:       'Awaiting Reporting Manager approval',
  [WF.PENDING_HR]:       'Awaiting HR review',
  [WF.PENDING_FINANCE]:  'Awaiting Finance approval',
  [WF.PROCESSING]:       'Payroll & billing in progress',
  [WF.COMPLETED]:        'Timesheet fully processed',
  [WF.CLIENT_APPROVED]:  'Client approved — pending internal review',
  [WF.RM_APPROVED]:      'Manager approved — pending HR review',
  [WF.HR_APPROVED]:      'HR approved — pending Finance',
  [WF.FINANCE_APPROVED]: 'Finance approved — ready for payroll',
};

export default function ActionBar({
  weekStatus,
  onSaveDraft,
  onSubmit,
  onResubmit,
  onExportPdf,
  onExportExcel,
}) {
  const isEditable   = EMPLOYEE_EDITABLE.has(weekStatus);
  const isRejected   = weekStatus === WF.CLIENT_REJECTED || weekStatus === WF.REJECTED;
  const isDraft      = weekStatus === WF.DRAFT;
  const isInFlight   = !isEditable && weekStatus !== WF.COMPLETED;
  const statusLabel  = STATUS_LABELS[weekStatus];

  return (
    <>
      <style>{`
        @media print {
          .ts-no-print { display: none !important; }
          .ts-print-only { display: block !important; }
        }
        .ts-print-only { display: none; }
        .ts-btn:hover { background: var(--hrms-surface-2) !important; }
        .ts-btn-primary:hover { opacity: 0.88; background: #0F172A !important; }
        .ts-btn-warn:hover { background: #FEF2F2 !important; }
      `}</style>

      <div className="ts-no-print" style={CARD}>
        <p style={TITLE}>Actions</p>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>

          {/* Employee: draft state */}
          {isDraft && (
            <button onClick={onSaveDraft} className="ts-btn" style={BTN}>
              💾 Save draft
            </button>
          )}
          {isDraft && (
            <button onClick={onSubmit} className="ts-btn-primary" style={BTN_PRIMARY}>
              ▶ Submit timesheet
            </button>
          )}

          {/* Employee: rejected — allow edit + resubmit */}
          {isRejected && (
            <button onClick={onResubmit} className="ts-btn-primary" style={BTN_PRIMARY}>
              ↺ Resubmit for review
            </button>
          )}
          {isRejected && (
            <button onClick={onSaveDraft} className="ts-btn" style={BTN}>
              💾 Save draft
            </button>
          )}

          {/* Always available: export */}
          <button onClick={onExportPdf} className="ts-btn" style={BTN}>
            📄 Export PDF
          </button>
          <button onClick={onExportExcel} className="ts-btn" style={BTN}>
            📊 Export Excel
          </button>

          {/* In-flight status indicator */}
          {isInFlight && statusLabel && (
            <span style={{
              fontSize: 12, color: '#854F0B',
              background: '#FAEEDA', borderRadius: 4,
              padding: '3px 9px', border: '0.5px solid #F3D9B5',
              marginLeft: 4,
            }}>
              ⏳ {statusLabel}
            </span>
          )}

          {/* Completed state */}
          {weekStatus === WF.COMPLETED && (
            <span style={{
              fontSize: 12, color: '#3B6D11',
              background: '#EAF3DE', borderRadius: 4,
              padding: '3px 9px', border: '0.5px solid #C0DCAA',
              marginLeft: 4,
            }}>
              ✓ Timesheet fully processed
            </span>
          )}
        </div>
      </div>
    </>
  );
}
