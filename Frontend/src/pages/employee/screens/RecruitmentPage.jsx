/**
 * RecruitmentPage.jsx
 * RBAC-gated Recruitment module for the Employee Dashboard.
 * All data loaded from /recruiter/* backend APIs — zero hardcoded mock values.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as api from "../../../services/recruiterApi";
import { closeAndOnboard as apiCloseAndOnboard } from "../../../services/recruiterApi";
import { requestNewSkillGlobal } from "../../../services/recruitmentApi";
import { X, AlertTriangle, Plus } from "../../../components/lucideShim";
import { useAuth } from "../../../context/AuthContext";
import { canAccessSkillApproval, canCloseAndOnboard, canAssignRecruiter } from "../../../utils/recruitmentAccess";
import SkillApprovalPage from "./SkillApprovalPage";

/* ── Design tokens ── */
const C = {
  navy:"#0d1b2a", navy2:"#1a2d42", navy3:"#243855",
  teal:"#0ea5a0", tealL:"#e0f7f6",
  ink:"#0d1b2a", ink2:"#3a4d5c", ink3:"#7a8fa0",
  surface:"#f4f7fa", white:"#fff", border:"#e2eaf3",
  green:"#16a34a", greenL:"#dcfce7",
  red:"#dc2626", redL:"#fee2e2",
  amber:"#d97706", amberL:"#fef3c7",
  blue:"#2563eb", blueL:"#eff6ff",
  purple:"#7c3aed", purpleL:"#f5f3ff",
  // Shared tokens used by Manager-compatible Skills component
  accent:"#F97316", light:"#F1F5F9", muted:"#64748B",
  text:"#0F172A",   yellow:"#F59E0B",
};

/* ── Avatar colour pool (deterministic from name) ── */
const AV_POOL = ["#14b8a6","#0ea5e9","#3b82f6","#8b5cf6","#f59e0b","#ef4444","#22c55e","#a855f7","#ec4899","#06b6d4"];
function avtColor(str) {
  let h = 0;
  for (let i = 0; i < (str||"").length; i++) h = (h*31 + str.charCodeAt(i)) >>> 0;
  return AV_POOL[h % AV_POOL.length];
}
function initials(name) {
  return (name||"?").split(" ").filter(Boolean).map(w=>w[0]).slice(0,2).join("").toUpperCase();
}

/* ── Source → badge type map ── */
const SRC_TYPE = { linkedin:"blue", referral:"teal", naukri:"blue", indeed:"purple", hirist:"amber", careers:"purple", "careers portal":"purple" };
function srcType(s) { return SRC_TYPE[(s||"").toLowerCase()] || "gray"; }

/* ── Priority → badge type map ── */
const PRI_TYPE = { urgent:"red", high:"amber", medium:"blue", normal:"gray", low:"gray", filled:"green", sourcing:"teal" };
function priType(s) { return PRI_TYPE[(s||"").toLowerCase()] || "gray"; }

/* ── Skill badge colour by index ── */
const SKILL_PALETTES = [
  {bg:C.blueL, color:"#1e3a8a"},{bg:C.tealL, color:"#134e4a"},
  {bg:C.amberL,color:"#78350f"},{bg:C.purpleL,color:"#4c1d95"},
  {bg:C.greenL,color:"#14532d"},{bg:"#fdf4ff",color:"#701a75"},
];
function skillPalette(i) { return SKILL_PALETTES[i % SKILL_PALETTES.length]; }

/* ── UI helpers ── */
const Badge = ({ type, children }) => {
  const map = { green:{bg:C.greenL,color:"#14532d"}, red:{bg:C.redL,color:"#7f1d1d"}, amber:{bg:C.amberL,color:"#78350f"}, blue:{bg:C.blueL,color:"#1e3a8a"}, purple:{bg:C.purpleL,color:"#4c1d95"}, teal:{bg:C.tealL,color:"#134e4a"}, gray:{bg:"#f1f5f9",color:"#334155"} };
  const s = map[type] || map.gray;
  return <span style={{ display:"inline-flex",alignItems:"center",gap:4,padding:"3px 9px",borderRadius:20,fontSize:10,fontWeight:700,background:s.bg,color:s.color }}><span style={{ width:5,height:5,borderRadius:"50%",background:s.color,display:"inline-block" }} />{children}</span>;
};
const Skill = ({ children, bg=C.tealL, color="#134e4a" }) => (
  <span style={{ fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:4,background:bg,color }}>{children}</span>
);
const Btn = ({ children, variant="outline", onClick, style={}, disabled=false }) => {
  const base = { display:"inline-flex",alignItems:"center",gap:6,padding:"8px 16px",borderRadius:8,fontSize:12,fontWeight:600,cursor:disabled?"not-allowed":"pointer",border:"none",fontFamily:"inherit",transition:"all .15s",opacity:disabled?0.6:1 };
  const variants = { primary:{background:C.navy,color:"#fff"}, teal:{background:C.teal,color:"#fff"}, outline:{background:"#fff",color:C.ink2,border:`1px solid ${C.border}`}, ghost:{background:C.surface,color:C.ink2} };
  return <button style={{ ...base, ...variants[variant], ...style }} onClick={disabled?undefined:onClick} disabled={disabled}>{children}</button>;
};
const Avt = ({ initials:init, color, size=28 }) => (
  <div style={{ width:size,height:size,borderRadius:"50%",background:color,display:"flex",alignItems:"center",justifyContent:"center",fontSize:size*0.38,fontWeight:700,color:"#fff",flexShrink:0 }}>{init}</div>
);

/* ── Toast ── */
function formatApiError(err, fallback = "Something went wrong") {
  const detail = err?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const msg = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item?.msg && Array.isArray(item?.loc)) return `${item.loc.join(".")}: ${item.msg}`;
        if (item?.msg) return item.msg;
        return null;
      })
      .filter(Boolean)
      .join("; ");
    if (msg) return msg;
  }
  if (detail && typeof detail === "object") {
    try { return JSON.stringify(detail); } catch {}
  }
  if (typeof err?.message === "string" && err.message.trim()) return err.message;
  return fallback;
}

function useToast() {
  const [toasts,setToasts] = useState([]);
  const show = (msg,type="info") => {
    const safeMsg = typeof msg === "string" ? msg : formatApiError({ data: { detail: msg } }, "Something went wrong");
    const id=Date.now();
    setToasts(t=>[...t,{id,msg:safeMsg,type}]);
    setTimeout(()=>setToasts(t=>t.filter(x=>x.id!==id)),3500);
  };
  return { toasts, show };
}
const ToastContainer = ({ toasts }) => {
  const icons={success:"✓",error:"✕",info:"ℹ"}; const colors={success:"#4ade80",error:"#f87171",info:"#60a5fa"};
  return <div style={{ position:"fixed",bottom:24,right:24,zIndex:999,display:"flex",flexDirection:"column",gap:8 }}>{toasts.map(t=><div key={t.id} style={{ background:C.navy,color:"#fff",padding:"12px 18px",borderRadius:10,fontSize:12,fontWeight:500,display:"flex",alignItems:"center",gap:10,boxShadow:"0 4px 20px rgba(0,0,0,0.2)",maxWidth:320 }}><span style={{ color:colors[t.type],fontSize:16,fontWeight:700 }}>{icons[t.type]}</span><span>{t.msg}</span></div>)}</div>;
};

/* ── StatCard ── */
const StatCard = ({ icon,value,label,trend,trendUp,accentColor,iconBg,iconColor,loading }) => (
  <div style={{ background:C.white,border:`1px solid ${C.border}`,borderRadius:12,padding:18,position:"relative",overflow:"hidden" }}>
    <div style={{ position:"absolute",bottom:0,left:0,right:0,height:3,background:accentColor }} />
    <div style={{ width:38,height:38,borderRadius:10,background:iconBg,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:12 }}>
      <span style={{ fontSize:19,color:iconColor }}>{icon}</span>
    </div>
    <div style={{ fontSize:28,fontWeight:700,color:C.ink,lineHeight:1 }}>{loading?"…":value}</div>
    <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginTop:4 }}>{label}</div>
    <div style={{ fontSize:11,fontWeight:600,marginTop:7,display:"flex",alignItems:"center",gap:3,color:trendUp?C.green:C.amber }}>{trendUp?"↑":"⚠"} {trend}</div>
  </div>
);

