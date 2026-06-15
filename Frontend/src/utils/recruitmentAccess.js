/**
 * recruitmentAccess.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Single source of truth for Recruitment and Skill-Set access control.
 *
 * ACCESS MATRIX
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * canAccessRecruitment(user)
 *   TRUE  when: role === "recruiter"
 *            OR designation IN ["recruiter", "recruitment manager"]
 *   FALSE for everyone else (plain employees, managers, admins, candidates)
 *
 *   Note: Admins reach recruitment via /admin-dashboard/recruitment directly
 *   and do not rely on this guard. This guard covers the employee-dashboard
 *   sidebar and page-map only.
 *
 * canAccessSkillApproval(user)
 *   TRUE  when: role === "admin"
 *   FALSE for everyone else
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * VALIDATION MATRIX
 * ─────────────────────────────────────────────────────────────────────────────
 *
 *  User   role       designation          Recruitment  SkillApproval
 *  ─────  ─────────  ───────────────────  ───────────  ─────────────
 *  A      recruiter  (any)                ✓            ✗
 *  B      employee   Recruiter            ✓            ✗
 *  C      employee   Recruitment Manager  ✓            ✗
 *  D      admin      (any)                via /admin   ✓
 *  E      employee   (other)              ✗            ✗
 *  F      manager    (any)                ✗            ✗
 */

/**
 * canAccessRecruitment
 *
 * Grants access to the Recruitment module in the employee dashboard
 * (sidebar visibility + page-map guard).
 *
 * @param {object|null} user  Object from useAuth() / GET /auth/me
 * @returns {boolean}
 */
export function canAccessRecruitment(user) {
  if (!user) return false;

  const role  = (user.role        || "").toLowerCase().trim();
  const desig = (user.designation || "").toLowerCase().trim();

  return (
    role === "recruiter" ||
    role === "hr" ||
    desig === "recruiter" ||
    desig === "recruitment manager"
  );
}

/**
 * canAccessSkillApproval
 *
 * Grants access to the Skill Set tab inside Recruitment
 * (approve/reject skill requests + master skill list).
 *
 * Only Admin users may manage skills.
 *
 * @param {object|null} user  Object from useAuth() / GET /auth/me
 * @returns {boolean}
 */
export function canAccessSkillApproval(user) {
  if (!user) return false;

  const role = (user.role || "").toLowerCase().trim();
  return role === "admin";
}

/**
 * canCloseAndOnboard
 *
 * Grants access to the "Close & Onboard" action on recruitment candidates.
 * Only Admin and HR roles may bypass the recruitment pipeline and push a
 * candidate directly into the onboarding module.
 *
 * Recruiter and Interviewer cannot use this action.
 *
 * @param {object|null} user  Object from useAuth() / GET /auth/me
 * @returns {boolean}
 */
/**
 * canAssignRecruiter
 *
 * Controls who may assign or reassign a recruiter to a requirement.
 * Only Admin and HR Head have this authority.
 *
 * @param {object|null} user  Object from useAuth() / GET /auth/me
 * @returns {boolean}
 */
export function canAssignRecruiter(user) {
  if (!user) return false;
  const role = (user.role || "").toLowerCase().trim();
  return role === "admin" || role === "hr";
}

export function canCloseAndOnboard(user) {
  if (!user) return false;

  const role = (user.role || "").toLowerCase().trim();
  return role === "admin" || role === "hr";
}
