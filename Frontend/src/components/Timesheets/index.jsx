import { useEffect, useRef, useState } from 'react';
import { useTimesheets } from '../../hooks/useTimesheets';
import { useWeekAttendance } from '../../hooks/useWeekAttendance';
import { timesheet as tsApi } from '../../services/timesheet';
import { fmtIso, formatWeekLabel, computeWeeklyHours, classifyWeek, ATTENDANCE_STATUS } from '../../utils/weekHelpers';
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
    resetLocalDraft,
    hydrateFromDB,
  } = useTimesheets();

  const { attendanceMap, isLoading: attendanceLoading } = useWeekAttendance(activeWeekStart);

  const [filters, setFilters]               = useState({ client: '', project: '', status: '' });
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [toast, setToast]                   = useState(null); // { message, type }
  const [submitting, setSubmitting]           = useState(false);
  const [persistedDraft, setPersistedDraft]   = useState(null);
  const [isDraftInitialized, setIsDraftInitialized] = useState(false);
  const [serverWeekStatus, setServerWeekStatus] = useState(null); // actual DB status for this week
  const [creatingRetroactive, setCreatingRetroactive] = useState(false);

  // 'past' | 'current' | 'future' — drives init strategy and empty-state message.
  const weekType = classifyWeek(activeWeekStart);

  // Tracks the AbortController for the current in-flight init request so
  // React StrictMode's cleanup can abort the first (stale) call and the second
  // (real) call is the only one that updates state.
  const initAbortRef = useRef(null);

  const showToast = (message, type = 'success') => setToast({ message, type });
  const closeToast = () => setToast(null);

  const totalHours = computeWeeklyHours(entries, attendanceMap);

  const weekLabel = formatWeekLabel(activeWeekStart, { includeWeekends: true });

  // Shared hydration: apply a draft returned by the backend to all relevant state.
  // IMPORTANT: when the server returns an empty entries array we do NOT reset local
  // state — the user may have unsaved draft work in localStorage. resetLocalDraft()
  // is only called explicitly when we know there is NO server record for a past week.
  const applyDraft = (draft) => {
    setPersistedDraft(draft);
    setServerWeekStatus(draft.status || WF.DRAFT);
    if (draft.entries?.length > 0) {
      hydrateFromDB(draft.entries);
    }
    // Empty entries → keep whatever is in localStorage (don't destroy local draft)
  };

  useEffect(() => {
    if (!activeWeekStart) return;

    setIsDraftInitialized(false);
    setServerWeekStatus(null);
    setPersistedDraft(null);

    // Future weeks have no data yet — skip all API calls.
    if (weekType === 'future') {
      resetLocalDraft();
      setIsDraftInitialized(true);
      return;
    }

    // Abort any previous in-flight init before starting a new one.
    // In React StrictMode (dev), the cleanup fires synchronously after the
    // first mount — the abort cancels that first fetch so only the second
    // (real) invocation completes and updates state.
    const controller = new AbortController();
    initAbortRef.current = controller;

    const end = new Date(activeWeekStart);
    end.setDate(end.getDate() + 6);
    const periodStart = fmtIso(activeWeekStart);
    const periodEnd = fmtIso(end);

    if (weekType === 'current') {
      // Current week: create-or-get (idempotent — backend returns existing if found).
      console.log('[Timesheets] initializing draft', { periodStart, periodEnd });
      tsApi.create({
        period_type: 'weekly',
        period_start: periodStart,
        period_end: periodEnd,
        entries: [],
      }, { signal: controller.signal })
        .then((draft) => {
          if (controller.signal.aborted) return;
          applyDraft(draft);
          console.log('[Timesheets] draft loaded', draft);
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          console.error('[Timesheets] draft initialization failed', err);
          showToast(err?.data?.detail || err?.message || 'Could not initialize timesheet draft', 'error');
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsDraftInitialized(true);
        });
    } else {
      // Past week: look up without auto-creating a new draft.
      // The list endpoint returns TimesheetOut (summary only, no entries[]).
      // When a match is found we must call GET /timesheet/{id} to get the full
      // detail response (with entries) before hydrating the UI.
      console.log('[Timesheets] looking up past week', { periodStart, periodEnd });
      tsApi.list({})
        .then((list) => {
          if (controller.signal.aborted) return;
          const found = (Array.isArray(list) ? list : []).find(
            (t) => t.period_start === periodStart && t.period_end === periodEnd,
          );
          if (found) {
            console.log('[Timesheets] past week summary found', found.id, found.status, '— fetching detail');
            // Fetch the full detail (with entries) before hydrating
            tsApi.get(found.id)
              .then((detail) => {
                if (controller.signal.aborted) return;
                console.log('[Timesheets] past week detail loaded, entries:', detail?.entries?.length ?? 0);
                applyDraft(detail);
              })
              .catch((err) => {
                if (controller.signal.aborted) return;
                console.warn('[Timesheets] detail fetch failed, using summary stub', err);
                // Fall back to the summary object — entries will be absent/empty
                // so applyDraft preserves whatever localStorage has
                applyDraft(found);
              })
              .finally(() => {
                if (!controller.signal.aborted) setIsDraftInitialized(true);
              });
          } else {
            resetLocalDraft();
            console.log('[Timesheets] no past week record found');
            setIsDraftInitialized(true);
          }
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          console.error('[Timesheets] past-week lookup failed', err);
          resetLocalDraft();
          setIsDraftInitialized(true);
        });
    }

    return () => { controller.abort(); };
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

    // For past weeks, create a retroactive timesheet using finalized attendance hours.
    const payloadEntries = entries
      .map((entry) => {
        const attendance = attendanceMap[entry.date];
        return {
          entry_date: entry.date,
          logged_hours: attendance?.attendance_status === ATTENDANCE_STATUS.FINALIZED
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
    setCreatingRetroactive(true);
    const created = await tsApi.create({
      period_type: 'weekly',
      period_start: periodStart,
      period_end: periodEnd,
      entries: payloadEntries,
    });
    setCreatingRetroactive(false);
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
      const submitResult = await tsApi.submit(tsId);

      // Update the displayed status to whatever the server actually set.
      // submit_timesheet returns TimesheetOut with real status:
      //   • client-site employees → 'pending_client_review'
      //   • WFH/WFO employees     → 'pending_review'
      const newStatus = submitResult?.status || WF.PENDING_CLIENT;
      setServerWeekStatus(newStatus);

      setShowSubmitModal(false);
      showToast('Timesheet submitted — awaiting review.');
    } catch (err) {
      console.error('[Timesheets] submit failed', err);
      showToast(err?.data?.detail || err?.message || 'Submit failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitConfirm = () => {
    submitPersistedTimesheet();
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

  // Use the real server status when available.
  // The hook always forces weekStatus → 'draft' via localStorage; serverWeekStatus
  // is the authoritative value fetched/updated from the backend.
  const effectiveWeekStatus = serverWeekStatus ?? weekStatus;

  return (
    <div id="timesheet-print-root" style={{ maxWidth: '100%', padding: '0.75rem 0' }}>
      <WeekHeader
        activeWeekStart={activeWeekStart}
        weekStatus={effectiveWeekStatus}
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
        weekStatus={effectiveWeekStatus}
        attendanceMap={attendanceMap}
        attendanceLoading={attendanceLoading}
        onUpdate={updateEntry}
      />

      <ActionBar
        weekStatus={effectiveWeekStatus}
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
