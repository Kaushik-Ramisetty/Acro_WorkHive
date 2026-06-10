import { useEffect, useMemo, useState } from 'react';
import {
  pmsApi,
  PMS_STATUS, PMS_STATUS_LABEL, MCR_STATUS, MCR_STATUS_LABEL, MCR_STATUS_TONE,
  ECA_STATUS, ECA_STATUS_LABEL, ECA_STATUS_TONE,
  isAutoLocked,
} from '../../services/pms';
import GoalDetailDrawer from '../admin/performance/GoalDetailDrawer';
import MidCycleReviewDrawer from '../admin/performance/MidCycleReviewDrawer';
import EndCycleAssessmentDrawer from '../admin/performance/EndCycleAssessmentDrawer';

// ── Shared status pill ──────────────────────────────────────────────────────

const STATUS_TONE = {
  draft:              'bg-slate-100 text-slate-600',
  goals_sent:         'bg-blue-50 text-blue-700',
  under_discussion:   'bg-amber-50 text-amber-700',
  employee_confirmed: 'bg-indigo-50 text-indigo-700',
  manager_approved:   'bg-emerald-50 text-emerald-700',
  hr_reviewed:        'bg-cyan-50 text-cyan-700',
  goals_locked:       'bg-rose-50 text-rose-700',
};

function StatusChip({ status }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_TONE[status] || 'bg-slate-100 text-slate-600'}`}>
      {PMS_STATUS_LABEL[status] || status}
    </span>
  );
}

function Avatar({ name, size = 36 }) {
  const initials = (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
  const hash = [...initials].reduce((n, ch) => n + ch.charCodeAt(0), 0);
  const palette = [
    'from-blue-500 to-indigo-500',
    'from-emerald-500 to-teal-500',
    'from-amber-500 to-orange-500',
    'from-rose-500 to-pink-500',
    'from-violet-500 to-purple-500',
    'from-cyan-500 to-sky-500',
  ];
  const grad = palette[hash % palette.length];
  return (
    <div
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${grad} font-semibold text-white shadow-sm`}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.34) }}
    >
      {initials}
    </div>
  );
}

const TABS = [
  { id: 'my-goals',  label: 'My Goals',          hint: 'Goals assigned directly to you' },
  { id: 'team',      label: 'Team Goal Sheets',   hint: "Review and manage your team's goal sheets" },
  { id: 'pending',   label: 'Action Required',   hint: 'Goals awaiting your discussion or approval' },
  { id: 'mid-cycle', label: 'Mid-Cycle Reviews',  hint: 'Review and approve mid-cycle progress' },
  { id: 'end-cycle', label: 'End Cycle',          hint: 'Rate your team members and submit to HR' },
];

