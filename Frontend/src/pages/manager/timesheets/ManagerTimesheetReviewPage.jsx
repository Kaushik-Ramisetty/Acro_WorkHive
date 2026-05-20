import { useEffect, useState } from "react";
import { timesheet as tsApi } from "../../../services/timesheet";

const STATUS_TONE = {
  draft:           { bg: "#F1F5F9", color: "#475569" },
  pending_review:  { bg: "#FEF3C7", color: "#B45309" },
  approved:        { bg: "#D1FAE5", color: "#047857" },
  rejected:        { bg: "#FEE2E2", color: "#B91C1C" },
};

function Pill({ status }) {
  const t = STATUS_TONE[status] || STATUS_TONE.draft;
  return (
    <span style={{
      background: t.bg, color: t.color,
      padding: "3px 10px", borderRadius: 999,
      fontSize: 11, fontWeight: 700,
    }}>{status}</span>
  );
}

export default function ManagerTimesheetReviewPage() {
  const [list, setList] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");

  const refresh = async () => {
    setLoading(true); setErr("");
    try {
      const rows = await tsApi.list({ status: "pending_review" });
      setList(Array.isArray(rows) ? rows : []);
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Could not load timesheets");
    } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);

  const open = async (id) => {
    setComment("");
    try {
      const d = await tsApi.get(id);
      setDetail(d);
    } catch (e) {
      setErr(e?.data?.detail || e.message);
    }
  };

  const review = async (decision) => {
    if (!detail) return;
    setBusy(true); setErr("");
    try {
      await tsApi.review(detail.id, { decision, review_comment: comment || null });
      setDetail(null);
      await refresh();
    } catch (e) {
      setErr(e?.data?.detail || e.message || "Review failed");
    } finally { setBusy(false); }
  };

  return (
    <div style={{ padding: 4 }}>
      <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Timesheet Approvals</h2>
      <p style={{ color: "#64748B", fontSize: 13, marginBottom: 18 }}>
        {list.length} pending — approve to lock, reject to send back for edits.
      </p>

      {err && <div style={{ background: "#FEE2E2", color: "#B91C1C", padding: 10, borderRadius: 6, fontSize: 12, marginBottom: 12 }}>{err}</div>}

      <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #E2E8F0", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#F8FAFC" }}>
              {["Timesheet", "Employee", "Period", "Hours", "Status", ""].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "#94A3B8" }}>Loading...</td></tr>}
            {!loading && list.length === 0 && <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "#94A3B8" }}>No timesheets pending review.</td></tr>}
            {list.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid #E2E8F0" }}>
                <td style={{ padding: "10px 14px", fontSize: 12, fontWeight: 600 }}>{t.id}</td>
                <td style={{ padding: "10px 14px", fontSize: 12 }}>#{t.employee_id}</td>
                <td style={{ padding: "10px 14px", fontSize: 12 }}>{t.period_start} - {t.period_end}</td>
                <td style={{ padding: "10px 14px", fontSize: 12, fontWeight: 600 }}>{(t.total_logged_hours || 0).toFixed(2)} h</td>
                <td style={{ padding: "10px 14px" }}><Pill status={t.status} /></td>
                <td style={{ padding: "10px 14px", textAlign: "right" }}>
                  <button onClick={() => open(t.id)} style={{ padding: "5px 12px", borderRadius: 6, background: "#10B981", color: "#fff", border: "none", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>Review</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }} onClick={() => setDetail(null)}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", width: 640, maxHeight: "85vh", overflow: "auto", borderRadius: 12, padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{detail.id}</h3>
            <p style={{ color: "#64748B", fontSize: 12, marginBottom: 16 }}>
              Employee #{detail.employee_id} - {detail.period_start} → {detail.period_end} - <strong>{(detail.total_logged_hours || 0).toFixed(2)} h</strong>
            </p>

            <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 16 }}>
              <thead>
                <tr style={{ background: "#F8FAFC" }}>
                  <th style={{ padding: 8, fontSize: 11, textAlign: "left", color: "#64748B" }}>Date</th>
                  <th style={{ padding: 8, fontSize: 11, textAlign: "left", color: "#64748B" }}>Project</th>
                  <th style={{ padding: 8, fontSize: 11, textAlign: "left", color: "#64748B" }}>Task</th>
                  <th style={{ padding: 8, fontSize: 11, textAlign: "right", color: "#64748B" }}>Hours</th>
                </tr>
              </thead>
              <tbody>
                {(detail.entries || []).map((e) => (
                  <tr key={e.id} style={{ borderTop: "1px solid #E2E8F0" }}>
                    <td style={{ padding: 8, fontSize: 12 }}>{e.entry_date}</td>
                    <td style={{ padding: 8, fontSize: 12 }}>{e.project_id || "-"}</td>
                    <td style={{ padding: 8, fontSize: 12 }}>{e.task_id || "-"}</td>
                    <td style={{ padding: 8, fontSize: 12, textAlign: "right", fontWeight: 600 }}>{(e.logged_hours || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comments (optional)"
              rows={3} style={{ width: "100%", padding: 8, border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 12, marginBottom: 12 }} />

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setDetail(null)} style={{ padding: "8px 14px", border: "1px solid #E2E8F0", borderRadius: 6, fontSize: 12, fontWeight: 600, background: "#fff", cursor: "pointer" }}>Cancel</button>
              <button onClick={() => review("reject")} disabled={busy} style={{ padding: "8px 14px", border: "none", borderRadius: 6, fontSize: 12, fontWeight: 600, background: "#EF4444", color: "#fff", cursor: "pointer" }}>Reject</button>
              <button onClick={() => review("approve")} disabled={busy} style={{ padding: "8px 14px", border: "none", borderRadius: 6, fontSize: 12, fontWeight: 600, background: "#10B981", color: "#fff", cursor: "pointer" }}>Approve & Lock</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
