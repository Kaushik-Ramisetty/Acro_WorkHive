import { useCallback, useEffect, useState } from 'react';
import { getWeekDates, getWeekId, getWeekStart } from '../utils/weekHelpers';
import { WF } from '../components/Timesheets/workflow/statuses';

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
  };
}
