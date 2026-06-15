/**
 * MidCycleReviewDrawer — Phase 2 mid-cycle review detail panel.
 *
 * Uses the shared Modal component (React Portal, z-[9999], centered overlay)
 * identical to GoalDetailDrawer so all three Phase 1/2/3 drawers behave the same.
 *
 * Props:
 *   review      - MidCycleReviewOut object (from API)
 *   assignment  - GoalAssignment the review belongs to (for KRA/KPI tree)
 *   viewerRole  - 'employee' | 'manager' | 'hr'
 *   onClose     - () => void
 *   onChanged   - () => void  (refresh parent list after action)
 */
import { useState, useMemo, useEffect } from 'react';
import Modal from '../../../components/Modal';
import { pmsApi, MCR_STATUS, MCR_STATUS_LABEL, MCR_STATUS_TONE, isAutoLocked } from '../../../services/pms';

// ── Helpers ───────────────────────────────────────────────────────────────────

const STEPS = [
  { id: MCR_STATUS.DRAFT,          label: 'Draft' },
  { id: MCR_STATUS.IN_PROGRESS,    label: 'In Progress' },
  { id: MCR_STATUS.SUBMITTED,      label: 'Submitted' },
  { id: MCR_STATUS.MGR_REVIEWED,   label: 'Mgr Reviewed' },
  { id: MCR_STATUS.MGR_APPROVED,   label: 'Mgr Approved' },
  { id: MCR_STATUS.HR_REVIEWED,    label: 'HR Reviewed' },
  { id: MCR_STATUS.LOCKED,         label: 'Locked' },
];

const stepIndex = (s) => STEPS.findIndex((x) => x.id === s);

function StatusPill({ status }) {
  const tone = MCR_STATUS_TONE[status] || { bg: '#F1F5F9', fg: '#475569' };
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
      style={{ backgroundColor: tone.bg, color: tone.fg }}>
      {MCR_STATUS_LABEL[status] || status}
    </span>
  );
}

/**
 * ProgressBar — renders a fill bar.
 * `value` is already the scaled display percentage (0–100).
 */
