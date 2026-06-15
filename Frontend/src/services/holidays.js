// Holidays API client — strictly location-scoped on the backend.
//
// Endpoints
// ---------
//   /holidays/me                 → caller's own location (preferred for widgets)
//   /holidays/upcoming           → next N days, defaults to caller's location
//   /holidays                    → year list, defaults to caller's location
//   /holidays/location/{loc}     → admin-only, inspect another office
//
// IMPORTANT: This module never merges results across locations. Every call
// goes to one server-filtered endpoint and we return the raw response so
// callers can't accidentally union two location's arrays together.
import { api } from './api';

function qs(obj) {
  const p = new URLSearchParams();
  Object.entries(obj || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  return p.toString() ? `?${p}` : '';
}

export const holidays = {
  /** Latest spec: returns ONLY the caller's location holidays. */
  me: ({ year, includeOptional = false } = {}) =>
    api.get('/holidays/me' + qs({ year, include_optional: includeOptional })),

  /** Upcoming. Server defaults `location` to the caller's `Employee.location`
   *  when none is passed — do NOT pass it client-side unless you're an admin
   *  inspecting another office.
   */
  upcoming: ({ days = 120, limit = 10, location, includeOptional = false } = {}) =>
    api.get('/holidays/upcoming' + qs({ days, limit, location, include_optional: includeOptional })),

  /** Year list — same server-default behaviour. */
  list: (year, { includeOptional = false } = {}) =>
    api.get('/holidays' + qs({ year, include_optional: includeOptional })),

  /** Admin-only: inspect another office's holidays. Returns 403 for non-admins. */
  forLocation: (location, { year, includeOptional = false } = {}) =>
    api.get(`/holidays/location/${encodeURIComponent(location)}` + qs({ year, include_optional: includeOptional })),
};

export default holidays;