/* ── Card wrappers ── */
const Card = ({ children,style={} }) => <div style={{ background:C.white,border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden",...style }}>{children}</div>;
const CardHeader = ({ title,badge,action }) => (
  <div style={{ padding:"14px 20px",borderBottom:`1px solid ${C.surface}`,display:"flex",alignItems:"center",justifyContent:"space-between" }}>
    <h3 style={{ fontSize:13,fontWeight:700,color:C.ink,margin:0 }}>{title}{badge!=null&&<span style={{ fontSize:11,background:C.surface,color:C.ink3,padding:"2px 9px",borderRadius:10,fontWeight:600,marginLeft:8 }}>{badge}</span>}</h3>
    {action}
  </div>
);

/* ── Modal wrapper ── */
const Modal = ({ open,onClose,title,width=700,children,footer }) => {
  if (!open) return null;
  return (
    <div style={{ position:"fixed",inset:0,background:"rgba(13,27,42,0.55)",zIndex:200,display:"flex",alignItems:"center",justifyContent:"center" }} onClick={e=>{ if(e.target===e.currentTarget) onClose(); }}>
      <div style={{ background:"#fff",borderRadius:16,width,maxWidth:"95vw",maxHeight:"90vh",overflowY:"auto",boxShadow:"0 20px 60px rgba(0,0,0,0.2)" }}>
        <div style={{ padding:"20px 24px",borderBottom:`1px solid ${C.border}`,display:"flex",alignItems:"center",justifyContent:"space-between",position:"sticky",top:0,background:"#fff",zIndex:10 }}>
          <h2 style={{ fontSize:15,fontWeight:700,color:C.ink,margin:0 }}>{title}</h2>
          <button onClick={onClose} style={{ width:32,height:32,borderRadius:8,background:C.surface,border:"none",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",fontSize:18,color:C.ink3 }}>✕</button>
        </div>
        <div style={{ padding:24 }}>{children}</div>
        {footer&&<div style={{ padding:"16px 24px",borderTop:`1px solid ${C.border}`,display:"flex",alignItems:"center",justifyContent:"flex-end",gap:10,background:"#fafbfd",borderRadius:"0 0 16px 16px" }}>{footer}</div>}
      </div>
    </div>
  );
};

/* ── Loading / Empty states ── */
const LoadingRows = ({ rows=3 }) => (
  <div style={{ padding:16 }}>
    {Array.from({length:rows}).map((_,i)=>(
      <div key={i} style={{ height:48,background:"linear-gradient(90deg,#f4f7fa 25%,#e2eaf3 50%,#f4f7fa 75%)",backgroundSize:"400% 100%",borderRadius:8,marginBottom:10,animation:"pulse 1.4s ease-in-out infinite" }} />
    ))}
    <style>{`@keyframes pulse{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}`}</style>
  </div>
);
const EmptyState = ({ icon="📭", msg="No data found." }) => (
  <div style={{ padding:"40px 20px",textAlign:"center",color:C.ink3 }}>
    <div style={{ fontSize:32,marginBottom:10 }}>{icon}</div>
    <div style={{ fontSize:13,fontWeight:500 }}>{msg}</div>
  </div>
);

/* ── Stage date/time formatters (used by DetailPanel interview details) ── */
function _fmtStageDate(d) {
  if (!d) return "TBD";
  try {
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-GB", { weekday:"short", day:"2-digit", month:"short", year:"numeric" });
  } catch { return d; }
}
function _fmtStageTime(t) {
  if (!t) return "TBD";
  try {
    const [h, m] = t.split(":").map(Number);
    const ampm = h >= 12 ? "PM" : "AM";
    return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${ampm}`;
  } catch { return t; }
}

/* ── Candidate Detail Slide-over ── */
// Stages that mean an interview has already been assigned
const INTERVIEW_ASSIGNED_STAGES = ['Awaiting Slot Selection','Interview Scheduled','HR Round','Selected','Onboarding'];

const DetailPanel = ({ candidate, name, onClose, onReschedule, onScheduleInterview, onAddRound, extraRounds=[], loading, onCloseAndOnboard, canOnboard }) => {
  if (loading) return (
    <>
      <div style={{ position:"fixed",inset:0,zIndex:150 }} onClick={onClose} />
      <div style={{ position:"fixed",right:0,top:0,bottom:0,width:440,background:"#fff",borderLeft:`1px solid ${C.border}`,zIndex:160,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",boxShadow:"-10px 0 40px rgba(0,0,0,0.1)" }}>
        <div style={{ fontSize:28,marginBottom:12 }}>⏳</div>
        <div style={{ fontSize:13,color:C.ink3 }}>Loading candidate…</div>
      </div>
    </>
  );
  if (!candidate) return null;

  const isRejected = candidate.mgr_approval_status === "rejected";
  const canAddRound = !isRejected && candidate.pipeline.some(p=>(p.feedback&&p.feedback.trim())||(p.managerRemark&&p.managerRemark.trim()));
  const triggerStage = [...candidate.pipeline].reverse().find(p=>(p.feedback&&p.feedback.trim())||(p.managerRemark&&p.managerRemark.trim()));
  // Bug 2 fix: determine interview state from pipeline — do not hardcode
  const isInterviewAssigned = candidate.pipeline.some(
    p => INTERVIEW_ASSIGNED_STAGES.includes(p.label) && (p.status === 'active' || p.status === 'done')
  );

  return (
    <>
      <div style={{ position:"fixed",inset:0,zIndex:150 }} onClick={onClose} />
      {/* Bug 1 fix: outer = flex column, NO overflowY — header/footer fixed, body scrolls */}
      <div style={{ position:"fixed",right:0,top:0,bottom:0,width:440,background:"#fff",borderLeft:`1px solid ${C.border}`,zIndex:160,display:"flex",flexDirection:"column",boxShadow:"-10px 0 40px rgba(0,0,0,0.1)" }}>
        {/* Header — flexShrink:0 keeps it fixed, no sticky needed */}
        <div style={{ flexShrink:0,padding:"20px 20px 16px",borderBottom:`1px solid ${C.border}`,display:"flex",alignItems:"center",gap:12,background:"#fff",zIndex:5 }}>
          <div style={{ width:48,height:48,borderRadius:12,background:"linear-gradient(135deg,#14b8a6,#0ea5e9)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:15,fontWeight:700,color:"#fff",flexShrink:0 }}>
            {(name||"").split(" ").map(w=>w[0]).join("").slice(0,2).toUpperCase()}
          </div>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:15,fontWeight:700,color:C.ink }}>{name}</div>
            <div style={{ fontSize:11,color:C.ink3,marginTop:2 }}>{candidate.role}</div>
          </div>
          <button onClick={onClose} style={{ border:"none",background:C.surface,borderRadius:8,width:32,height:32,cursor:"pointer",fontSize:18,display:"flex",alignItems:"center",justifyContent:"center" }}>✕</button>
        </div>
        {/* Body — flex:1 + overflowY:auto = scrollable zone; paddingBottom clears footer */}
        <div style={{ flex:1,overflowY:"auto",padding:20,paddingBottom:80 }}>
          <div style={{ marginBottom:22 }}>
            <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:10 }}>Contact & Professional</div>
            <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:10 }}>
              {[["Email",candidate.email],["Phone",candidate.phone],["Experience",candidate.exp],["Current Employer",candidate.employer],["Current CTC",candidate.ctc],["Expected CTC",candidate.expCtc],["Notice Period",candidate.notice],["Source",candidate.source]].map(([lbl,val])=>(
                <div key={lbl}><div style={{ fontSize:10,color:C.ink3,fontWeight:600 }}>{lbl}</div><div style={{ fontSize:12,fontWeight:600,color:C.ink,marginTop:2 }}>{val||"—"}</div></div>
              ))}
            </div>
          </div>
          <div style={{ marginBottom:22 }}>
            <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:10 }}>Skills</div>
            <div style={{ display:"flex",gap:4,flexWrap:"wrap" }}>
              {(candidate.skills||[]).map(s=><Skill key={s}>{s}</Skill>)}
            </div>
          </div>
          {isRejected&&candidate.rejection_reason&&(
            <div style={{ marginBottom:20,padding:"12px 14px",background:C.redL,borderRadius:8,border:`1px solid #fca5a5` }}>
              {/* <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.red,marginBottom:6 }}>Manager Rejection Remarks</div> */}
              {/* <div style={{ fontSize:12,color:"#7f1d1d",lineHeight:1.6,fontStyle:"italic" }}>"{candidate.rejection_reason}"</div> */}
              {candidate.rejected_by&&<div style={{ fontSize:11,color:C.ink3,marginTop:6 }}>Rejected by: <strong style={{ color:C.ink2 }}>{candidate.rejected_by}</strong></div>}
              {candidate.rejected_at&&<div style={{ fontSize:11,color:C.ink3,marginTop:2 }}>On: {candidate.rejected_at}</div>}
            </div>
          )}
          <div style={{ marginBottom:22 }}>
            <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:12 }}>Interview Timeline</div>
            <div style={{ position:"relative" }}>
              {/* Connector stops before the last item so it never bleeds outside */}
              {candidate.pipeline.length>1&&<div style={{ position:"absolute",left:12,top:24,bottom:24,width:1.5,background:`linear-gradient(to bottom,${C.teal}50,${C.border})`,zIndex:0 }} />}
              {candidate.pipeline.map((p,i)=>{
                const isDone=p.status==="done"; const isActive=p.status==="active";
                const isRejectedStage=p.label==="Rejected"&&isActive;
                const dotBg=isDone?C.green:isRejectedStage?C.red:isActive?C.amber:C.border;
                const dotShadow=isRejectedStage?`0 0 0 3px ${C.red}40`:isActive?`0 0 0 3px ${C.amber}40`:"none";
                const stageBorder=isDone?"#86efac":isRejectedStage?"#fca5a5":isActive?"#fcd34d":C.border;
                const stageBg=isDone?C.greenL:isRejectedStage?C.redL:isActive?C.amberL:"transparent";
                return (
                  <div key={i} style={{ display:"flex",gap:10,marginBottom:i<candidate.pipeline.length-1||extraRounds.length>0?12:0,position:"relative",zIndex:1 }}>
                    <div style={{ width:24,height:24,borderRadius:"50%",flexShrink:0,marginTop:1,background:dotBg,border:isActive?`2px solid #fff`:"none",boxShadow:dotShadow,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,color:isDone||isActive?"#fff":C.ink3 }}>
                      {isDone?"✓":isRejectedStage?"✗":"○"}
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ display:"flex",alignItems:"center",gap:10,padding:"10px 12px",borderRadius:8,border:`1px solid ${stageBorder}`,background:stageBg }}>
                        <div style={{ fontSize:12,fontWeight:600,color:isRejectedStage?C.red:C.ink }}>{p.label}</div>
                      </div>
                      {isDone&&p.feedback&&p.feedback.trim()&&(
                        <div style={{ marginTop:6,padding:"10px 12px",background:C.white,borderRadius:8,border:`1px solid ${C.border}` }}>
                          <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:4 }}>Interviewer Feedback</div>
                          <div style={{ fontSize:11,color:C.ink,lineHeight:1.6,fontStyle:"italic" }}>"{p.feedback}"</div>
                        </div>
                      )}
                      {p.managerRemark&&p.managerRemark.trim()&&(
                        <div style={{ marginTop:6,padding:"10px 12px",background:C.amberL,borderRadius:8,border:"1px solid #fcd34d" }}>
                          <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:"#92400e",marginBottom:4 }}>Manager Remark</div>
                          <div style={{ fontSize:11,color:"#78350f",lineHeight:1.6 }}>"{p.managerRemark}"</div>
                        </div>
                      )}
                      {isRejectedStage&&p.rejection_reason&&p.rejection_reason.trim()&&(
                        <div style={{ marginTop:6,padding:"10px 12px",background:C.redL,borderRadius:8,border:"1px solid #fca5a5" }}>
                          <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.red,marginBottom:4 }}>Rejection Reason</div>
                          <div style={{ fontSize:11,color:"#7f1d1d",lineHeight:1.6,fontStyle:"italic" }}>"{p.rejection_reason}"</div>
                        </div>
                      )}
                      {isActive&&p.label==="Interview Scheduled"&&(p.interviewer||p.interview_date)&&(
                        <div style={{ marginTop:6,padding:"10px 12px",background:C.blueL,borderRadius:8,border:"1px solid #93c5fd" }}>
                          <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.blue,marginBottom:6 }}>Scheduled Interview</div>
                          {p.interviewer&&<div style={{ fontSize:11,color:C.ink2,marginBottom:3,display:"flex",alignItems:"center",gap:5 }}><span>👤</span><strong>{p.interviewer}</strong></div>}
                          {p.interview_date&&<div style={{ fontSize:11,color:C.ink2,marginBottom:3,display:"flex",alignItems:"center",gap:5 }}><span>📅</span><span>{_fmtStageDate(p.interview_date)}</span></div>}
                          {p.interview_time&&<div style={{ fontSize:11,color:C.ink2,display:"flex",alignItems:"center",gap:5 }}><span>🕐</span><span>{_fmtStageTime(p.interview_time)}</span></div>}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {extraRounds.map((r,i)=>(
                <div key={`extra-${i}`} style={{ display:"flex",gap:10,marginBottom:12,position:"relative",zIndex:1 }}>
                  <div style={{ width:24,height:24,borderRadius:"50%",flexShrink:0,marginTop:1,background:C.blue,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,color:"#fff" }}>○</div>
                  <div style={{ flex:1 }}>
                    <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 12px",borderRadius:8,border:`1px solid ${C.blueL}`,background:C.blueL }}>
                      <div style={{ fontSize:12,fontWeight:600,color:C.ink }}>{r.name}</div>
                      <span style={{ fontSize:9,fontWeight:700,padding:"2px 8px",borderRadius:10,background:C.blue,color:"#fff" }}>Added</span>
                    </div>
                    {(r.interviewer||r.date)&&<div style={{ marginTop:4,fontSize:10,color:C.ink3,paddingLeft:12 }}>{r.interviewer&&`👤 ${r.interviewer}`}{r.interviewer&&r.date&&" · "}{r.date&&`📅 ${r.date}`}</div>}
                  </div>
                </div>
              ))}
            </div>
            {canAddRound?(
              <div style={{ marginTop:14 }}>
                {triggerStage&&<div style={{ display:"flex",alignItems:"flex-start",gap:8,padding:"10px 12px",background:C.amberL,border:"1px solid #fcd34d",borderRadius:8,marginBottom:10 }}><span style={{ fontSize:13,flexShrink:0 }}>⚠</span><div style={{ fontSize:11,color:"#78350f",lineHeight:1.5 }}>{triggerStage.managerRemark?<><strong>Manager requested:</strong> {triggerStage.managerRemark}</>:<><strong>Interviewer recommended</strong> further evaluation based on feedback from {triggerStage.label}.</>}</div></div>}
                <button onClick={()=>onAddRound(name)} style={{ display:"flex",alignItems:"center",justifyContent:"center",gap:8,width:"100%",padding:"10px 14px",border:`1.5px dashed ${C.teal}`,borderRadius:10,background:C.tealL,color:C.teal,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit",transition:"all .15s" }} onMouseEnter={e=>{e.currentTarget.style.background="#b2f0ed";e.currentTarget.style.borderStyle="solid";}} onMouseLeave={e=>{e.currentTarget.style.background=C.tealL;e.currentTarget.style.borderStyle="dashed";}}>+ Add Additional Round</button>
              </div>
            ):(candidate.pipeline.some(p=>p.status==="active"||p.status==="done")&&<div style={{ marginTop:12,padding:"9px 12px",background:C.surface,borderRadius:8,fontSize:11,color:C.ink3,lineHeight:1.5 }}>Additional rounds can be requested once interviewer feedback or a manager remark is recorded.</div>)}
          </div>
          <div>
            <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:10 }}>Recruiter Notes</div>
            <div style={{ background:C.surface,borderRadius:8,padding:12,fontSize:12,color:C.ink2,lineHeight:1.6,fontStyle:"italic" }}>{candidate.notes||"No notes yet."}</div>
          </div>
        </div>
        {/* Footer — flexShrink:0 + no sticky = always visible at bottom of flex column */}
        <div style={{ flexShrink:0,padding:"16px 20px",borderTop:`1px solid ${C.border}`,display:"flex",flexDirection:"column",gap:8,background:"#fff" }}>
          <div style={{ display:"flex",gap:8 }}>
            {candidate.resume_url
              ? <a href={`${import.meta.env.VITE_API_URL||"http://localhost:8000"}/${candidate.resume_url}`} target="_blank" rel="noreferrer" style={{ flex:1 }}><Btn variant="outline" style={{ width:"100%",justifyContent:"center" }}>⬇ Resume</Btn></a>
              : <Btn variant="outline" style={{ flex:1 }}>⬇ Resume</Btn>
            }
            {/* Rejected candidates cannot be scheduled for interviews */}
            {!isRejected&&(isInterviewAssigned
              ? <Btn variant="outline" style={{ flex:1 }} onClick={()=>onReschedule(null)}>📅 Reschedule Interview</Btn>
              : <Btn variant="teal"    style={{ flex:1 }} onClick={onScheduleInterview}>📅 Schedule Interview</Btn>
            )}
            {isRejected&&(
              <div style={{ flex:1,padding:"8px 12px",background:C.redL,borderRadius:8,border:`1px solid #fca5a5`,fontSize:11,fontWeight:600,color:C.red,display:"flex",alignItems:"center",justifyContent:"center",gap:5 }}>
                ✗ Rejected — No further interviews
              </div>
            )}
          </div>
          {/* Close & Onboard — only for Admin / HR */}
          {canOnboard && !candidate.onboarded_at && (
            <button
              onClick={onCloseAndOnboard}
              style={{ width:"100%",padding:"9px 14px",borderRadius:8,border:"1.5px solid #7c3aed",background:C.purpleL,color:"#7c3aed",fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit",display:"flex",alignItems:"center",justifyContent:"center",gap:6,transition:"all .15s" }}
              onMouseEnter={e=>{e.currentTarget.style.background="#ede9fe";}}
              onMouseLeave={e=>{e.currentTarget.style.background=C.purpleL;}}
            >
              🚀 Close &amp; Onboard
            </button>
          )}
          {candidate.onboarded_at && (
            <div style={{ padding:"9px 14px",background:C.greenL,borderRadius:8,border:`1px solid #86efac`,fontSize:11,fontWeight:700,color:C.green,display:"flex",alignItems:"center",justifyContent:"center",gap:6 }}>
              ✓ Moved to Onboarding
            </div>
          )}
        </div>
      </div>
    </>
  );
};

