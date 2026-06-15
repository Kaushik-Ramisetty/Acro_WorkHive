/**
 * SkillApprovalPage.jsx
 * Recruitment — Skill Set Approval panel for HR Head.
 *
 * Tabs:
 *   1. Pending   — skill requests awaiting approval (approve / reject)
 *   2. All Requests — full history
 *   3. Master Skill Set — every active skill in the system
 *
 * API: /admin/skill-requests/* and /admin/skill-set (via recruitmentApi.js)
 */

import { useState, useEffect, useCallback } from "react";
import {
  getSkillRequests,
  approveSkillRequest,
  rejectSkillRequest,
  getSkillSetMaster,
} from "../../../services/recruitmentApi";

/* ── Design tokens ── */
const C = {
  navy:    "#0d1b2a", navy2: "#1a2d42",
  teal:    "#0ea5a0", tealL: "#e0f7f6",
  ink:     "#0d1b2a", ink2:  "#3a4d5c", ink3: "#7a8fa0",
  surface: "#f4f7fa", white: "#fff",    border: "#e2eaf3",
  green:   "#16a34a", greenL:"#dcfce7",
  red:     "#dc2626", redL:  "#fee2e2",
  amber:   "#d97706", amberL:"#fef3c7",
  purple:  "#7c3aed", purpleL:"#f5f3ff",
};

/* ── Toast ── */
function Toast({ msg, type }) {
  const bg = type === "error" ? C.red : type === "info" ? C.teal : C.green;
  return (
    <div style={{
      position:"fixed", top:20, right:24, zIndex:9999,
      padding:"10px 18px", borderRadius:8, fontWeight:600, fontSize:13,
      background:bg, color:"#fff", boxShadow:"0 4px 12px rgba(0,0,0,0.18)",
      fontFamily:"'DM Sans',sans-serif",
    }}>
      {msg}
    </div>
  );
}

/* ── Status badge ── */
function StatusBadge({ status }) {
  const s = (status || "pending").toLowerCase();
  const map = {
    pending:  { bg: C.amberL,   color: C.amber,  label: "Pending"  },
    approved: { bg: C.greenL,   color: C.green,  label: "Approved" },
    rejected: { bg: C.redL,     color: C.red,    label: "Rejected" },
  };
  const { bg, color, label } = map[s] || map.pending;
  return (
    <span style={{ padding:"3px 10px", borderRadius:20, fontSize:11, fontWeight:700, background:bg, color }}>
      {label}
    </span>
  );
}

