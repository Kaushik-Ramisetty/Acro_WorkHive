const PlaceholderPage = ({ title }) => {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
      <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: "#f0fdfa" }}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
        </svg>
      </div>
      <h2 className="text-lg font-bold text-slate-700">{title}</h2>
      <p className="text-sm text-slate-400">This page is under construction.</p>
    </div>
  );
};

export default PlaceholderPage;
