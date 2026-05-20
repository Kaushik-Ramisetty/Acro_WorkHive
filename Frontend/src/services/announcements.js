/**
 * Announcements API service.
 * All calls go through the shared fetch-based `api` client, which attaches
 * the JWT token automatically and handles 401 session expiry.
 */
import { api } from './api';

// ---- Query-string builder (same pattern as leave.js) ----------------------
function buildQs(params) {
  if (!params) return '';
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '' && v !== false
  );
  if (!entries.length) return '';
  return '?' + entries
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
    .join('&');
}

// ---- API surface ----------------------------------------------------------
export const announcementsApi = {
  // ---- Feed (employee / manager / admin feed) ----------------------------
  /** List announcements. Pass mode='manage' for the admin management table. */
  list: (params) =>
    api.get('/announcements' + buildQs(params)),

  /** Latest N announcements for dashboard widgets (System Narrative etc.).
   *  Returns a bare array sorted by pinned-first then newest, role-filtered. */
  latest: (limit = 5) =>
    api.get('/announcements/latest' + buildQs({ limit })),

  /** Count unread announcements for the current user. */
  unreadCount: () =>
    api.get('/announcements/unread-count'),

  /** Fetch a single announcement by id. */
  one: (id) =>
    api.get(`/announcements/${id}`),

  // ---- Admin CRUD --------------------------------------------------------
  /** Create a new announcement (draft). */
  create: (payload) =>
    api.post('/announcements', payload),

  /** Update an existing announcement. */
  update: (id, payload) =>
    api.put(`/announcements/${id}`, payload),

  /** Delete an announcement. */
  remove: (id) =>
    api.delete(`/announcements/${id}`),

  // ---- Lifecycle transitions ---------------------------------------------
  /** Publish a draft announcement (admin/hr only). */
  publish: (id) =>
    api.post(`/announcements/${id}/publish`),

  /** Archive an announcement (admin/hr only). */
  archive: (id) =>
    api.post(`/announcements/${id}/archive`),

  // ---- Engagement tracking -----------------------------------------------
  /** Mark an announcement as read for the current user. */
  markRead: (id) =>
    api.post(`/announcements/${id}/read`),

  /** Acknowledge a mandatory announcement. */
  acknowledge: (id) =>
    api.post(`/announcements/${id}/acknowledge`),

  // ---- Analytics ---------------------------------------------------------
  /** Read/ack stats for a single announcement (admin/hr/manager). */
  analytics: (id) =>
    api.get(`/announcements/${id}/analytics`),
};

// ---- Static config (kept here so all pages share the same source of truth)

export const ANNOUNCEMENT_CATEGORIES = [
  'Company Updates',
  'Holidays',
  'Payroll',
  'Policies',
  'IT Maintenance',
  'Events',
  'Compliance',
  'Emergency Alerts',
  'Training',
];

export const ANNOUNCEMENT_PRIORITIES = [
  { value: 'normal',    label: 'Normal' },
  { value: 'important', label: 'Important' },
  { value: 'critical',  label: 'Critical' },
];

export const ANNOUNCEMENT_SCOPES = [
  { value: 'company',    label: 'Company-wide' },
  { value: 'department', label: 'Department' },
  { value: 'role',       label: 'Role' },
  { value: 'individual', label: 'Individual' },
];
