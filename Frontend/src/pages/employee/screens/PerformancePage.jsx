import { useEffect, useMemo, useState } from 'react';
import Toast from '../../../components/Timesheets/Toast';
import {
  pmsApi,
  PMS_STATUS, PMS_STATUS_LABEL, MCR_STATUS, MCR_STATUS_LABEL, MCR_STATUS_TONE,
  ECA_STATUS, ECA_STATUS_LABEL, ECA_STATUS_TONE,
} from '../../../services/pms';
import { PageTitle, Card, Pill, StatCard } from '../parts/UI';
import GoalDetailDrawer from '../../admin/performance/GoalDetailDrawer';
import MidCycleReviewDrawer from '../../admin/performance/MidCycleReviewDrawer';
import EndCycleAssessmentDrawer from '../../admin/performance/EndCycleAssessmentDrawer';

// Employee PMS hub. Uses the shared dashboard atoms (PageTitle/Card/Pill)
// + the teal accent (#14b8a6) so it matches the rest of the employee shell.

const TABS = [
  { id: 'my',           label: 'My Goals',            hint: 'All goals assigned to you' },
  { id: 'mid-cycle',    label: 'Mid-Cycle Review',    hint: 'Update progress and submit for manager review' },
  { id: 'end-cycle',    label: 'End Cycle Assessment', hint: 'Complete your self-assessment and view ratings' },
  { id: 'compensation', label: 'My Compensation',     hint: 'View your revision letter and acknowledge' },
];

const STATUS_TONE_TW = {
  draft:              'slate',
  goals_sent:         'blue',
  under_discussion:   'amber',
  employee_confirmed: 'violet',
  manager_approved:   'green',
  hr_reviewed:        'teal',
  goals_locked:       'rose',
};

function StatusChip({ status }) {
  return <Pill tone={STATUS_TONE_TW[status] || 'slate'}>{PMS_STATUS_LABEL[status] || status}</Pill>;
}

