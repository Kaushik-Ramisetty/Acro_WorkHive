/**
 * recruiterApi.js — Recruiter Dashboard API client
 * All endpoints live under /recruiter (prefix).
 * Uses the same BASE_URL + Bearer JWT pattern as api.js.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'hrms.auth.token';

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

async function request(method, path, { body, isFormData } = {}) {
  const tok = getToken();
  const headers = {
    Accept: 'application/json',
    ...(tok ? { Authorization: 'Bearer ' + tok } : {}),
    ...(body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
  };
  const res = await fetch(BASE_URL + path, {
    method,
    headers,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) { try { data = await res.json(); } catch { data = null; } }
  if (!res.ok) {
    const err = new Error((data && data.detail) || (data && data.message) || `HTTP ${res.status}`);
    err.status = res.status; err.data = data; throw err;
  }
  return data;
}

const get  = (path)         => request('GET',   path);
const post = (path, body, opts) => request('POST', path, { body, ...opts });
const patch = (path, body)  => request('PATCH', path, { body });

// ─── Dashboard ───────────────────────────────────────────────────────────────
export const getStats = () => get('/recruiter/stats');

// ─── Interviews ──────────────────────────────────────────────────────────────
export const getActiveInterviews   = () => get('/recruiter/interviews/active');
export const getUpcomingInterviews = () => get('/recruiter/interviews/upcoming');
export const getAllInterviews       = (roundType = null) => {
  const qs = roundType ? `?round=${encodeURIComponent(roundType)}` : '';
  return get(`/recruiter/interviews${qs}`);
};
export const rescheduleInterview = (roundId, payload) =>
  post(`/recruiter/interviews/${roundId}/reschedule`, payload);
export const overrideInterview = (roundId, payload) =>
  post(`/recruiter/interviews/${roundId}/override`, payload);
export const addRound = (pipelineId, payload) =>
  post(`/recruiter/pipeline/${pipelineId}/add-round`, payload);

// ─── Candidates ──────────────────────────────────────────────────────────────
export const getCandidates = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
  ).toString();
  return get(`/recruiter/candidates${qs ? '?' + qs : ''}`);
};
export const getCandidateDetail = (candidateId) =>
  get(`/recruiter/candidates/${encodeURIComponent(candidateId)}`);
export const checkCandidateDuplicate = (payload) =>
  post('/recruiter/candidates/check-duplicate', payload);
export const addCandidate = (formData) =>
  post('/recruiter/candidates', formData, { isFormData: true });
export const updateNotes = (candidateId, notes) =>
  patch(`/recruiter/candidates/${encodeURIComponent(candidateId)}/notes`, { notes });

// ─── Requirements ────────────────────────────────────────────────────────────
export const getRequirements = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
  ).toString();
  return get(`/recruiter/requirements${qs ? '?' + qs : ''}`);
};
export const getOpenRequirements = () => get('/recruiter/requirements?exclude_closed=true');
export const getRequirementDetail = (reqId) =>
  get(`/recruiter/requirements/${encodeURIComponent(reqId)}`);
export const createRequirement = (payload) =>
  post('/recruiter/requirements', payload);
export const updateRequirement = (reqId, payload) =>
  patch(`/recruiter/requirements/${encodeURIComponent(reqId)}`, payload);
export const closeRequirement = (reqId) =>
  patch(`/recruiter/requirements/${encodeURIComponent(reqId)}/close`, {});

/**
 * POST /recruiter/requirements/{reqId}/assign-recruiter
 * Admin/HR only — assign or reassign a recruiter to a requirement.
 */
export function assignRecruiter(reqId, recruiterId) {
  return post(`/recruiter/requirements/${encodeURIComponent(reqId)}/assign-recruiter`, { recruiter_id: recruiterId });
}

/**
 * GET /recruiter/recruiters
 * List active employees available as recruiter assignments (for dropdown).
 */
export function getRecruiters() {
  return get('/recruiter/recruiters');
}

// ─── Skills (delegates to /recruitment/ which already allows employee role) ──
export const getAllSkills = () => get('/recruitment/skills');
export const searchSkillsApi = (query, limit = 15) =>
  get(`/recruitment/skills/search?q=${encodeURIComponent(query)}&limit=${limit}`);
export const getDepartments = () => get('/recruitment/departments');

// ─── Pipeline ────────────────────────────────────────────────────────────────
export const getPipeline = (reqFilter = null) => {
  const qs = reqFilter && reqFilter !== 'All' ? `?req=${encodeURIComponent(reqFilter)}` : '';
  return get(`/recruiter/pipeline${qs}`);
};

// ─── Reference ───────────────────────────────────────────────────────────────
export const getInterviewers = () => get('/recruiter/interviewers');

/**
 * POST /recruiter/interviews/assign
 * Recruiter assigns an interviewer to an approved candidate (first-time scheduling).
 * payload: { candidate_id, round_name, round_type, interviewer_code }
 */
export function assignInterviewer(payload) {
  return post('/recruiter/interviews/assign', payload);
}

/**
 * POST /recruiter/candidates/{candidateId}/close-and-onboard
 * Admin/HR only — close the recruitment process and push the candidate into
 * the onboarding module.  Returns { message, onboarding_candidate_id, onboarding_ref }.
 */
export function closeAndOnboard(candidateId) {
  return post(`/recruiter/candidates/${encodeURIComponent(candidateId)}/close-and-onboard`);
}
