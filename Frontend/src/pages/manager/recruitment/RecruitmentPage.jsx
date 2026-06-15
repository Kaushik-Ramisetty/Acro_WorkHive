/**
 * RecruitmentPage.jsx — Manager Dashboard · Recruitment Module
 *
 * Design system: ManagerDashboard's C palette, Card/Btn/Badge/Av pattern,
 * DM Sans typography, inline styles — exactly matches existing HRMS style.
 *
 * Interview workflow:
 *   Default rounds:  Technical Round → HR Round
 *   Extra rounds:    Added dynamically by recruiter via "+ Add Additional Round"
 *   Pipeline stages: Shortlisted → Technical Round → [...dynamic] → HR Round
 *                    → Selected → Onboarding
 */

import { useState, useRef, useEffect, useMemo } from 'react';
import {
  Plus, Eye, Edit, X, Check, Download, Filter,
  ChevronDown, ChevronUp, Layers, Briefcase, UserPlus,
  AlertTriangle, ArrowRight, Clock, Star, Send,
} from '../../../components/lucideShim';
import {
  getDashboardStats, getRequirements, createRequirement,
  getPipeline, submitApproval,
  searchSkills as apiSearchSkills, getAllSkills, getDepartments,
  requestNewSkillGlobal,
} from '../../../services/recruitmentApi';

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  primary:    '#10B981', primaryDark:'#059669',
  accent:     '#F97316', blue:'#1D4ED8',
  purple:     '#8B5CF6', red:'#EF4444',
  yellow:     '#F59E0B', teal:'#06B6D4', pink:'#EC4899',
  bg:         '#F8FAFC', card:'#FFFFFF',
  border:     '#E2E8F0', text:'#0F172A',
  muted:      '#64748B', light:'#F1F5F9',
};

// ── Avatar colour pool ────────────────────────────────────────────────────────
const AV_POOL = ['#1D4ED8','#8B5CF6','#F97316','#10B981','#EF4444','#F59E0B','#EC4899','#06B6D4'];
function avtColor(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return AV_POOL[h % AV_POOL.length];
}

// ── Known stage colour map + dynamic fallback ────────────────────────────────
const KNOWN_STAGE_STYLES = {
  'Shortlisted':      { hdr:'#F0FDF4', accent:'#10B981', text:'#065F46' },
  'Technical Round':  { hdr:'#F5F3FF', accent:'#8B5CF6', text:'#4C1D95' },
  'HR Round':         { hdr:'#FDF4FF', accent:'#C026D3', text:'#701A75' },
  'Selected':         { hdr:'#ECFDF5', accent:'#10B981', text:'#064E3B' },
  'Onboarding':       { hdr:'#ECFEFF', accent:'#06B6D4', text:'#164E63' },
};

const EXTRA_ROUND_PALETTE = [
  { hdr:'#EFF6FF', accent:'#1D4ED8', text:'#1E3A8A' },
  { hdr:'#FFF7ED', accent:'#EA580C', text:'#7C2D12' },
  { hdr:'#F0FDF4', accent:'#16A34A', text:'#14532D' },
  { hdr:'#FFF1F2', accent:'#E11D48', text:'#881337' },
  { hdr:'#FAFAF9', accent:'#78716C', text:'#292524' },
];

function getStageStyle(stageName, extraRounds = []) {
  if (KNOWN_STAGE_STYLES[stageName]) return KNOWN_STAGE_STYLES[stageName];
  const idx = extraRounds.findIndex(r => r.name === stageName);
  return EXTRA_ROUND_PALETTE[idx >= 0 ? idx % EXTRA_ROUND_PALETTE.length : 0];
}

const IV_STATUS_CFG = {
  scheduled:   { bg:'#DBEAFE', color:'#1E40AF', dot:'#1D4ED8', label:'Scheduled'    },
  in_progress: { bg:'#FEF3C7', color:'#92400E', dot:'#F59E0B', label:'In Progress'  },
  completed:   { bg:'#D1FAE5', color:'#065F46', dot:'#10B981', label:'Completed'    },
  pending:     { bg:'#F1F5F9', color:'#475569', dot:'#94A3B8', label:'Pending'      },
};
function ivStatusBadge(status) {
  const s = status?.toLowerCase().replace(' ', '_') || 'pending';
  const cfg = IV_STATUS_CFG[s] || IV_STATUS_CFG.pending;
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:4, background:cfg.bg, color:cfg.color, fontSize:10, fontWeight:700, padding:'2px 9px', borderRadius:12 }}>
      <span style={{ width:5, height:5, borderRadius:'50%', background:cfg.dot }} />
      {cfg.label}
    </span>
  );
}

// ── Micro-components ──────────────────────────────────────────────────────────
function Av({ name, size = 36 }) {
  const init = (name||'U').split(' ').filter(Boolean).map(s=>s[0]).slice(0,2).join('').toUpperCase();
  return (
    <div style={{ width:size, height:size, borderRadius:'50%', background:avtColor(name||'X'), display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:size*0.34, flexShrink:0 }}>{init}</div>
  );
}

function Card({ children, style={}, hover=false }) {
  const [over, setOver] = useState(false);
  return (
    <div onMouseEnter={()=>hover&&setOver(true)} onMouseLeave={()=>hover&&setOver(false)}
      style={{ background:C.card, borderRadius:12, border:`1px solid ${C.border}`, padding:20, transition:'box-shadow 0.15s', boxShadow:over?'0 4px 18px rgba(0,0,0,0.07)':'0 1px 4px rgba(0,0,0,0.04)', ...style }}
    >{children}</div>
  );
}

function Btn({ children, onClick, variant='primary', size='md', disabled=false, style={} }) {
  const [over, setOver] = useState(false);
  const base = { border:'none', borderRadius:8, cursor:disabled?'not-allowed':'pointer', fontWeight:600, fontFamily:"'DM Sans',sans-serif", transition:'all 0.15s', display:'inline-flex', alignItems:'center', justifyContent:'center', gap:6, opacity:disabled?0.55:1 };
  const pad = size==='sm'?'6px 14px':size==='xs'?'4px 10px':'9px 20px';
  const fs  = size==='sm'?12:size==='xs'?11:14;
  const v = {
    primary: { background:over?C.primaryDark:C.primary, color:'#fff', padding:pad, fontSize:fs },
    outline: { background:'transparent', color:C.primary, border:`1.5px solid ${C.primary}`, padding:pad, fontSize:fs },
    danger:  { background:over?'#FEE2E2':'#FFF5F5', color:C.red, border:`1px solid #FECACA`, padding:pad, fontSize:fs },
    ghost:   { background:over?C.light:'transparent', color:C.muted, padding:pad, fontSize:fs },
    teal:    { background:over?'#0891B2':C.teal, color:'#fff', padding:pad, fontSize:fs },
  };
  return (
    <button style={{ ...base, ...(v[variant]||v.primary), ...style }}
      onClick={disabled?undefined:onClick}
      onMouseEnter={()=>setOver(true)} onMouseLeave={()=>setOver(false)}
      disabled={disabled}
    >{children}</button>
  );
}

function Badge({ children, variant='green' }) {
  const map = {
    green:{bg:'#D1FAE5',color:'#065F46'}, blue:{bg:'#DBEAFE',color:'#1E40AF'},
    red:{bg:'#FEE2E2',color:'#991B1B'},   amber:{bg:'#FEF3C7',color:'#92400E'},
    purple:{bg:'#EDE9FE',color:'#5B21B6'},gray:{bg:C.light,color:C.muted},
    teal:{bg:'#CFFAFE',color:'#164E63'},  orange:{bg:'#FFEDD5',color:'#9A3412'},
  };
  const s = map[variant]||map.gray;
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:5, padding:'3px 10px', borderRadius:20, background:s.bg, color:s.color, fontSize:11, fontWeight:700 }}>
      <span style={{ width:5, height:5, borderRadius:'50%', background:s.color, flexShrink:0 }} />{children}
    </span>
  );
}

function SkillChip({ label, onRemove, pending=false }) {
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:5, background:pending?'#FEF3C7':'#ECFDF5', color:pending?'#92400E':'#065F46', border:`1px solid ${pending?'#FCD34D':'#A7F3D0'}`, borderRadius:6, padding:'3px 10px', fontSize:12, fontWeight:600, whiteSpace:'nowrap' }}>
      {pending && <AlertTriangle size={10} color="#D97706" />}
      {label}
      {onRemove && <button onClick={onRemove} style={{ border:'none', background:'none', cursor:'pointer', padding:0, display:'flex', lineHeight:1 }}><X size={10} color={pending?'#D97706':'#059669'} /></button>}
    </span>
  );
}

