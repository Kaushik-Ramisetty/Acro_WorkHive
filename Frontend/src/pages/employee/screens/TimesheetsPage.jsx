import { useEffect, useMemo, useState } from "react";
import { PageTitle, Card, Pill } from "../parts/UI";
import { timesheet as tsApi } from "../../../services/timesheet";

const STATUS_TONE = {
  draft: "slate", pending_review: "amber",
  approved: "green", rejected: "red",
};

function startOfWeek(d) {
  const c = new Date(d);
  const dow = (c.getDay() + 6) % 7; // Mon=0
  c.setDate(c.getDate() - dow);
  c.setHours(0, 0, 0, 0);
  return c;
}
function fmtIso(d) { return d.toISOString().slice(0, 10); }
function dayLabel(d) {
  return d.toLocaleDateString("en-IN", { weekday: "long", month: "short", day: "numeric" });
}

const TimesheetsPage = () => {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [list, setList] = useState([]);            // existing timesheets
  const [activeTs, setActiveTs] = useState(null);  // ts for current week (or null)
  const [grid, setGrid] = useState({});            // { yyyy-mm-dd: [{project_id, task_id, logged_hours, description}, ...] }
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const days = useMemo(() => {
    const arr = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [weekStart]);

  const periodStart = fmtIso(days[0]);
  const periodEnd   = fmtIso(days[6]);

  const refresh = async () => {
    setErr("");
    try {
      const [ps, ts] = await Promise.all([tsApi.projects(), tsApi.list()]);
      setProjects(Array.isArray(ps) ? ps : []);
      setList(Array.isArray(ts) ? ts : []);
      const match = (Array.isArray(ts) ? ts : []).find(
        (s) => s.period_start === periodStart && s.period_end === periodEnd,
      );
      if (match) {
        const detail = await tsApi.get(match.id);
        setActiveTs(detail);
        const g = {};
        (detail.entries || []).forEach((e) => {
          (g[e.entry_date] = g[e.entry_date] || []).push(e);
        });
        setGrid(g);
      } else {
        setActiveTs(null);
        setGrid({});
      }
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Failed to load");
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [periodStart, periodEnd]);

  useEffect(() => {
    if (projects.length === 0) { setTasks([]); return; }
    // Pre-load tasks for the first project (used to populate the dropdown for any day).
    tsApi.tasks().then((rows) => setTasks(Array.isArray(rows) ? rows : [])).catch(() => setTasks([]));
  }, [projects]);

  const isLocked = !!activeTs?.is_locked;
  const status = activeTs?.status || "draft";

  const addRow = (iso) => {
    if (isLocked) return;
    setGrid((g) => ({
      ...g,
      [iso]: [...(g[iso] || []), { project_id: projects[0]?.id || "", task_id: "", logged_hours: 0, description: "" }],
    }));
  };
  const updateRow = (iso, idx, patch) => {
    setGrid((g) => ({
      ...g,
      [iso]: g[iso].map((r, i) => (i === idx ? { ...r, ...patch } : r)),
    }));
  };
  const removeRow = (iso, idx) => {
    setGrid((g) => ({ ...g, [iso]: g[iso].filter((_, i) => i !== idx) }));
  };

  const totalForDay = (iso) =>
    (grid[iso] || []).reduce((s, r) => s + (parseFloat(r.logged_hours) || 0), 0);
  const weekTotal = days.reduce((s, d) => s + totalForDay(fmtIso(d)), 0);

  const buildEntries = () => {
    const out = [];
    for (const d of days) {
      const iso = fmtIso(d);
      for (const r of grid[iso] || []) {
        const hrs = parseFloat(r.logged_hours);
        if (!hrs || hrs <= 0) continue;
        out.push({
          entry_date: iso,
          project_id: r.project_id || null,
          task_id: r.task_id || null,
          logged_hours: hrs,
          description: r.description || "",
          is_manual_entry: true,
        });
      }
    }
    return out;
  };

  const save = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      const payload = {
        period_type: "weekly",
        period_start: periodStart,
        period_end: periodEnd,
        entries: buildEntries(),
      };
      if (activeTs) {
        await tsApi.edit(activeTs.id, payload);
      } else {
        await tsApi.create(payload);
      }
      setMsg("Saved.");
      await refresh();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Save failed");
    } finally { setBusy(false); }
  };
  const submit = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      let id = activeTs?.id;
      if (!id) {
        const created = await tsApi.create({
          period_type: "weekly",
          period_start: periodStart,
          period_end: periodEnd,
          entries: buildEntries(),
        });
        id = created.id;
      } else {
        await tsApi.edit(id, {
          period_type: "weekly",
          period_start: periodStart,
          period_end: periodEnd,
          entries: buildEntries(),
        });
      }
      await tsApi.submit(id);
      setMsg("Submitted for review.");
      await refresh();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Submit failed");
    } finally { setBusy(false); }
  };

  const goPrev = () => {
    const d = new Date(weekStart); d.setDate(d.getDate() - 7); setWeekStart(d);
  };
  const goNext = () => {
    const d = new Date(weekStart); d.setDate(d.getDate() + 7); setWeekStart(d);
  };

  return (
    <div className="space-y-5">
      <PageTitle
        title="Timesheets"
        sub={`Week of ${dayLabel(days[0])} - ${dayLabel(days[6])}`}
        right={
          <>
            <button onClick={goPrev} className="px-3 py-1.5 rounded border border-slate-200 text-xs">{"< Previous"}</button>
            <button onClick={goNext} className="px-3 py-1.5 rounded border border-slate-200 text-xs">{"Next >"}</button>
          </>
        }
      />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Status:</span>
          <Pill tone={STATUS_TONE[status] || "slate"}>{status}</Pill>
          {isLocked && <Pill tone="slate">locked</Pill>}
        </div>
        <div className="flex items-center gap-2">
          {!isLocked && (
            <>
              <button onClick={save} disabled={busy}
                className="px-4 py-2 rounded-lg text-xs border border-slate-200 font-semibold text-slate-700 hover:bg-slate-50">
                Save Draft
              </button>
              <button onClick={submit} disabled={busy}
                className="px-4 py-2 rounded-lg text-xs text-white font-semibold" style={{ background: "#14b8a6" }}>
                Submit for Review
              </button>
            </>
          )}
        </div>
      </div>

      {err && <div className="bg-rose-50 text-rose-700 text-xs px-3 py-2 rounded">{err}</div>}
      {msg && <div className="bg-emerald-50 text-emerald-700 text-xs px-3 py-2 rounded">{msg}</div>}

      {days.map((d) => {
        const iso = fmtIso(d);
        const rows = grid[iso] || [];
        return (
          <Card key={iso}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-800">{dayLabel(d)}</h3>
              <div className="flex items-center gap-3">
                <span className="text-[11px] text-slate-500">{totalForDay(iso).toFixed(2)}h</span>
                {!isLocked && (
                  <button onClick={() => addRow(iso)}
                    className="text-[11px] font-semibold text-teal-600 hover:underline">+ Add entry</button>
                )}
              </div>
            </div>
            {rows.length === 0 && <p className="text-[11px] text-slate-400">No entries for this day.</p>}
            {rows.map((r, idx) => (
              <div key={idx} className="grid grid-cols-12 gap-2 mt-2 items-center text-xs">
                <select value={r.project_id || ""} onChange={(e) => updateRow(iso, idx, { project_id: e.target.value, task_id: "" })}
                  disabled={isLocked} className="col-span-3 px-2 py-1 border border-slate-200 rounded">
                  <option value="">- Project -</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <select value={r.task_id || ""} onChange={(e) => updateRow(iso, idx, { task_id: e.target.value })}
                  disabled={isLocked} className="col-span-3 px-2 py-1 border border-slate-200 rounded">
                  <option value="">- Task -</option>
                  {tasks.filter((t) => !r.project_id || t.project_id === r.project_id).map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <input type="number" step="0.25" min="0" max="24" value={r.logged_hours}
                  onChange={(e) => updateRow(iso, idx, { logged_hours: e.target.value })}
                  disabled={isLocked} className="col-span-1 px-2 py-1 border border-slate-200 rounded" />
                <input value={r.description || ""} onChange={(e) => updateRow(iso, idx, { description: e.target.value })}
                  disabled={isLocked} placeholder="Description"
                  className="col-span-4 px-2 py-1 border border-slate-200 rounded" />
                {!isLocked && (
                  <button onClick={() => removeRow(iso, idx)}
                    className="col-span-1 text-rose-600 text-[11px] hover:underline">Remove</button>
                )}
              </div>
            ))}
          </Card>
        );
      })}

      <Card>
        <div className="flex items-center justify-between text-sm">
          <span className="font-semibold text-slate-700">Total this week</span>
          <span className="text-base font-bold text-slate-900">{weekTotal.toFixed(2)} h</span>
        </div>
      </Card>

      {list.length > 0 && (
        <Card>
          <h3 className="text-sm font-bold text-slate-800 mb-3">Recent timesheets</h3>
          <table className="w-full text-xs">
            <thead className="text-slate-400 uppercase tracking-wider text-[10px]">
              <tr>
                <th className="text-left py-2">Period</th>
                <th className="text-right">Hours</th>
                <th className="text-left pl-4">Status</th>
              </tr>
            </thead>
            <tbody>
              {list.slice(0, 10).map((t) => (
                <tr key={t.id} className="border-t border-slate-100">
                  <td className="py-2">{t.period_start} - {t.period_end}</td>
                  <td className="text-right">{(t.total_logged_hours || 0).toFixed(2)}</td>
                  <td className="pl-4"><Pill tone={STATUS_TONE[t.status] || "slate"}>{t.status}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default TimesheetsPage;
