import { useEffect, useState } from 'react';
import Modal from '../../../components/Modal';
import Toast from '../../../components/Timesheets/Toast';
import { pmsApi, PMS_STATUS, PMS_STATUS_LABEL, isAutoLocked } from '../../../services/pms';
import { Avatar, StatusPill } from './PerformanceHubPage';

// Shared goal-sheet drawer used by HR, Manager and Employee.
// Renders the full assignment with a left-rail status stepper, a
// readable read-only view and an inline editor that activates per-role.

// Stepper order — keeps state-machine progress in sync visually.
const FLOW = [
  { key: PMS_STATUS.GOALS_SENT,         label: 'Goals Sent',         actor: 'HR' },
  { key: PMS_STATUS.UNDER_DISCUSSION,   label: 'Under Discussion',   actor: 'Manager' },
  { key: PMS_STATUS.EMPLOYEE_CONFIRMED, label: 'Employee Confirmed', actor: 'Employee' },
  { key: PMS_STATUS.MANAGER_APPROVED,   label: 'Manager Approved',   actor: 'Manager' },
  { key: PMS_STATUS.HR_REVIEWED,        label: 'HR Reviewed',        actor: 'HR' },
  { key: PMS_STATUS.GOALS_LOCKED,       label: 'Goals Locked',       actor: 'HR' },
];

const ROLE_TONE = {
  hr:       'bg-blue-50 text-blue-700 ring-blue-200',
  manager:  'bg-amber-50 text-amber-700 ring-amber-200',
  employee: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
};

