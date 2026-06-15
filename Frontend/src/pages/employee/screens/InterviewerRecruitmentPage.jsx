/**
 * InterviewerRecruitmentPage.jsx
 * Recruitment tab for the Interviewer role inside the Employee Dashboard.
 *
 * ALL data is fetched live from the backend — no mock arrays anywhere.
 * Only rounds/feedback assigned to the currently-logged-in interviewer are shown.
 *
 * API client: src/services/interviewerApi.js
 */

import { useState, useEffect, useCallback } from "react";
import { interviewerApi } from "../../../services/interviewerApi";

/* ── Design tokens (same as the rest of the HRMS dashboard) ── */
const C = {
  navy:    "#0d1b2a", navy2: "#1a2d42",
  teal:    "#0ea5a0", tealL:  "#e0f7f6",
  ink:     "#0d1b2a", ink2:   "#3a4d5c", ink3: "#7a8fa0",
  surface: "#f4f7fa", white:  "#fff",    border: "#e2eaf3",
  green:   "#16a34a", greenL: "#dcfce7",
  red:     "#dc2626", redL:   "#fee2e2",
  amber:   "#d97706", amberL: "#fef3c7",
  blue:    "#2563eb", blueL:  "#eff6ff",
  purple:  "#7c3aed", purpleL:"#f5f3ff",
};

/* ── Avatar color palette (deterministic from name) ── */
const AVATAR_COLORS = [
  "linear-gradient(135deg,#f59e0b,#ef4444)",
  "linear-gradient(135deg,#a855f7,#ec4899)",
  "linear-gradient(135deg,#10b981,#0ea5e9)",
  "linear-gradient(135deg,#1d4ed8,#6366f1)",
  "linear-gradient(135deg,#8b5cf6,#ec4899)",
  "linear-gradient(135deg,#ef4444,#f97316)",
  "linear-gradient(135deg,#14b8a6,#0ea5a0)",
  "linear-gradient(135deg,#f97316,#eab308)",
];

const CALENDAR_EVENT_COLORS = [C.purple, C.teal, C.blue, C.amber, C.green, C.red];

function avatarColor(name = "") {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function calendarColor(name = "") {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return CALENDAR_EVENT_COLORS[Math.abs(hash) % CALENDAR_EVENT_COLORS.length];
}

function formatTime(time24) {
  if (!time24) return "TBD";
  try {
    const [h, m] = time24.split(":").map(Number);
    const ampm = h >= 12 ? "PM" : "AM";
    const hour = h % 12 || 12;
    return `${hour}:${String(m).padStart(2, "0")} ${ampm}`;
  } catch {
    return time24;
  }
}

function todayISO() {
  return new Date().toISOString().split("T")[0];
}

/* ── Micro-components ── */
const Avt = ({ name, size = 36 }) => (
  <div style={{
    width: size, height: size, borderRadius: "50%",
    background: avatarColor(name || ""),
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: size * 0.34, fontWeight: 700, color: "#fff", flexShrink: 0,
  }}>
    {(name || "??").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
  </div>
);

const Badge = ({ type, children }) => {
  const map = {
    green:  { bg: C.greenL,  color: "#14532d" },
    red:    { bg: C.redL,    color: "#7f1d1d" },
    amber:  { bg: C.amberL,  color: "#78350f" },
    blue:   { bg: C.blueL,   color: "#1e3a8a" },
    purple: { bg: C.purpleL, color: "#4c1d95" },
    teal:   { bg: C.tealL,   color: "#134e4a" },
    gray:   { bg: "#f1f5f9", color: "#334155" },
  };
  const s = map[type] || map.gray;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: 20,
      fontSize: 10, fontWeight: 700, background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.color }} />
      {children}
    </span>
  );
};

const Btn = ({ children, variant = "outline", onClick, style = {}, disabled = false }) => {
  const variants = {
    primary: { background: C.navy,    color: "#fff", border: "none" },
    teal:    { background: C.teal,    color: "#fff", border: "none" },
    outline: { background: "#fff",    color: C.ink2, border: `1px solid ${C.border}` },
    ghost:   { background: C.surface, color: C.ink2, border: "none" },
    danger:  { background: C.redL,    color: C.red,  border: `1px solid #fecaca` },
  };
  const v = variants[variant] || variants.outline;
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        fontFamily: "inherit", transition: "all .15s", opacity: disabled ? 0.5 : 1,
        ...v, ...style,
      }}
    >{children}</button>
  );
};

const Chip = ({ children, color = C.teal, bg = C.tealL }) => (
  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 4, background: bg, color }}>{children}</span>
);

const StarRating = ({ value, max = 5, color = C.amber }) => (
  <div style={{ display: "flex", gap: 2 }}>
    {Array.from({ length: max }, (_, i) => (
      <span key={i} style={{ fontSize: 14, color: i < value ? color : C.border }}>★</span>
    ))}
  </div>
);

function statusBadge(status) {
  const typeMap = {
    "Awaiting Slot Selection": "amber",
    "Slots Added":             "blue",
    "Candidate Notified":      "blue",
    "Scheduled":               "teal",
    "Completed":               "green",
    "Rescheduled":             "purple",
  };
  // Human-friendly label overrides
  const labelMap = {
    "Scheduled": "Candidate Confirmed",
  };
  return <Badge type={typeMap[status] || "gray"}>{labelMap[status] || status}</Badge>;
}

