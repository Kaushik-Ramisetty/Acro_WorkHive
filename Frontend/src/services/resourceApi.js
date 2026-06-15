// Resource-management API client (bench + team views).
//
// Backends:
//   /admin/resource-employees   — full employee+allocation list (note the
//                                 'resource-' prefix; the path is chosen
//                                 specifically to avoid collision with the
//                                 pre-existing /admin/employees endpoint).
//   /admin/bench                — bench list with bench_duration_days
//   /admin/employee/{id}/projects        — project history (deduped by name)
//   /admin/employee/{id}/resource-details — save skills + allocation
//   /admin/reassign             — atomic move between projects
//   /admin/projects             — list / create projects
//   /admin/create-and-assign    — single shot: create project + assign
//   /admin/assign-employee      — assign to existing project
//   /admin/bench-employees      — lightweight bench list for dropdowns
//   /manager/team               — one row per active allocation
//   /manager/release-employee   — release from a single project
//   /manager/extend-project     — extend project end_date (cascades)
import { api } from "./api";

function qs(params) {
  if (!params) return "";
  const e = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "" && v !== false,
  );
  if (!e.length) return "";
  return (
    "?" +
    e
      .map(
        ([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v),
      )
      .join("&")
  );
}

export const resourceApi = {
  // ---- Admin: bench + employees ---------------------------------
  getEmployees:        ()             => api.get("/admin/resource-employees"),
  getBench:            ()             => api.get("/admin/bench"),
  getEmployeeProjects: (id)           => api.get("/admin/employee/" + id + "/projects"),
  saveEmployeeDetails: (id, payload)  => api.put("/admin/employee/" + id + "/resource-details", payload),
  reassign:            (payload)      => api.post("/admin/reassign", payload),

  // ---- Admin: projects + assign flows ---------------------------
  createProject:       (payload)      => api.post("/admin/projects", payload),
  getProjects:         (params)       => api.get("/admin/projects" + qs(params)),
  createAndAssign:     (payload)      => api.post("/admin/create-and-assign", payload),
  assignEmployee:      (payload)      => api.post("/admin/assign-employee", payload),
  getBenchList:        ()             => api.get("/admin/bench-employees"),

  // ---- Manager: team + actions ----------------------------------
  getTeam:             ()             => api.get("/manager/team"),
  releaseEmployee:     (payload)      => api.post("/manager/release-employee", payload),
  extendProject:       (payload)      => api.put("/manager/extend-project", payload),
};