export default function GoalDetailDrawer({ assignment, viewerRole, onClose, onChanged }) {
  const [a, setA] = useState(assignment);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [drawerToast, setDrawerToast] = useState(null);
  const showToast = (msg, type = 'error') => setDrawerToast({ msg, type });
  const [comment, setComment] = useState('');

  useEffect(() => {
    if (!assignment?.id) return;
    pmsApi.assignment(assignment.id).then(setA).catch(() => {});
  }, [assignment?.id]);

  if (!a) return null;
  const locked = a.status === PMS_STATUS.GOALS_LOCKED;
  const autoLocked = isAutoLocked(a);

  const canEdit = (() => {
    if (locked) return false;
    if (viewerRole === 'hr') return false;
    // CHANGE 2: Manager can also edit during employee_confirmed (manager review) state
    if (viewerRole === 'manager') return [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION, PMS_STATUS.EMPLOYEE_CONFIRMED].includes(a.status);
    if (viewerRole === 'employee') return [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION].includes(a.status);
    return false;
  })();

  const startEdit = () => {
    setDraft({
      kras: (a.kras || []).map((k) => ({
        id: k.id, title: k.title, description: k.description || '',
        weightage: k.weightage || 0, sort_order: k.sort_order || 0,
        // CHANGE 1: preserve from_template flag so UI can enforce read-only
        from_template: k.from_template || false,
        kpis: (k.kpis || []).map((p) => ({
          id: p.id, title: p.title, description: p.description || '',
          weightage: p.weightage || 0,
          from_template: p.from_template || false,
        })),
      })),
      competencies: (a.competencies || []).map((c) => ({
        id: c.id, title: c.title, description: c.description || '', weightage: c.weightage || 0,
        from_template: c.from_template || false,
      })),
    });
    setEditing(true);
  };

  const buildPayload = () => ({
    kras: (draft?.kras || []).map((k) => ({
      id: k.id || null,
      title: k.title, description: k.description || null,
      weightage: Number(k.weightage) || 0, sort_order: Number(k.sort_order) || 0,
      kpis: (k.kpis || []).map((p) => ({
        id: p.id || null,
        title: p.title, description: p.description || null,
        weightage: Number(p.weightage) || 0,
      })),
    })),
    competencies: (draft?.competencies || []).map((c) => ({
      id: c.id || null, title: c.title, description: c.description || null,
      weightage: Number(c.weightage) || 0,
    })),
    comment: comment.trim() || null,
  });

  const callAction = async (action) => {
    setBusy(true);
    try {
      let updated;
      const payload = editing ? buildPayload() : (comment ? { comment } : {});
      if (action === 'discuss')          updated = await pmsApi.managerDiscuss(a.id, payload);
      else if (action === 'employee')    updated = await pmsApi.employeeConfirm(a.id, payload);
      else if (action === 'mgrApprove')  updated = await pmsApi.managerApprove(a.id, payload);
      else if (action === 'hrReview')    updated = await pmsApi.hrReview(a.id, payload);
      else if (action === 'lock')        updated = await pmsApi.lock(a.id, payload);
      else if (action === 'unlock')      updated = await pmsApi.unlock(a.id, payload);
      else if (action === 'comment') {
        await pmsApi.comment(a.id, comment.trim());
        updated = await pmsApi.assignment(a.id);
      }
      setA(updated);
      setEditing(false);
      setDraft(null);
      setComment('');
      onChanged && onChanged();
    } catch (e) {
      showToast(e?.data?.detail || e?.message || 'Action failed');
    } finally { setBusy(false); }
  };

  // ── Actions per role × status ─────────────────────────────────────
  const actions = [];
  if (viewerRole === 'manager') {
    if ([PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION].includes(a.status))
      actions.push({ key: 'discuss', label: editing ? 'Save & Mark Discussed' : 'Mark Under Discussion', tone: 'primary' });
    if (a.status === PMS_STATUS.EMPLOYEE_CONFIRMED)
      // CHANGE 2: label changes when manager is editing during review
      actions.push({ key: 'mgrApprove', label: editing ? 'Save & Approve' : 'Approve Goals', tone: 'success' });
  } else if (viewerRole === 'employee') {
    if ([PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION].includes(a.status))
      actions.push({ key: 'employee', label: editing ? 'Save & Accept' : 'Accept Goals', tone: 'success' });
  } else if (viewerRole === 'hr') {
    if (a.status === PMS_STATUS.MANAGER_APPROVED)
      actions.push({ key: 'hrReview', label: 'Mark HR Reviewed', tone: 'primary' });
    if ([PMS_STATUS.HR_REVIEWED, PMS_STATUS.MANAGER_APPROVED].includes(a.status))
      actions.push({ key: 'lock', label: 'Lock Goals', tone: 'danger' });
    if (a.status === PMS_STATUS.GOALS_LOCKED && !autoLocked)
      actions.push({ key: 'unlock', label: 'Unlock', tone: 'primary' });
  }

  // Draft editing helpers
  const setKra = (i, patch) => setDraft((d) => ({ ...d, kras: d.kras.map((k, idx) => idx === i ? { ...k, ...patch } : k) }));
  const addKra = () => setDraft((d) => ({ ...d, kras: [...d.kras, { title: '', description: '', weightage: 0, sort_order: d.kras.length, kpis: [] }] }));
  const removeKra = (i) => setDraft((d) => ({ ...d, kras: d.kras.filter((_, idx) => idx !== i) }));
  const addKpi = (i) => setKra(i, { kpis: [...draft.kras[i].kpis, { title: '', description: '', weightage: 0 }] });
  const removeKpi = (i, j) => setKra(i, { kpis: draft.kras[i].kpis.filter((_, idx) => idx !== j) });
  const setKpi = (i, j, patch) => setKra(i, { kpis: draft.kras[i].kpis.map((p, idx) => idx === j ? { ...p, ...patch } : p) });
  const addComp = () => setDraft((d) => ({ ...d, competencies: [...d.competencies, { title: '', description: '', weightage: 0 }] }));
  const removeComp = (i) => setDraft((d) => ({ ...d, competencies: d.competencies.filter((_, idx) => idx !== i) }));
  const setComp = (i, patch) => setDraft((d) => ({ ...d, competencies: d.competencies.map((c, idx) => idx === i ? { ...c, ...patch } : c) }));

  // Stepper state
  const flowIdx = FLOW.findIndex((s) => s.key === a.status);

  return (
    <Modal title="Goal Sheet" onClose={onClose} width="max-w-5xl">
      {drawerToast && (
        <Toast message={drawerToast.msg} type={drawerToast.type} onClose={() => setDrawerToast(null)} />
      )}
      {/* Header summary */}
      <div className="-mx-6 -mt-5 mb-6 border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white px-6 pb-5 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Avatar name={a.employee_name || `E${a.employee_id}`} size={48} />
            <div>
              <h2 className="text-lg font-bold text-slate-900">{a.employee_name || `Employee #${a.employee_id}`}</h2>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                {a.period && (
                  <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 font-semibold text-blue-700">
                    {a.period}
                  </span>
                )}
                <span>Manager: <span className="font-semibold text-slate-700">{a.manager_name || '—'}</span></span>
                {a.sent_at && <span>· sent {new Date(a.sent_at).toLocaleDateString()}</span>}
              </p>
            </div>
          </div>
          <StatusPill status={a.status} />
        </div>

        {/* Stepper */}
        <div className="mt-5 flex flex-wrap items-center gap-1 overflow-x-auto">
          {FLOW.map((s, i) => {
            const done = i < flowIdx;
            const active = i === flowIdx;
            return (
              <div key={s.key} className="flex flex-1 min-w-[110px] items-center">
                <div className="flex flex-col items-center text-center">
                  <div
                    className={
                      'flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold ring-2 ring-offset-2 ring-offset-white transition ' +
                      (done   ? 'bg-emerald-500 text-white ring-emerald-200' :
                       active ? 'bg-blue-700 text-white ring-blue-200'
                              : 'bg-slate-200 text-slate-500 ring-slate-100')
                    }
                  >
                    {done ? '✓' : i + 1}
                  </div>
                  <span className={'mt-1.5 text-[10px] font-semibold ' + (active ? 'text-blue-700' : done ? 'text-emerald-600' : 'text-slate-400')}>
                    {s.label}
                  </span>
                </div>
                {i < FLOW.length - 1 && (
                  <div className={'mx-1 h-0.5 flex-1 rounded-full ' + (done ? 'bg-emerald-300' : 'bg-slate-200')} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {locked && (
        <div className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3 ${autoLocked ? 'border-orange-200 bg-orange-50' : 'border-rose-200 bg-rose-50'}`}>
          <svg className={`mt-0.5 shrink-0 ${autoLocked ? 'text-orange-600' : 'text-rose-600'}`} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
          <div>
            <p className={`text-sm font-semibold ${autoLocked ? 'text-orange-800' : 'text-rose-800'}`}>
              {autoLocked ? 'Auto-locked by system' : 'Goals are locked'}
            </p>
            <p className={`mt-0.5 text-xs ${autoLocked ? 'text-orange-700' : 'text-rose-700'}`}>
              {autoLocked
                ? 'This phase has been automatically locked after the deadline and can no longer be modified.'
                : 'Editing is disabled until HR unlocks this goal sheet.'}
            </p>
          </div>
        </div>
      )}

      {/* KRAs */}
      <SectionHeader title="Key Result Areas" count={(a.kras || []).length} accent="blue" />
      {!editing && (
        <div className="space-y-3">
          {(a.kras || []).length === 0 && (
            <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
              No KRAs on this goal sheet.
            </p>
          )}
          {(a.kras || []).map((k) => (
            <div key={k.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-start justify-between gap-4 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
                <div className="min-w-0 flex items-start gap-2">
                  {k.from_template && (
                    <span title="Template goal — read-only" className="mt-0.5 shrink-0">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                    </span>
                  )}
                  <div>
                    <h4 className="text-sm font-bold text-slate-900">{k.title}</h4>
                    {k.description && <p className="mt-1 text-xs text-slate-500">{k.description}</p>}
                  </div>
                </div>
                <WeightBadge value={k.weightage} />
              </div>
              {(k.kpis || []).length > 0 && (
                <div className="divide-y divide-slate-100">
                  {k.kpis.map((p) => (
                    <div key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                      <span className="min-w-0 flex-1 font-semibold text-slate-800 truncate">{p.title}</span>
                      <WeightBadge value={p.weightage} small />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {editing && draft && (
        <div className="space-y-3">
          {draft.kras.map((k, i) => (
            k.from_template ? (
              // CHANGE 1: Template KRAs are read-only — show locked card, no edit/delete
              <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 p-4 opacity-80">
                <div className="mb-2 flex items-center gap-1.5">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Template — read-only</span>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-bold text-slate-700">{k.title}</p>
                    {k.description && <p className="mt-1 text-xs text-slate-500">{k.description}</p>}
                  </div>
                  <WeightBadge value={k.weightage} />
                </div>
                {k.kpis.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    {k.kpis.map((p, j) => (
                      <div key={j} className="flex flex-wrap items-center gap-2 rounded-lg bg-white px-3 py-2 ring-1 ring-slate-100 text-sm">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-300" />
                        <span className="min-w-0 flex-1 font-semibold text-slate-600 truncate">{p.title}</span>
                        <WeightBadge value={p.weightage} small />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              // User-added KRA — fully editable
              <div key={i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                <div className="grid grid-cols-12 gap-2">
                  <div className="col-span-12 sm:col-span-8"><Input value={k.title} onChange={(e) => setKra(i, { title: e.target.value })} placeholder="KRA title" /></div>
                  <div className="col-span-8 sm:col-span-3">
                    <div className="relative">
                      <Input type="number" value={k.weightage} onChange={(e) => setKra(i, { weightage: e.target.value })} placeholder="Weight" className="pr-7" />
                      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                    </div>
                  </div>
                  <div className="col-span-4 sm:col-span-1 flex justify-end">
                    <IconBtn tone="danger" onClick={() => removeKra(i)} title="Remove">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </IconBtn>
                  </div>
                </div>
                <textarea
                  rows={2}
                  placeholder="Description"
                  value={k.description}
                  onChange={(e) => setKra(i, { description: e.target.value })}
                  className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                <div className="mt-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">KPIs</p>
                    <button type="button" onClick={() => addKpi(i)} className="text-xs font-semibold text-blue-700 hover:underline">+ Add KPI</button>
                  </div>
                  <div className="space-y-2">
                    {k.kpis.map((p, j) => (
                      <div key={j} className="grid grid-cols-12 gap-2 rounded-lg bg-white p-2 ring-1 ring-slate-200">
                        <div className="col-span-12 sm:col-span-9"><Input value={p.title} onChange={(e) => setKpi(i, j, { title: e.target.value })} placeholder="KPI" /></div>
                        <div className="col-span-9 sm:col-span-2">
                          <div className="relative">
                            <Input type="number" value={p.weightage} onChange={(e) => setKpi(i, j, { weightage: e.target.value })} placeholder="Wt" className="pr-7" />
                            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                          </div>
                        </div>
                        <div className="col-span-3 sm:col-span-1 flex justify-end">
                          <IconBtn tone="ghost" onClick={() => removeKpi(i, j)} title="Remove">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                          </IconBtn>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )
          ))}
          <button type="button" onClick={addKra} className="w-full rounded-xl border-2 border-dashed border-blue-200 bg-blue-50/30 py-3 text-sm font-semibold text-blue-700 transition hover:bg-blue-50">
            + Add KRA
          </button>
        </div>
      )}

      {/* Competencies */}
      <SectionHeader title="Competency Goals" count={(a.competencies || []).length} accent="emerald" className="mt-6" />
      {!editing && (
        <div className="space-y-2">
          {(a.competencies || []).length === 0 && (
            <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
              No competency goals.
            </p>
          )}
          {(a.competencies || []).map((c) => (
            <div key={c.id} className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
              <div className="min-w-0 flex items-start gap-2">
                {c.from_template && (
                  <span title="Template competency — read-only" className="mt-0.5 shrink-0">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  </span>
                )}
                <div>
                  <p className="text-sm font-bold text-slate-900">{c.title}</p>
                  {c.description && <p className="mt-1 text-xs text-slate-500">{c.description}</p>}
                </div>
              </div>
              <WeightBadge value={c.weightage} tone="emerald" />
            </div>
          ))}
        </div>
      )}
      {editing && draft && (
        <div className="space-y-2">
          {draft.competencies.map((c, i) => (
            c.from_template ? (
              // CHANGE 1: Template competencies are read-only — no edit/delete
              <div key={i} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 opacity-80">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 text-slate-400"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-700">{c.title}</p>
                  {c.description && <p className="mt-0.5 text-xs text-slate-500">{c.description}</p>}
                </div>
                <WeightBadge value={c.weightage} tone="emerald" />
              </div>
            ) : (
              // User-added competency — fully editable
              <div key={i} className="grid grid-cols-12 gap-2 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                <div className="col-span-12 sm:col-span-3"><Input value={c.title} onChange={(e) => setComp(i, { title: e.target.value })} placeholder="Competency" /></div>
                <div className="col-span-12 sm:col-span-6"><Input value={c.description} onChange={(e) => setComp(i, { description: e.target.value })} placeholder="Description" /></div>
                <div className="col-span-9 sm:col-span-2">
                  <div className="relative">
                    <Input type="number" value={c.weightage} onChange={(e) => setComp(i, { weightage: e.target.value })} placeholder="Weight" className="pr-7" />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                  </div>
                </div>
                <div className="col-span-3 sm:col-span-1 flex justify-end">
                  <IconBtn tone="danger" onClick={() => removeComp(i)} title="Remove">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </IconBtn>
                </div>
              </div>
            )
          ))}
          <button type="button" onClick={addComp} className="w-full rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50/30 py-3 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50">
            + Add Competency
          </button>
        </div>
      )}

      {/* Discussion */}
      <SectionHeader title="Discussion" count={(a.comments || []).length} accent="amber" className="mt-6" />
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="max-h-60 overflow-y-auto p-4">
          {(a.comments || []).length === 0 && (
            <p className="text-center text-sm text-slate-400">No comments yet — start the conversation below.</p>
          )}
          <div className="space-y-3">
            {(a.comments || []).map((c) => (
              <div key={c.id} className="flex gap-3">
                <Avatar name={c.author_role.slice(0, 2)} size={32} />
                <div className="min-w-0 flex-1 rounded-xl bg-slate-50 px-3 py-2 ring-1 ring-slate-100">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className={'inline-flex items-center rounded-full px-2 py-0.5 font-bold uppercase tracking-wider ring-1 ' + (ROLE_TONE[c.author_role] || ROLE_TONE.employee)}>
                      {c.author_role}
                    </span>
                    <span className="text-slate-400">{new Date(c.created_at).toLocaleString()}</span>
                    {c.stage && (
                      <span className="text-slate-400">· {PMS_STATUS_LABEL[c.stage] || c.stage}</span>
                    )}
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{c.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-slate-100 bg-slate-50/60 p-3">
          {autoLocked ? (
            <p className="text-center text-xs text-orange-600">Auto-locked — comments are disabled.</p>
          ) : (
            <textarea
              rows={2}
              placeholder={canEdit || actions.length ? 'Add a comment (also captured with your next action)…' : 'Add a comment'}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="-mx-6 -mb-5 mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <div className="flex gap-2">
          {canEdit && !editing && (
            <button
              type="button"
              onClick={startEdit}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 transition hover:bg-blue-100"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              Edit goals
            </button>
          )}
          {editing && (
            <button
              type="button"
              onClick={() => { setEditing(false); setDraft(null); }}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              Cancel edit
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!autoLocked && comment && actions.length === 0 && (
            <button
              type="button"
              onClick={() => callAction('comment')}
              disabled={busy}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
            >
              Add Comment
            </button>
          )}
          {actions.map((act) => {
            const toneCls =
              act.tone === 'danger'  ? 'bg-rose-600 hover:bg-rose-700' :
              act.tone === 'success' ? 'bg-emerald-600 hover:bg-emerald-700' :
                                       'bg-blue-700 hover:bg-blue-800';
            return (
              <button
                key={act.key}
                type="button"
                onClick={() => callAction(act.key)}
                disabled={busy}
                className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-sm transition disabled:opacity-60 ${toneCls}`}
              >
                {act.label}
              </button>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}


// ── Atomics ────────────────────────────────────────────────────────


function SectionHeader({ title, count, accent = 'blue', className = '' }) {
  const tone = {
    blue:    'bg-blue-50 text-blue-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    amber:   'bg-amber-50 text-amber-700',
  }[accent];
  return (
    <div className={'mb-3 flex items-center gap-2 ' + className}>
      <h3 className="text-sm font-bold text-slate-900">{title}</h3>
      <span className={'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ' + tone}>{count}</span>
    </div>
  );
}

function WeightBadge({ value, tone = 'blue', small }) {
  const palette = {
    blue:    'bg-blue-100 text-blue-800',
    emerald: 'bg-emerald-100 text-emerald-800',
  }[tone];
  return (
    <span className={'inline-flex shrink-0 items-center rounded-full font-bold ' + palette + ' ' + (small ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs')}>
      {value}%
    </span>
  );
}

function Input({ className = '', ...rest }) {
  return (
    <input
      {...rest}
      className={
        'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 ' +
        className
      }
    />
  );
}

function IconBtn({ children, tone = 'ghost', onClick, title }) {
  const cls =
    tone === 'danger' ? 'bg-rose-50 text-rose-600 hover:bg-rose-100' :
    'bg-slate-100 text-slate-500 hover:bg-slate-200';
  return (
    <button type="button" onClick={onClick} title={title} className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition ${cls}`}>
      {children}
    </button>
  );
}
