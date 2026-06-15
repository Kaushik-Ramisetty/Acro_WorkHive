const CARD = {
  background: 'var(--hrms-surface)', border: '0.5px solid var(--hrms-border)',
  borderRadius: 8, padding: '0.5rem 0.875rem', marginBottom: '0.625rem',
};

const SEL = {
  fontSize: 12, padding: '4px 8px', borderRadius: 5,
  border: '0.5px solid var(--hrms-border)', background: 'var(--hrms-surface-2)',
  color: 'var(--hrms-text-2)', cursor: 'pointer', outline: 'none', fontFamily: 'inherit',
};

export default function FilterBar({ entries, filters, onChange }) {
  const clients  = [...new Set(entries.map((e) => e.client).filter(Boolean))];
  const projects = [...new Set(entries.map((e) => e.project).filter(Boolean))];
  const hasFilter = filters.client || filters.project || filters.status;

  return (
    <div style={CARD}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--hrms-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em', marginRight: 2 }}>
          Filter
        </span>

        <select
          value={filters.client}
          onChange={(e) => onChange({ ...filters, client: e.target.value })}
          style={SEL}
        >
          <option value="">All clients</option>
          {clients.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        <select
          value={filters.project}
          onChange={(e) => onChange({ ...filters, project: e.target.value })}
          style={SEL}
        >
          <option value="">All projects</option>
          {projects.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>

        <select
          value={filters.status}
          onChange={(e) => onChange({ ...filters, status: e.target.value })}
          style={SEL}
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="approved">Approved</option>
        </select>

        {hasFilter && (
          <button
            onClick={() => onChange({ client: '', project: '', status: '' })}
            style={{ fontSize: 11, color: 'var(--hrms-text-faint)', background: 'none', border: 'none', cursor: 'pointer', padding: '3px 4px' }}
          >
            ✕ Clear
          </button>
        )}
      </div>
    </div>
  );
}