function ProgressBar({ value }) {
  const pct = Math.min(100, Math.max(0, Number(value) || 0));
  const color = pct >= 80 ? '#10b981' : pct >= 40 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="w-8 text-right text-[11px] font-bold" style={{ color }}>{pct.toFixed(0)}%</span>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function MidCycleReviewDrawer({ review: initialReview, assignment, viewerRole, onClose, onChanged }) {
  const [review, setReview]         = useState(initialReview);
  const [busy, setBusy]             = useState(false);
  const [error, setError]           = useState('');
  const [comment, setComment]       = useState('');
  const [editingProgress, setEditingProgress] = useState(false);

  // Local KPI progress edits (keyed by assigned_kpi_id).
  const [progressEdits, setProgressEdits] = useState(() => {
    const map = {};
    (initialReview.kpi_progress || []).forEach((p) => {
      map[p.assigned_kpi_id] = {
        current_value: p.current_value || '',
        progress_percent: p.progress_percent || 0,
        employee_notes: p.employee_notes || '',
      };
    });
    return map;
  });
  const [employeeComments, setEmployeeComments] = useState(initialReview.employee_comments || '');

  // Manager editing — notes AND progress value overrides.
  // Each entry: { manager_notes, current_value, progress_percent }
  // Keyed by assigned_kpi_id (number, stored as string key in the object).
  const [editingManagerNotes, setEditingManagerNotes] = useState(false);
  const [managerNotesEdits, setManagerNotesEdits] = useState(() => {
    const map = {};
    (initialReview.kpi_progress || []).forEach((p) => {
      map[p.assigned_kpi_id] = {
        manager_notes:    p.manager_notes    || '',
        current_value:    p.current_value    || '',
        progress_percent: p.progress_percent ?? 0,
      };
    });
    return map;
  });
  const [managerCommentEdit, setManagerCommentEdit] = useState(initialReview.manager_comments || '');

  // Keep manager edit state in sync when review updates (e.g. after a save).
  useEffect(() => {
    if (!editingManagerNotes) {
      const map = {};
      (review.kpi_progress || []).forEach((p) => {
        map[p.assigned_kpi_id] = {
          manager_notes:    p.manager_notes    || '',
          current_value:    p.current_value    || '',
          progress_percent: p.progress_percent ?? 0,
        };
      });
      setManagerNotesEdits(map);
      setManagerCommentEdit(review.manager_comments || '');
    }
  }, [review, editingManagerNotes]);

  // Evidence form.
  const [evidenceTitle, setEvidenceTitle]   = useState('');
  const [evidenceUrl, setEvidenceUrl]       = useState('');
  const [evidenceDesc, setEvidenceDesc]     = useState('');
  const [evidenceKpiId, setEvidenceKpiId]   = useState('');
  const [showEvidenceForm, setShowEvidenceForm] = useState(false);

  const isLocked    = review.status === MCR_STATUS.LOCKED;
  const autoLocked  = isAutoLocked(review);
  const curIdx      = stepIndex(review.status);

  // Flatten all KPIs from the assignment.
  const allKpis = useMemo(() => {
    if (!assignment) return [];
    return (assignment.kras || []).flatMap((kra) =>
      (kra.kpis || []).map((kpi) => ({ ...kpi, kra_title: kra.title }))
    );
  }, [assignment]);

  // ── Action helpers ────────────────────────────────────────────────────────

  const act = async (fn, label) => {
    setBusy(true); setError('');
    try {
      const updated = await fn();
      setReview(updated);
      onChanged && onChanged();
    } catch (e) {
      setError(e?.data?.detail || e?.message || `${label} failed.`);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveProgress = (submit = false) => {
    const kpi_progress = allKpis.map((kpi) => {
      const ed = progressEdits[kpi.id] || {};
      return {
        assigned_kpi_id: kpi.id,
        current_value: ed.current_value || '',
        progress_percent: parseFloat(ed.progress_percent) || 0,
        employee_notes: ed.employee_notes || '',
      };
    });
    const payload = { kpi_progress, employee_comments: employeeComments };
    if (submit) {
      act(() => pmsApi.submitProgress(review.id, payload), 'Submit');
    } else {
      act(() => pmsApi.saveProgress(review.id, payload), 'Save');
    }
    setEditingProgress(false);
  };

  // ── Manager: save draft notes without advancing state ──────────────────────

  const handleStartManagerEdit = () => {
    // Seed with current saved values (employee-submitted + any existing manager edits).
    const map = {};
    // First seed from KPI progress (has both employee values and manager_notes).
    (review.kpi_progress || []).forEach((p) => {
      map[p.assigned_kpi_id] = {
        manager_notes:    p.manager_notes    || '',
        current_value:    p.current_value    || '',
        progress_percent: p.progress_percent ?? 0,
      };
    });
    // Also pre-populate KPIs that have no progress row yet (so manager can edit them all).
    allKpis.forEach((kpi) => {
      if (!(kpi.id in map)) {
        map[kpi.id] = { manager_notes: '', current_value: '', progress_percent: 0 };
      }
    });
    setManagerNotesEdits(map);
    setManagerCommentEdit(review.manager_comments || '');
    setEditingManagerNotes(true);
  };

  const handleCancelManagerEdit = () => {
    setEditingManagerNotes(false);
  };

  const handleSaveManagerNotes = async () => {
    const kpi_notes = Object.entries(managerNotesEdits).map(([kid, data]) => ({
      assigned_kpi_id:  parseInt(kid, 10),
      manager_notes:    data.manager_notes    || null,
      current_value:    data.current_value    || null,
      progress_percent: data.progress_percent !== '' && data.progress_percent !== null
        ? parseFloat(data.progress_percent)
        : null,
    }));
    setBusy(true); setError('');
    try {
      const updated = await pmsApi.managerSaveMidCycleNotes(review.id, {
        manager_comments: managerCommentEdit || null,
        kpi_notes,
      });
      setReview(updated);
      setEditingManagerNotes(false);
      onChanged && onChanged();
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Save Notes failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleManagerReview = () => {
    act(() => pmsApi.managerReviewMidCycle(review.id, { manager_comments: comment }), 'Manager Review');
    setComment('');
  };

  const handleManagerApprove = () => {
    act(() => pmsApi.managerApproveMidCycle(review.id, { comment }), 'Manager Approve');
    setComment('');
  };

  const handleHrReview = () => {
    act(() => pmsApi.hrReviewMidCycle(review.id, { comment }), 'HR Review');
    setComment('');
  };

  const handleLock = () => {
    act(() => pmsApi.lockMidCycle(review.id, { comment }), 'Lock');
    setComment('');
  };

  const handleUnlock = () => {
    act(() => pmsApi.unlockMidCycle(review.id, {}), 'Unlock');
  };

  const handleAddEvidence = () => {
    if (!evidenceTitle.trim()) return;
    act(() => pmsApi.addEvidence(review.id, {
      title: evidenceTitle.trim(),
      description: evidenceDesc.trim() || null,
      evidence_url: evidenceUrl.trim() || null,
      assigned_kpi_id: evidenceKpiId ? parseInt(evidenceKpiId) : null,
    }), 'Add Evidence').then(() => {
      setEvidenceTitle(''); setEvidenceUrl(''); setEvidenceDesc(''); setEvidenceKpiId('');
      setShowEvidenceForm(false);
      pmsApi.midCycleReview(review.id).then((r) => setReview(r)).catch(() => {});
    });
  };

  const handleDeleteEvidence = (evId) => {
    act(async () => {
      await pmsApi.deleteEvidence(review.id, evId);
      return await pmsApi.midCycleReview(review.id);
    }, 'Delete Evidence');
  };

  // ── Permission flags ──────────────────────────────────────────────────────

  const canEditProgress = viewerRole === 'employee' &&
    [MCR_STATUS.DRAFT, MCR_STATUS.IN_PROGRESS].includes(review.status);
  const canSubmit = viewerRole === 'employee' &&
    [MCR_STATUS.DRAFT, MCR_STATUS.IN_PROGRESS].includes(review.status);
  const canAddEvidence = viewerRole === 'employee' && !isLocked &&
    [MCR_STATUS.DRAFT, MCR_STATUS.IN_PROGRESS, MCR_STATUS.SUBMITTED].includes(review.status);
  // Manager can save notes (without advancing state) when status is 'submitted' or 'manager_reviewed'.
  // After 'manager_approved' the review is read-only for the manager.
  const canManagerEdit    = viewerRole === 'manager' &&
    [MCR_STATUS.SUBMITTED, MCR_STATUS.MGR_REVIEWED].includes(review.status);
  const canManagerReview  = viewerRole === 'manager' && review.status === MCR_STATUS.SUBMITTED;
  const canManagerApprove = viewerRole === 'manager' && review.status === MCR_STATUS.MGR_REVIEWED;
  const canHrReview = viewerRole === 'hr' && review.status === MCR_STATUS.MGR_APPROVED;
  const canLock     = viewerRole === 'hr' &&
    [MCR_STATUS.HR_REVIEWED, MCR_STATUS.MGR_APPROVED].includes(review.status);
  const canUnlock   = viewerRole === 'hr' && isLocked && !autoLocked;

  const modalTitle = `${review.cycle_period || 'Mid-Cycle'} Review — ${review.employee_name || ''}`;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Modal title={modalTitle} onClose={onClose} width="max-w-4xl">

      {/* ── Summary strip (matches GoalDetailDrawer header style) ── */}
      <div className="-mx-6 -mt-5 mb-6 border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white px-6 pb-5 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs text-slate-500">
              Employee: <span className="font-semibold text-slate-700">{review.employee_name || '—'}</span>
              {review.manager_name && (
                <> · Manager: <span className="font-semibold text-slate-700">{review.manager_name}</span></>
              )}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              Period: {review.period || '—'} · Cycle: {review.cycle_period || 'Mid-Cycle'}
            </p>
          </div>
          <StatusPill status={review.status} />
        </div>

        {/* Progress stepper */}
        <ol className="mt-5 flex items-center gap-0">
          {STEPS.map((step, i) => {
            const done   = i < curIdx;
            const active = i === curIdx;
            return (
              <li key={step.id} className="flex flex-1 items-center">
                <span className={[
                  'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold',
                  done   ? 'bg-emerald-500 text-white' :
                  active ? 'bg-blue-700 text-white ring-2 ring-blue-200' :
                           'bg-slate-100 text-slate-400'
                ].join(' ')}>
                  {done ? '✓' : i + 1}
                </span>
                <span className={[
                  'ml-1 hidden text-[9px] font-semibold sm:block',
                  active ? 'text-blue-700' : done ? 'text-emerald-600' : 'text-slate-400'
                ].join(' ')}>
                  {step.label}
                </span>
                {i < STEPS.length - 1 && (
                  <div className={['mx-1 h-px flex-1', done ? 'bg-emerald-400' : 'bg-slate-200'].join(' ')} />
                )}
              </li>
            );
          })}
        </ol>
      </div>

      {/* ── Locked banner ── */}
      {isLocked && (
        <div className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3 ${autoLocked ? 'border-orange-200 bg-orange-50' : 'border-rose-200 bg-rose-50'}`}>
          <svg className={`mt-0.5 shrink-0 ${autoLocked ? 'text-orange-600' : 'text-rose-600'}`} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
          </svg>
          <div>
            <p className={`text-sm font-semibold ${autoLocked ? 'text-orange-800' : 'text-rose-800'}`}>
              {autoLocked ? 'Auto-locked by system' : 'Mid-cycle review is locked.'}
            </p>
            {autoLocked && (
              <p className="mt-0.5 text-xs text-orange-700">
                This phase has been automatically locked after the deadline and can no longer be modified.
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {/* ── KPI Progress ── */}
      <section className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">KPI Progress</h3>
          <div className="flex items-center gap-2">
            {/* Employee: edit their own progress */}
            {canEditProgress && !editingProgress && (
              <button type="button" onClick={() => setEditingProgress(true)}
                className="rounded-lg bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-100">
                Edit Progress
              </button>
            )}
            {editingProgress && (
              <>
                <button type="button" onClick={() => setEditingProgress(false)}
                  className="text-xs text-slate-500 hover:text-slate-700">Cancel</button>
                <button type="button" onClick={() => handleSaveProgress(false)} disabled={busy}
                  className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200">
                  Save Draft
                </button>
              </>
            )}
            {/* Manager: edit per-KPI notes without advancing state (Issue 2 fix) */}
            {canManagerEdit && !editingManagerNotes && (
              <button type="button" onClick={handleStartManagerEdit}
                className="rounded-lg bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600 hover:bg-indigo-100">
                Edit Notes
              </button>
            )}
            {editingManagerNotes && (
              <>
                <button type="button" onClick={handleCancelManagerEdit}
                  className="text-xs text-slate-500 hover:text-slate-700">Cancel</button>
                <button type="button" onClick={handleSaveManagerNotes} disabled={busy}
                  className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
                  {busy ? 'Saving…' : 'Save Notes'}
                </button>
              </>
            )}
          </div>
        </div>

        {allKpis.length === 0 && (
          <p className="text-xs text-slate-400">No KPIs found for this assignment.</p>
        )}

        {allKpis.map((kpi) => {
          const saved = (review.kpi_progress || []).find((p) => p.assigned_kpi_id === kpi.id);
          const ed    = progressEdits[kpi.id] || {};

          // Issue 2 fix: scale progress relative to KPI weightage.
          // Employee enters absolute progress (0-100). Display bar = progress / weight * 100.
          const rawProgress = saved ? (saved.progress_percent || 0) : 0;
          const displayPct  = (kpi.weightage > 0)
            ? Math.min(100, (rawProgress / kpi.weightage) * 100)
            : rawProgress;

          return (
            <div key={kpi.id} className="mb-3 rounded-xl border border-slate-100 bg-slate-50/50 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] text-slate-400">{kpi.kra_title}</p>
                  <p className="text-xs font-semibold text-slate-800">{kpi.title}</p>
                </div>
                <span className="text-[10px] font-semibold text-slate-400">{kpi.weightage}%</span>
              </div>

              {editingProgress ? (
                <div className="mt-2 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                      placeholder="Current value / achievement"
                      value={ed.current_value || ''}
                      onChange={(e) => setProgressEdits((prev) => ({
                        ...prev, [kpi.id]: { ...(prev[kpi.id] || {}), current_value: e.target.value }
                      }))}
                    />
                    <div className="flex items-center gap-1">
                      <input
                        type="number" min="0" max="100"
                        className="w-16 rounded-lg border border-slate-200 bg-white px-2 py-1 text-center text-xs"
                        value={ed.progress_percent ?? 0}
                        onChange={(e) => setProgressEdits((prev) => ({
                          ...prev, [kpi.id]: { ...(prev[kpi.id] || {}), progress_percent: e.target.value }
                        }))}
                      />
                      <span className="text-xs text-slate-400">/ {kpi.weightage}%</span>
                    </div>
                  </div>
                  <textarea
                    className="w-full resize-none rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                    rows={2}
                    placeholder="Notes on this KPI (optional)"
                    value={ed.employee_notes || ''}
                    onChange={(e) => setProgressEdits((prev) => ({
                      ...prev, [kpi.id]: { ...(prev[kpi.id] || {}), employee_notes: e.target.value }
                    }))}
                  />
                </div>
              ) : saved ? (
                <div className="mt-2 space-y-1">
                  {/* Scaled progress bar: progress / kpi_weight */}
                  <ProgressBar value={displayPct} />
                  <p className="text-[10px] text-slate-400">
                    {rawProgress}% of {kpi.weightage}% allocated
                    {kpi.weightage > 0 && ` · ${displayPct.toFixed(0)}% completion`}
                  </p>
                  {saved.current_value && (
                    <p className="text-[11px] text-slate-600">
                      Achievement: <span className="font-semibold">{saved.current_value}</span>
                    </p>
                  )}
                  {saved.employee_notes && (
                    <p className="text-[11px] italic text-slate-500">"{saved.employee_notes}"</p>
                  )}
                  {/* Manager fields — editable when manager is in edit mode, read-only otherwise */}
                  {editingManagerNotes ? (
                    <div className="mt-2 space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-2">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-500">Manager Edit</p>
                      {/* Achievement / current value override */}
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">Achievement</label>
                        <input
                          className="w-full rounded-lg border border-indigo-200 bg-white px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none"
                          placeholder="Override achievement / current value…"
                          value={(managerNotesEdits[kpi.id] || {}).current_value || ''}
                          onChange={(e) => setManagerNotesEdits((prev) => ({
                            ...prev,
                            [kpi.id]: { ...(prev[kpi.id] || {}), current_value: e.target.value },
                          }))}
                        />
                      </div>
                      {/* Progress % override */}
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">
                          Progress % <span className="text-slate-400 font-normal">(of {kpi.weightage}% allocated)</span>
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="number" min="0" max="100" step="0.1"
                            className="w-20 rounded-lg border border-indigo-200 bg-white px-2 py-1 text-center text-xs focus:border-indigo-400 focus:outline-none"
                            value={(managerNotesEdits[kpi.id] || {}).progress_percent ?? 0}
                            onChange={(e) => setManagerNotesEdits((prev) => ({
                              ...prev,
                              [kpi.id]: { ...(prev[kpi.id] || {}), progress_percent: e.target.value },
                            }))}
                          />
                          <span className="text-[10px] text-slate-400">%</span>
                          {/* Live mini-bar */}
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                            <div className="h-full rounded-full bg-indigo-400 transition-all"
                              style={{ width: `${Math.min(100, Math.max(0, parseFloat((managerNotesEdits[kpi.id] || {}).progress_percent) || 0))}%` }} />
                          </div>
                        </div>
                      </div>
                      {/* Manager notes */}
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">Manager Notes</label>
                        <textarea
                          className="w-full resize-none rounded-lg border border-indigo-200 bg-white px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none"
                          rows={2}
                          placeholder="Add manager notes for this KPI…"
                          value={(managerNotesEdits[kpi.id] || {}).manager_notes || ''}
                          onChange={(e) => setManagerNotesEdits((prev) => ({
                            ...prev,
                            [kpi.id]: { ...(prev[kpi.id] || {}), manager_notes: e.target.value },
                          }))}
                        />
                      </div>
                    </div>
                  ) : (saved.manager_notes && (
                    <div className="mt-1 rounded-lg bg-blue-50 px-2 py-1">
                      <p className="text-[11px] font-semibold text-blue-700">Manager: {saved.manager_notes}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2">
                  <p className="text-[11px] italic text-slate-400">No progress recorded yet.</p>
                  {/* Manager can enter progress even when employee hasn't submitted */}
                  {editingManagerNotes && (
                    <div className="mt-2 space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-2">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-500">Manager Edit</p>
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">Achievement</label>
                        <input
                          className="w-full rounded-lg border border-indigo-200 bg-white px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none"
                          placeholder="Enter achievement / current value…"
                          value={(managerNotesEdits[kpi.id] || {}).current_value || ''}
                          onChange={(e) => setManagerNotesEdits((prev) => ({
                            ...prev,
                            [kpi.id]: { ...(prev[kpi.id] || {}), current_value: e.target.value },
                          }))}
                        />
                      </div>
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">
                          Progress % <span className="text-slate-400 font-normal">(of {kpi.weightage}% allocated)</span>
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="number" min="0" max="100" step="0.1"
                            className="w-20 rounded-lg border border-indigo-200 bg-white px-2 py-1 text-center text-xs focus:border-indigo-400 focus:outline-none"
                            value={(managerNotesEdits[kpi.id] || {}).progress_percent ?? 0}
                            onChange={(e) => setManagerNotesEdits((prev) => ({
                              ...prev,
                              [kpi.id]: { ...(prev[kpi.id] || {}), progress_percent: e.target.value },
                            }))}
                          />
                          <span className="text-[10px] text-slate-400">%</span>
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                            <div className="h-full rounded-full bg-indigo-400 transition-all"
                              style={{ width: `${Math.min(100, Math.max(0, parseFloat((managerNotesEdits[kpi.id] || {}).progress_percent) || 0))}%` }} />
                          </div>
                        </div>
                      </div>
                      <div>
                        <label className="mb-0.5 block text-[10px] font-semibold text-indigo-600">Manager Notes</label>
                        <textarea
                          className="w-full resize-none rounded-lg border border-indigo-200 bg-white px-2 py-1 text-xs focus:border-indigo-400 focus:outline-none"
                          rows={2}
                          placeholder="Add manager notes for this KPI…"
                          value={(managerNotesEdits[kpi.id] || {}).manager_notes || ''}
                          onChange={(e) => setManagerNotesEdits((prev) => ({
                            ...prev,
                            [kpi.id]: { ...(prev[kpi.id] || {}), manager_notes: e.target.value },
                          }))}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {editingProgress && (
          <div className="mt-2">
            <label className="mb-1 block text-xs font-semibold text-slate-600">Overall Comments</label>
            <textarea
              className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs"
              rows={3}
              placeholder="Add your overall progress comments..."
              value={employeeComments}
              onChange={(e) => setEmployeeComments(e.target.value)}
            />
          </div>
        )}

        {/* Manager overall comment field — editable when in manager notes edit mode */}
        {editingManagerNotes && (
          <div className="mt-3 border-t border-indigo-100 pt-3">
            <label className="mb-1 block text-xs font-semibold text-indigo-600">Overall Manager Comment</label>
            <textarea
              className="w-full resize-none rounded-lg border border-indigo-200 bg-indigo-50/40 px-3 py-2 text-xs focus:border-indigo-400 focus:outline-none"
              rows={3}
              placeholder="Add an overall comment on this review…"
              value={managerCommentEdit}
              onChange={(e) => setManagerCommentEdit(e.target.value)}
            />
          </div>
        )}
      </section>

      {/* ── Employee Comments (read) ── */}
      {!editingProgress && review.employee_comments && (
        <section className="mb-5">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Employee Comments</h3>
          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700">
            {review.employee_comments}
          </div>
        </section>
      )}

      {/* ── Manager Comments (read-only; edit UI is embedded in KPI section above) ── */}
      {!editingManagerNotes && review.manager_comments && (
        <section className="mb-5">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Manager Comments</h3>
          <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-xs text-blue-800">
            {review.manager_comments}
          </div>
        </section>
      )}

      {/* ── HR Comments ── */}
      {review.hr_comments && (
        <section className="mb-5">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">HR Comments</h3>
          <div className="rounded-xl border border-violet-100 bg-violet-50 p-3 text-xs text-violet-800">
            {review.hr_comments}
          </div>
        </section>
      )}

      {/* ── Competency Goals (Issue 1 fix) ───────────────────────────────────────
           Competencies come from the assignment, not from the review itself.
           They are display-only in mid-cycle — no employee progress input for
           competencies at this stage (they are rated in End Cycle Assessment).
           Rendered only when the parent passed `assignment` with competencies. */}
      {(assignment?.competencies || []).length > 0 && (
        <section className="mb-6">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            Competency Goals
          </h3>
          <div className="space-y-2">
            {(assignment.competencies || []).map((comp) => (
              <div key={comp.id} className="rounded-xl border border-slate-100 bg-slate-50/50 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-slate-800">{comp.title}</p>
                    {comp.description && (
                      <p className="mt-0.5 text-[11px] text-slate-500">{comp.description}</p>
                    )}
                    {comp.target_level && (
                      <p className="mt-0.5 text-[10px] text-slate-400">
                        Target Level: <span className="font-semibold text-slate-600">{comp.target_level}</span>
                      </p>
                    )}
                  </div>
                  <span className="flex-shrink-0 text-[10px] font-semibold text-slate-400">
                    {comp.weightage}%
                  </span>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] italic text-slate-400">
            Competencies are rated during the End Cycle Assessment phase.
          </p>
        </section>
      )}

      {/* ── Evidence ── */}
      <section className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Evidence</h3>
          {canAddEvidence && (
            <button type="button" onClick={() => setShowEvidenceForm((v) => !v)}
              className="rounded-lg bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-600 hover:bg-teal-100">
              {showEvidenceForm ? 'Cancel' : '+ Add Evidence'}
            </button>
          )}
        </div>

        {showEvidenceForm && (
          <div className="mb-3 space-y-2 rounded-xl border border-teal-100 bg-teal-50/30 p-3">
            <input className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
              placeholder="Title *" value={evidenceTitle} onChange={(e) => setEvidenceTitle(e.target.value)} />
            <input className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
              placeholder="URL (optional)" value={evidenceUrl} onChange={(e) => setEvidenceUrl(e.target.value)} />
            <textarea className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs"
              rows={2} placeholder="Description (optional)"
              value={evidenceDesc} onChange={(e) => setEvidenceDesc(e.target.value)} />
            <select className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600"
              value={evidenceKpiId} onChange={(e) => setEvidenceKpiId(e.target.value)}>
              <option value="">Link to KPI (optional)</option>
              {allKpis.map((kpi) => (
                <option key={kpi.id} value={kpi.id}>{kpi.kra_title} → {kpi.title}</option>
              ))}
            </select>
            <button type="button" onClick={handleAddEvidence} disabled={busy || !evidenceTitle.trim()}
              className="rounded-lg bg-teal-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-teal-600 disabled:opacity-50">
              Add
            </button>
          </div>
        )}

        {(review.evidences || []).length === 0 ? (
          <p className="text-xs italic text-slate-400">No evidence added yet.</p>
        ) : (
          <div className="space-y-2">
            {(review.evidences || []).map((ev) => {
              const linkedKpi = allKpis.find((k) => k.id === ev.assigned_kpi_id);
              return (
                <div key={ev.id} className="flex items-start gap-2 rounded-xl border border-slate-100 p-3 text-xs">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-slate-800">{ev.title}</p>
                    {linkedKpi && <p className="text-[11px] text-slate-500">KPI: {linkedKpi.title}</p>}
                    {ev.description && <p className="mt-0.5 text-slate-500">{ev.description}</p>}
                    {ev.evidence_url && (
                      <a href={ev.evidence_url} target="_blank" rel="noopener noreferrer"
                        className="mt-0.5 inline-flex items-center gap-1 text-blue-600 hover:underline">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                          <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                        Link
                      </a>
                    )}
                  </div>
                  {canAddEvidence && (
                    <button type="button" onClick={() => handleDeleteEvidence(ev.id)}
                      className="flex-shrink-0 text-slate-300 hover:text-red-500">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
                      </svg>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Comment textarea for manager/HR actions ── */}
      {(canManagerReview || canManagerApprove || canHrReview || canLock) && (
        <section className="mb-5">
          <label className="mb-1.5 block text-xs font-semibold text-slate-600">
            {canLock ? 'Lock Comment (optional)' : 'Comment (optional)'}
          </label>
          <textarea
            className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-xs focus:border-blue-300 focus:outline-none"
            rows={3}
            placeholder="Add a comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </section>
      )}

      {/* ── Action buttons (inline at bottom, matches GoalDetailDrawer pattern) ── */}
      <div className="-mx-6 -mb-5 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <button type="button" onClick={onClose}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          Close
        </button>

        <div className="flex flex-wrap items-center gap-2">
          {/* Employee actions */}
          {canSubmit && !editingProgress && (
            <button type="button" disabled={busy} onClick={() => setEditingProgress(true)}
              className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-600 hover:bg-blue-100 disabled:opacity-50">
              Update Progress
            </button>
          )}
          {canSubmit && editingProgress && (
            <button type="button" disabled={busy} onClick={() => handleSaveProgress(true)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
              {busy ? 'Submitting…' : 'Submit for Review'}
            </button>
          )}

          {/* Manager actions */}
          {canManagerReview && (
            <button type="button" disabled={busy} onClick={handleManagerReview}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
              {busy ? 'Saving…' : 'Mark Reviewed'}
            </button>
          )}
          {canManagerApprove && (
            <button type="button" disabled={busy} onClick={handleManagerApprove}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
              {busy ? 'Approving…' : 'Approve Review'}
            </button>
          )}

          {/* HR actions */}
          {canHrReview && (
            <button type="button" disabled={busy} onClick={handleHrReview}
              className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50">
              {busy ? 'Saving…' : 'Mark HR Reviewed'}
            </button>
          )}
          {canLock && (
            <button type="button" disabled={busy} onClick={handleLock}
              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
              </svg>
              {busy ? 'Locking…' : 'Lock Mid-Cycle'}
            </button>
          )}
          {canUnlock && (
            <button type="button" disabled={busy} onClick={handleUnlock}
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-50">
              {busy ? '…' : 'Unlock'}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
