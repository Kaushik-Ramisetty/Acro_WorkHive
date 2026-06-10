import { useCallback, useEffect, useState } from 'react';
import { getWeekDates, getWeekId, getWeekStart } from '../utils/weekHelpers';
import { WF } from '../components/Timesheets/workflow/statuses';

// ── DB → hook entry converter ─────────────────────────────────────────────────

const _DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/**
 * Convert a TimesheetEntryOut (from backend) to the shape the hook / table expects.
 * Description is stored as "client - project - task" by the frontend.
 * logged_hours is kept so HoursCell can use it as a fallback when no AttendanceRecord exists.
 */
function dbEntryToHookEntry(e) {
  const parts   = (e.description || '').split(' - ');
  const d       = new Date(e.entry_date + 'T00:00:00');
  return {
    id:           e.id,
    day:          _DOW[d.getDay()],
    date:         e.entry_date,
    client:       e.client_name  || parts[0] || '',
    project:      e.project_name || parts[1] || '',
    task:         e.task_name    || parts[2] || '',
    status:       'draft',
    logged_hours: e.logged_hours || 0,
  };
}

// ── Week-entry generator ──────────────────────────────────────────────────────

/** Build one draft stub per Mon–Sun for the given week start (Date). */
function generateWeekEntries(weekStart) {
  return getWeekDates(weekStart, { includeWeekends: true }).map(({ name, iso }) => ({
    id:      `auto-${iso}`,
    day:     name,
    date:    iso,
    client:  '',
    project: '',
    task:    '',
    status:  'draft',
  }));
}

// ── localStorage helpers ──────────────────────────────────────────────────────

function storageKey(weekId) {
  return `workhive_timesheets_${weekId}`;
}

function loadWeek(weekId, weekStart) {
  try {
    const raw = localStorage.getItem(storageKey(weekId));
    if (raw) {
      const parsed = JSON.parse(raw);
      // Draft autosave is local-only. Workflow state must come from backend.
      parsed.weekStatus = WF.DRAFT;
      parsed.workflowHistory = [];
      if (parsed.entries) {
        const byDate = new Map(
          parsed.entries.map(({ hours: _dropped, status: _status, ...rest }) => [
            rest.date,
            { ...rest, status: 'draft' },
          ])
        );
        parsed.entries = generateWeekEntries(weekStart).map((entry) => ({
          ...entry,
          ...(byDate.get(entry.date) || {}),
          status: 'draft',
        }));
      }
      return parsed;
    }
  } catch { /* corrupt storage — fall through to fresh defaults */ }

  return {
    entries:         generateWeekEntries(weekStart),
    weekStatus:      WF.DRAFT,
    workflowHistory: [],
  };
}

function saveWeek(weekId, data) {
  try {
    localStorage.setItem(storageKey(weekId), JSON.stringify({
      ...data,
      weekStatus: WF.DRAFT,
      workflowHistory: [],
      entries: (data.entries || []).map(({ status: _status, ...entry }) => ({
        ...entry,
        status: 'draft',
      })),
    }));
  } catch { /* storage full — silent fail */ }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTimesheets() {
  const [activeWeekStart, setActiveWeekStart] = useState(() =>
    getWeekStart(new Date())
  );

  const weekId = getWeekId(activeWeekStart);

  const [state, setState] = useState(() => {
    const ws = getWeekStart(new Date());
    return loadWeek(getWeekId(ws), ws);
  });

  useEffect(() => {
    setState(loadWeek(weekId, activeWeekStart));
  }, [weekId]);

  const update = useCallback(
    (updater) => {
      setState((prev) => {
        const next = { ...prev, ...updater(prev) };
        saveWeek(weekId, next);
        return next;
      });
    },
    [weekId]
  );

  const updateEntry = useCallback(
    (id, changes) => {
      const { hours: _dropped, ...safe } = changes;
      update((s) => ({
        entries: s.entries.map((e) => (e.id === id ? { ...e, ...safe } : e)),
      }));
    },
    [update]
  );

  const setWeekStatus = useCallback(
    () => { update(() => ({ weekStatus: WF.DRAFT })); },
    [update]
  );

  const advanceWorkflow = useCallback(
    (_toStatus, _historyRecord) => {
      update((s) => ({
        weekStatus: WF.DRAFT,
        workflowHistory: [],
        entries: s.entries.map((e) => ({ ...e, status: 'draft' })),
      }));
    },
    [update]
  );

  const resubmit = useCallback(
    (_actedBy = 'You') => {
      update((s) => ({
        weekStatus: WF.DRAFT,
        workflowHistory: [],
        entries: s.entries.map((e) => ({ ...e, status: 'draft' })),
      }));
    },
    [update]
  );

  const saveDraft = useCallback(() => {
    saveWeek(weekId, state);
  }, [weekId, state]);

  /** Wipe local localStorage draft and reset to blank stubs for the active week. */
  const resetLocalDraft = useCallback(() => {
    try { localStorage.removeItem(storageKey(weekId)); } catch { /* ignore */ }
    setState({
      entries: generateWeekEntries(activeWeekStart),
      weekStatus: WF.DRAFT,
      workflowHistory: [],
    });
  }, [weekId, activeWeekStart]);

  /**
   * Populate the week grid from backend TimesheetEntryOut rows.
   * Days that have no DB entry keep blank stubs so the user can still fill them in.
   * Persists to localStorage so navigating away and back preserves the data.
   */
  const hydrateFromDB = useCallback((dbEntries) => {
    const byDate = new Map(dbEntries.map((e) => [e.entry_date, e]));
    const merged = generateWeekEntries(activeWeekStart).map((stub) => {
      const dbEntry = byDate.get(stub.date);
      return dbEntry ? dbEntryToHookEntry(dbEntry) : stub;
    });
    const next = { entries: merged, weekStatus: WF.DRAFT, workflowHistory: [] };
    saveWeek(weekId, next);
    setState(next);
  }, [weekId, activeWeekStart]);

  const navigateWeek = useCallback((delta) => {
    setActiveWeekStart((prev) => {
      const d = new Date(prev);
      d.setDate(d.getDate() + delta);
      return getWeekStart(d);
    });
  }, []);

  const goThisWeek = useCallback(() => {
    setActiveWeekStart(getWeekStart(new Date()));
  }, []);

  return {
    entries:         state.entries,
    weekStatus:      state.weekStatus,
    workflowHistory: state.workflowHistory ?? [],
    activeWeekStart,
    weekId,
    updateEntry,
    setWeekStatus,
    advanceWorkflow,
    resubmit,
    navigateWeek,
    goThisWeek,
    saveDraft,
    resetLocalDraft,
    hydrateFromDB,
  };
}
