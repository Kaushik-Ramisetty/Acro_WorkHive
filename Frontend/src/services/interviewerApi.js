/**
 * interviewerApi.js
 * Frontend API client for the Interviewer Dashboard.
 * Token is stored under 'hrms.auth.token' — same key used by all other API services.
 */

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN_KEY = "hrms.auth.token";

function authHeaders() {
  let token = null;
  try { token = localStorage.getItem(TOKEN_KEY); } catch { /* noop */ }
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: authHeaders(),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      detail = json.detail || JSON.stringify(json) || detail;
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}

export const interviewerApi = {
  /** Overview stat cards */
  getStats: () => request("GET", "/interviewer/stats"),

  /** All rounds assigned to the logged-in interviewer */
  getAssignments: () => request("GET", "/interviewer/assignments"),

  /** Upcoming scheduled interviews (today onwards) */
  getUpcoming: () => request("GET", "/interviewer/upcoming"),

  /** Calendar events (rounds with a scheduled date) */
  getCalendar: () => request("GET", "/interviewer/calendar"),

  /** Feedback history submitted by this interviewer */
  getFeedbackHistory: () => request("GET", "/interviewer/feedback-history"),

  /**
   * Add available time slots for a round.
   * @param {number} roundId
   * @param {Array<{slot_date: string, slot_time: string}>} slots
   */
  addSlots: (roundId, slots) =>
    request("POST", `/interviewer/rounds/${roundId}/slots`, { slots }),

  /**
   * Submit interview feedback for a round.
   * @param {number} roundId
   * @param {{ technical_rating, comm_rating, problem_rating, recommendation, notes }} data
   */
  submitFeedback: (roundId, data) =>
    request("POST", `/interviewer/rounds/${roundId}/feedback`, data),
};
