/**
 * Admin Bench Resource Management page.
 *
 * Three concerns on one screen:
 *   1. Summary cards (Total / Allocated / On Bench).
 *   2. Tabbed table (All / Bench / Allocated).
 *   3. Per-row actions: Edit (open modal), Assign (bench rows only),
 *      History (project history modal).
 *
 * The data model is intentionally a SINGLE source — `employees` from
 * /admin/resource-employees. The bench list (/admin/bench) is fetched
 * separately because it carries the bench_duration_days calculation that
 * isn't on the main payload. We merge the duration in by employee id.
 */
import { useEffect, useMemo, useState } from "react";
import { resourceApi } from "../../../services/resourceApi";

// Toast helper — minimal, no dependency. Mounts a fixed-position chip and
// removes itself after 2.5s. Used for success/error feedback per the brief.
function useToasts() {
  const [items, setItems] = useState([]);
  function push(message, tone = "success") {
    const id = Math.random().toString(36).slice(2);
    setItems((xs) => [...xs, { id, message, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 2500);
  }
  const node = (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          className="rounded-lg px-4 py-2 text-xs font-semibold shadow-md"
          style={{
            background: t.tone === "error" ? "#fef2f2" : "#f0fdf4",
            color: t.tone === "error" ? "#b91c1c" : "#15803d",
            border: t.tone === "error" ? "1px solid #fecaca" : "1px solid #bbf7d0",
          }}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
  return { push, node };
}

// Identify "manager-like" designations consistently with the backend cap.
const MANAGER_RE = /\b(senior manager|engineering manager|manager)\b/i;

function fmtDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-IN", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return d;
  }
}

// ---------------------------------------------------------------
// Add / Edit Employee details modal
// ---------------------------------------------------------------
function AddEmployeeDetailsModal({ open, onClose, employee, projects, employees, onSaved }) {
  const [skills, setSkills] = useState([]);
  const [skillInput, setSkillInput] = useState("");
  // 'project' is either an existing project_id, the string 'other', or empty.
  const [project, setProject] = useState("");
  const [otherProjectName, setOtherProjectName] = useState("");
  const [managerId, setManagerId] = useState("");
  const [active, setActive] = useState(true);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [experienceYears, setExperienceYears] = useState("");
  const [certifications, setCertifications] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Reset when re-opened.
  useEffect(() => {
    if (!open) return;
    setSkills(employee?.skills || []);
    setSkillInput("");
    setProject(employee?.latest_project_id || "");
    setOtherProjectName("");
    setManagerId(employee?.latest_manager_id ? String(employee.latest_manager_id) : "");
    setActive(!!employee?.has_active_allocation);
    setStartDate(employee?.latest_start_date ? String(employee.latest_start_date).slice(0, 10) : "");
    setEndDate(employee?.latest_end_date ? String(employee.latest_end_date).slice(0, 10) : "");
    setExperienceYears(
      typeof employee?.experience_years === "number" ? String(employee.experience_years) : ""
    );
    setCertifications(employee?.certifications || "");
    setError("");
  }, [open, employee]);

  // Pool of employees whose designation matches Manager / Senior Manager.
  const projectManagerOptions = useMemo(() => {
    return (employees || [])
      .filter((e) => MANAGER_RE.test(e.designation || ""))
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [employees]);

  // When the user picks an existing project, auto-fill its manager.
  function handleProjectChange(value) {
    setProject(value);
    if (value && value !== "other") {
      const p = (projects || []).find((x) => x.id === value);
      if (p?.project_manager_id) setManagerId(String(p.project_manager_id));
    } else if (value === "other") {
      setManagerId("");
    }
  }

  function addSkillFromInput() {
    const v = (skillInput || "").trim();
    if (!v) return;
    setSkills((prev) =>
      prev.some((s) => s.toLowerCase() === v.toLowerCase()) ? prev : [...prev, v],
    );
    setSkillInput("");
  }

  async function save() {
    if (!employee) return;
    setBusy(true);
    setError("");
    try {
      const isOther = project === "other";
      const wantsAllocation = active && startDate && (project || isOther);
      if (wantsAllocation && isOther && !otherProjectName.trim()) {
        throw new Error("Enter the new project name or pick an existing one.");
      }

      // Always persist profile fields (experience + certifications) when
      // editing — regardless of whether an allocation is created.
      const profilePayload = {
        skills,
        experience_years: experienceYears === "" ? null : Number(experienceYears),
        certifications: certifications || null,
      };

      if (wantsAllocation && isOther) {
        await resourceApi.createAndAssign({
          employee_id: employee.id,
          project_name: otherProjectName.trim(),
          manager_id: managerId ? Number(managerId) : null,
          skills,
          allocation_status: active ? "active" : "inactive",
          start_date: startDate,
          end_date: endDate || null,
        });
        // Bench profile fields aren't part of create-and-assign — save separately.
        await resourceApi.saveEmployeeDetails(employee.id, profilePayload);
      } else if (wantsAllocation) {
        await resourceApi.assignEmployee({
          employee_id: employee.id,
          project_id: project,
          start_date: startDate,
          end_date: endDate || null,
          manager_id: managerId ? Number(managerId) : null,
          skills,
          allocation_status: active ? "active" : "inactive",
        });
        await resourceApi.saveEmployeeDetails(employee.id, profilePayload);
      } else {
        // Skills-only / non-allocating save.
        await resourceApi.saveEmployeeDetails(employee.id, {
          ...profilePayload,
          project_id: project && project !== "other" ? project : null,
          manager_id: managerId ? Number(managerId) : null,
          allocation_status: active ? "active" : "inactive",
          start_date: startDate || null,
          end_date: endDate || null,
        });
      }
      onSaved?.();
      onClose?.();
    } catch (ex) {
      setError(ex?.data?.detail || ex?.message || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
         style={{ background: "rgba(15,28,46,0.55)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className="bg-white rounded-2xl w-full max-w-xl mx-4 shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-800">Edit resource details</h3>
            <p className="text-xs text-slate-400 mt-0.5">{employee?.name}</p>
          </div>
          <button onClick={onClose} className="rounded-full bg-slate-100 hover:bg-slate-200 w-8 h-8">×</button>
        </div>

        <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">

          {/* Skills */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Skills</label>
            <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
              {skills.map((s) => (
                <span key={s}
                      className="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2.5 py-0.5 text-[11px] font-semibold text-teal-700">
                  {s}
                  <button
                    onClick={() => setSkills(skills.filter((x) => x !== s))}
                    className="text-teal-500 hover:text-teal-700 leading-none"
                    aria-label="Remove">×</button>
                </span>
              ))}
              {skills.length === 0 && (
                <span className="text-[11px] text-slate-400">No skills yet</span>
              )}
            </div>
            <div className="flex gap-2">
              <input
                value={skillInput}
                onChange={(e) => setSkillInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSkillFromInput(); } }}
                placeholder="Type a skill and press Enter"
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
              <button onClick={addSkillFromInput}
                      className="rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-600 hover:bg-slate-50">
                Add
              </button>
            </div>
          </div>

          {/* Experience + certifications */}
          <div className="grid grid-cols-[120px_1fr] gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Experience</label>
              <div className="flex items-center gap-2">
                <input type="number" min={0} max={60} step={1}
                       value={experienceYears}
                       onChange={(e) => setExperienceYears(e.target.value)}
                       placeholder="0"
                       className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
                <span className="text-xs text-slate-500">yrs</span>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Certifications</label>
              <input value={certifications}
                     onChange={(e) => setCertifications(e.target.value)}
                     placeholder="e.g. AWS Solutions Architect, PMP"
                     className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
            </div>
          </div>

          {/* Project picker */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Project</label>
            <select value={project}
                    onChange={(e) => handleProjectChange(e.target.value)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400">
              <option value="">Select project (optional)</option>
              {(projects || []).map((p) => (
                <option key={p.id} value={p.id}>{p.name || p.id} ({p.id})</option>
              ))}
              <option value="other">Other (create new)</option>
            </select>
            {project === "other" && (
              <input
                value={otherProjectName}
                onChange={(e) => setOtherProjectName(e.target.value)}
                placeholder="New project name"
                className="mt-2 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            )}
          </div>

          {/* Manager picker */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Manager</label>
            <select value={managerId}
                    onChange={(e) => setManagerId(e.target.value)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400">
              <option value="">Select manager</option>
              {projectManagerOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} — {m.designation}
                </option>
              ))}
            </select>
          </div>

          {/* Active toggle */}
          <div className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2">
            <span className="text-xs font-semibold text-slate-600">Allocation Status</span>
            <button
              onClick={() => setActive((v) => !v)}
              className="text-xs font-semibold rounded-full px-3 py-1"
              style={{
                background: active ? "#dcfce7" : "#f1f5f9",
                color: active ? "#15803d" : "#475569",
              }}
            >
              {active ? "Active" : "Inactive"}
            </button>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Start Date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                     className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">End Date</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                     min={startDate || undefined}
                     className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button onClick={onClose} disabled={busy}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button onClick={save} disabled={busy}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  style={{ background: "#14b8a6" }}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------
// Project history modal
// ---------------------------------------------------------------
function ProjectHistoryModal({ open, onClose, employee }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !employee) return;
    let cancelled = false;
    setLoading(true);
    resourceApi.getEmployeeProjects(employee.id)
      .then((r) => { if (!cancelled) setRows(Array.isArray(r) ? r : []); })
      .catch(() => { if (!cancelled) setRows([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, employee]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
         style={{ background: "rgba(15,28,46,0.55)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className="bg-white rounded-2xl w-full max-w-2xl mx-4 shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-800">Project history</h3>
            <p className="text-xs text-slate-400 mt-0.5">{employee?.name}</p>
          </div>
          <button onClick={onClose} className="rounded-full bg-slate-100 hover:bg-slate-200 w-8 h-8">×</button>
        </div>
        <div className="px-6 py-5 max-h-[70vh] overflow-y-auto">
          {loading && <p className="text-xs text-slate-400">Loading…</p>}
          {!loading && rows.length === 0 && (
            <p className="text-xs text-slate-400">No project history found.</p>
          )}
          {!loading && rows.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-slate-500 uppercase">
                  <th className="py-2">Project</th>
                  <th className="py-2">Manager</th>
                  <th className="py-2">Start</th>
                  <th className="py-2">End</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.allocation_id} className="border-t border-slate-100">
                    <td className="py-2 font-semibold text-slate-700">{r.project_name || r.project_id}</td>
                    <td className="py-2 text-slate-600">{r.manager_name || "—"}</td>
                    <td className="py-2 text-slate-600">{fmtDate(r.start_date)}</td>
                    <td className="py-2 text-slate-600">{fmtDate(r.actual_end_date || r.end_date)}</td>
                    <td className="py-2">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold"
                            style={{
                              background: r.status === "active" ? "#dcfce7" : "#f1f5f9",
                              color: r.status === "active" ? "#15803d" : "#475569",
                            }}>
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------
// Main page
// ---------------------------------------------------------------
const TABS = [
  { id: "all",  label: "All Employees" },
  { id: "bench", label: "Bench" },
  { id: "alloc", label: "Allocated" },
];

export default function BenchResourceManagementPage() {
  const [employees, setEmployees] = useState([]);
  const [bench, setBench] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [editTarget, setEditTarget] = useState(null);
  const [historyTarget, setHistoryTarget] = useState(null);
  const toasts = useToasts();

  async function refresh() {
    setLoading(true);
    try {
      const [emps, bn, ps] = await Promise.all([
        resourceApi.getEmployees(),
        resourceApi.getBench(),
        resourceApi.getProjects(),
      ]);
      setEmployees(Array.isArray(emps) ? emps : []);
      setBench(Array.isArray(bn) ? bn : []);
      setProjects(Array.isArray(ps) ? ps : []);
    } catch (ex) {
      toasts.push(ex?.data?.detail || ex?.message || "Failed to load data", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);

  // Merge bench_duration_days from the bench list into the merged view.
  const benchByEmpId = useMemo(() => {
    const m = new Map();
    for (const b of bench) m.set(b.id, b);
    return m;
  }, [bench]);

  const rows = useMemo(() => {
    let base;
    if (tab === "bench")      base = employees.filter((e) => !e.has_active_allocation);
    else if (tab === "alloc") base = employees.filter((e) => e.has_active_allocation);
    else                       base = employees;
    const q = search.trim().toLowerCase();
    if (!q) return base;
    return base.filter((e) => {
      if ((e.name || "").toLowerCase().includes(q)) return true;
      if ((e.designation || "").toLowerCase().includes(q)) return true;
      if ((e.department || "").toLowerCase().includes(q)) return true;
      if ((e.skills || []).some((s) => (s || "").toLowerCase().includes(q))) return true;
      return false;
    });
  }, [employees, tab, search]);

  const totals = useMemo(() => {
    const total = employees.length;
    const allocated = employees.filter((e) => e.has_active_allocation).length;
    const onBench = total - allocated;
    return { total, allocated, onBench };
  }, [employees]);

  function handleSaved() {
    refresh();
    toasts.push("Saved successfully");
  }

  return (
    <div className="space-y-5 p-6">
      {toasts.node}

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-800">Bench &amp; Resource Management</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Manage bench employees, allocations and project assignments.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Total Employees", value: totals.total, color: "#1e40af", bg: "#dbeafe" },
          { label: "Allocated",       value: totals.allocated, color: "#15803d", bg: "#dcfce7" },
          { label: "On Bench",        value: totals.onBench, color: "#b45309", bg: "#fef3c7" },
        ].map((c) => (
          <div key={c.label} className="bg-white border border-slate-100 rounded-xl shadow-sm p-5">
            <p className="text-[11px] uppercase font-bold text-slate-400">{c.label}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: c.color }}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* Tabs + search */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-2">
        <div className="flex items-center gap-2">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
                    className="rounded-lg px-3 py-1.5 text-xs font-semibold transition"
                    style={{
                      background: tab === t.id ? "#1e3acb" : "transparent",
                      color: tab === t.id ? "#fff" : "#475569",
                    }}>
              {t.label}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, skill, designation…"
          className="w-full sm:w-80 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Employee", "Designation", "Experience", "Department", "Skills", "Project", "Manager", "On Bench", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-xs text-slate-400">Loading…</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-xs text-slate-400">No employees in this view.</td></tr>
              )}
              {!loading && rows.map((e) => {
                const benchDays = benchByEmpId.get(e.id)?.bench_duration_days;
                return (
                  <tr key={e.id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-700">{e.name}</p>
                      <p className="text-[11px] text-slate-400">{e.email || ""}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{e.designation || "—"}</td>
                    <td className="px-4 py-3 text-slate-600 text-xs">
                      {typeof e.experience_years === "number" ? `${e.experience_years} yr${e.experience_years === 1 ? "" : "s"}` : "—"}
                      {e.certifications && (
                        <p className="text-[10px] text-slate-400 mt-0.5 truncate" title={e.certifications}>
                          {e.certifications}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{e.department || "—"}</td>
                    <td className="px-4 py-3 max-w-[200px]">
                      <div className="flex flex-wrap gap-1">
                        {(e.skills || []).slice(0, 4).map((s) => (
                          <span key={s} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">{s}</span>
                        ))}
                        {(e.skills || []).length > 4 && (
                          <span className="text-[10px] text-slate-400">+{e.skills.length - 4}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{e.latest_project_name || "—"}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">{e.latest_manager_name || "—"}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {e.has_active_allocation ? "—" : (typeof benchDays === "number" ? `${benchDays} day(s)` : "—")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1.5">
                        <button onClick={() => setEditTarget(e)}
                                className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
                          Edit
                        </button>
                        {!e.has_active_allocation && (
                          <button onClick={() => setEditTarget(e)}
                                  className="rounded-md border border-teal-200 bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700 hover:bg-teal-100">
                            Assign
                          </button>
                        )}
                        <button onClick={() => setHistoryTarget(e)}
                                className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
                          History
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <AddEmployeeDetailsModal
        open={!!editTarget}
        employee={editTarget}
        employees={employees}
        projects={projects}
        onClose={() => setEditTarget(null)}
        onSaved={handleSaved}
      />

      <ProjectHistoryModal
        open={!!historyTarget}
        employee={historyTarget}
        onClose={() => setHistoryTarget(null)}
      />
    </div>
  );
}
