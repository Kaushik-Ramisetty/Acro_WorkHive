/**
 * Shared attendance weight table.
 *
 * holiday is intentionally 0.0 here — callers that build the working-day
 * *denominator* must subtract holiday rows separately (they are excluded
 * from the denominator entirely, not just counted as 0 worked).
 */
const UNITS = {
  present:        1.0,
  late:           1.0,
  wfh:            1.0,
  work_from_home: 1.0,
  half_day:       0.5,
  on_leave:       0.0,
  absent:         0.0,
  holiday:        0.0,
};

/**
 * Return the weighted attendance value for a status string.
 *   present / late / wfh  → 1.0
 *   half_day               → 0.5
 *   everything else        → 0.0
 */
export function attendanceUnits(status) {
  return UNITS[(status || '').toLowerCase()] ?? 0.0;
}

/**
 * Sum weighted attendance units across an array of record objects.
 * Each record must have a `.status` string field.
 */
export function calcPresentDays(records) {
  return (records || []).reduce((sum, r) => sum + attendanceUnits(r.status), 0);
}

/**
 * Format a fractional day count for display.
 *   1   → "1"
 *   0.5 → "0.5"
 *   2.5 → "2.5"
 */
export function fmtDays(n) {
  if (n == null || Number.isNaN(n)) return '0';
  return n % 1 === 0 ? String(n) : n.toFixed(1);
}
