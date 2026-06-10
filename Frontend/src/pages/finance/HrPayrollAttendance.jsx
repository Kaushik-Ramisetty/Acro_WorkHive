/**
 * HR Payroll Attendance Dashboard
 *
 * Data source: monthly_attendance_summary (joined with employees table via API).
 * HR responsibility: review attendance, review leave/LOP, freeze attendance.
 * HR must NOT see: salary, CTC, basic, HRA, PF, ESI, PT, TDS, gross, net.
 *
 * Flow:
 *   HR selects month/year → fetches monthly_attendance_summary →
 *   reviews each employee's attendance → validates → freezes →
 *   payroll generation is unblocked for Finance
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { usePayrollPeriod } from '../../context/PayrollPeriodContext';
import financeApi from '../../services/financeApi';

const MONTHS = [
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' },
];


function StatusBadge({ status, map }) {
  const cfg = map[status] || { bg: 'bg-slate-100 text-slate-500', label: status ?? '—' };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${cfg.bg}`}>
      {cfg.label}
    </span>
  );
}

const ATTENDANCE_STATUS_MAP = {
  pending:   { bg: 'bg-amber-100 text-amber-700',   label: 'Pending' },
  submitted: { bg: 'bg-blue-100 text-blue-700',     label: 'Submitted' },
  validated: { bg: 'bg-brand-100 text-brand-700',   label: 'Validated' },
  finalized: { bg: 'bg-emerald-100 text-emerald-700', label: 'Finalized' },
  issues:    { bg: 'bg-rose-100 text-rose-700',     label: 'Issues' },
  missing:   { bg: 'bg-rose-100 text-rose-700',     label: 'Missing' },
};

const TIMESHEET_STATUS_MAP = {
  pending:  { bg: 'bg-amber-100 text-amber-700',   label: 'Pending' },
  submitted:{ bg: 'bg-blue-100 text-blue-700',     label: 'Submitted' },
  approved: { bg: 'bg-emerald-100 text-emerald-700', label: 'Approved' },
  missing:  { bg: 'bg-rose-100 text-rose-700',     label: 'Missing' },
};

const VALIDATION_STATUS_MAP = {
  pending: { bg: 'bg-amber-100 text-amber-700',   label: 'Pending' },
  passed:  { bg: 'bg-emerald-100 text-emerald-700', label: 'Passed' },
  failed:  { bg: 'bg-rose-100 text-rose-700',     label: 'Failed' },
  missing: { bg: 'bg-rose-100 text-rose-700',     label: 'Missing' },
};

function SummaryChip({ label, value, accent }) {
  return (
    <div className={`rounded-lg border px-4 py-2.5 text-sm shadow-sm ${accent}`}>
      <span className="opacity-70">{label}: </span>
      <span className="font-bold">{value}</span>
    </div>
  );
}

export default function HrPayrollAttendance() {
  const navigate = useNavigate();
  const { role } = useAuth();

  const [selectedMonth, setSelectedMonth] = useState(null);
  const [selectedYear,  setSelectedYear]  = useState(null);
  const [availableMonths, setAvailableMonths] = useState([]);
  const [initLoading,  setInitLoading]    = useState(true);

  const [summary,       setSummary]       = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // 'validate' | 'freeze' | 'reset'
  const [notification,  setNotification]  = useState(null); // {type, msg}
  const [search,        setSearch]        = useState('');
  const [editLop,       setEditLop]       = useState(null);  // { row } or null
  const [editLopValue,  setEditLopValue]  = useState('');
  const [savingLop,     setSavingLop]     = useState(false);

  const load = useCallback(() => {
    if (!selectedMonth || !selectedYear) return;
    setLoading(true);
    setNotification(null);
    financeApi.getPayrollAttendanceSummary(selectedMonth, selectedYear)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [selectedMonth, selectedYear]);

  useEffect(() => { load(); }, [load]);

  // On mount: auto-detect the current open payroll month from actual data
  useEffect(() => {
    financeApi.getOpenPayrollMonth()
      .then(data => {
        setSelectedMonth(data.month);
        setSelectedYear(data.year);
        setAvailableMonths(data.available_months || []);
      })
      .catch(() => {
        const n = new Date();
        setSelectedMonth(n.getMonth() + 1);
        setSelectedYear(n.getFullYear());
      })
      .finally(() => setInitLoading(false));
  }, []);

  // ── Computed values ───────────────────────────────────────────────────────
  const rows         = summary?.rows ?? [];
  const totalEmp     = summary?.total_employees ?? 0;
  const withSummary  = summary?.with_summary ?? 0;
  const missingCount = summary?.missing_summary ?? 0;
  const frozenCount  = summary?.frozen_count ?? 0;
  const readyCount   = summary?.ready_count ?? 0;
  const issuesCount  = (summary?.issues_count ?? 0) + missingCount;
  const allFrozen    = summary?.all_frozen ?? false;
  const overall      = summary?.attendance_overall ?? 'pending';
  const monthLabel   = summary?.month_label
    ?? (selectedMonth && selectedYear
        ? (MONTHS.find(m => m.value === selectedMonth)?.label + ' ' + selectedYear)
        : '…');

  const canFreeze = overall === 'ready' && !allFrozen;
  const hasMismatch = rows.some(r =>
    r.total_working_days != null && (
      (r.present_days ?? 0) > r.total_working_days ||
      (r.leave_days ?? 0) + (r.lop_days ?? 0) > r.total_working_days
    )
  );

  const filteredRows = rows.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (r.employee_code || '').toLowerCase().includes(q) ||
      (r.employee_name || '').toLowerCase().includes(q) ||
      (r.department || '').toLowerCase().includes(q) ||
      (r.designation || '').toLowerCase().includes(q)
    );
  });

  // ── Action handlers ───────────────────────────────────────────────────────
  const handleValidate = async () => {
    setActionLoading('validate');
    setNotification(null);
    try {
      const res = await financeApi.validatePayrollAttendance(selectedMonth, selectedYear);
      load();
      const msg = res?.can_freeze
        ? `Validation passed — all ${res.validation_passed} employees ready.`
        : `Validation done — ${res.validation_failed || 0} issue(s) found. Fix before freezing.`;
      setNotification({ type: res?.can_freeze ? 'success' : 'warning', msg });
    } catch (e) {
      setNotification({ type: 'error', msg: e?.data?.detail || 'Validation failed.' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleFreeze = async () => {
    setActionLoading('freeze');
    setNotification(null);
    try {
      await financeApi.freezePayrollAttendance(selectedMonth, selectedYear);
      load();
      setNotification({ type: 'success', msg: `Attendance frozen for ${monthLabel}. Finance team has been notified. Payroll generation is now unlocked.` });
    } catch (e) {
      setNotification({ type: 'error', msg: e?.data?.detail || 'Freeze failed.' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleResetFreeze = async () => {
    setActionLoading('reset');
    setNotification(null);
    try {
      await financeApi.resetPayrollAttendanceFreeze(selectedMonth, selectedYear);
      load();
      setNotification({ type: 'warning', msg: '[DEV] Freeze reset — validate and freeze again to re-test.' });
    } catch (e) {
      setNotification({ type: 'error', msg: e?.data?.detail || 'Reset failed.' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSaveLop = async () => {
    if (!editLop) return;
    const parsed = parseInt(editLopValue, 10);
    if (isNaN(parsed) || parsed < 0 || parsed > (editLop.row.total_working_days ?? 31)) {
      setNotification({ type: 'error', msg: `LOP must be between 0 and ${editLop.row.total_working_days ?? 31}.` });
      return;
    }
    setSavingLop(true);
    setNotification(null);
    try {
      await financeApi.manualAttendanceSummary({
        employee_id:              editLop.row.employee_id,
        month:                    selectedMonth,
        year:                     selectedYear,
        total_working_days:       editLop.row.total_working_days ?? 0,
        present_days:             editLop.row.present_days ?? 0,
        leave_days:               editLop.row.leave_days ?? 0,
        payable_days:             Math.max(0, (editLop.row.total_working_days ?? 0) - parsed),
        lop_days:                 parsed,
        approved_timesheet_hours: editLop.row.approved_timesheet_hours ?? 0,
        timesheet_status:         editLop.row.timesheet_status ?? 'pending',
      });
      setEditLop(null);
      load();
      setNotification({ type: 'success', msg: `LOP updated to ${parsed} day(s) for ${editLop.row.employee_name}. Re-validate before freezing.` });
    } catch (e) {
      setNotification({ type: 'error', msg: e?.data?.detail || 'Failed to save LOP.' });
    } finally {
      setSavingLop(false);
    }
  };

  const r = (role || '').toLowerCase();
  const isHrOrAdmin = r === 'admin' || r === 'hr';

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <button
        onClick={() => navigate(r === 'admin' ? '/admin-dashboard/payroll' : '/employee-dashboard/finance-payroll')}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to Payroll Dashboard
      </button>

      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-800">
            HR Payroll Input Dashboard — {monthLabel}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Review attendance from <span className="font-medium">monthly_attendance_summary</span> — validate and freeze before payroll generation
          </p>
        </div>

        {/* Month / Year selector — populated from actual data in monthly_attendance_summary */}
        {availableMonths.length > 0 && selectedMonth && selectedYear && (
          <select
            value={`${selectedYear}-${selectedMonth}`}
            onChange={e => {
              const [y, m] = e.target.value.split('-').map(Number);
              setSelectedYear(y);
              setSelectedMonth(m);
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          >
            {availableMonths.map(opt => (
              <option key={`${opt.year}-${opt.month}`} value={`${opt.year}-${opt.month}`}>
                {opt.month_label}{opt.is_fully_frozen ? ' · Frozen' : ''}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Initial payroll period detection */}
      {initLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
          <div className="h-5 w-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          Detecting payroll period…
        </div>
      )}

      {!initLoading && (
        <>
      {/* Overall status banner */}
      <div className={`flex items-center justify-between rounded-xl border px-5 py-3 ${
        allFrozen   ? 'bg-emerald-50 border-emerald-200'
        : overall === 'ready'   ? 'bg-blue-50 border-blue-200'
        : overall === 'partial' ? 'bg-amber-50 border-amber-200'
        :                         'bg-slate-50 border-slate-200'
      }`}>
        <div>
          <p className={`text-sm font-semibold ${
            allFrozen ? 'text-emerald-800'
            : overall === 'ready'   ? 'text-blue-800'
            : overall === 'partial' ? 'text-amber-800'
            :                         'text-slate-600'
          }`}>
            {allFrozen           ? `🔒 Attendance Frozen — ${monthLabel}`
             : overall === 'ready'   ? `✓ Ready to Freeze — ${monthLabel}`
             : overall === 'partial' ? `⚠ Partial — Validate Required — ${monthLabel}`
             :                         `No Attendance Summary — ${monthLabel}`}
          </p>
          {allFrozen && (
            <p className="text-xs text-emerald-700 mt-0.5">
              Payroll generation is unlocked. Finance team has been notified.
            </p>
          )}
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${
          allFrozen           ? 'bg-emerald-200 text-emerald-800'
          : overall === 'ready'   ? 'bg-blue-200 text-blue-800'
          : overall === 'partial' ? 'bg-amber-200 text-amber-800'
          :                         'bg-slate-200 text-slate-600'
        }`}>
          {allFrozen ? 'Frozen' : overall}
        </span>
      </div>

      {/* Summary chips */}
      <div className="flex flex-wrap gap-3">
        <SummaryChip label="Total Employees" value={totalEmp} accent="bg-white border-slate-200 text-slate-700" />
        <SummaryChip label="With Summary" value={withSummary} accent="bg-white border-slate-200 text-slate-700" />
        <SummaryChip label="Ready" value={readyCount} accent="bg-blue-50 border-blue-200 text-blue-800" />
        <SummaryChip label="Frozen" value={frozenCount} accent="bg-emerald-50 border-emerald-200 text-emerald-800" />
        {missingCount > 0 && (
          <SummaryChip label="Missing Summary" value={missingCount} accent="bg-rose-50 border-rose-200 text-rose-800" />
        )}
        {issuesCount > 0 && (
          <SummaryChip label="Issues" value={issuesCount} accent="bg-rose-50 border-rose-200 text-rose-800" />
        )}
      </div>

      {/* Validation rules reference */}
      {!allFrozen && withSummary > 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-3 text-xs text-slate-500 space-y-0.5">
          <p className="font-semibold text-slate-600 mb-1">Validation checks before freeze:</p>
          <p>V1 · Every active employee must have an attendance summary row</p>
          <p>V2 · No negative days (present/leave/lop/payable)</p>
          <p>V3 · present + leave + lop must not exceed total_working_days</p>
          <p>V4 · total_working_days must be greater than zero</p>
          <p>V5 · payable_days must not exceed total_working_days</p>
          <p>V6 · Timesheet pending = warning only (non-blocking)</p>
        </div>
      )}

      {/* Notification */}
      {notification && (
        <div className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${
          notification.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
          : notification.type === 'warning' ? 'bg-amber-50 border-amber-200 text-amber-800'
          : 'bg-rose-50 border-rose-200 text-rose-800'
        }`}>
          <span className="flex-shrink-0 mt-0.5 font-bold">
            {notification.type === 'success' ? '✓' : '⚠'}
          </span>
          <span>{notification.msg}</span>
        </div>
      )}

      {/* Loading spinner */}
      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
          <div className="h-5 w-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          Loading attendance data…
        </div>
      )}

      {/* Main content */}
      {!loading && (
        <>
          {/* Missing summary warning */}
          {withSummary === 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
              <p className="text-base font-semibold text-amber-800">Attendance summary missing</p>
              <p className="text-sm text-amber-700 mt-1">
                No attendance records found in <code className="font-mono">monthly_attendance_summary</code> for {monthLabel}.
              </p>
              <p className="text-xs text-amber-600 mt-2">
                Attendance data must be populated by the Attendance/Timesheet module before HR can review and freeze.
              </p>
            </div>
          )}

          {/* Employees with missing summary */}
          {withSummary > 0 && missingCount > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-800">
              <strong>{missingCount} employee{missingCount > 1 ? 's' : ''}</strong> missing attendance summary for {monthLabel}.
              Freeze is blocked until all employees have a summary row.
            </div>
          )}

          {/* Attendance table */}
          {rows.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-soft">
              {/* Table header with search */}
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
                <p className="text-sm font-semibold text-slate-700">
                  Payroll Input Details — {monthLabel}
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    Source: monthly_attendance_summary
                  </span>
                </p>
                <input
                  type="text"
                  placeholder="Search by name, code, dept…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-brand-400"
                />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      {/* Employee Info */}
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Emp Code</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Employee Name</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Department</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Designation</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Date of Joining</th>
                      {/* Attendance Info */}
                      <th className="whitespace-nowrap px-3 py-2.5 text-center font-semibold text-slate-500">Working Days</th>
                      <th className="whitespace-nowrap px-3 py-2.5 text-center font-semibold text-slate-500">Present Days</th>
                      <th className="whitespace-nowrap px-3 py-2.5 text-center font-semibold text-slate-500">Leave Days</th>
                      <th className="whitespace-nowrap px-3 py-2.5 text-center font-semibold text-slate-500">
                        LOP Days {isHrOrAdmin && !allFrozen && <span className="text-[9px] text-brand-500 font-normal ml-0.5">✎ editable</span>}
                      </th>
                      <th className="whitespace-nowrap px-3 py-2.5 text-center font-semibold text-slate-500">Payable Days</th>
                      {/* Status Info */}
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Att. Status</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Timesheet</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Validation</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Ready</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold text-slate-500">Frozen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredRows.map(row => {
                      const mismatch =
                        row.total_working_days != null && (
                          (row.present_days ?? 0) > row.total_working_days ||
                          (row.leave_days ?? 0) + (row.lop_days ?? 0) > row.total_working_days
                        );
                      const noSummary = !row.has_summary;

                      return (
                        <tr
                          key={row.employee_id}
                          className={`transition ${
                            noSummary ? 'bg-rose-50'
                            : mismatch ? 'bg-amber-50'
                            : row.is_frozen ? 'bg-emerald-50'
                            : 'hover:bg-slate-50'
                          }`}
                        >
                          {/* Employee info */}
                          <td className="whitespace-nowrap px-3 py-2.5 font-mono text-slate-600">
                            {row.employee_code ?? '—'}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2.5 font-medium text-slate-800">
                            {row.employee_name}
                            {noSummary && (
                              <span className="ml-1.5 text-[10px] text-rose-600 font-semibold">⚠ no summary</span>
                            )}
                            {mismatch && (
                              <span className="ml-1.5 text-[10px] text-amber-600">⚠ day mismatch</span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">
                            {row.department ?? '—'}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">
                            {row.designation ?? '—'}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2.5 font-mono text-slate-500">
                            {row.date_of_joining ?? '—'}
                          </td>
                          {/* Attendance counts */}
                          <td className="px-3 py-2.5 text-center font-mono text-slate-700">
                            {row.total_working_days ?? '—'}
                          </td>
                          <td className="px-3 py-2.5 text-center font-mono text-slate-700">
                            {row.present_days ?? '—'}
                          </td>
                          <td className="px-3 py-2.5 text-center font-mono text-slate-700">
                            {row.leave_days ?? '—'}
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            {isHrOrAdmin && !row.is_frozen && editLop?.row.employee_id === row.employee_id ? (
                              <span className="inline-flex items-center gap-1">
                                <input
                                  type="number"
                                  min={0}
                                  max={row.total_working_days ?? 31}
                                  value={editLopValue}
                                  onChange={e => setEditLopValue(e.target.value)}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') handleSaveLop();
                                    if (e.key === 'Escape') setEditLop(null);
                                  }}
                                  autoFocus
                                  className="w-14 rounded border border-brand-400 px-1 py-0.5 text-xs font-mono text-center focus:outline-none focus:ring-1 focus:ring-brand-500"
                                />
                                <button
                                  onClick={handleSaveLop}
                                  disabled={savingLop}
                                  className="rounded bg-brand-600 px-1.5 py-0.5 text-[10px] font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
                                >
                                  {savingLop ? '…' : '✓'}
                                </button>
                                <button
                                  onClick={() => setEditLop(null)}
                                  className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-300"
                                >
                                  ✕
                                </button>
                              </span>
                            ) : (
                              <span
                                className={`font-mono font-semibold ${
                                  (row.lop_days ?? 0) > 0 ? 'text-rose-600' : 'text-slate-700'
                                } ${isHrOrAdmin && !row.is_frozen ? 'cursor-pointer hover:underline hover:text-brand-600' : ''}`}
                                title={isHrOrAdmin && !row.is_frozen ? 'Click to edit LOP days' : undefined}
                                onClick={() => {
                                  if (!isHrOrAdmin || row.is_frozen) return;
                                  setEditLop({ row });
                                  setEditLopValue(String(row.lop_days ?? 0));
                                }}
                              >
                                {row.lop_days ?? '—'}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-center font-mono font-semibold text-slate-800">
                            {row.payable_days ?? '—'}
                          </td>
                          {/* Status badges */}
                          <td className="px-3 py-2.5">
                            <StatusBadge status={row.attendance_status} map={ATTENDANCE_STATUS_MAP} />
                          </td>
                          <td className="px-3 py-2.5">
                            <StatusBadge status={row.timesheet_status} map={TIMESHEET_STATUS_MAP} />
                          </td>
                          <td className="px-3 py-2.5">
                            <StatusBadge status={row.validation_status} map={VALIDATION_STATUS_MAP} />
                            {row.validation_notes && (
                              <p className="mt-0.5 max-w-[180px] text-[10px] text-rose-600">
                                {row.validation_notes}
                              </p>
                            )}
                          </td>
                          <td className="px-3 py-2.5">
                            {row.is_ready_for_payroll
                              ? <span className="inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">Yes</span>
                              : <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">No</span>
                            }
                          </td>
                          <td className="px-3 py-2.5">
                            {row.is_frozen
                              ? <span className="inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">🔒 Frozen</span>
                              : <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-400">Open</span>
                            }
                          </td>
                        </tr>
                      );
                    })}

                    {/* Totals row */}
                    {filteredRows.length > 1 && (
                      <tr className="border-t-2 border-slate-300 bg-slate-100 font-semibold">
                        <td className="px-3 py-2.5" colSpan={5}>
                          <span className="text-slate-600">Totals ({filteredRows.length} employees)</span>
                        </td>
                        <td className="px-3 py-2.5 text-center font-mono text-slate-800">
                          {filteredRows.reduce((s, r) => s + (r.total_working_days ?? 0), 0)}
                        </td>
                        <td className="px-3 py-2.5 text-center font-mono text-slate-800">
                          {filteredRows.reduce((s, r) => s + (r.present_days ?? 0), 0)}
                        </td>
                        <td className="px-3 py-2.5 text-center font-mono text-slate-800">
                          {filteredRows.reduce((s, r) => s + (r.leave_days ?? 0), 0)}
                        </td>
                        <td className={`px-3 py-2.5 text-center font-mono font-bold ${
                          filteredRows.reduce((s, r) => s + (r.lop_days ?? 0), 0) > 0 ? 'text-rose-600' : 'text-slate-800'
                        }`}>
                          {filteredRows.reduce((s, r) => s + (r.lop_days ?? 0), 0)}
                        </td>
                        <td className="px-3 py-2.5 text-center font-mono text-slate-800">
                          {filteredRows.reduce((s, r) => s + (r.payable_days ?? 0), 0).toFixed(1)}
                        </td>
                        <td className="px-3 py-2.5" />
                        <td className="px-3 py-2.5" />
                        <td className="px-3 py-2.5 text-slate-600 text-xs">
                          {filteredRows.filter(r => r.validation_status === 'passed').length}
                          {' / '}
                          {filteredRows.length} passed
                        </td>
                        <td className="px-3 py-2.5 text-slate-600 text-xs">
                          {filteredRows.filter(r => r.is_ready_for_payroll).length} / {filteredRows.length}
                        </td>
                        <td className="px-3 py-2.5 text-slate-600 text-xs">
                          {filteredRows.filter(r => r.is_frozen).length} / {filteredRows.length}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Action buttons — HR only */}
          {isHrOrAdmin && withSummary > 0 && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-soft">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mr-2">
                HR Actions
              </p>

              {!allFrozen && (
                <>
                  <button
                    onClick={handleValidate}
                    disabled={!!actionLoading}
                    className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
                  >
                    {actionLoading === 'validate' ? 'Validating…' : 'Validate Attendance'}
                  </button>

                  <button
                    onClick={handleFreeze}
                    disabled={!!actionLoading || !canFreeze || hasMismatch || missingCount > 0}
                    title={
                      missingCount > 0
                        ? `${missingCount} employee(s) missing summary — fix before freezing`
                        : hasMismatch
                        ? 'Fix day-count mismatches before freezing'
                        : !canFreeze
                        ? 'Run Validate Attendance first — all employees must pass'
                        : ''
                    }
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 transition disabled:opacity-50"
                  >
                    {actionLoading === 'freeze' ? 'Freezing…' : '🔒 Freeze Attendance'}
                  </button>

                  {(!canFreeze || hasMismatch || missingCount > 0) && (
                    <span className="text-xs text-amber-700">
                      {missingCount > 0
                        ? `${missingCount} summary row(s) missing`
                        : hasMismatch
                        ? 'Day-count mismatch detected'
                        : 'Validate first to unlock freeze'}
                    </span>
                  )}
                </>
              )}

              {allFrozen && (
                <>
                  <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-700">
                    <span>🔒</span>
                    <span>Attendance frozen — payroll generation unlocked — Finance notified</span>
                  </span>
                  {/* DEV ONLY reset */}
                  <button
                    onClick={handleResetFreeze}
                    disabled={!!actionLoading}
                    className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 transition disabled:opacity-50"
                    title="DEV ONLY — resets freeze for re-testing"
                  >
                    {actionLoading === 'reset' ? 'Resetting…' : '🔧 Reset Freeze [DEV]'}
                  </button>
                </>
              )}
            </div>
          )}

          {/* Freeze flow explanation */}
          {!allFrozen && withSummary > 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 text-xs text-slate-500">
              <p className="font-semibold text-slate-600 mb-2">Freeze Attendance Flow</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>Attendance data loaded from <code className="font-mono">monthly_attendance_summary</code></li>
                <li>HR reviews attendance, leave impact, and LOP for each employee</li>
                <li>HR clicks <strong>Validate Attendance</strong> — system checks all 6 rules</li>
                <li>HR clicks <strong>Freeze Attendance</strong> — <code className="font-mono">is_frozen = true</code>, <code className="font-mono">finalized_at</code> set</li>
                <li>Finance team is notified — payroll generation is now unblocked</li>
                <li>Payroll uses: <code className="font-mono">employees</code> + <code className="font-mono">salary_structures.annual_ctc</code> + frozen <code className="font-mono">monthly_attendance_summary</code></li>
              </ol>
            </div>
          )}
        </>
      )}
        </>
      )}
    </div>
  );
}
