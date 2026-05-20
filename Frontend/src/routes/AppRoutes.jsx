import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth, dashboardPathForRole } from '../context/AuthContext';
import ProtectedRoute from '../components/ProtectedRoute';
import DashboardLayout from '../layouts/DashboardLayout';
import LoginPage from '../pages/LoginPage';
import NotFoundPage from '../pages/NotFoundPage';

import AdminHome from '../pages/admin/AdminHome';
import * as Admin from '../pages/admin/index.jsx';
import AdminProfile from '../pages/admin/AdminProfile';
import NotificationsPage from '../pages/shared/NotificationsPage';

import ManagerDashboard from '../pages/manager/ManagerDashboard';
import EmployeeDashboard from '../pages/employee/EmployeeDashboard';

// ── Onboarding-domain routes (merged from the Onboarding frontend) ─────────
import CandidateDashboard from '../pages/candidate/CandidateDashboard';
import VendorBGVReview from '../pages/vendor/VendorBGVReview';
import ChangePasswordPage from '../pages/employee/ChangePasswordPage';

function RootRedirect() {
  const { isAuthenticated, role } = useAuth();
  return <Navigate to={isAuthenticated ? dashboardPathForRole(role) : '/login'} replace />;
}

export default function AppRoutes() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<LoginPage />} />

        {/* Admin (shared layout + nested sub-pages) */}
        <Route
          path="/admin-dashboard"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<AdminHome />} />
          <Route path="profile"        element={<AdminProfile />} />
          <Route path="employees"      element={<Admin.Employees />} />
          <Route path="bench-resources" element={<Admin.BenchResource />} />
          <Route path="self-service"   element={<Admin.SelfService />} />
          <Route path="attendance"     element={<Admin.Attendance />} />
          <Route path="leave"          element={<Admin.LeaveManagement />} />
          <Route path="comp-off"       element={<Admin.CompOff />} />
          <Route path="regularization" element={<Admin.Regularization />} />
          <Route path="approvals"      element={<Admin.Approvals />} />
          <Route path="payroll"        element={<Admin.Payroll />} />
          <Route path="performance"    element={<Admin.Performance />} />
          <Route path="recruitment"    element={<Admin.Recruitment />} />
          <Route path="onboarding"     element={<Admin.Onboarding />} />
          <Route path="reports"        element={<Admin.Reports />} />
          <Route path="announcements"  element={<Admin.Announcements />} />
          <Route path="policies"       element={<Admin.Policies />} />
          <Route path="company"        element={<Admin.Company />} />
          <Route path="help"           element={<Admin.Help />} />
          <Route path="settings"       element={<Admin.Settings />} />
          <Route path="notifications"  element={<NotificationsPage />} />
        </Route>

        {/* Manager — full ZIP shell, drives sub-routes internally */}
        <Route
          path="/manager-dashboard/*"
          element={
            <ProtectedRoute allowedRoles={['manager']}>
              <ManagerDashboard />
            </ProtectedRoute>
          }
        />

        {/* Employee — full ZIP shell, drives sub-routes internally */}
        <Route
          path="/employee-dashboard/*"
          element={
            <ProtectedRoute allowedRoles={['employee']}>
              <EmployeeDashboard />
            </ProtectedRoute>
          }
        />

        {/* Candidate — self-service onboarding portal (merged from onboarding FE) */}
        <Route
          path="/candidate-dashboard"
          element={
            <ProtectedRoute allowedRoles={['candidate']}>
              <CandidateDashboard />
            </ProtectedRoute>
          }
        />

        {/* BGV vendor review portal — public, token-based (no login required) */}
        <Route path="/vendor/bgv-review/:token" element={<VendorBGVReview />} />

        {/* Force password change — shown after first login with a temp password */}
        <Route path="/change-password" element={<ChangePasswordPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  );
}
