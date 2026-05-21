import { useEffect, useState } from 'react';
import { useTimesheets } from '../../hooks/useTimesheets';
import { useWeekAttendance } from '../../hooks/useWeekAttendance';
import { timesheet as tsApi } from '../../services/timesheet';
import { fmtIso, formatWeekLabel } from '../../utils/weekHelpers';
import { exportToXlsx } from '../../utils/exportXlsx';
import { WF } from './workflow/statuses';

import WeekHeader   from './WeekHeader';
import MetricCards  from './MetricCards';
import FilterBar    from './FilterBar';
import EntriesTable from './EntriesTable';
import ActionBar    from './ActionBar';
import SubmitModal  from './SubmitModal';
import Toast        from './Toast';

export default function Timesheets() {
  const {
    entries,
    weekStatus,
    activeWeekStart,
    weekId,
    updateEntry,
    advanceWorkflow,
    resubmit,
    navigateWeek,
    goThisWeek,
    saveDraft,
  } = useTimesheets();

  const { attendanceMap, isLoading: attendanceLoading } = useWeekAttendance(activeWeekStart);

  const [filters, setFilters]               = useState({ client: '', project: '', status: '' });
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [toast, setToast]                   = useState(null); // { message, type }
  const [submitting, setSubmitting]         = useState(false);
  const [persistedDraft, setPersistedDraft] = useState(null);

  const showToast = (message, type = 'success') => setToast({ message, type });
  const closeToast = () => setToast(null);

  // Total hours from attendance (finalized days only) — single source of truth
  const totalHours = Object.values(attendanceMap)
    .filter((a) => a.attendance_status === 'FINALIZED')
    .reduce((s, a) => s + (a.effective_hours || 0), 0);

  const weekLabel = formatWeekLabel(activeWeekStart, { includeWeekends: true });

  useEffect(() => {
    if (!activeWeekStart) return;

    let cancelled = false;
    const end = new Date(activeWeekStart);
    end.setDate(end.getDate() + 6);
    const periodStart = fmtIso(activeWeekStart);
    const periodEnd = fmtIso(end);

    console.log('[Timesheets] initializing draft', { periodStart, periodEnd });
    tsApi.create({
      period_type: 'weekly',
      period_start: periodStart,
      period_end: periodEnd,
      entries: [],
    })
      .then((draft) => {
        if (cancelled) return;
        setPersistedDraft(draft);
        console.log('[Timesheets] draft loaded', draft);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('[Timesheets] draft initialization failed', err);
        showToast(err?.data?.detail || err?.message || 'Could not initialize timesheet draft', 'error');
      });

    return () => { cancelled = true; };
  }, [activeWeekStart]);

  // ── Handlers ──────────────────────────────────────────────────────────────────

  const handleSaveDraft = () => {
    saveDraft();
    showToast('Draft saved');
  };

  const resolvePersistedTimesheet = async () => {
    const end = new Date(activeWeekStart);
    end.setDate(end.getDate() + 6);
    const periodStart = fmtIso(activeWeekStart);
    const periodEnd = fmtIso(end);

    console.log('[Timesheets] resolving persisted timesheet', { periodStart, periodEnd });
    if (
      persistedDraft?.id &&
      persistedDraft.period_start === periodStart &&
      persistedDraft.period_end === periodEnd
    ) {
      console.log('[Timesheets] found initialized timesheet.id', persistedDraft.id);
      return persistedDraft;
    }

    const existing = await tsApi.list({});
    const found = (Array.isArray(existing) ? existing : []).find(
      (t) => t.period_start === periodStart && t.period_end === periodEnd
    );
    if (found?.id) {
      console.log('[Timesheets] found persisted timesheet.id', found.id);
      return found;
    }

    const payloadEntries = entries
      .map((entry) => {
        const attendance = attendanceMap[entry.date];
        return {
          entry_date: entry.date,
          logged_hours: attendance?.attendance_status === 'FINALIZED'
            ? Number(attendance.effective_hours || 0)
            : 0,
          is_billable: true,
          is_manual_entry: true,
          source: 'manual',
          description: [entry.client, entry.project, entry.task].filter(Boolean).join(' - ') || null,
        };
      })
      .filter((entry) => entry.logged_hours > 0);

    console.log('[Timesheets] no persisted timesheet found; creating draft', {
      periodStart,
      periodEnd,
      entryCount: payloadEntries.length,
    });
    const created = await tsApi.create({
      period_type: 'weekly',
      period_start: periodStart,
      period_end: periodEnd,
      entries: payloadEntries,
    });
    setPersistedDraft(created);
    console.log('[Timesheets] created persisted timesheet.id', created?.id);
    return created;
  };

  const submitPersistedTimesheet = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const persisted = await resolvePersistedTimesheet();
      const tsId = persisted?.id;
      console.log('[Timesheets] submit handler received ts_id', tsId);
      if (!tsId) throw new Error('No persisted timesheet id available for submit.');

      console.log('[Timesheets] calling POST /timesheet/%s/submit', tsId);
      await tsApi.submit(tsId);

      advanceWorkflow(WF.PENDING_CLIENT, {
        step:     'employee',
        outcome:  'done',
        actedBy:  'You',
        actedAt:  new Date().toISOString(),
        comments: null,
      });
      setShowSubmitModal(false);
      showToast('Timesheet submitted - awaiting Client Manager review.');
    } catch (err) {
      console.error('[Timesheets] submit failed', err);
      showToast(err?.data?.detail || err?.message || 'Submit failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitConfirm = () => {
    submitPersistedTimesheet();
    return;
    // eslint-disable-next-line no-unreachable
    advanceWorkflow(WF.PENDING_CLIENT, {
      step:     'employee',
      outcome:  'done',
      actedBy:  'You',
      actedAt:  new Date().toISOString(),
      comments: null,
    });
    setShowSubmitModal(false);
    showToast('Timesheet submitted — awaiting Client Manager review.');
  };

  const handleResubmit = () => {
    resubmit('You');
    showToast('Resubmitted — awaiting Client Manager review.');
  };

  const handleExportPdf = () => {
    window.print();
  };

  const handleExportExcel = async () => {
    // Enrich with attendance hours before export (hours live in attendanceMap, not entries)
    const enriched = entries.map((e) => ({
      ...e,
      hours: attendanceMap[e.date]?.effective_hours ?? 0,
    }));
    const filename = `timesheet_${weekId}.xlsx`;
    const result   = await exportToXlsx(enriched, filename);
    if (!result.ok) {
      showToast(result.note, 'error');
    } else {
      showToast(`Downloaded ${filename}`);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div id="timesheet-print-root" style={{ maxWidth: '100%', padding: '0.75rem 0' }}>
      <WeekHeader
        activeWeekStart={activeWeekStart}
        weekStatus={weekStatus}
        onPrev={() => navigateWeek(-7)}
        onNext={() => navigateWeek(7)}
        onThisWeek={goThisWeek}
      />

      <MetricCards attendanceMap={attendanceMap} entries={entries} />

      <FilterBar
        entries={entries}
        filters={filters}
        onChange={setFilters}
      />

      <EntriesTable
        entries={entries}
        filters={filters}
        weekStatus={weekStatus}
        attendanceMap={attendanceMap}
        attendanceLoading={attendanceLoading}
        onUpdate={updateEntry}
      />

      <ActionBar
        weekStatus={weekStatus}
        onSaveDraft={handleSaveDraft}
        onSubmit={() => setShowSubmitModal(true)}
        onResubmit={handleResubmit}
        onExportPdf={handleExportPdf}
        onExportExcel={handleExportExcel}
      />

      {showSubmitModal && (
        <SubmitModal
          weekLabel={weekLabel}
          totalHours={totalHours}
          onCancel={() => setShowSubmitModal(false)}
          onConfirm={handleSubmitConfirm}
        />
      )}

      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={closeToast} />
      )}
    </div>
  );
}
