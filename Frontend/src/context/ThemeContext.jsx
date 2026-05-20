import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'hrms.settings.theme';
const VALID = ['light', 'dark'];

const ThemeContext = createContext({
  theme: 'light',
  setTheme: () => {},
  toggleTheme: () => {},
});

function readInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = raw.startsWith('"') ? JSON.parse(raw) : raw;
      if (VALID.includes(parsed)) return parsed;
    }
    // Migrate any role-scoped legacy keys (admin/manager/employee).
    for (const k of [
      'hrms.settings.admin.theme',
      'hrms.settings.manager.theme',
      'hrms.settings.employee.theme',
    ]) {
      const v = window.localStorage.getItem(k);
      if (v) {
        const parsed = v.startsWith('"') ? JSON.parse(v) : v;
        if (VALID.includes(parsed)) return parsed;
      }
    }
  } catch {
    /* ignore */
  }
  return 'light';
}

function applyThemeClass(theme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
    root.setAttribute('data-theme', 'dark');
    root.style.colorScheme = 'dark';
  } else {
    root.classList.remove('dark');
    root.setAttribute('data-theme', 'light');
    root.style.colorScheme = 'light';
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readInitialTheme);

  useEffect(() => {
    applyThemeClass(theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(theme));
      // Keep legacy role-scoped keys in sync so existing settings UIs that
      // still read them on first render get a consistent value.
      window.localStorage.setItem('hrms.settings.admin.theme', JSON.stringify(theme));
      window.localStorage.setItem('hrms.settings.manager.theme', JSON.stringify(theme));
      window.localStorage.setItem('hrms.settings.employee.theme', JSON.stringify(theme));
    } catch {
      /* ignore */
    }
  }, [theme]);

  // React to changes from other tabs.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          const parsed = e.newValue.startsWith('"') ? JSON.parse(e.newValue) : e.newValue;
          if (VALID.includes(parsed)) setThemeState(parsed);
        } catch {
          /* ignore */
        }
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setTheme = useCallback((value) => {
    const next = typeof value === 'function' ? value(theme) : value;
    if (VALID.includes(next)) setThemeState(next);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme, isDark: theme === 'dark' }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

export default ThemeContext;