const PerformancePage = () => {
  const [tab, setTab] = useState('my');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(null);

  // Phase 2: mid-cycle reviews.
  const [mcrRows, setMcrRows]     = useState([]);
  const [mcrLoading, setMcrLoading] = useState(false);
  const [mcrDrawer, setMcrDrawer] = useState(null);   // { review, assignment }

  const load = () => {
    setLoading(true);
    pmsApi.assignments({ scope: 'employee' })
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };

  const loadMcr = () => {
    setMcrLoading(true);
    pmsApi.midCycleReviews({ scope: 'employee' })
      .then((d) => setMcrRows(Array.isArray(d) ? d : []))
      .catch(() => setMcrRows([]))
      .finally(() => setMcrLoading(false));
  };

  // Phase 3: end-cycle assessments.
  const [ecaRows, setEcaRows]         = useState([]);
  const [ecaLoading, setEcaLoading]   = useState(false);
  const [ecaDrawer, setEcaDrawer]     = useState(null);

  const loadEca = () => {
    setEcaLoading(true);
    pmsApi.assessments({ scope: 'employee' })
      .then((d) => setEcaRows(Array.isArray(d) ? d : []))
      .catch(() => setEcaRows([]))
      .finally(() => setEcaLoading(false));
  };

  // Phase 5: compensation revisions.
  const [compRows, setCompRows]       = useState([]);
  const [compLoading, setCompLoading] = useState(false);

  // Toast + confirm state (replaces browser alert/confirm).
  const [pageToast, setPageToast] = useState(null);
  const [pendingAck, setPendingAck] = useState(null);
  const showToast = (msg, type = 'success') => setPageToast({ msg, type });

  const loadComp = () => {
    setCompLoading(true);
    pmsApi.revisions({})
      .then((d) => setCompRows(Array.isArray(d) ? d : []))
      .catch(() => setCompRows([]))
      .finally(() => setCompLoading(false));
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (tab === 'mid-cycle') loadMcr(); }, [tab]);
  useEffect(() => { if (tab === 'end-cycle') loadEca(); }, [tab]);
  useEffect(() => { if (tab === 'compensation') loadComp(); }, [tab]);

  const counts = useMemo(() => ({
    total:      rows.length,
    locked:     rows.filter((r) => r.status === PMS_STATUS.GOALS_LOCKED).length,
    mcrPending: mcrRows.filter((r) => [MCR_STATUS.DRAFT, MCR_STATUS.IN_PROGRESS].includes(r.status)).length,
  }), [rows, mcrRows]);

  // Only 'my' tab uses the goals list; mid-cycle, end-cycle, compensation have their own data.
  const filtered = useMemo(() => rows, [rows]);

  const tabHint = TABS.find((t) => t.id === tab)?.hint;

  return (
    <div className="space-y-5">
      <PageTitle
        title="Performance"
        sub="Review your goals, discuss with your manager, and accept the final goal sheet."
      />

      {/* Stat strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard
          label="Total Goal Sheets"
          value={counts.total}
          sub={counts.total ? 'Across all cycles' : 'Nothing yet'}
          iconBg="#f0fdfa"
          icon={
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
          }
        />
        <StatCard
          label="Locked"
          value={counts.locked}
          sub={counts.locked ? 'Finalised by HR' : 'None locked'}
          subColor="#e11d48"
          iconBg="#fee2e2"
          icon={
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#e11d48" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
          }
        />
        <StatCard
          label="MCR Pending"
          value={counts.mcrPending}
          sub={counts.mcrPending ? 'Update progress' : 'All up to date'}
          subColor="#2563eb"
          iconBg="#dbeafe"
          icon={
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          }
        />
      </div>

      {/* Tabs */}
      <Card padding="p-0">
        <div className="flex flex-wrap gap-1 border-b border-slate-100 px-5 pt-4">
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={
                  'px-4 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ' +
                  (active
                    ? 'text-teal-600 border-teal-500'
                    : 'text-slate-500 border-transparent hover:text-slate-700')
                }
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <p className="px-5 pt-3 text-[11px] text-slate-400">{tabHint}</p>

        <div className="space-y-3 p-5">
          {tab === 'my' && loading && <SkeletonList />}
          {tab === 'my' && !loading && filtered.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-teal-50 text-teal-600">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
              </div>
              <h3 className="text-sm font-semibold text-slate-800">No goal sheets yet</h3>
              <p className="mt-1 text-xs text-slate-500">Your goal sheets will appear here once HR sends them.</p>
            </div>
          )}
          {/* Mid-Cycle tab content */}
          {tab === 'mid-cycle' && (
            <>
              {mcrLoading && <SkeletonList />}
              {!mcrLoading && mcrRows.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                  </div>
                  <h3 className="text-sm font-semibold text-slate-800">No Mid-Cycle Reviews</h3>
                  <p className="mt-1 text-xs text-slate-500">HR will open your mid-cycle review when the time comes.</p>
                </div>
              )}
              {!mcrLoading && mcrRows.map((mcr) => {
                const tone = MCR_STATUS_TONE[mcr.status] || { bg: '#F1F5F9', fg: '#475569' };
                const needsAction = [MCR_STATUS.DRAFT, MCR_STATUS.IN_PROGRESS].includes(mcr.status);
                const assignment  = rows.find((a) => a.id === mcr.assignment_id);
                return (
                  <div key={mcr.id}
                    onClick={() => setMcrDrawer({ review: mcr, assignment })}
                    className="group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-blue-200 hover:bg-blue-50/20">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-800">
                            {mcr.cycle_period || 'Mid-Cycle Review'}
                          </h4>
                          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                            style={{ backgroundColor: tone.bg, color: tone.fg }}>
                            {MCR_STATUS_LABEL[mcr.status] || mcr.status}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-400">
                          Period: <span className="font-semibold text-slate-600">{mcr.period || '—'}</span>
                          {mcr.submitted_at && <> · submitted {new Date(mcr.submitted_at).toLocaleDateString()}</>}
                        </p>
                      </div>
                      {needsAction && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-700">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                          Update needed
                        </span>
                      )}
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-[11px] text-slate-500">
                        {mcr.status === MCR_STATUS.LOCKED ? '🔒 Locked' :
                         needsAction ? 'Update your KPI progress' : 'View review'}
                      </p>
                      <button type="button"
                        onClick={(e) => { e.stopPropagation(); setMcrDrawer({ review: mcr, assignment }); }}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-600">
                        {needsAction ? 'Update Progress' : 'Open'}
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Phase 3: End Cycle Assessment */}
          {tab === 'end-cycle' && (
            <>
              {ecaLoading && <SkeletonList />}
              {!ecaLoading && ecaRows.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
                  <h3 className="text-sm font-semibold text-slate-800">No End-Cycle Assessments</h3>
                  <p className="mt-1 text-xs text-slate-500">HR will open your end-cycle assessment when the time comes.</p>
                </div>
              )}
              {!ecaLoading && ecaRows.map((eca) => {
                const tone = ECA_STATUS_TONE[eca.status] || { bg: '#F1F5F9', fg: '#475569' };
                const needsAction = [ECA_STATUS.DRAFT, ECA_STATUS.SELF_ASSESSED].includes(eca.status);
                const assignment = rows.find((a) => a.id === eca.assignment_id);
                return (
                  <div key={eca.id}
                    onClick={() => setEcaDrawer({ assessment: eca, assignment })}
                    className="group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-indigo-200 hover:bg-indigo-50/20">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-800">{eca.cycle_period || 'End-Cycle Assessment'}</h4>
                          <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                            style={{ backgroundColor: tone.bg, color: tone.fg }}>
                            {ECA_STATUS_LABEL[eca.status] || eca.status}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-400">Period: {eca.period || '—'}</p>
                      </div>
                      <div className="text-right">
                        {eca.self_rating && <p className="text-xs font-semibold text-amber-600">Self: {eca.self_rating.toFixed(1)} ★</p>}
                        {eca.manager_rating && <p className="text-xs font-semibold text-indigo-600">Manager: {eca.manager_rating.toFixed(1)} ★</p>}
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-[11px] text-slate-500">
                        {needsAction ? '✏ Complete your self-assessment' : 'View assessment'}
                      </p>
                      <button type="button"
                        onClick={(e) => { e.stopPropagation(); setEcaDrawer({ assessment: eca, assignment }); }}
                        className="inline-flex items-center gap-1 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-600">
                        {needsAction ? 'Assess' : 'Open'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Phase 5: My Compensation */}
          {tab === 'compensation' && (
            <>
              {compLoading && <SkeletonList />}
              {!compLoading && compRows.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
                  <h3 className="text-sm font-semibold text-slate-800">No Compensation Revisions</h3>
                  <p className="mt-1 text-xs text-slate-500">Your compensation revision letter will appear here once generated by HR.</p>
                </div>
              )}
              {!compLoading && compRows.map((rev) => (
                <div key={rev.id} className="rounded-xl border border-slate-100 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-slate-800">Compensation Revision</p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        Effective: {rev.effective_from ? new Date(rev.effective_from).toLocaleDateString() : '—'}
                      </p>
                    </div>
                    {rev.employee_acknowledged_at ? (
                      <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                        ✓ Acknowledged
                      </span>
                    ) : rev.letter_generated_at ? (
                      <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                        Pending Acknowledgement
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                    <div className="text-center">
                      <p className="text-xs text-slate-400">Previous CTC</p>
                      <p className="text-sm font-bold text-slate-600">₹{rev.old_ctc ? rev.old_ctc.toLocaleString('en-IN') : '—'}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-slate-400">Revised CTC</p>
                      <p className="text-sm font-bold text-emerald-600">₹{rev.new_ctc ? rev.new_ctc.toLocaleString('en-IN') : '—'}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs text-slate-400">Hike</p>
                      <p className="text-sm font-bold text-amber-600">{rev.hike_percent != null ? `${rev.hike_percent.toFixed(1)}%` : '—'}</p>
                    </div>
                  </div>
                  {!rev.employee_acknowledged_at && rev.letter_generated_at && (
                    <div className="mt-3 border-t border-slate-100 pt-3">
                      <button type="button"
                        onClick={() => setPendingAck(rev.id)}
                        className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700">
                        Acknowledge Revision
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </>
          )}

          {/* My Goals tab content */}
          {tab === 'my' && !loading && filtered.map((a) => {
            const kraCount = (a.kras || []).length;
            const kpiCount = (a.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0);
            const compCount = (a.competencies || []).length;
            const needsAction = [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION].includes(a.status);
            return (
              <div
                key={a.id}
                onClick={() => setDrawer(a)}
                className="group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-teal-200 hover:bg-teal-50/30"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-slate-800">
                        {a.period || 'Goal Sheet'}
                      </h4>
                      <StatusChip status={a.status} />
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400">
                      Manager: <span className="font-semibold text-slate-600">{a.manager_name || '—'}</span>
                      {a.sent_at && <> · sent {new Date(a.sent_at).toLocaleDateString()}</>}
                    </p>
                  </div>
                  {needsAction && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-700">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                      Action needed
                    </span>
                  )}
                </div>

                <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                  <MiniStat value={kraCount}  label="KRAs"  color="#3b82f6" />
                  <MiniStat value={kpiCount}  label="KPIs"  color="#8b5cf6" />
                  <MiniStat value={compCount} label="Comp." color="#14b8a6" />
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                  <p className="text-[11px] text-slate-500">
                    {a.status === PMS_STATUS.GOALS_LOCKED
                      ? '🔒 Locked — view only'
                      : needsAction
                        ? 'Review and accept the goals'
                        : 'View progress'}
                  </p>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setDrawer(a); }}
                    className="inline-flex items-center gap-1 rounded-lg bg-teal-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-teal-600 group-hover:bg-teal-600"
                  >
                    {needsAction ? 'Review' : 'Open'}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {drawer && (
        <GoalDetailDrawer
          assignment={drawer}
          viewerRole="employee"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}

      {mcrDrawer && (
        <MidCycleReviewDrawer
          review={mcrDrawer.review}
          assignment={mcrDrawer.assignment}
          viewerRole="employee"
          onClose={() => setMcrDrawer(null)}
          onChanged={() => { loadMcr(); setMcrDrawer(null); }}
        />
      )}

      {ecaDrawer && (
        <EndCycleAssessmentDrawer
          assessment={ecaDrawer.assessment}
          assignment={ecaDrawer.assignment}
          viewerRole="employee"
          onClose={() => setEcaDrawer(null)}
          onChanged={() => { loadEca(); setEcaDrawer(null); }}
        />
      )}

      {pageToast && (
        <Toast message={pageToast.msg} type={pageToast.type} onClose={() => setPageToast(null)} />
      )}

      {pendingAck && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
            <p className="text-sm font-semibold text-slate-800">Acknowledge your compensation revision?</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setPendingAck(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50">
                Cancel
              </button>
              <button type="button"
                onClick={async () => {
                  const id = pendingAck;
                  setPendingAck(null);
                  try {
                    await pmsApi.acknowledgeRevision(id);
                    loadComp();
                  } catch (e) { showToast(e?.message || 'Failed.', 'error'); }
                }}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700">
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};


function MiniStat({ value, label, color }) {
  return (
    <div className="text-center">
      <div className="text-base font-bold" style={{ color }}>{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-28 animate-pulse rounded-xl bg-slate-100" />
      ))}
    </div>
  );
}

export default PerformancePage;