export default function ManagerPerformancePage() {
  const [tab, setTab] = useState('team');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(null);

  // Phase 2: mid-cycle reviews.
  const [mcrRows, setMcrRows]     = useState([]);
  const [mcrLoading, setMcrLoading] = useState(false);
  const [mcrDrawer, setMcrDrawer] = useState(null);

  // Phase 3: end-cycle assessments.
  const [ecaRows, setEcaRows]     = useState([]);
  const [ecaLoading, setEcaLoading] = useState(false);
  const [ecaDrawer, setEcaDrawer] = useState(null);

  // My Goals: goals assigned directly to this manager as an employee.
  const [myRows, setMyRows]       = useState([]);
  const [myLoading, setMyLoading] = useState(false);
  const [myDrawer, setMyDrawer]   = useState(null);

  const load = () => {
    setLoading(true);
    pmsApi.assignments({ scope: 'manager' })
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };

  const loadMcr = () => {
    setMcrLoading(true);
    pmsApi.midCycleReviews({ scope: 'manager' })
      .then((d) => setMcrRows(Array.isArray(d) ? d : []))
      .catch(() => setMcrRows([]))
      .finally(() => setMcrLoading(false));
  };

  const loadEca = () => {
    setEcaLoading(true);
    pmsApi.assessments({ scope: 'manager' })
      .then((d) => setEcaRows(Array.isArray(d) ? d : []))
      .catch(() => setEcaRows([]))
      .finally(() => setEcaLoading(false));
  };

  const loadMyGoals = () => {
    setMyLoading(true);
    pmsApi.assignments({ scope: 'employee' })
      .then((d) => setMyRows(Array.isArray(d) ? d : []))
      .catch(() => setMyRows([]))
      .finally(() => setMyLoading(false));
  };

  useEffect(() => { load(); loadMyGoals(); }, []);
  useEffect(() => { if (tab === 'mid-cycle') loadMcr(); }, [tab]);
  useEffect(() => { if (tab === 'end-cycle') loadEca(); }, [tab]);

  const pending = useMemo(() =>
    rows.filter((r) => [
      PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION, PMS_STATUS.EMPLOYEE_CONFIRMED
    ].includes(r.status)),
  [rows]);

  const filtered = useMemo(() => {
    if (tab === 'team') return rows;
    if (tab === 'pending') return pending;
    return rows;
  }, [rows, tab, pending]);

  const tabHint = TABS.find((t) => t.id === tab)?.hint;

  return (
    <div className="space-y-5">
      {/* Stats strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="My Goals"    value={myRows.length}              icon="🎯" accent="#7c3aed" />
        <StatCard label="Team Goal Sheets"  value={rows.length}           icon="📊" />
        <StatCard label="Action Required" value={pending.length}         icon="⚡" accent="#d97706" />
        <StatCard label="Approved"    value={rows.filter((r) => r.status === PMS_STATUS.MANAGER_APPROVED).length} icon="✅" accent="#059669" />
        <StatCard label="Locked"      value={rows.filter((r) => r.status === PMS_STATUS.GOALS_LOCKED).length}    icon="🔒" accent="#dc2626" />
      </div>

      {/* Tabs */}
      <div className="rounded-xl border border-slate-100 bg-white shadow-sm">
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
                    ? 'text-blue-700 border-blue-600'
                    : 'text-slate-500 border-transparent hover:text-slate-700')
                }
              >
                {t.label}
                {t.id === 'pending' && pending.length > 0 && (
                  <span className="ml-1.5 inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold text-amber-700">
                    {pending.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <p className="px-5 pt-3 text-[11px] text-slate-400">{tabHint}</p>

        <div className="p-5">
          {/* My Goals tab */}
          {tab === 'my-goals' && (
            <>
              {myLoading && <SkeletonList />}
              {!myLoading && myRows.length === 0 && (
                <EmptyState title="No goals assigned to you" description="Goals assigned to you by HR will appear here." />
              )}
              {!myLoading && myRows.map((a) => {
                const kraCount = (a.kras || []).length;
                const kpiCount = (a.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0);
                return (
                  <div
                    key={a.id}
                    onClick={() => setMyDrawer(a)}
                    className="mb-3 group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-violet-200 hover:bg-violet-50/20"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar name={a.employee_name} size={36} />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-800">{a.employee_name}</p>
                          <p className="text-[11px] text-slate-400">
                            {a.manager_name ? `Manager: ${a.manager_name}` : (a.period || 'No period')}
                          </p>
                        </div>
                      </div>
                      <StatusChip status={a.status} />
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                      <MiniStat value={kraCount} label="KRAs" color="#7c3aed" />
                      <MiniStat value={kpiCount} label="KPIs" color="#8b5cf6" />
                      <MiniStat value={(a.competencies || []).length} label="Comp." color="#10b981" />
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-[11px] text-slate-500">{a.period || 'No period'}</p>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setMyDrawer(a); }}
                        className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-violet-700"
                      >
                        Open
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Mid-Cycle tab */}
          {tab === 'mid-cycle' && (
            <>
              {mcrLoading && <SkeletonList />}
              {!mcrLoading && mcrRows.length === 0 && (
                <EmptyState title="No mid-cycle reviews" description="Mid-cycle reviews for your team will appear here." />
              )}
              {!mcrLoading && mcrRows.map((mcr) => {
                const tone = MCR_STATUS_TONE[mcr.status] || { bg: '#F1F5F9', fg: '#475569' };
                const needsAction = mcr.status === MCR_STATUS.SUBMITTED;
                const autoLock = isAutoLocked(mcr);
                const assignment = rows.find((a) => a.id === mcr.assignment_id);
                return (
                  <div key={mcr.id}
                    onClick={() => setMcrDrawer({ review: mcr, assignment })}
                    className="mb-3 group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-blue-200 hover:bg-blue-50/20">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar name={mcr.employee_name} size={36} />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-800">{mcr.employee_name}</p>
                          <p className="text-[11px] text-slate-400">
                            {mcr.cycle_period || 'Mid-Cycle'} · {mcr.period || '—'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {autoLock && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                          </span>
                        )}
                        <span className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold"
                          style={{ backgroundColor: tone.bg, color: tone.fg }}>
                          {MCR_STATUS_LABEL[mcr.status] || mcr.status}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-[11px] text-slate-500">
                        {autoLock ? 'Auto-locked — read only' : needsAction ? 'Awaiting your review' : 'View details'}
                      </p>
                      <button type="button"
                        onClick={(e) => { e.stopPropagation(); setMcrDrawer({ review: mcr, assignment }); }}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700">
                        Open
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
                <EmptyState title="No end-cycle assessments" description="End-cycle assessments for your team will appear here." />
              )}
              {!ecaLoading && ecaRows.map((eca) => {
                const tone = ECA_STATUS_TONE[eca.status] || { bg: '#F1F5F9', fg: '#475569' };
                const needsAction = [ECA_STATUS.SELF_ASSESSED, ECA_STATUS.MGR_ASSESSED].includes(eca.status);
                const autoLock = isAutoLocked(eca);
                const assignment = rows.find((a) => a.id === eca.assignment_id);
                return (
                  <div key={eca.id}
                    onClick={() => setEcaDrawer({ assessment: eca, assignment })}
                    className="mb-3 group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-indigo-200 hover:bg-indigo-50/20">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar name={eca.employee_name} size={36} />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-800">{eca.employee_name}</p>
                          <p className="text-[11px] text-slate-400">
                            {eca.cycle_period || 'End-Cycle'} · {eca.period || '—'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {autoLock && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                          </span>
                        )}
                        {eca.self_rating && (
                          <span className="text-xs font-semibold text-amber-600">Self: {eca.self_rating.toFixed(1)} ★</span>
                        )}
                        <span className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold"
                          style={{ backgroundColor: tone.bg, color: tone.fg }}>
                          {ECA_STATUS_LABEL[eca.status] || eca.status}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-[11px] text-slate-500">
                        {autoLock ? 'Auto-locked — read only' : needsAction ? 'Complete your manager assessment' : 'View assessment'}
                      </p>
                      <button type="button"
                        onClick={(e) => { e.stopPropagation(); setEcaDrawer({ assessment: eca, assignment }); }}
                        className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-700">
                        Open
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Phase 1 tabs */}
          {!['mid-cycle', 'end-cycle', 'my-goals'].includes(tab) && loading && <SkeletonList />}
          {!['mid-cycle', 'end-cycle', 'my-goals'].includes(tab) && !loading && filtered.length === 0 && (
            <EmptyState
              title={tab === 'pending' ? 'No pending actions' : 'No team goal sheets yet'}
              description={tab === 'pending' ? 'All caught up.' : 'Goals assigned to your team will appear here.'}
            />
          )}
          {!['mid-cycle', 'end-cycle', 'my-goals'].includes(tab) && !loading && filtered.map((a) => {
            const kraCount = (a.kras || []).length;
            const kpiCount = (a.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0);
            const needsAction = [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION, PMS_STATUS.EMPLOYEE_CONFIRMED].includes(a.status);
            const autoLock = isAutoLocked(a);
            return (
              <div
                key={a.id}
                onClick={() => setDrawer(a)}
                className="mb-3 group cursor-pointer rounded-xl border border-slate-100 p-4 transition hover:border-blue-200 hover:bg-blue-50/20"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <Avatar name={a.employee_name} size={36} />
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-800">{a.employee_name}</p>
                      <p className="text-[11px] text-slate-400">{a.period || 'No period'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {autoLock && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                      </span>
                    )}
                    {!autoLock && needsAction && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-700">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                        Action needed
                      </span>
                    )}
                    <StatusChip status={a.status} />
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                  <MiniStat value={kraCount}  label="KRAs"  color="#3b82f6" />
                  <MiniStat value={kpiCount}  label="KPIs"  color="#8b5cf6" />
                  <MiniStat value={(a.competencies || []).length} label="Comp." color="#10b981" />
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                  <p className="text-[11px] text-slate-500">
                    {autoLock ? 'Auto-locked — read only' :
                     a.status === PMS_STATUS.EMPLOYEE_CONFIRMED ? 'Ready for your approval' :
                     [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION].includes(a.status) ? 'Open discussion' :
                     'View details'}
                  </p>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setDrawer(a); }}
                    className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700"
                  >
                    Open
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {myDrawer && (
        <GoalDetailDrawer
          assignment={myDrawer}
          viewerRole="employee"
          onClose={() => setMyDrawer(null)}
          onChanged={() => { loadMyGoals(); setMyDrawer(null); }}
        />
      )}

      {drawer && (
        <GoalDetailDrawer
          assignment={drawer}
          viewerRole="manager"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}

      {mcrDrawer && (
        <MidCycleReviewDrawer
          review={mcrDrawer.review}
          assignment={mcrDrawer.assignment}
          viewerRole="manager"
          onClose={() => setMcrDrawer(null)}
          onChanged={() => { loadMcr(); setMcrDrawer(null); }}
        />
      )}

      {ecaDrawer && (
        <EndCycleAssessmentDrawer
          assessment={ecaDrawer.assessment}
          assignment={ecaDrawer.assignment}
          viewerRole="manager"
          onClose={() => setEcaDrawer(null)}
          onChanged={() => { loadEca(); setEcaDrawer(null); }}
        />
      )}
    </div>
  );
}


function StatCard({ label, value, icon, accent = '#3b82f6' }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-sm">
      <div className="mb-3 text-2xl">{icon}</div>
      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">{label}</div>
      <div className="text-2xl font-bold" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function MiniStat({ value, label, color }) {
  return (
    <div className="text-center">
      <div className="text-base font-bold" style={{ color }}>{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
    </div>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
      </div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 text-xs text-slate-500">{description}</p>
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