/* ── Add Round Modal ── */
const ROUND_TYPES = ["Technical","System Design","Architecture","Client Discussion","Cultural Fit","Custom"];
function AddRoundModal({ open, candidateName, onClose, onConfirm, showToast }) {
  const empty = { name:"", type:"", interviewer:"", date:"", time:"", reason:"" };
  const [form, setForm] = useState(empty);
  const up = k => e => setForm(f=>({ ...f, [k]: typeof e==="string"?e:e.target.value }));
  const handleConfirm = () => {
    if (!form.name.trim()||!form.type) { showToast("Round name and type are required","error"); return; }
    onConfirm({ ...form, id:`R-${Date.now()}` }); setForm(empty); onClose();
  };
  const inp = { width:"100%",padding:"9px 12px",border:`1px solid ${C.border}`,borderRadius:8,fontSize:12,color:C.ink,outline:"none",fontFamily:"inherit",background:C.white,boxSizing:"border-box" };
  const lbl = { fontSize:11,fontWeight:600,color:C.ink2,display:"block",marginBottom:5 };
  return (
    <Modal open={open} onClose={onClose} title="Add Additional Interview Round" width={500}
      footer={<><Btn variant="ghost" onClick={onClose}>Cancel</Btn><Btn variant="teal" onClick={handleConfirm}>+ Add Round</Btn></>}>
      {candidateName&&<div style={{ padding:"8px 12px",background:C.tealL,borderRadius:8,fontSize:12,color:C.teal,fontWeight:600,marginBottom:18 }}>Adding round for: {candidateName}</div>}
      <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
        <div><label style={lbl}>Round Name <span style={{ color:C.red }}>*</span></label><input style={inp} placeholder="e.g. System Design Round" value={form.name} onChange={up("name")} /></div>
        <div><label style={lbl}>Round Type <span style={{ color:C.red }}>*</span></label>
          <div style={{ display:"flex",flexWrap:"wrap",gap:8 }}>{ROUND_TYPES.map(t=><button key={t} onClick={()=>setForm(f=>({...f,type:t}))} style={{ padding:"6px 14px",borderRadius:8,fontSize:12,fontWeight:600,cursor:"pointer",fontFamily:"inherit",transition:"all .15s",background:form.type===t?C.teal:C.surface,color:form.type===t?"#fff":C.ink2,border:`1.5px solid ${form.type===t?C.teal:C.border}` }}>{t}</button>)}</div>
        </div>
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div><label style={lbl}>Schedule Date</label><input type="date" style={inp} value={form.date} onChange={up("date")} /></div>
          <div><label style={lbl}>Schedule Time</label><input type="time" style={inp} value={form.time} onChange={up("time")} /></div>
        </div>
        <div><label style={lbl}>Reason for Additional Round <span style={{ color:C.red }}>*</span></label>
          <textarea rows={3} style={{ ...inp,resize:"vertical" }} placeholder="e.g. Manager requested a system design evaluation…" value={form.reason} onChange={up("reason")} />
        </div>
      </div>
    </Modal>
  );
}
function AddCandidateModal({
  open,
  onClose,
  onConfirm,
  addSubmitting,
  addForm,
  upAdd,
  candidateSource,
  setCandidateSource,
  addReqList,
  addSkills,
  setAddSkills,
  addSkillInput,
  setAddSkillInput,
  resumeRef,
  coverRef,
  idProofRef,
  othersRef,
}) {
  const fg = { display:"flex",flexDirection:"column",gap:5 };
  const inp = { border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 12px",fontSize:12,fontFamily:"inherit",color:C.ink,outline:"none",width:"100%",background:"#fff",boxSizing:"border-box" };
  const lbl = { fontSize:11,fontWeight:600,color:C.ink2 };
  return (
    <Modal open={open} onClose={onClose} title="Add New Candidate"
      footer={<>
        <Btn variant="outline" onClick={onClose}>Cancel</Btn>
        <Btn variant="teal" onClick={onConfirm} disabled={addSubmitting}>{addSubmitting?"Saving…":"Save Candidate"}</Btn>
      </>}>
      {/* Basic Info */}
      <div style={{ marginBottom:24 }}>
        <div style={{ fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:14,paddingBottom:8,borderBottom:`1px solid ${C.border}` }}>Basic Information</div>
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div style={fg}><label style={lbl}>First Name *</label><input style={inp} placeholder="First name" value={addForm.first_name} onChange={upAdd("first_name")} /></div>
          <div style={fg}><label style={lbl}>Last Name</label><input style={inp} placeholder="Last name" value={addForm.last_name} onChange={upAdd("last_name")} /></div>
          <div style={fg}><label style={lbl}>Email *</label><input type="email" style={inp} placeholder="candidate@email.com" value={addForm.email} onChange={upAdd("email")} /></div>
          <div style={fg}><label style={lbl}>Mobile</label><input type="tel" style={inp} placeholder="+91 phone number" value={addForm.mobile} onChange={upAdd("mobile")} /></div>
        </div>
      </div>
      {/* Professional Details */}
      <div style={{ marginBottom:24 }}>
        <div style={{ fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:14,paddingBottom:8,borderBottom:`1px solid ${C.border}` }}>Professional Details</div>
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div style={fg}><label style={lbl}>Current Job Title</label><input style={inp} placeholder="e.g. Senior Engineer" value={addForm.current_job_title} onChange={upAdd("current_job_title")} /></div>
          <div style={fg}><label style={lbl}>Current Employer</label><input style={inp} placeholder="Company name" value={addForm.current_employer} onChange={upAdd("current_employer")} /></div>
          <div style={fg}><label style={lbl}>Current CTC</label><input style={inp} placeholder="Enter Current CTC" value={addForm.current_ctc} onChange={upAdd("current_ctc")} /></div>
          <div style={fg}><label style={lbl}>Expected CTC</label><input style={inp} placeholder="e.g. ₹18,00,000" value={addForm.expected_ctc} onChange={upAdd("expected_ctc")} /></div>
          <div style={fg}><label style={lbl}>Current Location</label><input style={inp} placeholder="Enter Current Location" value={addForm.curr_location} onChange={upAdd("curr_location")} /></div>
          <div style={fg}><label style={lbl}>Notice Period</label><input style={inp} placeholder="Enter Notice Period" value={addForm.notice_period} onChange={upAdd("notice_period")} /></div>
          <div style={{ gridColumn:"span 2",...fg }}><label style={lbl}>Experience (Years)</label><input type="number" style={{ ...inp,maxWidth:200 }} placeholder="e.g. 5" value={addForm.experience_years} onChange={upAdd("experience_years")} /></div>
          <div style={{ gridColumn:"span 2",...fg }}>
            <label style={lbl}>Source *</label>
            <select style={inp} value={candidateSource} onChange={e=>{setCandidateSource(e.target.value);upAdd("source")({target:{value:e.target.value}}); }}>
              <option value="">Select source…</option><option>LinkedIn</option><option>Naukri</option><option>Indeed</option><option>Hirist</option><option>Referral</option><option>Careers Portal</option><option>Others</option>
            </select>
            {candidateSource==="Others"&&<input style={{ ...inp,marginTop:10 }} placeholder="Enter source name" value={addForm.other_source} onChange={upAdd("other_source")} />}
          </div>
          <div style={{ gridColumn:"span 2",...fg }}><label style={lbl}>Assign to Requirement</label>
            <select style={inp} value={addForm.requirement_id} onChange={upAdd("requirement_id")}>
              <option value="">Select requirement…</option>
              {addReqList.map(r=><option key={r.db_id} value={r.db_id}>{r.req_id} · {r.title}</option>)}
            </select>
          </div>
          <div style={{ gridColumn:"span 2",...fg }}>
            <label style={lbl}>Skill Set</label>
            <div style={{ display:"flex",flexWrap:"wrap",gap:6,border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 10px",minHeight:42,background:"#fff" }}>
              {addSkills.map(s=><span key={s} style={{ display:"flex",alignItems:"center",gap:4,background:C.tealL,color:"#134e4a",fontSize:11,fontWeight:600,padding:"3px 8px",borderRadius:6 }}>{s}<button onClick={()=>setAddSkills(sk=>sk.filter(x=>x!==s))} style={{ border:"none",background:"transparent",cursor:"pointer",color:"#134e4a",fontSize:14,lineHeight:1,padding:0 }}>×</button></span>)}
              <input value={addSkillInput} onChange={e=>setAddSkillInput(e.target.value)} onKeyDown={e=>{ if(e.key==="Enter"||e.key===","){ e.preventDefault(); const v=addSkillInput.trim().replace(/,$/,""); if(v){setAddSkills(sk=>[...sk,v]);setAddSkillInput("");} } }} placeholder="Add skill…" style={{ border:"none",outline:"none",fontSize:12,fontFamily:"inherit",minWidth:80,flex:1,background:"transparent",color:C.ink }} />
            </div>
          </div>
        </div>
      </div>
      {/* Attachments */}
      <div>
        <div style={{ fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:C.ink3,marginBottom:14,paddingBottom:8,borderBottom:`1px solid ${C.border}` }}>Attachment Information</div>
        {[{label:"Resume",ref:resumeRef,accept:undefined,hint:undefined},{label:"Cover Letter",ref:coverRef,accept:undefined,hint:undefined},{label:"ID Proof",ref:idProofRef,accept:".pdf,.jpg,.jpeg,.png",hint:"PDF, JPG or PNG · Aadhaar, PAN, Passport, Driving License"},{label:"Others",ref:othersRef,accept:undefined,hint:undefined}].map(f=>(
          <div key={f.label} style={{ marginBottom:10 }}>
            <div style={{ display:"flex",alignItems:"center",gap:12 }}>
              <label style={{ width:110,fontSize:11,fontWeight:600,color:C.ink2 }}>{f.label}</label>
              <input type="file" ref={f.ref} accept={f.accept} style={{ flex:1,fontSize:12 }} />
            </div>
            {f.hint&&<div style={{ marginLeft:122,fontSize:10,color:C.ink3,marginTop:3 }}>{f.hint}</div>}
          </div>
        ))}
      </div>
    </Modal>
  );
}

function DuplicateCandidateModal({ open, duplicateCandidate, onCancel, onViewExisting }) {
  const matchedBy = duplicateCandidate?.matched_by || [];
  const matchCandidate = duplicateCandidate?.matched_candidate;
  const matchLines = matchedBy.map((reason) => reason === "email" ? "Email Match" : "Mobile Match");

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="Potential Duplicate Candidate Found"
      width={500}
      footer={
        <>
          <Btn variant="outline" onClick={onCancel}>Cancel Creation</Btn>
          <Btn variant="teal" onClick={onViewExisting} disabled={!duplicateCandidate?.matched_candidate_id}>
            View Existing Candidate
          </Btn>
        </>
      }
    >
      <div style={{ background:C.amberL, border:`1px solid #fcd34d`, borderRadius:8, padding:"12px 14px", marginBottom:18, fontSize:12, color:"#78350f" }}>
        A candidate with the same email address or mobile number already exists. A new candidate record will not be created.
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:16 }}>
        {[
          ["Candidate Name", matchCandidate?.candidate_name || "—"],
          ["Email", matchCandidate?.email || "—"],
          ["Mobile Number", matchCandidate?.mobile || "—"],
          ["Created Date", matchCandidate?.created_date ? new Date(matchCandidate.created_date).toLocaleString() : "—"],
        ].map(([label, value]) => (
          <div key={label} style={{ background:C.surface, borderRadius:8, padding:"10px 12px" }}>
            <div style={{ fontSize:10, fontWeight:700, textTransform:"uppercase", letterSpacing:".06em", color:C.ink3, marginBottom:4 }}>{label}</div>
            <div style={{ fontSize:12, fontWeight:600, color:C.ink, wordBreak:"break-word" }}>{value}</div>
          </div>
        ))}
      </div>

      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        <div style={{ fontSize:10, fontWeight:700, textTransform:"uppercase", letterSpacing:".06em", color:C.ink3 }}>Duplicate Reason</div>
        {matchLines.map((line) => (
          <div key={line} style={{ fontSize:12, fontWeight:600, color:C.green }}>✓ {line}</div>
        ))}
      </div>
    </Modal>
  );
}
/* ── Skill chip (approved = green, pending = amber) ─────────────────────────── */
function SkillChip({ label, onRemove, pending = false }) {
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:5, background:pending?"#FEF3C7":"#ECFDF5", color:pending?"#92400E":"#065F46", border:`1px solid ${pending?"#FCD34D":"#A7F3D0"}`, borderRadius:6, padding:"3px 10px", fontSize:12, fontWeight:600, whiteSpace:"nowrap" }}>
      {pending && <AlertTriangle size={10} color="#D97706" />}
      {label}
      {onRemove && <button onClick={onRemove} style={{ border:"none", background:"none", cursor:"pointer", padding:0, display:"flex", lineHeight:1 }}><X size={10} color={pending?"#D97706":"#059669"} /></button>}
    </span>
  );
}

/* ── Skills multi-select — fetches from skill_set master via API ─────────────
   Matches Manager implementation exactly including Request New Skill workflow. */