/* ── Reject modal ── */
function RejectModal({ skillName, onConfirm, onCancel, loading }) {
  const [reason, setReason] = useState("");
  return (
    <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.45)", zIndex:9000, display:"flex", alignItems:"center", justifyContent:"center" }}>
      <div style={{ background:C.white, borderRadius:14, padding:28, width:440, boxShadow:"0 20px 60px rgba(0,0,0,0.2)", fontFamily:"'DM Sans',sans-serif" }}>
        <div style={{ fontSize:17, fontWeight:800, color:C.navy, marginBottom:6 }}>Reject Skill Request</div>
        <div style={{ fontSize:13, color:C.ink2, marginBottom:16 }}>
          Rejecting: <strong>"{skillName}"</strong>
        </div>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Reason for rejection (optional)"
          rows={3}
          style={{ width:"100%", border:`1px solid ${C.border}`, borderRadius:8, padding:"9px 12px", fontSize:13,
            fontFamily:"'DM Sans',sans-serif", resize:"vertical", outline:"none", boxSizing:"border-box", color:C.ink }}
        />
        <div style={{ display:"flex", gap:10, justifyContent:"flex-end", marginTop:18 }}>
          <button onClick={onCancel} style={{ padding:"8px 18px", border:`1px solid ${C.border}`, borderRadius:8, background:"transparent", fontSize:13, fontWeight:600, cursor:"pointer", color:C.ink2, fontFamily:"'DM Sans',sans-serif" }}>
            Cancel
          </button>
          <button onClick={() => onConfirm(reason)} disabled={loading}
            style={{ padding:"8px 18px", background:C.red, color:"#fff", border:"none", borderRadius:8, fontSize:13, fontWeight:700, cursor:loading?"not-allowed":"pointer", opacity:loading?0.6:1, fontFamily:"'DM Sans',sans-serif" }}>
            {loading ? "Rejecting…" : "Confirm Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main page ── */
export default function SkillApprovalPage() {
  const [tab, setTab]               = useState("pending");
  const [requests, setRequests]     = useState([]);
  const [masterSkills, setMaster]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [acting, setActing]         = useState(false);
  const [toast, setToast]           = useState(null);
  const [rejectTarget, setReject]   = useState(null); // { id, skillName }
  const [masterSearch, setMSearch]  = useState("");

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reqs, master] = await Promise.all([
        getSkillRequests(),
        getSkillSetMaster(),
      ]);
      setRequests(Array.isArray(reqs)    ? reqs    : []);
      setMaster(Array.isArray(master)    ? master  : []);
    } catch (e) {
      showToast(e.message || "Failed to load skill data", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id, skillName) => {
    setActing(true);
    try {
      await approveSkillRequest(id);
      showToast(`"${skillName}" approved and added to the skill set`);
      load();
    } catch (e) {
      showToast(e.message || "Approval failed", "error");
    } finally {
      setActing(false);
    }
  };

  const handleReject = async (reason) => {
    if (!rejectTarget) return;
    setActing(true);
    try {
      await rejectSkillRequest(rejectTarget.id, reason || null);
      showToast(`"${rejectTarget.skillName}" request rejected`);
      setReject(null);
      load();
    } catch (e) {
      showToast(e.message || "Rejection failed", "error");
    } finally {
      setActing(false);
    }
  };

  const pending   = requests.filter(r => (r.status || "pending").toLowerCase() === "pending");
  const displayed = tab === "pending" ? pending : requests;

  const filteredMaster = masterSkills.filter(s =>
    (s.name || s || "").toLowerCase().includes(masterSearch.toLowerCase())
  );

  const tabs = [
    { id:"pending", label:`Pending (${pending.length})` },
    { id:"all",     label:"All Requests" },
    { id:"master",  label:`Master Skill Set (${masterSkills.length})` },
  ];

  return (
    <div style={{ fontFamily:"'DM Sans',sans-serif", color:C.ink }}>
      {toast && <Toast msg={toast.msg} type={toast.type} />}
      {rejectTarget && (
        <RejectModal
          skillName={rejectTarget.skillName}
          onConfirm={handleReject}
          onCancel={() => setReject(null)}
          loading={acting}
        />
      )}

      {/* ── Header ── */}
      <div style={{ marginBottom:24 }}>
        <div style={{ fontSize:22, fontWeight:800, color:C.navy }}>Skill Set Approval</div>
        <div style={{ fontSize:13, color:C.ink3, marginTop:4 }}>
          Review skill requests from managers and recruiters, and manage the master skill catalogue.
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div style={{ display:"flex", gap:14, marginBottom:24, flexWrap:"wrap" }}>
        {[
          { label:"Pending Requests",  value:pending.length,                                              bg:C.amberL,   color:C.amber  },
          { label:"Total Requests",    value:requests.length,                                             bg:C.tealL,    color:C.teal   },
          { label:"Skills in Master",  value:masterSkills.length,                                         bg:C.purpleL,  color:C.purple },
          { label:"Approved",          value:requests.filter(r=>r.status==="approved").length,            bg:C.greenL,   color:C.green  },
          { label:"Rejected",          value:requests.filter(r=>r.status==="rejected").length,            bg:C.redL,     color:C.red    },
        ].map(s => (
          <div key={s.label} style={{ background:s.bg, borderRadius:12, padding:"16px 22px", minWidth:130, flex:"1 1 130px" }}>
            <div style={{ fontSize:26, fontWeight:800, color:s.color }}>{s.value}</div>
            <div style={{ fontSize:11, fontWeight:700, color:s.color, opacity:0.75, marginTop:2, textTransform:"uppercase", letterSpacing:0.4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── Tabs ── */}
      <div style={{ display:"flex", gap:4, marginBottom:20, borderBottom:`2px solid ${C.border}` }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding:"9px 18px", border:"none", background:"transparent", cursor:"pointer",
            fontWeight:700, fontSize:13, fontFamily:"'DM Sans',sans-serif",
            color: tab===t.id ? C.teal : C.ink3,
            borderBottom: tab===t.id ? `3px solid ${C.teal}` : "3px solid transparent",
            marginBottom:-2, transition:"all 0.15s",
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Content ── */}
      {loading ? (
        <div style={{ textAlign:"center", color:C.ink3, padding:"60px 0", fontSize:14 }}>
          Loading skill data…
        </div>
      ) : tab === "master" ? (
        /* Master skill set */
        <div style={{ background:C.white, borderRadius:12, border:`1px solid ${C.border}`, overflow:"hidden" }}>
          <div style={{ padding:"14px 20px", borderBottom:`1px solid ${C.border}`, display:"flex", alignItems:"center", gap:12 }}>
            <span style={{ fontSize:13, fontWeight:700, color:C.ink2, flex:1 }}>
              All Active Skills ({filteredMaster.length})
            </span>
            <input
              value={masterSearch}
              onChange={e => setMSearch(e.target.value)}
              placeholder="Search skills…"
              style={{ border:`1px solid ${C.border}`, borderRadius:8, padding:"6px 12px", fontSize:12,
                fontFamily:"'DM Sans',sans-serif", outline:"none", width:200, color:C.ink }}
            />
          </div>
          <div style={{ padding:18, display:"flex", flexWrap:"wrap", gap:8, minHeight:80 }}>
            {filteredMaster.length === 0 ? (
              <div style={{ color:C.ink3, fontSize:13 }}>No skills found.</div>
            ) : filteredMaster.map((s, i) => (
              <span key={i} style={{
                background:C.tealL, color:C.teal, borderRadius:20,
                padding:"4px 14px", fontSize:12, fontWeight:600,
              }}>
                {s.name || s}
              </span>
            ))}
          </div>
        </div>
      ) : (
        /* Requests table */
        displayed.length === 0 ? (
          <div style={{ textAlign:"center", color:C.ink3, padding:"60px 0", fontSize:14 }}>
            {tab === "pending" ? "No pending skill requests. All caught up! ✓" : "No requests found."}
          </div>
        ) : (
          <div style={{ background:C.white, borderRadius:12, border:`1px solid ${C.border}`, overflow:"auto" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
              <thead>
                <tr style={{ background:C.surface }}>
                  {["Skill Name","Requested By","Requirement","Submitted","Status","Actions"].map(h => (
                    <th key={h} style={{ padding:"11px 16px", textAlign:"left", fontWeight:700,
                      color:C.ink2, fontSize:11, textTransform:"uppercase", letterSpacing:0.4,
                      whiteSpace:"nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayed.map((r, i) => {
                  const isPending = (r.status || "pending").toLowerCase() === "pending";
                  return (
                    <tr key={r.id ?? i} style={{ borderTop:`1px solid ${C.border}`, background: i%2===0 ? C.white : "#fafbfc" }}>
                      <td style={{ padding:"12px 16px", fontWeight:700, color:C.navy }}>{r.skill_name}</td>
                      <td style={{ padding:"12px 16px", color:C.ink2 }}>{r.requested_by_name || r.requested_by || "—"}</td>
                      <td style={{ padding:"12px 16px", color:C.ink2 }}>{r.requirement_id || "—"}</td>
                      <td style={{ padding:"12px 16px", color:C.ink3, whiteSpace:"nowrap" }}>
                        {r.created_at ? new Date(r.created_at).toLocaleDateString("en-IN", { day:"2-digit", month:"short", year:"numeric" }) : "—"}
                      </td>
                      <td style={{ padding:"12px 16px" }}>
                        <StatusBadge status={r.status} />
                      </td>
                      <td style={{ padding:"12px 16px" }}>
                        {isPending ? (
                          <div style={{ display:"flex", gap:6 }}>
                            <button
                              onClick={() => handleApprove(r.id, r.skill_name)}
                              disabled={acting}
                              style={{ padding:"5px 13px", background:C.green, color:"#fff", border:"none",
                                borderRadius:6, fontSize:12, fontWeight:700, cursor:acting?"not-allowed":"pointer",
                                opacity:acting?0.6:1, fontFamily:"'DM Sans',sans-serif" }}>
                              Approve
                            </button>
                            <button
                              onClick={() => setReject({ id:r.id, skillName:r.skill_name })}
                              disabled={acting}
                              style={{ padding:"5px 13px", background:C.red, color:"#fff", border:"none",
                                borderRadius:6, fontSize:12, fontWeight:700, cursor:acting?"not-allowed":"pointer",
                                opacity:acting?0.6:1, fontFamily:"'DM Sans',sans-serif" }}>
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span style={{ color:C.ink3, fontSize:12 }}>
                            {r.status === "approved" ? `Approved${r.approved_by ? " by " + r.approved_by : ""}` : `Rejected${r.rejection_reason ? ": " + r.rejection_reason : ""}`}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
