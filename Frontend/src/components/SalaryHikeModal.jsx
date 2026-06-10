import { useState, useMemo, useEffect } from 'react';
import financeApi from '../services/financeApi';

function fmt(n) {
  if (!n && n !== 0) return '—';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

function fmtL(n) {
  if (!n) return '—';
  return `₹${(n / 100000).toFixed(2)}L`;
}

export default function SalaryHikeModal({ onClose, onSubmitted }) {
  const [employees, setEmployees] = useState([]);
  const [empSearch, setEmpSearch] = useState('');
  const [selectedEmpId, setSelectedEmpId] = useState('');
  const [currentCtc, setCurrentCtc] = useState(null);
  const [currentBasic, setCurrentBasic] = useState(null);
  const [hikeType, setHikeType] = useState('percentage');
  const [hikeValue, setHikeValue] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [reason, setReason] = useState('');
  const [loadingCtc, setLoadingCtc] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [loadingEmps, setLoadingEmps] = useState(true);

  useEffect(() => {
    financeApi.listEmployees()
      .then(setEmployees)
      .catch(() => setEmployees([]))
      .finally(() => setLoadingEmps(false));
  }, []);

  const filteredEmps = useMemo(() => {
    if (!empSearch) return employees;
    const q = empSearch.toLowerCase();
    return employees.filter(e =>
      (e.name || '').toLowerCase().includes(q) ||
      (e.employee_code || '').toLowerCase().includes(q)
    );
  }, [employees, empSearch]);

  const handleEmpChange = async (empId) => {
    setSelectedEmpId(empId);
    setCurrentCtc(null);
    setCurrentBasic(null);
    if (!empId) return;
    setLoadingCtc(true);
    try {
      const struct = await financeApi.getSalaryStructure(empId);
      setCurrentCtc(struct?.annual_ctc ?? 0);
      setCurrentBasic(struct?.basic ?? null);
    } catch {
      setCurrentCtc(0);
    } finally {
      setLoadingCtc(false);
    }
  };

  const hikeVal = parseFloat(hikeValue);
  const newCtc = useMemo(() => {
    if (currentCtc === null || !hikeValue || isNaN(hikeVal) || hikeVal <= 0) return null;
    if (hikeType === 'percentage') return Math.round(currentCtc * (1 + hikeVal / 100));
    return Math.round(currentCtc + hikeVal);
  }, [currentCtc, hikeType, hikeValue, hikeVal]);

  const validate = () => {
    const e = {};
    if (!selectedEmpId) e.employee = 'Employee is required';
    if (!hikeValue || isNaN(hikeVal) || hikeVal <= 0) e.hikeValue = 'Hike value must be a positive number';
    if (!effectiveFrom) e.effectiveFrom = 'Effective date is required';
    if (newCtc !== null && currentCtc !== null && newCtc <= currentCtc)
      e.hikeValue = 'New CTC must be greater than current CTC';
    return e;
  };

  const handleSubmit = async () => {
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    setSubmitting(true);
    setErrors({});
    try {
      const result = await financeApi.createHikeRequest({
        employee_id: parseInt(selectedEmpId),
        hike_type: hikeType,
        hike_value: hikeVal,
        effective_from: effectiveFrom,
        reason: reason || undefined,
      });
      onSubmitted(result);
      onClose();
    } catch (err) {
      setErrors({ submit: err?.data?.detail || err?.message || 'Failed to create hike request' });
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white";
  const errCls = "text-xs text-rose-600 mt-1";

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-8 mb-8 w-full max-w-lg bg-white rounded-2xl shadow-xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Give Salary Hike</h2>
            <p className="text-xs text-slate-400 mt-0.5">Submits a hike request for Finance review</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">

          {/* Employee select */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Employee *</label>
            <input
              type="text"
              placeholder="Search by name or code..."
              value={empSearch}
              onChange={e => setEmpSearch(e.target.value)}
              className={inputCls + " mb-1.5"}
            />
            <select
              value={selectedEmpId}
              onChange={e => handleEmpChange(e.target.value)}
              className={inputCls}
              disabled={loadingEmps}
            >
              <option value="">{loadingEmps ? 'Loading employees...' : '— Select employee —'}</option>
              {filteredEmps.map(e => (
                <option key={e.id} value={e.id}>
                  {e.name} ({e.employee_code || `EMP${e.id}`})
                </option>
              ))}
            </select>
            {errors.employee && <p className={errCls}>{errors.employee}</p>}
          </div>

          {/* Current salary info */}
          {selectedEmpId && (
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500">Current Annual CTC</p>
                <p className="font-mono font-bold text-slate-800 mt-0.5">
                  {loadingCtc ? '…' : fmtL(currentCtc)}
                </p>
              </div>
              {currentBasic !== null && (
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Current Basic (Monthly)</p>
                  <p className="font-mono font-bold text-slate-800 mt-0.5">
                    {loadingCtc ? '…' : fmt(currentBasic)}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Hike type */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-2">Hike Type</label>
            <div className="flex gap-4">
              {[
                { value: 'percentage', label: 'Percentage (%)' },
                { value: 'fixed', label: 'Fixed Amount (₹)' },
              ].map(opt => (
                <label key={opt.value} className="flex items-center gap-2 cursor-pointer text-sm text-slate-700">
                  <input
                    type="radio"
                    value={opt.value}
                    checked={hikeType === opt.value}
                    onChange={() => { setHikeType(opt.value); setHikeValue(''); }}
                    className="accent-brand-600"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          {/* Hike value */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              {hikeType === 'percentage' ? 'Hike Percentage (%) *' : 'Hike Amount (₹) *'}
            </label>
            <input
              type="number"
              value={hikeValue}
              onChange={e => setHikeValue(e.target.value)}
              placeholder={hikeType === 'percentage' ? 'e.g. 15' : 'e.g. 50000'}
              min="0.01"
              step="0.01"
              className={inputCls}
            />
            {errors.hikeValue && <p className={errCls}>{errors.hikeValue}</p>}
          </div>

          {/* New CTC preview */}
          {newCtc !== null && (
            <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-100">
              <p className="text-xs font-semibold text-emerald-700 mb-1">New Annual CTC (Preview)</p>
              <p className="font-mono font-bold text-emerald-800 text-lg">{fmtL(newCtc)}</p>
              {currentCtc > 0 && (
                <p className="text-xs text-emerald-600 mt-0.5">
                  +{fmt(newCtc - currentCtc)} &nbsp;
                  ({((newCtc - currentCtc) / currentCtc * 100).toFixed(1)}% increase)
                </p>
              )}
            </div>
          )}

          {/* Effective from */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Effective From *</label>
            <input
              type="date"
              value={effectiveFrom}
              onChange={e => setEffectiveFrom(e.target.value)}
              className={inputCls}
            />
            {errors.effectiveFrom && <p className={errCls}>{errors.effectiveFrom}</p>}
          </div>

          {/* Reason */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Reason / Remarks</label>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={2}
              placeholder="Annual increment, performance review, promotion, etc."
              className={inputCls + " resize-none"}
            />
          </div>

          {errors.submit && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700">
              {errors.submit}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition"
          >
            {submitting ? 'Submitting…' : 'Submit Hike Request'}
          </button>
        </div>
      </div>
    </div>
  );
}
