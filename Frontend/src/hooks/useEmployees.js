import { useCallback, useEffect, useMemo, useState } from 'react';
import { employeesApi } from '../services/employees';

export function useEmployees() {
  const [employees, setEmployees] = useState([]);
  const [reference, setReference] = useState({ roles: [], departments: [], designations: [], managers: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({ q: '', role: '', department_id: '' });

  const loadReference = useCallback(async () => {
    // Pull dropdown reference data + the manager picker list in parallel.
    // Failures are silent so dropdowns gracefully degrade.
    const [refData, mgrs] = await Promise.all([
      employeesApi.reference().catch(() => ({ roles: [], departments: [], designations: [] })),
      employeesApi.managers().catch(() => []),
    ]);
    setReference({ ...refData, managers: Array.isArray(mgrs) ? mgrs : [] });
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await employeesApi.list(filters);
      setEmployees(list);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Failed to load employees.');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { loadReference(); }, [loadReference]);
  useEffect(() => { loadList(); }, [loadList]);

  const create = useCallback(async (payload) => {
    const created = await employeesApi.create(payload);
    setEmployees((prev) => [created, ...prev]);
    return created;
  }, []);

  const update = useCallback(async (id, payload) => {
    const updated = await employeesApi.update(id, payload);
    setEmployees((prev) => prev.map((e) => (e.id === id ? updated : e)));
    return updated;
  }, []);

  const remove = useCallback(async (id) => {
    await employeesApi.remove(id);
    setEmployees((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const setFilter = useCallback((patch) => setFilters((f) => ({ ...f, ...patch })), []);

  return useMemo(() => ({
    employees, reference, loading, error,
    filters, setFilter,
    refresh: loadList,
    create, update, remove,
  }), [employees, reference, loading, error, filters, setFilter, loadList, create, update, remove]);
}