function recommendationBadge(r) {
  if (r === "Strong Hire") return <Badge type="green">⭐ Strong Hire</Badge>;
  if (r === "Hire")        return <Badge type="teal">✓ Hire</Badge>;
  if (r === "Neutral")     return <Badge type="gray">~ Neutral</Badge>;
  if (r === "Reject")      return <Badge type="red">✕ Reject</Badge>;
  return null;
}

/* ── Modal wrapper ── */
const Modal = ({ open, onClose, title, width = 560, children, footer }) => {
  if (!open) return null;
  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(13,27,42,0.55)", zIndex: 300, display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ background: "#fff", borderRadius: 16, width, maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,0.2)" }}>
        <div style={{ padding: "20px 24px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, background: "#fff", zIndex: 5 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: C.ink }}>{title}</h2>
          <button onClick={onClose} style={{ width: 32, height: 32, borderRadius: 8, background: C.surface, border: "none", cursor: "pointer", fontSize: 16, color: C.ink3 }}>✕</button>
        </div>
        <div style={{ padding: 24 }}>{children}</div>
        {footer && (
          <div style={{ padding: "16px 24px", borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end", gap: 10, background: "#fafbfd", borderRadius: "0 0 16px 16px" }}>{footer}</div>
        )}
      </div>
    </div>
  );
};

/* ── Loading spinner ── */
const Spinner = () => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 60 }}>
    <div style={{ width: 36, height: 36, border: `3px solid ${C.border}`, borderTop: `3px solid ${C.teal}`, borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const EmptyState = ({ icon, title, subtitle }) => (
  <div style={{ textAlign: "center", padding: "60px 20px", color: C.ink3 }}>
    <div style={{ fontSize: 40, marginBottom: 12 }}>{icon}</div>
    <div style={{ fontSize: 14, fontWeight: 700, color: C.ink2, marginBottom: 6 }}>{title}</div>
    {subtitle && <div style={{ fontSize: 12 }}>{subtitle}</div>}
  </div>
);

/* ── Candidate Profile Drawer ── */
const CandidateProfileDrawer = ({ interview, open, onClose }) => {
  if (!open || !interview) return null;

  const BASE     = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const resumeUrl = interview.resume_url ? `${BASE}/${interview.resume_url}` : null;
  const ext      = resumeUrl ? resumeUrl.split(".").pop().toLowerCase() : "";
  const dlName   = `${(interview.candidate_name || "Candidate").replace(/\s+/g, "_")}_Resume${ext ? "." + ext : ""}`;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 200 }} />
      <div style={{ position: "fixed", right: 0, top: 0, bottom: 0, width: 460, background: "#fff", borderLeft: `1px solid ${C.border}`, zIndex: 210, display: "flex", flexDirection: "column", boxShadow: "-10px 0 40px rgba(0,0,0,0.1)", overflowY: "auto" }}>

        {/* Header */}
        <div style={{ padding: "20px 20px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 12, position: "sticky", top: 0, background: "#fff", zIndex: 5 }}>
          <Avt name={interview.candidate_name} size={48} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>{interview.candidate_name}</div>
            <div style={{ fontSize: 11, color: C.ink3, marginTop: 2 }}>{interview.role} · {interview.company}</div>
          </div>
          <button onClick={onClose} style={{ border: "none", background: C.surface, borderRadius: 8, width: 32, height: 32, cursor: "pointer", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>✕</button>
        </div>

        <div style={{ padding: 20, flex: 1 }}>
          {/* Assigned Interview info */}
          <div style={{ marginBottom: 20, padding: "12px 14px", background: C.tealL, borderRadius: 10, border: `1px solid ${C.teal}40` }}>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.teal, marginBottom: 6 }}>Assigned Interview</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: C.ink }}>{interview.round}</span>
              <span style={{ fontSize: 11, color: C.ink3 }}>·</span>
              <span style={{ fontSize: 11, color: C.ink3, fontFamily: "monospace" }}>{interview.req_id}</span>
              {statusBadge(interview.status)}
            </div>
            {interview.date && (
              <div style={{ fontSize: 11, color: C.ink3, marginTop: 6 }}>📅 {interview.date}{interview.time ? ` · ${formatTime(interview.time)}` : ""}</div>
            )}
          </div>

          {/* Quick stats grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
            {[
              ["Experience",    interview.exp],
              ["Current CTC",   interview.ctc],
              ["Expected CTC",  interview.exp_ctc],
              ["Notice Period", interview.notice],
              ["Source",        interview.source],
              ["Company",       interview.company],
            ].map(([lbl, val]) => (
              <div key={lbl} style={{ background: C.surface, borderRadius: 8, padding: "10px 12px" }}>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 3 }}>{lbl}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.ink }}>{val || "—"}</div>
              </div>
            ))}
          </div>

          {/* Skills */}
          {interview.skills?.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: C.ink3, marginBottom: 10 }}>Skills</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {interview.skills.map(s => <Chip key={s}>{s}</Chip>)}
              </div>
            </div>
          )}

          {/* Manager remark */}
          {interview.manager_remark && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: C.ink3, marginBottom: 8 }}>Manager Remark</div>
              <div style={{ padding: "12px 14px", background: C.amberL, borderRadius: 8, border: "1px solid #fcd34d" }}>
                <div style={{ fontSize: 11, color: "#78350f", lineHeight: 1.6 }}>"{interview.manager_remark}"</div>
              </div>
            </div>
          )}

          {/* Recruiter notes */}
          {interview.recruiter_notes && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: C.ink3, marginBottom: 8 }}>Recruiter Notes</div>
              <div style={{ padding: "12px 14px", background: C.surface, borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 11, color: C.ink2, lineHeight: 1.6, fontStyle: "italic" }}>
                "{interview.recruiter_notes}"
              </div>
            </div>
          )}

          {/* Previous round feedback */}
          {interview.previous_feedback?.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: C.ink3, marginBottom: 8 }}>Previous Round Feedback</div>
              {interview.previous_feedback.map((f, i) => (
                <div key={i} style={{ padding: "12px 14px", background: C.greenL, borderRadius: 8, border: "1px solid #86efac", marginBottom: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#14532d", marginBottom: 4 }}>{f.round} · {f.date}</div>
                  {f.recommendation && <div style={{ fontSize: 10, color: "#166534", marginBottom: 4 }}>Recommendation: <strong>{f.recommendation}</strong></div>}
                  {f.notes && <div style={{ fontSize: 11, color: "#166534", lineHeight: 1.6 }}>"{f.notes}"</div>}
                </div>
              ))}
            </div>
          )}

          {/* Resume */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: C.ink3, marginBottom: 10 }}>Resume</div>
            {resumeUrl ? (
              <div style={{ display: "flex", gap: 10 }}>
                <Btn variant="outline" style={{ flex: 1 }} onClick={() => window.open(resumeUrl, "_blank")}>👁 View Resume</Btn>
                <a href={resumeUrl} download={dlName} style={{ flex: 1, textDecoration: "none" }}>
                  <Btn variant="outline" style={{ width: "100%", justifyContent: "center" }}>⬇ Download</Btn>
                </a>
              </div>
            ) : (
              <div style={{ padding: "14px 16px", background: C.surface, borderRadius: 8, fontSize: 12, color: C.ink3, textAlign: "center", border: `1px dashed ${C.border}` }}>
                No resume uploaded
              </div>
            )}
          </div>

          {/* Teams link */}
          {interview.teams_link && (
            <a href={interview.teams_link} target="_blank" rel="noreferrer" style={{ display: "block", textDecoration: "none" }}>
              <Btn variant="teal" style={{ width: "100%", justifyContent: "center" }}>📹 Join Teams Meeting</Btn>
            </a>
          )}
        </div>
      </div>
    </>
  );
};

