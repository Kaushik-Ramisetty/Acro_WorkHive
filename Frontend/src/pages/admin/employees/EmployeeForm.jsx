import { useEffect, useState } from 'react';

const FIELD_BASE =
  'mt-1.5 block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 shadow-sm transition focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-100';

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'employee', label: 'Employee' },
  { value: 'finance', label: 'Finance' },
  { value: 'finance_head', label: 'Finance Head' },
];

export default function EmployeeForm({ open, mode = 'create', initial, reference, onSubmit, onCancel }) {
  const [form, setForm] = useState({
    name: '',
    email: '',
    role: 'employee',
    department_id: '',
    designation_id: '',
    password: '',
    phone: '',
    employee_code: '',
    location: '',
    reporting_manager_id: '',
  });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');

  useEffect(() => {
    if (!open) return;
    setServerError('');
    setErrors({});

    if (mode === 'edit' && initial) {
      setForm({
        name: initial.full_name || '',
        email: initial.email || '',
        role: initial.role || 'employee',
        department_id: initial.department_id || '',
        designation_id: initial.designation_id || '',
        phone: initial.phone || '',
        employee_code: initial.employee_code || '',
        location: initial.location || '',
        reporting_manager_id: initial.reporting_manager_id ?? '',
        password: '',
      });
      return;
    }

    setForm({
      name: '',
      email: '',
      role: 'employee',
      department_id: '',
      designation_id: '',
      password: '',
      phone: '',
      employee_code: '',
      location: '',
      reporting_manager_id: '',
    });
  }, [open, mode, initial]);

  if (!open) return null;

  const update = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  function validate() {
    const next = {};
    if (!form.name.trim()) next.name = 'Name is required.';

    if (mode === 'create') {
      if (!form.email.trim()) next.email = 'Email is required.';
      else if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) next.email = 'Enter a valid email.';

      if (!form.password) next.password = 'Temporary password is required.';
      else if (form.password.length < 4) next.password = 'Password is too short.';
    }

    if (!ROLE_OPTIONS.some((role) => role.value === form.role)) next.role = 'Pick a role.';

    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setServerError('');

    try {
      const payload = mode === 'edit'
        ? {
            name: form.name,
            role: form.role,
            department_id: form.department_id || null,
            designation_id: form.designation_id || null,
            phone: form.phone || null,
            employee_code: form.employee_code || null,
            location: form.location || null,
            // Empty string maps to null so the backend removes the reporting manager.
            reporting_manager_id:
              form.reporting_manager_id === '' ? null : Number(form.reporting_manager_id),
          }
        : {
            name: form.name,
            email: form.email,
            role: form.role,
            department_id: form.department_id || null,
            designation_id: form.designation_id || null,
            password: form.password,
            phone: form.phone || null,
            employee_code: form.employee_code || null,
          };

      await onSubmit(payload);
    } catch (err) {
      setServerError(err?.data?.detail || err?.message || 'Something went wrong.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" onClick={onCancel}>
      <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{mode === 'edit' ? 'Edit Employee' : 'Add Employee'}</h3>
            <p className="text-xs text-slate-500">
              {mode === 'edit'
                ? 'Update role, department, designation, or contact details.'
                : 'Create a new employee account. They can sign in with the temporary password.'}
            </p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {serverError && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-slate-700">Full Name<span className="ml-0.5 text-red-500">*</span></label>
            <input className={FIELD_BASE} value={form.name} onChange={update('name')} placeholder="Jane Doe" />
            {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Email<span className="ml-0.5 text-red-500">*</span></label>
            <input
              type="email"
              className={FIELD_BASE}
              value={form.email}
              onChange={update('email')}
              placeholder="jane.doe@acronotics.com"
              disabled={mode === 'edit'}
            />
            {mode === 'edit' && <p className="mt-1 text-[10px] text-slate-400">Email is the user's login id; can't be changed inline.</p>}
            {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Role<span className="ml-0.5 text-red-500">*</span></label>
            <select className={FIELD_BASE} value={form.role} onChange={update('role')}>
              {ROLE_OPTIONS.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
            </select>
            {errors.role && <p className="mt-1 text-xs text-red-600">{errors.role}</p>}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Department</label>
            <select className={FIELD_BASE} value={form.department_id} onChange={update('department_id')}>
              <option value="">- Select department -</option>
              {(reference?.departments || []).map((department) => (
                <option key={department.id} value={department.id}>{department.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Designation</label>
            <select className={FIELD_BASE} value={form.designation_id} onChange={update('designation_id')}>
              <option value="">- Select designation -</option>
              {(reference?.designations || []).map((designation) => (
                <option key={designation.id} value={designation.id}>{designation.title}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Phone</label>
            <input type="tel" className={FIELD_BASE} value={form.phone} onChange={update('phone')} placeholder="+91 98765 43210" />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">Employee Code</label>
            <input className={FIELD_BASE} value={form.employee_code} onChange={update('employee_code')} placeholder="AIN###" />
          </div>

          {mode === 'edit' && (
            <>
              <div>
                <label className="block text-xs font-semibold text-slate-700">Location</label>
                <input
                  list="employee-location-options"
                  className={FIELD_BASE}
                  value={form.location}
                  onChange={update('location')}
                  placeholder="e.g. Bangalore, Pune"
                />
                <datalist id="employee-location-options">
                  <option value="Bangalore" />
                  <option value="Pune" />
                </datalist>
                <p className="mt-1 text-[10px] text-slate-400">
                  Drives location-scoped holidays + leave calendar for this user.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Reporting Manager</label>
                <select
                  className={FIELD_BASE}
                  value={form.reporting_manager_id}
                  onChange={update('reporting_manager_id')}
                >
                  <option value="">- No reporting manager -</option>
                  {(reference?.managers || [])
                    .filter((manager) => !initial || manager.id !== initial.id)
                    .map((manager) => (
                      <option key={manager.id} value={manager.id}>{manager.full_name}</option>
                    ))}
                </select>
                {initial?.reporting_manager_name && (
                  <p className="mt-1 text-[10px] text-slate-400">
                    Current: <span className="font-medium text-slate-600">{initial.reporting_manager_name}</span>
                  </p>
                )}
              </div>
            </>
          )}

          {mode === 'create' && (
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-700">Temporary Password<span className="ml-0.5 text-red-500">*</span></label>
              <input type="text" className={FIELD_BASE} value={form.password} onChange={update('password')} placeholder="Welcome@2024" />
              {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
              <p className="mt-1 text-[10px] text-slate-500">The new employee can change this from their profile after signing in.</p>
            </div>
          )}

          <div className="sm:col-span-2 mt-2 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-[#1e3acb] px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#1a31b3] disabled:opacity-60"
            >
              {submitting ? 'Saving...' : mode === 'edit' ? 'Save Changes' : 'Create Employee'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
