import { useCallback, useEffect, useRef, useState } from 'react';
import { notificationsApi } from '../services/notifications';

const POLL_INTERVAL_MS = 30000; // 30s polling for unread count

/**
 * useNotifications
 *
 * Powers the navbar dropdown:
 *   - items     → latest 10 (from /notifications/recent)
 *   - unread    → unread badge count
 *   - refresh   → re-fetch recent items + unread count
 *   - markRead  → PUT /notifications/{id}/read
 *   - markAllRead → PUT /notifications/read-all
 *
 * The dedicated Notifications page uses notificationsApi.listPaged() directly
 * so it can paginate / filter / search without polluting the global state.
 */
export function useNotifications({ limit = 10 } = {}) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const refreshCount = useCallback(async () => {
    try {
      const res = await notificationsApi.unreadCount();
      setUnread(res.count || 0);
    } catch { /* silent */ }
  }, []);

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await notificationsApi.recent(limit);
      setItems(Array.isArray(rows) ? rows : []);
    } catch { /* silent */ } finally {
      setLoading(false);
    }
    // Refresh the badge alongside so they don't drift.
    refreshCount();
  }, [limit, refreshCount]);

  // Poll the unread-count endpoint while the hook is mounted.
  useEffect(() => {
    refreshCount();
    timerRef.current = setInterval(refreshCount, POLL_INTERVAL_MS);
    return () => clearInterval(timerRef.current);
  }, [refreshCount]);

  const markRead = useCallback(async (id) => {
    try {
      await notificationsApi.markRead(id);
      setItems((p) => p.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      setUnread((c) => Math.max(0, c - 1));
    } catch { /* silent */ }
  }, []);

  const markAllRead = useCallback(async () => {
    try {
      await notificationsApi.markAllRead();
      setItems((p) => p.map((n) => ({ ...n, is_read: true })));
      setUnread(0);
    } catch { /* silent */ }
  }, []);

  return { items, unread, loading, refreshList, refreshCount, markRead, markAllRead };
}
