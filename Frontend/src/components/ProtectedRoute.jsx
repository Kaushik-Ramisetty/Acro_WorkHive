import { Navigate, useLocation } from 'react-router-dom'
import { useAuth, dashboardPathForRole } from '../context/AuthContext'

/**
 * ProtectedRoute
 *
 * Props:
 *  - children:    React node to render when access is allowed.
 *  - allowedRoles: optional array of role strings that may view this route.
 *                  If omitted, any authenticated user is allowed.
 */
export default function ProtectedRoute({ children, allowedRoles }) {
  const { isAuthenticated, role } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (allowedRoles && allowedRoles.length > 0 && !allowedRoles.includes(role)) {
    // Wrong role: redirect them to their own dashboard.
    return <Navigate to={dashboardPathForRole(role)} replace />
  }

  return children
}
