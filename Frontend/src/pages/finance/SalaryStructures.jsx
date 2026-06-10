/**
 * Salary Structures
 *
 * Enterprise payroll flow:
 *   1. Finance picks an existing DB employee from a searchable dropdown
 *   2. System auto-loads existing salary structure if present
 *   3. Finance enters Annual CTC → system computes full breakup
 *   4. Save creates a NEW salary revision row (never overwrites history)
 *      Exception: same effective_from as an existing active row = same-day correction (in-place update)
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import financeApi from '../../services/financeApi';

function fmt(n) {
  if (n === undefined || n === null) return '₹0';
  return `₹${Number(n).toLocaleString('en-IN')}`;
}

// ─── Reusable searchable employee dropdown ────────────────────────────────────

function EmployeeSearch({ employees, value, onChange, disabled }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const selected = employees.find((e) => e.id === value);

  useEffect(() => {
    if (selected && !open) setQuery('');
  }, [selected, open]);

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const displayValue = open ? query : (selected ? `${selected.name} (${selected.employee_code})` : query);

  const filtered = employees.filter((e) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      e.name.toLowerCase().includes(q) ||
      e.employee_code.toLowerCase().includes(q) ||
      (e.email || '').toLowerCase().includes(q) ||
      (e.department || '').toLowerCase().includes(q)
    );
  });

  const select = (emp) => {
    onChange(emp.id);
    setQuery('');
    setOpen(false);
  };

  const clear = () => {
    onChange(null);
    setQuery('');
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <input
          type="text"
          disabled={disabled}
          value={displayValue}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); if (!e.target.value) onChange(null); }}
          onFocus={() => setOpen(true)}
          placeholder="Search by name, code, or department…"
          className={`w-full rounded-lg border border-slate-200 pl-3 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 ${disabled ? 'bg-slate-50 cursor-not-allowed' : ''}`}
        />
        {value && !disabled && (
          <button onClick={clear} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs">✕</button>
        )}
      </div>
      {open && !disabled && (
        <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-56 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-3 text-xs text-slate-400">No employees found</div>
          ) : (
            filtered.map((emp) => (
              <button
                key={emp.id}
                onMouseDown={() => select(emp)}
                className={`w-full text-left px-4 py-2.5 hover:bg-brand-50 transition-colors text-sm border-b border-slate-50 last:border-0 ${
                  value === emp.id ? 'bg-brand-50' : ''
                }`}
              >
                <span className="font-medium text-slate-800">{emp.name}</span>
                <span className="ml-2 text-xs text-slate-400 font-mono">{emp.employee_code}</span>
                <span className="block text-xs text-slate-400 mt-0.5">{emp.department} · {emp.designation}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ─── CTC Modal (From Annual CTC) ──────────────────────────────────────────────

function CTCModal({ employees, onClose, onSaved }) {
  const [step, setStep] = useState('input'); // 'input' | 'preview'
  const [selectedEmpId, setSelectedEmpId] = useState(null);
  const [annualCTC, setAnnualCTC] = useState('');
  const [bankName, setBankName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [ifsc, setIfsc] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [revisionReason, setRevisionReason] = useState('');
  const [preview, setPreview] = useState(null);
  const [existingStructure, setExistingStructure] = useState(null);
  const [busy, setBusy] = useState(false);
  const [checkingExisting, setCheckingExisting] = useState(false);
  const [err, setErr] = useState('');

  // When employee is selected, auto-load existing structure
  const handleEmployeeSelect = async (empId) => {
    setSelectedEmpId(empId);
    setExistingStructure(null);
    setAnnualCTC('');
    setBankName(''); setAccountNumber(''); setIfsc(''); setEffectiveFrom(''); setRevisionReason('');
    if (!empId) return;

    setCheckingExisting(true);
    try {
      const existing = await financeApi.getSalaryStructure(empId);
      setExistingStructure(existing);
      // Auto-fill bank details from existing structure
      setBankName(existing.bank_name || '');
      setAccountNumber(existing.account_number || '');
      setIfsc(existing.ifsc_code || '');
      // Do NOT pre-fill effectiveFrom — user must enter a new date for the revision
      // so the backend creates a true new revision row (not a same-day correction).
      setEffectiveFrom('');
      // Pre-fill CTC if known
      if (existing.annual_ctc) setAnnualCTC(String(Math.round(existing.annual_ctc)));
    } catch {
      // 404 = no existing structure, which is fine
    } finally {
      setCheckingExisting(false);
    }
  };

  const handlePreview = async () => {
    if (!selectedEmpId) { setErr('Please select an employee'); return; }
    if (!annualCTC || parseFloat(annualCTC) <= 0) { setErr('Please enter a valid Annual CTC'); return; }
    setBusy(true); setErr('');
    try {
      const data = await financeApi.previewCTC({
        employee_id: selectedEmpId,
        annual_ctc: parseFloat(annualCTC),
        bank_name: bankName || undefined,
        account_number: accountNumber || undefined,
        ifsc_code: ifsc || undefined,
        effective_from: effectiveFrom || undefined,
      });
      setPreview(data);
      setStep('preview');
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Preview failed');
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async () => {
    setBusy(true); setErr('');
    try {
      await financeApi.structureFromCTC({
        employee_id: selectedEmpId,
        annual_ctc: parseFloat(annualCTC),
        bank_name: bankName || undefined,
        account_number: accountNumber || undefined,
        ifsc_code: ifsc || undefined,
        effective_from: effectiveFrom || undefined,
        revision_reason: revisionReason || undefined,
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const selectedEmp = employees.find((e) => e.id === selectedEmpId);

  const Row = ({ label, value, accent = '' }) => (
    <div className="flex justify-between py-1.5 border-b border-slate-50 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono font-medium ${accent || 'text-slate-700'}`}>{fmt(value)}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-10 mb-8 w-full max-w-lg bg-white rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">
              {existingStructure ? 'New Salary Revision (CTC)' : 'Create Salary Structure from Annual CTC'}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">Auto-split CTC into salary components using Indian payroll rules</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg">✕</button>
        </div>

        <div className="p-6 space-y-4">
          {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3 border border-rose-100">{err}</p>}

          {step === 'input' && (
            <>
              {/* Employee Search */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Select Employee *</label>
                <EmployeeSearch
                  employees={employees}
                  value={selectedEmpId}
                  onChange={handleEmployeeSelect}
                />
                {checkingExisting && (
                  <p className="text-xs text-slate-400 mt-1">Checking existing structure…</p>
                )}
              </div>

              {/* Existing structure notice */}
              {existingStructure && (
                <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800">
                  <strong>Active revision found</strong> — CTC: {fmt(existingStructure.annual_ctc)} | Net/month: {fmt(existingStructure.net_monthly)} | Effective: {existingStructure.effective_from || 'N/A'}<br />
                  Saving creates a <strong>new salary revision</strong>. The current revision remains in history and closed payrolls are never affected.
                </div>
              )}

              {/* Employee info card */}
              {selectedEmp && (
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600 grid grid-cols-2 gap-1">
                  <span><strong>Code:</strong> {selectedEmp.employee_code}</span>
                  <span><strong>Dept:</strong> {selectedEmp.department}</span>
                  <span><strong>Desig:</strong> {selectedEmp.designation}</span>
                  <span><strong>Email:</strong> {selectedEmp.email}</span>
                </div>
              )}

              {/* CTC input */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Annual CTC (₹) *</label>
                  <input
                    type="number"
                    step="1000"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                    value={annualCTC}
                    onChange={(e) => setAnnualCTC(e.target.value)}
                    placeholder="e.g. 600000"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Effective From</label>
                  <input
                    type="date"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                  />
                </div>
              </div>

              {/* Bank details */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Bank Details</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Bank Name</label>
                    <input type="text" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                      value={bankName} onChange={(e) => setBankName(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Account Number</label>
                    <input type="text" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                      value={accountNumber} onChange={(e) => setAccountNumber(e.target.value)} />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-slate-600 mb-1">IFSC Code</label>
                    <input type="text" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                      value={ifsc} onChange={(e) => setIfsc(e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Revision reason */}
              {existingStructure && (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Reason for Revision <span className="text-slate-400">(recommended)</span>
                  </label>
                  <textarea
                    rows={2}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                    placeholder="e.g. Annual appraisal, promotion, market correction…"
                    value={revisionReason}
                    onChange={(e) => setRevisionReason(e.target.value)}
                  />
                </div>
              )}
            </>
          )}

          {step === 'preview' && preview && (
            <>
              {selectedEmp && (
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-bold text-sm">
                    {selectedEmp.name[0]}
                  </div>
                  <div>
                    <p className="font-semibold text-slate-800">{selectedEmp.name}</p>
                    <p className="text-slate-400">{selectedEmp.employee_code} · {selectedEmp.department}</p>
                  </div>
                </div>
              )}
              <div className="rounded-xl bg-brand-50 border border-brand-100 p-3 text-center">
                <p className="text-xs text-brand-600 font-medium">Annual CTC: {fmt(preview.annual_ctc)}</p>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-0.5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Earnings (Monthly)</p>
                <Row label="Basic" value={preview.basic} />
                <Row label="HRA" value={preview.hra} />
                {preview.lta > 0 && <Row label="LTA" value={preview.lta} />}
                <Row label="Special Allowance" value={preview.special_allowance} />
                <Row label="Transport Allowance" value={preview.transport_allowance} />
                {preview.da > 0 && <Row label="DA" value={preview.da} />}
                {preview.medical_allowance > 0 && <Row label="Medical Allowance" value={preview.medical_allowance} />}
                <Row label="Gross Monthly" value={preview.gross_monthly} accent="text-slate-800 font-bold" />
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-0.5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Deductions (Monthly)</p>
                <Row label="PF (Employee)" value={preview.pf_employee} accent="text-indigo-700" />
                <Row label="PF (Employer)" value={preview.pf_employer} accent="text-indigo-500" />
                <Row label="ESI (Employee)" value={preview.esi_employee} accent="text-purple-700" />
                <Row label="ESI (Employer)" value={preview.esi_employer} accent="text-purple-500" />
                <Row label="Professional Tax" value={preview.professional_tax} accent="text-amber-700" />
                <Row label="TDS" value={preview.tds} accent="text-rose-600" />
              </div>
              <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3 flex justify-between items-center">
                <span className="text-sm font-semibold text-emerald-800">Net Monthly Take-Home</span>
                <span className="font-mono text-lg font-bold text-emerald-700">{fmt(preview.net_monthly)}</span>
              </div>
              {existingStructure && (
                <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-xs text-blue-800 text-center">
                  A <strong>new salary revision</strong> will be created effective {effectiveFrom || 'today'}.
                  The current revision is preserved in history — closed payrolls remain unaffected.
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex gap-3 justify-end px-6 pb-6">
          {step === 'preview' && (
            <button onClick={() => setStep('input')} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
              Back
            </button>
          )}
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          {step === 'input' ? (
            <button onClick={handlePreview} disabled={busy || checkingExisting}
              className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
              {busy ? 'Computing…' : 'Preview Breakdown'}
            </button>
          ) : (
            <button onClick={handleSave} disabled={busy}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
              {busy ? 'Saving…' : (existingStructure ? 'Save Revision' : 'Save Structure')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Manual Entry Modal ───────────────────────────────────────────────────────

function StructureModal({ employees, initial, onClose, onSaved }) {
  const buildForm = (src) => ({
    employee_id: src?.employee_id || null,
    basic: src?.basic ?? '',
    hra: src?.hra ?? '',
    da: src?.da ?? '',
    special_allowance: src?.special_allowance ?? '',
    transport_allowance: src?.transport_allowance ?? '',
    medical_allowance: src?.medical_allowance ?? '',
    other_allowances: src?.other_allowances ?? '',
    pf_employee: src?.pf_employee ?? '',
    pf_employer: src?.pf_employer ?? '',
    esi_employee: src?.esi_employee ?? '',
    esi_employer: src?.esi_employer ?? '',
    professional_tax: src?.professional_tax ?? '',
    tds: src?.tds ?? '',
    bank_name: src?.bank_name ?? '',
    account_number: src?.account_number ?? '',
    ifsc_code: src?.ifsc_code ?? '',
    effective_from: src?.effective_from ?? '',
    revision_reason: '',
  });

  const [form, setForm] = useState(buildForm(initial));
  const [existingStructure, setExistingStructure] = useState(initial || null);
  const [checkingExisting, setCheckingExisting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  // When employee selected, auto-load existing structure if any
  const handleEmployeeSelect = async (empId) => {
    set('employee_id', empId);
    setExistingStructure(null);
    if (!empId) return;

    setCheckingExisting(true);
    try {
      const existing = await financeApi.getSalaryStructure(empId);
      setExistingStructure(existing);
      // Fill all fields from existing structure EXCEPT effective_from.
      // Clearing effective_from forces a new date, ensuring the backend
      // creates a proper new revision row (not a same-day correction).
      setForm({ ...buildForm(existing), effective_from: '' });
    } catch {
      // 404 = no structure, keep empty form
      setForm((f) => ({ ...buildForm(null), employee_id: empId }));
    } finally {
      setCheckingExisting(false);
    }
  };

  const NUMERIC_FIELDS = [
    'basic', 'hra', 'da', 'special_allowance', 'transport_allowance',
    'medical_allowance', 'other_allowances',
    'pf_employee', 'pf_employer', 'esi_employee', 'esi_employer',
    'professional_tax', 'tds',
  ];

  const gross = ['basic', 'hra', 'da', 'special_allowance', 'transport_allowance', 'medical_allowance', 'other_allowances']
    .reduce((s, k) => s + (parseFloat(form[k]) || 0), 0);
  const deductions = ['pf_employee', 'esi_employee', 'professional_tax', 'tds']
    .reduce((s, k) => s + (parseFloat(form[k]) || 0), 0);
  const net = gross - deductions;

  const submit = async () => {
    if (!form.employee_id) { setErr('Please select an employee'); return; }
    setBusy(true); setErr('');
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, NUMERIC_FIELDS.includes(k) ? (parseFloat(v) || 0) : v])
      );
      await financeApi.upsertSalaryStructure(payload);
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Failed to save');
    } finally {
      setBusy(false);
    }
  };

  const Field = ({ label, name, type = 'number' }) => (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      <input
        type={type}
        step="any"
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
        value={form[name] ?? ''}
        onChange={(e) => set(name, e.target.value)}
      />
    </div>
  );

  const isEdit = !!existingStructure;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-8 mb-8 w-full max-w-2xl bg-white rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">
              {isEdit ? 'New Salary Revision (Manual)' : 'Create Salary Structure (Manual)'}
            </h2>
            {isEdit && <p className="text-xs text-blue-600 mt-0.5">A new salary revision will be created — existing history is preserved</p>}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg">✕</button>
        </div>

        <div className="p-6 space-y-5">
          {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3 border border-rose-100">{err}</p>}

          {/* Employee Search — locked when editing from table click (initial provided) */}
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Employee *</label>
            <EmployeeSearch
              employees={employees}
              value={form.employee_id}
              onChange={initial ? undefined : handleEmployeeSelect}
              disabled={!!initial}
            />
            {checkingExisting && <p className="text-xs text-slate-400 mt-1">Loading existing structure…</p>}
            {!initial && existingStructure && (
              <p className="text-xs text-blue-700 mt-1">Active structure found — saving creates a new revision with the effective date you set below.</p>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Earnings (Monthly ₹)</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Field label="Basic" name="basic" />
              <Field label="HRA" name="hra" />
              <Field label="DA (Dearness Allow.)" name="da" />
              <Field label="Special Allowance" name="special_allowance" />
              <Field label="Transport Allowance" name="transport_allowance" />
              <Field label="Medical Allowance" name="medical_allowance" />
              <Field label="Other Allowances" name="other_allowances" />
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Deductions (Monthly ₹)</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Field label="PF (Employee)" name="pf_employee" />
              <Field label="PF (Employer)" name="pf_employer" />
              <Field label="ESI (Employee)" name="esi_employee" />
              <Field label="ESI (Employer)" name="esi_employer" />
              <Field label="Professional Tax" name="professional_tax" />
              <Field label="TDS" name="tds" />
            </div>
          </div>

          {/* Live preview */}
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 grid grid-cols-3 gap-4 text-sm">
            <div className="text-center">
              <p className="text-xs text-slate-500">Gross Monthly</p>
              <p className="font-mono font-bold text-slate-800">{fmt(gross)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-500">Deductions</p>
              <p className="font-mono font-bold text-rose-600">{fmt(deductions)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-slate-500">Net Monthly</p>
              <p className="font-mono font-bold text-emerald-700">{fmt(net)}</p>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Bank Details</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Field label="Bank Name" name="bank_name" type="text" />
              <Field label="Account Number" name="account_number" type="text" />
              <Field label="IFSC Code" name="ifsc_code" type="text" />
              <Field label="Effective From" name="effective_from" type="date" />
            </div>
          </div>

          {/* Revision reason — shown when editing an existing structure */}
          {isEdit && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                Reason for Revision <span className="text-slate-400">(recommended)</span>
              </label>
              <textarea
                rows={2}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                placeholder="e.g. Annual appraisal, promotion, market correction…"
                value={form.revision_reason || ''}
                onChange={(e) => set('revision_reason', e.target.value)}
              />
            </div>
          )}
        </div>

        <div className="flex gap-3 justify-end px-6 pb-6">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={busy || checkingExisting}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
            {busy ? 'Saving…' : (isEdit ? 'Save Revision' : 'Save Structure')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Salary Revision History Modal ───────────────────────────────────────────

function SalaryRevisionHistory({ employeeId, employeeName, onClose }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!employeeId) return;
    setLoading(true);
    financeApi.getSalaryStructureHistory(employeeId)
      .then(setHistory)
      .catch(() => setErr('Failed to load revision history'))
      .finally(() => setLoading(false));
  }, [employeeId]);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4">
      <div className="mx-auto mt-10 mb-8 w-full max-w-4xl bg-white rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Salary Revision History</h2>
            <p className="text-xs text-slate-400 mt-0.5">{employeeName} — all revisions, newest first</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg">✕</button>
        </div>

        <div className="p-6">
          {loading && (
            <div className="flex items-center justify-center h-24">
              <div className="h-6 w-6 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
            </div>
          )}
          {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3">{err}</p>}

          {!loading && !err && history.length === 0 && (
            <p className="text-sm text-slate-500 text-center py-8">No salary structure history found.</p>
          )}

          {!loading && history.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                    {['#', 'Status', 'Effective From', 'Gross/Month', 'Net/Month', 'Annual CTC', 'Basic', 'PF (Emp)', 'TDS'].map((h) => (
                      <th key={h} className="px-3 py-2.5 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.map((s, idx) => (
                    <tr key={s.id} className={`border-b border-slate-50 transition ${s.is_active ? 'bg-emerald-50' : 'hover:bg-slate-50'}`}>
                      <td className="px-3 py-2.5 font-mono text-xs text-slate-400">v{history.length - idx}</td>
                      <td className="px-3 py-2.5">
                        {s.is_active
                          ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">Active</span>
                          : <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">Superseded</span>
                        }
                      </td>
                      <td className="px-3 py-2.5 font-mono text-slate-700">{s.effective_from || '—'}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-700">{fmt(s.gross_monthly)}</td>
                      <td className="px-3 py-2.5 font-mono font-semibold text-emerald-700">{fmt(s.net_monthly)}</td>
                      <td className="px-3 py-2.5 font-mono text-brand-700">{fmt(s.annual_ctc)}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-600">{fmt(s.basic)}</td>
                      <td className="px-3 py-2.5 font-mono text-indigo-700">{fmt(s.pf_employee)}</td>
                      <td className="px-3 py-2.5 font-mono text-rose-600">{fmt(s.tds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-slate-400">
                Superseded revisions are preserved for audit. Closed payrolls always reference the exact revision used at run time.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end px-6 pb-6">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Close</button>
        </div>
      </div>
    </div>
  );
}


// ─── Tax Declaration Panel ────────────────────────────────────────────────────

function TaxDeclarationPanel({ employees }) {
  const [selectedEmpId, setSelectedEmpId] = useState(null);
  const [fy, setFy] = useState(() => {
    const today = new Date();
    const year = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
    return `${year}-${String(year + 1).slice(2)}`;
  });
  const [form, setForm] = useState({
    sec_80c: '', sec_80d: '', sec_80ccd: '', hra_exemption: '',
    sec_24b: '', other_deductions: '', opted_new_regime: false,
  });
  const [existing, setExisting] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!selectedEmpId) { setExisting(null); setMsg(''); return; }
    setLoading(true);
    financeApi.listTaxDeclarations({ employeeId: selectedEmpId, financialYear: fy })
      .then((rows) => {
        const row = rows.find((r) => r.financial_year === fy) || null;
        setExisting(row);
        if (row) {
          setForm({
            sec_80c: row.sec_80c || '',
            sec_80d: row.sec_80d || '',
            sec_80ccd: row.sec_80ccd || '',
            hra_exemption: row.hra_exemption || '',
            sec_24b: row.sec_24b || '',
            other_deductions: row.other_deductions || '',
            opted_new_regime: row.opted_new_regime || false,
          });
          setMsg('');
        } else {
          setForm({ sec_80c: '', sec_80d: '', sec_80ccd: '', hra_exemption: '', sec_24b: '', other_deductions: '', opted_new_regime: false });
          setMsg('');
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedEmpId, fy]);

  const handleSave = async () => {
    if (!selectedEmpId) { setErr('Select an employee first'); return; }
    setSaving(true); setErr(''); setMsg('');
    try {
      await financeApi.upsertTaxDeclaration({
        employee_id: selectedEmpId,
        financial_year: fy,
        sec_80c: parseFloat(form.sec_80c) || 0,
        sec_80d: parseFloat(form.sec_80d) || 0,
        sec_80ccd: parseFloat(form.sec_80ccd) || 0,
        hra_exemption: parseFloat(form.hra_exemption) || 0,
        sec_24b: parseFloat(form.sec_24b) || 0,
        other_deductions: parseFloat(form.other_deductions) || 0,
        opted_new_regime: form.opted_new_regime,
      });
      setMsg('Declaration saved. TDS will be recomputed on next payroll generation.');
      setExisting(true);
    } catch (e) {
      setErr(e?.data?.detail || e.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const totalDeductions = [
    parseFloat(form.sec_80c) || 0,
    parseFloat(form.sec_80d) || 0,
    parseFloat(form.sec_80ccd) || 0,
    parseFloat(form.hra_exemption) || 0,
    parseFloat(form.sec_24b) || 0,
    parseFloat(form.other_deductions) || 0,
  ].reduce((a, b) => a + b, 0);

  const FY_OPTIONS = ['2025-26', '2024-25', '2023-24'];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-soft p-6 space-y-5">
      <div>
        <h2 className="text-base font-bold text-slate-800">Tax Declarations (Form 12BB / TDS)</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Submit employee investment declarations to compute correct TDS. TDS = ₹0 if annual income is below ₹2,50,000 (Old) or ₹3,00,000 (New regime).
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Employee *</label>
          <EmployeeSearch employees={employees} value={selectedEmpId} onChange={setSelectedEmpId} />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Financial Year</label>
          <select
            value={fy}
            onChange={(e) => setFy(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          >
            {FY_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {loading && <p className="text-xs text-slate-400">Loading declaration…</p>}

      {!loading && selectedEmpId && (
        <>
          {existing && (
            <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-2 text-xs text-blue-800">
              Existing declaration found for FY {fy} — editing will update it.
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {/* Tax Regime */}
            <div className="col-span-2 md:col-span-3">
              <label className="block text-xs font-medium text-slate-600 mb-2">Tax Regime</label>
              <div className="flex gap-4">
                {[{ value: false, label: 'Old Regime (with deductions)' }, { value: true, label: 'New Regime (lower slabs, fewer deductions)' }].map((opt) => (
                  <label key={String(opt.value)} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name="tax_regime"
                      checked={form.opted_new_regime === opt.value}
                      onChange={() => setField('opted_new_regime', opt.value)}
                      className="accent-brand-500"
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            {[
              { key: 'sec_80c', label: 'Section 80C', sub: 'PF, LIC, ELSS, PPF (max ₹1,50,000)', disabled: form.opted_new_regime },
              { key: 'sec_80d', label: 'Section 80D', sub: 'Health insurance (max ₹25,000)', disabled: form.opted_new_regime },
              { key: 'sec_80ccd', label: 'NPS 80CCD(1B)', sub: 'Additional NPS (max ₹50,000)', disabled: form.opted_new_regime },
              { key: 'hra_exemption', label: 'HRA Exemption', sub: 'Computed from rent receipts', disabled: form.opted_new_regime },
              { key: 'sec_24b', label: 'Home Loan Interest 24(b)', sub: 'Max ₹2,00,000 for self-occupied', disabled: form.opted_new_regime },
              { key: 'other_deductions', label: 'Other Deductions', sub: 'Any other approved deductions', disabled: false },
            ].map(({ key, label, sub, disabled }) => (
              <div key={key}>
                <label className={`block text-xs font-medium mb-1 ${disabled ? 'text-slate-400' : 'text-slate-600'}`}>
                  {label}
                </label>
                <input
                  type="number"
                  step="100"
                  disabled={disabled}
                  value={form[key]}
                  onChange={(e) => setField(key, e.target.value)}
                  placeholder="₹0"
                  className={`w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 ${disabled ? 'bg-slate-50 text-slate-400 cursor-not-allowed' : ''}`}
                />
                <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>
              </div>
            ))}
          </div>

          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 flex items-center justify-between text-sm">
            <div>
              <p className="font-medium text-slate-700">Total Declared Deductions</p>
              <p className="text-xs text-slate-400 mt-0.5">
                {form.opted_new_regime ? 'New regime: standard deduction ₹75,000 only' : 'Old regime: standard deduction ₹50,000 + declared deductions above'}
              </p>
            </div>
            <p className="font-mono text-lg font-bold text-brand-700">
              ₹{totalDeductions.toLocaleString('en-IN')}
            </p>
          </div>

          {err && <p className="text-xs text-rose-600 bg-rose-50 rounded-lg p-3 border border-rose-100">{err}</p>}
          {msg && <p className="text-xs text-emerald-700 bg-emerald-50 rounded-lg p-3 border border-emerald-100">{msg}</p>}

          {/* Proof status strip */}
          {existing && typeof existing === 'object' && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 flex items-center justify-between gap-4 flex-wrap text-xs">
              <div className="flex items-center gap-6">
                <span className={existing.proof_submitted ? 'text-emerald-700 font-medium' : 'text-slate-500'}>
                  {existing.proof_submitted ? '✓ Proof submitted' : 'Proof not yet submitted'}
                </span>
                {existing.proof_submitted && (
                  <span className={existing.proof_verified ? 'text-emerald-700 font-medium' : 'text-amber-700'}>
                    {existing.proof_verified
                      ? `✓ Verified by ${existing.verified_by_name || 'HR'}`
                      : 'Awaiting HR verification'}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {!existing.proof_submitted && (
                  <button
                    onClick={async () => {
                      setSaving(true); setErr(''); setMsg('');
                      try {
                        await financeApi.submitTaxDeclarationProof(existing.id);
                        setMsg('Proof marked as submitted. HR can now verify.');
                        setExisting({ ...existing, proof_submitted: true });
                      } catch (e) { setErr(e?.data?.detail || 'Failed'); }
                      finally { setSaving(false); }
                    }}
                    disabled={saving}
                    className="rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50"
                  >
                    Mark Proof Submitted
                  </button>
                )}
                {existing.proof_submitted && !existing.proof_verified && (
                  <>
                    <button
                      onClick={async () => {
                        setSaving(true); setErr(''); setMsg('');
                        try {
                          await financeApi.verifyTaxDeclaration(existing.id, { approved: true });
                          setMsg('Declaration verified. TDS recomputed.');
                          setExisting({ ...existing, proof_verified: true });
                        } catch (e) { setErr(e?.data?.detail || 'Failed'); }
                        finally { setSaving(false); }
                      }}
                      disabled={saving}
                      className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
                    >
                      Verify & Apply
                    </button>
                    <button
                      onClick={async () => {
                        setSaving(true); setErr(''); setMsg('');
                        try {
                          await financeApi.verifyTaxDeclaration(existing.id, { approved: false });
                          setMsg('Declaration proof rejected.');
                          setExisting({ ...existing, proof_verified: false });
                        } catch (e) { setErr(e?.data?.detail || 'Failed'); }
                        finally { setSaving(false); }
                      }}
                      disabled={saving}
                      className="rounded-lg bg-rose-100 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-200 disabled:opacity-50"
                    >
                      Reject Proof
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {saving ? 'Saving…' : (existing ? 'Update Declaration' : 'Save Declaration')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SalaryStructures() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [structures, setStructures] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // null | 'create' | {structure object}
  const [ctcModal, setCtcModal] = useState(false);
  const [historyModal, setHistoryModal] = useState(null); // null | { employeeId, employeeName }
  const [search, setSearch] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [structs, emps] = await Promise.all([
        financeApi.listSalaryStructures(),
        financeApi.listEmployees(),
      ]);
      setStructures(structs);
      setEmployees(emps);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Build a quick lookup map: employee_id → employee record
  const empMap = Object.fromEntries(employees.map((e) => [e.id, e]));

  // Search by name, employee code, or department
  const filtered = structures.filter((s) => {
    if (!search) return true;
    const q = search.toLowerCase();
    const emp = empMap[s.employee_id];
    return (
      String(s.employee_id).includes(q) ||
      (s.employee_name || '').toLowerCase().includes(q) ||
      (s.employee_code || '').toLowerCase().includes(q) ||
      (emp?.department || '').toLowerCase().includes(q)
    );
  });

  if (loading) return (
    <div className="flex items-center justify-center h-48">
      <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
    </div>
  );

  // How many employees don't yet have a salary structure
  const structuredEmpIds = new Set(structures.map((s) => s.employee_id));
  const unstructuredCount = employees.filter((e) => !structuredEmpIds.has(e.id)).length;

  return (
    <div className="space-y-6">
      {modal !== null && (
        <StructureModal
          employees={employees}
          initial={modal === 'create' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      )}
      {ctcModal && (
        <CTCModal employees={employees} onClose={() => setCtcModal(false)} onSaved={load} />
      )}
      {historyModal && (
        <SalaryRevisionHistory
          employeeId={historyModal.employeeId}
          employeeName={historyModal.employeeName}
          onClose={() => setHistoryModal(null)}
        />
      )}

      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          if (role_ === 'admin') navigate('/admin-dashboard/payroll');
          else if (role_ === 'finance_head' || role_ === 'financehead') navigate('/employee-dashboard/finance-head-payroll');
          else navigate('/employee-dashboard/finance-payroll');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Salary Structures</h1>
          <p className="text-sm text-slate-500 mt-0.5">Configure monthly salary components for each employee</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setCtcModal(true)}
            className="flex items-center gap-2 rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100 transition"
          >
            From Annual CTC
          </button>
          <button
            onClick={() => setModal('create')}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 transition"
          >
            + Manual Entry
          </button>
        </div>
      </div>

      {/* Summary chips */}
      <div className="flex flex-wrap gap-3">
        <div className="rounded-lg bg-white border border-slate-200 px-4 py-2 text-sm shadow-sm">
          <span className="text-slate-500">Configured: </span>
          <span className="font-bold text-slate-800">{structures.length}</span>
        </div>
        <div className="rounded-lg bg-white border border-slate-200 px-4 py-2 text-sm shadow-sm">
          <span className="text-slate-500">Total Employees: </span>
          <span className="font-bold text-slate-800">{employees.length}</span>
        </div>
        {unstructuredCount > 0 && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-2 text-sm">
            <span className="text-amber-700 font-medium">{unstructuredCount} employee{unstructuredCount > 1 ? 's' : ''} missing salary structure</span>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Search by name, code, or department…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-brand-400"
        />
        <span className="text-xs text-slate-400">{filtered.length} of {structures.length} records</span>
      </div>

      {/* Table or empty state */}
      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <p className="text-4xl mb-3">💼</p>
          <p className="text-slate-600 font-medium">
            {structures.length === 0 ? 'No salary structures configured yet' : 'No matching records'}
          </p>
          {structures.length === 0 && employees.length > 0 && (
            <p className="text-xs text-slate-400 mt-2 mb-4">
              {employees.length} active employees found — create their salary structures to enable payroll
            </p>
          )}
          {structures.length === 0 && (
            <button
              onClick={() => setCtcModal(true)}
              className="mt-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
            >
              Create First Structure
            </button>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500 uppercase">
                  {['Employee', 'Code', 'Dept', 'Basic', 'HRA', 'Allowances', 'PF', 'ESI', 'TDS', 'Gross/Month', 'Net/Month', 'Annual CTC', 'Eff. Date', 'Actions'].map((h) => (
                    <th key={h} className="px-3 py-3 text-left font-semibold tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => {
                  const emp = empMap[s.employee_id];
                  const name = s.employee_name || emp?.name || `#${s.employee_id}`;
                  const code = s.employee_code || emp?.employee_code || `EMP${String(s.employee_id).padStart(4, '0')}`;
                  const dept = emp?.department || '—';
                  return (
                    <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                      <td className="px-3 py-2.5 font-medium text-slate-800">{name}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-slate-500">{code}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-500">{dept}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-600">{fmt(s.basic)}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-600">{fmt(s.hra)}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-600">
                        {fmt((s.special_allowance || 0) + (s.transport_allowance || 0) + (s.medical_allowance || 0) + (s.other_allowances || 0))}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-indigo-700">{fmt(s.pf_employee)}</td>
                      <td className="px-3 py-2.5 font-mono text-purple-700">{fmt(s.esi_employee)}</td>
                      <td className="px-3 py-2.5 font-mono text-rose-600">{fmt(s.tds)}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-700">{fmt(s.gross_monthly)}</td>
                      <td className="px-3 py-2.5 font-mono font-semibold text-emerald-700">{fmt(s.net_monthly)}</td>
                      <td className="px-3 py-2.5 font-mono text-brand-700">{fmt(s.annual_ctc)}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-slate-500">{s.effective_from || '—'}</td>
                      <td className="px-3 py-2.5">
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => setModal(s)}
                            className="rounded bg-slate-100 text-slate-700 px-2.5 py-1 text-xs font-medium hover:bg-slate-200 transition"
                          >
                            Revise
                          </button>
                          <button
                            onClick={() => setHistoryModal({ employeeId: s.employee_id, employeeName: name })}
                            className="rounded bg-brand-50 text-brand-700 px-2.5 py-1 text-xs font-medium hover:bg-brand-100 transition"
                          >
                            History
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tax Declarations */}
      <TaxDeclarationPanel employees={employees} />
    </div>
  );
}