function Toast({ message, type='success', onDone }) {
  useEffect(() => { const t = setTimeout(onDone, 3200); return ()=>clearTimeout(t); }, [onDone]);
  const cfg = {
    success:{ bg:'#ECFDF5', border:'#A7F3D0', color:'#065F46', icon:<Check size={14} color="#059669"/> },
    error:  { bg:'#FEF2F2', border:'#FECACA', color:'#991B1B', icon:<X size={14} color="#EF4444"/> },
    info:   { bg:'#EFF6FF', border:'#BFDBFE', color:'#1E40AF', icon:<AlertTriangle size={14} color="#3B82F6"/> },
  };
  const s = cfg[type]||cfg.success;
  return (
    <div style={{ position:'fixed', bottom:28, right:28, zIndex:9999, display:'flex', alignItems:'center', gap:10, background:s.bg, border:`1px solid ${s.border}`, color:s.color, padding:'12px 20px', borderRadius:10, fontSize:13, fontWeight:600, boxShadow:'0 4px 20px rgba(0,0,0,0.10)', maxWidth:380, animation:'fadeInUp 0.2s ease' }}>
      {s.icon}{message}
      <button onClick={onDone} style={{ marginLeft:8, border:'none', background:'none', cursor:'pointer', display:'flex' }}><X size={14} color={s.color} /></button>
    </div>
  );
}

function LabeledField({ label, required, children }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
      <label style={{ fontSize:12, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4 }}>
        {label}{required && <span style={{ color:C.red }}> *</span>}
      </label>
      {children}
    </div>
  );
}

const iStyle = { width:'100%', padding:'9px 13px', border:`1px solid ${C.border}`, borderRadius:8, fontSize:13, color:C.text, outline:'none', fontFamily:"'DM Sans',sans-serif", background:'#fff', boxSizing:'border-box' };
const selectStyle = { ...iStyle, cursor:'pointer' };

function priorityBadge(p) {
  if (p==='Urgent') return <Badge variant="red">+ Urgent</Badge>;
  if (p==='High')   return <Badge variant="orange">+ High</Badge>;
  if (p==='Medium') return <Badge variant="amber">~ Medium</Badge>;
  return <Badge variant="gray">– Normal</Badge>;
}
function statusBadge(s) {
  const m = { Active:'green','In Review':'blue', Sourcing:'amber', Closed:'gray' };
  return <Badge variant={m[s]||'gray'}>{s}</Badge>;
}

