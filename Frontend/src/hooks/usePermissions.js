// React hook wrapper around the permission utilities. Lets components
// declaratively check capabilities of the currently-logged-in user
// without scattering role strings throughout the JSX.
//
// Usage:
//
//   const { has, hasAny, role } = usePermissions();
//   if (!has(PERMISSIONS.LEAVE_APPROVE_MANAGER)) return null;
//
// Backward compatibility: existing components that read `user.role`
// directly are unaffected. This hook is purely additive.

import { useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import {
  PERMISSIONS,
  hasPermission,
  hasAnyPermission,
  hasAllPermissions,
  permissionsForRole,
} from '../utils/permissions';

export function usePermissions() {
  const { user, role } = useAuth();
  return useMemo(() => ({
    user,
    role,
    permissions: permissionsForRole(role),
    has:    (perm)  => hasPermission(user || role, perm),
    hasAny: (perms) => hasAnyPermission(user || role, perms),
    hasAll: (perms) => hasAllPermissions(user || role, perms),
    PERMISSIONS,
  }), [user, role]);
}

export { PERMISSIONS };
