import { useState } from "react";
import { regularization } from "../services/attendance";

/**
 * Shared Regularize Attendance modal.
 *
 * Extracted from `pages/employee/screens/AttendancePage.jsx` so it can be
 * opened from the Employee Dashboard's Quick Actions tile without
 * navigating away. Behaviour and styling are identical to the original
 * inline component.
 *
 * Props:
 *   open         — boolean, modal visible when true
 *   onClose      — () => void, called on Cancel / X / outside-click
 *   onSubmitted  — () => void, called after a successful submit (use this
 *                  to refetch lists on the parent page)
 */
const TEAL = "#14b8a6";
const FONT = "'DM Sans', system-ui, sans-serif";

export default function RegularizeModal({ open, onClose, onSubmitted }) {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate]       = useState(today);
  const [type, setType]       = useState("missed_checkout");
  const [checkIn, setCheckIn] = useState("09:00");
  const [checkOut, setCheckOut] = useState("18:00");
  const [reason, setReason]   = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr]         = useState("");

  if (!open) return null;

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setSubmitting(true);
    try {
      await regularization.submit({
        date,
        regularization_type: type,
        requested_check_in:  checkIn  ? `${checkIn}:00`  : null,
        requested_check_out: checkOut ? `${checkOut}:00` : null,
        reason,
      });
      if (onSubmitted) onSubmitted();
      onClose();
    } catch (e2) {
      setErr(e2?.data?.detail || e2.message || "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <form
        onSubmit={submit}
        style={{ fontFamily: FONT }}
        className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-6"
      >
        <h3 className="text-base font-bold text-slate-800 mb-4">Regularize Attendance</h3>
        <div className="space-y-3 text-xs">
          <label className="block">
            <span className="text-slate-500 font-medium">Date</span>
            <input
              type="date" value={date} onChange={(e) => setDate(e.target.value)} required
              className="w-full mt-1 px-3 py-2 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-300"
            />
          </label>
          <label className="block">
            <span className="text-slate-500 font-medium">Type</span>
            <select
              value={type} onChange={(e) => setType(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-300"
            >
              <option value="full_day">Full Day</option>
              <option value="wrong_time">Wrong Time</option>
              <option value="missed_checkout">Missed Checkout</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-slate-500 font-medium">Check-in</span>
              <input
                type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)}
                className="w-full mt-1 px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-teal-300"
              />
            </label>
            <label className="block">
              <span className="text-slate-500 font-medium">Check-out</span>
              <input
                type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)}
                className="w-full mt-1 px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-teal-300"
              />
            </label>
          </div>
          <label className="block">
            <span className="text-slate-500 font-medium">Reason</span>
            <textarea
              value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
              className="w-full mt-1 px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-teal-300 resize-none"
            />
          </label>
          {err && <div className="text-rose-600 bg-rose-50 px-3 py-2 rounded-lg">{err}</div>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button" onClick={onClose}
            className="px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit" disabled={submitting}
            className="px-4 py-2 text-xs font-bold rounded-xl text-white disabled:opacity-60"
            style={{ background: TEAL }}
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </div>
      </form>
    </div>
  );
}
