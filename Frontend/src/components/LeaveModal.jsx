import { useEffect, useMemo, useState } from 'react';
import Icon from './Icon';
import { leaveApi } from '../services/leave';

function StatusPill({ status }) {
  const tone = {
    pending:        { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-500',   label: 'Pending' },
    approved:       { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500', label: 'Approved (Reserved)' },
    rejected:       { bg: 'bg-rose-50',    text: 'text-rose-700',    dot: 'bg-rose-500',    label: 'Rejected' },
    cancel_pending: { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-500',   label: 'Cancellation Pending' },
    cancelled:      { bg: 'bg-slate-100',  text: 'text-slate-600',   dot: 'bg-slate-400',   label: 'Cancelled' },
    consumed:       { bg: 'bg-blue-50',    text: 'text-blue-700',    dot: 'bg-blue-500',    label: 'Consumed' },
  }[status] || { bg: 'bg-slate-100', text: 'text-slate-600', dot: 'bg-slate-400', label: status };
  return (
    <span className={'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ' + tone.bg + ' ' + tone.text}>
      <span className={'h-1.5 w-1.5 rounded-full ' + tone.dot} />
      {tone.label}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function Field({ label, children }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <div className="mt-1 text-sm text-slate-800">{children}</div>
    </div>
  );
}

function ChainStep({ label, who, when, status }) {
  // status: 'done' | 'current' | 'upcoming'
  const tone = {
    done:     { ring: 'ring-emerald-500', bg: 'bg-emerald-500', text: 'text-emerald-700' },
    current:  { ring: 'ring-amber-500',   bg: 'bg-amber-500',   text: 'text-amber-700' },
    upcoming: { ring: 'ring-slate-300',   bg: 'bg-slate-200',   text: 'text-slate-500' },
  }[status];
  return (
    <div className="flex items-start gap-3">
      <div className={'mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full ring-2 ring-offset-1 ' + tone.ring + ' ' + tone.bg} />
      <div>
        <p className={'text-xs font-semibold ' + tone.text}>{label}</p>
        <p className="text-[11px] text-slate-500">
          {when ? `${who || ''} · ${fmtDateTime(when)}` : (status === 'current' ? 'Awaiting decision' : 'Pending')}
        </p>
      </div>
    </div>
  );
}

function ApprovalChain({ leave, detail }) {
  // Manager step status
  const mgrDone = !!leave.manager_approval?.at;
  const hrDone  = !!leave.hr_approval?.at;
  const isCanceled = leave.status === 'cancelled';
  const isRejected = leave.status === 'rejected';
  const cancelChain = leave.status === 'cancel_pending';

  const mgrStatus = mgrDone ? 'done' : (leave.next_approver_role === 'manager' ? 'current' : (hrDone ? 'done' : 'upcoming'));
  const hrStatus  = hrDone ? 'done' : (leave.next_approver_role === 'hr' ? 'current' : 'upcoming');

  return (
    <div className="space-y-3">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Approval chain</p>
      <ChainStep
        label="Manager approval"
        who={leave.manager_approval?.by_name}
        when={leave.manager_approval?.at}
        status={mgrStatus}
      />
      <ChainStep
        label="HR approval"
        who={leave.hr_approval?.by_name}
        when={leave.hr_approval?.at}
        status={hrStatus}
      />
      {isRejected && <p className="rounded bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700">Request was rejected. {leave.rejection_reason ? '— ' + leave.rejection_reason : ''}</p>}
      {cancelChain && <p className="rounded bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-700">Cancellation requested · awaiting {leave.next_approver_role} approval</p>}
      {isCanceled && <p className="rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">Request fully cancelled.</p>}
    </div>
  );
}

function AuditList({ entries }) {
  if (!entries?.length) return <p className="text-[11px] text-slate-400">No audit entries yet.</p>;
  return (
    <ol className="space-y-2 border-l border-slate-200 pl-3">
      {entries.map((a) => (
        <li key={a.id} className="text-[11px]">
          <span className="font-semibold text-slate-700">{a.action.replace(/_/g, ' ')}</span>
          {' · '}
          <span className="text-slate-500">{a.actor_name || 'system'}</span>
          {a.from_status && a.to_status && <span className="text-slate-400">  ({a.from_status} → {a.to_status})</span>}
          <p className="text-[10px] uppercase tracking-wider text-slate-400">{fmtDateTime(a.created_at)}</p>
          {a.note && <p className="text-[11px] italic text-slate-500">"{a.note}"</p>}
        </li>
      ))}
    </ol>
  );
}

/**
 * Detail modal with approval chain, audit, and role-aware actions.
 *
 * Props:
 *   open, leave, onClose
 *   capabilities?: { canApprove, canReject, canCancel, canApproveCancel }
 *   onApprove, onReject, onCancel, onApproveCancel — async callbacks; the dialog disables buttons while running
 */
export default function LeaveModal({
  open, leave, onClose,
  capabilities = {},
  onApprove, onReject, onCancel, onApproveCancel,
}) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(null); // 'approve' | 'reject' | 'cancel' | 'approve_cancel'
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    setRejectReason(''); setShowRejectInput(false);
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Fetch detail (with audit) once a leave is selected.
  useEffect(() => {
    if (!open || !leave?.id) { setDetail(null); return; }
    let cancelled = false;
    leaveApi.one(leave.id).then((d) => { if (!cancelled) setDetail(d); }).catch(() => {});
    return () => { cancelled = true; };
  }, [open, leave?.id]);

  const view = detail || leave;
  if (!open || !view) return null;

  const handle = async (key, fn) => {
    try { setBusy(key); await fn(); onClose?.(); }
    catch (e) { alert(e?.data?.detail || e?.message || 'Action failed'); }
    finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-6 py-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Leave Request</h3>
            <p className="mt-0.5 text-xs text-slate-500">Request ID: {view.id}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill status={view.status} />
            <button onClick={onClose} aria-label="Close" className="rounded-md p-1 text-slate-500 transition hover:bg-slate-100">
              <Icon name="reject" className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 px-6 py-5 md:grid-cols-2">
          <div className="space-y-5">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-sm font-bold text-white">
                {(view.employee_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
              </div>
              <div>
                <p className="font-semibold text-slate-900">{view.employee_name}</p>
                {view.employee_code && <p className="text-xs text-slate-500">{view.employee_code}</p>}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Leave Type">{view.leave_type_name}</Field>
              <Field label="Days">{view.total_days}</Field>
              <Field label="Start Date">{fmtDate(view.start_date)}</Field>
              <Field label="End Date">{fmtDate(view.end_date)}</Field>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Reason</p>
              <p className="mt-1 rounded-lg bg-slate-50 px-3 py-2 text-sm leading-relaxed text-slate-700">
                {view.reason || 'No reason provided.'}
              </p>
            </div>
          </div>

          <div className="space-y-5">
            <ApprovalChain leave={view} detail={detail} />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Audit trail</p>
              <div className="mt-2 max-h-44 overflow-y-auto"><AuditList entries={detail?.audit} /></div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 bg-slate-50/40 px-6 py-3">
          {showRejectInput ? (
            <div className="flex items-center gap-2">
              <input
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Reason for rejection (optional)"
                className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
              <button
                onClick={() => setShowRejectInput(false)}
                disabled={!!busy}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                onClick={() => handle('reject', () => onReject(view, rejectReason))}
                disabled={!!busy}
                className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-60"
              >
                {busy === 'reject' ? 'Rejecting…' : 'Confirm reject'}
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">Close</button>

              {capabilities.canCancel && view.status === 'pending' && (
                <button
                  disabled={!!busy}
                  onClick={() => handle('cancel', () => onCancel(view))}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  {busy === 'cancel' ? 'Cancelling…' : 'Cancel request'}
                </button>
              )}
              {capabilities.canCancel && view.status === 'approved' && (
                <button
                  disabled={!!busy}
                  onClick={() => handle('cancel', () => onCancel(view))}
                  className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                >
                  {busy === 'cancel' ? 'Submitting…' : 'Request cancellation'}
                </button>
              )}

              {capabilities.canReject && view.status === 'pending' && (
                <button
                  disabled={!!busy}
                  onClick={() => setShowRejectInput(true)}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                >
                  Reject
                </button>
              )}

              {capabilities.canApprove && view.status === 'pending' && (
                <button
                  disabled={!!busy}
                  onClick={() => handle('approve', () => onApprove(view))}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-60"
                >
                  {busy === 'approve' ? 'Approving…' : 'Approve'}
                </button>
              )}
              {capabilities.canApproveCancel && view.status === 'cancel_pending' && (
                <button
                  disabled={!!busy}
                  onClick={() => handle('approve_cancel', () => onApproveCancel(view))}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-60"
                >
                  {busy === 'approve_cancel' ? 'Approving…' : 'Approve cancellation'}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
