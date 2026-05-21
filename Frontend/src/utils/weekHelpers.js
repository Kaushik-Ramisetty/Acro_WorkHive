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