function SkillsInput({ value, onChange, pendingSkills, onAddPending, showToast }) {
  const [query, setQuery]           = useState("");
  const [showDrop, setShowDrop]     = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [allSkills, setAllSkills]   = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [masterLoaded, setMasterLoaded] = useState(false);
  const ref = useRef();

  // Load full master list on mount
  useEffect(() => {
    api.getAllSkills()
      .then(res => { setAllSkills((res || []).map(r => r.name)); setMasterLoaded(true); })
      .catch(() => setMasterLoaded(true));
  }, []);

  // Debounced search when user types ≥ 2 chars
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setSuggestions([]); return; }
    const timer = setTimeout(() => {
      api.searchSkillsApi(q, 15)
        .then(res => {
          const names = (res?.results || []).map(r => r.name);
          setSuggestions(names.filter(s => !value.includes(s) && !(pendingSkills||[]).includes(s)));
        })
        .catch(() => setSuggestions([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [query, value, pendingSkills]);

  const displayList = query.trim().length >= 2
    ? suggestions
    : allSkills.filter(s => !value.includes(s) && !(pendingSkills||[]).includes(s));

  const exactMatch   = allSkills.some(s => s.toLowerCase() === query.trim().toLowerCase())
                    || suggestions.some(s => s.toLowerCase() === query.trim().toLowerCase());
  const showNewSkill = query.trim().length > 1 && !exactMatch
                    && !value.includes(query.trim()) && !(pendingSkills||[]).includes(query.trim());

  const add = (skill) => { onChange([...value, skill]); setQuery(""); setShowDrop(false); };

  // Request new skill → HR Admin approval workflow (same as Manager)
  const requestNew = async () => {
    const skillName = query.trim();
    setRequesting(true);
    try {
      await requestNewSkillGlobal(skillName);
      onAddPending(skillName);
      setQuery(""); setShowDrop(false);
      if (showToast) showToast(`"${skillName}" sent for HR Admin approval`, "info");
    } catch (err) {
      const msg = err?.data?.detail || err?.message || "Request failed";
      if (showToast) showToast(msg, "error");
    } finally { setRequesting(false); }
  };

  // Close dropdown on outside click
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowDrop(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  return (
    <div ref={ref} style={{ position:"relative" }}>
      {/* Selected chips + search input */}
      <div
        style={{ border:`1px solid ${C.border}`, borderRadius:8, padding:"8px 10px", background:"#fff",
                 display:"flex", flexWrap:"wrap", gap:6, minHeight:46, cursor:"text" }}
        onClick={() => setShowDrop(true)}
      >
        {value.map(s => <SkillChip key={s} label={s} onRemove={() => onChange(value.filter(x => x !== s))} />)}
        {(pendingSkills||[]).map(s => <SkillChip key={s} label={s} pending onRemove={() => onAddPending(null, s)} />)}
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setShowDrop(true); }}
          onFocus={() => setShowDrop(true)}
          placeholder={value.length === 0 && (pendingSkills||[]).length === 0 ? "Search or select skills…" : ""}
          style={{ border:"none", outline:"none", fontSize:12, background:"transparent",
                   fontFamily:"inherit", minWidth:120, flex:1, color:C.text }}
        />
      </div>

      {/* Dropdown */}
      {showDrop && (displayList.length > 0 || showNewSkill) && (
        <div style={{ position:"absolute", top:"100%", left:0, right:0, zIndex:200, background:"#fff",
                      border:`1px solid ${C.border}`, borderRadius:8,
                      boxShadow:"0 4px 16px rgba(0,0,0,0.10)", maxHeight:240, overflowY:"auto", marginTop:4 }}>
          {displayList.length === 0 && !showNewSkill && (
            <div style={{ padding:"10px 14px", fontSize:12, color:C.muted }}>
              {masterLoaded ? "No skills found" : "Loading skills…"}
            </div>
          )}
          {displayList.map(s => (
            <div key={s} onMouseDown={() => add(s)}
              style={{ padding:"9px 14px", fontSize:13, cursor:"pointer", color:C.text }}
              onMouseEnter={e => e.currentTarget.style.background = C.light}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              {s}
            </div>
          ))}
          {showNewSkill && (
            <div
              onMouseDown={requesting ? undefined : requestNew}
              style={{ padding:"9px 14px", fontSize:13, cursor:requesting?"wait":"pointer",
                       color:C.accent, fontWeight:600, borderTop:`1px solid ${C.border}`,
                       display:"flex", alignItems:"center", gap:6, opacity:requesting?0.6:1 }}
              onMouseEnter={e => e.currentTarget.style.background = "#FFF7ED"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              <Plus size={13} color={C.accent} />
              {requesting ? "Sending request…" : `Request new skill: "${query.trim()}"`}
            </div>
          )}
        </div>
      )}

      {(pendingSkills||[]).length > 0 && (
        <div style={{ fontSize:11, color:C.yellow, marginTop:5, fontWeight:500 }}>
          ⏳ Pending HR Admin approval: {pendingSkills.join(", ")}
        </div>
      )}
    </div>
  );
}

/* ── New / Edit Requirement Modal ── */
const REQ_EMPTY = {
  title:"", client_name:"", department_id:"", employment_type:"", work_mode:"", location:"",
  min_experience:"", max_experience:"", openings:"1", priority:"Normal",
  skills:[], pendingSkills:[], job_description:"", qualification:"", budget_range:"", target_joining:"",
};

function NewRequirementModal({ open, onClose, onSuccess, editData, showToast }) {
  const [form, setForm]       = useState(REQ_EMPTY);
  const [depts, setDepts]     = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors]   = useState({});
  const isEdit = !!editData;

  useEffect(() => {
    if (!open) return;
    api.getDepartments().then(data => setDepts(data || [])).catch(() => {});
    if (editData) {
      setForm({
        title:            editData.title           || "",
        client_name:      editData.client_name      || "",
        department_id:    editData.department_id   || "",
        employment_type:  editData.employment_type || "",
        work_mode:        editData.work_mode        || "",
        location:         editData.location         || "",
        min_experience:   editData.min_exp != null  ? String(editData.min_exp) : "",
        max_experience:   editData.max_exp != null  ? String(editData.max_exp) : "",
        openings:         editData.openings != null ? String(editData.openings) : "1",
        priority:         editData.priority         || "Normal",
        skills:           editData.skills           || [],
        pendingSkills:    editData.pending_skills    || [],
        job_description:  editData.jd               || "",
        qualification:    editData.preferred_qualification || "",
        budget_range:     editData.budget_range     || "",
        target_joining:   editData.target_joining   || "",
      });
    } else {
      setForm(REQ_EMPTY);
    }
    setErrors({});
  }, [open, editData]);

  const up = k => e => setForm(f => ({ ...f, [k]: typeof e === "string" ? e : e.target.value }));

  // Add / remove a pending (awaiting HR approval) skill chip
  const addPending = (skill, removeSkill) => {
    if (removeSkill) { setForm(f => ({ ...f, pendingSkills: f.pendingSkills.filter(s => s !== removeSkill) })); }
    else if (skill)  { setForm(f => ({ ...f, pendingSkills: [...f.pendingSkills, skill] })); }
  };

  const validate = () => {
    const e = {};
    if (!form.title.trim())        e.title    = "Title is required";
    if (!form.department_id)       e.department_id = "Department is required";
    if (!form.skills.length)       e.skills   = "At least one skill is required";
    const min = parseInt(form.min_experience);
    const max = parseInt(form.max_experience);
    if (!isNaN(min) && !isNaN(max) && min > max) e.experience = "Min experience cannot exceed max";
    const open = parseInt(form.openings);
    if (isNaN(open) || open < 1)   e.openings = "Openings must be at least 1";
    if (form.target_joining) {
      const tj = new Date(form.target_joining);
      const today = new Date(); today.setHours(0,0,0,0);
      if (tj < today)              e.target_joining = "Target joining cannot be in the past";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    try {
      const payload = {
        title:           form.title.trim(),
        client_name:     form.client_name.trim() || null,
        department_id:   form.department_id || null,
        employment_type: form.employment_type || null,
        work_mode:       form.work_mode || null,
        location:        form.location.trim() || null,
        min_experience:  form.min_experience !== "" ? parseInt(form.min_experience) : null,
        max_experience:  form.max_experience !== "" ? parseInt(form.max_experience) : null,
        openings:        parseInt(form.openings) || 1,
        priority:        form.priority || "Normal",
        skills:          form.skills,
        pending_skills:  form.pendingSkills || [],
        job_description: form.job_description.trim() || null,
        qualification:   form.qualification.trim() || null,
        budget_range:    form.budget_range.trim() || null,
        target_joining:  form.target_joining || null,
      };
      if (isEdit) {
        await api.updateRequirement(editData.id, payload);
        showToast("Requirement updated successfully", "success");
      } else {
        await api.createRequirement(payload);
        showToast("Requirement created successfully", "success");
      }
      onSuccess();
      onClose();
    } catch (err) {
      showToast(err?.data?.detail || (isEdit ? "Failed to update requirement" : "Failed to create requirement"), "error");
    } finally { setSubmitting(false); }
  };

  const inp = { border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 12px",fontSize:12,fontFamily:"inherit",color:C.ink,outline:"none",width:"100%",background:"#fff",boxSizing:"border-box" };
  const lbl = { fontSize:11,fontWeight:600,color:C.ink2,display:"block",marginBottom:5 };
  const fg  = { display:"flex",flexDirection:"column",gap:4 };
  const err = { fontSize:10,color:C.red,marginTop:3 };

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Edit Requirement — ${editData?.id}` : "New Requirement"} width={680}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn variant="teal" onClick={handleSubmit} disabled={submitting}>{submitting ? (isEdit ? "Saving…" : "Creating…") : (isEdit ? "Save Changes" : "Create Requirement")}</Btn>
      </>}>
      <div style={{ display:"flex",flexDirection:"column",gap:18 }}>
        {/* Row 1 — Job Title */}
        <div style={fg}>
          <label style={lbl}>Job Title <span style={{ color:C.red }}>*</span></label>
          <input style={{ ...inp,borderColor:errors.title?C.red:C.border }} placeholder="e.g. Senior Frontend Engineer" value={form.title} onChange={up("title")} />
          {errors.title && <div style={err}>{errors.title}</div>}
        </div>
        {/* Row 2 — Client Name */}
        <div style={fg}>
          <label style={lbl}>Client Name</label>
          <input style={inp} placeholder="e.g. Acme Corp" value={form.client_name} onChange={up("client_name")} />
        </div>
        {/* Row 3 — Department + Employment Type */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div style={fg}>
            <label style={lbl}>Department <span style={{ color:C.red }}>*</span></label>
            <select style={{ ...inp,borderColor:errors.department_id?C.red:C.border }} value={form.department_id} onChange={up("department_id")}>
              <option value="">Select department…</option>
              {depts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            {errors.department_id && <div style={err}>{errors.department_id}</div>}
          </div>
          <div style={fg}>
            <label style={lbl}>Employment Type</label>
            <select style={inp} value={form.employment_type} onChange={up("employment_type")}>
              <option value="">Select…</option><option>Full Time</option><option>Contract</option><option>Internship</option>
            </select>
          </div>
        </div>
        {/* Row 4 — Work Mode + Location */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div style={fg}>
            <label style={lbl}>Work Mode</label>
            <select style={inp} value={form.work_mode} onChange={up("work_mode")}>
              <option value="">Select…</option><option>Remote</option><option>Hybrid</option><option>Onsite</option>
            </select>
          </div>
          <div style={fg}>
            <label style={lbl}>Location</label>
            <input style={inp} placeholder="e.g. Bangalore" value={form.location} onChange={up("location")} />
          </div>
        </div>
        {/* Row 5 — Min Exp + Max Exp + Openings + Priority */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:14 }}>
          <div style={fg}>
            <label style={lbl}>Min Experience (yrs)</label>
            <input type="number" min="0" style={inp} placeholder="0" value={form.min_experience} onChange={up("min_experience")} />
          </div>
          <div style={fg}>
            <label style={lbl}>Max Experience (yrs)</label>
            <input type="number" min="0" style={inp} placeholder="10" value={form.max_experience} onChange={up("max_experience")} />
            {errors.experience && <div style={err}>{errors.experience}</div>}
          </div>
          <div style={fg}>
            <label style={lbl}>Openings <span style={{ color:C.red }}>*</span></label>
            <input type="number" min="1" style={{ ...inp,borderColor:errors.openings?C.red:C.border }} placeholder="1" value={form.openings} onChange={up("openings")} />
            {errors.openings && <div style={err}>{errors.openings}</div>}
          </div>
          <div style={fg}>
            <label style={lbl}>Priority</label>
            <select style={inp} value={form.priority} onChange={up("priority")}>
              <option>Normal</option><option>Medium</option><option>High</option><option>Urgent</option>
            </select>
          </div>
        </div>
        {/* Row 6 — Skills */}
        <div style={fg}>
          <label style={lbl}>Required Skills <span style={{ color:C.red }}>*</span></label>
          <SkillsInput value={form.skills} onChange={skills => setForm(f => ({ ...f, skills }))} pendingSkills={form.pendingSkills} onAddPending={addPending} showToast={showToast} />
          {errors.skills && <div style={err}>{errors.skills}</div>}
        </div>
        {/* Row 7 — Job Description */}
        <div style={fg}>
          <label style={lbl}>Job Description</label>
          <textarea rows={5} style={{ ...inp,resize:"vertical" }} placeholder="Describe the role, responsibilities, and requirements…" value={form.job_description} onChange={up("job_description")} />
        </div>
        {/* Row 8 — Qualification */}
        <div style={fg}>
          <label style={lbl}>Preferred Qualification</label>
          <input style={inp} placeholder="e.g. B.E. / B.Tech in Computer Science" value={form.qualification} onChange={up("qualification")} />
        </div>
        {/* Row 9 — Target Joining + Budget Range */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
          <div style={fg}>
            <label style={lbl}>Target Joining Date</label>
            <input type="date" style={{ ...inp,borderColor:errors.target_joining?C.red:C.border }} value={form.target_joining} onChange={up("target_joining")} />
            {errors.target_joining && <div style={err}>{errors.target_joining}</div>}
          </div>
          <div style={fg}>
            <label style={lbl}>Budget Range</label>
            <input style={inp} placeholder="e.g. ₹18L – ₹28L" value={form.budget_range} onChange={up("budget_range")} />
          </div>
        </div>
      </div>
    </Modal>
  );
}

/* ════════════════════════════════════════════════
   MAIN COMPONENT
   ════════════════════════════════════════════════ */
export default function RecruitmentPage() {
  /* ── UI state ── */
  const [activeTab, setActiveTab]     = useState("overview");
  const [modal, setModal]             = useState(null);
  const [detailName, setDetailName]   = useState(null);
  const [detailData, setDetailData]   = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [feedbackCandidate, setFeedbackCandidate] = useState("");
  const [rescheduleRoundId, setRescheduleRoundId] = useState(null);
  const [rescheduleFor, setRescheduleFor]         = useState("");
  const [reqDetail, setReqDetail]     = useState(null);
  const [score, setScore]             = useState(0);
  const [rec, setRec]                 = useState(null);
  const [candidateSource, setCandidateSource] = useState("");
  const { toasts, show: toast } = useToast();

  /* ── Role-based feature flags ── */
  const { user } = useAuth();
  const canSeeSkillSet    = canAccessSkillApproval(user);
  const canOnboard        = canCloseAndOnboard(user);
  const canAssign         = canAssignRecruiter(user);

  /* ── Close & Onboard state ── */
  const [onboardTarget, setOnboardTarget]     = useState(null); // { candidate_id, full_name }
  const [onboardSubmitting, setOnboardSubmitting] = useState(false);

  /* ── Assign Recruiter state ── */
  const [recruiters, setRecruiters]           = useState([]);
  const [assignTarget, setAssignTarget]       = useState(null); // requirement object
  const [assignRecruiterVal, setAssignRecruiterVal] = useState('');
  const [assignSubmitting, setAssignSubmitting] = useState(false);

  /* ── API data state ── */
  const [stats, setStats]                   = useState({ open_reqs:0,total_candidates:0,pending_review:0,interviews_this_week:0,offers_sent:0 });
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [activeInterviews, setActiveInterviews]     = useState([]);
  const [upcomingInterviews, setUpcomingInterviews] = useState([]);
  const [candidates, setCandidates]         = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [requirements, setRequirements]     = useState([]);
  const [requirementsLoading, setRequirementsLoading] = useState(false);
  const [pipelineData, setPipelineData]     = useState({});
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineReqFilter, setPipelineReqFilter] = useState("All");
  const [interviews, setInterviews]         = useState([]);
  const [interviewsLoading, setInterviewsLoading] = useState(false);
  const [interviewers, setInterviewers]     = useState([]);
  const [addReqList, setAddReqList]         = useState([]);

  /* ── Requirement CRUD state ── */
  const [reqModal, setReqModal]             = useState(false);
  const [reqEditData, setReqEditData]       = useState(null);
  const [reqStatusFilter, setReqStatusFilter] = useState(() => {
    try { return localStorage.getItem('hrms.req.statusFilter') || 'All'; } catch { return 'All'; }
  });
  const [recruiterFilter, setRecruiterFilter] = useState(() => {
    try { return JSON.parse(localStorage.getItem('hrms.req.recruiterFilter') || '[]'); } catch { return []; }
  });
  const [closingReqId, setClosingReqId]     = useState(null);

  /* ── Extra rounds (local state for UI — API submits via add-round endpoint) ── */
  const [extraRoundsMap, setExtraRoundsMap] = useState({});
  const [addRoundModal, setAddRoundModal]   = useState(false);
  const [roundCandidate, setRoundCandidate] = useState(null);
  const [roundPipelineId, setRoundPipelineId] = useState(null);

  /* ── Add Candidate form state ── */
  const [addForm, setAddForm] = useState({ first_name:"",last_name:"",email:"",mobile:"",current_job_title:"",current_employer:"",current_ctc:"",expected_ctc:"",curr_location:"",notice_period:"",experience_years:"",source:"",other_source:"",requirement_id:"" });
  const [addSkills, setAddSkills]     = useState([]);
  const [addSkillInput, setAddSkillInput] = useState("");
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [duplicateCandidate, setDuplicateCandidate] = useState(null);
  const resumeRef      = useRef(); const coverRef = useRef();
  const idProofRef     = useRef(); const othersRef = useRef();

  /* ── Reschedule form state ── */
  const [rescheduleForm, setRescheduleForm] = useState({ new_date:"",new_time:"",interviewer_code:"",interview_format:"Microsoft Teams",reason:"" });
  const [rescheduleSubmitting, setRescheduleSubmitting] = useState(false);

  /* ── Schedule Interview form state (Bug 2) ── */
  const [scheduleIvForm, setScheduleIvForm] = useState({ round_name:"Technical Round", round_type:"Technical", interviewer_code:"", notes:"" });
  const [scheduleIvSubmitting, setScheduleIvSubmitting] = useState(false);

  /* ── Data loaders ── */
  const loadOverview = useCallback(async () => {
    setOverviewLoading(true);
    try {
      const [s, aiv, uiv] = await Promise.all([api.getStats(), api.getActiveInterviews(), api.getUpcomingInterviews()]);
      setStats(s||{open_reqs:0,total_candidates:0,pending_review:0,interviews_this_week:0,offers_sent:0});
      setActiveInterviews(aiv||[]);
      setUpcomingInterviews(uiv||[]);
    } catch { toast("Failed to load overview data","error"); }
    finally { setOverviewLoading(false); }
  }, []);

  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    try { const data = await api.getCandidates(); setCandidates(data||[]); }
    catch { toast("Failed to load candidates","error"); }
    finally { setCandidatesLoading(false); }
  }, []);

  const loadRequirements = useCallback(async (overrideIds) => {
    setRequirementsLoading(true);
    try {
      const ids = overrideIds !== undefined ? overrideIds : recruiterFilter;
      const params = ids.length > 0 ? { recruiter_ids: ids.join(',') } : {};
      const data = await api.getRequirements(params);
      setRequirements(data||[]);
    }
    catch { toast("Failed to load requirements","error"); }
    finally { setRequirementsLoading(false); }
  }, [recruiterFilter]);

  const loadRecruiters = useCallback(async () => {
    try { const data = await api.getRecruiters(); setRecruiters(data||[]); }
    catch {}
  }, []);

  const loadPipeline = useCallback(async (reqFilter="All") => {
    setPipelineLoading(true);
    try { const data = await api.getPipeline(reqFilter); setPipelineData(data||{}); }
    catch { toast("Failed to load pipeline","error"); }
    finally { setPipelineLoading(false); }
  }, []);

  const loadInterviews = useCallback(async () => {
    setInterviewsLoading(true);
    try { const data = await api.getAllInterviews(); setInterviews(data||[]); }
    catch { toast("Failed to load interviews","error"); }
    finally { setInterviewsLoading(false); }
  }, []);

  /* ── Persist filters to localStorage ── */
  useEffect(() => { try { localStorage.setItem('hrms.req.statusFilter', reqStatusFilter); } catch {} }, [reqStatusFilter]);
  useEffect(() => { try { localStorage.setItem('hrms.req.recruiterFilter', JSON.stringify(recruiterFilter)); } catch {} }, [recruiterFilter]);

  /* ── Bootstrap on mount ── */
  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => {
    if (activeTab==="candidates")   loadCandidates();
    if (activeTab==="requirements") { loadRequirements(); loadRecruiters(); }
    if (activeTab==="pipeline")     loadPipeline(pipelineReqFilter);
    if (activeTab==="interviews")   loadInterviews();
  }, [activeTab]);

  /* ── ESC closes modals ── */
  useEffect(() => {
    const h = e => { if(e.key==="Escape"){ setModal(null); closeDetail(); } };
    window.addEventListener("keydown",h);
    return ()=>window.removeEventListener("keydown",h);
  }, []);

  /* ── Detail panel ── */
  const openDetail = useCallback(async (candidateId) => {
    if (!candidateId) return;
    setDetailName(candidateId);
    setDetailData(null);
    setDetailLoading(true);
    try { const data = await api.getCandidateDetail(candidateId); setDetailData(data); }
    catch { toast("Failed to load candidate details","error"); }
    finally { setDetailLoading(false); }
  }, [toast]);
  const closeDetail = () => { setDetailName(null); setDetailData(null); setDetailLoading(false); };

  /* ── Reschedule ── */
  const openReschedule = (roundId, candidateName="") => {
    setRescheduleRoundId(roundId);
    setRescheduleFor(candidateName);
    setRescheduleForm({ new_date:"",new_time:"",interviewer_code:"",interview_format:"Microsoft Teams",reason:"" });
    setModal("reschedule");
    // Load interviewers for dropdown
    api.getInterviewers().then(data=>setInterviewers(data||[])).catch(()=>{});
  };
  const confirmReschedule = async () => {
    if (!rescheduleForm.new_date||!rescheduleForm.new_time) { toast("Date and time are required","error"); return; }
    if (!rescheduleRoundId) { toast("No interview round selected","error"); return; }
    setRescheduleSubmitting(true);
    try {
      await api.rescheduleInterview(rescheduleRoundId, {
        new_date: rescheduleForm.new_date, new_time: rescheduleForm.new_time,
        interviewer_code: rescheduleForm.interviewer_code||null,
        interview_format: rescheduleForm.interview_format, reason: rescheduleForm.reason||null,
      });
      setModal(null);
      toast("Interview rescheduled — calendars and emails updated","success");
      loadOverview(); if(activeTab==="interviews") loadInterviews();
    } catch(e) { toast(e?.data?.detail||"Failed to reschedule","error"); }
    finally { setRescheduleSubmitting(false); }
  };

  const openFeedback = (candidateId, candidateName="") => { setFeedbackCandidate(candidateName||candidateId); setScore(0); setRec(null); setModal("feedback"); };

  /* ── Schedule Interview (Bug 2) — opens ONLY when no interview exists ── */
  const openScheduleInterview = () => {
    setScheduleIvForm({ round_name:"Technical Round", round_type:"Technical", interviewer_code:"", notes:"" });
    api.getInterviewers().then(data=>setInterviewers(data||[])).catch(()=>{});
    setModal("scheduleInterview");
  };
  const confirmScheduleInterview = async () => {
    const candidateId = detailData?.candidate_id || detailName;
    if (!candidateId) { toast("Candidate details are still loading. Please try again.","error"); return; }
    if (!scheduleIvForm.interviewer_code) { toast("Please select an interviewer","error"); return; }
    setScheduleIvSubmitting(true);
    try {
      await api.assignInterviewer({
        candidate_id:    candidateId,
        round_name:      scheduleIvForm.round_name  || "Technical Round",
        round_type:      scheduleIvForm.round_type  || "Technical",
        interviewer_code: scheduleIvForm.interviewer_code,
      });
      setModal(null);
      toast("Interview assigned — candidate moved to Awaiting Slot Selection","success");
      if (candidateId) openDetail(candidateId);
      if (activeTab==="candidates") loadCandidates();
    } catch(e) { toast(formatApiError(e, "Failed to schedule interview"),"error"); }
    finally { setScheduleIvSubmitting(false); }
  };

  /* ── Add Candidate ── */
  const openAddCandidate = () => {
    setAddForm({ first_name:"",last_name:"",email:"",mobile:"",current_job_title:"",current_employer:"",current_ctc:"",expected_ctc:"",curr_location:"",notice_period:"",experience_years:"",source:"",other_source:"",requirement_id:"" });
    setAddSkills([]); setAddSkillInput(""); setCandidateSource("");
    setDuplicateCandidate(null);
    api.getOpenRequirements().then(data=>setAddReqList(data||[])).catch(()=>{});
    setModal("addCandidate");
  };
  const confirmAddCandidate = async () => {
    if (!addForm.first_name||!addForm.email) { toast("First name and email are required","error"); return; }
    setAddSubmitting(true);
    try {
      const duplicateCheck = await api.checkCandidateDuplicate({
        email: addForm.email,
        mobile: addForm.mobile || null,
      });
      if (duplicateCheck?.duplicate_found) {
        setDuplicateCandidate(duplicateCheck);
        setModal("duplicateCandidate");
        return;
      }

      const fd = new FormData();
      Object.entries(addForm).forEach(([k,v])=>{ if(v!==null&&v!==undefined&&v!=="") fd.append(k,v); });
      fd.append("skills", JSON.stringify(addSkills));
      if (resumeRef.current?.files?.[0])   fd.append("resume",       resumeRef.current.files[0]);
      if (coverRef.current?.files?.[0])    fd.append("cover_letter", coverRef.current.files[0]);
      if (idProofRef.current?.files?.[0])  fd.append("id_proof",     idProofRef.current.files[0]);
      if (othersRef.current?.files?.[0])   fd.append("others",       othersRef.current.files[0]);
      await api.addCandidate(fd);
      setModal(null); setCandidateSource("");
      setDuplicateCandidate(null);
      toast("Candidate added successfully and entered Sourcing stage","success");
      loadCandidates(); loadOverview();
    } catch(e) {
      const duplicate = e?.data?.duplicate_found ? e.data : (e?.data?.detail?.duplicate_found ? e.data.detail : null);
      if (duplicate?.duplicate_found) {
        setDuplicateCandidate(duplicate);
        setModal("duplicateCandidate");
      } else {
        toast(formatApiError(e, "Failed to add candidate"),"error");
      }
    }
    finally { setAddSubmitting(false); }
  };

  /* ── Add Round ── */
  const openAddRound = (candidateName) => {
    setRoundCandidate(candidateName);
    setRoundPipelineId(detailData?.pipeline_id||null);
    setAddRoundModal(true);
  };
  const handleAddRound = async (roundData) => {
    const pipelineId = roundPipelineId;
    if (!pipelineId) { toast("Cannot add round — pipeline ID missing","error"); return; }
    try {
      await api.addRound(pipelineId, { pipeline_id:pipelineId, round_name:roundData.name, round_type:roundData.type||"Technical", reason:roundData.reason||"" });
      setExtraRoundsMap(prev=>({ ...prev, [roundCandidate]:[...(prev[roundCandidate]||[]),roundData] }));
      setAddRoundModal(false); setRoundCandidate(null); setRoundPipelineId(null);
      toast(`"${roundData.name}" added — pipeline updated`,"success");
      if (detailData?.candidate_id) openDetail(detailData.candidate_id);
    } catch(e) { toast(e?.data?.detail||"Failed to add round","error"); }
  };

  /* ── Close & Onboard ── */
  const openCloseAndOnboard = (candidateId, fullName) => {
    setOnboardTarget({ candidate_id: candidateId, full_name: fullName });
    setModal("closeAndOnboard");
  };
  const confirmCloseAndOnboard = async () => {
    if (!onboardTarget) return;
    setOnboardSubmitting(true);
    try {
      const res = await apiCloseAndOnboard(onboardTarget.candidate_id);
      setModal(null);
      setOnboardTarget(null);
      toast(res?.message || `${onboardTarget.full_name} moved to onboarding`, "success");
      loadCandidates();
      loadOverview();
      closeDetail();
    } catch (e) {
      toast(formatApiError(e, "Failed to start onboarding"), "error");
    } finally {
      setOnboardSubmitting(false);
    }
  };

  const reqDetail_open = (req) => { setReqDetail(req); setModal("reqDetail"); };

  /* ── Recruiter filter toggle ── */
  const toggleRecruiterFilter = (id) => {
    const next = recruiterFilter.includes(id)
      ? recruiterFilter.filter(x => x !== id)
      : [...recruiterFilter, id];
    setRecruiterFilter(next);
    if (activeTab === "requirements") loadRequirements(next);
  };
  const clearRecruiterFilter = () => {
    setRecruiterFilter([]);
    if (activeTab === "requirements") loadRequirements([]);
  };

  /* ── Assign Recruiter handlers ── */
  const openAssignRecruiter = (req, e) => {
    e.stopPropagation();
    setAssignTarget(req);
    setAssignRecruiterVal(req.assigned_recruiter_id ? String(req.assigned_recruiter_id) : '');
    setModal('assignRecruiter');
    if (recruiters.length === 0) loadRecruiters();
  };
  const confirmAssignRecruiter = async () => {
    if (!assignTarget || !assignRecruiterVal) { toast("Please select a recruiter", "error"); return; }
    setAssignSubmitting(true);
    try {
      await api.assignRecruiter(assignTarget.req_id, parseInt(assignRecruiterVal, 10));
      toast(`Recruiter assigned to ${assignTarget.req_id}`, "success");
      loadRequirements();
      setModal(null);
      setAssignTarget(null);
      setAssignRecruiterVal('');
    } catch (e) {
      toast(formatApiError(e, "Failed to assign recruiter"), "error");
    } finally {
      setAssignSubmitting(false);
    }
  };

  /* ── Requirement CRUD handlers ── */
  const openNewReq  = () => { setReqEditData(null); setReqModal(true); };
  const openEditReq = async (req) => {
    try {
      const detail = await api.getRequirementDetail(req.req_id);
      setReqEditData(detail);
      setReqModal(true);
      setModal(null);
    } catch { toast("Failed to load requirement details", "error"); }
  };
  const onReqSuccess = () => { loadRequirements(); loadOverview(); };
  const handleCloseReq = async (reqId) => {
    setClosingReqId(reqId);
    try {
      await api.closeRequirement(reqId);
      toast("Requirement closed", "success");
      setModal(null);
      loadRequirements();
      loadOverview();
    } catch (e) { toast(e?.data?.detail || "Failed to close requirement", "error"); }
    finally { setClosingReqId(null); }
  };

  /* ── Tab bar ── */
  const TAB_LABELS = { skillset: "Skill Set" };
  const tabs = [
    "overview", "requirements", "candidates", "pipeline", "interviews",
    ...(canSeeSkillSet ? ["skillset"] : []),
  ];
  const TabBar = () => (
    <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:12 }}>
      <div style={{ display:"flex",gap:2,background:"#fff",border:`1px solid ${C.border}`,borderRadius:10,padding:4 }}>
        {tabs.map(t=>(
          <button key={t} onClick={()=>setActiveTab(t)} style={{ padding:"7px 18px",borderRadius:7,fontSize:12,fontWeight:600,cursor:"pointer",border:"none",fontFamily:"inherit",background:activeTab===t?C.navy:"transparent",color:activeTab===t?"#fff":C.ink3,transition:"all .15s" }}>
            {TAB_LABELS[t] || (t.charAt(0).toUpperCase()+t.slice(1))}
          </button>
        ))}
      </div>
      {activeTab==="candidates"    && <Btn variant="teal" onClick={openAddCandidate}>+ Add Candidate</Btn>}
      {activeTab==="requirements"  && <Btn variant="teal" onClick={openNewReq}>+ New Requirement</Btn>}
    </div>
  );

  /* ── OVERVIEW TAB ── */
  const OverviewTab = () => (
    <div style={{ display:"flex",flexDirection:"column",gap:20 }}>
      {/* Stats */}
      <div style={{ display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:14 }}>
        <StatCard loading={overviewLoading} icon="📋" value={stats.open_reqs}              label="Open Reqs"            trend="from DB" trendUp accentColor={C.blue}   iconBg={C.blueL}   iconColor={C.blue}   />
        <StatCard loading={overviewLoading} icon="👥" value={stats.total_candidates}       label="Total Candidates"    trend="from DB" trendUp accentColor={C.teal}   iconBg={C.tealL}   iconColor={C.teal}   />
        <StatCard loading={overviewLoading} icon="⏳" value={stats.pending_review}         label="Pending Review"       trend="awaiting" trendUp={false} accentColor={C.amber} iconBg={C.amberL} iconColor={C.amber} />
        <StatCard loading={overviewLoading} icon="🎥" value={stats.interviews_this_week}   label="Interviews This Week" trend="this week" trendUp accentColor={C.purple} iconBg={C.purpleL} iconColor={C.purple} />
        <StatCard loading={overviewLoading} icon="🏆" value={stats.offers_sent}            label="Offers Sent"         trend="from DB" trendUp accentColor={C.green}  iconBg={C.greenL}  iconColor={C.green}  />
      </div>

      {/* Active Interview Schedule */}
      <Card>
        <CardHeader title="Active Interview Schedule" action={<span style={{ fontSize:11,color:C.teal,fontWeight:600,cursor:"pointer" }} onClick={()=>setActiveTab("interviews")}>View all</span>} />
        {overviewLoading ? <LoadingRows rows={2} /> : activeInterviews.length===0 ? <EmptyState icon="🎥" msg="No active interviews scheduled." /> :
          activeInterviews.map(iv=>(
            <div key={iv.round_id} style={{ border:`1px solid ${C.border}`,borderRadius:10,padding:"12px 14px",margin:"0 16px 10px" }}>
              <div style={{ display:"flex",alignItems:"center",gap:10,marginBottom:9 }}>
                <Avt initials={initials(iv.candidate_name)} color={`linear-gradient(135deg,${avtColor(iv.candidate_name)},${avtColor(iv.candidate_name+"X")})`} size={32} />
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:12,fontWeight:700,color:C.ink }}>{iv.candidate_name}</div>
                  <div style={{ fontSize:10,color:C.ink3 }}>{iv.role}</div>
                </div>
                <Badge type={iv.round_type||"blue"}>{iv.round_name}</Badge>
              </div>
              <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:"6px 10px",marginBottom:9 }}>
                {[["Interviewer",iv.interviewer_name||"—"],["Date",iv.date_label||"TBD"],["Format",iv.interview_format||"—"],["Status",iv.status_label]].map(([lbl,val])=>(
                  <div key={lbl}><div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".06em",color:C.ink3 }}>{lbl}</div><div style={{ fontSize:11,fontWeight:600,color:lbl==="Status"?iv.status_color:C.ink }}>{val}</div></div>
                ))}
              </div>
              <div style={{ display:"flex",gap:6,borderTop:`1px solid ${C.surface}`,paddingTop:8 }}>
                <button style={{ flex:1,fontSize:10,fontWeight:600,padding:5,borderRadius:6,border:"none",cursor:"pointer",background:C.surface,color:C.ink2,fontFamily:"inherit" }} onClick={()=>openReschedule(iv.round_id,iv.candidate_name)}>Reschedule</button>
                <button style={{ flex:1,fontSize:10,fontWeight:600,padding:5,borderRadius:6,border:"none",cursor:"pointer",background:C.blueL,color:C.blue,fontFamily:"inherit" }} onClick={()=>toast(`Override applied for ${iv.candidate_name}`,"info")}>Override</button>
                <button style={{ flex:1,fontSize:10,fontWeight:600,padding:5,borderRadius:6,border:"none",cursor:"pointer",background:C.purpleL,color:C.purple,fontFamily:"inherit" }} onClick={()=>openDetail(iv.candidate_id)}>Details</button>
              </div>
            </div>
          ))
        }
      </Card>

      {/* Upcoming Interviews */}
      <Card>
        <CardHeader title="Upcoming Interviews" action={<span style={{ fontSize:11,color:C.teal,fontWeight:600,cursor:"pointer" }}>View all</span>} />
        {overviewLoading ? <LoadingRows rows={1} /> : upcomingInterviews.length===0 ? <EmptyState icon="📅" msg="No upcoming interviews." /> : (
          <div style={{ display:"grid",gridTemplateColumns:`repeat(${Math.min(upcomingInterviews.length,3)},1fr)` }}>
            {upcomingInterviews.slice(0,3).map((cal,i)=>{
              const calBg  = cal.pending?C.amberL:C.blueL;
              const dayClr = cal.pending?C.amber:C.blue;
              const monClr = cal.pending?"#fbbf24":"#93c5fd";
              return (
                <div key={cal.round_id} style={{ display:"flex",alignItems:"center",gap:12,padding:"12px 14px",borderRight:i<upcomingInterviews.length-1?`1px solid ${C.surface}`:"none" }}>
                  <div style={{ width:42,height:42,borderRadius:9,background:calBg,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
                    <div style={{ fontSize:17,fontWeight:700,color:dayClr,lineHeight:1 }}>{cal.day||"?"}</div>
                    <div style={{ fontSize:8,fontWeight:700,color:monClr,textTransform:"uppercase",letterSpacing:".04em" }}>{cal.month||""}</div>
                  </div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:12,fontWeight:600,color:C.ink }}>{cal.candidate_name}</div>
                    <div style={{ fontSize:10,color:C.ink3,marginTop:1 }}>{cal.sub}</div>
                    <div style={{ display:"flex",alignItems:"center",gap:8,marginTop:4 }}>
                      <span style={{ fontSize:10,color:C.ink3 }}>🕐 {cal.time_label}</span>
                      {cal.interviewer_name&&<span style={{ fontSize:10,color:C.ink3 }}>👤 {cal.interviewer_name}</span>}
                      {cal.pending?<span style={{ fontSize:10,color:C.amber,fontWeight:600 }}>Slot pending</span>:<span style={{ fontSize:9,fontWeight:700,background:C.purpleL,color:C.purple,padding:"2px 7px",borderRadius:4 }}>📹 {cal.interview_format||"Teams"}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );

  /* ── CANDIDATES TAB ── */
  const CandidatesTab = () => (
    <Card>
      <CardHeader title="All Candidates" badge={candidates.length||null} />
      {candidatesLoading?<LoadingRows rows={5}/>:candidates.length===0?<EmptyState icon="👥" msg="No candidates found."/>:(
        <div style={{ overflowX:"auto" }}>
          <table style={{ width:"100%",borderCollapse:"collapse" }}>
            <thead><tr>{["Candidate","Role Applied","Source","Experience","CTC Expected","Stage","Req","Actions"].map(h=>(
              <th key={h} style={{ padding:"10px 16px",textAlign:"left",fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,background:C.surface,whiteSpace:"nowrap" }}>{h}</th>
            ))}</tr></thead>
            <tbody>
              {candidates.map(row=>(
                <tr key={row.candidate_id} onClick={()=>openDetail(row.candidate_id)} style={{ cursor:"pointer" }}>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}>
                    <div style={{ display:"flex",alignItems:"center",gap:8 }}>
                      <Avt initials={initials(row.full_name)} color={avtColor(row.full_name)} />
                      <div>
                        <div style={{ fontWeight:600,color:C.ink,fontSize:12 }}>{row.full_name}</div>
                        <div style={{ fontSize:10,color:C.ink3 }}>{row.email}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.role||"—"}</td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}><Badge type={srcType(row.source)}>{row.source||"—"}</Badge></td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.exp||"—"}</td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.ctc||"—"}</td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}><Badge type={row.stage_type||"gray"}>{row.stage||"Sourced"}</Badge></td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.req_id||"—"}</td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }} onClick={e=>e.stopPropagation()}>
                    <div style={{ display:"flex",gap:6,alignItems:"center",flexWrap:"wrap" }}>
                      {row.is_selected
                        ? <Btn variant="teal" style={{ fontSize:10,padding:"5px 10px" }} onClick={()=>toast(`Onboarding initiated for ${row.full_name}`,"success")}>Initiate Onboarding</Btn>
                        : <span style={{ color:C.teal,fontSize:11,fontWeight:600,cursor:"pointer",display:"inline-flex",alignItems:"center",gap:3 }} onClick={()=>openDetail(row.candidate_id)}>View →</span>
                      }
                      {canOnboard && !row.onboarded_at && (
                        <Btn
                          variant="outline"
                          style={{ fontSize:10,padding:"5px 10px",color:"#7c3aed",border:`1px solid #7c3aed`,background:C.purpleL }}
                          onClick={() => openCloseAndOnboard(row.candidate_id, row.full_name)}
                        >
                          Close &amp; Onboard
                        </Btn>
                      )}
                      {row.onboarded_at && (
                        <span style={{ fontSize:10,fontWeight:700,color:C.green,padding:"3px 8px",borderRadius:6,background:C.greenL }}>Onboarded</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );

  /* ── REQUIREMENTS TAB ── */
  const RequirementsTab = () => {
    const [rfOpen, setRfOpen] = useState(false);
    const [rfSearch, setRfSearch] = useState('');
    const rfFiltered = recruiters.filter(r =>
      r.name.toLowerCase().includes(rfSearch.toLowerCase()) ||
      (r.employee_code||'').toLowerCase().includes(rfSearch.toLowerCase())
    );

    const STATUS_FILTERS = ["All","Active","In Review","Sourcing","Closed"];
    const filtered = reqStatusFilter === "All"
      ? requirements
      : requirements.filter(r => r.status === reqStatusFilter);

    return (
      <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
        {/* Filter bar: status pills + recruiter dropdown */}
        <div style={{ display:"flex",alignItems:"center",gap:10,flexWrap:"wrap" }}>
          <div style={{ display:"flex",gap:6,flexWrap:"wrap" }}>
            {STATUS_FILTERS.map(s => (
              <button key={s} onClick={() => setReqStatusFilter(s)}
                style={{ padding:"5px 14px",borderRadius:20,fontSize:11,fontWeight:600,cursor:"pointer",fontFamily:"inherit",border:`1.5px solid ${reqStatusFilter===s?C.teal:C.border}`,background:reqStatusFilter===s?C.tealL:"#fff",color:reqStatusFilter===s?C.teal:C.ink3,transition:"all .15s" }}>
                {s}
              </button>
            ))}
          </div>

          {/* Recruiter multi-select dropdown */}
          <div style={{ position:"relative" }}>
            <button onClick={() => setRfOpen(o => !o)}
              style={{ display:"flex",alignItems:"center",gap:6,padding:"5px 12px",borderRadius:20,fontSize:11,fontWeight:600,cursor:"pointer",fontFamily:"inherit",border:`1.5px solid ${recruiterFilter.length>0?C.purple:C.border}`,background:recruiterFilter.length>0?C.purpleL:"#fff",color:recruiterFilter.length>0?C.purple:C.ink3,transition:"all .15s" }}>
              {recruiterFilter.length > 0 ? `Recruiter: ${recruiterFilter.length} selected` : "All Recruiters"}
              <span style={{ fontSize:8 }}>▼</span>
            </button>
            {rfOpen && (
              <div style={{ position:"absolute",top:"calc(100% + 6px)",left:0,zIndex:200,background:"#fff",border:`1px solid ${C.border}`,borderRadius:10,boxShadow:"0 8px 24px rgba(0,0,0,0.12)",minWidth:230,maxHeight:280,overflow:"hidden",display:"flex",flexDirection:"column" }}>
                <div style={{ padding:"8px 10px",borderBottom:`1px solid ${C.surface}` }}>
                  <input value={rfSearch} onChange={e => setRfSearch(e.target.value)}
                    placeholder="Search recruiter…"
                    style={{ width:"100%",border:`1px solid ${C.border}`,borderRadius:6,padding:"5px 8px",fontSize:11,fontFamily:"inherit",outline:"none",boxSizing:"border-box" }} />
                </div>
                <div style={{ overflowY:"auto",flex:1 }}>
                  {rfFiltered.length === 0
                    ? <div style={{ padding:"12px",fontSize:11,color:C.ink3,textAlign:"center" }}>No recruiters found</div>
                    : rfFiltered.map(r => (
                      <label key={r.id} style={{ display:"flex",alignItems:"center",gap:8,padding:"8px 12px",cursor:"pointer",fontSize:11,color:C.ink2,borderBottom:`1px solid ${C.surface}` }}
                        onMouseEnter={e => e.currentTarget.style.background = C.surface}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <input type="checkbox" checked={recruiterFilter.includes(r.id)}
                          onChange={() => toggleRecruiterFilter(r.id)}
                          style={{ accentColor:C.purple,cursor:"pointer" }} />
                        <div>
                          <div style={{ fontWeight:600 }}>{r.name}</div>
                          {r.employee_code && <div style={{ fontSize:9,color:C.ink3 }}>{r.employee_code}</div>}
                        </div>
                      </label>
                    ))
                  }
                </div>
                {recruiterFilter.length > 0 && (
                  <div style={{ padding:"8px 12px",borderTop:`1px solid ${C.surface}` }}>
                    <button onClick={() => { clearRecruiterFilter(); setRfOpen(false); }}
                      style={{ width:"100%",fontSize:11,fontWeight:600,padding:"5px",borderRadius:6,border:"none",cursor:"pointer",background:C.redL,color:C.red,fontFamily:"inherit" }}>
                      Clear Filter
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Active filter indicators */}
          {recruiterFilter.length > 0 && (
            <div style={{ display:"flex",gap:4,flexWrap:"wrap" }}>
              {recruiterFilter.map(id => {
                const rec = recruiters.find(r => r.id === id);
                return rec ? (
                  <span key={id} style={{ display:"inline-flex",alignItems:"center",gap:4,padding:"3px 8px",borderRadius:20,fontSize:10,fontWeight:600,background:C.purpleL,color:C.purple }}>
                    {rec.name}
                    <button onClick={() => toggleRecruiterFilter(id)} style={{ border:"none",background:"transparent",color:C.purple,cursor:"pointer",padding:0,fontSize:11,lineHeight:1 }}>×</button>
                  </span>
                ) : null;
              })}
            </div>
          )}
        </div>

        <Card>
          <CardHeader title="Requirements" badge={filtered.length || null} />
          {requirementsLoading ? <LoadingRows rows={4} /> : filtered.length === 0 ? <EmptyState icon="📋" msg="No requirements found." /> : (
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%",borderCollapse:"collapse" }}>
                <thead>
                  <tr>{["Req ID","Job Title","Priority","Skills","Openings","Candidates","Assigned Recruiter","Status","Created","Actions"].map(h => (
                    <th key={h} style={{ padding:"10px 14px",textAlign:"left",fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,background:C.surface,whiteSpace:"nowrap" }}>{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {filtered.map(req => (
                    <tr key={req.req_id} style={{ cursor:"pointer" }}
                      onMouseEnter={e => e.currentTarget.style.background = C.surface}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}`,fontSize:11,fontWeight:700,color:C.teal,whiteSpace:"nowrap" }}
                        onClick={() => reqDetail_open(req)}>{req.req_id}</td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}` }}
                        onClick={() => reqDetail_open(req)}>
                        <div style={{ fontSize:12,fontWeight:600,color:C.ink }}>{req.title}</div>
                        <div style={{ fontSize:10,color:C.ink3,marginTop:2 }}>{req.department||"—"}{req.location ? ` · ${req.location}` : ""}</div>
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}` }}
                        onClick={() => reqDetail_open(req)}>
                        <Badge type={req.priority_type || priType(req.priority)}>{req.priority || "Normal"}</Badge>
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}` }}
                        onClick={() => reqDetail_open(req)}>
                        <div style={{ display:"flex",gap:4,flexWrap:"wrap" }}>
                          {(req.skills||[]).slice(0,3).map((s,i) => { const p=skillPalette(i); return <Skill key={s} bg={p.bg} color={p.color}>{s}</Skill>; })}
                          {req.skills?.length > 3 && <span style={{ fontSize:9,color:C.ink3,fontWeight:600 }}>+{req.skills.length-3}</span>}
                        </div>
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}`,fontSize:12,fontWeight:600,color:C.ink,textAlign:"center" }}
                        onClick={() => reqDetail_open(req)}>{req.openings ?? "—"}</td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}`,fontSize:12,color:C.ink2,textAlign:"center" }}
                        onClick={() => reqDetail_open(req)}>{req.candidate_count}</td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}`,fontSize:11,color:C.ink2 }}
                        onClick={() => reqDetail_open(req)}>
                        {req.assigned_recruiter_name
                          ? <div>
                              <div style={{ fontWeight:600 }}>{req.assigned_recruiter_name}</div>
                              {req.assigned_at && <div style={{ fontSize:9,color:C.ink3 }}>since {new Date(req.assigned_at).toLocaleDateString()}</div>}
                            </div>
                          : <span style={{ color:C.ink3 }}>—</span>}
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}` }}
                        onClick={() => reqDetail_open(req)}>
                        <Badge type={req.status==="Active"?"green":req.status==="Closed"?"red":req.status==="Sourcing"?"teal":"amber"}>{req.status}</Badge>
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}`,fontSize:11,color:C.ink3,whiteSpace:"nowrap" }}
                        onClick={() => reqDetail_open(req)}>
                        <div>{req.created_date || "—"}</div>
                        {req.created_by_name && <div style={{ fontSize:9,color:C.ink3 }}>by {req.created_by_name}</div>}
                      </td>
                      <td style={{ padding:"11px 14px",borderTop:`1px solid ${C.surface}` }} onClick={e => e.stopPropagation()}>
                        <div style={{ display:"flex",gap:5,flexWrap:"wrap" }}>
                          <button style={{ fontSize:10,fontWeight:600,padding:"4px 10px",borderRadius:6,border:"none",cursor:"pointer",background:C.blueL,color:C.blue,fontFamily:"inherit" }}
                            onClick={() => openEditReq(req)}>Edit</button>
                          {canAssign && req.status !== "Closed" && (
                            <button style={{ fontSize:10,fontWeight:600,padding:"4px 10px",borderRadius:6,border:"none",cursor:"pointer",background:C.purpleL,color:C.purple,fontFamily:"inherit" }}
                              onClick={(e) => openAssignRecruiter(req, e)}>
                              {req.assigned_recruiter_name ? "Reassign" : "Assign"}
                            </button>
                          )}
                          {req.status !== "Closed" && (
                            <button style={{ fontSize:10,fontWeight:600,padding:"4px 10px",borderRadius:6,border:"none",cursor:closingReqId===req.req_id?"not-allowed":"pointer",background:C.redL,color:C.red,fontFamily:"inherit",opacity:closingReqId===req.req_id?0.6:1 }}
                              onClick={() => handleCloseReq(req.req_id)}
                              disabled={closingReqId===req.req_id}>
                              {closingReqId===req.req_id ? "…" : "Close"}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    );
  };

  /* ── PIPELINE TAB ── */
  const PipelineTab = () => {
    const stageColors = {
      "Shortlisted":{"color":C.green,"bg":"#f0fdf4"},"Manager Approval":{"color":C.amber,"bg":"#fefce8"},"Manager Review":{"color":C.amber,"bg":"#fefce8"},
      "Approved":{"color":C.blue,"bg":"#eff6ff"},"Technical Round":{"color":C.blue,"bg":"#eff6ff"},
      "HR Round":{"color":"#c026d3","bg":"#fdf4ff"},"Selected":{"color":C.green,"bg":C.greenL},
      "Onboarding":{"color":"#06b6d4","bg":"#ecfeff"},
    };
    const stageEntries = Object.entries(pipelineData);
    const pipelineReqs = requirements.map(r=>r.req_id);

    return (
      <Card>
        <CardHeader title="Recruitment Pipeline" action={
          <select style={{ border:`1px solid ${C.border}`,borderRadius:7,padding:"5px 10px",fontSize:12,fontFamily:"inherit",color:C.ink2,background:"#fff" }}
            value={pipelineReqFilter} onChange={e=>{ setPipelineReqFilter(e.target.value); loadPipeline(e.target.value); }}>
            <option value="All">All Requirements</option>
            {pipelineReqs.map(r=><option key={r}>{r}</option>)}
          </select>
        } />
        {pipelineLoading?<LoadingRows rows={4}/>:stageEntries.length===0?<EmptyState icon="🔄" msg="No candidates in pipeline."/>:(
          <div style={{ overflowX:"auto",padding:"16px 20px 20px" }}>
            <div style={{ display:"flex",gap:14,minWidth:"max-content" }}>
              {stageEntries.map(([stage,cards])=>{
                const sc = stageColors[stage]||{ color:C.teal,bg:"#f0fdf4" };
                return (
                  <div key={stage} style={{ width:190,flexShrink:0 }}>
                    <div style={{ borderRadius:8,padding:"8px 10px",marginBottom:10,background:sc.bg,display:"flex",alignItems:"center",justifyContent:"space-between" }}>
                      <span style={{ fontSize:10,fontWeight:700,letterSpacing:".04em",color:sc.color }}>{stage}</span>
                      <span style={{ fontSize:10,fontWeight:700,color:"#fff",padding:"1px 8px",borderRadius:20,background:sc.color }}>{cards.length}</span>
                    </div>
                    {cards.map(card=>(
                      <div key={card.pipeline_id} onClick={()=>openDetail(card.candidate_id)} style={{ background:"#fff",border:`1px solid ${stage==="Rejected"?C.red:C.border}`,borderRadius:10,padding:11,marginBottom:9,cursor:"pointer",position:"relative",overflow:"hidden" }}
                        onMouseEnter={e=>e.currentTarget.style.boxShadow="0 2px 10px rgba(0,0,0,0.07)"} onMouseLeave={e=>e.currentTarget.style.boxShadow="none"}>
                        <div style={{ position:"absolute",left:0,top:0,bottom:0,width:3,background:sc.color }} />
                        <div style={{ paddingLeft:6 }}>
                          <div style={{ fontSize:12,fontWeight:700,color:C.ink }}>{card.candidate_name}</div>
                          <div style={{ fontSize:10,color:C.ink3,marginBottom:8 }}>{card.role||"—"}</div>
                          {card.exp&&<div style={{ fontSize:10,color:C.ink3,marginBottom:3 }}>💼 {card.exp}</div>}
                          {card.company&&<div style={{ fontSize:10,color:C.ink3,marginBottom:3 }}>🏢 {card.company}</div>}
                          {card.ctc&&<div style={{ fontSize:10,color:C.ink3,marginBottom:3 }}>₹ {card.ctc}</div>}
                          {card.interview_date&&<div style={{ fontSize:10,color:C.ink3,marginBottom:3 }}>📅 {card.interview_date}</div>}
                          {card.interviewer&&<div style={{ fontSize:10,color:C.ink3,marginBottom:3 }}>👤 {card.interviewer}</div>}
                          {card.is_special&&<Badge type="green">Offer Sent</Badge>}
                          {(card.skills||[]).length>0&&<div style={{ display:"flex",gap:4,flexWrap:"wrap",marginTop:7 }}>{card.skills.slice(0,3).map((s,i)=>{ const p=skillPalette(i); return <Skill key={s} bg={p.bg} color={p.color}>{s}</Skill>; })}</div>}
                          {card.rejection_reason&&(
                            <div style={{ marginTop:8,padding:"7px 9px",background:C.redL,borderRadius:6,border:`1px solid #fca5a5` }}>
                              <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".06em",color:C.red,marginBottom:3 }}>Manager Rejection Remarks</div>
                              <div style={{ fontSize:10,color:"#7f1d1d",lineHeight:1.5,fontStyle:"italic" }}>"{card.rejection_reason}"</div>
                              {card.rejected_by&&<div style={{ fontSize:9,color:C.ink3,marginTop:3 }}>By: {card.rejected_by}{card.rejected_at&&` · ${card.rejected_at}`}</div>}
                            </div>
                          )}
                        </div>
                        <div style={{ display:"flex",gap:5,marginTop:9,borderTop:`1px solid ${C.surface}`,paddingTop:8 }} onClick={e=>e.stopPropagation()}>
                          <button style={{ flex:1,fontSize:10,fontWeight:600,padding:5,borderRadius:6,border:"none",cursor:"pointer",background:C.tealL,color:"#134e4a",fontFamily:"inherit" }} onClick={()=>openDetail(card.candidate_id)}>View</button>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>
    );
  };

  /* ── INTERVIEWS TAB ── */
  const InterviewsTab = () => (
    <Card>
      <CardHeader title="All Interviews" action={
        <select style={{ border:`1px solid ${C.border}`,borderRadius:7,padding:"5px 10px",fontSize:12,fontFamily:"inherit",color:C.ink2,background:"#fff" }}>
          <option>All Rounds</option><option>Technical Round</option><option>HR Round</option><option>System Design</option>
        </select>
      } />
      {interviewsLoading?<LoadingRows rows={4}/>:interviews.length===0?<EmptyState icon="📅" msg="No interviews found."/>:(
        <div style={{ overflowX:"auto" }}>
          <table style={{ width:"100%",borderCollapse:"collapse" }}>
            <thead><tr>{["Candidate","Role","Round","Interviewer","Date & Time","Format","Status","Actions"].map(h=>(
              <th key={h} style={{ padding:"10px 16px",textAlign:"left",fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,background:C.surface,whiteSpace:"nowrap" }}>{h}</th>
            ))}</tr></thead>
            <tbody>
              {interviews.map(row=>(
                <tr key={row.round_id}>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}>
                    <div style={{ display:"flex",alignItems:"center",gap:8 }}>
                      <Avt initials={initials(row.candidate_name)} color={avtColor(row.candidate_name)} />
                      <span style={{ fontWeight:600,fontSize:12,color:C.ink }}>{row.candidate_name}</span>
                    </div>
                  </td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.role||"—"}</td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}><Badge type={row.status_type||"gray"}>{row.round_name}</Badge></td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}` }}>{row.interviewer_name||"—"}</td>
                  <td style={{ padding:"12px 16px",fontSize:12,color:C.ink2,borderTop:`1px solid ${C.surface}`,whiteSpace:"nowrap" }}>{row.interview_date||"TBD"}</td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}>
                    <span style={{ fontSize:9,fontWeight:700,background:(row.interview_format||"").toLowerCase().includes("person")?C.greenL:C.purpleL,color:(row.interview_format||"").toLowerCase().includes("person")?C.green:C.purple,padding:"2px 7px",borderRadius:4 }}>
                      {(row.interview_format||"").toLowerCase().includes("person")?"👥 In-person":"📹 "+(row.interview_format||"Teams")}
                    </span>
                  </td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}><Badge type={row.status_type||"gray"}>{row.status}</Badge></td>
                  <td style={{ padding:"12px 16px",borderTop:`1px solid ${C.surface}` }}>
                    <div style={{ display:"flex",gap:5 }}>
                      {(row.actions||[]).includes("Reschedule")&&<button style={{ fontSize:10,fontWeight:600,padding:"5px 11px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:"inherit",background:C.surface,color:C.ink2 }} onClick={()=>openReschedule(row.round_id,row.candidate_name)}>Reschedule</button>}
                      {(row.actions||[]).includes("Feedback")&&<button style={{ fontSize:10,fontWeight:600,padding:"5px 11px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:"inherit",background:C.purpleL,color:C.purple }} onClick={()=>openFeedback(row.candidate_id,row.candidate_name)}>Feedback</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );

  const fg = { display:"flex",flexDirection:"column",gap:5 };
  const inp = { border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 12px",fontSize:12,fontFamily:"inherit",color:C.ink,outline:"none",width:"100%",background:"#fff",boxSizing:"border-box" };
  const lbl = { fontSize:11,fontWeight:600,color:C.ink2 };
  const upAdd = k => e => setAddForm(f=>({...f,[k]:e.target.value}));

  

  /* ── RESCHEDULE MODAL ── */
  const RescheduleModal = () => (
    <Modal open={modal==="reschedule"} onClose={()=>setModal(null)} title={`Reschedule Interview${rescheduleFor?" — "+rescheduleFor:""}`} width={480}
      footer={<><Btn variant="outline" onClick={()=>setModal(null)}>Cancel</Btn><Btn variant="teal" onClick={confirmReschedule} disabled={rescheduleSubmitting}>{rescheduleSubmitting?"Saving…":"Confirm Reschedule"}</Btn></>}>
      <div style={{ background:C.amberL,border:"1px solid #fcd34d",borderRadius:8,padding:"12px 14px",marginBottom:18,fontSize:12,color:"#78350f",display:"flex",gap:8,alignItems:"center" }}>
        ⚠ Rescheduling will update the HRMS calendar, Teams calendar, and send email notifications.
      </div>
      <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
        <div style={fg}><label style={lbl}>New Interview Date *</label><input type="date" style={inp} value={rescheduleForm.new_date} onChange={e=>setRescheduleForm(f=>({...f,new_date:e.target.value}))} /></div>
        <div style={fg}><label style={lbl}>New Time *</label><input type="time" style={inp} value={rescheduleForm.new_time} onChange={e=>setRescheduleForm(f=>({...f,new_time:e.target.value}))} /></div>
        <div style={fg}><label style={lbl}>Interviewer</label>
          <select style={inp} value={rescheduleForm.interviewer_code} onChange={e=>setRescheduleForm(f=>({...f,interviewer_code:e.target.value}))}>
            <option value="">Select interviewer…</option>
            {interviewers.map(iv=><option key={iv.employee_code} value={iv.employee_code}>{iv.full_name}{iv.designation?" · "+iv.designation:""}</option>)}
          </select>
        </div>
        <div style={fg}><label style={lbl}>Interview Format</label>
          <select style={inp} value={rescheduleForm.interview_format} onChange={e=>setRescheduleForm(f=>({...f,interview_format:e.target.value}))}>
            <option>Microsoft Teams</option><option>In-Person</option><option>Google Meet</option><option>Phone Screen</option>
          </select>
        </div>
        <div style={fg}><label style={lbl}>Reason for Reschedule</label><textarea style={{ ...inp,resize:"vertical",minHeight:80 }} placeholder="Optional: reason for rescheduling…" value={rescheduleForm.reason} onChange={e=>setRescheduleForm(f=>({...f,reason:e.target.value}))} /></div>
      </div>
    </Modal>
  );

  /* ── SCHEDULE INTERVIEW MODAL (Bug 2) — no date/time/reason/warning banner ── */
  const ScheduleInterviewModal = () => (
    <Modal open={modal==="scheduleInterview"} onClose={()=>setModal(null)} title="Schedule Interview" width={480}
      footer={<><Btn variant="outline" onClick={()=>setModal(null)}>Cancel</Btn><Btn variant="teal" onClick={confirmScheduleInterview} disabled={scheduleIvSubmitting}>{scheduleIvSubmitting?"Saving…":"Assign Interviewer"}</Btn></>}>
      {detailData&&<div style={{ background:C.tealL,border:`1px solid ${C.teal}`,borderRadius:8,padding:"10px 14px",marginBottom:18,fontSize:12,color:"#134e4a",fontWeight:600 }}>
        Scheduling interview for: {detailData.full_name}
      </div>}
      <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
        <div style={fg}><label style={lbl}>Round Name</label>
          <select style={inp} value={scheduleIvForm.round_name} onChange={e=>setScheduleIvForm(f=>({...f,round_name:e.target.value}))}>
            <option>Technical Round</option><option>HR Round</option><option>System Design Round</option><option>Machine Coding Round</option><option>Cultural Fit Round</option>
          </select>
        </div>
        <div style={fg}><label style={lbl}>Interview Type</label>
          <select style={inp} value={scheduleIvForm.round_type} onChange={e=>setScheduleIvForm(f=>({...f,round_type:e.target.value}))}>
            <option value="Technical">Technical</option><option value="HR">HR</option><option value="System Design">System Design</option><option value="Cultural Fit">Cultural Fit</option>
          </select>
        </div>
        <div style={fg}><label style={lbl}>Assign Interviewer *</label>
          <select style={inp} value={scheduleIvForm.interviewer_code} onChange={e=>setScheduleIvForm(f=>({...f,interviewer_code:e.target.value}))}>
            <option value="">Select interviewer…</option>
            {interviewers.map(iv=><option key={iv.employee_code} value={iv.employee_code}>{iv.full_name}{iv.designation?" · "+iv.designation:""}</option>)}
          </select>
        </div>
        <div style={fg}><label style={lbl}>Notes (optional)</label>
          <textarea style={{ ...inp,resize:"vertical",minHeight:72 }} placeholder="Any special instructions for the interviewer…" value={scheduleIvForm.notes} onChange={e=>setScheduleIvForm(f=>({...f,notes:e.target.value}))} />
        </div>
      </div>
    </Modal>
  );

  /* ── FEEDBACK MODAL ── */
  const FeedbackModal = () => (
    <Modal open={modal==="feedback"} onClose={()=>setModal(null)} title="Interview Feedback" width={500}
      footer={<><Btn variant="outline" onClick={()=>setModal(null)}>Cancel</Btn><Btn variant="teal" onClick={()=>{ setModal(null); if(rec==="approve") toast("Feedback submitted — candidate moved to next round","success"); else if(rec==="reject") toast("Feedback submitted — candidate rejected","error"); else toast("Feedback submitted successfully","success"); }}>Submit Feedback</Btn></>}>
      {feedbackCandidate&&<div style={{ fontSize:14,fontWeight:700,color:C.ink,marginBottom:18 }}>Candidate: {feedbackCandidate}</div>}
      <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
        <div><label style={{ ...lbl,display:"block",marginBottom:8 }}>Overall Score</label><div style={{ display:"flex",gap:6 }}>{[1,2,3,4,5].map(n=><span key={n} onClick={()=>setScore(n)} style={{ fontSize:22,cursor:"pointer",color:n<=score?C.amber:C.border }}>★</span>)}</div></div>
        <div style={fg}><label style={lbl}>Technical Skills</label><select style={inp}><option>Excellent</option><option>Good</option><option>Average</option><option>Below Average</option></select></div>
        <div style={fg}><label style={lbl}>Communication</label><select style={inp}><option>Excellent</option><option>Good</option><option>Average</option><option>Below Average</option></select></div>
        <div style={fg}><label style={lbl}>Cultural Fit</label><select style={inp}><option>Strong fit</option><option>Moderate fit</option><option>Not a fit</option></select></div>
        <div style={fg}><label style={lbl}>Detailed Feedback & Notes</label><textarea style={{ ...inp,resize:"vertical",minHeight:100 }} placeholder="Write your assessment…" /></div>
        <div><label style={{ ...lbl,display:"block",marginBottom:8 }}>Recommendation *</label>
          <div style={{ display:"flex",gap:10 }}>
            <button onClick={()=>setRec("approve")} style={{ flex:1,display:"flex",alignItems:"center",justifyContent:"center",gap:6,padding:"8px 16px",borderRadius:8,fontSize:12,fontWeight:600,cursor:"pointer",fontFamily:"inherit",background:C.greenL,color:C.green,border:`2px solid ${rec==="approve"?C.green:"transparent"}` }}>✓ Approve — Move to Next</button>
            <button onClick={()=>setRec("reject")}  style={{ flex:1,display:"flex",alignItems:"center",justifyContent:"center",gap:6,padding:"8px 16px",borderRadius:8,fontSize:12,fontWeight:600,cursor:"pointer",fontFamily:"inherit",background:C.redL,color:C.red,border:`2px solid ${rec==="reject"?C.red:"transparent"}` }}>✕ Reject</button>
          </div>
        </div>
      </div>
    </Modal>
  );

  /* ── REQUIREMENT DETAIL MODAL ── */
  const ReqDetailModal = () => {
    if (!reqDetail) return null;
    const r = reqDetail;
    const expRange = (r.min_experience != null || r.max_experience != null)
      ? `${r.min_experience ?? 0} – ${r.max_experience ?? "∞"} yrs`
      : "—";
    return (
      <Modal open={modal==="reqDetail"} onClose={()=>setModal(null)} title={`${r.title} · ${r.req_id}`} width={620}
        footer={<>
          <Btn variant="outline" onClick={()=>setModal(null)}>Close</Btn>
          {r.status !== "Closed" && (
            <Btn variant="ghost" style={{ color:C.red,border:`1px solid ${C.red}` }}
              onClick={() => handleCloseReq(r.req_id)}
              disabled={closingReqId===r.req_id}>
              {closingReqId===r.req_id ? "Closing…" : "Close Requirement"}
            </Btn>
          )}
          <Btn variant="teal" onClick={() => openEditReq(r)}>Edit</Btn>
        </>}>
        {/* Meta grid */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10,marginBottom:16 }}>
          {[
            ["Req ID",      r.req_id],
            ["Priority",    r.priority || "Normal"],
            ["Status",      r.status],
            ["Department",  r.department || "—"],
            ["Location",    r.location || "—"],
            ["Work Mode",   r.work_mode || "—"],
            ["Experience",  expRange],
            ["Openings",    r.openings ?? "—"],
            ["Candidates",  r.candidate_count ?? 0],
          ].map(([k,v]) => (
            <div key={k} style={{ background:C.surface,borderRadius:8,padding:"10px 12px" }}>
              <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:3 }}>{k}</div>
              <div style={{ fontSize:12,fontWeight:600,color:C.ink }}>{v}</div>
            </div>
          ))}
        </div>

        {/* Skills */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:8 }}>Required Skills</div>
          <div style={{ display:"flex",gap:6,flexWrap:"wrap" }}>
            {(r.skills||[]).length > 0
              ? (r.skills||[]).map((s,i) => { const p=skillPalette(i); return <Skill key={s} bg={p.bg} color={p.color}>{s}</Skill>; })
              : <span style={{ fontSize:11,color:C.ink3,fontStyle:"italic" }}>No skills specified.</span>
            }
          </div>
        </div>

        {/* Two-col info */}
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14 }}>
          {[
            ["Budget Range",       r.budget_range || "—"],
            ["Target Joining",     r.target_joining || "—"],
            ["Employment Type",    r.employment_type || "—"],
            ["Qualification",      r.qualification || r.preferred_qualification || "—"],
          ].map(([k,v]) => (
            <div key={k} style={{ background:C.surface,borderRadius:8,padding:"10px 12px" }}>
              <div style={{ fontSize:9,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:3 }}>{k}</div>
              <div style={{ fontSize:12,fontWeight:500,color:C.ink }}>{v}</div>
            </div>
          ))}
        </div>

        {/* Job Description */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:8 }}>Job Description</div>
          <div style={{ background:C.surface,borderRadius:8,padding:14,fontSize:12,color:C.ink2,lineHeight:1.8,maxHeight:220,overflowY:"auto",whiteSpace:"pre-wrap",wordBreak:"break-word" }}>
            {r.job_description?.trim()
              ? r.job_description
              : <span style={{ color:C.ink3,fontStyle:"italic" }}>No job description available.</span>
            }
          </div>
        </div>

        {/* Footer info */}
        <div style={{ fontSize:11,color:C.ink3,padding:"8px 12px",background:C.surface,borderRadius:8 }}>
          Created: {r.created_date || "—"}
          {r.created_by_name && ` · By ${r.created_by_name}`}
          {r.assigned_recruiter_name && ` · Assigned: ${r.assigned_recruiter_name}`}
        </div>
      </Modal>
    );
  };

  /* ── RENDER ── */
  return (
    <div style={{ display:"flex",flexDirection:"column",gap:20,fontFamily:"'DM Sans',system-ui,sans-serif" }}>
      {/* Page header */}
      <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:12 }}>
        <div>
          <h1 style={{ fontSize:18,fontWeight:700,color:C.ink,margin:0 }}>Recruitment</h1>
          <p style={{ fontSize:12,color:C.ink3,margin:"4px 0 0" }}>Manage candidates, requirements, pipeline and interviews</p>
        </div>
      </div>

      <TabBar />

      {activeTab==="overview"      && <OverviewTab />}
      {activeTab==="candidates"    && <CandidatesTab />}
      {activeTab==="requirements"  && <RequirementsTab />}
      {activeTab==="pipeline"      && <PipelineTab />}
      {activeTab==="interviews"    && <InterviewsTab />}
      {activeTab==="skillset" && canSeeSkillSet && <SkillApprovalPage />}

      {/* Modals */}
      <AddCandidateModal
        open={modal==="addCandidate"}
        onClose={()=>{setModal(null);setCandidateSource("");setDuplicateCandidate(null);}}
        onConfirm={confirmAddCandidate}
        addSubmitting={addSubmitting}
        addForm={addForm}
        upAdd={upAdd}
        candidateSource={candidateSource}
        setCandidateSource={setCandidateSource}
        addReqList={addReqList}
        addSkills={addSkills}
        setAddSkills={setAddSkills}
        addSkillInput={addSkillInput}
        setAddSkillInput={setAddSkillInput}
        resumeRef={resumeRef}
        coverRef={coverRef}
        idProofRef={idProofRef}
        othersRef={othersRef}
      />
      <DuplicateCandidateModal
        open={modal==="duplicateCandidate" && Boolean(duplicateCandidate)}
        duplicateCandidate={duplicateCandidate}
        onCancel={()=>{ setModal(null); setDuplicateCandidate(null); }}
        onViewExisting={()=>{
          const candidateId = duplicateCandidate?.matched_candidate_id || duplicateCandidate?.matched_candidate?.candidate_id;
          setModal(null);
          setDuplicateCandidate(null);
          if (candidateId) openDetail(candidateId);
        }}
      />
      <RescheduleModal />
      <ScheduleInterviewModal />
      <FeedbackModal />
      <ReqDetailModal />
      <NewRequirementModal
        open={reqModal}
        onClose={() => setReqModal(false)}
        onSuccess={onReqSuccess}
        editData={reqEditData}
        showToast={toast}
      />

      {/* Detail Panel */}
      {detailName && (
        <DetailPanel
          candidate={detailData}
          name={detailData?.full_name||"Loading…"}
          onClose={closeDetail}
          onReschedule={()=>{ closeDetail(); openReschedule(null, detailData?.full_name||""); }}
          onScheduleInterview={()=>{ setModal(null); openScheduleInterview(); }}
          onAddRound={openAddRound}
          extraRounds={extraRoundsMap[detailData?.candidate_id]||[]}
          loading={detailLoading}
          canOnboard={canOnboard}
          onCloseAndOnboard={()=>{ if(detailData) openCloseAndOnboard(detailData.candidate_id, detailData.full_name); }}
        />
      )}

      {/* Add Round modal */}
      <AddRoundModal
        open={addRoundModal}
        candidateName={roundCandidate}
        onClose={()=>{ setAddRoundModal(false); setRoundCandidate(null); setRoundPipelineId(null); }}
        onConfirm={handleAddRound}
        showToast={toast}
      />

      {/* ── Assign Recruiter modal ── */}
      <Modal
        open={modal === "assignRecruiter"}
        onClose={() => { if (!assignSubmitting) { setModal(null); setAssignTarget(null); setAssignRecruiterVal(''); } }}
        title="Assign Recruiter"
        width={420}
        footer={
          <>
            <Btn variant="ghost" onClick={() => { setModal(null); setAssignTarget(null); setAssignRecruiterVal(''); }} disabled={assignSubmitting}>Cancel</Btn>
            <Btn variant="primary" onClick={confirmAssignRecruiter} disabled={assignSubmitting || !assignRecruiterVal}>
              {assignSubmitting ? "Assigning…" : "Assign"}
            </Btn>
          </>
        }
      >
        <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
          {assignTarget && (
            <div style={{ padding:"10px 14px",background:C.surface,borderRadius:8 }}>
              <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:4 }}>Requirement</div>
              <div style={{ fontSize:12,fontWeight:700,color:C.teal }}>{assignTarget.req_id}</div>
              <div style={{ fontSize:12,color:C.ink,marginTop:2 }}>{assignTarget.title}</div>
            </div>
          )}
          {assignTarget?.assigned_recruiter_name && (
            <div style={{ padding:"8px 12px",background:C.amberL,borderRadius:6,fontSize:11,color:C.amber,border:`1px solid #fcd34d` }}>
              Currently assigned to <strong>{assignTarget.assigned_recruiter_name}</strong>. Selecting a new recruiter will reassign and notify them.
            </div>
          )}
          <div>
            <label style={{ display:"block",fontSize:11,fontWeight:600,color:C.ink2,marginBottom:6 }}>Select Recruiter *</label>
            <select value={assignRecruiterVal} onChange={e => setAssignRecruiterVal(e.target.value)}
              style={{ width:"100%",border:`1px solid ${C.border}`,borderRadius:8,padding:"8px 10px",fontSize:12,fontFamily:"inherit",color:C.ink,outline:"none",boxSizing:"border-box" }}>
              <option value="">— Select —</option>
              {recruiters.map(r => (
                <option key={r.id} value={r.id}>{r.name}{r.employee_code ? ` (${r.employee_code})` : ''}</option>
              ))}
            </select>
          </div>
          <div style={{ fontSize:10,color:C.ink3,lineHeight:1.6 }}>
            The selected recruiter will receive an in-app notification with the requirement details.
          </div>
        </div>
      </Modal>

      {/* ── Close & Onboard confirmation modal ── */}
      <Modal
        open={modal === "closeAndOnboard"}
        onClose={() => { if (!onboardSubmitting) { setModal(null); setOnboardTarget(null); } }}
        title="Start Onboarding"
        width={460}
        footer={
          <>
            <Btn variant="ghost" onClick={() => { setModal(null); setOnboardTarget(null); }} disabled={onboardSubmitting}>Cancel</Btn>
            <Btn variant="teal" onClick={confirmCloseAndOnboard} disabled={onboardSubmitting}>
              {onboardSubmitting ? "Processing…" : "Confirm"}
            </Btn>
          </>
        }
      >
        <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
          <div style={{ padding:"12px 14px",background:C.purpleL,border:`1px solid #c4b5fd`,borderRadius:8,fontSize:12,color:"#4c1d95",lineHeight:1.6 }}>
            This will close the recruitment process and move the candidate into onboarding.
          </div>
          {onboardTarget && (
            <div style={{ padding:"12px 14px",background:C.surface,borderRadius:8 }}>
              <div style={{ fontSize:10,fontWeight:700,textTransform:"uppercase",letterSpacing:".07em",color:C.ink3,marginBottom:6 }}>Candidate</div>
              <div style={{ fontSize:13,fontWeight:700,color:C.ink }}>{onboardTarget.full_name}</div>
            </div>
          )}
          <div style={{ fontSize:11,color:C.ink3,lineHeight:1.6 }}>
            The candidate will appear in the Onboarding module with status <strong>CREATED</strong>. The recruitment record will be marked as <strong>Onboarded</strong>. This action cannot be undone.
          </div>
        </div>
      </Modal>

      <ToastContainer toasts={toasts} />
    </div>
  );
}
