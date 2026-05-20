import { useState } from 'react';
import { useEmployees } from '../../../hooks/useEmployees';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';
import ConfirmDialog from '../../../components/ConfirmDialog';
import EmployeeTable from './EmployeeTable';
import EmployeeForm from './EmployeeForm';

export default function EmployeesPage() {
  const {
    employees, reference, loading, error,
    filters, setFilter, refresh,
    update, remove,
  } = useEmployees();

  // Modal state — used for editing only. Creating new employees is disabled
  // here; new hires are onboarded via Employees-updated.xlsx + seed.py.
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const openEdit = (emp) => {
    setEditing(emp);
    setFormOpen(true);
  };

  const submitForm = async (payload) => {
    if (!editing) return;
    await update(editing.id, payload);
    setFormOpen(false);
  };

  const askDelete = (emp) => {
    setPendingDelete(emp);
    setConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await remove(pendingDelete.id);
      setConfirmOpen(false);
      setPendingDelete(null);
    } catch (e) {
      // surface inline by re-using the global error path
      alert(e?.data?.detail || e?.message || 'Failed to delete employee.');
    } finally {
      setDeleting(false);
    }
  };

  // Counters for the stat strip
  const total = employees.length;
  const counts = employees.reduce((acc, e) => {
    const role = (e.role || 'unknown').toLowerCase();
    acc[role] = (acc[role] || 0) + 1;
    if ((e.employment_status || '').toLowerCase() === 'active') acc.active = (acc.active || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        subtitle="Manage everyone in the workspace — edit and deactivate accounts."
      />

      {/* Stat strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total',    value: total,                tone: 'text-slate-700',   bg: 'bg-slate-100' },
          { label: 'Active',   value: counts.active || 0,   tone: 'text-emerald-600', bg: 'bg-emerald-50' },
          { label: 'Managers', value: counts.manager || 0,  tone: 'text-amber-600',   bg: 'bg-amber-50' },
          { label: 'Admins',   value: counts.admin || 0,    tone: 'text-rose-600',    bg: 'bg-rose-50' },
        ].map((s) => (
          <div key={s.label} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{s.label}</p>
              <p className={'mt-1 text-2xl font-bold ' + s.tone}>{s.value}</p>
            </div>
            <div className={'h-9 w-9 rounded-xl ' + s.bg} />
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-12">
        <div className="relative sm:col-span-6">
          <Icon name="search" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            value={filters.q}
            onChange={(e) => setFilter({ q: e.target.value })}
            placeholder="Search by name or email…"
            className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>

        <select
          value={filters.role}
          onChange={(e) => setFilter({ role: e.target.value })}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 sm:col-span-3"
        >
          <option value="">All roles</option>
          {(reference?.roles || []).map((r) => (
            <option key={r.id} value={r.name}>{r.name[0].toUpperCase() + r.name.slice(1)}</option>
          ))}
        </select>

        <select
          value={filters.department_id}
          onChange={(e) => setFilter({ department_id: e.target.value })}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 sm:col-span-3"
        >
          <option value="">All departments</option>
          {(reference?.departments || []).map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}

      <EmployeeTable
        employees={employees}
        loading={loading}
        onEdit={openEdit}
        onDelete={askDelete}
      />

      <EmployeeForm
        open={formOpen}
        mode="edit"
        initial={editing}
        reference={reference}
        onSubmit={submitForm}
        onCancel={() => setFormOpen(false)}
      />

      <ConfirmDialog
        open={confirmOpen}
        title="Delete employee?"
        message={pendingDelete ? `${pendingDelete.full_name} will be deactivated and hidden from lists. The DB row is preserved (soft delete).` : ''}
        confirmLabel="Delete"
        tone="danger"
        busy={deleting}
        onCancel={() => { setConfirmOpen(false); setPendingDelete(null); }}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
