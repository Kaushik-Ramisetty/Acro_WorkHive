/**
 * Admin Team Management page.
 *
 * Surfaces:
 *   - Summary cards: total teams / members / active projects / departments
 *     covered.
 *   - Teams table with search, lead, member count, active-project count.
 *   - Modals for create/edit team, manage members, transfer member.
 */
import { useEffect, useMemo, useState } from "react";
import { teamApi } from "../../../services/teamApi";
import { resourceApi } from "../../../services/resourceApi";

// Reusable toast hook (same shape used by the bench page).
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
        <div key={t.id}
             className="rounded-lg px-4 py-2 text-xs font-semibold shadow-md"
             style={{
               background: t.tone === "error" ? "#fef2f2" : "#f0fdf4",
               color: t.tone === "error" ? "#b91c1c" : "#15803d",
               border: t.tone === "error" ? "1px solid #fecaca" : "1px solid #bbf7d0",
             }}>
          {t.message}
        </div>
      ))}
    </div>
  );
  return { push, node };
}

// Manager-like designations get the "Lead" candidates list.
const LEAD_RE = /\b(senior manager|engineering manager|manager|lead)\b/i;


// ---------------------------------------------------------------
// Create/Edit team modal
// ---------------------------------------------------------------
function TeamFormModal({ open, onClose, onSaved, team, employees }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [leadId, setLeadId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(team?.name || "");
    setDescription(team?.description || "");
    setDepartmentId(team?.department_id || "");
    setLeadId(team?.lead_id ? String(team.lead_id) : "");
    setError("");
  }, [open, team]);

  const departments = useMemo(() => {
    // Distinct list of (id, name) from employees.
    const seen = new Map();
    for (const e of (employees || [])) {
      if (e.department && !seen.has(e.department)) {
        // We don't have department_id on the employee payload; we render
        // the name only and rely on backend matching by id. Since the
        // create-team form needs an id, we'll require admin to leave dept
        // blank for now if no FK is known. (Backend accepts null.)
        seen.set(e.department, e.department);
      }
    }
    return Array.from(seen.values()).sort();
  }, [employees]);

  const leadOptions = useMemo(
    () => (employees || []).filter((e) => LEAD_RE.test(e.designation || "")),
    [employees],
  );

  async function save() {
    setBusy(true); setError("");
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        department_id: departmentId.trim() || null,
        lead_id: leadId ? Number(leadId) : null,
      };
      if (team?.id) {
        await teamApi.update(team.id, payload);
      } else {
        await teamApi.create({ ...payload, member_ids: [] });
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
           className="bg-white rounded-2xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-800">{team?.id ? "Edit team" : "Create team"}</h3>
          <button onClick={onClose} className="rounded-full bg-slate-100 hover:bg-slate-200 w-8 h-8">×</button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Team name <span className="text-red-400">*</span></label>
            <input value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="e.g. Platform Squad"
                   className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                      rows={2}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Department</label>
              <input value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}
                     placeholder="DEP001 (optional)"
                     className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Team Lead</label>
              <select value={leadId} onChange={(e) => setLeadId(e.target.value)}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
                <option value="">— None —</option>
                {leadOptions.map((e) => (
                  <option key={e.id} value={e.id}>{e.name} — {e.designation || "Manager"}</option>
                ))}
              </select>
            </div>
          </div>
          {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>}
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button onClick={onClose} disabled={busy}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button onClick={save} disabled={busy || !name.trim()}
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
// Manage Members modal
// ---------------------------------------------------------------
function MembersModal({ open, onClose, team, employees, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [addId, setAddId] = useState("");
  const [addRole, setAddRole] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function reload() {
    if (!team?.id) return;
    setLoading(true);
    try { setDetail(await teamApi.detail(team.id)); }
    catch (ex) { setError(ex?.data?.detail || ex?.message || "Load failed"); }
    finally { setLoading(false); }
  }

  useEffect(() => { if (open) { setError(""); setAddId(""); setAddRole(""); reload(); } /* eslint-disable-next-line */ }, [open, team]);

  const memberIds = useMemo(() => new Set((detail?.members || []).map((m) => m.employee_id)), [detail]);
  const candidates = useMemo(
    () => (employees || []).filter((e) => !memberIds.has(e.id)),
    [employees, memberIds],
  );

  async function add() {
    if (!addId) return;
    setBusy(true); setError("");
    try {
      await teamApi.addMember(team.id, {
        employee_id: Number(addId),
        role_in_team: addRole.trim() || null,
      });
      setAddId(""); setAddRole("");
      await reload();
      onChanged?.();
    } catch (ex) { setError(ex?.data?.detail || ex?.message || "Add failed"); }
    finally { setBusy(false); }
  }

  async function remove(employeeId) {
    if (!window.confirm("Remove this member from the team?")) return;
    setBusy(true); setError("");
    try {
      await teamApi.removeMember(team.id, employeeId);
      await reload();
      onChanged?.();
    } catch (ex) { setError(ex?.data?.detail || ex?.message || "Remove failed"); }
    finally { setBusy(false); }
  }

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
         style={{ background: "rgba(15,28,46,0.55)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className="bg-white rounded-2xl w-full max-w-2xl mx-4 shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-800">Manage members</h3>
            <p className="text-xs text-slate-400 mt-0.5">{team?.name}</p>
          </div>
          <button onClick={onClose} className="rounded-full bg-slate-100 hover:bg-slate-200 w-8 h-8">×</button>
        </div>
        <div className="px-6 py-5 max-h-[70vh] overflow-y-auto space-y-4">
          {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>}

          {/* Add member */}
          <div className="rounded-lg border border-slate-100 p-3">
            <p className="text-xs font-semibold text-slate-600 mb-2">Add member</p>
            <div className="grid grid-cols-[1fr_140px_auto] gap-2">
              <select value={addId} onChange={(e) => setAddId(e.target.value)}
                      className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
                <option value="">Select employee</option>
                {candidates.map((e) => (
                  <option key={e.id} value={e.id}>{e.name} — {e.designation || "—"}</option>
                ))}
              </select>
              <input value={addRole} onChange={(e) => setAddRole(e.target.value)}
                     placeholder="Role on team"
                     className="border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              <button onClick={add} disabled={busy || !addId}
                      className="rounded-lg px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
                      style={{ background: "#14b8a6" }}>
                Add
              </button>
            </div>
          </div>

          {/* Existing members */}
          <div>
            <p className="text-xs font-semibold text-slate-600 mb-2">Current members ({(detail?.members || []).length})</p>
            {loading && <p className="text-xs text-slate-400">Loading…</p>}
            {!loading && (detail?.members || []).length === 0 && (
              <p className="text-xs text-slate-400">No members yet.</p>
            )}
            {!loading && (detail?.members || []).map((m) => (
              <div key={m.id} className="flex items-center justify-between border-t border-slate-100 py-2">
                <div>
                  <p className="text-sm font-semibold text-slate-700">{m.employee_name}</p>
                  <p className="text-[11px] text-slate-400">
                    {m.designation || "—"}{m.role_in_team ? ` · ${m.role_in_team}` : ""}
                  </p>
                </div>
                <button onClick={() => remove(m.employee_id)} disabled={busy}
                        className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-rose-600 hover:bg-rose-50">
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
        <div className="px-6 py-3 border-t border-slate-100 flex justify-end">
          <button onClick={onClose}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------
// Main page
// ---------------------------------------------------------------
export default function TeamManagementPage() {
  const [teams, setTeams] = useState([]);
  const [summary, setSummary] = useState({ total_teams: 0, total_members: 0, active_projects: 0, departments_with_teams: 0 });
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editTarget, setEditTarget] = useState(null);
  const [membersTarget, setMembersTarget] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const toasts = useToasts();

  async function refresh() {
    setLoading(true);
    try {
      const [t, s, emps] = await Promise.all([
        teamApi.list(),
        teamApi.summary(),
        resourceApi.getEmployees(),
      ]);
      setTeams(Array.isArray(t) ? t : []);
      setSummary(s || { total_teams: 0, total_members: 0, active_projects: 0, departments_with_teams: 0 });
      setEmployees(Array.isArray(emps) ? emps : []);
    } catch (ex) {
      toasts.push(ex?.data?.detail || ex?.message || "Failed to load", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return teams;
    return teams.filter((t) =>
      (t.name || "").toLowerCase().includes(q)
      || (t.lead_name || "").toLowerCase().includes(q)
      || (t.department_name || "").toLowerCase().includes(q)
    );
  }, [teams, search]);

  async function handleDelete(team) {
    if (!window.confirm(`Archive team "${team.name}"?`)) return;
    try {
      await teamApi.remove(team.id);
      toasts.push("Team archived");
      refresh();
    } catch (ex) {
      toasts.push(ex?.data?.detail || ex?.message || "Delete failed", "error");
    }
  }

  return (
    <div className="space-y-5 p-6">
      {toasts.node}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Team Management</h1>
          <p className="text-xs text-slate-400 mt-0.5">Create teams, assign leads, and manage members.</p>
        </div>
        <button onClick={() => setCreateOpen(true)}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white"
                style={{ background: "#14b8a6" }}>
          + New team
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Teams",       value: summary.total_teams,            color: "#1e40af" },
          { label: "Total Members",     value: summary.total_members,          color: "#15803d" },
          { label: "Active Projects",   value: summary.active_projects,        color: "#b45309" },
          { label: "Departments",       value: summary.departments_with_teams, color: "#7c3aed" },
        ].map((c) => (
          <div key={c.label} className="bg-white border border-slate-100 rounded-xl shadow-sm p-5">
            <p className="text-[11px] uppercase font-bold text-slate-400">{c.label}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: c.color }}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <div>
        <input value={search} onChange={(e) => setSearch(e.target.value)}
               placeholder="Search teams, leads, departments…"
               className="w-full sm:w-96 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Team", "Lead", "Department", "Members", "Active Projects", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-xs text-slate-400">Loading…</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-xs text-slate-400">No teams yet.</td></tr>
              )}
              {!loading && filtered.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-slate-700">{t.name}</p>
                    <p className="text-[11px] text-slate-400">{t.description || ""}</p>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">{t.lead_name || "— Unassigned —"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{t.department_name || t.department_id || "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-700 font-semibold">{t.member_count}</td>
                  <td className="px-4 py-3 text-xs text-slate-700 font-semibold">{t.active_project_count}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1.5">
                      <button onClick={() => setEditTarget(t)}
                              className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
                        Edit
                      </button>
                      <button onClick={() => setMembersTarget(t)}
                              className="rounded-md border border-teal-200 bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700 hover:bg-teal-100">
                        Members
                      </button>
                      <button onClick={() => handleDelete(t)}
                              className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100">
                        Archive
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <TeamFormModal
        open={createOpen || !!editTarget}
        team={editTarget}
        employees={employees}
        onClose={() => { setCreateOpen(false); setEditTarget(null); }}
        onSaved={() => { refresh(); toasts.push("Saved successfully"); }}
      />

      <MembersModal
        open={!!membersTarget}
        team={membersTarget}
        employees={employees}
        onChanged={refresh}
        onClose={() => setMembersTarget(null)}
      />
    </div>
  );
}
