import NotificationBell from "../../../components/NotificationBell";
import SearchBar from "../../../components/SearchBar";
import ProfileMenu from "../../../components/ProfileMenu";
import { useSidebar } from "../EmployeeDashboard";

const Topbar = () => {
  const { setOpen } = useSidebar();
  return (
    <header className="fixed top-0 left-0 md:left-[240px] right-0 h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 md:px-6 z-20 gap-2">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <button
          onClick={() => setOpen(true)}
          className="md:hidden rounded-md p-2 text-slate-500 hover:bg-slate-100"
          aria-label="Open sidebar"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <SearchBar variant="employee" className="flex-1 max-w-xs md:max-w-md" />
      </div>

      <div className="flex items-center gap-2 md:gap-4">
        <NotificationBell />
        <ProfileMenu role="employee" />
      </div>
    </header>
  );
};

export default Topbar;
