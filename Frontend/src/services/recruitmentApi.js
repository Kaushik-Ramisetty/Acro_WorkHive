/**
 * recruitmentApi.js — Manager Recruitment Module API client
 *
 * Uses the same base HTTP client (api.js / VITE_API_URL + Bearer JWT)
 * as every other core HRMS module. All endpoints live under /recruitment.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'hrms.auth.token';

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

async function request(method, path, { body } = {}) {
  const tok = getToken();
  const headers = {
    Accept: 'application/json',
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(tok ? { Authorization: 'Bearer ' + tok } : {}),
  };

  const res = await fetch(BASE_URL + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    try { data = await res.json(); } catch { data = null; }
  }

  if (!res.ok) {
    const err = new Error(
      (data && data.detail) || (data && data.message) || `HTTP ${res.status}`
    );
    err.status = res.status;
    err.data   = data;
    throw err;
  }
  return data;
}

const get    = (path)         => request('GET',   path);
const post   = (path, body)   => request('POST',  path, { body });
const patch  = (path, body)   => request('PATCH', path, { body });


// ─────────────────────────────────────────────────────────────────────────────
// Dashboard
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /recruitment/dashboard
 * Returns { open_reqs, in_pipeline, awaiting_approval, interviews_sched, positions_closed }
 */
export function getDashboardStats() {
  return get('/recruitment/dashboard');
}


// ─────────────────────────────────────────────────────────────────────────────
// Requirements
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /recruitment/requirements[?status=Active]
 * Returns array of requirement objects matching the mock REQUIREMENTS shape.
 */
export function getRequirements(statusFilter = null) {
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
  return get(`/recruitment/requirements${qs}`);
}

/**
 * GET /recruitment/requirements/:reqId
 */
export function getRequirement(reqId) {
  return get(`/recruitment/requirements/${encodeURIComponent(reqId)}`);
}

/**
 * POST /recruitment/requirements
 * payload matches RequirementCreate schema:
 * { title, department_id, employment_type, work_mode, location,
 *   min_experience, max_experience, openings, priority,
 *   skills[], pending_skills[], job_description, qualification,
 *   budget_range, target_joining }
 */
export function createRequirement(payload) {
  return post('/recruitment/requirements', payload);
}

/**
 * PATCH /recruitment/requirements/:reqId/status
 * payload: { status: 'Active' | 'In Review' | 'Sourcing' | 'Closed' }
 */
export function updateRequirementStatus(reqId, newStatus) {
  return patch(`/recruitment/requirements/${encodeURIComponent(reqId)}/status`, {
    status: newStatus,
  });
}


// ─────────────────────────────────────────────────────────────────────────────
// Pipeline / Candidates
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /recruitment/pipeline[?req=REQ-XXXX]
 * Returns all pipeline candidate objects for this manager's requirements.
 */
export function getPipeline(reqFilter = null) {
  const qs = reqFilter && reqFilter !== 'All'
    ? `?req=${encodeURIComponent(reqFilter)}`
    : '';
  return get(`/recruitment/pipeline${qs}`);
}

/**
 * POST /recruitment/pipeline/:pipelineId/approve
 * payload: { action: 'approve'|'reject', remark?, rejection_reason? }
 */
export function submitApproval(pipelineId, action, { remark = null, rejectionReason = null } = {}) {
  return post(`/recruitment/pipeline/${pipelineId}/approve`, {
    action,
    remark,
    rejection_reason: rejectionReason,
  });
}


// ─────────────────────────────────────────────────────────────────────────────
// Departments
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /recruitment/departments
 * Returns [{id, name}] — used to populate the Department dropdown dynamically.
 */
export function getDepartments() {
  return get('/recruitment/departments');
}


// ─────────────────────────────────────────────────────────────────────────────
// Skills
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /recruitment/skills
 * Returns all active skills from skill_set master table [{name}].
 * Used on initial dropdown open (no search term yet).
 */
export function getAllSkills() {
  return get('/recruitment/skills');
}

/**
 * GET /recruitment/skills/search?q=Re
 * Minimum 2 characters. Returns { results: [{name}], query, total }.
 */
export function searchSkills(query, limit = 10) {
  if (!query || query.trim().length < 2) return Promise.resolve({ results: [], query, total: 0 });
  return get(
    `/recruitment/skills/search?q=${encodeURIComponent(query.trim())}&limit=${limit}`
  );
}

/**
 * POST /recruitment/skills/request-global
 * Manager requests a brand-new skill to be added to the master.
 * Goes to HR Admin for approval — NOT inserted directly.
 * payload: { skill_name }
 */
export function requestNewSkillGlobal(skillName) {
  return post('/recruitment/skills/request-global', { skill_name: skillName });
}

/**
 * POST /recruitment/skills/request  (backward-compat — per-requirement)
 * payload: { skill_name, requirement_id, is_primary? }
 */
export function requestNewSkill(skillName, requirementId, isPrimary = false) {
  return post('/recruitment/skills/request', {
    skill_name:     skillName,
    requirement_id: requirementId,
    is_primary:     isPrimary,
  });
}

/**
 * GET /recruitment/skills/pending[?requirement_id=N]
 */
export function getPendingSkills(requirementId = null) {
  const qs = requirementId ? `?requirement_id=${requirementId}` : '';
  return get(`/recruitment/skills/pending${qs}`);
}


// ─────────────────────────────────────────────────────────────────────────────
// HR Admin — Skill requests (called from admin panel)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /admin/skill-requests[?status=pending]
 * Returns global SkillRequest rows for HR Admin approval workflow.
 * Shape: [{ id, skill_name, status, requested_by, requested_at, approved_by, rejection_reason }]
 * The page reads r.requested_at as r.created_at so we normalise below.
 */
export async function getSkillRequests(statusFilter = null) {
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
  const rows = await get(`/admin/skill-requests${qs}`);
  return Array.isArray(rows) ? rows.map(r => ({
    ...r,
    created_at: r.requested_at || r.created_at,
  })) : [];
}

/**
 * POST /admin/skill-requests/:id/approve
 * HR Admin approves a skill request — inserts into skill_set master table.
 */
export function approveSkillRequest(requestId) {
  return post(`/admin/skill-requests/${requestId}/approve`);
}

/**
 * POST /admin/skill-requests/:id/reject
 * HR Admin rejects a skill request with an optional reason.
 */
export function rejectSkillRequest(requestId, reason = null) {
  return post(`/admin/skill-requests/${requestId}/reject`, { reason });
}

/**
 * GET /admin/skill-set — full master skill list (admin view with metadata).
 * Shape: [{ id, skill_name, is_active, added_by, added_at }]
 * The page renders r.name || r for display — works with skill_name field too via the || r fallback.
 */
export async function getSkillSetMaster() {
  const rows = await get('/admin/skill-set');
  return Array.isArray(rows) ? rows.map(r => ({ ...r, name: r.skill_name })) : [];
}
