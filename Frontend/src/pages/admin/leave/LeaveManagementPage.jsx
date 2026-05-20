import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../../context/AuthContext';
import { useLeaveData } from '../../../hooks/useLeaveData';
import { leaveApi } from '../../../services/leave';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';
import LeaveCard from '../../../components/LeaveCard';
import LeaveFilters from '../../../components/LeaveFilters';
import LeaveTable from '../../../components/LeaveTable';
import LeaveModal from '../../../components/LeaveModal';
import ConfirmDialog from '../../../components/ConfirmDialog';
import MyLeavePanel from '../../../components/MyLeavePanel';
import CompOffPage from '../compoff/CompOffPage';

// shape helpers
function toTableRow(r) {
  return {
    id: r.id,
    employeeName: r.employee_name,
    employeeCode: r.employee_code,
    leaveType: r.leave_type_name,
    startDate: r.start_date,
    endDate: r.end_date,
    days: r.total_days,
    status: r.status,
    reason: r.reason,
  };
}

// Page
export default function LeaveManagementPage() {
  const { user, role } = useAuth();
  const isAdmin = role === 'admin';

  const {
    requests, loading, error,
    filters, setFilter, refresh,
    approve, reject, cancel, approveCancel,
  } = useLeaveData({});

  const [selected, setSelected] = useState(null);
  // Apply Leave is now its own sub-section tab; WFH was removed from this
  // page and lives on the admin dashboard's Quick Actions panel.
  const [toast, setToast] = useState(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const [uiFilters, setUiFilters] = useState({ q: '', status: '', leaveType: '' });
  const setUi = (patch) => setUiFilters((f) => ({ ...f, ...patch }));

  const filtered = useMemo(() => {
    const q = uiFilters.q.trim().toLowerCase();
    return requests
      .filter((r) => (q ? (r.employee_name || '').toLowerCase().includes(q) : true))
      .filter((r) => (uiFilters.status ? r.status === uiFilters.status : true))
      .filter((r) => (uiFilters.leaveType ? r.leave_type_name === uiFilters.leaveType : true))
      .map(toTableRow);
  }, [requests, uiFilters]);

  const counts = useMemo(() => ({
    total:    requests.length,
    pending:  requests.filter((r) => r.status === 'pending' || r.status === 'cancel_pending').length,
    approved: requests.filter((r) => r.status === 'approved').length,
    rejected: requests.filter((r) => r.status === 'rejected').length,
  }), [requests]);

  const flash = (tone, message) => { setToast({ tone, message }); setTimeout(() => setToast(null), 2800); };

  const fullDoc = (id) => requests.find((r) => r.id === id);

  const onApprove = async (rowOrFull) => {
    const id = rowOrFull.id;
    const target = fullDoc(id) || rowOrFull;
    try {
      await (target.status === 'cancel_pending' ? approveCancel(id) : approve(id));
      flash('emerald', `${target.id} approved.`);
    } catch (e) { flash('rose', e?.data?.detail || 'Approve failed.'); }
  };
  const onReject = async (rowOrFull, reason) => {
    const id = rowOrFull.id;
    try { await reject(id, reason); flash('rose', `${id} rejected.`); }
    catch (e) { flash('rose', e?.data?.detail || 'Reject failed.'); }
  };
  const onCancel = async (full) => {
    try { await cancel(full.id); flash('amber', `Cancellation submitted for ${full.id}.`); }
    catch (e) { flash('rose', e?.data?.detail || 'Cancel failed.'); }
  };
  const onApproveCancel = async (full) => {
    try { await approveCancel(full.id); flash('emerald', `Cancellation approved for ${full.id}.`); }
    catch (e) { flash('rose', e?.data?.detail || 'Approve-cancel failed.'); }
  };

  const onApplySubmitted = () => { flash('emerald', 'Leave request submitted.'); refresh(); };

  const onReset = async () => {
    setResetting(true);
    try {
      const res = await leaveApi.adminCleanup();
      const total = (res.leave_requests_deleted || 0) + (res.audit_deleted || 0)
                  + (res.worked_on_leave_deleted || 0) + (res.notifications_deleted || 0)
                  + (res.comp_off_deleted || 0);
      flash('emerald', `Reset complete — ${res.leave_requests_deleted} requests, ${res.balances_reset} balances, ${total} total rows touched.`);
      setResetOpen(false);
      refresh();
    } catch (e) {
      flash('rose', e?.data?.detail || e?.message || 'Reset failed.');
    } finally { setResetting(false); }
  };

  const leaveTypeNames = useMemo(() => Array.from(new Set(requests.map((r) => r.leave_type_name).filter(Boolean))).sort(), [requests]);

  const selectedFull = selected ? (requests.find((r) => r.id === selected.id) || selected) : null;
  const capabilities = useMemo(() => {
    if (!selectedFull) return {};
    const isMine = selectedFull.employee_id === user?.id;
    return {
      canApprove:       (role === 'admin' || role === 'manager') && selectedFull.status === 'pending',
      canReject:        (role === 'admin' || role === 'manager') && selectedFull.status === 'pending',
      canCancel:        (isMine || role === 'admin') && (selectedFull.status === 'pending' || selectedFull.status === 'approved'),
      canApproveCancel: (role === 'admin' || role === 'manager') && selectedFull.status === 'cancel_pending',
    };
  }, [selectedFull, user, role]);

  // Sub-section toggle: 'leave' (default) | 'apply' | 'compoff'.
  // Initial value can be driven by ?section=apply so the admin Quick Actions
  // shortcut on the dashboard can deep-link straight to the Apply Leave tab.
  const location = useLocation();
  const navigate = useNavigate();
  const initialSection = (() => {
    const qs = new URLSearchParams(location.search || '');
    const s = qs.get('section');
    return (s === 'apply' || s === 'compoff') ? s : 'leave';
  })();
  const [section, setSection] = useState(initialSection);
  // If the user clicks a different tab, drop the query string so reloads
  // don't snap back to the deep-linked section.
  useEffect(() => {
    if (!location.search) return;
    const qs = new URLSearchParams(location.search);
    if (qs.get('section') && qs.get('section') !== section) {
      navigate(location.pathname, { replace: true });
    }
  }, [section]); // eslint-disable-line react-hooks/exhaustive-deps

  const SectionTabs = (
    <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
      {[
        { id: 'leave',   label: 'Leave Management' },
        { id: 'apply',   label: 'Apply Leave' },
        { id: 'compoff', label: 'Comp-Off' },
      ].map((t) => {
        const active = section === t.id;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => setSection(t.id)}
            className={'rounded-lg px-3 py-1.5 text-xs font-semibold transition ' +
              (active
                ? 'bg-[#1e3acb] text-white shadow-sm'
                : 'text-slate-500 hover:bg-slate-100')}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );

  if (section === 'compoff') {
    return (
      <div className="space-y-6">
        {SectionTabs}
        <CompOffPage />
      </div>
    );
  }

  if (section === 'apply') {
    return (
      <div className="space-y-6">
        {SectionTabs}
        <MyLeavePanel />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {SectionTabs}
      <PageHeader
        title="Leave Management"
        subtitle="Review, approve, or reject leave requests across the organization."
        right={
          <>
            {role === 'admin' && (
              <button onClick={() => setResetOpen(true)}
                className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100">
                <Icon name="warning" className="h-4 w-4" />
                Reset Leave Data
              </button>
            )}
          </>
        }
      />

      {toast && (
        <div className={
          'rounded-lg border px-3 py-2 text-sm shadow-sm ' +
          (toast.tone === 'emerald' ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
           : toast.tone === 'amber' ? 'border-amber-200 bg-amber-50 text-amber-800'
                                    : 'border-rose-200 bg-rose-50 text-rose-800')
        }>{toast.message}</div>
      )}

      {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <LeaveCard label="Total Requests"    value={counts.total}    tone="slate" />
        <LeaveCard label="Pending Approvals" value={counts.pending}  tone="amber" />
        <LeaveCard label="Approved"          value={counts.approved} tone="emerald" />
        <LeaveCard label="Rejected"          value={counts.rejected} tone="rose" />
      </div>

      <LeaveFilters filters={uiFilters} setFilter={setUi} leaveTypes={leaveTypeNames} />

      <LeaveTable
        rows={filtered}
        loading={loading}
        onRowClick={(r) => setSelected(requests.find((x) => x.id === r.id))}
        onApprove={(r) => onApprove(r)}
        onReject={(r) => onReject(r, '')}
      />

      <LeaveModal
        open={!!selected}
        leave={selectedFull}
        capabilities={capabilities}
        onClose={() => setSelected(null)}
        onApprove={onApprove}
        onReject={onReject}
        onCancel={onCancel}
        onApproveCancel={onApproveCancel}
      />

      <ConfirmDialog
        open={resetOpen}
        title="Reset all leave data?"
        message={'This will permanently delete every leave request, audit log entry, comp-off credit, and reset all balances back to their opening values. This cannot be undone.'}
        confirmLabel="Yes, wipe it"
        tone="danger"
        busy={resetting}
        onCancel={() => setResetOpen(false)}
        onConfirm={onReset}
      />
    </div>
  );
}
