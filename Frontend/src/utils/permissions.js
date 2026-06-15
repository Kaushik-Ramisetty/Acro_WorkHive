// Centralised permission registry — frontend mirror of
// Backend/app/core/permissions.py.
//
// This module is **additive** and **opt-in**: every existing role check in
// the UI (`user.role === 'admin'`, etc.) continues to work. New code (and
// future refactors) can use `hasPermission(user, PERMISSIONS.X)` so that
// adding a new role only requires updating the table in one place.
//
// Keep this map in sync with the backend. The backend is the source of
// truth — frontend checks are UX hints only; the API still enforces
// authorization on every request.

export const PERMISSIONS = Object.freeze({
  // Employee management
  EMPLOYEE_READ:           'employee:read',
  EMPLOYEE_READ_ALL:       'employee:read_all',
  EMPLOYEE_UPDATE:         'employee:update',
  EMPLOYEE_UPDATE_SELF:    'employee:update_self',
  EMPLOYEE_CREATE:         'employee:create',
  EMPLOYEE_DELETE:         'employee:delete',

  // Leave management
  LEAVE_APPLY:             'leave:apply',
  LEAVE_VIEW_OWN:          'leave:view_own',
  LEAVE_VIEW_TEAM:         'leave:view_team',
  LEAVE_VIEW_ALL:          'leave:view_all',
  LEAVE_APPROVE_MANAGER:   'leave:approve_manager',
  LEAVE_APPROVE_HR:        'leave:approve_hr',
  LEAVE_ADMIN:             'leave:admin',

  // Attendance
  ATTENDANCE_PUNCH:        'attendance:punch',
  ATTENDANCE_VIEW_OWN:     'attendance:view_own',
  ATTENDANCE_VIEW_TEAM:    'attendance:view_team',
  ATTENDANCE_VIEW_ALL:     'attendance:view_all',
  REGULARIZATION_REQUEST:  'regularization:request',
  REGULARIZATION_APPROVE:  'regularization:approve',

  // Timesheet
  TIMESHEET_SUBMIT:        'timesheet:submit',
  TIMESHEET_REVIEW:        'timesheet:review',
  TIMESHEET_PAYROLL_SYNC:  'timesheet:payroll_sync',

  // Onboarding
  CANDIDATE_MANAGE:        'candidate:manage',
  OFFER_MANAGE:            'offer:manage',
  BGV_INITIATE:            'bgv:initiate',
  BGV_VIEW:                'bgv:view',
  CONVERT_CANDIDATE:       'candidate:convert',
  ACTIVATE_EMPLOYEE:       'employee:activate',

  // Misc
  NOTIFICATION_READ_OWN:   'notification:read_own',
  SEARCH_GLOBAL:           'search:global',
  ADMIN_ALL:               'admin:*',
});

const P = PERMISSIONS;

const ROLE_PERMISSIONS = Object.freeze({
  admin: new Set([
    P.ADMIN_ALL,
    P.EMPLOYEE_READ_ALL, P.EMPLOYEE_READ, P.EMPLOYEE_CREATE, P.EMPLOYEE_UPDATE,
    P.EMPLOYEE_UPDATE_SELF, P.EMPLOYEE_DELETE,
    P.LEAVE_APPLY, P.LEAVE_VIEW_OWN, P.LEAVE_VIEW_TEAM, P.LEAVE_VIEW_ALL,
    P.LEAVE_APPROVE_MANAGER, P.LEAVE_APPROVE_HR, P.LEAVE_ADMIN,
    P.ATTENDANCE_PUNCH, P.ATTENDANCE_VIEW_OWN, P.ATTENDANCE_VIEW_TEAM, P.ATTENDANCE_VIEW_ALL,
    P.REGULARIZATION_REQUEST, P.REGULARIZATION_APPROVE,
    P.TIMESHEET_SUBMIT, P.TIMESHEET_REVIEW, P.TIMESHEET_PAYROLL_SYNC,
    P.CANDIDATE_MANAGE, P.OFFER_MANAGE, P.BGV_INITIATE, P.BGV_VIEW,
    P.CONVERT_CANDIDATE, P.ACTIVATE_EMPLOYEE,
    P.NOTIFICATION_READ_OWN, P.SEARCH_GLOBAL,
  ]),
  hr: new Set([
    P.EMPLOYEE_READ_ALL, P.EMPLOYEE_READ, P.EMPLOYEE_CREATE, P.EMPLOYEE_UPDATE,
    P.EMPLOYEE_UPDATE_SELF,
    P.LEAVE_APPROVE_HR, P.LEAVE_VIEW_ALL, P.LEAVE_VIEW_TEAM, P.LEAVE_VIEW_OWN,
    P.ATTENDANCE_VIEW_ALL, P.ATTENDANCE_VIEW_TEAM, P.REGULARIZATION_APPROVE,
    P.CANDIDATE_MANAGE, P.OFFER_MANAGE, P.BGV_INITIATE, P.BGV_VIEW,
    P.CONVERT_CANDIDATE, P.ACTIVATE_EMPLOYEE, P.NOTIFICATION_READ_OWN,
  ]),
  manager: new Set([
    P.EMPLOYEE_READ, P.EMPLOYEE_UPDATE_SELF,
    P.LEAVE_APPLY, P.LEAVE_VIEW_OWN, P.LEAVE_VIEW_TEAM, P.LEAVE_APPROVE_MANAGER,
    P.ATTENDANCE_PUNCH, P.ATTENDANCE_VIEW_OWN, P.ATTENDANCE_VIEW_TEAM,
    P.REGULARIZATION_REQUEST, P.REGULARIZATION_APPROVE,
    P.TIMESHEET_SUBMIT, P.TIMESHEET_REVIEW,
    P.NOTIFICATION_READ_OWN, P.SEARCH_GLOBAL,
  ]),
  employee: new Set([
    P.EMPLOYEE_UPDATE_SELF, P.EMPLOYEE_READ,
    P.LEAVE_APPLY, P.LEAVE_VIEW_OWN,
    P.ATTENDANCE_PUNCH, P.ATTENDANCE_VIEW_OWN,
    P.REGULARIZATION_REQUEST,
    P.TIMESHEET_SUBMIT,
    P.NOTIFICATION_READ_OWN, P.SEARCH_GLOBAL,
  ]),
  candidate: new Set(),
  it_admin: new Set([
    P.EMPLOYEE_READ_ALL, P.EMPLOYEE_READ, P.EMPLOYEE_UPDATE, P.ACTIVATE_EMPLOYEE,
    P.NOTIFICATION_READ_OWN,
  ]),
});

function normaliseRole(role) {
  return (role || '').toString().trim().toLowerCase();
}

/** Returns the Set of effective permissions for a role name. */
export function permissionsForRole(role) {
  return ROLE_PERMISSIONS[normaliseRole(role)] || new Set();
}

/**
 * Pure check: does this user / role have a permission?
 * Accepts either a user object (`{ role }`) or a role string.
 */
export function hasPermission(userOrRole, perm) {
  const role = typeof userOrRole === 'string'
    ? userOrRole
    : (userOrRole && userOrRole.role);
  const perms = permissionsForRole(role);
  if (perms.has(PERMISSIONS.ADMIN_ALL)) return true;
  return perms.has(perm);
}

/** Returns true iff the user has ANY of the listed permissions. */
export function hasAnyPermission(userOrRole, perms) {
  return (perms || []).some((p) => hasPermission(userOrRole, p));
}

/** Returns true iff the user has ALL of the listed permissions. */
export function hasAllPermissions(userOrRole, perms) {
  return (perms || []).every((p) => hasPermission(userOrRole, p));
}