// ── Skills multi-select ───────────────────────────────────────────────────────
function SkillsInput({ value, onChange, pendingSkills, onAddPending, showToast }) {
  const [query, setQuery]         = useState('');
  const [showDrop, setShowDrop]   = useState(false);
  const [requesting, setRequesting] = useState(false);
  const ref = useRef();

  const [allSkills, setAllSkills]       = useState([]);
  const [suggestions, setSuggestions]   = useState([]);
  const [masterLoaded, setMasterLoaded] = useState(false);

  useEffect(() => {
    getAllSkills()
      .then(res => { setAllSkills((res || []).map(r => r.name)); setMasterLoaded(true); })
      .catch(() => setMasterLoaded(true));
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setSuggestions([]); return; }
    const timer = setTimeout(() => {
      apiSearchSkills(q, 15)
        .then(res => {
          const names = (res.results || []).map(r => r.name);
          setSuggestions(names.filter(s => !value.includes(s) && !pendingSkills.includes(s)));
        })
        .catch(() => setSuggestions([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [query, value, pendingSkills]);

  const displayList = query.trim().length >= 2
    ? suggestions
    : allSkills.filter(s => !value.includes(s) && !pendingSkills.includes(s));

  const exactMatch   = allSkills.some(s => s.toLowerCase() === query.trim().toLowerCase())
                    || suggestions.some(s => s.toLowerCase() === query.trim().toLowerCase());
  const showNewSkill = query.trim().length > 1 && !exactMatch
                    && !value.includes(query.trim()) && !pendingSkills.includes(query.trim());

  const add = (skill) => { onChange([...value, skill]); setQuery(''); setShowDrop(false); };

  const requestNew = async () => {
    const skillName = query.trim();
    setRequesting(true);
    try {
      await requestNewSkillGlobal(skillName);
      onAddPending(skillName);
      setQuery('');
      setShowDrop(false);
      if (showToast) showToast(`"${skillName}" sent for HR Admin approval`, 'info');
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Request failed';
      if (showToast) showToast(msg, 'error');
    } finally {
      setRequesting(false);
    }
  };

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowDrop(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div ref={ref} style={{ position:'relative' }}>
      <div
        style={{ border:`1px solid ${C.border}`, borderRadius:8, padding:'8px 10px', background:'#fff',
                 display:'flex', flexWrap:'wrap', gap:6, minHeight:46, cursor:'text' }}
        onClick={() => setShowDrop(true)}
      >
        {value.map(s => <SkillChip key={s} label={s} onRemove={() => onChange(value.filter(x => x !== s))} />)}
        {pendingSkills.map(s => <SkillChip key={s} label={s} pending onRemove={() => onAddPending(null, s)} />)}
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setShowDrop(true); }}
          onFocus={() => setShowDrop(true)}
          placeholder={value.length === 0 && pendingSkills.length === 0 ? 'Search or select skills…' : ''}
          style={{ border:'none', outline:'none', fontSize:12, background:'transparent',
                   fontFamily:"'DM Sans',sans-serif", minWidth:120, flex:1, color:C.text }}
        />
      </div>

      {showDrop && (displayList.length > 0 || showNewSkill) && (
        <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:200, background:'#fff',
                      border:`1px solid ${C.border}`, borderRadius:8,
                      boxShadow:'0 4px 16px rgba(0,0,0,0.10)', maxHeight:240, overflowY:'auto', marginTop:4 }}>
          {displayList.length === 0 && !showNewSkill && (
            <div style={{ padding:'10px 14px', fontSize:12, color:C.muted }}>
              {masterLoaded ? 'No skills found' : 'Loading skills…'}
            </div>
          )}
          {displayList.map(s => (
            <div key={s} onMouseDown={() => add(s)}
              style={{ padding:'9px 14px', fontSize:13, cursor:'pointer', color:C.text }}
              onMouseEnter={e => e.currentTarget.style.background = C.light}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              {s}
            </div>
          ))}
          {showNewSkill && (
            <div
              onMouseDown={requesting ? undefined : requestNew}
              style={{ padding:'9px 14px', fontSize:13, cursor: requesting ? 'wait' : 'pointer',
                       color: C.accent, fontWeight:600, borderTop:`1px solid ${C.border}`,
                       display:'flex', alignItems:'center', gap:6, opacity: requesting ? 0.6 : 1 }}
              onMouseEnter={e => e.currentTarget.style.background = '#FFF7ED'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <Plus size={13} color={C.accent} />
              {requesting ? 'Sending request…' : `Request new skill: "${query.trim()}"`}
            </div>
          )}
        </div>
      )}

      {pendingSkills.length > 0 && (
        <div style={{ fontSize:11, color:C.yellow, marginTop:5, fontWeight:500 }}>
          ⏳ Pending HR Admin approval: {pendingSkills.join(', ')}
        </div>
      )}
    </div>
  );
}

// ── New Requirement Drawer ─────────────────────────────────────────────────────
function NewRequirementDrawer({ open, onClose, onSave, showToast }) {
  const empty = { title:'', department:'', employmentType:'', workMode:'', location:'', minExp:'', maxExp:'', openings:'', priority:'High', skills:[], pendingSkills:[], jd:'', preferredQualification:'', targetJoining:'', budgetRange:'' };
  const [form, setForm] = useState(empty);
  const up = k => v => setForm(f => ({ ...f, [k]: v }));

  const [departments, setDepartments] = useState([]);
  useEffect(() => {
    if (!open) return;
    getDepartments()
      .then(data => setDepartments(data || []))
      .catch(() => setDepartments([]));
  }, [open]);

  const addPending = (skill, removeSkill) => {
    if (removeSkill) { setForm(f => ({ ...f, pendingSkills: f.pendingSkills.filter(s => s !== removeSkill) })); }
    else if (skill)  { setForm(f => ({ ...f, pendingSkills: [...f.pendingSkills, skill] })); }
  };

  const handleSave = () => {
    if (!form.title || !form.department || !form.skills.length) { showToast('Please fill in all required fields', 'error'); return; }
    onSave(form); setForm(empty); onClose(); showToast('Requirement created successfully!', 'success');
  };

  if (!open) return null;
  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.45)', zIndex:400, backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', right:0, top:0, bottom:0, width:560, background:'#fff', zIndex:401, display:'flex', flexDirection:'column', boxShadow:'-8px 0 40px rgba(0,0,0,0.12)', overflowY:'auto' }}>
        <div style={{ padding:'20px 24px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between', position:'sticky', top:0, background:'#fff', zIndex:5 }}>
          <div><div style={{ fontWeight:700, fontSize:16, color:C.text }}>New Requirement</div><div style={{ fontSize:12, color:C.muted, marginTop:2 }}>Fill in the details to raise a hiring requirement</div></div>
          <button onClick={onClose} style={{ border:'none', background:C.light, borderRadius:8, width:34, height:34, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}><X size={16} color={C.muted} /></button>
        </div>
        <div style={{ padding:'24px 24px 100px', display:'flex', flexDirection:'column', gap:18 }}>
          <LabeledField label="Job Title" required><input style={iStyle} placeholder="e.g. Senior Frontend Engineer" value={form.title} onChange={e => up('title')(e.target.value)} /></LabeledField>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
            <LabeledField label="Department" required>
              <select style={selectStyle} value={form.department} onChange={e => up('department')(e.target.value)}>
                <option value="">Select…</option>
                {departments.length > 0
                  ? departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)
                  : <option disabled>Loading departments…</option>
                }
              </select>
            </LabeledField>
            <LabeledField label="Employment Type" required><select style={selectStyle} value={form.employmentType} onChange={e=>up('employmentType')(e.target.value)}><option value="">Select…</option><option>Full Time</option><option>Contract</option><option>Internship</option></select></LabeledField>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
            <LabeledField label="Work Mode" required><select style={selectStyle} value={form.workMode} onChange={e=>up('workMode')(e.target.value)}><option value="">Select…</option><option>Remote</option><option>Hybrid</option><option>Onsite</option></select></LabeledField>
            <LabeledField label="Location" required><input style={iStyle} placeholder="+Add location" value={form.location} onChange={e=>up('location')(e.target.value)} /></LabeledField>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14 }}>
            <LabeledField label="Min Experience" required><select style={selectStyle} value={form.minExp} onChange={e=>up('minExp')(e.target.value)}><option value="">Select Min</option>{[0,1,2,3,4,5,6,7,8,10].map(n=><option key={n}>{n}</option>)}</select></LabeledField>
            <LabeledField label="Max Experience" required><select style={selectStyle} value={form.maxExp} onChange={e=>up('maxExp')(e.target.value)}><option value="">Select Max</option>{[1,2,3,4,5,6,7,8,10,12,15].map(n=><option key={n}>{n}</option>)}</select></LabeledField>
            <LabeledField label="Openings" required><input type="number" min={1} style={iStyle} placeholder="e.g. 2" value={form.openings} onChange={e=>up('openings')(e.target.value)} /></LabeledField>
          </div>
          <LabeledField label="Priority">
            <div style={{ display:'flex', gap:8 }}>
              {['Low','Medium','High','Urgent'].map(p=>(
                <button key={p} onClick={()=>up('priority')(p)} style={{ flex:1, padding:'8px 0', borderRadius:8, fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:"'DM Sans',sans-serif", transition:'all 0.15s', background:form.priority===p?C.primary:C.light, color:form.priority===p?'#fff':C.muted, border:`1.5px solid ${form.priority===p?C.primary:C.border}` }}>{p}</button>
              ))}
            </div>
          </LabeledField>
          <LabeledField label="Skills" required>
            <SkillsInput value={form.skills} onChange={up('skills')} pendingSkills={form.pendingSkills} onAddPending={addPending} showToast={showToast} />
            <div style={{ marginTop:8 }}>
              <span style={{ fontSize:11, color:C.muted, fontWeight:600, marginRight:8 }}>Suggestion:</span>
              {['JavaScript','HTML','CSS','React.js','Node.js','RESTful','API','MySQL','Git','MongoDB','AWS','Agile','Testing','Linux','DevOps'].filter(s=>!form.skills.includes(s)).slice(0,8).map(s=>(
                <button key={s} onClick={()=>up('skills')([...form.skills,s])} style={{ display:'inline-flex', alignItems:'center', marginRight:6, marginBottom:4, padding:'3px 10px', border:`1px solid ${C.primary}`, borderRadius:14, background:'transparent', color:C.primary, fontSize:11, fontWeight:600, cursor:'pointer', fontFamily:"'DM Sans',sans-serif" }}>{s}</button>
              ))}
            </div>
          </LabeledField>
          <LabeledField label="Job Description" required>
            <textarea rows={5} style={{ ...iStyle, resize:'vertical', minHeight:100 }} placeholder="Describe the role and responsibilities…" value={form.jd} onChange={e=>up('jd')(e.target.value)} />
          </LabeledField>
          <LabeledField label="Preferred Qualifications"><input style={iStyle} placeholder="e.g. B.E. / M.Tech in Computer Science" value={form.preferredQualification} onChange={e=>up('preferredQualification')(e.target.value)} /></LabeledField>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
            <LabeledField label="Target Joining Timeline"><input type="date" style={iStyle} value={form.targetJoining} onChange={e=>up('targetJoining')(e.target.value)} /></LabeledField>
            <LabeledField label="Budget Range"><input style={iStyle} placeholder="e.g. ₹18L – ₹28L" value={form.budgetRange} onChange={e=>up('budgetRange')(e.target.value)} /></LabeledField>
          </div>
        </div>
        <div style={{ position:'sticky', bottom:0, background:'#fff', borderTop:`1px solid ${C.border}`, padding:'16px 24px', display:'flex', gap:10, justifyContent:'flex-end' }}>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="outline" onClick={()=>showToast('Draft saved','info')}>Save Draft</Btn>
          <Btn variant="primary" onClick={handleSave}><Check size={14}/> Submit Requirement</Btn>
        </div>
      </div>
    </>
  );
}

// ── Add Additional Round Modal ─────────────────────────────────────────────────
function AddRoundModal({ open, candidateName, onClose, onConfirm, showToast }) {
  const empty = { name:'', type:'', interviewer:'', date:'', time:'', reason:'' };
  const [form, setForm] = useState(empty);
  const up = k => e => setForm(f=>({...f,[k]:typeof e === 'string' ? e : e.target.value}));

  const ROUND_TYPES = ['Technical','System Design','Machine Coding','Client Discussion','Architecture','Managerial','Cultural Fit','Custom'];
  const INTERVIEWERS = ['Anil Joshi','Priya R.','Vikram K.','Neha P.','Samyaka L.','Ankit J.'];

  const handleConfirm = () => {
    if (!form.name || !form.type) { showToast('Round name and type are required','error'); return; }
    onConfirm({ ...form, id: `R-${Date.now()}` });
    setForm(empty);
    onClose();
  };

  if (!open) return null;
  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.5)', zIndex:600, backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#fff', borderRadius:14, width:520, maxWidth:'95vw', maxHeight:'90vh', overflowY:'auto', zIndex:601, boxShadow:'0 20px 60px rgba(0,0,0,0.18)' }}>
        <div style={{ padding:'20px 24px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontWeight:700, fontSize:16, color:C.text }}>Add Additional Round</div>
            {candidateName && <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>For: <strong>{candidateName}</strong></div>}
          </div>
          <button onClick={onClose} style={{ border:'none', background:C.light, borderRadius:8, width:32, height:32, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}><X size={15} color={C.muted} /></button>
        </div>
        <div style={{ padding:'22px 24px', display:'flex', flexDirection:'column', gap:16 }}>
          <LabeledField label="Round Name" required>
            <input style={iStyle} placeholder="e.g. System Design Round" value={form.name} onChange={up('name')} />
          </LabeledField>
          <LabeledField label="Round Type" required>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
              {ROUND_TYPES.map(t=>(
                <button key={t} onClick={()=>setForm(f=>({...f,type:t}))} style={{ padding:'6px 14px', borderRadius:8, fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:"'DM Sans',sans-serif", transition:'all 0.15s', background:form.type===t?C.primary:C.light, color:form.type===t?'#fff':C.muted, border:`1.5px solid ${form.type===t?C.primary:C.border}` }}>{t}</button>
              ))}
            </div>
          </LabeledField>
          <LabeledField label="Assign Interviewer">
            <select style={selectStyle} value={form.interviewer} onChange={up('interviewer')}>
              <option value="">Select interviewer…</option>
              {INTERVIEWERS.map(i=><option key={i}>{i}</option>)}
            </select>
          </LabeledField>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
            <LabeledField label="Schedule Date"><input type="date" style={iStyle} value={form.date} onChange={up('date')} /></LabeledField>
            <LabeledField label="Schedule Time"><input type="time" style={iStyle} value={form.time} onChange={up('time')} /></LabeledField>
          </div>
          <LabeledField label="Reason for Additional Round" required>
            <textarea rows={3} style={{ ...iStyle, resize:'vertical' }}
              placeholder="e.g. Manager recommends a system design evaluation before proceeding to HR…"
              value={form.reason} onChange={up('reason')}
            />
          </LabeledField>
        </div>
        <div style={{ padding:'16px 24px', borderTop:`1px solid ${C.border}`, display:'flex', gap:10, justifyContent:'flex-end' }}>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleConfirm} disabled={!form.name||!form.type}><Plus size={13}/> Add Round</Btn>
        </div>
      </div>
    </>
  );
}

