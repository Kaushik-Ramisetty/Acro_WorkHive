import DashboardLayout from './DashboardLayout';

// Finance-specific layout wrapper. Extends DashboardLayout which is already
// role-aware — it reads role from useAuth() and renders the finance sidebar
// via SIDEBAR_CONFIG['finance']. Kept as a separate file so finance-specific
// chrome (e.g. compliance banners, fiscal-year selectors) can be added here
// without touching the shared layout.
export default function FinanceLayout() {
  return <DashboardLayout />;
}
