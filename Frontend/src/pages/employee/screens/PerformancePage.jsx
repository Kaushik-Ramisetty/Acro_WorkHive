import UnderConstruction from "../../../components/UnderConstruction";

// Tiny inline icons for the "What's coming" grid.
const StarIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);
const TargetIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
  </svg>
);
const ChatIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const PerformancePage = () => (
  <UnderConstruction
    accent="teal"
    title="Performance Reviews"
    description="Track your goals, review history, and incoming feedback in one place. We're putting the finishing touches on it."
    features={[
      { label: "Goals & OKRs tracker",   icon: TargetIcon },
      { label: "Quarterly review history", icon: StarIcon },
      { label: "360° peer feedback",     icon: ChatIcon },
    ]}
  />
);

export default PerformancePage;
