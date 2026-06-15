/**
 * Attendance finalization states shared across hooks and components.
 * FINALIZED: attendance record is complete (check-in + check-out processed).
 * PENDING_CHECKOUT: employee has checked in but not yet checked out.
 * NO_ATTENDANCE: no record exists for this day.
 */
export const ATTENDANCE_STATUS = {
  FINALIZED: 'FINALIZED',
  PENDING_CHECKOUT: 'PENDING_CHECKOUT',
  NO_ATTENDANCE: 'NO_ATTENDANCE',
};

export function fmtIso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function getWeekStart(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  const dow = (d.getDay() + 6) % 7; // 0 = Monday
  d.setDate(d.getDate() - dow);
  return d;
}

export function getWeekId(weekStart) {
  const d = new Date(weekStart);
  d.setHours(0, 0, 0, 0);
  // ISO 8601: find the Thursday of this week
  const thu = new Date(d);
  thu.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const yearStart = new Date(thu.getFullYear(), 0, 4);
  const weekNum =
    1 +
    Math.round(
      ((thu - yearStart) / 86400000 - 3 + ((yearStart.getDay() + 6) % 7)) / 7
    );
  return `${thu.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

export function getWeekDates(weekStart, { includeWeekends = false } = {}) {
  const NAMES = includeWeekends
    ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
  return NAMES.map((name, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return { name, date: d, iso: fmtIso(d) };
  });
}

export function formatWeekLabel(weekStart, { includeWeekends = false } = {}) {
  const start = new Date(weekStart);
  const end = new Date(weekStart);
  end.setDate(end.getDate() + (includeWeekends ? 6 : 4));
  const fmt = (d) =>
    `${d.getDate()} ${d.toLocaleString('en-US', { month: 'short' })} ${d.getFullYear()}`;
  return `${fmt(start)} – ${fmt(end)}`;
}

/**
 * Classify a week relative to today.
 * Returns 'past' | 'current' | 'future'.
 * Boundaries: Monday (weekStart) through Sunday (weekStart + 6 days) inclusive.
 */
export function classifyWeek(weekStart) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(weekStart);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  if (today < start) return 'future';
  if (today > end) return 'past';
  return 'current';
}

/**
 * Canonical weekly-hours calculation shared by MetricCards, SubmitModal, and
 * any other consumer that needs to display or validate the total for a week.
 *
 * Priority per day (mirrors HoursCell display logic):
 *   1. FINALIZED attendance  → use effective_hours
 *   2. PENDING_CHECKOUT      → 0  (not yet confirmed)
 *   3. No / missing record   → fall back to entry.logged_hours
 */
export function computeWeeklyHours(entries, attendanceMap) {
  return (entries || []).reduce((sum, entry) => {
    const att = (attendanceMap || {})[entry.date];
    if (att?.attendance_status === ATTENDANCE_STATUS.FINALIZED && att.effective_hours) {
      return sum + att.effective_hours;
    }
    if (att?.attendance_status === ATTENDANCE_STATUS.PENDING_CHECKOUT) {
      return sum;
    }
    return sum + (entry.logged_hours || 0);
  }, 0);
}
