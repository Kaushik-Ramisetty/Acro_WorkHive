import { useEffect, useState } from "react";
import { regularization } from "../../../services/attendance";

const STATUS_TONE = {
  pending:  { bg: "#FEF3C7", color: "#B45309" },
  approved: { bg: "#D1FAE5", color: "#047857" },
  rejected: { bg: "#FEE2E2", color: "#B91C1C" },
};

function Pill({ status }) {
  const t = STATUS_TONE[status] || STATUS_TONE.pending;
  return (
    <span style={{
      background: t.bg, color: t.color,
      padding: "3px 10px", borderRadius: 999,
      fontSize: 11, fontWeight: 700,
    }}>{status}</span>
  );
}

export default function RegularizationApprovalsPage() {
  const [filter, setFilter] = useState("pending");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewing, setReviewing] = useState(null);
  const [comment, setComment] = useState("");

  const refresh = async () => {
    setLoading(true); setErr("");
    try {
      const list = await regularization.list(filter ? { status: filter } : {});
      setRows(Array.isArray(list) ? list : []);
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Could not load regularizations");
    } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [filter]);

  const decide = async (status) => {
    if (!reviewing) return;
    setBusy(true); setErr("");
    try {
      await regularization.review(reviewing.id, { status, review_comment: comment || null });
      setReviewing(null); setComment("");
      await refresh();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Decision failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Regularization Requests</h1>
          <p className="text-xs text-slate-500 mt-1">{rows.length} {filter || "all"} requests</p>
        </div>
        <div className="flex gap-2">
          {["pending", "approved", "rejected", ""].map((f) => (
            <button key={f || "all"}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-md border text-xs font-semibold ${
                filter === f ? "bg-teal-500 text-white border-teal-500" : "border-slate-200 text-slate-600 bg-white"
              }`}>
              {f || "All"}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="bg-rose-50 text-rose-700 text-xs px-3 py-2 rounded mb-3">{err}</div>}

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider">
            <tr>
              {["ID", "Employee", "Date", "Type", "Requested in/out", "Reason", "Status", ""].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left font-bold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={8} className="px-4 py-6 text-center text-slate-400">No regularization requests.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="px-4 py-3 font-semibold text-slate-700">{r.id}</td>
                <td className="px-4 py-3 text-slate-600">#{r.employee_id}</td>
                <td className="px-4 py-3 text-slate-600">{r.date}</td>
                <td className="px-4 py-3 text-slate-600">{r.regularization_type || "-"}</td>
                <td className="px-4 py-3 text-slate-600">
                  {r.requested_check_in ? r.requested_check_in.slice(0, 5) : "-"} → {r.requested_check_out ? r.requested_check_out.slice(0, 5) : "-"}
                </td>
                <td className="px-4 py-3 text-slate-600 max-w-xs truncate" title={r.reason}>{r.reason || "-"}</td>
                <td className="px-4 py-3"><Pill status={r.status} /></td>
                <td className="px-4 py-3 text-right">
                  {r.status === "pending" && (
                    <button onClick={() => { setReviewing(r); setComment(""); }}
                      className="px-3 py-1.5 rounded bg-teal-500 text-white text-[11px] font-semibold hover:bg-teal-600">Review</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {reviewing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onClick={() => setReviewing(null)}>
          <div onClick={(e) => e.stopPropagation()} className="bg-white w-[480px] rounded-xl shadow-xl p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Review {reviewing.id}</h3>
            <div className="text-xs space-y-1.5 text-slate-600 mb-3">
              <div><strong>Employee:</strong> #{reviewing.employee_id}</div>
              <div><strong>Date:</strong> {reviewing.date}</div>
              <div><strong>Type:</strong> {reviewing.regularization_type}</div>
              <div><strong>Requested check-in:</strong> {reviewing.requested_check_in?.slice(0,5) || "-"}</div>
              <div><strong>Requested check-out:</strong> {reviewing.requested_check_out?.slice(0,5) || "-"}</div>
              <div><strong>Reason:</strong> {reviewing.reason || "-"}</div>
            </div>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Review comment (optional)"
              rows={3} className="w-full px-2 py-1.5 border border-slate-200 rounded text-xs mb-3" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setReviewing(null)} className="px-3 py-1.5 text-xs rounded border border-slate-200">Cancel</button>
              <button onClick={() => decide("rejected")} disabled={busy}
                className="px-3 py-1.5 text-xs rounded bg-rose-500 text-white font-semibold">Reject</button>
              <button onClick={() => decide("approved")} disabled={busy}
                className="px-3 py-1.5 text-xs rounded bg-emerald-500 text-white font-semibold">Approve</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
