import UnderConstruction from "../../../components/UnderConstruction";

const BookIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);
const PathIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="6" cy="6" r="3" /><circle cx="18" cy="18" r="3" /><path d="M9 6h7a3 3 0 0 1 3 3v6" />
  </svg>
);
const AwardIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="8" r="6" /><path d="M15.5 13.5l1.5 7-5-3-5 3 1.5-7" />
  </svg>
);

const TrainingPage = () => (
  <UnderConstruction
    accent="violet"
    title="Training & Learning"
    description="A curated course catalog, your active learning paths, and the certificates you've earned — all coming together."
    features={[
      { label: "Curated course catalog",       icon: BookIcon },
      { label: "Personalized learning paths",  icon: PathIcon },
      { label: "Certificates & badges",        icon: AwardIcon },
    ]}
  />
);

export default TrainingPage;
