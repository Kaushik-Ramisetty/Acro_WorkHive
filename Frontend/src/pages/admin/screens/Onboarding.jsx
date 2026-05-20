/**
 * Onboarding.jsx — Candidate → Employee onboarding workflow screen.
 *
 * Data flow:
 *   • All reads/writes go through src/services/onboardingApi.js
 *   • Backend returns { success, message, data } — the API layer unwraps it
 *   • normalizeCandidate() maps backend shape → UI shape (bgv_status, docs_uploaded, etc.)
 *   • After every mutating action the relevant candidate is re-fetched so the UI
 *     always reflects backend truth (no optimistic state that can drift)
 *
 * Views:
 *   'list'   → CandidateList  (searchable / filterable table)
 *   'detail' → CandidateDetail (full workflow panel for one candidate)
 */

import React, { useState, useEffect, useCallback } from 'react';
import Card from '../../../components/Card';
import PageHeader from '../../../components/PageHeader';
import Icon from '../../../components/Icon';
import PortalModal from '../../../components/Modal';
import PhoneInput from '../../../components/PhoneInput';
import { API_BASE_URL as BASE_URL } from '../../../config/api';
import {
  getCandidates,
  getCandidate,
  createCandidate,
  generateOffer,
  sendOfferEmail,
  acceptOffer,
  convertToEmployee,
  convertToEmployeeFull,
  getEmployeeDetails,
  activateEmployee,
  markJoined,
  markNotJoined,
  markCandidateNotJoined,
  getDepartments,
  getDesignations,
  searchManagers,
  updateBgvStatus,
  initiateBgv,
  verifyDocument,
} from '../../../services/onboardingApi';

// ─── Status definitions ───────────────────────────────────────────────────────

const CANDIDATE_STATUSES = {
  CREATED:         { label: 'Created',          color: 'bg-slate-100 text-slate-600'    },
  OFFER_GENERATED: { label: 'Offer Generated',  color: 'bg-purple-100 text-purple-700'  },
  OFFER_SENT:      { label: 'Offer Sent',        color: 'bg-blue-100 text-blue-700'      },
  OFFER_ACCEPTED:  { label: 'Offer Accepted',    color: 'bg-green-100 text-green-700'    },
  OFFER_REJECTED:  { label: 'Offer Rejected',    color: 'bg-red-100 text-red-700'        },
  DOCS_PENDING:    { label: 'Docs Pending',      color: 'bg-yellow-100 text-yellow-700'  },
  DOCS_SUBMITTED:  { label: 'Docs Submitted',    color: 'bg-teal-100 text-teal-700'      },
  BGV_IN_PROGRESS: { label: 'BGV In Progress',   color: 'bg-orange-100 text-orange-700'  },
  BGV_CLEAR:       { label: 'BGV Clear',         color: 'bg-green-100 text-green-700'    },
  BGV_FAILED:      { label: 'BGV Failed',        color: 'bg-red-100 text-red-700'        },
  BGV_ON_HOLD:     { label: 'BGV On Hold',       color: 'bg-orange-100 text-orange-700'  },
  CONVERTED:       { label: 'Converted',         color: 'bg-indigo-100 text-indigo-700'  },
  JOINED:          { label: 'Joined',            color: 'bg-emerald-100 text-emerald-700'},
  NOT_JOINED:      { label: 'Did Not Join',      color: 'bg-slate-100 text-slate-500'    },
};

const BGV_STATUS_CONFIG = {
  NOT_STARTED:  { label: 'Not Initiated', color: 'bg-slate-100 text-slate-500',   icon: '○' },
  PENDING:      { label: 'Pending',      color: 'bg-slate-100 text-slate-500',   icon: '○' },
  IN_PROGRESS:  { label: 'In Progress',  color: 'bg-yellow-100 text-yellow-700', icon: '◑' },
  REVIEW:       { label: 'Under Review', color: 'bg-orange-100 text-orange-700', icon: '◑' },
  CLEAR:        { label: 'BGV Cleared', color: 'bg-green-100 text-green-700',   icon: '✓' },
  ON_HOLD:      { label: 'BGV On Hold', color: 'bg-orange-100 text-orange-700', icon: '⏸' },
  FAILED:       { label: 'BGV Failed',  color: 'bg-red-100 text-red-700',       icon: '✗' },
};

// Legacy display-only list (table/list view badges).
const REQUIRED_DOCS = [
  { id: 'aadhar',  label: 'Aadhaar Card'       },
  { id: 'pan',     label: 'PAN Card'            },
  { id: 'degree',  label: 'Degree Certificate'  },
  { id: 'exp',     label: 'Experience Letters'  },
  { id: 'photo',   label: 'Passport Photo'      },
  { id: 'bank',    label: 'Bank Account Proof'  },
];

// Mandatory document types that must be VERIFIED before BGV can start.
// Must match REQUIRED_DOC_TYPES in candidate_portal.py and bgv_service.py.
const BGV_REQUIRED_DOC_TYPES = new Set([
  'bgv_form', 'aadhar', 'pan', 'qualification', 'address_proof', 'cif',
]);

// Human-readable labels for the document review panel.
const BGV_DOC_LABELS = {
  bgv_form:      'Updated BGV Form',
  aadhar:        'Aadhaar Card',
  pan:           'PAN Card',
  qualification: 'Highest Qualification',
  address_proof: 'Address Proof',
  cif:           'CIF Document',
};

// Base linear flow — all candidates follow this path
const TIMELINE_STEPS = [
  { key: 'CREATED',         label: 'Candidate Created'     },
  { key: 'OFFER_GENERATED', label: 'Offer Generated'       },
  { key: 'OFFER_SENT',      label: 'Offer Sent'            },
  { key: 'OFFER_ACCEPTED',  label: 'Offer Accepted'        },
  { key: 'DOCS_SUBMITTED',  label: 'Documents Submitted'   },
  { key: 'BGV_IN_PROGRESS', label: 'BGV In Progress'       },
  { key: 'BGV_CLEAR',       label: 'BGV Cleared'           },
  { key: 'CONVERTED',       label: 'Converted to Employee' },
  { key: 'JOINED',          label: 'Joined'                },
];

// BGV branch outcomes — shown as inline status badges, not timeline steps
const BGV_BRANCH_STATUSES = new Set(['BGV_IN_PROGRESS', 'BGV_CLEAR', 'BGV_ON_HOLD', 'BGV_FAILED']);

// Statuses that come AFTER offer acceptance (for "Offer Accepted" step highlighting)
const POST_OFFER_STATUSES = new Set([
  'DOCS_PENDING', 'DOCS_SUBMITTED',
  'BGV_IN_PROGRESS', 'BGV_CLEAR', 'BGV_ON_HOLD', 'BGV_FAILED',
  'CONVERTED', 'JOINED', 'NOT_JOINED',
]);

const TERMINAL_FAIL_STATUSES = new Set(['OFFER_REJECTED', 'BGV_FAILED', 'NOT_JOINED']);
const AVATAR_COLORS = [
  '#6366F1', '#10B981', '#F59E0B', '#3B5BDB',
  '#8B5CF6', '#06B6D4', '#EF4444', '#F97316',
];

// ─── normalizeCandidate ───────────────────────────────────────────────────────
/**
 * Map the backend API shape → the UI shape.
 *
 * Backend fields that differ:
 *   offer_letter_url  → offer_url
 *   expected_joining_date → joining_date
 *   bgv_check.status  → bgv_status
 *   documents[].doc_type → docs_uploaded  (deduped type array)
 *   onboarded_employee → embedded object
 */
function normalizeCandidate(raw) {
  const colorIdx = (raw.id || 0) % AVATAR_COLORS.length;
  const fullName = raw.name ||
    [raw.first_name, raw.last_name].filter(Boolean).join(' ') || '';

  const rawDocs = raw.documents || [];

  // ── Document verification state ───────────────────────────────────────────
  // Backend now returns documents_verified and bgv_initiable directly.
  // We also compute client-side from raw_documents as defence-in-depth.
  const verifiedDocTypes = new Set(
    rawDocs.filter((d) => d.status === 'VERIFIED').map((d) => d.doc_type),
  );
  const clientDocsVerified = [...BGV_REQUIRED_DOC_TYPES].every((t) => verifiedDocTypes.has(t));
  // Prefer the backend-computed flag; fall back to client computation.
  const allRequiredDocsVerified =
    raw.documents_verified !== undefined ? raw.documents_verified : clientDocsVerified;

  const _earlyStatuses = new Set([
    'CREATED','OFFER_GENERATED','OFFER_SENT','OFFER_REJECTED','DOCS_PENDING','DOCS_SUBMITTED',
  ]);

  return {
    // ── Identity ──
    id:            raw.id,
    candidate_ref: raw.candidate_ref,
    first_name:    raw.first_name || '',
    last_name:     raw.last_name  || '',
    name:          fullName,
    email:         raw.email,
    phone:         raw.phone || null,
    role:          raw.role,
    department:    raw.department || null,
    ctc:           raw.ctc || null,
    // ── Dates ──
    joining_date:  raw.expected_joining_date || null,
    created_at:    raw.created_at ? raw.created_at.slice(0, 10) : '',
    // ── Status (keep raw backend value) ──
    status:        raw.status,
    // ── Offer ──
    offer_url:          raw.offer_letter_url || null,
    offer_sent_at:      raw.offer_sent_at || null,
    offer_accepted_at:  raw.offer_accepted_at || null,
    is_offer_accepted:  raw.is_offer_accepted || false,
    credentials_sent:   raw.credentials_sent || false,
    // ── BGV (derived from nested bgv_check) ──
    // Only show real BGV status & details once the offer is accepted.
    // For early pipeline statuses, always return NOT_STARTED and null bgv_check
    // so stale DB records (wrong candidate_id associations) never show through.
    bgv_status:   _earlyStatuses.has(raw.status)
                    ? 'NOT_STARTED'
                    : (raw.bgv_check?.status ?? 'NOT_STARTED'),
    bgv_check:    _earlyStatuses.has(raw.status) ? null : (raw.bgv_check || null),
    // ── Documents (list of doc_type strings, deduped) ──
    docs_uploaded: [...new Set(rawDocs.map((d) => d.doc_type))],
    raw_documents: rawDocs,
    // ── Document verification gate (controls BGV Initiate button) ──
    // True only when ALL 6 required documents (bgv_form, aadhar, pan,
    // qualification, address_proof, cif) are in VERIFIED state.
    all_required_docs_verified: allRequiredDocsVerified,
    verified_doc_types:         [...verifiedDocTypes],
    // bgv_initiable: verified AND no bgv_check record yet
    bgv_initiable: allRequiredDocsVerified && !raw.bgv_check,
    // ── Onboarded employee (legacy nested object) ──
    onboarded_employee: raw.onboarded_employee || null,
    // ── Full Employee record (new conversion flow via /convert/{id}) ──
    employee:    raw.employee || null,
    employee_id: raw.employee?.id || null,
    // ── Resolved fields — backend picks best source (employees table > onboarded_employees) ──
    employee_code:   raw.resolved_employee_code || raw.employee?.employee_code || raw.onboarded_employee?.employee_code || null,
    manager: raw.resolved_manager_name || raw.employee?.reporting_manager_name || raw.onboarded_employee?.manager_name || null,
    // ── UI-only ──
    initials: getInitials(raw.name),
    color:    AVATAR_COLORS[colorIdx],
  };
}

