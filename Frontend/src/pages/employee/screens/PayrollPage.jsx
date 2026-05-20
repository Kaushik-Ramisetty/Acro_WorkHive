import UnderConstruction from "../../../components/UnderConstruction";

const SlipIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="12" y1="13" x2="12" y2="19" /><line x1="9" y1="16" x2="15" y2="16" />
  </svg>
);
const ChartIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
  </svg>
);
const FormIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
);

const PayrollPage = () => (
  <UnderConstruction
    accent="amber"
    title="My Payroll"
    description="Download monthly payslips, see year-to-date earnings, and access your tax statements — all from one place."
    features={[
      { label: "Monthly payslips",  icon: SlipIcon  },
      { label: "Year-to-date summary", icon: ChartIcon },
      { label: "Tax statements (Form 16)", icon: FormIcon },
    ]}
  />
);

export default PayrollPage;
