import { createContext, useContext, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppProvider, useApp } from "./AppContext";
import { useAuth } from "../../context/AuthContext";
import Sidebar from "./parts/Sidebar";
import Topbar from "./parts/Topbar";
import ApplyLeaveModal from "./parts/ApplyLeaveModal";
import RequestWFHModal from "./parts/RequestWFHModal";

import DashboardPage from "./screens/DashboardPage";
import MyProfilePage from "./screens/MyProfilePage";
import LeavePage from "./screens/LeavePage";
import CompOffPage from "./screens/CompOffPage";
import AttendancePage from "./screens/AttendancePage";
import PayrollPage from "./screens/PayrollPage";
import MyRequestsPage from "./screens/MyRequestsPage";
import PerformancePage from "./screens/PerformancePage";
import GoalsPage from "./screens/GoalsPage";
import TimesheetsPage from "./screens/TimesheetsPage";
import DocumentsPage from "./screens/DocumentsPage";
import TrainingPage from "./screens/TrainingPage";
import CompanyPage from "./screens/CompanyPage";
import AnnouncementsPage from "./screens/AnnouncementsPage";
import SettingsPage from "../../components/SettingsPage";
import PoliciesPage from "../admin/policies/PoliciesPage";
import SelfServicePage from "../shared/SelfServicePage";
import NotificationsPage from "../shared/NotificationsPage";

// Finance payroll pages — imported lazily to avoid loading for non-finance users.
// These are only rendered when role === 'finance' or 'finance_head'.
import PayrollHome    from "../finance/PayrollHome";
import FinanceHeadHome from "../finance/FinanceHeadHome";
import PayrollRunManagement from "../finance/PayrollRunManagement";
import PayrollErrors from "../finance/PayrollErrors";
import FinanceReview from "../finance/FinanceReview";
import PayrollSummary from "../finance/PayrollSummary";
import PayrollAnalytics from "../finance/PayrollAnalytics";
import PayslipBankAdvice from "../finance/PayslipBankAdvice";
import SalaryStructures from "../finance/SalaryStructures";
import SalaryRevision from "../finance/SalaryRevision";
import BonusRequest from "../finance/BonusRequest";
import OffCyclePayments from "../finance/OffCyclePayments";
import Reimbursements from "../finance/Reimbursements";
import FinalSettlement from "../finance/FinalSettlement";
import FinalApproval from "../finance/FinalApproval";

// Recruitment — visible only for Employee + HR + (Recruiter | Recruitment Manager).
// canAccessRecruitment enforces this exactly; no other designation gets access here.
import RecruitmentPage from "./screens/RecruitmentPage";
import { canAccessRecruitment } from "../../utils/recruitmentAccess";

// Context so Topbar's hamburger button can open the mobile sidebar.
export const SidebarCtx = createContext({ open: false, setOpen: () => {} });
export const useSidebar = () => useContext(SidebarCtx);

