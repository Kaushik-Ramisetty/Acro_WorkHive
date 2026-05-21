// Shared primitives for all Finance pages.
// Uses --hrms-* CSS variables for theme compatibility (light + dark mode).
export const FONT = "'DM Sans', system-ui, sans-serif";

export function fmtIso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function monthStart() { const d = new Date(); d.setDate(1); return fmtIso(d); }
export function today() { return fmtIso(new Date()); }
export function fmtCurrency(n) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);
}

export function SectionTitle({ children }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--hrms-text)', marginBottom: 14, fontFamily: FONT }}>
      {children}
    </div>
  );
}

export function StatCard({ label, value, sub, color = '#1D4ED8', bg = '#EFF6FF' }) {
  return (
    <div style={{ flex: 1, minWidth: 130, padding: '16px 18px', borderRadius: 12,
      background: bg, textAlign: 'center', fontFamily: FONT }}>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--hrms-text-muted)', marginTop: 3, fontWeight: 600 }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--hrms-text-faint)', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export function DateRangeBar({ start, end, onStart, onEnd, onRefresh, loading, extra }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 18, flexWrap: 'wrap' }}>
      <div>
        <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)', display: 'block',
          marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>From</label>
        <input type="date" value={start} onChange={(e) => onStart(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--hrms-border)', borderRadius: 8,
            fontSize: 12, fontFamily: FONT, background: 'var(--hrms-surface)', color: 'var(--hrms-text)' }} />
      </div>
      <div>
        <label style={{ fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)', display: 'block',
          marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>To</label>
        <input type="date" value={end} onChange={(e) => onEnd(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--hrms-border)', borderRadius: 8,
            fontSize: 12, fontFamily: FONT, background: 'var(--hrms-surface)', color: 'var(--hrms-text)' }} />
      </div>
      {extra}
      <button onClick={onRefresh} disabled={loading}
        style={{ padding: '8px 18px', background: '#0F172A', color: '#fff', border: 'none',
          borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: FONT,
          opacity: loading ? 0.6 : 1 }}>
        {loading ? 'Loading…' : 'Apply'}
      </button>
    </div>
  );
}

export function DataTable({ cols, rows, emptyMsg = 'No data.' }) {
  return (
    <div style={{ border: '1px solid var(--hrms-border)', borderRadius: 10, overflow: 'hidden',
      background: 'var(--hrms-surface)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: FONT }}>
        <thead>
          <tr style={{ background: 'var(--hrms-surface-2)', borderBottom: '1px solid var(--hrms-border)' }}>
            {cols.map((c) => (
              <th key={c.key} style={{
                padding: '10px 14px', textAlign: c.right ? 'right' : 'left',
                fontSize: 10, fontWeight: 700, color: 'var(--hrms-text-muted)',
                textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap',
              }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={cols.length} style={{ padding: 28, textAlign: 'center',
                color: 'var(--hrms-text-faint)', fontSize: 13 }}>
                {emptyMsg}
              </td>
            </tr>
          )}
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderTop: '1px solid var(--hrms-border)' }}>
              {cols.map((c) => (
                <td key={c.key} style={{
                  padding: '11px 14px', textAlign: c.right ? 'right' : 'left',
                  fontWeight: c.bold ? 700 : 400,
                  color: c.color || 'var(--hrms-text-2)',
                  whiteSpace: 'nowrap',
                }}>
                  {c.render ? c.render(row) : (row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div style={{ background: '#FEE2E2', color: '#B91C1C', padding: '10px 14px',
      borderRadius: 8, fontSize: 12, marginBottom: 16, fontFamily: FONT }}>
      {message}
    </div>
  );
}

export function EmptyPrompt({ message = 'Click Apply to load data.' }) {
  return (
    <div style={{ textAlign: 'center', padding: 40, color: 'var(--hrms-text-faint)',
      fontSize: 13, fontFamily: FONT }}>
      {message}
    </div>
  );
}
