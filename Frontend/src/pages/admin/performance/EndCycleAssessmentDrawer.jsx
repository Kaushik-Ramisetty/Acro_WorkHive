/**
 * EndCycleAssessmentDrawer — Phase 3 end-of-cycle assessment detail panel.
 *
 * Uses the shared Modal component (React Portal, z-[9999], centered overlay)
 * identical to GoalDetailDrawer so all three Phase 1/2/3 drawers open the same way.
 *
 * Props:
 *   assessment  - EndCycleAssessmentOut object from API
 *   assignment  - GoalAssignment the assessment belongs to (for KRA/competency tree)
 *   viewerRole  - 'employee' | 'manager' | 'hr'
 *   onClose     - () => void
 *   onChanged   - () => void
 */
import { useState, useMemo } from 'react';
import Modal from '../../../components/Modal';
import { pmsApi, ECA_STATUS, ECA_STATUS_LABEL, ECA_STATUS_TONE, RATING_LABELS, isAutoLocked } from '../../../services/pms';

// ── Helpers ───────────────────────────────────────────────────────────────────

const STEPS = [
  { id: ECA_STATUS.DRAFT,           label: 'Draft' },
  { id: ECA_STATUS.SELF_ASSESSED,   label: 'Self Assessed' },
  { id: ECA_STATUS.MGR_ASSESSED,    label: 'Mgr Assessed' },
  { id: ECA_STATUS.SUBMITTED_TO_HR, label: 'Submitted to HR' },
  { id: ECA_STATUS.HR_RECEIVED,     label: 'HR Received' },
  { id: ECA_STATUS.LOCKED,          label: 'Locked' },
];

const stepIndex = (s) => STEPS.findIndex((x) => x.id === s);

function StatusPill({ status }) {
  const tone = ECA_STATUS_TONE[status] || { bg: '#F1F5F9', fg: '#475569' };
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
      style={{ backgroundColor: tone.bg, color: tone.fg }}>
      {ECA_STATUS_LABEL[status] || status}
    </span>
  );
}

function RatingStars({ value, onChange, readonly = false }) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((s) => (
        <button key={s} type="button" disabled={readonly}
          onClick={() => !readonly && onChange && onChange(s)}
          className={`text-xl transition ${readonly ? 'cursor-default' : 'hover:scale-110'} ${
            s <= (value || 0) ? 'text-amber-400' : 'text-slate-200'
          }`}
          title={RATING_LABELS[s]}>
          ★
        </button>
      ))}
      {value ? (
        <span className="ml-2 text-xs font-semibold text-slate-600">
          {Number(value).toFixed(1)} — {RATING_LABELS[Math.round(value)] || ''}
        </span>
      ) : null}
    </div>
  );
}

