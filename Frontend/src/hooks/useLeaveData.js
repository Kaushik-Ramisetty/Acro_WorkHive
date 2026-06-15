import { useCallback, useEffect, useMemo, useState } from 'react';
import { leaveApi } from '../services/leave';

/**
 * useLeaveData(filters)
 *
 * Loads /leave/list, /leave/types, and current-user balance in one place,
 * exposes mutation helpers (apply, approve, reject, cancel, approveCancel)
 * and refreshes the affected lists automatically.
 *
 * filters: { status?, employeeId?, pendingMyApproval? }
 */
export function useLeaveData(initialFilters = {}) {
  const [requests, setRequests] = useState([]);
  const [types, setTypes] = useState([]);
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(initialFilters);

  const setFilter = useCallback(
    (patch) => setFilters((f) => ({ ...f, ...patch })),
    [],
  );

  const loadTypes = useCallback(async () => {
    try { setTypes(await leaveApi.types()); } catch { /* silent */ }
  }, []);

  const loadBalances = useCallback(async () => {
    try { setBalances(await leaveApi.myBalance()); } catch { /* silent */ }
  }, []);

  const loadRequests = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = {
        status: filters.status,
        employee_id: filters.employeeId,
        pending_my_approval: filters.pendingMyApproval ? true : undefined,
      };
      const rows = await leaveApi.list(params);
      setRequests(rows);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Failed to load leave requests.');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { loadTypes(); loadBalances(); }, [loadTypes, loadBalances]);
  useEffect(() => { loadRequests(); }, [loadRequests]);

  const apply = useCallback(async (payload) => {
    const created = await leaveApi.apply(payload);
    setRequests((p) => [created, ...p]);
    loadBalances();
    return created;
  }, [loadBalances]);

  // After any approve/reject/cancel action, re-fetch from the backend
  // instead of patching the list in place. This is the simplest way to
  // honour the server-side `pending_my_approval` filter — once a manager
  // approves, the leave moves to next_approver_role='hr' and the backend
  // correctly drops it from the manager's queue.
  const approve = useCallback(async (id) => {
    const updated = await leaveApi.approve(id);
    await loadRequests();
    loadBalances();
    return updated;
  }, [loadRequests, loadBalances]);

  const reject = useCallback(async (id, reason) => {
    const updated = await leaveApi.reject(id, reason);
    await loadRequests();
    return updated;
  }, [loadRequests]);

  const cancel = useCallback(async (id) => {
    const updated = await leaveApi.cancel(id);
    await loadRequests();
    loadBalances();
    return updated;
  }, [loadRequests, loadBalances]);

  const approveCancel = useCallback(async (id) => {
    const updated = await leaveApi.approveCancel(id);
    await loadRequests();
    loadBalances();
    return updated;
  }, [loadRequests, loadBalances]);

  return useMemo(() => ({
    requests, types, balances, loading, error,
    filters, setFilter,
    refresh: loadRequests,
    apply, approve, reject, cancel, approveCancel,
  }), [requests, types, balances, loading, error, filters, setFilter,
       loadRequests, apply, approve, reject, cancel, approveCancel]);
}