function Shell({ onLogout }) {
  const { currentPage, modalOpen } = useApp();
  const { employee_type, user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const isClientSite = (employee_type || "").toLowerCase() === "client_site";

  // ── Recruitment access — role/designation-based ───────────────────────────
  // TRUE  for: role=recruiter, OR designation=Recruiter, OR designation=Recruitment Manager
  // FALSE for: plain employees, managers, admins, candidates
  const hasRecruitmentAccess = canAccessRecruitment(user);

  // Access-denied screen for direct URL attempts by unauthorized employees.
  const RecruitmentAccessDenied = () => (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
                  minHeight:300, fontFamily:"'DM Sans',sans-serif", color:"#64748b" }}>
      <div style={{ fontSize:40, marginBottom:12 }}>🔒</div>
      <div style={{ fontSize:16, fontWeight:700, color:"#0d1b2a", marginBottom:6 }}>
        Recruitment Access Restricted
      </div>
      <div style={{ fontSize:13, textAlign:"center", maxWidth:340 }}>
        Recruitment is available only for Recruiters and Recruitment Managers.
        Contact your admin if you believe this is incorrect.
      </div>
    </div>
  );

  // pageMap is built inside Shell so TimesheetsPage receives the live isClientSite prop.
  const pageMap = useMemo(() => ({
    dashboard:      <DashboardPage />,
    myprofile:      <MyProfilePage />,
    "self-service": <SelfServicePage />,
    attendance:     <AttendancePage />,
    leave:         <LeavePage />,
    "comp-off":    <CompOffPage />,
    payroll:       <PayrollPage />,
    myrequests:    <MyRequestsPage />,
    // Recruitment — visible only for Recruiters and Recruitment Managers.
    recruitment:   hasRecruitmentAccess ? <RecruitmentPage /> : <RecruitmentAccessDenied />,
    performance:   <PerformancePage />,
    goals:         <GoalsPage />,
    timesheets:    <TimesheetsPage isClientSite={isClientSite} />,
    documents:     <DocumentsPage />,
    training:      <TrainingPage />,
    company:       <CompanyPage />,
    announcements: <AnnouncementsPage />,
    policies:      <PoliciesPage />,
    settings:      <SettingsPage />,
    notifications: <NotificationsPage />,
    // Finance payroll pages — only rendered for finance / finance_head roles
    "finance-payroll":       <PayrollHome />,
    "finance-head-payroll":  <FinanceHeadHome />,
    "finance-payroll/payroll-runs":     <PayrollRunManagement />,
    "finance-payroll/errors":           <PayrollErrors />,
    "finance-payroll/review":           <FinanceReview />,
    "finance-payroll/summary":          <PayrollSummary />,
    "finance-payroll/analytics":        <PayrollAnalytics />,
    "finance-payroll/payslips":         <PayslipBankAdvice />,
    "finance-payroll/salary-structures": <SalaryStructures />,
    "finance-payroll/salary-revisions":  <SalaryRevision />,
    "finance-payroll/salary-revision":   <SalaryRevision />,
    "finance-payroll/bonus-requests":    <BonusRequest />,
    "finance-payroll/off-cycle-payments": <OffCyclePayments />,
    "finance-payroll/reimbursements":    <Reimbursements />,
    "finance-payroll/ff":                <FinalSettlement />,
    "finance-payroll/head-approval":     <FinalApproval />,
    "finance-head-payroll/final-approval":    <FinalApproval />,
    "finance-head-payroll/salary-revision":   <SalaryRevision />,
    "finance-head-payroll/salary-revisions":  <SalaryRevision />,
    "finance-head-payroll/bonus-requests":    <BonusRequest />,
    "finance-head-payroll/off-cycle-payments": <OffCyclePayments />,
    "finance-head-payroll/summary":        <PayrollSummary />,
    "finance-head-payroll/payslips":       <PayslipBankAdvice />,
    "finance-head-payroll/bank-advice":    <PayslipBankAdvice />,
    "finance-head-payroll/analytics":      <PayrollAnalytics />,
  }), [isClientSite, hasRecruitmentAccess]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <SidebarCtx.Provider value={{ open: sidebarOpen, setOpen: setSidebarOpen }}>
      <div className="min-h-screen" style={{ background: "var(--hrms-bg)" }}>
        <Sidebar onLogout={onLogout} />
        <Topbar />

        {/* Page content */}
        <main className="md:ml-[240px] pt-14 min-h-screen">
          <div className="p-6">
            {pageMap[currentPage] ?? <DashboardPage />}
          </div>
        </main>

        {/* Modals */}
        {modalOpen === "applyLeave" && <ApplyLeaveModal />}
        {modalOpen === "requestWfh" && <RequestWFHModal />}
      </div>
    </SidebarCtx.Provider>
  );
}

export default function EmployeeDashboard() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };
  return (
    <AppProvider>
      <Shell onLogout={handleLogout} />
    </AppProvider>
  );
}