function ReadonlyRating({ rating, comments, assessedAt, label }) {
  if (!rating) {
    return <p className="text-xs italic text-slate-400">No {label.toLowerCase()} rating yet.</p>;
  }
  return (
    <div className="space-y-1.5">
      <RatingStars value={rating} readonly />
      {comments && <p className="text-sm text-slate-600">{comments}</p>}
      {assessedAt && (
        <p className="text-[11px] text-slate-400">
          {label} rated on {new Date(assessedAt).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}

function Section({ title, icon, children }) {
  return (
    <div className="mb-5 rounded-xl border border-slate-100 p-4">
      <p className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
        {icon && <span className="mr-1">{icon}</span>}{title}
      </p>
      {children}
    </div>
  );
}

// ── Mid vs End Comparison helpers ────────────────────────────────────────────

const DERIVED_LABEL = { 1: 'Below Exp', 2: 'Needs Improvement', 3: 'Meets Exp', 4: 'Exceeds Exp', 5: 'Outstanding' };

function VariancePill({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const v = Number(value);
  const color = v > 0
    ? 'bg-emerald-50 text-emerald-700'
    : v < 0
    ? 'bg-red-50 text-red-700'
    : 'bg-slate-50 text-slate-500';
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${color}`}>
      {v > 0 ? `+${v}` : v}
    </span>
  );
}

function MidVsEndComparison({ rows, eca }) {
  const hasMidData = rows.some((r) => r.achievement_pct != null);
  const goalRows   = rows.filter((r) => r.row_type === 'kra' || r.row_type === 'kpi' || !r.row_type);
  const compRows   = rows.filter((r) => r.row_type === 'competency');

  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-xl border border-slate-100 p-6 text-center">
        <p className="text-sm italic text-slate-400">No comparison data available.</p>
        <p className="mt-1 text-xs text-slate-400">Complete mid-cycle and end-cycle assessments to see the comparison.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Achievement % = Σ(KPI achieved weight) ÷ Σ(KPI assigned weight) × 100.
        Mid Rating derived from Achievement %: 0–20%→1, 21–40%→2, 41–60%→3, 61–80%→4, 81–100%→5.
        Variance (Goals) = End Manager Rating − Mid Rating. Variance (Competency) = Manager − Self.
      </p>

      {/* ── Overall Assessment Summary ── */}
      <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-indigo-500">Overall Assessment</p>
        <div className="flex flex-wrap gap-8">
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Self Rating</p>
            {eca.self_rating
              ? <RatingStars value={eca.self_rating} readonly />
              : <p className="text-xs italic text-slate-400">Not rated</p>}
          </div>
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Manager Rating</p>
            {eca.manager_rating
              ? <RatingStars value={eca.manager_rating} readonly />
              : <p className="text-xs italic text-slate-400">Not rated</p>}
          </div>
          {eca.self_rating != null && eca.manager_rating != null && (
            <div className="flex flex-col justify-center">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Mgr vs Self</p>
              <VariancePill value={Number((eca.manager_rating - eca.self_rating).toFixed(2))} />
            </div>
          )}
        </div>
      </div>

      {/* ── Goal Ratings (KRAs + KPIs) ── */}
      {goalRows.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Goal Ratings (KRAs &amp; KPIs)</p>
          {!hasMidData && (
            <p className="mb-2 text-[11px] italic text-amber-600">No mid-cycle progress recorded — mid-cycle columns show —</p>
          )}
          <div className="overflow-x-auto rounded-xl border border-slate-100">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="px-3 py-2 text-left">KRA / KPI</th>
                  <th className="px-3 py-2 text-right">Assigned Wt</th>
                  <th className="px-3 py-2 text-right">Achieved Wt</th>
                  <th className="px-3 py-2 text-right">Achievement %</th>
                  <th className="px-3 py-2 text-right">Mid Rating</th>
                  <th className="px-3 py-2 text-right">End Self</th>
                  <th className="px-3 py-2 text-right">End Manager</th>
                  <th className="px-3 py-2 text-center">Variance</th>
                </tr>
              </thead>
              <tbody>
                {goalRows.map((row, i) => {
                  const isKRA = row.row_type === 'kra' || !row.row_type;
                  const displayName = isKRA ? row.kra_title : row.kpi_title;
                  const key = isKRA
                    ? `kra-${row.kra_id}`
                    : `kpi-${row.kpi_id ?? i}`;
                  return (
                    <tr key={key}
                      className={`border-b border-slate-50 ${isKRA ? 'bg-slate-50' : 'bg-white'}`}>
                      <td className={`max-w-[200px] px-3 py-2 ${isKRA ? 'font-semibold text-slate-800' : 'pl-7 text-slate-600'}`}>
                        <span className="block truncate" title={displayName}>{displayName}</span>
                        {!isKRA && (
                          <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">KPI</span>
                        )}
                      </td>
                      {/* Assigned Weight */}
                      <td className="px-3 py-2 text-right text-slate-500">
                        {row.weightage != null ? `${row.weightage}%` : '—'}
                      </td>
                      {/* Achieved Weight (= Σ KPI progress for KRA, individual for KPI) */}
                      <td className="px-3 py-2 text-right">
                        {row.achieved_weight != null
                          ? <span className="font-semibold text-teal-700">{Number(row.achieved_weight).toFixed(1)}%</span>
                          : <span className="text-slate-400">—</span>}
                      </td>
                      {/* Achievement % = achieved / assigned × 100 */}
                      <td className="px-3 py-2 text-right">
                        {row.achievement_pct != null
                          ? <span className="font-semibold text-indigo-700">{row.achievement_pct}%</span>
                          : <span className="text-slate-400">—</span>}
                      </td>
                      {/* Mid Rating derived from Achievement % */}
                      <td className="px-3 py-2 text-right">
                        {row.derived_mid_rating != null
                          ? <span title={DERIVED_LABEL[row.derived_mid_rating]} className="font-semibold text-indigo-600">
                              {row.derived_mid_rating}
                              <span className="ml-1 text-[10px] font-normal text-slate-400">({DERIVED_LABEL[row.derived_mid_rating]})</span>
                            </span>
                          : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.end_self_rating != null
                          ? <span className="font-semibold text-blue-600">{Number(row.end_self_rating).toFixed(1)}</span>
                          : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.end_manager_rating != null
                          ? <span className="font-semibold text-amber-600">{Number(row.end_manager_rating).toFixed(1)}</span>
                          : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <VariancePill value={row.variance} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Competencies ── */}
      {compRows.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Competencies</p>
          <div className="overflow-x-auto rounded-xl border border-slate-100">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="px-3 py-2 text-left">Competency</th>
                  <th className="px-3 py-2 text-right">Weight</th>
                  <th className="px-3 py-2 text-right">End Self</th>
                  <th className="px-3 py-2 text-right">End Manager</th>
                  <th className="px-3 py-2 text-center">Variance (Mgr − Self)</th>
                </tr>
              </thead>
              <tbody>
                {compRows.map((row, i) => (
                  <tr key={`comp-${i}`}
                    className={`border-b border-slate-50 ${i % 2 === 0 ? 'bg-white' : 'bg-violet-50/30'}`}>
                    <td className="max-w-[200px] px-3 py-2 font-medium text-slate-800">
                      <span className="mr-1.5 inline-block rounded bg-violet-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-violet-600">COMP</span>
                      <span className="truncate" title={row.kra_title}>{row.kra_title}</span>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500">
                      {row.weightage != null ? `${row.weightage}%` : '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {row.end_self_rating != null
                        ? <span className="font-semibold text-blue-600">{Number(row.end_self_rating).toFixed(1)}</span>
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {row.end_manager_rating != null
                        ? <span className="font-semibold text-amber-600">{Number(row.end_manager_rating).toFixed(1)}</span>
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <VariancePill value={row.variance} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Main Component ────────────────────────────────────────────────────────────

export default function EndCycleAssessmentDrawer({
  assessment: initialAssessment, assignment, viewerRole, onClose, onChanged
}) {
  const [eca, setEca]         = useState(initialAssessment);
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');
  const [activeTab, setActiveTab] = useState('overview');

  // Self-assessment state.
  const [selfRating, setSelfRating]     = useState(initialAssessment.self_rating || 0);
  const [selfComments, setSelfComments] = useState(initialAssessment.self_comments || '');
  const [kraRatings, setKraRatings]     = useState(() => {
    const m = {};
    (initialAssessment.kra_ratings || []).forEach((r) => {
      m[r.assigned_kra_id] = { self_rating: r.self_rating || 0, self_notes: r.self_notes || '' };
    });
    return m;
  });
  const [compRatings, setCompRatings] = useState(() => {
    const m = {};
    (initialAssessment.competency_ratings || []).forEach((r) => {
      m[r.assigned_competency_id] = { self_rating: r.self_rating || 0, self_notes: r.self_notes || '' };
    });
    return m;
  });

  // Manager assessment state.
  const [mgrRating, setMgrRating]       = useState(initialAssessment.manager_rating || 0);
  const [mgrComments, setMgrComments]   = useState(initialAssessment.manager_comments || '');
  const [mgrKraRatings, setMgrKraRatings] = useState(() => {
    const m = {};
    (initialAssessment.kra_ratings || []).forEach((r) => {
      m[r.assigned_kra_id] = { manager_rating: r.manager_rating || 0, manager_notes: r.manager_notes || '' };
    });
    return m;
  });
  const [mgrCompRatings, setMgrCompRatings] = useState(() => {
    const m = {};
    (initialAssessment.competency_ratings || []).forEach((r) => {
      m[r.assigned_competency_id] = { manager_rating: r.manager_rating || 0, manager_notes: r.manager_notes || '' };
    });
    return m;
  });

  // HR notes — saved independently without advancing the state machine.
  const [hrNotes, setHrNotes]         = useState(initialAssessment.hr_notes || '');
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesError, setNotesError]   = useState('');

  const isLocked   = eca.status === ECA_STATUS.LOCKED;
  const autoLocked = isAutoLocked(eca);
  const curIdx     = stepIndex(eca.status);

  const allKras  = useMemo(() => (assignment?.kras || []), [assignment]);
  const allComps = useMemo(() => (assignment?.competencies || []), [assignment]);

  // ── Action helpers ────────────────────────────────────────────────────────

  const act = async (fn, label) => {
    setBusy(true); setError('');
    try {
      const updated = await fn();
      setEca(updated);
      onChanged && onChanged();
    } catch (e) {
      setError(e?.data?.detail || e?.message || `${label} failed.`);
    } finally {
      setBusy(false);
    }
  };

  const handleSelfAssess = () => act(
    () => pmsApi.selfAssess(eca.id, {
      self_rating: selfRating,
      self_comments: selfComments || null,
      kra_ratings: allKras.map((kra) => ({
        assigned_kra_id: kra.id,
        self_rating: kraRatings[kra.id]?.self_rating || null,
        self_notes: kraRatings[kra.id]?.self_notes || null,
      })),
      competency_ratings: allComps.map((comp) => ({
        assigned_competency_id: comp.id,
        self_rating: compRatings[comp.id]?.self_rating || null,
        self_notes: compRatings[comp.id]?.self_notes || null,
      })),
    }),
    'Self-assessment'
  );

  const handleMgrAssess = () => act(
    () => pmsApi.managerAssess(eca.id, {
      manager_rating: mgrRating,
      manager_comments: mgrComments || null,
      kra_ratings: allKras.map((kra) => ({
        assigned_kra_id: kra.id,
        manager_rating: mgrKraRatings[kra.id]?.manager_rating || null,
        manager_notes: mgrKraRatings[kra.id]?.manager_notes || null,
      })),
      competency_ratings: allComps.map((comp) => ({
        assigned_competency_id: comp.id,
        manager_rating: mgrCompRatings[comp.id]?.manager_rating || null,
        manager_notes: mgrCompRatings[comp.id]?.manager_notes || null,
      })),
    }),
    'Manager assessment'
  );

  const handleSubmitToHR = () => act(
    () => pmsApi.submitAssessmentToHR(eca.id, { notes: null }),
    'Submit to HR'
  );

  const handleHrReceive = () => act(
    () => pmsApi.hrReceiveAssessment(eca.id, { notes: hrNotes || null }),
    'Receive'
  );

  const handleLock = () => act(
    () => pmsApi.lockAssessment(eca.id, { notes: hrNotes || null }),
    'Lock'
  );

  const handleUnlock = () => act(
    () => pmsApi.unlockAssessment(eca.id, {}),
    'Unlock'
  );

  // Save HR notes without triggering a state transition or closing the drawer.
  const handleSaveHrNotes = async () => {
    setNotesSaving(true); setNotesError('');
    try {
      const updated = await pmsApi.updateHrNotes(eca.id, hrNotes);
      setEca(updated);
    } catch (e) {
      setNotesError(e?.data?.detail || e?.message || 'Failed to save notes.');
    } finally {
      setNotesSaving(false);
    }
  };

  // ── Permission flags ──────────────────────────────────────────────────────

  const canSelfAssess  = viewerRole === 'employee' &&
    [ECA_STATUS.DRAFT, ECA_STATUS.SELF_ASSESSED].includes(eca.status);
  const canMgrAssess   = viewerRole === 'manager' &&
    [ECA_STATUS.SELF_ASSESSED, ECA_STATUS.MGR_ASSESSED].includes(eca.status);
  const canSubmitToHR  = viewerRole === 'manager' && eca.status === ECA_STATUS.MGR_ASSESSED;
  const canHrReceive   = viewerRole === 'hr' && eca.status === ECA_STATUS.SUBMITTED_TO_HR;
  const canLock        = viewerRole === 'hr' &&
    [ECA_STATUS.HR_RECEIVED, ECA_STATUS.SUBMITTED_TO_HR].includes(eca.status);
  const canUnlock      = viewerRole === 'hr' && eca.status === ECA_STATUS.LOCKED && !autoLocked;

  const modalTitle = `End-Cycle Assessment — ${eca.employee_name || ''}`;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Modal title={modalTitle} onClose={onClose} width="max-w-4xl">

      {/* ── Summary strip (matches GoalDetailDrawer header style) ── */}
      <div className="-mx-6 -mt-5 mb-6 border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white px-6 pb-5 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs text-slate-500">
              Manager: <span className="font-semibold text-slate-700">{eca.manager_name || '—'}</span>
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              Period: {eca.period || '—'} · Cycle: {eca.cycle_period || '—'}
            </p>
          </div>
          <StatusPill status={eca.status} />
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
                  active ? 'bg-indigo-600 text-white ring-2 ring-indigo-200' :
                           'bg-slate-100 text-slate-400'
                ].join(' ')}>
                  {done ? '✓' : i + 1}
                </span>
                <span className={[
                  'ml-1 hidden text-[9px] font-semibold sm:block',
                  active ? 'text-indigo-700' : done ? 'text-emerald-600' : 'text-slate-400'
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
              {autoLocked ? 'Auto-locked by system' : 'Assessment is locked.'}
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

      {/* ── Tabs ── */}
      <div className="mb-5 flex border-b border-slate-100">
        {['overview', 'kras', 'competencies', 'comparison'].map((t) => (
          <button key={t} type="button" onClick={() => setActiveTab(t)}
            className={`px-4 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${
              activeTab === t
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}>
            {t === 'overview' ? 'Overview'
              : t === 'kras' ? 'Goal Ratings'
              : t === 'competencies' ? 'Competencies'
              : 'Mid vs End'}
          </button>
        ))}
      </div>

      {/* ── Overview Tab ── */}
      {activeTab === 'overview' && (
        <div className="space-y-0">
          <Section title="Self Assessment" icon="👤">
            {canSelfAssess ? (
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Overall Self Rating *</label>
                  <RatingStars value={selfRating} onChange={setSelfRating} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Comments</label>
                  <textarea rows={3}
                    className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none"
                    placeholder="Share your self-assessment comments…"
                    value={selfComments} onChange={(e) => setSelfComments(e.target.value)} />
                </div>
              </div>
            ) : (
              <ReadonlyRating rating={eca.self_rating} comments={eca.self_comments}
                assessedAt={eca.self_assessed_at} label="Employee" />
            )}
          </Section>

          <Section title="Manager Assessment" icon="👔">
            {canMgrAssess ? (
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Overall Rating *</label>
                  <RatingStars value={mgrRating} onChange={setMgrRating} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Comments</label>
                  <textarea rows={3}
                    className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none"
                    placeholder="Assessment comments and feedback…"
                    value={mgrComments} onChange={(e) => setMgrComments(e.target.value)} />
                </div>
              </div>
            ) : (
              <ReadonlyRating rating={eca.manager_rating} comments={eca.manager_comments}
                assessedAt={eca.manager_assessed_at} label="Manager" />
            )}
          </Section>

          {(viewerRole === 'hr' || eca.hr_notes) && (
            <Section title="HR Notes" icon="📋">
              {viewerRole === 'hr' && !isLocked ? (
                <div className="space-y-2">
                  <textarea rows={3}
                    className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none"
                    placeholder="Enter HR notes… (click Save Notes to persist)"
                    value={hrNotes} onChange={(e) => setHrNotes(e.target.value)} />
                  {notesError && (
                    <p className="text-xs text-red-600">{notesError}</p>
                  )}
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={handleSaveHrNotes}
                      disabled={notesSaving || busy}
                      className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
                      {notesSaving ? 'Saving…' : 'Save Notes'}
                    </button>
                    {eca.hr_notes && (
                      <span className="text-[11px] text-slate-400">Last saved: {eca.hr_notes.slice(0, 40)}{eca.hr_notes.length > 40 ? '…' : ''}</span>
                    )}
                  </div>
                </div>
              ) : eca.hr_notes ? (
                <p className="text-sm text-slate-600">{eca.hr_notes}</p>
              ) : (
                <p className="text-xs italic text-slate-400">No HR notes yet.</p>
              )}
            </Section>
          )}
        </div>
      )}

      {/* ── Goal Ratings Tab ── */}
      {activeTab === 'kras' && (
        <div className="space-y-4">
          {allKras.length === 0 ? (
            <p className="text-sm italic text-slate-400">No KRAs in the goal sheet.</p>
          ) : allKras.map((kra) => {
            const ekr     = eca.kra_ratings?.find((r) => r.assigned_kra_id === kra.id);
            const myEdit  = kraRatings[kra.id] || { self_rating: 0, self_notes: '' };
            const mgrEdit = mgrKraRatings[kra.id] || { manager_rating: 0, manager_notes: '' };
            return (
              <div key={kra.id} className="rounded-xl border border-slate-100 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{kra.title}</p>
                  <span className="text-[11px] font-semibold text-slate-400">{kra.weightage}%</span>
                </div>
                {kra.description && <p className="mt-0.5 text-xs text-slate-400">{kra.description}</p>}

                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Self</p>
                    {canSelfAssess ? (
                      <>
                        <RatingStars value={myEdit.self_rating}
                          onChange={(v) => setKraRatings((p) => ({ ...p, [kra.id]: { ...p[kra.id], self_rating: v } }))} />
                        <input className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          placeholder="Notes…" value={myEdit.self_notes}
                          onChange={(e) => setKraRatings((p) => ({ ...p, [kra.id]: { ...p[kra.id], self_notes: e.target.value } }))} />
                      </>
                    ) : (
                      <>
                        <RatingStars value={ekr?.self_rating} readonly />
                        {ekr?.self_notes && <p className="mt-1 text-xs text-slate-500">{ekr.self_notes}</p>}
                      </>
                    )}
                  </div>
                  <div>
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Manager</p>
                    {canMgrAssess ? (
                      <>
                        <RatingStars value={mgrEdit.manager_rating}
                          onChange={(v) => setMgrKraRatings((p) => ({ ...p, [kra.id]: { ...p[kra.id], manager_rating: v } }))} />
                        <input className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          placeholder="Notes…" value={mgrEdit.manager_notes}
                          onChange={(e) => setMgrKraRatings((p) => ({ ...p, [kra.id]: { ...p[kra.id], manager_notes: e.target.value } }))} />
                      </>
                    ) : (
                      <>
                        <RatingStars value={ekr?.manager_rating} readonly />
                        {ekr?.manager_notes && <p className="mt-1 text-xs text-slate-500">{ekr.manager_notes}</p>}
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Competency Ratings Tab ── */}
      {activeTab === 'competencies' && (
        <div className="space-y-4">
          {allComps.length === 0 ? (
            <p className="text-sm italic text-slate-400">No competencies in the goal sheet.</p>
          ) : allComps.map((comp) => {
            const ecr     = eca.competency_ratings?.find((r) => r.assigned_competency_id === comp.id);
            const myEdit  = compRatings[comp.id] || { self_rating: 0, self_notes: '' };
            const mgrEdit = mgrCompRatings[comp.id] || { manager_rating: 0, manager_notes: '' };
            return (
              <div key={comp.id} className="rounded-xl border border-slate-100 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-800">{comp.title}</p>
                  <span className="text-[11px] font-semibold text-slate-400">{comp.weightage}%</span>
                </div>
                {comp.description && <p className="mt-0.5 text-xs text-slate-400">{comp.description}</p>}

                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Self</p>
                    {canSelfAssess ? (
                      <>
                        <RatingStars value={myEdit.self_rating}
                          onChange={(v) => setCompRatings((p) => ({ ...p, [comp.id]: { ...p[comp.id], self_rating: v } }))} />
                        <input className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          placeholder="Notes…" value={myEdit.self_notes}
                          onChange={(e) => setCompRatings((p) => ({ ...p, [comp.id]: { ...p[comp.id], self_notes: e.target.value } }))} />
                      </>
                    ) : (
                      <>
                        <RatingStars value={ecr?.self_rating} readonly />
                        {ecr?.self_notes && <p className="mt-1 text-xs text-slate-500">{ecr.self_notes}</p>}
                      </>
                    )}
                  </div>
                  <div>
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Manager</p>
                    {canMgrAssess ? (
                      <>
                        <RatingStars value={mgrEdit.manager_rating}
                          onChange={(v) => setMgrCompRatings((p) => ({ ...p, [comp.id]: { ...p[comp.id], manager_rating: v } }))} />
                        <input className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          placeholder="Notes…" value={mgrEdit.manager_notes}
                          onChange={(e) => setMgrCompRatings((p) => ({ ...p, [comp.id]: { ...p[comp.id], manager_notes: e.target.value } }))} />
                      </>
                    ) : (
                      <>
                        <RatingStars value={ecr?.manager_rating} readonly />
                        {ecr?.manager_notes && <p className="mt-1 text-xs text-slate-500">{ecr.manager_notes}</p>}
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Mid vs End Comparison Tab ── */}
      {activeTab === 'comparison' && (
        <MidVsEndComparison rows={eca.mid_cycle_comparison || []} eca={eca} />
      )}

      {/* ── Action buttons (inline at bottom, matches GoalDetailDrawer pattern) ── */}
      <div className="-mx-6 -mb-5 mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <button type="button" onClick={onClose}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          Close
        </button>

        <div className="flex flex-wrap items-center gap-2">
          {canSelfAssess && (
            <button type="button" onClick={handleSelfAssess} disabled={busy || !selfRating}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
              {busy ? 'Saving…' : 'Submit Self Assessment'}
            </button>
          )}
          {canMgrAssess && (
            <button type="button" onClick={handleMgrAssess} disabled={busy || !mgrRating}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
              {busy ? 'Saving…' : 'Save Assessment'}
            </button>
          )}
          {canSubmitToHR && (
            <button type="button" onClick={handleSubmitToHR} disabled={busy}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
              {busy ? 'Submitting…' : 'Submit to HR'}
            </button>
          )}
          {canHrReceive && (
            <button type="button" onClick={handleHrReceive} disabled={busy}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
              {busy ? 'Processing…' : 'Mark Received'}
            </button>
          )}
          {canLock && (
            <button type="button" onClick={handleLock} disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
              </svg>
              {busy ? 'Locking…' : 'Lock Assessment'}
            </button>
          )}
          {canUnlock && (
            <button type="button" onClick={handleUnlock} disabled={busy}
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-50">
              {busy ? 'Unlocking…' : 'Unlock'}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
