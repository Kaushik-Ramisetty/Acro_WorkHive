import UnderConstruction from '../../components/UnderConstruction';

const _icoDoc      = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>);
const _icoActivity = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>);
const _icoCalendar = (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>);

export default function ReportsPage() {
  return (
    <UnderConstruction
      accent="teal"
      title="Reports & Exports"
      description="Custom and saved reports for financial analytics with rich filters, scheduled delivery, and PDF/CSV exports."
      features={[
        { label: 'Saved report library', icon: _icoDoc      },
        { label: 'Ad-hoc query builder', icon: _icoActivity },
        { label: 'Scheduled exports',    icon: _icoCalendar },
      ]}
    />
  );
}
