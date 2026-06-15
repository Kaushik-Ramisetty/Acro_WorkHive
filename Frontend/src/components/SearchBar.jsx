import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { searchApi } from '../services/search';

const PLACEHOLDER = {
  admin:    'Search employees, leaves, comp-off…',
  manager:  'Search team, leaves, comp-off…',
  employee: 'Search your leaves, comp-off…',
};

const STATUS_TONE = {
  pending:        '#92400E',
  approved:       '#065F46',
  rejected:       '#991B1B',
  cancel_pending: '#92400E',
  cancelled:      '#475569',
  consumed:       '#1E40AF',
  expired:        '#475569',
};

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

/**
 * Reusable global search bar. Drops into any Topbar.
 * Props: variant — 'admin' | 'manager' | 'employee' (controls placeholder + the
 * route prefix used when navigating to a result).
 */
export default function SearchBar({ variant = 'admin', className = '' }) {
  const { role } = useAuth();
  const navigate = useNavigate();
  const v = variant || role || 'admin';

  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState({ employees: [], leaves: [], compoff: [] });
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);
  const timerRef = useRef(null);

  const total = results.employees.length + results.leaves.length + results.compoff.length;

  useEffect(() => {
    if (!q.trim()) {
      setResults({ employees: [], leaves: [], compoff: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const data = await searchApi.query(q);
        setResults(data || { employees: [], leaves: [], compoff: [] });
      } catch {
        setResults({ employees: [], leaves: [], compoff: [] });
      } finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [q]);

  // Click-outside to close
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const base = '/' + v + '-dashboard';
  const goto = (path) => {
    setOpen(false);
    setQ('');
    navigate(base + path);
  };

  const onEmployeeClick = () => {
    // Only admin has an Employees page that supports search
    if (v === 'admin') goto('/employees');
    else if (v === 'manager') goto('/team');
    else goto('/profile');
  };

  return (
    <div ref={ref} className={'relative ' + className}>
      <div className="relative">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
          <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          type="text"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={PLACEHOLDER[v] || PLACEHOLDER.admin}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
        />
        {q && (
          <button
            onClick={() => { setQ(''); setResults({ employees: [], leaves: [], compoff: [] }); }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Clear"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>

      {open && q.trim() && (
        <div className="absolute left-0 right-0 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg z-40 max-h-[28rem] overflow-y-auto">
          {loading && (
            <div className="px-4 py-3 text-xs text-slate-400">Searching…</div>
          )}
          {!loading && total === 0 && (
            <div className="px-4 py-6 text-center text-xs text-slate-400">No matches for "{q}"</div>
          )}

          {!loading && results.employees.length > 0 && (
            <div>
              <div className="bg-slate-50 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">Employees</div>
              {results.employees.map((e) => (
                <button
                  key={'e-' + e.id}
                  onClick={onEmployeeClick}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-slate-50"
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-[11px] font-bold text-white">
                    {(e.full_name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{e.full_name}</p>
                    <p className="truncate text-[11px] text-slate-500">{e.designation || ''}{e.designation && e.department ? ' · ' : ''}{e.department || ''} · {e.email}</p>
                  </div>
                </button>
              ))}
            </div>
          )}

          {!loading && results.leaves.length > 0 && (
            <div>
              <div className="bg-slate-50 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">Leave requests</div>
              {results.leaves.map((r) => (
                <button
                  key={'l-' + r.id}
                  onClick={() => goto('/leave')}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      <span className="text-[10px] text-slate-400 mr-1">{r.id}</span>
                      {r.employee_name}
                    </p>
                    <p className="truncate text-[11px] text-slate-500">
                      {r.leave_type_name} · {fmtDate(r.start_date)} → {fmtDate(r.end_date)} · {r.total_days}d
                    </p>
                  </div>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                    style={{ background: '#f1f5f9', color: STATUS_TONE[r.status] || '#475569' }}>
                    {r.status}
                  </span>
                </button>
              ))}
            </div>
          )}

          {!loading && results.compoff.length > 0 && (
            <div>
              <div className="bg-slate-50 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">Comp-off</div>
              {results.compoff.map((c) => (
                <button
                  key={'c-' + c.id}
                  onClick={() => goto('/comp-off')}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{c.employee_name}</p>
                    <p className="truncate text-[11px] text-slate-500">
                      {c.days} day{c.days !== 1 ? 's' : ''} · worked on {fmtDate(c.worked_on)}
                    </p>
                  </div>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                    style={{ background: '#f1f5f9', color: STATUS_TONE[c.status] || '#475569' }}>
                    {c.status}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
