import { useEffect, useState } from "react";

/**
 * Role-agnostic "Request Work From Home" modal.
 *
 * Mirrors the Employee modal: From Date with min=today, days input that
 * derives the To Date, optional Reason. WFH submission is currently a UI-only
 * flow (no /wfh API yet); the modal calls onSubmitted() so callers can refresh
 * downstream lists if/when that endpoint lands.
 *
 * Props:
 *   open         boolean
 *   onClose()    close without applying
 *   onSubmitted() called after a successful submit
 */

function todayIso() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
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

export default function RequestWFHDialog({ open, onClose, onSubmitted }) {
  const today = todayIso();
  const [form, setForm] = useState({ from: "", to: "", days: "", reason: "", type: "full" });
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    setForm({ from: "", to: "", days: "", reason: "", type: "full" });
    setSubmitted(false);
  }, [open]);

  useEffect(() => {
    setForm((prev) => {
      const next = addDays(prev.from, prev.days);
      return next === prev.to ? prev : { ...prev, to: next };
    });
  }, [form.from, form.days]);

  if (!open) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    setSubmitted(true);
    onSubmitted?.();
    setTimeout(() => { onClose?.(); setSubmitted(false); }, 1800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(15,28,46,0.55)", backdropFilter: "blur(3px)" }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-white rounded-2xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-800">Request Work From Home</h2>
            <p className="text-xs text-slate-400 mt-0.5">Submit a WFH request for manager approval</p>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center hover:bg-slate-200 transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {submitted ? (
          <div className="py-14 flex flex-col items-center justify-center gap-3">
            <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: "#eff6ff", border: "2px solid #bfdbfe" }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-700">WFH request submitted!</p>
            <p className="text-xs text-slate-400">Awaiting manager approval.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-2">WFH Type</label>
              <div className="flex gap-3">
                {[{ val: "full", label: "Full Day" }, { val: "half", label: "Half Day" }].map(({ val, label }) => (
                  <button key={val} type="button"
                    onClick={() => setForm({ ...form, type: val })}
                    className="flex-1 py-2.5 rounded-lg border text-sm font-semibold transition-all duration-150"
                    style={{
                      background: form.type === val ? "#eff6ff" : "#fff",
                      borderColor: form.type === val ? "#3b82f6" : "#e2e8f0",
                      color: form.type === val ? "#3b82f6" : "#64748b",
                    }}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">From Date <span className="text-red-400">*</span></label>
                <input type="date" required value={form.from}
                  min={today}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v && v < today) return;
                    setForm({ ...form, from: v });
                  }}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent" />
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">To Date</label>
                <input type="date" readOnly tabIndex={-1} value={form.to}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-500 bg-slate-50 cursor-not-allowed" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Reason</label>
              <textarea rows={3}
                placeholder="Provide a reason for working from home (optional)…"
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent resize-none" />
            </div>

            <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3 flex items-center gap-3">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <p className="text-xs text-blue-700">WFH requests must be submitted at least <strong>1 business day</strong> in advance.</p>
            </div>

            <div className="flex gap-3 pt-1">
              <button type="button" onClick={onClose}
                className="flex-1 py-2.5 rounded-lg border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors">
                Cancel
              </button>
              <button type="submit"
                className="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white transition-colors"
                style={{ background: "#3b82f6" }}>
                Submit Request
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
