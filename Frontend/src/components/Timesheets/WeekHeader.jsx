import { formatWeekLabel } from '../../utils/weekHelpers';
import { WF_DISPLAY } from './workflow/statuses';

const NAV_BTN = {
  fontSize: 13, padding: '5px 11px', borderRadius: 6,
  border: '0.5px solid var(--hrms-border)', background: 'transparent',
  color: 'var(--hrms-text-2)', cursor: 'pointer', fontFamily: 'inherit',
};

const DRAFT_DISPLAY = { label: 'Draft', color: 'var(--hrms-text-muted)', bg: 'var(--hrms-surface-2)', border: 'var(--hrms-border)' };

export default function WeekHeader({ activeWeekStart, weekStatus, onPrev, onNext, onThisWeek }) {
  const weekLabel = formatWeekLabel(activeWeekStart, { includeWeekends: true });
  const s = WF_DISPLAY[weekStatus] || DRAFT_DISPLAY;

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: '0.5rem' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
          <p style={{ margin: 0, fontSize: 20, fontWeight: 500, color: 'var(--hrms-text)' }}>Timesheet</p>
          <span style={{
            fontSize: 12, color: s.color, background: s.bg,
            borderRadius: 6, padding: '3px 9px', border: `0.5px solid ${s.border}`,
          }}>
            {s.label}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--hrms-text-muted)' }}>Week of {weekLabel}</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <button
          onClick={onPrev}
          style={NAV_BTN}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--hrms-surface-2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
          ← Prev
        </button>
        <button
          onClick={onThisWeek}
          style={NAV_BTN}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--hrms-surface-2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
          This Week
        </button>
        <button
          onClick={onNext}
          style={NAV_BTN}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--hrms-surface-2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