/* ── Slot Selection Modal ── */
const SlotSelectionModal = ({ open, interview, onClose, onSubmit, submitting }) => {
  const [newDate, setNewDate] = useState("");
  const [newTime, setNewTime] = useState("");
  const [pendingSlots, setPendingSlots] = useState([]);

  const addSlot = () => {
    if (!newDate || !newTime) return;
    const dup = pendingSlots.find(s => s.slot_date === newDate && s.slot_time === newTime);
    if (dup) return;
    setPendingSlots(prev => [...prev, { slot_date: newDate, slot_time: newTime }]);
    setNewTime("");
  };

  const removeSlot = idx => setPendingSlots(prev => prev.filter((_, i) => i !== idx));

  const handleSubmit = () => {
    if (pendingSlots.length === 0) return;
    onSubmit(pendingSlots);
    setPendingSlots([]);
    setNewDate("");
    setNewTime("");
  };

  const existingSlots = interview?.slots || [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add Available Interview Slots"
      width={520}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn
            variant="teal"
            disabled={pendingSlots.length === 0 || submitting}
            onClick={handleSubmit}
          >
            {submitting ? "Submitting…" : `✓ Submit ${pendingSlots.length > 0 ? `(${pendingSlots.length} slot${pendingSlots.length > 1 ? "s" : ""})` : "Slots"}`}
          </Btn>
        </>
      }
    >
      {interview && (
        <div style={{ marginBottom: 14, padding: "10px 14px", background: C.tealL, borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: C.ink }}>{interview.candidate_name}</div>
          <div style={{ fontSize: 11, color: C.ink3 }}>{interview.role} · {interview.round}</div>
        </div>
      )}

      <div style={{ marginBottom: 16, padding: "10px 12px", background: C.blueL, borderRadius: 8, fontSize: 12, color: "#1e3a8a", lineHeight: 1.5 }}>
        ℹ Candidate will receive these slots via email and choose their preferred time. A Teams meeting will be generated automatically after their selection.
      </div>

      {/* Existing slots already in DB */}
      {existingSlots.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 8 }}>Previously Added Slots</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {existingSlots.map(s => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: s.is_selected ? C.greenL : C.surface, borderRadius: 8, border: `1px solid ${s.is_selected ? "#86efac" : C.border}` }}>
                <span style={{ fontSize: 12, color: C.ink2 }}>
                  📅 {s.slot_date} · 🕐 {formatTime(s.slot_time)}
                </span>
                {s.is_selected
                  ? <Badge type="green">✓ Selected by candidate</Badge>
                  : <Badge type="gray">Pending</Badge>
                }
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add new slots */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 8 }}>Add New Slot</div>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 10, color: C.ink3, display: "block", marginBottom: 4 }}>Date</label>
            <input
              type="date"
              value={newDate}
              min={todayISO()}
              onChange={e => setNewDate(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.ink, fontFamily: "inherit", outline: "none", boxSizing: "border-box" }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 10, color: C.ink3, display: "block", marginBottom: 4 }}>Time</label>
            <input
              type="time"
              value={newTime}
              onChange={e => setNewTime(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.ink, fontFamily: "inherit", outline: "none", boxSizing: "border-box" }}
            />
          </div>
          <Btn variant="teal" onClick={addSlot} disabled={!newDate || !newTime} style={{ flexShrink: 0 }}>
            + Add
          </Btn>
        </div>
      </div>

      {/* Pending (unsaved) slots */}
      {pendingSlots.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 8 }}>Slots to Submit</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {pendingSlots.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "#f0fdfa", borderRadius: 8, border: `1px solid ${C.teal}40` }}>
                <span style={{ fontSize: 12, color: C.ink2 }}>
                  📅 {s.slot_date} · 🕐 {formatTime(s.slot_time)}
                </span>
                <button onClick={() => removeSlot(i)} style={{ border: "none", background: "none", cursor: "pointer", color: C.red, fontSize: 14 }}>✕</button>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, padding: "8px 12px", background: C.greenL, borderRadius: 8, border: "1px solid #86efac", fontSize: 12, color: "#14532d", fontWeight: 600 }}>
            ✓ {pendingSlots.length} slot{pendingSlots.length > 1 ? "s" : ""} ready — candidate will be notified via email.
          </div>
        </div>
      )}
    </Modal>
  );
};

