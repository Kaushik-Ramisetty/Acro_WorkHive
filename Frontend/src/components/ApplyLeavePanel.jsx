import { useEffect, useMemo, useState } from "react";
import { leaveApi } from "../services/leave";
import { useAuth } from "../context/AuthContext";

/**
 * Inline "Apply Leave" panel — visually + behaviourally identical to the
 * Employee dashboard's Apply Leave MODAL (pages/employee/parts/ApplyLeaveModal),
 * just rendered as a regular section instead of behind a backdrop.
 *
 * Used as a sub-tab inside Manager + Admin Leave Management so all three
 * roles get the same Apply Leave experience.
 *
 * Props:
 *   onSubmitted()  optional — fired after a successful POST /leave/apply
 */

const LEAVE_TYPE_LABEL_OVERRIDES = { 'LOP_leaves': 'LOPs' };
function formatLeaveTypeName(name) {
  if (!name) return '';
  if (LEAVE_TYPE_LABEL_OVERRIDES[name]) return LEAVE_TYPE_LABEL_OVERRIDES[name];
  return String(name)
    .replace(/_/g, ' ')
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function isLeaveTypeAllowed(t, gender) {
  const g = (gender || '').toString().trim().toLowerCase();
  const apg = (t?.applicable_gender || '').toString().trim().toLowerCase();
  const name = (t?.name || '').toLowerCase();
  const isMaternity = apg === 'female' || (!apg && name.includes('maternity'));
  const isPaternity = apg === 'male'   || (!apg && name.includes('paternity'));
  if (isMaternity && g !== 'female') return false;
  if (isPaternity && g !== 'male')   return false;
  return true;
}

function addDays(isoDate, n) {
  if (!isoDate) return "";
  const num = Number(n);
  if (!Number.isFinite(num) || num < 1) return "";
  const d = new Date(isoDate + "T00:00:00");
  if (Number.isNaN(d.getTime())) return "";
  d.setDate(d.getDate() + (Math.floor(num) - 1));
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function todayIso() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function ApplyLeavePanel({ onSubmitted }) {
  const { user } = useAuth();
  const today = todayIso();
  const initial = { leave_type_id: "", start_date: today, days: "", end_date: "", reason: "" };
  const [form, setForm] = useState(initial);
  const [types, setTypes] = useState([]);
  const [balances, setBalances] = useState([]);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const visibleTypes = useMemo(
    () => (types || []).filter((t) => isLeaveTypeAllowed(t, user?.gender)),
    [types, user?.gender]
  );

  // Recompute end_date whenever start_date or days change.
  useEffect(() => {
    setForm((prev) => {
      const next = addDays(prev.start_date, prev.days);
      return next === prev.end_date ? prev : { ...prev, end_date: next };
    });
  }, [form.start_date, form.days]);

  // Load types + balances once
  useEffect(() => {
    let cancelled = false;
    Promise.all([leaveApi.types(), leaveApi.myBalance()])
      .then(([t, b]) => { if (!cancelled) { setTypes(t || []); setBalances(b || []); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const balanceFor = (typeId) => balances.find((b) => b.leave_type_id === typeId);
  const selectedBal = form.leave_type_id ? balanceFor(form.leave_type_id) : null;

  const reset = () => {
    setForm({ leave_type_id: "", start_date: todayIso(), days: "", end_date: "", reason: "" });
    setError(""); setSubmitted(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await leaveApi.apply({
        leave_type_id: form.leave_type_id,
        start_date: form.start_date,
        end_date: form.end_date,
        reason: form.reason,
      });
      setSubmitted(true);
      onSubmitted?.();
      // Match the Employee modal: hold the success state briefly, then reset
      // back to a blank form so the user can immediately apply for another.
      setTimeout(() => { setSubmitted(false); reset(); }, 1600);
    } catch (ex) {
      setError(ex?.data?.detail || ex?.message || 'Failed to apply.');
    } finally { setBusy(false); }
  };

  // Card styling mirrors the Employee modal exactly (max-w-lg, shadow-2xl,
  // rounded-2xl, identical header text). The only intentional difference is
  // we don't render the close X button or the dark overlay, since this is an
  // inline panel — the surrounding tab UI handles navigation.
  return (
    <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100">
        <h2 className="text-base font-bold text-slate-800">Apply Leave</h2>
        <p className="text-xs text-slate-400 mt-0.5">Submit a leave request for approval</p>
      </div>

      {submitted ? (
        <div className="py-14 flex flex-col items-center justify-center gap-3">
          <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: "#f0fdf4", border: "2px solid #bbf7d0" }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </div>
          <p className="text-sm font-semibold text-slate-700">Leave request submitted!</p>
          <p className="text-xs text-slate-400">Your manager will review it shortly.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Leave Type <span className="text-red-400">*</span></label>
            <select required
              value={form.leave_type_id}
              onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent bg-white">
              <option value="">Select leave type</option>
              {visibleTypes.map((t) => (
                <option key={t.id} value={t.id}>{formatLeaveTypeName(t.name)}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">From Date <span className="text-red-400">*</span></label>
              <input type="date" required
                min={today}
                value={form.start_date}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v && v < today) return;
                  setForm({ ...form, start_date: v });
                }}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">No. of Days <span className="text-red-400">*</span></label>
              <input type="number" min={1} step={1} required
                placeholder="—"
                value={form.days}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === "") { setForm({ ...form, days: "" }); return; }
                  const n = parseInt(raw, 10);
                  setForm({ ...form, days: Number.isFinite(n) && n >= 1 ? n : "" });
                }}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">To Date</label>
              <input type="date" readOnly tabIndex={-1}
                value={form.end_date}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-500 bg-slate-50 cursor-not-allowed" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Reason</label>
            <textarea rows={3}
              placeholder="Briefly describe the reason for your leave..."
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent resize-none" />
          </div>

          {/* Live balance info */}
          {selectedBal && (
            <div className="bg-teal-50 border border-teal-100 rounded-lg px-4 py-3 flex items-center gap-3">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#14b8a6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <p className="text-xs text-teal-700">
                You have <strong>{selectedBal.available} {formatLeaveTypeName(selectedBal.leave_type_name)}</strong> day(s) available
                {selectedBal.reserved > 0 ? ` (${selectedBal.reserved} reserved)` : ''}.
              </p>
            </div>
          )}

          {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>}

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={reset} disabled={busy}
              className="flex-1 py-2.5 rounded-lg border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-60">
              Cancel
            </button>
            <button type="submit" disabled={busy}
              className="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-60"
              style={{ background: "#14b8a6" }}>
              {busy ? 'Submitting…' : 'Submit Request'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
