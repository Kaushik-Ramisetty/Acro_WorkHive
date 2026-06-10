import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import ffApi from '../../services/ffApi';
import financeApi from '../../services/financeApi';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n) {
  if (!n && n !== 0) return '—';
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
}

function StatusBadge({ status }) {
  const map = {
    draft:        'bg-slate-100 text-slate-600',
    calculated:   'bg-blue-100 text-blue-700',
    under_review: 'bg-amber-100 text-amber-700',
    approved:     'bg-emerald-100 text-emerald-700',
    paid:         'bg-green-100 text-green-800',
    cancelled:    'bg-rose-100 text-rose-700',
  };
  const label = status ? status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[status] || 'bg-slate-100 text-slate-600'}`}>
      {label}
    </span>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-800">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

function FieldRow({ label, value, accent }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-slate-50">
      <span className="text-xs text-slate-500 w-48 flex-shrink-0">{label}</span>
      <span className={`text-sm font-medium text-right ${accent || 'text-slate-800'}`}>{value ?? '—'}</span>
    </div>
  );
}

// ─── Create FF Modal ──────────────────────────────────────────────────────────

function CreateFFModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ employee_id: '', last_working_day: '', separation_type: 'resignation', remarks: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [employees, setEmployees] = useState([]);

  useEffect(() => {
    financeApi.listEmployees()
      .then(setEmployees)
      .catch(() => setEmployees([]));
  }, []);

  const submit = async () => {
    if (!form.employee_id) { setError('Employee is required'); return; }
    setSaving(true);
    setError('');
    try {
      const data = {
        employee_id: parseInt(form.employee_id),
        last_working_day: form.last_working_day || undefined,
        separation_type: form.separation_type,
        remarks: form.remarks || undefined,
      };
      const result = await ffApi.create(data);
      onCreated(result);
      onClose();
    } catch (e) {
      setError(e?.data?.detail || e.message || 'Failed to create FF record');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Initiate Final Settlement" onClose={onClose}>
      <div className="space-y-4">
        {error && <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">{error}</div>}
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Employee <span className="text-rose-500">*</span></label>
          <select
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={form.employee_id}
            onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
          >
            <option value="">— Select Employee —</option>
            {employees.map(emp => (
              <option key={emp.id} value={emp.id}>
                {emp.name} ({emp.employee_code}) · {emp.department}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-400">Only active employees are listed</p>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Last Working Day</label>
          <input
            type="date"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={form.last_working_day}
            onChange={(e) => setForm({ ...form, last_working_day: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Separation Type</label>
          <select
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={form.separation_type}
            onChange={(e) => setForm({ ...form, separation_type: e.target.value })}
          >
            <option value="resignation">Resignation</option>
            <option value="termination">Termination</option>
            <option value="retirement">Retirement</option>
            <option value="end_of_contract">End of Contract</option>
            <option value="deceased">Deceased</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Remarks</label>
          <textarea
            rows={2}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Optional notes..."
            value={form.remarks}
            onChange={(e) => setForm({ ...form, remarks: e.target.value })}
          />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={saving} className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50">
            {saving ? 'Creating…' : 'Create FF'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Calculate FF Modal ───────────────────────────────────────────────────────

function CalculateFFModal({ ff, onClose, onCalculated }) {
  const [form, setForm] = useState({
    bonus_pending: ff.bonus_pending || 0,
    variable_pay_pending: ff.variable_pay_pending || 0,
    other_earnings: ff.other_earnings || 0,
    notice_period_days: ff.notice_period_days || 0,
    loan_recovery: ff.loan_recovery || 0,
    advance_recovery: ff.advance_recovery || 0,
    asset_recovery: ff.asset_recovery || 0,
    other_deductions: ff.other_deductions || 0,
    tds_on_settlement: ff.tds_on_settlement || 0,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const calculate = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await ffApi.calculate(ff.id, form);
      onCalculated(result);
      onClose();
    } catch (e) {
      setError(e?.data?.detail || e.message || 'Calculation failed');
    } finally {
      setSaving(false);
    }
  };

  const numField = (key, label) => (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label} (₹)</label>
      <input
        type="number"
        step="0.01"
        min="0"
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: parseFloat(e.target.value) || 0 })}
      />
    </div>
  );

  return (
    <Modal title={`Calculate FF — ${ff.employee_name}`} onClose={onClose}>
      <div className="space-y-5">
        {error && <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">{error}</div>}
        <p className="text-xs text-slate-500">
          Unpaid salary, leave encashment, and gratuity are <strong>auto-computed</strong> from HR records.
          You can override additional amounts below.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Additional Earnings</p>
            {numField('bonus_pending', 'Bonus Pending')}
            {numField('variable_pay_pending', 'Variable Pay Pending')}
            {numField('other_earnings', 'Other Earnings')}
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Deductions / Recoveries</p>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Notice Period (days)</label>
              <input
                type="number"
                min="0"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={form.notice_period_days}
                onChange={(e) => setForm({ ...form, notice_period_days: parseInt(e.target.value) || 0 })}
              />
            </div>
            {numField('loan_recovery', 'Loan Recovery')}
            {numField('advance_recovery', 'Advance Recovery')}
            {numField('asset_recovery', 'Asset Recovery')}
            {numField('other_deductions', 'Other Deductions')}
            {numField('tds_on_settlement', 'TDS on Settlement')}
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={calculate} disabled={saving} className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50">
            {saving ? 'Calculating…' : 'Calculate'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── View FF Modal ────────────────────────────────────────────────────────────

function ViewFFModal({ ff, onClose }) {
  const backendBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const statementUrl = `${backendBase}/finance/ff/${ff.id}/statement`;
  const pdfUrl = `${backendBase}/finance/ff/${ff.id}/pdf`;

  return (
    <Modal title={`Final Settlement — ${ff.employee_name}`} onClose={onClose}>
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Employee</p>
            <FieldRow label="Name" value={ff.employee_name} />
            <FieldRow label="Code" value={ff.employee_code} />
            <FieldRow label="Department" value={ff.department} />
            <FieldRow label="Designation" value={ff.designation} />
            <FieldRow label="Date of Joining" value={ff.date_of_joining} />
            <FieldRow label="Last Working Day" value={ff.last_working_day} />
            <FieldRow label="Separation Type" value={ff.separation_type} />
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Status</p>
            <FieldRow label="Status" value={<StatusBadge status={ff.status} />} />
            <FieldRow label="Approved By" value={ff.approved_by_name} />
            <FieldRow label="Approved At" value={ff.approved_at ? new Date(ff.approved_at).toLocaleDateString('en-IN') : null} />
            <FieldRow label="Paid Date" value={ff.paid_date} />
            <FieldRow label="Payment Reference" value={ff.payment_reference} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-4">
            <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wider mb-3">Earnings</p>
            <FieldRow label="Unpaid Salary" value={fmt(ff.unpaid_salary)} />
            <FieldRow label={`Leave Encashment (${ff.leave_encashment_days} days)`} value={fmt(ff.leave_encashment_amount)} />
            <FieldRow label="Bonus Pending" value={fmt(ff.bonus_pending)} />
            <FieldRow label="Variable Pay" value={fmt(ff.variable_pay_pending)} />
            <FieldRow label={`Gratuity ${ff.gratuity_eligible ? '✓' : '(not eligible)'}`} value={fmt(ff.gratuity_amount)} accent={ff.gratuity_eligible ? 'text-emerald-700' : 'text-slate-400'} />
            <FieldRow label="Other Earnings" value={fmt(ff.other_earnings)} />
            {(ff.pending_reimbursements_amount > 0) && (
              <FieldRow label="Pending Reimbursements" value={fmt(ff.pending_reimbursements_amount)} accent="text-blue-700" />
            )}
            <div className="mt-2 pt-2 border-t border-emerald-200 flex justify-between">
              <span className="text-xs font-bold text-emerald-700">Gross Settlement</span>
              <span className="text-sm font-bold text-emerald-700">{fmt(ff.gross_settlement)}</span>
            </div>
          </div>

          <div className="rounded-xl bg-rose-50 border border-rose-100 p-4">
            <p className="text-xs font-semibold text-rose-700 uppercase tracking-wider mb-3">Deductions</p>
            <FieldRow label={`Notice Period (${ff.notice_period_days} days)`} value={fmt(ff.notice_period_recovery)} />
            <FieldRow label="Loan Recovery" value={fmt(ff.loan_recovery)} />
            <FieldRow label="Advance Recovery" value={fmt(ff.advance_recovery)} />
            {(ff.asset_recovery > 0) && (
              <FieldRow label="Asset Recovery" value={fmt(ff.asset_recovery)} />
            )}
            <FieldRow label="Other Deductions" value={fmt(ff.other_deductions)} />
            <FieldRow label="TDS on Settlement" value={fmt(ff.tds_on_settlement)} />
            <div className="mt-2 pt-2 border-t border-rose-200 flex justify-between">
              <span className="text-xs font-bold text-rose-700">Total Deductions</span>
              <span className="text-sm font-bold text-rose-700">{fmt(ff.total_deductions)}</span>
            </div>
          </div>
        </div>

        <div className="rounded-xl bg-brand-50 border border-brand-200 p-4 flex items-center justify-between">
          <span className="text-sm font-bold text-brand-700">NET FINAL PAYABLE</span>
          <span className="text-2xl font-bold text-brand-700 font-mono">{fmt(ff.net_payable)}</span>
        </div>

        {ff.remarks && (
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm text-slate-600">
            <strong className="text-xs text-slate-500 uppercase block mb-1">Remarks</strong>
            {ff.remarks}
          </div>
        )}

        <div className="flex justify-end gap-2">
          {ff.status !== 'draft' && (
            <a
              href={pdfUrl}
              download
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download PDF
            </a>
          )}
          <a
            href={statementUrl}
            download
            className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Statement (CSV)
          </a>
        </div>
      </div>
    </Modal>
  );
}

// ─── Mark Paid Modal ──────────────────────────────────────────────────────────

function MarkPaidModal({ ff, onClose, onPaid }) {
  const [form, setForm] = useState({ paid_date: new Date().toISOString().split('T')[0], payment_reference: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await ffApi.markPaid(ff.id, form.paid_date, form.payment_reference);
      onPaid(result);
      onClose();
    } catch (e) {
      setError(e?.data?.detail || e.message || 'Failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`Mark FF Paid — ${ff.employee_name}`} onClose={onClose}>
      <div className="space-y-4">
        {error && <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">{error}</div>}
        <div className="rounded-xl bg-brand-50 border border-brand-200 p-4 flex justify-between items-center">
          <span className="text-sm font-semibold text-brand-700">Net Final Payable</span>
          <span className="text-xl font-bold text-brand-700 font-mono">{fmt(ff.net_payable)}</span>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Payment Date <span className="text-rose-500">*</span></label>
          <input type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={form.paid_date} onChange={(e) => setForm({ ...form, paid_date: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Payment Reference / UTR</label>
          <input type="text" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Bank UTR / NEFT reference"
            value={form.payment_reference} onChange={(e) => setForm({ ...form, payment_reference: e.target.value })} />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
          <button onClick={submit} disabled={saving} className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
            {saving ? 'Saving…' : 'Mark as Paid'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function FinalSettlement() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [showCalc, setShowCalc] = useState(null);
  const [showView, setShowView] = useState(null);
  const [showPaid, setShowPaid] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const loadRecords = () => {
    setLoading(true);
    ffApi.list(filterStatus ? { status: filterStatus } : {})
      .then(setRecords)
      .catch((e) => setError(e?.data?.detail || e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadRecords(); }, [filterStatus]);

  const updateRecord = (updated) => {
    setRecords((prev) => prev.map((r) => r.id === updated.id ? updated : r));
  };

  const doAction = async (ffId, action, label) => {
    setActionLoading(`${ffId}-${action}`);
    try {
      let result;
      if (action === 'submit') result = await ffApi.submit(ffId);
      else if (action === 'approve') result = await ffApi.approve(ffId);
      else if (action === 'reject') result = await ffApi.reject(ffId);
      else if (action === 'cancel') result = await ffApi.cancel(ffId);
      if (result) updateRecord(result);
    } catch (e) {
      alert(e?.data?.detail || e.message || `${label} failed`);
    } finally {
      setActionLoading(null);
    }
  };

  const statuses = ['', 'draft', 'calculated', 'under_review', 'approved', 'paid', 'cancelled'];

  return (
    <div className="space-y-6">
      <button
        onClick={() => {
          const role_ = (role || '').toLowerCase();
          navigate(role_ === 'admin' ? '/admin-dashboard/payroll' : '/employee-dashboard/finance');
        }}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Payroll Dashboard
      </button>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Final Settlement (FF)</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage Full & Final settlements for exiting employees</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Initiate FF
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {[
          { label: 'Total', count: records.length, color: 'text-slate-700' },
          { label: 'Draft', count: records.filter(r => r.status === 'draft').length, color: 'text-slate-500' },
          { label: 'Calculated', count: records.filter(r => r.status === 'calculated').length, color: 'text-blue-600' },
          { label: 'Under Review', count: records.filter(r => r.status === 'under_review').length, color: 'text-amber-600' },
          { label: 'Approved', count: records.filter(r => r.status === 'approved').length, color: 'text-emerald-700' },
          { label: 'Paid', count: records.filter(r => r.status === 'paid').length, color: 'text-green-700' },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-3 text-center shadow-sm">
            <p className="text-xs text-slate-500">{s.label}</p>
            <p className={`text-2xl font-bold font-mono mt-0.5 ${s.color}`}>{s.count}</p>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-slate-500">Filter:</span>
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              filterStatus === s
                ? 'bg-brand-500 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {s ? s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'All'}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="h-8 w-8 rounded-full border-4 border-brand-500 border-t-transparent animate-spin" />
          </div>
        ) : error ? (
          <div className="p-6 text-sm text-rose-700">{error}</div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-slate-400">
            <div className="text-4xl mb-3">📋</div>
            <p className="text-sm font-medium">No Final Settlement records found</p>
            <p className="text-xs mt-1">Click "Initiate FF" to start the process for an exiting employee</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {['Employee', 'Department', 'Last Working Day', 'Separation', 'Net Payable', 'Status', 'Approval', 'Payment', 'Actions'].map((h) => (
                    <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((r) => {
                  const isLoading = (act) => actionLoading === `${r.id}-${act}`;
                  return (
                    <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50 transition">
                      <td className="py-3 px-4">
                        <p className="font-medium text-slate-800">{r.employee_name}</p>
                        <p className="text-xs text-slate-400">{r.employee_code || `#${r.employee_id}`}</p>
                      </td>
                      <td className="py-3 px-4 text-slate-500">{r.department}</td>
                      <td className="py-3 px-4 text-slate-500">{r.last_working_day || '—'}</td>
                      <td className="py-3 px-4">
                        <span className="capitalize text-slate-500">{r.separation_type?.replace(/_/g, ' ') || '—'}</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-brand-700">{fmt(r.net_payable)}</td>
                      <td className="py-3 px-4"><StatusBadge status={r.status} /></td>
                      <td className="py-3 px-4 text-xs text-slate-500">{r.approved_by_name || '—'}</td>
                      <td className="py-3 px-4 text-xs text-slate-500">{r.paid_date || '—'}</td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1 flex-wrap">
                          {/* View */}
                          <button
                            onClick={() => setShowView(r)}
                            className="rounded px-2 py-1 text-xs bg-slate-100 text-slate-700 hover:bg-slate-200 transition"
                          >View</button>

                          {/* Calculate */}
                          {['draft', 'calculated'].includes(r.status) && (
                            <button
                              onClick={() => setShowCalc(r)}
                              className="rounded px-2 py-1 text-xs bg-blue-100 text-blue-700 hover:bg-blue-200 transition"
                            >Calculate</button>
                          )}

                          {/* Submit for Review */}
                          {r.status === 'calculated' && (
                            <button
                              onClick={() => doAction(r.id, 'submit', 'Submit')}
                              disabled={isLoading('submit')}
                              className="rounded px-2 py-1 text-xs bg-amber-100 text-amber-700 hover:bg-amber-200 transition disabled:opacity-50"
                            >{isLoading('submit') ? '…' : 'Submit'}</button>
                          )}

                          {/* Approve */}
                          {r.status === 'under_review' && (
                            <button
                              onClick={() => doAction(r.id, 'approve', 'Approve')}
                              disabled={isLoading('approve')}
                              className="rounded px-2 py-1 text-xs bg-emerald-100 text-emerald-700 hover:bg-emerald-200 transition disabled:opacity-50"
                            >{isLoading('approve') ? '…' : 'Approve'}</button>
                          )}

                          {/* Reject */}
                          {r.status === 'under_review' && (
                            <button
                              onClick={() => doAction(r.id, 'reject', 'Reject')}
                              disabled={isLoading('reject')}
                              className="rounded px-2 py-1 text-xs bg-rose-100 text-rose-700 hover:bg-rose-200 transition disabled:opacity-50"
                            >{isLoading('reject') ? '…' : 'Reject'}</button>
                          )}

                          {/* Mark Paid */}
                          {r.status === 'approved' && (
                            <button
                              onClick={() => setShowPaid(r)}
                              className="rounded px-2 py-1 text-xs bg-green-100 text-green-700 hover:bg-green-200 transition"
                            >Mark Paid</button>
                          )}

                          {/* Cancel */}
                          {!['paid', 'cancelled'].includes(r.status) && (
                            <button
                              onClick={() => { if (window.confirm('Cancel this FF record?')) doAction(r.id, 'cancel', 'Cancel'); }}
                              disabled={isLoading('cancel')}
                              className="rounded px-2 py-1 text-xs bg-slate-100 text-slate-500 hover:bg-slate-200 transition disabled:opacity-50"
                            >{isLoading('cancel') ? '…' : 'Cancel'}</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateFFModal
          onClose={() => setShowCreate(false)}
          onCreated={(rec) => { setRecords([rec, ...records]); }}
        />
      )}
      {showCalc && (
        <CalculateFFModal
          ff={showCalc}
          onClose={() => setShowCalc(null)}
          onCalculated={updateRecord}
        />
      )}
      {showView && (
        <ViewFFModal
          ff={showView}
          onClose={() => setShowView(null)}
        />
      )}
      {showPaid && (
        <MarkPaidModal
          ff={showPaid}
          onClose={() => setShowPaid(null)}
          onPaid={updateRecord}
        />
      )}
    </div>
  );
}