/* ── Slot Workflow Indicator ── */
const SlotWorkflow = ({ status }) => {
  const steps = [
    { label: "Slots Added",          done: ["Slots Added", "Candidate Notified", "Scheduled", "Completed"].includes(status) },
    { label: "Candidate Notified",   done: ["Candidate Notified", "Scheduled", "Completed"].includes(status) },
    { label: "Candidate Chose Slot", done: ["Scheduled", "Completed"].includes(status) },
    { label: "Interview Scheduled",  done: ["Scheduled", "Completed"].includes(status) },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {steps.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: i < steps.length - 1 ? 12 : 0, position: "relative" }}>
          {i < steps.length - 1 && (
            <div style={{ position: "absolute", left: 9, top: 20, width: 2, height: "100%", background: s.done ? C.teal : C.border }} />
          )}
          <div style={{ width: 20, height: 20, borderRadius: "50%", flexShrink: 0, background: s.done ? C.teal : C.border, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#fff", zIndex: 1 }}>
            {s.done ? "✓" : ""}
          </div>
          <div style={{ fontSize: 12, fontWeight: s.done ? 600 : 400, color: s.done ? C.ink : C.ink3 }}>{s.label}</div>
        </div>
      ))}
    </div>
  );
};

/* ── Feedback Submission Modal ── */
const FeedbackModal = ({ open, interview, onClose, onSubmit, submitting }) => {
  const empty = { technicalRating: 0, commRating: 0, problemRating: 0, notes: "", recommendation: "" };
  const [form, setForm] = useState(empty);
  const up = k => v => setForm(f => ({ ...f, [k]: v }));

  const RatingRow = ({ label, field }) => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: `1px solid ${C.surface}` }}>
      <span style={{ fontSize: 13, fontWeight: 500, color: C.ink }}>{label}</span>
      <div style={{ display: "flex", gap: 6 }}>
        {[1, 2, 3, 4, 5].map(n => (
          <button key={n} onClick={() => up(field)(n)}
            style={{ border: "none", background: "none", cursor: "pointer", fontSize: 20, color: n <= form[field] ? C.amber : C.border, padding: 0, lineHeight: 1, transition: "color .1s" }}>★</button>
        ))}
      </div>
    </div>
  );

  const canSubmit = form.technicalRating > 0 && form.commRating > 0 && form.problemRating > 0 && form.recommendation && form.notes.trim();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Submit Interview Feedback"
      width={520}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="teal" disabled={!canSubmit || submitting} onClick={() => onSubmit(form)}>
            {submitting ? "Submitting…" : "Submit Feedback"}
          </Btn>
        </>
      }
    >
      {interview && (
        <div style={{ marginBottom: 18, display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", background: C.surface, borderRadius: 10 }}>
          <Avt name={interview.candidate_name} size={36} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{interview.candidate_name}</div>
            <div style={{ fontSize: 11, color: C.ink3 }}>{interview.role} · {interview.round}</div>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 4 }}>Evaluation Ratings</div>
        <RatingRow label="Technical Skills" field="technicalRating" />
        <RatingRow label="Communication"    field="commRating"      />
        <RatingRow label="Problem Solving"  field="problemRating"   />
      </div>

      <div style={{ marginBottom: 18 }}>
        <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, display: "block", marginBottom: 8 }}>
          Recommendation <span style={{ color: C.red }}>*</span>
        </label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {[
            { value: "Strong Hire", bg: C.greenL,  color: "#14532d", border: "#86efac", icon: "⭐" },
            { value: "Hire",        bg: C.tealL,   color: "#134e4a", border: C.teal,    icon: "✓" },
            { value: "Neutral",     bg: "#f1f5f9", color: "#334155", border: "#cbd5e1", icon: "~" },
            { value: "Reject",      bg: C.redL,    color: "#7f1d1d", border: "#fecaca", icon: "✕" },
          ].map(opt => (
            <button key={opt.value} onClick={() => up("recommendation")(opt.value)}
              style={{ padding: "10px 14px", borderRadius: 10, fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", transition: "all .15s", background: form.recommendation === opt.value ? opt.bg : "#fff", color: form.recommendation === opt.value ? opt.color : C.ink2, border: `2px solid ${form.recommendation === opt.value ? opt.border : C.border}`, display: "flex", alignItems: "center", gap: 6 }}>
              <span>{opt.icon}</span> {opt.value}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: C.ink3, lineHeight: 1.5 }}>
          ⓘ This is your recommendation only. Final hire/reject decision is made by the manager.
        </div>
      </div>

      <div>
        <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, display: "block", marginBottom: 6 }}>
          Detailed Notes <span style={{ color: C.red }}>*</span>
        </label>
        <textarea
          rows={4}
          value={form.notes}
          onChange={e => up("notes")(e.target.value)}
          placeholder="Summarise the interview — technical depth, communication, problem-solving approach, overall impression…"
          style={{ width: "100%", padding: "10px 12px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.ink, outline: "none", fontFamily: "inherit", resize: "vertical", boxSizing: "border-box", lineHeight: 1.6 }}
        />
      </div>
    </Modal>
  );
};


/* ════ TAB CONTENT COMPONENTS ════ */

/* ── Tab 1: Assigned Interviews ── */
function AssignedTab({ interviews, onViewCandidate, onSelectSlots, onSubmitFeedback }) {
  if (!interviews?.length) return (
    <EmptyState icon="📋" title="No interviews assigned yet" subtitle="Interviews will appear here once a recruiter assigns you to a candidate." />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {interviews.map(iv => (
        <div
          key={iv.round_id}
          style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)", transition: "box-shadow .15s" }}
          onMouseEnter={e => e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.07)"}
          onMouseLeave={e => e.currentTarget.style.boxShadow = "0 1px 4px rgba(0,0,0,0.04)"}
        >
          {/* Top row */}
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <Avt name={iv.candidate_name} size={40} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: C.ink }}>{iv.candidate_name}</div>
                <div style={{ fontSize: 11, color: C.ink3, marginTop: 2 }}>
                  {[iv.role, iv.exp, iv.company].filter(Boolean).join(" · ")}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {statusBadge(iv.status)}
              <span style={{ fontSize: 10, color: C.ink3, fontFamily: "monospace" }}>{iv.req_id}</span>
            </div>
          </div>

          {/* Round + Skills row */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6, background: C.navy, color: "#fff" }}>{iv.round}</span>
            {iv.skills.slice(0, 3).map(s => <Chip key={s}>{s}</Chip>)}
            {iv.skills.length > 3 && <Chip color={C.ink3} bg={C.surface}>+{iv.skills.length - 3}</Chip>}
          </div>

          {/* Schedule info (if scheduled) */}
          {iv.date && (
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12, padding: "8px 12px", background: C.surface, borderRadius: 8 }}>
              <span style={{ fontSize: 12, color: C.ink2 }}>📅 {iv.date}{iv.time ? `, ${formatTime(iv.time)}` : " — Time TBD"}</span>
              {iv.teams_link && (
                <a href={iv.teams_link} target="_blank" rel="noreferrer" style={{ fontSize: 11, fontWeight: 600, color: C.blue, textDecoration: "none" }}>📹 Join Teams Meeting →</a>
              )}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Btn variant="outline" style={{ fontSize: 11 }} onClick={() => onViewCandidate(iv)}>👤 View Candidate</Btn>
            {iv.status === "Awaiting Slot Selection" && (
              <Btn variant="teal" style={{ fontSize: 11 }} onClick={() => onSelectSlots(iv)}>📅 Add Available Slots</Btn>
            )}
            {["Slots Added", "Candidate Notified"].includes(iv.status) && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ padding: "4px 12px", background: C.blueL, borderRadius: 8, fontSize: 11, color: C.blue, fontWeight: 600 }}>
                  {iv.status === "Candidate Notified"
                    ? "✉ Candidate notified — awaiting slot selection…"
                    : "⏳ Slots added — notifying candidate…"}
                </div>
                <Btn variant="outline" style={{ fontSize: 11 }} onClick={() => onSelectSlots(iv)}>+ More Slots</Btn>
              </div>
            )}
            {iv.status === "Scheduled" && (
              <Btn variant="teal" style={{ fontSize: 11 }} onClick={() => onSubmitFeedback(iv)}>★ Submit Feedback</Btn>
            )}
            {iv.status === "Completed" && (
              <span style={{ fontSize: 11, fontWeight: 600, color: C.green, display: "flex", alignItems: "center", gap: 4 }}>✓ Feedback Submitted</span>
            )}
          </div>

          {/* Slot workflow indicator */}
          {["Slots Added", "Candidate Notified"].includes(iv.status) && (
            <div style={{ marginTop: 14, padding: "14px 16px", background: C.surface, borderRadius: 10, border: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 12 }}>Interview Workflow</div>
              <SlotWorkflow status={iv.status} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Tab 2: Upcoming Interviews ── */
function UpcomingTab({ upcoming, onViewCandidate }) {
  if (!upcoming?.length) return (
    <EmptyState icon="📅" title="No upcoming interviews" subtitle="Scheduled interviews will appear here." />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {upcoming.map(iv => {
        const dateParts = iv.date ? iv.date.split(" ") : [];
        const dayNum  = dateParts[0] || "";
        const monthYr = dateParts.slice(1).join(" ") || "";

        return (
          <div key={iv.round_id} style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px", display: "flex", alignItems: "center", gap: 16, boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
            {/* Date badge */}
            <div style={{ width: 52, height: 52, borderRadius: 10, background: C.blueL, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.blue, lineHeight: 1 }}>{dayNum}</div>
              <div style={{ fontSize: 9, fontWeight: 700, color: "#93c5fd", textTransform: "uppercase" }}>{monthYr}</div>
            </div>
            {/* Details */}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{iv.candidate_name}</div>
              <div style={{ fontSize: 11, color: C.ink3, marginTop: 2 }}>{iv.role} · {iv.round}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
                {iv.time && <span style={{ fontSize: 11, color: C.ink2 }}>🕐 {formatTime(iv.time)}</span>}
                <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 4, background: C.purpleL, color: C.purple }}>📹 Teams</span>
              </div>
            </div>
            {/* Actions */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
              {iv.teams_link ? (
                <a href={iv.teams_link} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8, background: C.blue, color: "#fff", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
                  📹 Join Meeting
                </a>
              ) : (
                <span style={{ fontSize: 11, color: C.amber, fontWeight: 600 }}>⏳ Link pending</span>
              )}
              <Btn variant="outline" style={{ fontSize: 11 }} onClick={() => onViewCandidate(iv)}>👤 View Candidate</Btn>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Tab 3: Calendar ── */
function CalendarTab({ events }) {
  const now = new Date();
  const [displayDate, setDisplayDate] = useState(new Date(now.getFullYear(), now.getMonth(), 1));

  const year  = displayDate.getFullYear();
  const month = displayDate.getMonth();
  const monthName = displayDate.toLocaleString("default", { month: "long" });

  const firstDayOfWeek = new Date(year, month, 1).getDay();
  const daysInMonth    = new Date(year, month + 1, 0).getDate();

  const days = [];
  for (let i = 0; i < firstDayOfWeek; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(d);
  while (days.length % 7 !== 0) days.push(null);

  const weeks = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));

  const todayDay   = now.getDate();
  const todayMonth = now.getMonth();
  const todayYear  = now.getFullYear();

  // Filter events for current month/year
  const monthEvents = (events || []).filter(e => {
    try {
      const d = new Date(e.date + "T00:00:00");
      return d.getFullYear() === year && d.getMonth() === month;
    } catch { return false; }
  });

  const eventsByDay = {};
  monthEvents.forEach(e => {
    const day = new Date(e.date + "T00:00:00").getDate();
    if (!eventsByDay[day]) eventsByDay[day] = [];
    eventsByDay[day].push(e);
  });

  const prevMonth = () => setDisplayDate(new Date(year, month - 1, 1));
  const nextMonth = () => setDisplayDate(new Date(year, month + 1, 1));
  const dayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <div>
      <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: C.ink }}>{monthName} {year}</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={prevMonth} style={{ border: `1px solid ${C.border}`, background: "#fff", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 12, color: C.ink2, fontFamily: "inherit" }}>← Prev</button>
            <button onClick={nextMonth} style={{ border: `1px solid ${C.border}`, background: "#fff", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 12, color: C.ink2, fontFamily: "inherit" }}>Next →</button>
          </div>
        </div>

        {/* Day labels */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", borderBottom: `1px solid ${C.border}` }}>
          {dayLabels.map(d => (
            <div key={d} style={{ padding: "10px 0", textAlign: "center", fontSize: 11, fontWeight: 700, color: C.ink3, textTransform: "uppercase", letterSpacing: ".05em" }}>{d}</div>
          ))}
        </div>

        {/* Date grid */}
        {weeks.map((week, wi) => (
          <div key={wi} style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", borderBottom: wi < weeks.length - 1 ? `1px solid ${C.surface}` : "none" }}>
            {week.map((day, di) => {
              const isToday  = day === todayDay && month === todayMonth && year === todayYear;
              const dayEvts  = day ? (eventsByDay[day] || []) : [];
              return (
                <div key={di} style={{ minHeight: 70, padding: "8px 6px", borderRight: di < 6 ? `1px solid ${C.surface}` : "none", background: isToday ? "#f0fdfa" : "#fff" }}>
                  {day && (
                    <>
                      <div style={{ width: 24, height: 24, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: isToday ? 700 : 400, color: isToday ? "#fff" : C.ink, background: isToday ? C.teal : "transparent", marginBottom: 4 }}>
                        {day}
                      </div>
                      {dayEvts.map((ev, ei) => (
                        <div key={ei} style={{ padding: "2px 5px", borderRadius: 4, background: calendarColor(ev.candidate_name), fontSize: 9, fontWeight: 700, color: "#fff", marginBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                          title={`${ev.candidate_name}${ev.time ? " · " + ev.time : ""}`}>
                          {ev.candidate_name.split(" ")[0]}
                        </div>
                      ))}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      {monthEvents.length > 0 && (
        <div style={{ marginTop: 14, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: C.ink3, fontWeight: 600 }}>Scheduled interviews:</span>
          {monthEvents.map((ev, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: calendarColor(ev.candidate_name) }} />
              <span style={{ fontSize: 11, color: C.ink2 }}>{ev.candidate_name} — {ev.day} {ev.month}{ev.time ? ", " + ev.time : ""}</span>
            </div>
          ))}
        </div>
      )}
      {monthEvents.length === 0 && (
        <div style={{ marginTop: 14, fontSize: 12, color: C.ink3, textAlign: "center" }}>No scheduled interviews in {monthName} {year}</div>
      )}
    </div>
  );
}

/* ── Tab 4: Feedback History ── */
function FeedbackHistoryTab({ history }) {
  if (!history?.length) return (
    <EmptyState icon="📝" title="No feedback submitted yet" subtitle="Your submitted feedback records will appear here." />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {history.map(f => (
        <div key={f.id} style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <Avt name={f.candidate_name} size={38} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{f.candidate_name}</div>
                <div style={{ fontSize: 11, color: C.ink3 }}>{f.role} · {f.round}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {recommendationBadge(f.recommendation)}
              <span style={{ fontSize: 11, color: C.ink3 }}>{f.date}</span>
            </div>
          </div>

          {/* Ratings */}
          <div style={{ display: "flex", gap: 20, marginBottom: 12, padding: "10px 14px", background: C.surface, borderRadius: 8, flexWrap: "wrap" }}>
            {[
              ["Technical",       f.technical_rating],
              ["Communication",   f.comm_rating],
              ["Problem Solving", f.problem_rating],
            ].map(([lbl, val]) => (
              <div key={lbl} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3 }}>{lbl}</span>
                <StarRating value={val || 0} />
              </div>
            ))}
          </div>

          {/* Notes */}
          {f.notes && (
            <div style={{ fontSize: 12, color: C.ink2, lineHeight: 1.6, fontStyle: "italic" }}>"{f.notes}"</div>
          )}
        </div>
      ))}
    </div>
  );
}


/* ════════════════════════════════════════════════
   MAIN PAGE
   ════════════════════════════════════════════════ */
export default function InterviewerRecruitmentPage() {
  const [activeTab,    setActiveTab]    = useState("assigned");
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [profileIv,    setProfileIv]    = useState(null);
  const [slotsOpen,    setSlotsOpen]    = useState(false);
  const [slotsIv,      setSlotsIv]      = useState(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackIv,   setFeedbackIv]   = useState(null);
  const [toasts,       setToasts]       = useState([]);

  // ── Data state ──
  const [stats,          setStats]          = useState({ assigned: 0, today: 0, pending_feedback: 0, completed: 0 });
  const [assignments,    setAssignments]    = useState([]);
  const [upcoming,       setUpcoming]       = useState([]);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [feedbackHistory,setFeedbackHistory]= useState([]);

  // ── Loading / error state ──
  const [loading,            setLoading]            = useState(true);
  const [error,              setError]              = useState(null);
  const [slotsSubmitting,    setSlotsSubmitting]    = useState(false);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);

  const toast = (msg, type = "success") => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3500);
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, assignData, upData, calData, fbData] = await Promise.all([
        interviewerApi.getStats(),
        interviewerApi.getAssignments(),
        interviewerApi.getUpcoming(),
        interviewerApi.getCalendar(),
        interviewerApi.getFeedbackHistory(),
      ]);
      setStats(statsData);
      setAssignments(assignData);
      setUpcoming(upData);
      setCalendarEvents(calData);
      setFeedbackHistory(fbData);
    } catch (e) {
      setError(e.message || "Failed to load recruitment data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const openProfile  = iv => { setProfileIv(iv);  setProfileOpen(true);  };
  const openSlots    = iv => { setSlotsIv(iv);    setSlotsOpen(true);    };
  const openFeedback = iv => { setFeedbackIv(iv); setFeedbackOpen(true); };

  const handleSlotsSubmit = async (slots) => {
    setSlotsSubmitting(true);
    try {
      await interviewerApi.addSlots(slotsIv.round_id, slots);
      toast(`${slots.length} slot${slots.length > 1 ? "s" : ""} submitted for ${slotsIv.candidate_name} — candidate will be notified`, "success");
      setSlotsOpen(false);
      setSlotsIv(null);
      await loadAll();
    } catch (e) {
      toast(e.message || "Failed to submit slots", "error");
    } finally {
      setSlotsSubmitting(false);
    }
  };

  const handleFeedbackSubmit = async (form) => {
    setFeedbackSubmitting(true);
    try {
      await interviewerApi.submitFeedback(feedbackIv.round_id, {
        technical_rating: form.technicalRating,
        comm_rating:      form.commRating,
        problem_rating:   form.problemRating,
        recommendation:   form.recommendation,
        notes:            form.notes,
      });
      toast(`Feedback submitted for ${feedbackIv.candidate_name}`, "success");
      setFeedbackOpen(false);
      setFeedbackIv(null);
      await loadAll();
    } catch (e) {
      toast(e.message || "Failed to submit feedback", "error");
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const TABS = [
    { id: "assigned",  label: "Assigned Interviews" },
    { id: "upcoming",  label: "Upcoming Interviews"  },
    { id: "calendar",  label: "Calendar"             },
    { id: "history",   label: "Feedback History"     },
  ];

  return (
    <div style={{ fontFamily: "'DM Sans',system-ui,sans-serif" }}>

      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>Recruitment</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: C.ink3 }}>Manage assigned interviews and candidate evaluations</p>
        </div>
        <button
          onClick={loadAll}
          disabled={loading}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", border: `1px solid ${C.border}`, borderRadius: 8, background: "#fff", cursor: loading ? "not-allowed" : "pointer", fontSize: 12, color: C.ink2, fontFamily: "inherit", opacity: loading ? 0.6 : 1 }}
        >
          🔄 {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{ marginBottom: 20, padding: "12px 16px", background: C.redL, border: "1px solid #fecaca", borderRadius: 10, fontSize: 13, color: C.red, display: "flex", alignItems: "center", gap: 10 }}>
          ⚠ {error}
          <button onClick={loadAll} style={{ marginLeft: "auto", border: "none", background: "none", cursor: "pointer", fontSize: 12, color: C.red, fontWeight: 600, fontFamily: "inherit" }}>Retry</button>
        </div>
      )}

      {/* Overview stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 24 }}>
        {[
          { label: "ASSIGNED INTERVIEWS", value: stats.assigned,        sub: "Total assigned",      subC: C.ink3,  bg: C.tealL,  icon: "📋", accentColor: C.teal   },
          { label: "UPCOMING TODAY",      value: stats.today,           sub: "Scheduled today",     subC: C.blue,  bg: C.blueL,  icon: "📅", accentColor: C.blue   },
          { label: "PENDING FEEDBACK",    value: stats.pending_feedback,sub: "Awaiting submission", subC: C.amber, bg: C.amberL, icon: "⏳", accentColor: C.amber  },
          { label: "COMPLETED",           value: stats.completed,       sub: "Feedback submitted",  subC: C.green, bg: C.greenL, icon: "✅", accentColor: C.green  },
        ].map((s, i) => (
          <div key={i} style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, padding: "18px 20px", position: "relative", overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
            <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: s.accentColor }} />
            <div style={{ width: 36, height: 36, borderRadius: 9, background: s.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17, marginBottom: 12 }}>{s.icon}</div>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: C.ink3, marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: C.ink, lineHeight: 1, marginBottom: 4 }}>
              {loading ? <span style={{ display: "inline-block", width: 40, height: 28, background: C.surface, borderRadius: 6 }} /> : s.value}
            </div>
            <div style={{ fontSize: 11, fontWeight: 600, color: s.subC }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Tab navigation */}
      <div style={{ display: "flex", gap: 2, marginBottom: 24, borderBottom: `1px solid ${C.border}` }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            style={{ border: "none", background: "none", padding: "10px 20px", fontFamily: "inherit", fontWeight: 600, fontSize: 13, cursor: "pointer", color: activeTab === t.id ? C.teal : C.ink3, borderBottom: `2.5px solid ${activeTab === t.id ? C.teal : "transparent"}`, transition: "all .15s", marginBottom: -1 }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading ? (
        <Spinner />
      ) : (
        <>
          {activeTab === "assigned" && (
            <AssignedTab
              interviews={assignments}
              onViewCandidate={openProfile}
              onSelectSlots={openSlots}
              onSubmitFeedback={openFeedback}
            />
          )}
          {activeTab === "upcoming" && (
            <UpcomingTab upcoming={upcoming} onViewCandidate={openProfile} />
          )}
          {activeTab === "calendar" && (
            <CalendarTab events={calendarEvents} />
          )}
          {activeTab === "history" && (
            <FeedbackHistoryTab history={feedbackHistory} />
          )}
        </>
      )}

      {/* Candidate profile drawer */}
      <CandidateProfileDrawer
        open={profileOpen}
        interview={profileIv}
        onClose={() => { setProfileOpen(false); setProfileIv(null); }}
      />

      {/* Slot selection modal */}
      <SlotSelectionModal
        open={slotsOpen}
        interview={slotsIv}
        onClose={() => { setSlotsOpen(false); setSlotsIv(null); }}
        onSubmit={handleSlotsSubmit}
        submitting={slotsSubmitting}
      />

      {/* Feedback modal */}
      <FeedbackModal
        open={feedbackOpen}
        interview={feedbackIv}
        onClose={() => { setFeedbackOpen(false); setFeedbackIv(null); }}
        onSubmit={handleFeedbackSubmit}
        submitting={feedbackSubmitting}
      />

      {/* Toast container */}
      {toasts.length > 0 && (
        <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 999, display: "flex", flexDirection: "column", gap: 8 }}>
          {toasts.map(t => (
            <div key={t.id} style={{ background: C.navy, color: "#fff", padding: "12px 18px", borderRadius: 10, fontSize: 12, fontWeight: 500, display: "flex", alignItems: "center", gap: 10, boxShadow: "0 4px 20px rgba(0,0,0,0.2)", maxWidth: 340 }}>
              <span style={{ color: t.type === "success" ? "#4ade80" : t.type === "error" ? "#f87171" : "#60a5fa", fontSize: 16 }}>
                {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}
              </span>
              {t.msg}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