// ─── Utility helpers ──────────────────────────────────────────────────────────

function getInitials(name = '') {
  return name.split(' ').slice(0, 2).map((w) => w[0]).join('').toUpperCase();
}

function getStatusConfig(status) {
  return CANDIDATE_STATUSES[status] || { label: status, color: 'bg-slate-100 text-slate-600' };
}

function getBgvConfig(status) {
  return BGV_STATUS_CONFIG[status] || BGV_STATUS_CONFIG.NOT_STARTED;
}

function getDocumentStatus(docs = []) {
  const count = docs.filter((doc) => REQUIRED_DOCS.some((required) => required.id === doc)).length;
  if (count >= REQUIRED_DOCS.length) return { label: 'Completed', color: 'bg-green-100 text-green-700' };
  if (count > 0) return { label: 'Partial', color: 'bg-yellow-100 text-yellow-700' };
  return { label: 'Pending', color: 'bg-slate-100 text-slate-500' };
}

function getStepIndex(status) {
  return TIMELINE_STEPS.findIndex((s) => s.key === status);
}

// ─── Toast ────────────────────────────────────────────────────────────────────

function Toast({ toasts, onRemove }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 rounded-xl px-4 py-3 shadow-lg text-sm font-medium
            ${t.type === 'error'   ? 'bg-red-600 text-white'
            : t.type === 'success' ? 'bg-emerald-600 text-white'
            : 'bg-slate-800 text-white'}`}
        >
          <span>{t.message}</span>
          <button onClick={() => onRemove(t.id)} className="ml-2 opacity-70 hover:opacity-100">✕</button>
        </div>
      ))}
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState([]);
  const add = useCallback((message, type = 'success') => {
    const id = Date.now();
    setToasts((p) => [...p, { id, message, type }]);
    setTimeout(() => setToasts((p) => p.filter((t) => t.id !== id)), 4500);
  }, []);
  const remove = useCallback((id) => setToasts((p) => p.filter((t) => t.id !== id)), []);
  return { toasts, add, remove };
}

// ─── StatusBadge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const cfg = getStatusConfig(status);
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

// ─── BgvBadge ────────────────────────────────────────────────────────────────

function BgvBadge({ status }) {
  const cfg = getBgvConfig(status);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.color}`}>
      <span>{cfg.icon}</span>{cfg.label}
    </span>
  );
}

