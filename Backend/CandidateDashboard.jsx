import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  getCandidateStatus,
  uploadCandidateDocument,
  deleteCandidateDocument,
  resolveCandidateByEmail,
  submitCandidateDocuments,
} from '../../services/candidateApi';
// NOTE: initiateBgv is intentionally NOT imported here.
// Per the BGV workflow, only HR Admin can trigger BGV — candidates have
// a read-only view of their BGV status. The backend enforces this with
// requires_role("admin", "hr") on POST /api/v1/bgv/initiate.

// Mandatory = must be uploaded before BGV can start
// Optional  = can be uploaded but are not required
const REQUIRED_DOCS = [
  { id: 'bgv_form',      label: 'Updated BGV Form',             optional: false },
  { id: 'aadhar',        label: 'Aadhaar Card',                 optional: false },
  { id: 'pan',           label: 'PAN Card',                     optional: false },
  { id: 'qualification', label: 'Highest Qualification',        optional: false },
  { id: 'exp1',          label: 'Experience Letter 1',          optional: true  },
  { id: 'exp2',          label: 'Experience Letter 2',          optional: true  },
  { id: 'exp3',          label: 'Experience Letter 3',          optional: true  },
  { id: 'address_proof', label: 'Address Proof',                optional: false },
  { id: 'cif',           label: 'CIF Document (Mandatory)',     optional: false },
];
const MANDATORY_DOC_IDS = new Set(REQUIRED_DOCS.filter((d) => !d.optional).map((d) => d.id));

const MAX_FILE_SIZE  = 10 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png']);
const ACCEPTED_EXTS  = new Set(['pdf', 'jpg', 'jpeg', 'png']);

const BGV_LABELS = {
  PENDING:     'Pending',
  IN_PROGRESS: 'In Progress',
  CLEAR:       'BGV Cleared',
  ON_HOLD:     'BGV On Hold',
  FAILED:      'BGV Rejected',
  REVIEW:      'Under Review',
};

function Toast({ toasts }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`rounded-lg px-4 py-3 text-sm font-medium shadow-lg ${
            toast.type === 'error' ? 'bg-red-600 text-white' : 'bg-emerald-600 text-white'
          }`}
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}

function isValidFile(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  return (ACCEPTED_TYPES.has(file.type) || ACCEPTED_EXTS.has(ext)) && file.size <= MAX_FILE_SIZE;
}

function SpinnerIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5">
      <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35l.815-8.15h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5a.75.75 0 0 1 .786-.711Z" clipRule="evenodd" />
    </svg>
  );
}