// ── Rejection Reason Modal ─────────────────────────────────────────────────────
function RejectModal({ open, name, onClose, onConfirm }) {
  const [reason, setReason] = useState('');
  if (!open) return null;
  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.5)', zIndex:600 }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#fff', borderRadius:14, padding:28, width:420, zIndex:601, boxShadow:'0 20px 60px rgba(0,0,0,0.18)' }}>
        <div style={{ fontWeight:700, fontSize:16, color:C.text, marginBottom:6 }}>Reject Candidate</div>
        <div style={{ fontSize:13, color:C.muted, marginBottom:20 }}>Rejecting <strong>{name}</strong>. Please provide a reason for the recruiter.</div>
        <LabeledField label="Reason for Rejection" required>
          <textarea rows={4} style={{ ...iStyle, resize:'none' }} placeholder="e.g. Experience doesn't meet minimum requirement…" value={reason} onChange={e=>setReason(e.target.value)} />
        </LabeledField>
        <div style={{ display:'flex', gap:10, justifyContent:'flex-end', marginTop:20 }}>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="danger" onClick={()=>{onConfirm(reason);setReason('');}} disabled={!reason.trim()}><X size={13}/> Confirm Rejection</Btn>
        </div>
      </div>
    </>
  );
}

// ── Interview Timeline ─────────────────────────────────────────────────────────
function InterviewTimeline({ rounds = [], onAddRound, isRejected = false }) {
  const canAddRound = rounds.some(r => (r.feedback && r.feedback.trim()) || (r.managerRemark && r.managerRemark.trim()));
  const triggerRound = [...rounds].reverse().find(r => (r.feedback && r.feedback.trim()) || (r.managerRemark && r.managerRemark.trim()));

  return (
    <div style={{ marginBottom:20 }}>
      <div style={{ fontSize:12, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:14 }}>Interview Timeline</div>

      {rounds.length === 0 && (
        <div style={{ padding:'16px', background:C.light, borderRadius:8, fontSize:12, color:C.muted, textAlign:'center' }}>
          No interview rounds started yet.
        </div>
      )}

      <div style={{ position:'relative' }}>
        {rounds.length > 1 && (
          <div style={{ position:'absolute', left:13, top:14, bottom:14, width:1.5, background:`linear-gradient(to bottom, ${C.primary}40, ${C.border})`, zIndex:0 }} />
        )}

        {rounds.map((r, i) => {
          const isDone   = r.status === 'completed';
          const isActive = r.status === 'scheduled' || r.status === 'in_progress';
          const dotColor = isDone ? C.primary : isActive ? C.yellow : C.border;

          return (
            <div key={i} style={{ display:'flex', gap:14, marginBottom:i < rounds.length-1 ? 20 : 0, position:'relative', zIndex:1 }}>
              <div style={{ flexShrink:0, marginTop:2 }}>
                <div style={{ width:28, height:28, borderRadius:'50%', background:isDone?C.primary:isActive?'#FFF9C4':C.light, border:`2px solid ${dotColor}`, display:'flex', alignItems:'center', justifyContent:'center', boxShadow:isDone?`0 0 0 4px ${C.primary}20`:isActive?`0 0 0 4px ${C.yellow}20`:'none', transition:'all 0.2s' }}>
                  {isDone && <Check size={13} color="#fff" />}
                  {isActive && <Clock size={12} color={C.yellow} />}
                  {!isDone && !isActive && <span style={{ width:7, height:7, borderRadius:'50%', background:C.border, display:'block' }} />}
                </div>
              </div>

              <div style={{ flex:1, background:isDone?'#FAFFFE':isActive?'#FFFDF0':C.light, border:`1px solid ${isDone?'#A7F3D0':isActive?'#FCD34D':C.border}`, borderRadius:10, padding:'12px 14px' }}>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
                  <div>
                    <div style={{ fontWeight:700, fontSize:13, color:C.text }}>{r.name}</div>
                    <div style={{ fontSize:11, color:C.muted, marginTop:2, display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                      {r.interviewer && <span>👤 {r.interviewer}</span>}
                      {r.date       && <span>📅 {r.date}</span>}
                      {r.format     && <span>🎯 {r.format}</span>}
                    </div>
                  </div>
                  {ivStatusBadge(r.status)}
                </div>

                {r.feedback && r.feedback.trim() && (
                  <div style={{ marginTop:10, padding:'10px 12px', background:'#fff', borderRadius:8, border:`1px solid ${C.border}` }}>
                    <div style={{ fontSize:10, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:5 }}>Interviewer Feedback</div>
                    <div style={{ fontSize:12, color:C.text, lineHeight:1.6, fontStyle:'italic' }}>"{r.feedback}"</div>
                  </div>
                )}

                {r.managerRemark && r.managerRemark.trim() && (
                  <div style={{ marginTop:8, padding:'10px 12px', background:'#FFFBEB', borderRadius:8, border:'1px solid #FDE68A' }}>
                    <div style={{ fontSize:10, fontWeight:700, color:'#92400E', textTransform:'uppercase', letterSpacing:0.4, marginBottom:5 }}>Manager Remark</div>
                    <div style={{ fontSize:12, color:'#78350F', lineHeight:1.6 }}>"{r.managerRemark}"</div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {canAddRound && (
        <div style={{ marginTop:18 }}>
          {triggerRound && (
            <div style={{ display:'flex', alignItems:'flex-start', gap:8, padding:'10px 12px', background:'#FFFBEB', border:'1px solid #FDE68A', borderRadius:8, marginBottom:10 }}>
              <AlertTriangle size={14} color="#D97706" style={{ flexShrink:0, marginTop:1 }} />
              <div style={{ fontSize:12, color:'#78350F', lineHeight:1.5 }}>
                {triggerRound.managerRemark
                  ? <><strong>Manager requested:</strong> {triggerRound.managerRemark}</>
                  : <><strong>Interviewer recommended:</strong> further evaluation based on feedback from {triggerRound.name}.</>
                }
              </div>
            </div>
          )}
          <button
            onClick={onAddRound}
            style={{ display:'flex', alignItems:'center', gap:8, width:'100%', padding:'10px 14px', border:`1.5px dashed ${C.primary}`, borderRadius:10, background:'#F0FDF4', color:C.primary, fontSize:13, fontWeight:600, cursor:'pointer', fontFamily:"'DM Sans',sans-serif", justifyContent:'center', transition:'all 0.15s' }}
            onMouseEnter={e=>{ e.currentTarget.style.background='#D1FAE5'; e.currentTarget.style.borderStyle='solid'; }}
            onMouseLeave={e=>{ e.currentTarget.style.background='#F0FDF4'; e.currentTarget.style.borderStyle='dashed'; }}
          >
            <Plus size={15}/> Add Additional Round
          </button>
        </div>
      )}

      {!canAddRound && !isRejected && rounds.length > 0 && (
        <div style={{ marginTop:14, padding:'10px 14px', background:C.light, borderRadius:8, display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ width:6, height:6, borderRadius:'50%', background:C.border, flexShrink:0 }} />
          <span style={{ fontSize:11, color:C.muted }}>Additional rounds can be requested once interviewer feedback or a manager remark is recorded.</span>
        </div>
      )}
    </div>
  );
}

// ── Resume Preview Modal ──────────────────────────────────────────────────────
function ResumePreviewModal({ open, url, candidateName, onClose }) {
  if (!open) return null;
  const ext = (url || '').split('.').pop().split('?')[0].toLowerCase();
  const isPdf   = ext === 'pdf';
  const isImage = ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext);
  const isDoc   = ['doc', 'docx'].includes(ext);

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.65)', zIndex:700, backdropFilter:'blur(3px)' }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#fff', borderRadius:14, width:'85vw', maxWidth:920, height:'88vh', zIndex:701, display:'flex', flexDirection:'column', boxShadow:'0 24px 70px rgba(0,0,0,0.22)' }}>
        <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
          <div style={{ fontWeight:700, fontSize:14, color:C.text }}>📄 {candidateName} — Resume</div>
          <button onClick={onClose} style={{ border:'none', background:C.light, borderRadius:8, width:32, height:32, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}><X size={15} color={C.muted} /></button>
        </div>
        <div style={{ flex:1, overflow:'hidden', display:'flex', alignItems:'center', justifyContent:'center', background:'#F8FAFC' }}>
          {isPdf && <iframe src={url} title={`${candidateName} Resume`} style={{ width:'100%', height:'100%', border:'none' }} />}
          {isImage && <img src={url} alt={`${candidateName} Resume`} style={{ maxWidth:'100%', maxHeight:'100%', objectFit:'contain', padding:16 }} />}
          {isDoc && (
            <div style={{ textAlign:'center', padding:40, color:C.muted }}>
              <div style={{ fontSize:36, marginBottom:14 }}>📝</div>
              <div style={{ fontWeight:700, fontSize:14, color:C.text, marginBottom:8 }}>Word Document</div>
              <div style={{ fontSize:12, color:C.muted, marginBottom:20 }}>Word documents cannot be previewed inline.</div>
              <a href={`https://docs.google.com/viewer?url=${encodeURIComponent(url)}`} target="_blank" rel="noreferrer" style={{ textDecoration:'none' }}>
                <Btn variant="outline" size="sm">🔗 Open in Google Docs Viewer</Btn>
              </a>
            </div>
          )}
          {!isPdf && !isImage && !isDoc && url && (
            <div style={{ textAlign:'center', color:C.muted, fontSize:13, padding:40 }}>
              <div style={{ fontSize:36, marginBottom:14 }}>📁</div>
              <div style={{ fontWeight:600, marginBottom:8 }}>Preview not available for this file type</div>
              <div>Please use Download Resume to access the file.</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Resume Drawer ──────────────────────────────────────────────────────────────
function ResumeDrawer({ candidate, open, onClose, onApprove, onReject, onAddRound, extraRounds }) {
  const [resumePreviewOpen, setResumePreviewOpen] = useState(false);
  if (!open || !candidate) return null;

  const stageOrder = ['Sourced','Manager Approval','Technical Round','Awaiting Slot Selection','Interview Scheduled',...(extraRounds||[]).map(r=>r.name),'HR Round','Selected','Onboarding'];
  const stageIdx = stageOrder.indexOf(candidate.stage);

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(15,23,42,0.45)', zIndex:500, backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', right:0, top:0, bottom:0, width:520, background:'#fff', zIndex:501, display:'flex', flexDirection:'column', boxShadow:'-8px 0 40px rgba(0,0,0,0.12)' }}>
        <div style={{ padding:'20px 22px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:14, position:'sticky', top:0, background:'#fff' }}>
          <Av name={candidate.name} size={48} />
          <div style={{ flex:1 }}>
            <div style={{ fontWeight:700, fontSize:16, color:C.text }}>{candidate.name}</div>
            <div style={{ fontSize:13, color:C.muted }}>{candidate.role} · {candidate.company}</div>
          </div>
          <button onClick={onClose} style={{ border:'none', background:C.light, borderRadius:8, width:32, height:32, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}><X size={15} color={C.muted}/></button>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'20px 22px' }}>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:20 }}>
            {[['Experience',candidate.exp],['Current Company',candidate.company],['Current CTC',candidate.ctc],['Notice Period',candidate.notice||'30 days']].map(([l,v])=>(
              <div key={l} style={{ background:C.light, borderRadius:8, padding:'12px 14px' }}>
                <div style={{ fontSize:10, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:4 }}>{l}</div>
                <div style={{ fontSize:13, fontWeight:600, color:C.text }}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{ marginBottom:20 }}>
            <div style={{ fontSize:12, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:10 }}>Skills</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {(candidate.skills||[]).map(s=><SkillChip key={s} label={s} />)}
            </div>
          </div>

          <InterviewTimeline
            rounds={candidate.interviewRounds||[]}
            onAddRound={()=>onAddRound(candidate)}
            isRejected={candidate.status === 'rejected'}
          />

          {stageIdx >= 0 && (
            <div style={{ marginBottom:20, padding:'12px 14px', background:C.light, borderRadius:8, display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ width:8, height:8, borderRadius:'50%', background:C.primary, flexShrink:0 }} />
              <div style={{ fontSize:12, color:C.muted }}>Currently in <strong style={{ color:C.text }}>{candidate.stage}</strong> stage ({stageIdx+1} of {stageOrder.length})</div>
            </div>
          )}

          {(() => {
            const BASE    = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const url     = candidate.resume_url ? `${BASE}/${candidate.resume_url}` : null;
            const ext     = url ? url.split('.').pop().toLowerCase() : '';
            const dlName  = `${(candidate.name || 'Candidate').replace(/\s+/g, '_')}_Resume${ext ? '.' + ext : ''}`;
            return (
              <div style={{ marginBottom:20 }}>
                <div style={{ fontSize:12, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:10 }}>Resume</div>
                {url ? (
                  <div style={{ display:'flex', gap:10 }}>
                    <Btn variant="outline" size="sm" style={{ flex:1 }} onClick={() => setResumePreviewOpen(true)}>
                      👁 View Resume
                    </Btn>
                    <a href={url} download={dlName} style={{ flex:1, textDecoration:'none' }}>
                      <Btn variant="outline" size="sm" style={{ width:'100%', justifyContent:'center' }}>
                        <Download size={12} /> Download Resume
                      </Btn>
                    </a>
                  </div>
                ) : (
                  <div style={{ padding:'14px 16px', background:C.light, borderRadius:8, fontSize:12, color:C.muted, textAlign:'center', border:`1px dashed ${C.border}` }}>
                    No resume uploaded
                  </div>
                )}
              </div>
            );
          })()}

          <LabeledField label="Recruiter Notes">
            <textarea rows={3} placeholder="Add your notes or comments about this candidate…" style={{ ...iStyle, resize:'vertical' }} />
          </LabeledField>
        </div>

        {candidate.stage === 'Manager Approval' && (
          <div style={{ padding:'16px 22px', borderTop:`1px solid ${C.border}`, display:'flex', gap:10 }}>
            <Btn variant="danger" style={{ flex:1 }} onClick={()=>onReject(candidate)}><X size={14}/> Reject</Btn>
            <Btn variant="primary" style={{ flex:1 }} onClick={()=>onApprove(candidate)}><Check size={14}/> Approve Candidate</Btn>
          </div>
        )}
      </div>

      <ResumePreviewModal
        open={resumePreviewOpen}
        url={candidate.resume_url
          ? `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/${candidate.resume_url}`
          : null
        }
        candidateName={candidate.name}
        onClose={() => setResumePreviewOpen(false)}
      />
    </>
  );
}

// ── Kanban Card ────────────────────────────────────────────────────────────────
function KanbanCard({ candidate, extraRounds, onClick }) {
  const [over, setOver] = useState(false);
  const stageStyle = getStageStyle(candidate.stage, extraRounds);
  const lastRound  = (candidate.interviewRounds||[]).slice(-1)[0];
  const hasRemarks = lastRound && (lastRound.feedback || lastRound.managerRemark);

  return (
    <div onClick={onClick} onMouseEnter={()=>setOver(true)} onMouseLeave={()=>setOver(false)}
      style={{ background:'#fff', border:`1px solid ${C.border}`, borderRadius:10, padding:'12px 14px', marginBottom:8, cursor:'pointer', boxShadow:over?'0 3px 12px rgba(0,0,0,0.09)':'0 1px 3px rgba(0,0,0,0.04)', transition:'box-shadow 0.15s', position:'relative', overflow:'hidden', borderLeft:`3px solid ${stageStyle.accent}` }}
    >
      {hasRemarks && (
        <div title="Has feedback/remarks" style={{ position:'absolute', top:10, right:10, width:7, height:7, borderRadius:'50%', background:C.yellow, boxShadow:`0 0 0 2px #FFF` }} />
      )}

      <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:7 }}>
        <Av name={candidate.name} size={30} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontWeight:700, fontSize:12, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{candidate.name}</div>
          <div style={{ fontSize:11, color:C.muted }}>{candidate.role}</div>
        </div>
      </div>

      <div style={{ fontSize:11, color:C.muted, marginBottom:4 }}>💼 {candidate.exp} · {candidate.company}</div>

      {candidate.interviewer && (
        <div style={{ fontSize:11, color:C.muted, marginBottom:3 }}>👤 {candidate.interviewer}</div>
      )}
      {candidate.ivDate && candidate.ivTime && (
        <div style={{ fontSize:11, color:C.blue, fontWeight:600, marginBottom:4 }}>📅 {candidate.ivDate}, {candidate.ivTime}</div>
      )}
      {candidate.ivDate && !candidate.ivTime && (
        <div style={{ fontSize:11, color:C.blue, fontWeight:600, marginBottom:4 }}>📅 {candidate.ivDate}</div>
      )}

      {candidate.ivStatus && (
        <div style={{ marginBottom:6 }}>{ivStatusBadge(candidate.ivStatus)}</div>
      )}

      {candidate.offerStatus    && <div style={{ fontSize:11, color:C.primary, fontWeight:600, marginBottom:4 }}>✓ {candidate.offerStatus}</div>}
      {candidate.onboardingDate && <div style={{ fontSize:11, color:C.teal,  fontWeight:600, marginBottom:4 }}>📋 Joining: {candidate.onboardingDate}</div>}

      <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginTop:4 }}>
        {(candidate.skills||[]).slice(0,2).map(s=>(
          <span key={s} style={{ fontSize:9, fontWeight:700, padding:'2px 7px', borderRadius:4, background:'#ECFDF5', color:'#065F46' }}>{s}</span>
        ))}
        {(candidate.skills||[]).length > 2 && (
          <span style={{ fontSize:9, fontWeight:700, padding:'2px 7px', borderRadius:4, background:C.light, color:C.muted }}>+{(candidate.skills||[]).length-2}</span>
        )}
      </div>
    </div>
  );
}

// ── Kanban Column ──────────────────────────────────────────────────────────────
function KanbanColumn({ stage, candidates, extraRounds, onCandidateClick }) {
  const col = getStageStyle(stage, extraRounds);
  const isDynamic = !KNOWN_STAGE_STYLES[stage];
  return (
    <div style={{ width:190, flexShrink:0 }}>
      <div style={{ background:col.hdr, borderRadius:8, padding:'8px 12px', marginBottom:10, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          {isDynamic && <span title="Recruiter-added round" style={{ fontSize:9, fontWeight:700, background:col.accent, color:'#fff', padding:'1px 6px', borderRadius:4 }}>+</span>}
          <span style={{ fontSize:11, fontWeight:700, color:col.text, letterSpacing:0.3 }}>{stage}</span>
        </div>
        <span style={{ fontSize:10, fontWeight:700, color:'#fff', background:col.accent, padding:'2px 8px', borderRadius:12 }}>{candidates.length}</span>
      </div>
      {candidates.length === 0 && (
        <div style={{ textAlign:'center', padding:'20px 10px', fontSize:11, color:C.border, borderRadius:8, border:`1px dashed ${C.border}`, background:col.hdr + '80' }}>No candidates</div>
      )}
      {candidates.map(c=>(
        <KanbanCard key={c.id} candidate={c} extraRounds={extraRounds} onClick={()=>onCandidateClick(c)} />
      ))}
    </div>
  );
}

// ── Approval Card ──────────────────────────────────────────────────────────────
function ApprovalCard({ candidate, onApprove, onReject, onViewResume }) {
  return (
    <div style={{ border:`1px solid ${C.border}`, borderRadius:12, padding:'18px 20px', background:'#fff', marginBottom:14, boxShadow:'0 1px 4px rgba(0,0,0,0.04)' }}>
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:16 }}>
        <div style={{ display:'flex', alignItems:'center', gap:14 }}>
          <Av name={candidate.name} size={44} />
          <div>
            <div style={{ fontWeight:700, fontSize:15, color:C.text }}>{candidate.name}</div>
            <div style={{ fontSize:12, color:C.muted, marginTop:2 }}>{candidate.role} · {candidate.skills?candidate.skills.slice(0,2).join(' + '):''}</div>
          </div>
        </div>
        {candidate.status==='awaiting' && <Badge variant="amber">⏱ Awaiting Approval</Badge>}
        {candidate.status==='approved' && <Badge variant="green">✓ Approved For Interview</Badge>}
        {candidate.status==='rejected' && <Badge variant="red">✕ Rejected</Badge>}
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginBottom:14, padding:'14px 16px', background:C.light, borderRadius:8 }}>
        {[['Experience',candidate.exp],['Current Company',candidate.currentCompany||candidate.company],['Expected CTC',candidate.expCTC||candidate.exp_ctc||candidate.ctc],['Notice Period',candidate.notice||'30 days']].map(([l,v])=>(
          <div key={l}>
            <div style={{ fontSize:10, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.4, marginBottom:3 }}>{l}</div>
            <div style={{ fontSize:13, fontWeight:700, color:C.text }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:14 }}>
        {(candidate.skills||[]).map(s=><SkillChip key={s} label={s} />)}
      </div>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'flex-end', gap:10, paddingTop:12, borderTop:`1px solid ${C.border}` }}>
        <Btn variant="ghost" size="sm" onClick={()=>onViewResume(candidate)}>👤 View Profile</Btn>
        {candidate.status==='awaiting' && (
          <>
            <Btn variant="danger" size="sm" onClick={()=>onReject(candidate)}><X size={13}/> Reject</Btn>
            <Btn variant="primary" size="sm" onClick={()=>onApprove(candidate)}><Check size={13}/> Approve</Btn>
          </>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════════════════════════
export default function RecruitmentPage() {
  const [activeTab,    setActiveTab]    = useState('requirements');
  const [drawerOpen,   setDrawerOpen]   = useState(false);
  const [requirements, setRequirements] = useState([]);
  const [candidates,   setCandidates]   = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [toast,        setToast]        = useState(null);
  const [approvalTab,  setApprovalTab]  = useState('awaiting');
  const [reqFilter,    setReqFilter]    = useState('All');
  const [resumeCandidate, setResumeCandidate] = useState(null);
  const [rejectTarget,    setRejectTarget]    = useState(null);
  const [pipelineReqFilter, setPipelineReqFilter] = useState('All');

  const [extraRounds,    setExtraRounds]    = useState([]);
  const [addRoundModal,  setAddRoundModal]  = useState(false);
  const [roundCandidate, setRoundCandidate] = useState(null);

  const showToast = (msg, type='success') => setToast({ msg, type });

  useEffect(() => {
    Promise.all([getRequirements(), getPipeline()])
      .then(([reqs, cands]) => {
        setRequirements(reqs);
        setCandidates(cands);
      })
      .catch(() => showToast('Could not load recruitment data — check your connection', 'error'))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dynamicPipelineStages = useMemo(() => [
    'Shortlisted',
    'Technical Round',
    ...extraRounds.map(r => r.name),
    'HR Round',
    'Selected',
    'Onboarding',
  ], [extraRounds]);

  const awaitingCandidates = useMemo(
    () => candidates.filter(c => c.status === 'awaiting'),
    [candidates]
  );

  const approvedCandidates = useMemo(
    () => candidates.filter(c => c.status !== 'awaiting' && c.status !== 'rejected'),
    [candidates, extraRounds]
  );

  const rejectedCandidates  = useMemo(() => candidates.filter(c => c.status === 'rejected'), [candidates]);

  const filteredReqs = useMemo(
    () => reqFilter === 'All' ? requirements : requirements.filter(r => r.status === reqFilter),
    [requirements, reqFilter]
  );

  const pipelineCandidates = useMemo(() => {
    if (pipelineReqFilter === 'All') return candidates;
    return candidates.filter(c => c.req === pipelineReqFilter);
  }, [candidates, pipelineReqFilter]);

  const handleApprove = async (candidate) => {
    try {
      const updated = await submitApproval(candidate.pipeline_id, 'approve', {
        remark: candidate.manager_remark || null,
      });
      setCandidates(cs => cs.map(c => c.pipeline_id === updated.pipeline_id ? updated : c));
      setResumeCandidate(null);
      showToast(`Recruiter notified successfully — ${candidate.name} approved`, 'success');
    } catch {
      showToast(`Failed to approve ${candidate.name} — please try again`, 'error');
    }
  };

  const handleReject = (candidate) => {
    setRejectTarget(candidate);
    setResumeCandidate(null);
  };

  const confirmReject = async (reason) => {
    try {
      const updated = await submitApproval(rejectTarget.pipeline_id, 'reject', {
        rejectionReason: reason,
      });
      setCandidates(cs => cs.map(c => c.pipeline_id === updated.pipeline_id ? updated : c));
      setRejectTarget(null);
      showToast(`${rejectTarget.name} rejected — recruiter notified`, 'info');
    } catch {
      showToast(`Failed to reject candidate — please try again`, 'error');
    }
  };

  const addRequirement = async (form) => {
    try {
      const payload = {
        title:           form.title,
        department_id:   form.department || null,
        employment_type: form.employmentType || null,
        work_mode:       form.workMode || null,
        location:        form.location || null,
        min_experience:  form.minExp  ? parseInt(form.minExp,  10) : null,
        max_experience:  form.maxExp  ? parseInt(form.maxExp,  10) : null,
        openings:        form.openings ? parseInt(form.openings, 10) : 1,
        priority:        form.priority  || 'Normal',
        skills:          form.skills         || [],
        pending_skills:  form.pendingSkills  || [],
        job_description: form.jd             || null,
        qualification:   form.preferredQualification || null,
        budget_range:    form.budgetRange    || null,
        target_joining:  form.targetJoining  || null,
      };
      const created = await createRequirement(payload);
      setRequirements(prev => [created, ...prev]);
    } catch (err) {
      showToast('Failed to create requirement — ' + (err.message || 'Unknown error'), 'error');
    }
  };

  const handleAddRound = (roundData) => {
    const { id:_id, ...round } = roundData;
    if (!extraRounds.find(r => r.name === round.name)) {
      setExtraRounds(prev => [...prev, round]);
    }
    if (roundCandidate) {
      const newRound = {
        name:        round.name,
        status:      'scheduled',
        interviewer: round.interviewer || '',
        date:        round.date ? `${round.date}, ${round.time || ''}`.trim().replace(/,\s*$/, '') : '',
        format:      'Teams',
        feedback:    '',
        managerRemark: round.reason || '',
      };
      setCandidates(cs => cs.map(c =>
        c.id === roundCandidate.id
          ? { ...c, interviewRounds: [...(c.interviewRounds||[]), newRound] }
          : c
      ));
      setResumeCandidate(prev => prev?.id === roundCandidate.id
        ? { ...prev, interviewRounds: [...(prev.interviewRounds||[]), newRound] }
        : prev
      );
    }
    setRoundCandidate(null);
    showToast(`"${round.name}" added to pipeline${roundCandidate ? ` for ${roundCandidate.name}` : ''}`, 'success');
  };

  const openAddRound = (candidate = null) => {
    setRoundCandidate(candidate);
    setAddRoundModal(true);
  };

  const stats = useMemo(() => ({
    openReqs:        requirements.filter(r => r.status !== 'Closed').length,
    inPipeline:      candidates.length,
    awaitingApproval:awaitingCandidates.length,
    interviewsSched: candidates.filter(c => c.stage === 'Technical Round' || c.stage === 'HR Round' || extraRounds.some(r=>r.name===c.stage)).length,
    positionsClosed: requirements.filter(r => r.status === 'Closed').length,
  }), [requirements, candidates, awaitingCandidates, extraRounds]);

  const TABS = [
    { id:'requirements', label:'Requirements' },
    { id:'pipeline',     label:'Pipeline' },
    { id:'approvals',    label:`Approvals${awaitingCandidates.length>0?` (${awaitingCandidates.length})`:''}` },
  ];

  if (loading) {
    return (
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:300, fontFamily:"'DM Sans',sans-serif", color:C.muted, fontSize:13 }}>
        Loading recruitment data…
      </div>
    );
  }

  return (
    <div style={{ fontFamily:"'DM Sans',sans-serif" }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24, flexWrap:'wrap', gap:12 }}>
        <div>
          <h2 style={{ margin:0, fontSize:22, fontWeight:800, color:C.text, letterSpacing:'-0.3px' }}>Recruitment</h2>
          <p style={{ margin:'4px 0 0', fontSize:13, color:C.muted }}>Manage hiring requirements, candidate pipeline, and approvals for your team.</p>
        </div>
        <div style={{ display:'flex', gap:10, alignItems:'center', flexWrap:'wrap' }}>
          <Btn variant="primary" onClick={()=>setDrawerOpen(true)} style={{ borderRadius:10, padding:'10px 22px', fontSize:14, boxShadow:'0 2px 12px rgba(16,185,129,0.28)' }}>
            <Plus size={15}/> New Requirement
          </Btn>
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:14, marginBottom:24 }}>
        {[
          { label:'OPEN REQS',         value:stats.openReqs,         sub:'+2 this month',    subC:C.primary, bg:'#ECFDF5', ic:'#10B981', icon:<Briefcase size={16} color="#10B981"/> },
          { label:'IN PIPELINE',       value:stats.inPipeline,       sub:'+8 new',           subC:C.blue,    bg:'#EFF6FF', ic:C.blue,    icon:<UserPlus size={16} color={C.blue}/> },
          { label:'AWAITING APPROVAL', value:stats.awaitingApproval, sub:'⚠ Action needed', subC:C.yellow,  bg:'#FEF9C3', ic:C.yellow,  icon:<AlertTriangle size={16} color={C.yellow}/> },
          { label:'INTERVIEWS SCHED.', value:stats.interviewsSched,  sub:'↑ This week',      subC:C.primary, bg:'#ECFDF5', ic:C.primary, icon:<Star size={16} color={C.primary}/> },
          { label:'POSITIONS CLOSED',  value:stats.positionsClosed,  sub:'↑ vs last month',  subC:C.blue,    bg:'#EFF6FF', ic:C.blue,    icon:<Check size={16} color={C.blue}/> },
        ].map((s,i)=>(
          <Card key={i} hover style={{ padding:'18px 20px', borderTop:`3px solid ${s.ic}`, minWidth:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
              <div style={{ background:s.bg, borderRadius:8, padding:8, display:'flex' }}>{s.icon}</div>
              <span style={{ fontSize:10, color:C.muted, fontWeight:700, textTransform:'uppercase', letterSpacing:0.5 }}>{s.label}</span>
            </div>
            <div style={{ fontSize:28, fontWeight:800, color:C.text, marginBottom:4 }}>{s.value}</div>
            <div style={{ fontSize:12, fontWeight:600, color:s.subC }}>{s.sub}</div>
          </Card>
        ))}
      </div>

      <div style={{ display:'flex', gap:2, marginBottom:24, borderBottom:`1px solid ${C.border}`, paddingBottom:0 }}>
        {TABS.map(t=>(
          <button key={t.id} onClick={()=>setActiveTab(t.id)} style={{ border:'none', background:'none', padding:'10px 20px', fontFamily:"'DM Sans',sans-serif", fontWeight:600, fontSize:13, cursor:'pointer', color:activeTab===t.id?C.primary:C.muted, borderBottom:`2.5px solid ${activeTab===t.id?C.primary:'transparent'}`, transition:'all 0.15s', marginBottom:-1 }}>{t.label}</button>
        ))}
      </div>

      {activeTab === 'requirements' && (
        <Card>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16, flexWrap:'wrap', gap:10 }}>
            <span style={{ fontWeight:700, fontSize:15, color:C.text }}>Open Requirements</span>
            <div style={{ display:'flex', gap:8, alignItems:'center' }}>
              {['All','Active','In Review','Sourcing','Closed'].map(f=>(
                <button key={f} onClick={()=>setReqFilter(f)} style={{ padding:'5px 14px', borderRadius:20, fontSize:12, fontWeight:600, cursor:'pointer', border:`1.5px solid ${reqFilter===f?C.primary:C.border}`, background:reqFilter===f?C.primary:'#fff', color:reqFilter===f?'#fff':C.muted, fontFamily:"'DM Sans',sans-serif", transition:'all 0.15s' }}>{f}</button>
              ))}
              <Btn variant="outline" size="sm"><Download size={12}/> Export</Btn>
            </div>
          </div>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', minWidth:800 }}>
              <thead>
                <tr>{['REQ ID','Job Role','Priority','Skills','Pipeline','Status','Created','Actions'].map(h=>(
                  <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize:10, fontWeight:700, color:C.muted, textTransform:'uppercase', letterSpacing:0.5, background:C.light, whiteSpace:'nowrap' }}>{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {filteredReqs.map(r=>(
                  <tr key={r.id} style={{ borderBottom:`1px solid ${C.border}`, transition:'background 0.1s' }} onMouseEnter={e=>e.currentTarget.style.background='#FAFAFA'} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <td style={{ padding:'12px 14px', fontSize:12, color:C.primary, fontWeight:700 }}>{r.id}</td>
                    <td style={{ padding:'12px 14px' }}>
                      <div style={{ fontWeight:700, fontSize:13, color:C.text }}>{r.title}</div>
                      <div style={{ fontSize:11, color:C.muted }}>{r.department} · {r.openings} opening{r.openings>1?'s':''}</div>
                    </td>
                    <td style={{ padding:'12px 14px' }}>{priorityBadge(r.priority)}</td>
                    <td style={{ padding:'12px 14px' }}>
                      <div style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
                        {(r.skills||[]).slice(0,2).map(s=><span key={s} style={{ fontSize:10, fontWeight:600, padding:'2px 7px', borderRadius:4, background:'#DBEAFE', color:'#1E40AF' }}>{s}</span>)}
                        {(r.skills||[]).length>2 && <span style={{ fontSize:10, color:C.muted }}>+{r.skills.length-2}</span>}
                      </div>
                      {r.pendingSkills?.length>0 && (
                        <div style={{ display:'flex', gap:4, marginTop:4, flexWrap:'wrap' }}>
                          {r.pendingSkills.map(s=><span key={s} style={{ fontSize:10, fontWeight:600, padding:'2px 7px', borderRadius:4, background:'#FEF3C7', color:'#92400E', display:'inline-flex', alignItems:'center', gap:3 }}><AlertTriangle size={8} color="#D97706"/> {s}</span>)}
                        </div>
                      )}
                    </td>
                    <td style={{ padding:'12px 14px', fontSize:13, fontWeight:700, color:C.blue }}>{r.pipeline} cands</td>
                    <td style={{ padding:'12px 14px' }}>{statusBadge(r.status)}</td>
                    <td style={{ padding:'12px 14px', fontSize:12, color:C.muted, whiteSpace:'nowrap' }}>{r.created}</td>
                    <td style={{ padding:'12px 14px' }}>
                      <div style={{ display:'flex', gap:6 }}>
                        <button title="View Pipeline" onClick={()=>{setPipelineReqFilter(r.id);setActiveTab('pipeline');}} style={{ border:`1px solid ${C.border}`, background:'#fff', borderRadius:6, padding:'5px 10px', cursor:'pointer', fontSize:12, color:C.muted, display:'flex', alignItems:'center', gap:4, fontFamily:"'DM Sans',sans-serif" }}><Layers size={11}/> View</button>
                        <button title="Edit" onClick={()=>showToast('Edit mode coming soon','info')} style={{ border:`1px solid ${C.border}`, background:'#fff', borderRadius:6, padding:'5px 8px', cursor:'pointer', color:C.muted, display:'flex', alignItems:'center', fontFamily:"'DM Sans',sans-serif" }}><Edit size={11}/></button>
                        <button title="Pause / Close" onClick={()=>showToast('Requirement paused','info')} style={{ border:`1px solid ${C.border}`, background:'#fff', borderRadius:6, padding:'5px 8px', cursor:'pointer', color:C.muted, display:'flex', alignItems:'center', fontFamily:"'DM Sans',sans-serif" }}><X size={11}/></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredReqs.length===0 && <div style={{ textAlign:'center', padding:'40px 20px', color:C.muted, fontSize:13 }}>No requirements match the selected filter.</div>}
          </div>
        </Card>
      )}

      {activeTab === 'pipeline' && (
        <Card style={{ padding:0, overflow:'hidden' }}>
          <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:10 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontWeight:700, fontSize:15, color:C.text }}>Candidate Pipeline</span>
              {extraRounds.length > 0 && (
                <span style={{ fontSize:11, fontWeight:600, color:C.primary, background:'#D1FAE5', padding:'2px 10px', borderRadius:12 }}>
                  {extraRounds.length} custom round{extraRounds.length>1?'s':''} active
                </span>
              )}
            </div>
            <div style={{ display:'flex', gap:8, alignItems:'center' }}>
              <select value={pipelineReqFilter} onChange={e=>setPipelineReqFilter(e.target.value)} style={{ ...selectStyle, width:'auto', fontSize:12, padding:'6px 10px' }}>
                <option value="All">All Requirements</option>
                {requirements.map(r=><option key={r.id} value={r.id}>{r.id} – {r.title}</option>)}
              </select>
              {pipelineReqFilter !== 'All' && (
                <Btn variant="ghost" size="sm" onClick={()=>setPipelineReqFilter('All')}>× Clear Filter</Btn>
              )}
            </div>
          </div>

          <div style={{ overflowX:'auto', padding:'16px 20px 20px', minHeight:300 }}>
            <div style={{ display:'flex', gap:12, minWidth:'max-content' }}>
              {dynamicPipelineStages.map(stage=>(
                <KanbanColumn
                  key={stage}
                  stage={stage}
                  extraRounds={extraRounds}
                  candidates={pipelineCandidates.filter(c=>c.stage===stage)}
                  onCandidateClick={setResumeCandidate}
                />
              ))}
            </div>
          </div>
        </Card>
      )}

      {activeTab === 'approvals' && (
        <div>
          <div style={{ display:'flex', gap:0, marginBottom:20, background:'#fff', borderRadius:10, border:`1px solid ${C.border}`, padding:4, width:'fit-content' }}>
            {[
              { id:'awaiting', label:`Awaiting (${awaitingCandidates.length})` },
              { id:'approved', label:`Approved (${approvedCandidates.length})` },
              { id:'rejected', label:`Rejected (${rejectedCandidates.length})` },
            ].map(t=>(
              <button key={t.id} onClick={()=>setApprovalTab(t.id)} style={{ padding:'7px 20px', borderRadius:8, fontSize:13, fontWeight:600, cursor:'pointer', border:'none', fontFamily:"'DM Sans',sans-serif", background:approvalTab===t.id?C.primary:'transparent', color:approvalTab===t.id?'#fff':C.muted, transition:'all 0.15s' }}>{t.label}</button>
            ))}
          </div>
          {approvalTab==='awaiting' && (
            awaitingCandidates.length===0
              ? <div style={{ textAlign:'center', padding:'60px 20px', color:C.muted, fontSize:13 }}><div style={{ fontWeight:600 }}>All caught up — no pending approvals.</div></div>
              : awaitingCandidates.map(c=><ApprovalCard key={c.id} candidate={c} onApprove={handleApprove} onReject={handleReject} onViewResume={setResumeCandidate} />)
          )}
          {approvalTab==='approved' && (
            approvedCandidates.length===0
              ? <div style={{ textAlign:'center', padding:'60px 20px', color:C.muted, fontSize:13 }}>No approved candidates yet.</div>
              : approvedCandidates.map(c=><ApprovalCard key={c.id} candidate={{...c,status:'approved'}} onApprove={handleApprove} onReject={handleReject} onViewResume={setResumeCandidate} />)
          )}
          {approvalTab==='rejected' && (
            rejectedCandidates.length===0
              ? <div style={{ textAlign:'center', padding:'60px 20px', color:C.muted, fontSize:13 }}>No rejected candidates.</div>
              : rejectedCandidates.map(c=><ApprovalCard key={c.id} candidate={{...c,status:'rejected'}} onApprove={handleApprove} onReject={handleReject} onViewResume={setResumeCandidate} />)
          )}
        </div>
      )}

      <NewRequirementDrawer open={drawerOpen} onClose={()=>setDrawerOpen(false)} onSave={addRequirement} showToast={showToast} />

      <ResumeDrawer
        open={!!resumeCandidate}
        candidate={resumeCandidate}
        extraRounds={extraRounds}
        onClose={()=>setResumeCandidate(null)}
        onApprove={handleApprove}
        onReject={handleReject}
        onAddRound={openAddRound}
      />

      <AddRoundModal
        open={addRoundModal}
        candidateName={roundCandidate?.name || null}
        onClose={()=>{ setAddRoundModal(false); setRoundCandidate(null); }}
        onConfirm={handleAddRound}
        showToast={showToast}
      />

      <RejectModal open={!!rejectTarget} name={rejectTarget?.name} onClose={()=>setRejectTarget(null)} onConfirm={confirmReject} />

      {toast && <Toast message={toast.msg} type={toast.type} onDone={()=>setToast(null)} />}

      <style>{`@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
}