function DocumentStatusBadge({ docs }) {
  const cfg = getDocumentStatus(docs);
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

// ─── Avatar ───────────────────────────────────────────────────────────────────

function Avatar({ name, color, size = 9 }) {
  return (
    <div
      className={`flex h-${size} w-${size} shrink-0 items-center justify-center rounded-full text-white font-bold`}
      style={{ background: color, fontSize: size <= 8 ? 11 : 13 }}
    >
      {getInitials(name)}
    </div>
  );
}

// ─── StatusTimeline ───────────────────────────────────────────────────────────

function StatusTimeline({ currentStatus, bgvStatus }) {
  // Map BGV branch statuses onto the base timeline index so the
  // connector dots render correctly even for non-linear states.
  const effectiveStatus = (() => {
    switch (currentStatus) {
      case 'BGV_ON_HOLD': return 'BGV_IN_PROGRESS'; // on the BGV_IN_PROGRESS step
      case 'BGV_FAILED':  return 'BGV_IN_PROGRESS'; // same position, different badge
      default:            return currentStatus;
    }
  })();

  const currentIdx = getStepIndex(effectiveStatus);
  const isFailed   = currentStatus === 'BGV_FAILED' || TERMINAL_FAIL_STATUSES.has(currentStatus);
  const isOnHold   = currentStatus === 'BGV_ON_HOLD';
  const isClear    = currentStatus === 'BGV_CLEAR';

  // BGV inline badge config
  const bgvBadge = bgvStatus && bgvStatus !== 'NOT_STARTED' ? (
    BGV_STATUS_CONFIG[bgvStatus] || { label: bgvStatus, color: 'bg-slate-100 text-slate-500', icon: '○' }
  ) : null;

  return (
    <div className="flex flex-col">
      {TIMELINE_STEPS.map((step, idx) => {
        const done   = currentIdx > idx;
        const active = currentIdx === idx;

        // Special colour logic for BGV step
        const isBgvStep = step.key === 'BGV_IN_PROGRESS' || step.key === 'BGV_CLEAR';
        const activeColor = isFailed && isBgvStep ? 'bg-red-500 border-red-500'
                          : isOnHold && isBgvStep ? 'bg-orange-500 border-orange-500'
                          : isClear  && isBgvStep ? 'bg-emerald-500 border-emerald-500'
                          : 'bg-blue-600 border-blue-600';

        const dotClass  = done   ? 'bg-emerald-500 border-emerald-500'
                        : active ? activeColor
                        : 'bg-slate-200 border-slate-300';
        const lineClass = done ? 'bg-emerald-400' : 'bg-slate-200';
        const labelClass = done  ? 'text-slate-700'
                         : active ? 'text-slate-900 font-semibold'
                         : 'text-slate-400';

        return (
          <div key={step.key} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div className={`h-3 w-3 rounded-full border-2 mt-1 shrink-0 ${dotClass}`} />
              {idx < TIMELINE_STEPS.length - 1 && (
                <div className={`w-0.5 h-6 ${lineClass}`} />
              )}
            </div>
            <div className="flex flex-1 items-center gap-2">
              <p className={`text-sm ${labelClass}`}>{step.label}</p>
              {/* Inline BGV badge next to the BGV_IN_PROGRESS step */}
              {isBgvStep && bgvBadge && (active || done) && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${bgvBadge.color}`}>
                  {bgvBadge.icon} {bgvBadge.label}
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* Terminal state banners */}
      {isFailed && currentStatus !== 'NOT_JOINED' && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
          <span>✗</span>
          <span>BGV Failed — HR override is allowed</span>
        </div>
      )}
      {isOnHold && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-orange-50 px-3 py-2 text-sm text-orange-700">
          <span>⏸</span>
          <span>BGV On Hold — awaiting further review</span>
        </div>
      )}
      {TERMINAL_FAIL_STATUSES.has(currentStatus) && currentStatus !== 'BGV_FAILED' && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
          <span>⚠</span>
          <span>{getStatusConfig(currentStatus).label}</span>
        </div>
      )}
    </div>
  );
}

// ─── Modal shell ──────────────────────────────────────────────────────────────
// Thin wrapper — delegates to the portal-based PortalModal so this modal
// renders on document.body, completely outside the sidebar/layout tree.

function Modal({ title, onClose, children, width = 'max-w-lg' }) {
  return (
    <PortalModal title={title} onClose={onClose} width={width}>
      {children}
    </PortalModal>
  );
}

// ─── CreateCandidateModal ─────────────────────────────────────────────────────
// Department + role are fetched from the DB:
//   - Departments come from GET /departments/
//   - Designations (Role / Position) come from GET /designations/?department_id=X
// The candidate row stores department NAME and role TITLE (strings) so the
// downstream Convert-to-Employee flow can resolve them back to ids by name.

function CreateCandidateModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', phone: '',
    department_id: '', designation_id: '',
    ctc: '', joining_date: '',
  });
  const [departments, setDepartments]   = useState([]);
  const [designations, setDesignations] = useState([]);
  const [loadingDepts,  setLoadingDepts]  = useState(true);
  const [loadingDesigs, setLoadingDesigs] = useState(false);
  const [deptsErr,  setDeptsErr]  = useState('');   // inline (non-blocking)
  const [desigsErr, setDesigsErr] = useState('');   // inline (non-blocking)
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');       // form-submission errors only

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }));

  // ── Load department list (with retry support) ────────────────────────────
  const loadDepartments = () => {
    let cancelled = false;
    setLoadingDepts(true);
    setDeptsErr('');
    getDepartments()
      .then((rows) => {
        if (cancelled) return;
        const arr = Array.isArray(rows) ? rows : (rows?.data || []);
        arr.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        setDepartments(arr);
        // Don't auto-pick: let the user explicitly choose so the form
        // validates the field rather than silently submitting the first one.
      })
      .catch((err) => {
        if (cancelled) return;
        // Inline-only — never block the rest of the form. The Retry button
        // below the dropdown lets the user re-attempt without re-opening
        // the modal.
        setDeptsErr(err?.message || 'Could not load departments.');
        setDepartments([]);
      })
      .finally(() => { if (!cancelled) setLoadingDepts(false); });
    return () => { cancelled = true; };
  };
  useEffect(() => {
    const cleanup = loadDepartments();
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load designations on dept change (with retry support) ────────────────
  const loadDesignations = (deptId) => {
    if (!deptId) { setDesignations([]); setDesigsErr(''); return () => {}; }
    let cancelled = false;
    setLoadingDesigs(true);
    setDesigsErr('');
    getDesignations(deptId)
      .then((rows) => {
        if (cancelled) return;
        const arr = Array.isArray(rows) ? rows : (rows?.data || []);
        arr.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
        setDesignations(arr);
        setForm((p) => ({
          ...p,
          designation_id: arr.find((d) => d.id === p.designation_id) ? p.designation_id : '',
        }));
      })
      .catch((err) => {
        if (cancelled) return;
        setDesigsErr(err?.message || 'Could not load designations.');
        setDesignations([]);
      })
      .finally(() => { if (!cancelled) setLoadingDesigs(false); });
    return () => { cancelled = true; };
  };
  useEffect(() => {
    const cleanup = loadDesignations(form.department_id);
    return cleanup;
  }, [form.department_id]);

  const selectedDept  = departments.find((d) => d.id === form.department_id);
  const selectedDesig = designations.find((d) => d.id === form.designation_id);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.first_name || !form.last_name || !form.email || !form.designation_id || !form.department_id) {
      setError('First name, last name, email, role and department are required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const raw = await createCandidate({
        first_name:            form.first_name.trim(),
        last_name:             form.last_name.trim(),
        email:                 form.email,
        phone:                 form.phone || null,
        // Send the human-readable strings — that's what the schema expects
        // and what the Convert-to-Employee modal later matches against
        // /departments and /designations to resolve the ids.
        role:                  selectedDesig ? selectedDesig.title : '',
        department:            selectedDept  ? selectedDept.name   : null,
        ctc:                   form.ctc || null,
        expected_joining_date: form.joining_date || null,
      });
      onCreated(normalizeCandidate(raw));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Add New Candidate" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
        )}
        <div className="grid grid-cols-2 gap-4">
          {[
            { label: 'First Name *', key: 'first_name', type: 'text',  placeholder: 'e.g. Rahul' },
            { label: 'Last Name *',  key: 'last_name',  type: 'text',  placeholder: 'e.g. Mehta' },
            { label: 'Email *',      key: 'email',      type: 'email', placeholder: 'rahul@email.com' },
            { label: 'CTC (LPA in INR)', key: 'ctc',    type: 'text',  placeholder: 'e.g. 12 LPA' },
          ].map(({ label, key, type, placeholder }) => (
            <div key={key}>
              <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
              <input type={type} placeholder={placeholder} value={form[key]} onChange={set(key)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100" />
            </div>
          ))}
          {/* Phone — uses PhoneInput for E.164 validation */}
          <PhoneInput
            value={form.phone}
            onChange={(v) => setForm((p) => ({ ...p, phone: v }))}
            label="Phone"
            hint="Include country code: +919876543210"
          />
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Department *</label>
            <select value={form.department_id} onChange={set('department_id')} disabled={loadingDepts}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 disabled:bg-slate-50">
              <option value="">
                {loadingDepts ? 'Loading…'
                 : deptsErr   ? 'Could not load — click Retry below'
                 : departments.length === 0 ? 'No departments configured'
                 : 'Select department'}
              </option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            {deptsErr && (
              <p className="mt-1 text-[11px] text-amber-700">
                Couldn't load departments.{' '}
                <button type="button" onClick={loadDepartments} className="font-semibold underline">Retry</button>
              </p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Role / Position *</label>
            <select value={form.designation_id} onChange={set('designation_id')}
              disabled={!form.department_id || loadingDesigs}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 disabled:bg-slate-50">
              <option value="">
                {!form.department_id ? 'Pick a department first'
                 : loadingDesigs     ? 'Loading…'
                 : desigsErr         ? 'Could not load — click Retry below'
                 : designations.length === 0 ? 'No designations configured'
                 : 'Select role / position'}
              </option>
              {designations.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}{d.level != null ? ` (L${d.level})` : ''}
                </option>
              ))}
            </select>
            {desigsErr && form.department_id && (
              <p className="mt-1 text-[11px] text-amber-700">
                Couldn't load designations.{' '}
                <button type="button" onClick={() => loadDesignations(form.department_id)} className="font-semibold underline">Retry</button>
              </p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Expected Joining Date</label>
            <input type="date" value={form.joining_date} onChange={set('joining_date')}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500" />
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button type="submit" disabled={loading}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
            {loading ? 'Creating…' : 'Create Candidate'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ─── OfferLetterModal ─────────────────────────────────────────────────────────

function buildDefaultSubject(candidate) {
  return `Offer Letter - ${candidate.name} | ${candidate.role} at Acronotics`;
}

function buildDefaultBody(candidate) {
  const joining = candidate.joining_date || 'as discussed';
  const ctcLine = candidate.ctc ? `\nCTC (Annual)    : ${candidate.ctc}` : '';
  return `Dear ${candidate.name},

We are pleased to extend this offer of employment for the position of ${candidate.role}${candidate.department ? ` in the ${candidate.department} department` : ''}.

Offer Details
─────────────────────────────
Role            : ${candidate.role}
Department      : ${candidate.department || 'N/A'}
Expected Joining: ${joining}${ctcLine}
Reference No.   : ${candidate.candidate_ref || '—'}
─────────────────────────────

Please find your offer letter attached to this email.

Kindly respond within 7 days to confirm your acceptance.

This offer is contingent upon successful completion of the background verification process.

We look forward to welcome you to the Acronotics team!

Warm regards,
HR Team — Acronotics`;
}

function OfferLetterModal({ candidate, onClose, onRefresh, toast }) {
  const [generating, setGenerating] = useState(false);
  const [sending,    setSending]    = useState(false);
  // 'preview' = show offer preview | 'compose' = email compose form
  const [view, setView] = useState('preview');

  const [emailForm, setEmailForm] = useState({
    to_email: candidate.email || '',
    subject:  buildDefaultSubject(candidate),
    body:     buildDefaultBody(candidate),
  });

  const hasOffer = !!(
    candidate.offer_url ||
    ['OFFER_GENERATED', 'OFFER_SENT', 'OFFER_ACCEPTED',
     'DOCS_PENDING', 'DOCS_SUBMITTED', 'BGV_IN_PROGRESS', 'BGV_CLEAR',
     'BGV_FAILED', 'CONVERTED', 'JOINED'].includes(candidate.status)
  );

  // BASE_URL imported from config/api

  const setField = (k) => (e) => setEmailForm((p) => ({ ...p, [k]: e.target.value }));

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateOffer(candidate.id);
      toast('Offer letter generated!', 'success');
      await onRefresh();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleSend = async () => {
    if (!emailForm.to_email || !emailForm.subject) {
      toast('Recipient email and subject are required.', 'error');
      return;
    }
    setSending(true);
    try {
      await sendOfferEmail(candidate.id, {
        to_email: emailForm.to_email,
        subject:  emailForm.subject,
        body:     emailForm.body,
      });
      toast(`✅ Offer email sent to ${emailForm.to_email}`, 'success');
      await onRefresh();
      onClose();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSending(false);
    }
  };

  // ── Preview view ──────────────────────────────────────────────────────────
  if (view === 'preview') {
    return (
      <Modal title="Offer Letter" onClose={onClose} width="max-w-xl">
        {/* Offer summary card */}
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Offer Preview
            </span>
            {hasOffer && (
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                Generated
              </span>
            )}
          </div>
          <div className="space-y-1.5 text-sm text-slate-700">
            <p><span className="font-medium">Candidate:</span> {candidate.name}</p>
            <p><span className="font-medium">Role:</span> {candidate.role}</p>
            <p><span className="font-medium">Department:</span> {candidate.department || '—'}</p>
            <p><span className="font-medium">CTC (Annual):</span> {candidate.ctc || '—'}</p>
            <p><span className="font-medium">Joining Date:</span> {candidate.joining_date || 'TBD'}</p>
          </div>
          {hasOffer && candidate.offer_url && (
            <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-center text-sm text-blue-700">
              📄 Offer letter ready — will be attached to the email
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-3">
          {!hasOffer && (
            <button onClick={handleGenerate} disabled={generating}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60">
              {generating ? 'Generating…' : '⚡ Generate Offer'}
            </button>
          )}
          {hasOffer && candidate.offer_url && (
            <a href={`${BASE_URL}${candidate.offer_url}`} target="_blank" rel="noreferrer"
              className="flex-1 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 text-center">
              ⬇ Download PDF
            </a>
          )}
          <button
            onClick={() => setView('compose')}
            disabled={!hasOffer}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
            ✉ Send Offer Email
          </button>
        </div>
        {!hasOffer && (
          <p className="mt-3 text-center text-xs text-slate-400">
            Generate the offer letter first before sending.
          </p>
        )}
      </Modal>
    );
  }

  // ── Email compose view ────────────────────────────────────────────────────
  return (
    <Modal title="Compose Offer Email" onClose={onClose} width="max-w-2xl">
      {/* Back link */}
      <button
        onClick={() => setView('preview')}
        className="mb-4 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
        ← Back to preview
      </button>

      <div className="space-y-4">
        {/* To */}
        <div>
          <label className="mb-1 block text-xs font-semibold text-slate-500 uppercase tracking-wide">
            To *
          </label>
          <input
            type="email"
            value={emailForm.to_email}
            onChange={setField('to_email')}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100"
            placeholder="candidate@email.com"
          />
          {emailForm.to_email !== candidate.email && (
            <p className="mt-1 text-xs text-amber-600">
              ⚠ Recipient differs from candidate's saved email ({candidate.email})
            </p>
          )}
        </div>

        {/* Subject */}
        <div>
          <label className="mb-1 block text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Subject *
          </label>
          <input
            type="text"
            value={emailForm.subject}
            onChange={setField('subject')}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100"
          />
        </div>

        {/* Body */}
        <div>
          <label className="mb-1 block text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Message Body
          </label>
          <textarea
            rows={12}
            value={emailForm.body}
            onChange={setField('body')}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100 resize-y"
          />
        </div>

        {/* Attachment notice */}
        {candidate.offer_url && (
          <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-700">
            <span>📎</span>
            <span>Offer letter PDF will be attached automatically.</span>
          </div>
        )}

        {/* Footer buttons */}
        <div className="flex justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={() => setView('preview')}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={sending}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
            {sending
              ? <><span className="animate-spin">⟳</span> Sending…</>
              : '✉ Send Email'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── ConvertToEmployeeModal ───────────────────────────────────────────────────

function SectionHeader({ icon, title }) {
  return (
    <div className="flex items-center gap-2 border-b border-slate-100 pb-2 mb-4">
      <span className="text-base">{icon}</span>
      <span className="text-sm font-semibold text-slate-700 uppercase tracking-wide">{title}</span>
    </div>
  );
}

function FormField({ label, required, children, hint, error }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">
        {label}{required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
      {hint  && !error && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}

const INPUT_CLS =
  'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none ' +
  'focus:border-blue-500 focus:ring-1 focus:ring-blue-100 disabled:bg-slate-50 disabled:text-slate-400';

// const TIMEZONES = [
//   "Asia/Kolkata","Asia/Dubai","Asia/Singapore","Asia/Tokyo",
//   "Europe/London","Europe/Paris","Europe/Berlin",
//   "America/New_York","America/Chicago","America/Los_Angeles","UTC",
// ];

function ConvertToEmployeeModal({ candidate, onClose, onRefresh, toast }) {
  // ── Reference data ───────────────────────────────────────────────────────────
  const [departments,   setDepartments]   = useState([]);
  const [designations,  setDesignations]  = useState([]);
  const [loadingDepts,  setLoadingDepts]  = useState(true);
  const [loadingDesigs, setLoadingDesigs] = useState(false);
  // Auto-resolved from candidate.department / candidate.role -- the admin
  // does NOT pick these; the candidate's profile is the source of truth.
  const [matchedDept,   setMatchedDept]   = useState(null);  // {id, name} | null
  const [matchedDesig,  setMatchedDesig]  = useState(null);  // {id, title, level} | null
  const [matchError,    setMatchError]    = useState(null);

  // ── Manager search ───────────────────────────────────────────────────────────
  const [managerQuery,    setManagerQuery]    = useState('');
  const [managerResults,  setManagerResults]  = useState([]);
  const [selectedManager, setSelectedManager] = useState(null);
  const [managerFocused,  setManagerFocused]  = useState(false);

  // ── Form state ───────────────────────────────────────────────────────────────
  const nameParts = (candidate.name || '').trim().split(' ');
  const [form, setForm] = useState({
    // Basic
    first_name:      candidate.first_name || nameParts[0] || '',
    last_name:       candidate.last_name  || nameParts.slice(1).join(' ') || '',
    phone:           candidate.phone || '',
    secondary_phone: '',
    // Employment
    department_id:       '',
    designation_id:      '',
    employment_status:   'active',
    date_of_joining:     candidate.joining_date || '',
    location:            '',
    // time_zone:           'Asia/Kolkata',
    // Personal
    date_of_birth:   '',
    gender:          '',
    Nationality:     '',
    Marital_status:  '',
    blood_group:     '',
    // Banking & ID
    aadhaar:      '',
    pan:          '',
    bank_account: '',
    bank_ifsc:    '',
    // Emergency
    emergency_contact_name:  '',
    emergency_contact_phone: '',
    // Password
    password: 'employee123',
  });
  const [errors,  setErrors]  = useState({});
  const [loading, setLoading] = useState(false);
  const [showPwd, setShowPwd] = useState(false);

  const set = (k) => (e) => {
    const val = e.target ? e.target.value : e;
    setForm((p) => ({
      ...p,
      [k]: val,
      ...(k === 'department_id' ? { designation_id: '' } : {}),
    }));
    setErrors((p) => ({ ...p, [k]: '' }));
  };

  // ── Load departments + auto-resolve from candidate.department ────────────────
  // Resolution rules:
  //   1. If the candidate's department string matches a DB row by case-
  //      insensitive name, pre-select it.
  //   2. Otherwise, leave the dropdown unselected and show a soft notice so
  //      the admin can pick the correct department manually. Validation only
  //      fails if the dropdown is still empty at submit time.
  useEffect(() => {
    getDepartments()
      .then((d) => {
        const list = Array.isArray(d) ? d : [];
        setDepartments(list);
        const candDept = (candidate.department || '').trim().toLowerCase();
        if (!candDept) {
          setMatchError('Candidate has no department on file — please pick one below.');
          return;
        }
        const dm = list.find((x) => (x.name || '').trim().toLowerCase() === candDept);
        if (dm) {
          setMatchedDept(dm);
          setForm((p) => ({ ...p, department_id: dm.id }));
          // Clear any prior notice — auto-resolution succeeded.
          setMatchError((prev) => (prev && prev.startsWith('Department')) ? null : prev);
        } else {
          setMatchError(`We couldn't auto-match department "${candidate.department}" — please pick the correct one below.`);
        }
      })
      .catch(() => toast('Could not load departments', 'error'))
      .finally(() => setLoadingDepts(false));
  }, []);

  // ── Load designations + auto-resolve from candidate.role ─────────────────────
  useEffect(() => {
    if (!form.department_id) { setDesignations([]); return; }
    setLoadingDesigs(true);
    getDesignations(form.department_id)
      .then((d) => {
        const list = Array.isArray(d) ? d : [];
        setDesignations(list);
        const candRole = (candidate.role || '').trim().toLowerCase();
        if (!candRole) {
          setMatchError((prev) => prev || 'Candidate has no role on file — please pick one below.');
          return;
        }
        const dg = list.find((x) => (x.title || '').trim().toLowerCase() === candRole);
        if (dg) {
          setMatchedDesig(dg);
          setForm((p) => ({ ...p, designation_id: dg.id }));
          // Clear any prior auto-match warning if it was about designation.
          setMatchError((prev) => (prev && prev.toLowerCase().includes('designation')) ? null : prev);
        } else {
          setMatchError((prev) => prev || `We couldn't auto-match designation "${candidate.role}" — please pick the correct one below.`);
        }
      })
      .catch(() => setDesignations([]))
      .finally(() => setLoadingDesigs(false));
  }, [form.department_id]);

  // Whenever the user manually picks values that satisfy both fields, drop
  // the soft notice so the form looks clean again.
  useEffect(() => {
    if (form.department_id && form.designation_id && matchError) {
      setMatchError(null);
    }
  }, [form.department_id, form.designation_id, matchError]);

  // ── Manager debounce search ────────────────────────────────────────────────────
  useEffect(() => {
    if (!managerQuery || managerQuery.length < 2) { setManagerResults([]); return; }
    const t = setTimeout(() => {
      searchManagers(managerQuery)
        .then((r) => setManagerResults(Array.isArray(r) ? r : []))
        .catch(() => setManagerResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [managerQuery]);

  // ── Validation ────────────────────────────────────────────────────────────────
  const validate = () => {
    const e = {};
    if (!form.first_name.trim())   e.first_name     = 'Required';
    if (!form.last_name.trim())    e.last_name      = 'Required';
    // Department / Designation are pulled from the candidate's profile; if
    // they could not be resolved we show matchError instead of a per-field
    // error and block submission below.
    if (!form.department_id)       e.department_id  = 'Could not resolve from candidate profile';
    if (!form.designation_id)      e.designation_id = 'Could not resolve from candidate profile';
    if (!selectedManager?.id)      e.reporting_manager = 'Select a reporting manager from the employee list';
    if (!form.date_of_joining)     e.date_of_joining= 'Required';
    if (!form.password || form.password.length < 6)
                                   e.password       = 'Min 6 characters';
    setErrors(e);
    return Object.keys(e).length === 0 && !matchError;
  };

  // ── Submit ─────────────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setLoading(true);
    try {
      await convertToEmployee(candidate.id, {
        first_name:              form.first_name.trim(),
        last_name:               form.last_name.trim(),
        phone:                   form.phone || null,
        secondary_phone:         form.secondary_phone || null,
        department_id:           form.department_id,
        designation_id:          form.designation_id,
        reporting_manager_id:    selectedManager?.id || null,
        employment_status:       'active',  // always active for new conversions

        date_of_joining:         form.date_of_joining || null,
        date_of_birth:           form.date_of_birth   || null,
        gender:                  form.gender     || null,
        Nationality:             form.Nationality || null,
        Marital_status:          form.Marital_status || null,
        blood_group:             form.blood_group || null,
        location:                form.location   || null,
        // time_zone:               form.time_zone  || null,
        aadhaar:                 form.aadhaar      || null,
        pan:                     form.pan          || null,
        bank_account:            form.bank_account || null,
        bank_ifsc:               form.bank_ifsc   || null,
        emergency_contact_name:  form.emergency_contact_name  || null,
        emergency_contact_phone: form.emergency_contact_phone || null,
        password:                form.password,
      });
      toast(`🎉 ${candidate.name} converted to Employee!`, 'success');
      await onRefresh();
      onClose();
    } catch (err) {
      toast(err.message || 'Conversion failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const err = (k) => errors[k] || undefined;

  return (
    <Modal title="Convert to Employee" onClose={onClose} width="max-w-4xl">
      {/* Candidate identity strip */}
      <div className="mb-5 flex items-center gap-3 rounded-xl bg-blue-50 px-4 py-3">
        <Avatar name={candidate.name} color={candidate.color} size={10} />
        <div>
          <p className="font-semibold text-slate-900">{candidate.name}</p>
          <p className="text-sm text-slate-500">{candidate.role} · {candidate.email}</p>
        </div>
        <span className="ml-auto rounded-full bg-emerald-100 px-3 py-0.5 text-xs font-semibold text-emerald-700">
          Ready to Convert
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="max-h-[68vh] overflow-y-auto pr-2 space-y-7">

          {/* ── Basic Info ─────────────────────────────────────────────── */}
          <section>
            <SectionHeader icon="👤" title="Basic Information" />
            <div className="grid grid-cols-2 gap-4">
              <FormField label="First Name" required error={err('first_name')}>
                <input className={INPUT_CLS} value={form.first_name} onChange={set('first_name')} placeholder="First name" />
              </FormField>
              <FormField label="Last Name" required error={err('last_name')}>
                <input className={INPUT_CLS} value={form.last_name} onChange={set('last_name')} placeholder="Last name" />
              </FormField>
              <FormField label="Email">
                <input className={INPUT_CLS} value={candidate.email} disabled />
              </FormField>
              <FormField label="Phone" error={err('phone')}>
                <PhoneInput
                  value={form.phone}
                  onChange={(v) => { setForm((p) => ({ ...p, phone: v })); setErrors((p) => ({ ...p, phone: '' })); }}
                  error={errors.phone}
                  hint="E.164 format: +919876543210"
                />
              </FormField>
              <FormField label="Secondary Phone" error={err('secondary_phone')}>
                <PhoneInput
                  value={form.secondary_phone}
                  onChange={(v) => { setForm((p) => ({ ...p, secondary_phone: v })); setErrors((p) => ({ ...p, secondary_phone: '' })); }}
                  label=""
                  
                />
              </FormField>
            </div>
          </section>

          {/* ── Employment Details ──────────────────────────────────────── */}
          <section>
            <SectionHeader icon="💼" title="Employment Details" />
            <div className="grid grid-cols-2 gap-4">

              {matchError && (
                <div className="col-span-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  ⚠ {matchError}
                </div>
              )}

              <FormField label="Department" required error={err('department_id')}
                hint="Locked — pulled from candidate profile">
                <input
                  className={INPUT_CLS + ' bg-slate-50 text-slate-700 cursor-not-allowed'}
                  value={
                    matchedDept ? matchedDept.name
                    : loadingDepts ? 'Loading…'
                    : (candidate.department || '—')
                  }
                  disabled
                  readOnly
                />
              </FormField>

              <FormField label="Designation" required error={err('designation_id')}
                hint="Locked — pulled from candidate profile">
                <input
                  className={INPUT_CLS + ' bg-slate-50 text-slate-700 cursor-not-allowed'}
                  value={
                    matchedDesig ? `${matchedDesig.title} (L${matchedDesig.level})`
                    : loadingDesigs ? 'Loading…'
                    : (candidate.role || '—')
                  }
                  disabled
                  readOnly
                />
              </FormField>

              <FormField label="Reporting Manager" required
                error={err('reporting_manager')}
                hint="Type 2+ chars to search. Must be an existing employee.">
                <div className="relative">
                  <input
                    className={INPUT_CLS}
                    value={selectedManager
                      ? `${selectedManager.first_name} ${selectedManager.last_name} (${selectedManager.employee_code})`
                      : managerQuery}
                    onChange={(e) => {
                      // Free-typed text never becomes the value -- only a click on a result row sets selectedManager.
                      setSelectedManager(null);
                      setManagerQuery(e.target.value);
                      setErrors((p) => ({ ...p, reporting_manager: '' }));
                    }}
                    onFocus={() => setManagerFocused(true)}
                    onBlur={() => setTimeout(() => setManagerFocused(false), 180)}
                    placeholder="Search name or code…"
                  />
                  {managerFocused && managerResults.length > 0 && (
                    <div className="absolute z-50 mt-1 w-full rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden">
                      {managerResults.slice(0, 6).map((m) => (
                        <button key={m.id} type="button"
                          onMouseDown={() => { setSelectedManager(m); setManagerQuery(''); setManagerResults([]); }}
                          className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-blue-50">
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">
                            {m.first_name?.[0]}{m.last_name?.[0]}
                          </div>
                          <div>
                            <p className="font-medium text-slate-800">{m.first_name} {m.last_name}</p>
                            <p className="text-xs text-slate-400">{m.employee_code}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                  {managerFocused && managerQuery.length >= 2 && managerResults.length === 0 && (
                    <div className="absolute z-50 mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500 shadow-xl">
                      No matching employee found. Reporting manager must be an existing employee.
                    </div>
                  )}
                  {selectedManager && (
                    <button type="button"
                      onClick={() => { setSelectedManager(null); setManagerQuery(''); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 text-lg">×</button>
                  )}
                </div>
              </FormField>

              {/* Employment status dropdown removed — new conversions are always created as Active. */}

              <FormField label="Date of Joining" required error={err('date_of_joining')}>
                <input type="date" className={INPUT_CLS} value={form.date_of_joining} onChange={set('date_of_joining')} />
              </FormField>

              <FormField label="Location">
                <input className={INPUT_CLS} value={form.location} onChange={set('location')} placeholder="City, Country" />
              </FormField>

              {/* <FormField label="Time Zone">
                <select className={INPUT_CLS} value={form.time_zone} onChange={set('time_zone')}>
                  {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
                </select>
              </FormField> */}
            </div>
          </section>

          {/* ── Personal Info ───────────────────────────────────────────── */}
          <section>
            <SectionHeader icon="🪪" title="Personal Information" />
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Date of Birth">
                <input type="date" className={INPUT_CLS} value={form.date_of_birth} onChange={set('date_of_birth')} />
              </FormField>
              <FormField label="Gender">
                <select className={INPUT_CLS} value={form.gender} onChange={set('gender')}>
                  <option value="">— Select —</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </FormField>
              <FormField label="Nationality">
                <input className={INPUT_CLS} value={form.Nationality} onChange={set('Nationality')} placeholder="e.g. Indian" />
              </FormField>
              <FormField label="Marital Status">
                <select className={INPUT_CLS} value={form.Marital_status} onChange={set('Marital_status')}>
                  <option value="">— Select —</option>
                  <option value="single">Single</option>
                  <option value="married">Married</option>
                  <option value="divorced">Divorced</option>
                  <option value="widowed">Widowed</option>
                </select>
              </FormField>
              <FormField label="Blood Group">
                <select className={INPUT_CLS} value={form.blood_group} onChange={set('blood_group')}>
                  <option value="">— Select —</option>
                  {['A+','A-','B+','B-','AB+','AB-','O+','O-'].map((bg) => (
                    <option key={bg} value={bg}>{bg}</option>
                  ))}
                </select>
              </FormField>
            </div>
          </section>

          {/* ── Banking & Identity ──────────────────────────────────────── */}
          <section>
            <SectionHeader icon="🏦" title="Banking & Identity" />
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Aadhaar Number" hint="Stored securely">
                <input className={INPUT_CLS} value={form.aadhaar} onChange={set('aadhaar')} placeholder="XXXX XXXX XXXX" maxLength={12} />
              </FormField>
              <FormField label="PAN Number" hint="Stored securely">
                <input className={INPUT_CLS} value={form.pan} onChange={set('pan')} placeholder="XXXXXXXXXX" maxLength={10} style={{textTransform:'uppercase'}} />
              </FormField>
              <FormField label="Bank Account Number" hint="Stored securely">
                <input className={INPUT_CLS} value={form.bank_account} onChange={set('bank_account')} placeholder="Account number" />
              </FormField>
              <FormField label="IFSC Code">
                <input className={INPUT_CLS} value={form.bank_ifsc} onChange={set('bank_ifsc')} placeholder="XXXXXXXXXX" maxLength={11} style={{textTransform:'uppercase'}} />
              </FormField>
            </div>
          </section>

          {/* ── Emergency Contact ───────────────────────────────────────── */}
          <section>
            <SectionHeader icon="🆘" title="Emergency Contact" />
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Contact Name">
                <input className={INPUT_CLS} value={form.emergency_contact_name} onChange={set('emergency_contact_name')} placeholder="Full name" />
              </FormField>
              <FormField label="Contact Phone">
                <input className={INPUT_CLS} value={form.emergency_contact_phone} onChange={set('emergency_contact_phone')} placeholder="+91 XXXXX XXXXX" />
              </FormField>
            </div>
          </section>

          {/* ── Password Setup ────────────────────────────────────────────
          <section>
            <SectionHeader icon="🔐" title="Login Password" />
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Default Password" required error={err('password')}
                hint="Stored as bcrypt hash · Employee should change after first login">
                <div className="relative">
                  <input
                    type={showPwd ? 'text' : 'password'}
                    className={INPUT_CLS + ' pr-16'}
                    value={form.password}
                    onChange={set('password')}
                    placeholder="Min 6 characters"
                  />
                  <button type="button" onClick={() => setShowPwd((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-medium text-slate-400 hover:text-slate-600">
                    {showPwd ? 'Hide' : 'Show'}
                  </button>
                </div>
              </FormField>
              <div className="flex items-end pb-1">
                <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700 w-full">
                  <strong>Default:</strong> employee123<br/>
                  Employee can log in immediately after conversion.
                </div>
              </div>
            </div>
          </section> */}

        </div>{/* end scrollable */}

        {/* Footer */}
        <div className="mt-5 border-t border-slate-100 pt-4 flex items-center justify-between">
          
          <div className="flex gap-3">
            <button type="button" onClick={onClose}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
              Cancel
            </button>
            <button type="submit" disabled={loading || loadingDepts}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">
              {loading
                ? <><span className="animate-spin inline-block mr-1">⟳</span>Converting…</>
                : '✓ Convert to Employee'}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}


// ─── EmployeeCredentialsCard ─────────────────────────────────────────────────
// Shown inside the candidate detail view when status = CONVERTED | JOINED.
// Lets HR set the official email + password so the employee can log in.

// BASE_URL imported from config/api

function EmployeeCredentialsCard({ candidate, toast, onRefresh }) {
  const [officialEmail, setOfficialEmail] = React.useState(
    candidate.employee?.official_email || ''
  )
  const [password,  setPassword]  = React.useState('')
  const [showPwd,   setShowPwd]   = React.useState(false)
  const [saving,    setSaving]    = React.useState(false)
  const [credError, setCredError] = React.useState('')

  const employeeId  = candidate.employee?.id
  const isActivated = candidate.employee?.is_activated ?? false
  const officialSet = candidate.employee?.official_email

  const handleSave = async (e) => {
    e.preventDefault()
    if (!officialEmail.trim())  { setCredError('Official email is required.'); return }
    if (password.length < 6)    { setCredError('Password must be at least 6 characters.'); return }
    if (!employeeId)            { setCredError('Employee record not found. Re-convert the candidate first.'); return }
    setCredError('')
    setSaving(true)
    try {
      const { authHeaders } = await import('../../../config/auth')
      const res = await fetch(`${BASE_URL}/onboarding/activate/${employeeId}`, {
        method: 'PUT',
        // Backend gates /onboarding/* with `requires_role("admin","hr")`.
        // Without the bearer token the call returns 401.
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          official_email: officialEmail.trim().toLowerCase(),
          temp_password:  password,
        }),
      })
      const json = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(json.detail || json.message || `HTTP ${res.status}`)
      toast(`✅ Credentials saved. Welcome email sent to ${officialEmail.trim()}.`, 'success')
      setPassword('')
      onRefresh()
    } catch (err) {
      setCredError(err.message || 'Failed to save. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const INPUT = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100'

  return (
    <Card title="Employee Portal Credentials">
      {/* Activation status */}
      <div className="flex items-center gap-3 mb-4 rounded-lg px-3 py-2.5 border"
        style={{ background: isActivated ? '#f0fdf4' : '#fefce8', borderColor: isActivated ? '#bbf7d0' : '#fde68a' }}>
        <span className="text-lg">{isActivated ? '✅' : '⏳'}</span>
        <div>
          <p className="text-sm font-semibold" style={{ color: isActivated ? '#15803d' : '#92400e' }}>
            {isActivated ? 'Account Activated' : 'Pending Activation'}
          </p>
          <p className="text-xs" style={{ color: isActivated ? '#166534' : '#b45309' }}>
            {isActivated
              ? `Login: ${officialSet}`
              : 'Set official email and password below to activate the employee portal account'}
          </p>
        </div>
      </div>

      {credError && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
          {credError}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-4">
        {/* Official Email */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            Official Company Email <span className="text-red-500">*</span>
          </label>
          <input
            type="email"
            value={officialEmail}
            onChange={e => { setOfficialEmail(e.target.value); setCredError('') }}
            placeholder="firstname.lastname@company.com"
            className={INPUT}
          />
          <p className="mt-1 text-xs text-slate-400">Employee will use this email to log into the portal</p>
        </div>

        {/* Password */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            {isActivated ? 'New Password' : 'Temporary Password'}{' '}
            <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <input
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={e => { setPassword(e.target.value); setCredError('') }}
              placeholder="Min 6 characters"
              className={INPUT + ' pr-14'}
            />
            <button type="button" onClick={() => setShowPwd(s => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-slate-400 hover:text-slate-600">
              {showPwd ? 'Hide' : 'Show'}
            </button>
          </div>
          
        </div>

       

        <button type="submit" disabled={saving}
          className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors">
          {saving ? 'Saving…' : isActivated ? ' Update ' : ' Set Credentials & Send Welcome Email'}
        </button>
      </form>
    </Card>
  )
}


// ─── DocumentReviewPanel ──────────────────────────────────────────────────────
/**
 * HR Admin document review panel.
 *
 * Step 1 of the BGV workflow: HR reviews each required document and marks it
 * VERIFIED or REJECTED.  Only after all 6 required documents are VERIFIED
 * is the "Initiate BGV" button enabled (Step 2).
 *
 * Props:
 *   candidate   — normalized candidate object (has raw_documents)
 *   busy        — parent is busy (disables buttons)
 *   onVerify    — async (docId, approved, remarks) handler
 */
function DocumentReviewPanel({ candidate, busy, onVerify }) {
  // remarkDraft removed -- HR no longer enters per-doc remarks; verify() always sends null.
  const [verifying,   setVerifying]   = useState({}); // { [docId]: bool }

  // Build a lookup: doc_type → most-recent document object (any status).
  const docByType = {};
  for (const d of (candidate.raw_documents || [])) {
    // Keep the first (most-recent, since backend orders by uploaded_at desc).
    if (!docByType[d.doc_type]) docByType[d.doc_type] = d;
  }

  const handleVerify = async (doc, approved) => {
    setVerifying((p) => ({ ...p, [doc.id]: true }));
    try {
      await onVerify(doc.id, approved, null);
    } finally {
      setVerifying((p) => ({ ...p, [doc.id]: false }));
    }
  };

  const allVerified = candidate.all_required_docs_verified;

  return (
    <Card title="Document Review (Step 1 — HR)">
      {/* Summary banner */}
      {allVerified ? (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          <span className="text-base">✅</span>
          <span>All required documents verified. HR can now initiate BGV below.</span>
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          <span className="text-base">⚠</span>
          <span>Verify all required documents before BGV can be initiated.</span>
        </div>
      )}

      <div className="divide-y divide-slate-100">
        {[...BGV_REQUIRED_DOC_TYPES].map((docType) => {
          const doc       = docByType[docType];
          const label     = BGV_DOC_LABELS[docType] || docType;
          const isVerified = doc?.status === 'VERIFIED';
          const isRejected = doc?.status === 'REJECTED';
          const isUploaded = doc?.status === 'UPLOADED';
          const isBusyDoc  = verifying[doc?.id] || false;

          return (
            <div key={docType} className="py-3">
              <div className="flex items-start gap-3">
                {/* Status dot */}
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold
                    ${isVerified ? 'bg-green-100 text-green-700'
                    : isRejected ? 'bg-red-100 text-red-700'
                    : isUploaded ? 'bg-blue-100 text-blue-700'
                    : 'bg-slate-100 text-slate-400'}`}
                >
                  {isVerified ? '✓' : isRejected ? '✗' : isUploaded ? '!' : '—'}
                </span>

                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-800">{label}</p>
                    {/* Status badge */}
                    {isVerified && (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700">Verified</span>
                    )}
                    {isRejected && (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">Rejected</span>
                    )}
                    {isUploaded && (
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">Awaiting Review</span>
                    )}
                    {!doc && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">Not Uploaded</span>
                    )}
                  </div>

                  {doc && (
                    <p className="mt-0.5 text-xs text-slate-400 truncate">
                      {doc.original_filename}
                      {doc.file_url && (
                        <a
                          href={`${BASE_URL}${doc.file_url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700 hover:bg-blue-100 align-middle"
                        >
                          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3" aria-hidden>
                            <path fillRule="evenodd" d="M10 4.5a5.5 5.5 0 014.879 2.965A.75.75 0 0114.121 8.5H5.879a.75.75 0 01-.758-1.035A5.5 5.5 0 0110 4.5zm0 11A5.5 5.5 0 015.121 12.535.75.75 0 015.879 11.5h8.242a.75.75 0 01.758 1.035A5.5 5.5 0 0110 15.5zM10 7a3 3 0 100 6 3 3 0 000-6z" clipRule="evenodd"/>
                          </svg>
                          View
                        </a>
                      )}
                      {doc.verified_at && (
                        <span className="ml-2 text-slate-300">
                          · {isVerified ? 'Verified' : 'Reviewed'}: {new Date(doc.verified_at).toLocaleDateString()}
                        </span>
                      )}
                    </p>
                  )}

                  {doc?.remarks && !isUploaded && (
                    <p className="mt-0.5 text-xs text-slate-500 italic">Remarks: "{doc.remarks}"</p>
                  )}

                  {/* Approve / Reject — only for uploaded (pending review) docs */}
                  {isUploaded && (
                    <div className="mt-2">
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={busy || isBusyDoc}
                          onClick={() => handleVerify(doc, true)}
                          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
                        >
                          {isBusyDoc ? '…' : '✓'} Approve
                        </button>
                        <button
                          type="button"
                          disabled={busy || isBusyDoc}
                          onClick={() => handleVerify(doc, false)}
                          className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                        >
                          {isBusyDoc ? '…' : '✗'} Reject
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Re-review button for already-verified or rejected docs */}
                  {(isVerified || isRejected) && (
                    <div className="mt-2 flex gap-2">
                      {isRejected && (
                        <button
                          type="button"
                          disabled={busy || isBusyDoc}
                          onClick={() => handleVerify(doc, true)}
                          className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 disabled:opacity-60"
                        >
                          {isBusyDoc ? '…' : '✓ Approve instead'}
                        </button>
                      )}
                      {isVerified && (
                        <button
                          type="button"
                          disabled={busy || isBusyDoc}
                          onClick={() => handleVerify(doc, false)}
                          className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-500 hover:bg-slate-100 disabled:opacity-60"
                        >
                          {isBusyDoc ? '…' : '✗ Reject instead'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}


// ─── CandidateDetail ─────────────────────────────────────────────────────────

function CandidateDetail({ candidateId, onBack, toast }) {
  const [candidate, setCandidate] = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [modal,     setModal]     = useState(null);  // 'offer' | 'convert'
  const [busy,      setBusy]      = useState(false);

  // ── Fetch full detail from backend ──
  // When the candidate has been converted, the backend already embeds the
  // linked Employee record (via resolved_employee_code / resolved_manager_name).
  // We call getCandidate once — no extra round-trip needed.
  const refreshCandidate = useCallback(async () => {
    try {
      const raw = await getCandidate(candidateId);
      const normalized = normalizeCandidate(raw);

      // If we got a linked employee but the employee_code is still missing,
      // fall back to fetching the employee record directly using employee.id.
      if (
        raw.employee?.id &&
        !normalized.employee_code
      ) {
        try {
          const emp = await getEmployeeDetails(raw.employee.id);
          normalized.employee_code = emp.employee_code || normalized.employee_code;
          if (!normalized.manager && emp.reporting_manager_id) {
            // manager name wasn't resolved — use id as fallback label
            normalized.manager = `Manager #${emp.reporting_manager_id}`;
          }
        } catch (_) {
          // non-critical — display what we have
        }
      }

      setCandidate(normalized);
    } catch (err) {
      toast(err.message, 'error');
    }
  }, [candidateId, toast]);

  useEffect(() => {
    setLoading(true);
    refreshCandidate().finally(() => setLoading(false));
  }, [refreshCandidate]);

  // ── Accept offer (quick action from detail) ──
  const handleAcceptOffer = async () => {
    setBusy(true);
    try {
      await acceptOffer(candidate.id);
      toast('Offer accepted!', 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Activate account — uses OnboardedEmployee.id ──
  const handleActivate = async () => {
    const empId = candidate.onboarded_employee?.id;
    if (!empId) { toast('No employee record found.', 'error'); return; }
    setBusy(true);
    try {
      await activateEmployee(empId);
      toast('Employee account activated!', 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Mark joined — uses OnboardedEmployee.id ──
  const handleMarkJoined = async () => {
    const empId = candidate.onboarded_employee?.id;
    if (!empId) { toast('No employee record found.', 'error'); return; }
    setBusy(true);
    try {
      await markJoined(empId);
      toast('Marked as joined!', 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Mark not joined ─────────────────────────────────────────────────────────
  // Uses candidate.id — works regardless of whether an OnboardedEmployee or
  // Employee row exists. The backend handles both cases and does NOT error
  // if neither record is present.
  const handleMarkNotJoined = async () => {
    setBusy(true);
    try {
      await markCandidateNotJoined(candidate.id);
      toast('Candidate marked as Did Not Join.', 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message || 'Could not update status.', 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Verify / Reject a document (HR Admin — Step 1 of BGV workflow) ─────────
  // Called by DocumentReviewPanel.  After each verify/reject we refresh the
  // candidate so the BGV button gate (all_required_docs_verified) updates.
  const handleVerifyDoc = async (docId, approved, remarks) => {
    try {
      await verifyDocument(docId, approved, remarks);
      const action = approved ? 'verified ✓' : 'rejected ✗';
      toast(`Document ${action}`, approved ? 'success' : 'error');
      await refreshCandidate();
    } catch (err) {
      toast(err.message || 'Could not update document status.', 'error');
    }
  };

  // ── Initiate BGV (HR Admin — Step 2, only after docs verified) ─────────────
  // Backend enforces:
  //   1. requires_role("admin","hr")  — candidates cannot call this.
  //   2. All required documents must be VERIFIED — returns 409 if not.
  //   3. BGV cannot be initiated twice — returns 409 if already started.
  const handleInitiateBgv = async () => {
    setBusy(true);
    try {
      const result = await initiateBgv(candidate.id);
      // Guard expires_at — if missing or unparseable, fall back to a generic message
      // instead of rendering "Invalid Date" in the success toast.
      const expiry = result?.expires_at ? new Date(result.expires_at) : null;
      const expiryStr = expiry && !Number.isNaN(expiry.getTime())
        ? `Expires: ${expiry.toLocaleDateString()}`
        : 'Vendor link sent.';
      toast(`✅ BGV initiated! ${expiryStr}`, 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message || 'Could not initiate BGV.', 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Update BGV status (admin override) ──
  const handleUpdateBgv = async (newStatus) => {
    setBusy(true);
    try {
      const result = await updateBgvStatus(candidate.id, newStatus);
      // The earlier `if (!result && result !== 0)` was dead code — for object
      // responses it can never be true. Use a real null/undefined check.
      if (result == null) {
        throw new Error('No response from server — check backend logs.');
      }
      const cfg = BGV_STATUS_CONFIG[newStatus];
      const label = cfg ? cfg.label : newStatus;
      toast(`BGV status updated to "${label}"`, 'success');
      await refreshCandidate();
    } catch (err) {
      toast(err.message || 'Failed to update BGV status.', 'error');
    } finally {
      setBusy(false);
    }
  };

  // ── Loading state ──
  if (loading || !candidate) {
    return (
      <div className="flex items-center justify-center py-32">
        <span className="text-sm text-slate-400 animate-pulse">Loading candidate…</span>
      </div>
    );
  }

  // ── Button visibility logic (based on actual backend status) ──
  const status      = candidate.status;
  const empStatus   = candidate.onboarded_employee?.status;

  const showOffer     = !['CONVERTED','JOINED','NOT_JOINED'].includes(status);
  const showAccept    = status === 'OFFER_SENT';
  const canConvert    = ['OFFER_ACCEPTED','DOCS_PENDING','DOCS_SUBMITTED',
                         'BGV_IN_PROGRESS','BGV_CLEAR','BGV_FAILED'].includes(status);
  const canActivate   = status === 'CONVERTED' && empStatus === 'INACTIVE';
  const canMarkJoined    = status === 'CONVERTED' && empStatus === 'ACTIVE';
  const canMarkNoJoin    = ['CONVERTED','OFFER_ACCEPTED','OFFER_SENT'].includes(status)
                           || (status === 'CONVERTED' && empStatus === 'ACTIVE');

  // Offer already generated/sent flags
  const offerSent     = ['OFFER_SENT','OFFER_ACCEPTED','DOCS_PENDING','DOCS_SUBMITTED',
                          'BGV_IN_PROGRESS','BGV_CLEAR','BGV_FAILED','CONVERTED','JOINED'].includes(status);
  const offerAccepted = ['OFFER_ACCEPTED','DOCS_PENDING','DOCS_SUBMITTED',
                          'BGV_IN_PROGRESS','BGV_CLEAR','BGV_FAILED','CONVERTED','JOINED'].includes(status);

  return (
    <div className="space-y-6">
      {/* Back */}
      <button onClick={onBack}
        className="flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
        <Icon name="chevronLeft" className="h-4 w-4" /> Back to Candidates
      </button>

      {/* Header row */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-4">
          <Avatar name={candidate.name} color={candidate.color} size={14} />
          <div>
            <h2 className="text-xl font-bold text-slate-900">{candidate.name}</h2>
            <p className="text-sm text-slate-500">{candidate.role} · {candidate.department}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge status={status} />
              {/* <BgvBadge status={candidate.bgv_status} /> */}
              {candidate.candidate_ref && (
                <span className="text-xs text-slate-400 font-mono">{candidate.candidate_ref}</span>
              )}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          {showOffer && (
            <button onClick={() => setModal('offer')}
              className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100">
              <Icon name="doc" className="h-4 w-4" /> Offer Letter
            </button>
          )}
          {showAccept && (
            <button onClick={handleAcceptOffer} disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-60">
              <Icon name="approve" className="h-4 w-4" /> Accept Offer
            </button>
          )}
          {canConvert && (
            <button onClick={() => setModal('convert')}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700">
              <Icon name="users" className="h-4 w-4" /> Convert to Employee
            </button>
          )}
          {canActivate && (
            <button onClick={handleActivate} disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
              <Icon name="approve" className="h-4 w-4" /> {busy ? 'Activating…' : 'Activate Account'}
            </button>
          )}
          {canMarkJoined && (
            <button onClick={handleMarkJoined} disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">
              <Icon name="approve" className="h-4 w-4" /> Mark Joined
            </button>
          )}
          {canMarkNoJoin && (
            <button onClick={handleMarkNotJoined} disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-100 disabled:opacity-60">
              <Icon name="reject" className="h-4 w-4" /> Mark Not Joined
            </button>
          )}
        </div>
      </div>

      {/* 3-column content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left: info + timeline */}
        <div className="space-y-6 lg:col-span-1">
          <Card title="Basic Information">
            <div className="space-y-3 text-sm">
              {[
                { label: 'Email',        value: candidate.email },
                { label: 'Phone',        value: candidate.phone || '—' },
                { label: 'Department',   value: candidate.department || '—' },
                { label: 'CTC (Annual)', value: candidate.ctc || '—' },
                { label: 'Joining Date', value: candidate.joining_date || 'TBD' },
                { label: 'Manager',      value: candidate.manager || '— Not assigned —' },
                { label: 'Emp. Code',    value: candidate.employee_code || candidate.onboarded_employee?.employee_code || '—' },
                { label: 'Created',      value: candidate.created_at },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between gap-2">
                  <span className="text-slate-400 shrink-0">{label}</span>
                  <span className="text-right font-medium text-slate-700 break-all">{value}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Onboarding Progress">
            <StatusTimeline currentStatus={status} bgvStatus={candidate.bgv_status} />
          </Card>
        </div>

        {/* Right: offer + docs + bgv */}
        <div className="space-y-6 lg:col-span-2">

          {/* Offer status cards */}
          <Card title="Offer Status">
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Generated', ok: !!candidate.offer_url || !['CREATED'].includes(status) && status !== 'CREATED' },
                { label: 'Sent',      ok: offerSent },
                { label: 'Accepted',  ok: offerAccepted },
              ].map(({ label, ok }) => (
                <div key={label}
                  className={`rounded-xl border p-4 text-center ${ok ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'}`}>
                  <p className={`text-2xl font-bold ${ok ? 'text-emerald-600' : 'text-slate-300'}`}>{ok ? '✓' : '—'}</p>
                  <p className="mt-1 text-xs font-medium text-slate-500">{label}</p>
                </div>
              ))}
            </div>
          </Card>

          {/* Document Review — Step 1 (shown once offer is accepted) */}
          {offerAccepted && (
            <DocumentReviewPanel
              candidate={candidate}
              busy={busy}
              onVerify={handleVerifyDoc}
            />
          )}

          {/* BGV */}
          <Card title="Background Verification (BGV — Step 2)">
            {/* Status row */}
            <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
              <div>
                <p className="mb-2 text-sm text-slate-500">Current BGV Status</p>
                <BgvBadge status={candidate.bgv_status} />
                {candidate.bgv_check?.vendor_name && (
                  <p className="mt-1 text-xs text-slate-400">Vendor: {candidate.bgv_check.vendor_name}</p>
                )}
                {candidate.bgv_check?.initiated_at && (
                  <p className="mt-0.5 text-xs text-slate-400">
                    Initiated: {new Date(candidate.bgv_check.initiated_at).toLocaleDateString()}
                  </p>
                )}
                {candidate.bgv_check?.completed_at && (
                  <p className="mt-0.5 text-xs text-slate-400">
                    Completed: {new Date(candidate.bgv_check.completed_at).toLocaleDateString()}
                  </p>
                )}
                {candidate.bgv_check?.remarks && (
                  <p className="mt-1 text-xs text-slate-500 italic">"{candidate.bgv_check.remarks}"</p>
                )}
              </div>

              {/* ── BGV Initiation Gate ──────────────────────────────────────────
                  RULE: HR Admin can initiate BGV ONLY after ALL required
                  documents are VERIFIED (document_status = VERIFIED).
                  The backend enforces this with assert_documents_verified()
                  and requires_role("admin","hr"). The UI mirrors both checks.
              ────────────────────────────────────────────────────────────────── */}
              {candidate.bgv_status === 'NOT_STARTED' && (
                <div className="flex flex-col items-end gap-2">
                  {candidate.all_required_docs_verified ? (
                    /* All docs verified → button enabled */
                    <button
                      type="button"
                      disabled={busy}
                      onClick={handleInitiateBgv}
                      className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition"
                    >
                      🔍 Initiate BGV &amp; Send Vendor Link
                    </button>
                  ) : (
                    /* Docs not fully verified → button disabled + explanation */
                    <>
                      <button
                        type="button"
                        disabled
                        title="Verify all required documents first"
                        className="flex items-center gap-2 rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-400 cursor-not-allowed"
                      >
                        🔍 Initiate BGV &amp; Send Vendor Link
                      </button>
                      <p className="text-xs text-amber-700 text-right max-w-xs">
                        ⚠ All required documents must be verified (Step 1) before BGV can be initiated.
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Admin status override (manual control) */}
            {candidate.bgv_status !== 'NOT_STARTED' && (
              <div>
                <p className="mb-2 text-xs text-slate-400">Admin override — update BGV status manually</p>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(BGV_STATUS_CONFIG).filter(([k]) => k !== 'PENDING' && k !== 'NOT_STARTED').map(([key, cfg]) => {
                    const isActive = candidate.bgv_status === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        disabled={busy || isActive}
                        onClick={() => handleUpdateBgv(key)}
                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold text-left transition
                          ${isActive
                            ? cfg.color + ' ring-2 ring-blue-300 ring-offset-1 cursor-default'
                            : 'bg-slate-50 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed'
                          }`}
                      >
                        {cfg.icon} {cfg.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {status === 'BGV_FAILED' && (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                ⚠ BGV failed. You can still convert the candidate — HR override is allowed.
              </div>
            )}
            {status === 'BGV_CLEAR' && (
              <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                ✅ BGV cleared. Candidate is eligible for conversion to employee.
              </div>
            )}
          </Card>

          {/* Employee Portal Credentials — shown only after conversion */}
          {['CONVERTED', 'JOINED'].includes(status) && candidate.employee_id && (
            <EmployeeCredentialsCard
              candidate={candidate}
              toast={toast}
              onRefresh={refreshCandidate}
            />
          )}

        </div>
      </div>

      {/* Modals */}
      {modal === 'offer' && (
        <OfferLetterModal
          candidate={candidate}
          onClose={() => setModal(null)}
          onRefresh={refreshCandidate}
          toast={toast}
        />
      )}
      {modal === 'convert' && (
        <ConvertToEmployeeModal
          candidate={candidate}
          onClose={() => setModal(null)}
          onRefresh={refreshCandidate}
          toast={toast}
        />
      )}
    </div>
  );
}

// ─── CandidateList ────────────────────────────────────────────────────────────

function CandidateList({ candidates, loading, onSelect, onAdd }) {
  const [search,       setSearch]       = useState('');
  const [filterStatus, setFilterStatus] = useState('ALL');

  const filtered = candidates.filter((c) => {
    const matchSearch = c.name.toLowerCase().includes(search.toLowerCase()) ||
                        c.email.toLowerCase().includes(search.toLowerCase()) ||
                        c.role.toLowerCase().includes(search.toLowerCase());
    const matchStatus = filterStatus === 'ALL' || c.status === filterStatus;
    return matchSearch && matchStatus;
  });

  const stats = [
    { label: 'Total',        value: candidates.length,                                                     color: 'text-slate-700',   bg: 'bg-slate-50'   },
    { label: 'Offer Sent',   value: candidates.filter((c) => c.status === 'OFFER_SENT').length,            color: 'text-blue-700',    bg: 'bg-blue-50'    },
    { label: 'Accepted',     value: candidates.filter((c) => c.status === 'OFFER_ACCEPTED').length,        color: 'text-green-700',   bg: 'bg-green-50'   },
    { label: 'Converted',    value: candidates.filter((c) => ['CONVERTED','JOINED'].includes(c.status)).length, color: 'text-indigo-700',  bg: 'bg-indigo-50'  },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Candidate Onboarding"
        subtitle="End-to-end workflow: offer → documents → BGV → employee activation"
        right={
          <button onClick={onAdd}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700">
            <Icon name="plus" className="h-4 w-4" /> Add Candidate
          </button>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className={`rounded-2xl border border-slate-200 ${s.bg} px-5 py-4 shadow-sm`}>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="mt-1 text-xs font-medium text-slate-500">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <Card padding="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-48">
            <Icon name="search" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input type="text" placeholder="Search by name, email or role…"
              value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100" />
          </div>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500">
            <option value="ALL">All Status</option>
            {Object.entries(CANDIDATE_STATUSES).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          <span className="ml-auto text-xs text-slate-400">
            {filtered.length} record{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </Card>

      {/* Table */}
      <Card padding="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {['Candidate', 'Role', 'Department', 'Joining Date', 'Status', 'Actions'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-sm text-slate-400 animate-pulse">
                    Loading candidates from backend…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-sm text-slate-400">
                    {candidates.length === 0
                      ? 'No candidates yet. Click "Add Candidate" to get started.'
                      : 'No candidates match your search.'}
                  </td>
                </tr>
              ) : (
                filtered.map((c) => {
                  // Rename BGV_CLEAR's label to "BGV" only in this table — keep
                  // the existing badge colour + global CANDIDATE_STATUSES label
                  // (used elsewhere) untouched.
                  const statusCfg = getStatusConfig(c.status);
                  const statusLabel = c.status === 'BGV_CLEAR' ? 'BGV' : statusCfg.label;
                  return (
                  <tr key={c.id} className="border-b border-slate-50 transition hover:bg-blue-50/40">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <Avatar name={c.name} color={c.color} size={9} />
                        <div>
                          <p className="font-semibold text-slate-900 text-sm">{c.name}</p>
                          <p className="text-xs text-slate-400">{c.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">{c.role}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                        {c.department || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">{c.joining_date || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusCfg.color}`}>
                        {statusLabel}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => onSelect(c)}
                        className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-blue-400 hover:text-blue-700">
                        View <Icon name="chevronRight" className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ─── Root Onboarding component ────────────────────────────────────────────────

export default function Onboarding() {
  const { toasts, add: addToast, remove: removeToast } = useToast();

  const [view,        setView]        = useState('list');     // 'list' | 'detail'
  const [selectedId,  setSelectedId]  = useState(null);       // candidate DB id
  const [candidates,  setCandidates]  = useState([]);         // normalised list
  const [listLoading, setListLoading] = useState(true);
  const [listError,   setListError]   = useState('');
  const [showCreate,  setShowCreate]  = useState(false);

  // ── Load candidate list ──
  const loadCandidates = useCallback(async () => {
    setListLoading(true);
    setListError('');
    try {
      const rawList = await getCandidates();
      // rawList is an array (envelope unwrapped by onboardingApi.js)
      const list = Array.isArray(rawList) ? rawList : [];
      setCandidates(list.map(normalizeCandidate));
    } catch (err) {
      setListError(err.message);
      addToast(err.message, 'error');
    } finally {
      setListLoading(false);
    }
  }, [addToast]);

  useEffect(() => { loadCandidates(); }, [loadCandidates]);

  // ── Handlers ──
  const handleSelect              = (c) => { setSelectedId(c.id); setView('detail'); };
  const handleBack                = () => { setSelectedId(null); setView('list'); loadCandidates(); };
  const handleCreated = (c) => {
    setCandidates((prev) => [c, ...prev]);
    setShowCreate(false);
    addToast(`${c.name} added successfully!`, 'success');
  };

  return (
    <div>
      {listError && view === 'list' && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <span>⚠ {listError}</span>
          <button onClick={loadCandidates} className="ml-4 font-semibold underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {view === 'list' && (
        <CandidateList
          candidates={candidates}
          loading={listLoading}
          onSelect={handleSelect}
          onAdd={() => setShowCreate(true)}
        />
      )}

      {view === 'detail' && selectedId && (
        <CandidateDetail
          candidateId={selectedId}
          onBack={handleBack}
          toast={addToast}
        />
      )}

      {showCreate && (
        <CreateCandidateModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}

      <Toast toasts={toasts} onRemove={removeToast} />
    </div>
  );
}