function DocumentUploadSection({ uploadedDocTypes, uploadingType, onUpload, onDeleteRequest, deletingType, locked = false }) {
  const [selectedType, setSelectedType] = useState(REQUIRED_DOCS[0].id);
  const fileInputRef = useRef(null);

  const isUploading          = uploadingType !== null;
  const isDeleting           = deletingType  !== null;
  const isBusy               = isUploading || isDeleting || locked;

  // Locked banner shown above the grid when BGV is in progress
  if (locked) {
    return (
      <section className="overflow-hidden rounded-lg border border-slate-100 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
          <h2 className="text-lg font-semibold text-slate-950">Document Upload</h2>
        </div>
        <div className="px-5 py-5 sm:px-6">
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center gap-2">
            <span>🔒</span>
            <span>Document uploads are <strong>locked</strong> — BGV has been initiated. Contact HR if you need to make changes.</span>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {REQUIRED_DOCS.map((doc) => {
              const uploaded = uploadedDocTypes.includes(doc.id);
              return (
                <div key={doc.id} className={`flex min-h-14 items-center rounded-lg border px-4 gap-3 ${uploaded ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'}`}>
                  <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${uploaded ? 'border-emerald-500 bg-emerald-500' : 'border-slate-300'}`}>
                    {uploaded ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                  </span>
                  <span className="text-sm text-slate-600 flex-1">{doc.label}</span>
                  {doc.optional && <span className="text-[10px] text-slate-400">optional</span>}
                </div>
              );
            })}
          </div>
        </div>
      </section>
    );
  }
  const selectedDoc          = REQUIRED_DOCS.find((doc) => doc.id === selectedType);
  const isSelectedUploaded   = uploadedDocTypes.includes(selectedType);

  const handleFiles = (files) => {
    if (isBusy || !selectedType || !files?.length) return;
    onUpload(selectedType, Array.from(files));
  };

  return (
    <section className="overflow-hidden rounded-lg border border-slate-100 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <h2 className="text-lg font-semibold text-slate-950">Document Upload</h2>
      </div>

      <div className="space-y-4 px-5 py-5 sm:px-6">
        {/* ── Document type grid ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {REQUIRED_DOCS.map((doc) => {
            const uploaded           = uploadedDocTypes.includes(doc.id);
            const selected           = selectedType === doc.id;
            const isThisUploading    = uploadingType === doc.id;
            const isThisDeleting     = deletingType  === doc.id;

            return (
              /*
               * Outer div — holds the border / bg / ring styling.
               * Can't nest <button> inside <button>, so the selection
               * target and the trash icon are separate inner buttons.
               */
              <div
                key={doc.id}
                className={`flex min-h-14 items-center rounded-lg border text-base transition ${
                  selected
                    ? 'border-blue-400 bg-blue-50 text-slate-700 ring-2 ring-blue-100'
                    : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300'
                } ${isBusy ? 'opacity-60' : ''}`}
              >
                {/* Selection button — left / main area */}
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => setSelectedType(doc.id)}
                  className="flex flex-1 items-center gap-3 self-stretch px-4 text-left"
                >
                  {/* Uploaded indicator dot */}
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                      uploaded
                        ? 'border-emerald-500 bg-emerald-500'
                        : selected
                          ? 'border-blue-500'
                          : 'border-slate-400'
                    }`}
                  >
                    {uploaded ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                  </span>

                  <span className="flex-1 truncate text-sm">{doc.label}</span>
                  {doc.optional && (
                    <span className="shrink-0 text-[10px] text-slate-400 italic">optional</span>
                  )}

                  {isThisUploading && (
                    <SpinnerIcon className="h-4 w-4 animate-spin text-blue-500" />
                  )}
                </button>

                {/* Trash icon button — only for uploaded docs */}
                {uploaded && !isThisUploading && (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => onDeleteRequest(doc.id)}
                    title="Remove document"
                    className="mr-2 shrink-0 rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 disabled:pointer-events-none"
                  >
                    {isThisDeleting
                      ? <SpinnerIcon className="h-3.5 w-3.5 animate-spin text-slate-400" />
                      : <TrashIcon />
                    }
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Drop zone ──────────────────────────────────────────────────── */}
        <div
          role="button"
          tabIndex={isBusy ? -1 : 0}
          onClick={() => { if (!isBusy) fileInputRef.current?.click(); }}
          onKeyDown={(event) => {
            if (!isBusy && (event.key === 'Enter' || event.key === ' ')) fileInputRef.current?.click();
          }}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            handleFiles(event.dataTransfer.files);
          }}
          className={`flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-4 py-10 text-center transition ${
            isBusy
              ? 'cursor-not-allowed border-blue-200 bg-blue-50/60'
              : 'cursor-pointer border-slate-200 bg-slate-50 hover:border-blue-300 hover:bg-blue-50/40'
          }`}
        >
          {uploadingType === selectedType ? (
            <>
              <SpinnerIcon className="h-9 w-9 animate-spin text-blue-500" />
              <p className="text-lg font-medium text-blue-700">
                Uploading {selectedDoc?.label}…
              </p>
              <p className="text-sm text-blue-400">Please wait</p>
            </>
          ) : isUploading ? (
            <>
              <svg className="h-9 w-9 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2h7.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" />
              </svg>
              <p className="text-lg font-medium text-slate-400">Upload in progress…</p>
              <p className="text-sm text-slate-300">Please wait until the current upload finishes</p>
            </>
          ) : (
            <>
              <svg className="h-9 w-9 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2h7.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" />
              </svg>
              <p className="text-lg font-medium text-slate-700">
                Drop files here or click to browse
              </p>
              <p className="text-sm text-slate-400">PDF, JPG, PNG accepted &middot; max 10 MB each</p>
              {selectedDoc && (
                <p className="text-xs font-medium text-blue-600">
                  {isSelectedUploaded
                    ? `Replace: ${selectedDoc.label}`
                    : `Selected: ${selectedDoc.label}`}
                </p>
              )}
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.jpg,.jpeg,.png"
            disabled={isBusy}
            onChange={(event) => {
              handleFiles(event.target.files);
              event.target.value = '';
            }}
          />
        </div>
      </div>
    </section>
  );
}

export default function CandidateDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [candidateId,       setCandidateId]       = useState(user?.candidateId ?? null);
  const [status,            setStatus]            = useState(null);
  const [loading,           setLoading]           = useState(true);
  const [uploadingType,     setUploadingType]     = useState(null);
  const [deletingType,      setDeletingType]      = useState(null);
  const [confirmDeleteType, setConfirmDeleteType] = useState(null);
  const [submitting,        setSubmitting]        = useState(false);
  // bgvBusy intentionally removed — candidates cannot initiate BGV.
  // HR Admin triggers BGV via the admin Onboarding panel after document verification.
  const [toasts,            setToasts]            = useState([]);

  const addToast = useCallback((message, type = 'success') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  useEffect(() => {
    if (candidateId || !user?.email) return;
    resolveCandidateByEmail(user.email)
      .then((data) => setCandidateId(data.candidate_id))
      .catch(() => addToast('Could not find your onboarding record. Contact HR.', 'error'));
  }, [candidateId, user?.email, addToast]);

  const loadStatus = useCallback(async () => {
    if (!candidateId) { setLoading(false); return; }
    setLoading(true);
    try {
      const data = await getCandidateStatus(candidateId);
      setStatus(data);
    } catch (err) {
      // If the stored candidateId is stale (404), re-resolve by email and retry once.
      if (err.message?.includes('not found') || err.message?.includes('404')) {
        try {
          if (user?.email) {
            const resolved = await resolveCandidateByEmail(user.email);
            if (resolved?.candidate_id && resolved.candidate_id !== candidateId) {
              setCandidateId(resolved.candidate_id);
              // loadStatus will re-run when candidateId state updates
              return;
            }
          }
        } catch (_) { /* ignore resolution failure */ }
      }
      addToast('Could not load your onboarding status. Please refresh or contact HR.', 'error');
    } finally {
      setLoading(false);
    }
  }, [candidateId, user?.email, addToast]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleUpload = useCallback(async (documentType, files) => {
    if (!candidateId) {
      addToast('Your onboarding record is not loaded yet. Please refresh.', 'error');
      return;
    }
    const invalid = files.find((f) => !isValidFile(f));
    if (invalid) {
      addToast('Upload PDF, JPG, JPEG, or PNG files up to 10 MB each.', 'error');
      return;
    }
    setUploadingType(documentType);
    try {
      await uploadCandidateDocument(candidateId, documentType, files);
      addToast('Document uploaded successfully.');
      await loadStatus();
    } catch (err) {
      addToast(err.message, 'error');
    } finally {
      setUploadingType(null);
    }
  }, [candidateId, loadStatus, addToast]);

  const handleDeleteRequest = useCallback((docType) => {
    setConfirmDeleteType(docType);
  }, []);

  const handleDeleteCancel = useCallback(() => {
    setConfirmDeleteType(null);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    const docType = confirmDeleteType;
    setConfirmDeleteType(null);
    setDeletingType(docType);
    try {
      await deleteCandidateDocument(candidateId, docType);
      addToast('Document removed successfully.');
      await loadStatus();
    } catch (err) {
      addToast(err.message, 'error');
    } finally {
      setDeletingType(null);
    }
  }, [confirmDeleteType, candidateId, loadStatus, addToast]);

  const handleSubmit = useCallback(async () => {
    if (!candidateId) {
      addToast('Your onboarding record is not loaded yet. Please refresh.', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const result = await submitCandidateDocuments(candidateId);
      if (result?.already_submitted) {
        addToast('Your documents have already been submitted.');
      } else {
        addToast('Documents submitted! HR will review and notify you.');
      }
      await loadStatus();
    } catch (err) {
      addToast(err.message || 'Could not submit. Please try again.', 'error');
    } finally {
      setSubmitting(false);
    }
  }, [candidateId, loadStatus, addToast]);

  // handleInitiateBgv intentionally removed — candidates cannot initiate BGV.
  // The backend enforces requires_role("admin","hr") on POST /api/v1/bgv/initiate.
  // HR Admin uses the Onboarding panel to verify documents and then initiate BGV.

  const uploadedDocTypes = status?.uploaded_doc_types ?? [];
  const uploadedCount    = status?.document_count ?? status?.docs_uploaded_count ?? 0;
  const totalRequired    = status?.total_required_documents ?? REQUIRED_DOCS.length;
  // BGV can be initiated when all MANDATORY docs are uploaded
  const allMandatoryUploaded = MANDATORY_DOC_IDS.size > 0 &&
    [...MANDATORY_DOC_IDS].every((id) => uploadedDocTypes.includes(id));
  const allDocsUploaded  = allMandatoryUploaded;

  // Lock uploads once BGV is in progress or beyond
  const BGV_LOCKED_STATUSES = new Set(['BGV_IN_PROGRESS','BGV_CLEAR','BGV_FAILED','BGV_ON_HOLD','CONVERTED','JOINED']);
  const bgvLocked        = BGV_LOCKED_STATUSES.has(status?.status ?? '');
  // Guard: never show a real BGV status for candidates who haven't accepted the offer.
  // The backend already guards this, but apply it on the frontend too as defence-in-depth.
  const _earlyPipelineStatuses = new Set(['CREATED','OFFER_GENERATED','OFFER_SENT','OFFER_REJECTED','DOCS_PENDING','DOCS_SUBMITTED']);
  const bgvStatus        = (_earlyPipelineStatuses.has(status?.status ?? '') ? null : status?.bgv_status) || null;
  const candidateName    = status?.candidate_name ?? status?.name ?? user?.name ?? 'Candidate';
  const bgvLabel         = bgvStatus ? (BGV_LABELS[bgvStatus] ?? bgvStatus) : 'Not Initiated';
  // Submit-step gating. Candidate explicitly confirms once all required docs are uploaded.
  const _SUBMITTED_OR_BEYOND = new Set(['DOCS_SUBMITTED','BGV_IN_PROGRESS','BGV_CLEAR','BGV_FAILED','BGV_ON_HOLD','CONVERTED','JOINED']);
  const isSubmitted      = _SUBMITTED_OR_BEYOND.has(status?.status ?? '');
  const canSubmit        = !isSubmitted && allDocsUploaded && !bgvLocked;

  return (
    <main className="min-h-screen bg-slate-50">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <section className="bg-gradient-to-r from-[#24459f] to-[#4568e7] px-8 py-12 text-white sm:px-12">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold leading-tight sm:text-4xl">
              Welcome back, {candidateName}!
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-blue-50">
              Complete your onboarding by uploading all required documents and initiating BGV.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { logout(); navigate('/login', { replace: true }); }}
            className="ml-6 mt-1 shrink-0 rounded-lg border border-white/30 bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/20"
          >
            Sign out
          </button>
        </div>
      </section>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {loading ? (
          <div className="rounded-lg border border-slate-100 bg-white py-20 text-center text-sm text-slate-500 shadow-sm">
            Loading your onboarding status...
          </div>
        ) : (
          <>
            <DocumentUploadSection
              uploadedDocTypes={uploadedDocTypes}
              uploadingType={uploadingType}
              onUpload={handleUpload}
              onDeleteRequest={handleDeleteRequest}
              deletingType={deletingType}
              locked={bgvLocked}
            />

            {/* <p className="text-base text-slate-400">
              {uploadedCount} / {totalRequired} mandatory documents uploaded
              {uploadedDocTypes.filter((t) => !MANDATORY_DOC_IDS.has(t)).length > 0 && (
                <span className="ml-2 text-slate-300">
                  · {uploadedDocTypes.filter((t) => !MANDATORY_DOC_IDS.has(t)).length} optional
                </span>
              )}
            </p> */}

            {/* ── Submit step ─────────────────────────────────────────────────
                  Candidate explicitly confirms their submission once every
                  mandatory document is uploaded. The button is hidden once
                  BGV has started. */}
            {!bgvLocked && (
              <section className="rounded-lg border border-slate-100 bg-white px-5 py-5 shadow-sm sm:px-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-950">Submit for Review</h2>
                    <p className="mt-1 text-sm text-slate-500">
                      {isSubmitted
                        ? 'Your documents have been submitted. HR will review and start verification.'
                        : allDocsUploaded
                          ? 'All mandatory documents are uploaded. Click Submit to send them to HR for review.'
                          : `Upload all ${totalRequired} mandatory documents to enable Submit. (${uploadedCount}/${totalRequired} done)`}
                    </p>
                  </div>
                  {isSubmitted ? (
                    <span className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
                      <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden>
                        <path fillRule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-7.5 7.5a1 1 0 01-1.41 0l-3.5-3.5a1 1 0 011.41-1.42L8.5 12.09l6.79-6.8a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      Submitted
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={handleSubmit}
                      disabled={!canSubmit || submitting}
                      className={'inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition ' +
                        (canSubmit && !submitting
                          ? 'bg-[#1e3acb] text-white shadow-sm hover:bg-[#1a31b3]'
                          : 'cursor-not-allowed bg-slate-200 text-slate-500')}
                    >
                      {submitting && <SpinnerIcon className="h-4 w-4 animate-spin" />}
                      {submitting ? 'Submitting…' : 'Submit'}
                    </button>
                  )}
                </div>
              </section>
            )}

            {/* ── BGV section (read-only for candidates) ─────────────────────
                  Per the new workflow, BGV is triggered by HR only AFTER they
                  verify all required documents. Candidates see status here but
                  cannot trigger the verification themselves. */}
            <section className="rounded-lg border border-slate-100 bg-white px-5 py-5 shadow-sm sm:px-6">
              <div className="flex flex-col gap-1">
                <h2 className="text-lg font-semibold text-slate-950">Background Verification</h2>
                <p className="mt-1 text-sm text-slate-500">BGV status: {bgvLabel}</p>
                {!bgvStatus && (
                  <p className="mt-2 text-xs text-slate-400">
                    Your HR team will review your documents and initiate the
                    background verification once your submission is complete.
                  </p>
                )}
              </div>
            </section>
          </>
        )}
      </div>

            {/* ── Delete confirmation modal ───────────────────────────────────────── */}
      {confirmDeleteType && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h3 className="text-base font-semibold text-slate-900">
              Delete Document
            </h3>

            <p className="mt-2 text-sm text-slate-500">
              Are you sure you want to delete this document? This action cannot be undone.
            </p>

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={handleDeleteCancel}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleDeleteConfirm}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <Toast toasts={toasts} />
    </main>
  );
}
