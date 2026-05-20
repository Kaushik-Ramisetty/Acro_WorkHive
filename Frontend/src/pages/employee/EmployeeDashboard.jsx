import { createContext, useContext, useState } from "react";
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

// Context so Topbar's hamburger button can open the mobile sidebar.
export const SidebarCtx = createContext({ open: false, setOpen: () => {} });
export const useSidebar = () => useContext(SidebarCtx);

const pageMap = {
  dashboard:      <DashboardPage />,
  myprofile:      <MyProfilePage />,
  "self-service": <SelfServicePage />,
  attendance:     <AttendancePage />,
  leave:         <LeavePage />,
  "comp-off":    <CompOffPage />,
  payroll:       <PayrollPage />,
  myrequests:    <MyRequestsPage />,
  performance:   <PerformancePage />,
  goals:         <GoalsPage />,
  timesheets:    <TimesheetsPage />,
  documents:     <DocumentsPage />,
  training:      <TrainingPage />,
  company:       <CompanyPage />,
  announcements: <AnnouncementsPage />,
  policies:      <PoliciesPage />,
  settings:      <SettingsPage />,
  notifications: <NotificationsPage />,
};

function Shell({ onLogout }) {
  const { currentPage, modalOpen } = useApp();
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
