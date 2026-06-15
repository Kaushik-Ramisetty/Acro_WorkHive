/**
 * Recruitment.jsx — Admin Dashboard Recruitment screen
 *
 * All admins see the full RecruitmentPage. The Skill Set tab inside
 * RecruitmentPage is conditionally shown based on canAccessSkillApproval
 * (role === "admin"), so every admin automatically gets it.
 *
 * HR Head-specific routing has been removed. There is no longer a separate
 * Skill Set Approval standalone page for admins.
 */
import RecruitmentPage from '../../employee/screens/RecruitmentPage';

export default function Recruitment() {
  return <RecruitmentPage />;
}
