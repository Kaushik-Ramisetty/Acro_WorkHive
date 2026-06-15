/**
 * Self Service landing page — shared across admin / manager / employee
 * dashboards. All three roles see the same six sections; routing wires
 * it under /<role>-dashboard/self-service.
 *
 * Sections (View / Edit / Salary / Taxation / Quick Info / Workflow)
 * mirror the layout in the reference image. Click handlers currently
 * surface a transient banner ("Coming soon") rather than navigating —
 * the brief is explicit that this is FRONTEND ONLY with placeholder
 * navigation. Wiring real routes is a follow-up.
 */
import { useMemo, useState } from "react";
import SelfServiceSection from "../../components/selfservice/SelfServiceSection";


// Sized to match the existing dashboard icon set.
const ICON_SIZE = 18;
const Stroke = (props) => (
  <svg
    width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round"
    {...props}
  />
);

const Icons = {
  view:     <Stroke><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></Stroke>,
  edit:     <Stroke><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></Stroke>,
  salary:   <Stroke><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></Stroke>,
  taxation: <Stroke><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 9h6v6H9z" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="3" y1="15" x2="21" y2="15" /></Stroke>,
  quick:    <Stroke><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></Stroke>,
  workflow: <Stroke><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="9" y="14" width="7" height="7" rx="1" /><path d="M6.5 10v2a1.5 1.5 0 0 0 1.5 1.5h.5" /><path d="M17.5 10v2a1.5 1.5 0 0 1-1.5 1.5h-.5" /></Stroke>,
};


export default function SelfServicePage() {
  // Transient banner shown when a placeholder link is clicked. Self-clears
  // after 2.5 s so the page never accumulates stale state.
  const [banner, setBanner] = useState(null);

  const notify = (label) => {
    setBanner({ label, ts: Date.now() });
    setTimeout(() => setBanner((b) => (b && b.label === label ? null : b)), 2500);
  };

  // Section definitions mirror the reference image. Each `onClick` is a
  // placeholder until the equivalent dedicated page or modal is built;
  // when that happens, swap the body of `notify(...)` for the real
  // navigate(...) call.
  const sections = useMemo(() => [
    {
      title: "View",
      icon: Icons.view,
      links: [
        { label: "Employment",          onClick: () => notify("Employment") },
        { label: "Contact",             onClick: () => notify("Contact") },
        { label: "Personal",            onClick: () => notify("Personal") },
        { label: "Statutory",           onClick: () => notify("Statutory") },
        { label: "Bank",                onClick: () => notify("Bank") },
        { label: "Family",              onClick: () => notify("Family") },
        { label: "Nominee",             onClick: () => notify("Nominee") },
        { label: "Immigration",         onClick: () => notify("Immigration") },
        { label: "Driving Licenses",    onClick: () => notify("Driving Licenses") },
        { label: "Skills",              onClick: () => notify("Skills") },
        { label: "Languages",           onClick: () => notify("Languages") },
        { label: "Qualifications",      onClick: () => notify("Qualifications") },
        { label: "Social Details",      onClick: () => notify("Social Details") },
        { label: "Assets List",         onClick: () => notify("Assets List") },
        { label: "Previous Experience", onClick: () => notify("Previous Experience") },
        { label: "Policy",              onClick: () => notify("Policy") },
      ],
    },
    {
      title: "Edit",
      icon: Icons.edit,
      links: [
        { label: "Profile",             onClick: () => notify("Edit Profile") },
        { label: "Contact",             onClick: () => notify("Edit Contact") },
        { label: "Personal",            onClick: () => notify("Edit Personal") },
        { label: "Immigration",         onClick: () => notify("Edit Immigration") },
        { label: "Visa Details",        onClick: () => notify("Visa Details") },
        { label: "Driving License",     onClick: () => notify("Driving License") },
        { label: "Family",              onClick: () => notify("Edit Family") },
        { label: "Nominee",             onClick: () => notify("Edit Nominee") },
        { label: "Skills",              onClick: () => notify("Edit Skills") },
        { label: "Languages",           onClick: () => notify("Edit Languages") },
        { label: "Qualification",       onClick: () => notify("Edit Qualification") },
        { label: "Previous Experience", onClick: () => notify("Edit Previous Experience") },
      ],
    },
    {
      title: "Salary",
      icon: Icons.salary,
      links: [
        { label: "CTC",                  onClick: () => notify("CTC") },
        { label: "Download CTC",         onClick: () => notify("Download CTC") },
        { label: "Payslip",              onClick: () => notify("Payslip") },
        { label: "Download Payslip",     onClick: () => notify("Download Payslip") },
        { label: "Monthly Report",       onClick: () => notify("Monthly Report") },
        { label: "Download PF Card",     onClick: () => notify("Download PF Card") },
      ],
    },
    {
      title: "Taxation",
      icon: Icons.taxation,
      links: [
        { label: "View Tax Eligibility",  onClick: () => notify("Tax Eligibility") },
        { label: "Tax Projection",        onClick: () => notify("Tax Projection") },
        { label: "Download Tax Projection", onClick: () => notify("Download Tax Projection") },
        { label: "Download Form 16",      onClick: () => notify("Form 16") },
        { label: "Edit Tax Eligibility",  onClick: () => notify("Edit Tax Eligibility") },
        { label: "Add Declaration",       onClick: () => notify("Add Declaration") },
        { label: "Submit Tax Declaration", onClick: () => notify("Submit Tax Declaration") },
        { label: "Add Investment / Claim", onClick: () => notify("Add Investment / Claim") },
        { label: "Previous Employer Form 16", onClick: () => notify("Previous Employer Form 16") },
      ],
    },
    {
      title: "Quick Info",
      icon: Icons.quick,
      links: [
        { label: "Leave Balances",     onClick: () => notify("Leave Balances") },
        { label: "Loan Details",       onClick: () => notify("Loan Details") },
        { label: "Reimbursement Details", onClick: () => notify("Reimbursement Details") },
        { label: "Holiday List",       onClick: () => notify("Holiday List") },
        { label: "My Documents",       onClick: () => notify("My Documents") },
        { label: "Employee Search",    onClick: () => notify("Employee Search") },
        { label: "Tax Calculator",     onClick: () => notify("Tax Calculator") },
        { label: "Photo Gallery",      onClick: () => notify("Photo Gallery") },
        { label: "Survey",             onClick: () => notify("Survey") },
        { label: "Add Quick Links",    onClick: () => notify("Add Quick Links") },
      ],
    },
    {
      title: "Workflow",
      icon: Icons.workflow,
      links: [
        { label: "My Approvers",        onClick: () => notify("My Approvers") },
        { label: "My Workflow",         onClick: () => notify("My Workflow") },
        { label: "Organization Chart",  onClick: () => notify("Organization Chart") },
        { label: "ORG Chart Corporate View", onClick: () => notify("ORG Chart Corporate View") },
      ],
    },
  ], []);

  return (
    <div className="space-y-4">
      {/* Transient "coming soon" banner. Lives at the top of the page so
          it's visible regardless of where the user clicked. */}
      {banner && (
        <div
          className="rounded-lg px-4 py-2 text-xs font-semibold border"
          style={{ background: "#f0fdfa", color: "#0f766e", borderColor: "#99f6e4" }}
          role="status"
        >
          “{banner.label}” — coming soon. This action will be wired up in a follow-up.
        </div>
      )}

      <SelfServiceSection sections={sections} title="Self Service" />
    </div>
  );
}
