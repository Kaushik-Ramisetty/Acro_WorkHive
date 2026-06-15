import { createContext, useContext, useState, useMemo, useCallback } from "react";
import { useLocation, useNavigate as useRouterNavigate } from "react-router-dom";

const AppContext = createContext(null);

const BASE = "/employee-dashboard";

const URL_TO_PAGE = (path) => {
  // /employee-dashboard or /employee-dashboard/<page>
  const trimmed = path.replace(/^\/+|\/+$/g, "").split("/");
  const seg = trimmed[1];
  const sub = trimmed[2];

  if (!seg || !seg.length) return "dashboard";
  if ((seg === "finance-payroll" || seg === "finance-head-payroll") && sub) {
    return `${seg}/${sub}`;
  }
  return seg;
};

export const AppProvider = ({ children }) => {
  const location = useLocation();
  const routerNavigate = useRouterNavigate();
  const [modalOpen, setModalOpen] = useState(null);

  const currentPage = URL_TO_PAGE(location.pathname);

  const navigate = useCallback((page) => {
    routerNavigate(BASE + (page === "dashboard" ? "" : "/" + page));
  }, [routerNavigate]);

  const openModal = useCallback((modal) => setModalOpen(modal), []);
  const closeModal = useCallback(() => setModalOpen(null), []);

  const value = useMemo(
    () => ({ currentPage, navigate, modalOpen, openModal, closeModal }),
    [currentPage, navigate, modalOpen, openModal, closeModal]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useApp = () => useContext(AppContext);
