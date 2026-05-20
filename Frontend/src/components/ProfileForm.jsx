import { useEffect, useState } from 'react';
import InputField from './InputField';

export default function ProfileForm({ initial, editing = false, onCancel, onSave }) {
  const [form, setForm] = useState(initial);
  const [saved, setSaved] = useState(false);

  // Re-sync local state whenever the parent supplies a new `initial` object —
  // important because /auth/me may resolve after first render.
  useEffect(() => { setForm(initial); }, [initial]);

  function update(name) {
    return (e) => setForm({ ...form, [name]: e.target.value });
  }

  function handleSave(e) {
    e.preventDefault();
    onSave?.(form);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  function handleCancel() {
    setForm(initial);
    onCancel?.();
  }

  return (
    <form onSubmit={handleSave} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900">Personal Information</h3>
          <p className="text-xs text-slate-500">Update your details. Changes are saved locally for this preview.</p>
        </div>
        {saved && (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
            Saved
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <InputField label="Full Name"  name="fullName"   value={form.fullName || ''}   onChange={update('fullName')}   disabled={!editing} required />
        <InputField label="Email"      name="email"      type="email" value={form.email || ''} onChange={update('email')} disabled={!editing} required />
        <InputField label="Phone"      name="phone"      type="tel"   value={form.phone || ''} onChange={update('phone')} disabled={!editing} placeholder="+91 98765 43210" />
        <InputField label="Employee ID" name="employeeId" value={form.employeeId || ''} onChange={update('employeeId')} disabled />
        <InputField label="Department" name="department" value={form.department || ''} onChange={update('department')} disabled={!editing} />
        <InputField label="Position"   name="position"   value={form.position || ''}   onChange={update('position')}   disabled={!editing} />
        <InputField label="Location"   name="location"   value={form.location || ''}   onChange={update('location')}   disabled={!editing} />
        <InputField label="Manager"    name="manager"    value={form.manager || ''}    onChange={update('manager')}    disabled />
      </div>

      <div className="mt-5">
        <InputField
          label="Bio"
          name="bio"
          type="textarea"
          rows={3}
          value={form.bio || ''}
          onChange={update('bio')}
          disabled={!editing}
          placeholder="A short description about yourself"
        />
      </div>

      {editing && (
        <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-brand-700"
          >
            Save Changes
          </button>
        </div>
      )}
    </form>
  );
}

export function ChangePasswordForm() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  function update(name) {
    return (e) => setForm({ ...form, [name]: e.target.value });
  }

  function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!form.current || !form.next || !form.confirm) {
      setError('Please fill in every field.');
      return;
    }
    if (form.next.length < 6) {
      setError('New password must be at least 6 characters.');
      return;
    }
    if (form.next !== form.confirm) {
      setError("New password and confirmation don't match.");
      return;
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    setForm({ current: '', next: '', confirm: '' });
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900">Change Password</h3>
          <p className="text-xs text-slate-500">Use a strong password you don't reuse anywhere else.</p>
        </div>
        {saved && (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
            Password updated
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <InputField label="Current Password" name="current" type="password" value={form.current} onChange={update('current')} required />
        <InputField label="New Password"     name="next"    type="password" value={form.next}    onChange={update('next')}    required hint="At least 6 characters" />
        <InputField label="Confirm Password" name="confirm" type="password" value={form.confirm} onChange={update('confirm')} required />
      </div>

      {error && <p className="mt-3 text-xs text-red-600">{error}</p>}

      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          className="rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          Update Password
        </button>
      </div>
    </form>
  );
}
