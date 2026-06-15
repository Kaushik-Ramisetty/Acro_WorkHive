import { useNavigate } from 'react-router-dom';
import Icon from './Icon';
import NotificationBell from './NotificationBell';
import SearchBar from './SearchBar';
import ProfileMenu from './ProfileMenu';

export default function Navbar({ onMenuClick, role }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="flex items-center gap-4 px-5 py-3">
        <button
          onClick={onMenuClick}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100 md:hidden"
          aria-label="Open sidebar"
        >
          <Icon name="menu" />
        </button>

        <SearchBar variant={role} className="flex-1 max-w-2xl" />

        <div className="ml-auto flex items-center gap-3">
          <NotificationBell />
          <ProfileMenu role={role} />
        </div>
      </div>
    </header>
  );
}
