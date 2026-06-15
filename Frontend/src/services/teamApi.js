// Team-management API client.
//
// Backend surface (mounted at /admin/teams* and /manager/teams*):
//   GET    /admin/teams/summary
//   GET    /admin/teams
//   GET    /admin/teams/{id}
//   POST   /admin/teams
//   PUT    /admin/teams/{id}
//   DELETE /admin/teams/{id}
//   POST   /admin/teams/{id}/members
//   DELETE /admin/teams/{id}/members/{employee_id}
//   POST   /admin/teams/{from}/members/{employee_id}/transfer-to/{to}
//
//   GET    /manager/teams              (lists teams the caller leads)
//   GET    /manager/teams/{id}
//   POST   /manager/teams/{id}/members
//   DELETE /manager/teams/{id}/members/{employee_id}
import { api } from "./api";

function qs(params) {
  if (!params) return "";
  const e = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "" && v !== false,
  );
  if (!e.length) return "";
  return "?" + e.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
}

export const teamApi = {
  // ---- Admin ----------------------------------------------------
  summary:        ()                   => api.get("/admin/teams/summary"),
  list:           (params)             => api.get("/admin/teams" + qs(params)),
  detail:         (id)                 => api.get("/admin/teams/" + id),
  create:         (payload)            => api.post("/admin/teams", payload),
  update:         (id, payload)        => api.put("/admin/teams/" + id, payload),
  remove:         (id)                 => api.delete("/admin/teams/" + id),
  addMember:      (id, payload)        => api.post("/admin/teams/" + id + "/members", payload),
  removeMember:   (id, employeeId)     => api.delete("/admin/teams/" + id + "/members/" + employeeId),
  transferMember: (fromId, employeeId, toId, role) =>
    api.post("/admin/teams/" + fromId + "/members/" + employeeId + "/transfer-to/" + toId + qs({ role_in_team: role })),

  // ---- Manager (team lead) --------------------------------------
  myTeams:           ()                       => api.get("/manager/teams"),
  myTeamDetail:      (id)                     => api.get("/manager/teams/" + id),
  myAddMember:       (id, payload)            => api.post("/manager/teams/" + id + "/members", payload),
  myRemoveMember:    (id, employeeId)         => api.delete("/manager/teams/" + id + "/members/" + employeeId),
};
