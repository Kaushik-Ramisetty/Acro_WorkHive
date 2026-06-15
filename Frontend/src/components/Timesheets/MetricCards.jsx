import { computeWeeklyHours, ATTENDANCE_STATUS } from '../../utils/weekHelpers';

export default function MetricCards({ attendanceMap, entries }) {
  // computeWeeklyHours applies the canonical priority: FINALIZED attendance →
  // PENDING_CHECKOUT (=0) → fallback to entry.logged_hours.  This keeps the
  // metric card consistent with HoursCell and the SubmitModal total.
  const total    = computeWeeklyHours(entries, attendanceMap);
  const days     = Object.values(attendanceMap || {});
  const pending  = days.filter((a) => a.attendance_status === ATTENDANCE_STATUS.PENDING_CHECKOUT).length;
  const count    = entries.length;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '5px 0', marginBottom: '0.625rem', flexWrap: 'wrap',
    }}>
      {/* Total attendance hours */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 7,
        background: 'var(--hrms-surface-2)', borderRadius: 6,
        padding: '5px 12px', border: '0.5px solid var(--hrms-border)',
      }}>
        <span style={{ fontSize: 13, color: 'var(--hrms-text-faint)' }}>⏱</span>
        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--hrms-text)', letterSpacing: '-0.01em' }}>
          {total}h
        </span>
        <span style={{ fontSize: 12, color: 'var(--hrms-text-faint)' }}>this week</span>
      </div>

      {/* Pending checkout warning */}
      {pending > 0 && (
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          background: '#FAEEDA', borderRadius: 6,
          padding: '5px 10px', border: '0.5px solid #F3D9B5',
          fontSize: 11, color: '#854F0B',
        }}>
          ⚠ {pending} day{pending > 1 ? 's' : ''} pending checkout
        </div>
      )}

      <span style={{ fontSize: 12, color: 'var(--hrms-text-faint)' }}>
        {count} entr{count === 1 ? 'y' : 'ies'}
      </span>
    </div>
  );
}
