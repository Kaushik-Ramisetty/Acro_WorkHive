import { useEffect, useState, useCallback } from 'react';

/**
 * usePersistedState — like useState but mirrors the value to localStorage so
 * settings survive a page reload. The first read happens lazily inside the
 * initializer so SSR / non-window contexts don't crash.
 *
 *   const [theme, setTheme] = usePersistedState('hrms.settings.theme', 'light');
 *
 * @template T
 * @param {string} key      localStorage key (use a "hrms.settings.*" prefix)
 * @param {T}      initial  default value when nothing is stored yet
 * @returns {[T, (v: T | ((prev: T) => T)) => void]}
 */
export function usePersistedState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      if (typeof window === 'undefined') return initial;
      const raw = window.localStorage.getItem(key);
      return raw == null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(key, JSON.stringify(value));
      }
    } catch {
      /* quota / disabled storage — ignore */
    }
  }, [key, value]);

  return [value, setValue];
}

/**
 * useSaveFeedback — returns [savedFlag, fireSaved] where calling fireSaved()
 * sets the flag to true for `ms` milliseconds. Useful for "Saved ✓" toasts.
 */
export function useSaveFeedback(ms = 1800) {
  const [saved, setSaved] = useState(false);
  const fire = useCallback(() => {
    setSaved(true);
    const t = setTimeout(() => setSaved(false), ms);
    return () => clearTimeout(t);
  }, [ms]);
  return [saved, fire];
}

export default usePersistedState;
