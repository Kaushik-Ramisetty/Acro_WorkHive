/**
 * VendorBGVReview.jsx — Public BGV vendor review portal.
 *
 * Route: /vendor/bgv-review/:token
 * No authentication required — access is controlled entirely by the secure token.
 *
 * States:
 *   loading   → fetching candidate details from backend
 *   invalid   → token does not exist
 *   expired   → token has passed its expiry timestamp
 *   used      → token was already submitted
 *   ready     → valid token; show candidate info + submission form
 *   submitted → vendor successfully submitted result
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getVendorBgvDetails, submitVendorBgvResult } from '../../services/vendorApi';

import { API_BASE } from '../../config/api';

const DOC_LABELS = {
  bgv_form:      'Updated BGV Form',
  aadhar:        'Aadhaar Card',
  pan:           'PAN Card',
  qualification: 'Highest Qualification',
  exp1:          'Experience Letter 1',
  exp2:          'Experience Letter 2',
  exp3:          'Experience Letter 3',
  address_proof: 'Address Proof',
  cif:           'CIF Document',
};

// ── Error state helpers ───────────────────────────────────────────────────────

function classify(errorMessage = '') {
  const msg = errorMessage.toLowerCase();
  if (msg.includes('already been used') || msg.includes('already submitted')) return 'used';
  if (msg.includes('expired'))                                                  return 'expired';
  if (msg.includes('invalid') || msg.includes('does not exist'))               return 'invalid';
  return 'error';
}

const ERROR_CONFIG = {
  invalid: {
    icon:    '🔒',
    title:   'Invalid Link',
    color:   'border-red-200',
    body:    'This review link does not exist or has been revoked. Please contact HR.',
  },
  expired: {
    icon:    '⏰',
    title:   'Link Expired',
    color:   'border-amber-200',
    body:    'This review link has expired. Please contact HR to resend a new link.',
  },
  used: {
    icon:    '✅',
    title:   'Already Submitted',
    color:   'border-blue-200',
    body:    'A BGV result has already been submitted using this link. No further action is required.',
  },
  error: {
    icon:    '⚠️',
    title:   'Access Denied',
    color:   'border-red-200',
    body:    null,
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function PageShell({ children }) {
  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="mx-auto max-w-2xl space-y-4">{children}</div>
    </div>
  );
}

function PortalHeader() {
  return (
    <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5 flex items-center gap-4">
      <div className="h-11 w-11 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
        BGV
      </div>
      <div>
        <h1 className="text-base font-bold text-slate-800">BGV Vendor Review Portal</h1>
        <p className="text-xs text-slate-400 mt-0.5">Secure · One-time access · Powered by Acronotics</p>
      </div>
    </div>
  );
}

function ErrorCard({ type, message }) {
  const cfg = ERROR_CONFIG[type] || ERROR_CONFIG.error;
  return (
    <PageShell>
      <PortalHeader />
      <div className={`rounded-2xl bg-white border ${cfg.color} shadow-sm p-8 text-center`}>
        <div className="text-5xl mb-4">{cfg.icon}</div>
        <h2 className="text-lg font-bold text-slate-800 mb-2">{cfg.title}</h2>
        <p className="text-sm text-slate-500">{cfg.body || message}</p>
      </div>
    </PageShell>
  );
}

function LoadingCard() {
  return (
    <PageShell>
      <PortalHeader />
      <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-12 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent mx-auto mb-4" />
        <p className="text-sm text-slate-500">Loading review details…</p>
      </div>
    </PageShell>
  );
}

function SuccessCard() {
  return (
    <PageShell>
      <PortalHeader />
      <div className="rounded-2xl bg-white border border-green-200 shadow-sm p-8 text-center">
        <div className="text-5xl mb-4">✅</div>
        <h2 className="text-lg font-bold text-slate-800 mb-2">BGV Submitted Successfully</h2>
        <p className="text-sm text-slate-500">
          Your review has been recorded and the admin has been notified.
          This link is now expired and cannot be used again.
        </p>
      </div>
    </PageShell>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function VendorBGVReview() {
  const { token } = useParams();

  const [pageState, setPageState]     = useState('loading');
  const [errorType, setErrorType]     = useState('error');
  const [errorMsg, setErrorMsg]       = useState('');
  const [reviewData, setReviewData]   = useState(null);

  const [bgvStatus, setBgvStatus]     = useState('');  // 'CLEAR' | 'FAILED'
  const [remarks, setRemarks]         = useState('');
  const [submitting, setSubmitting]   = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Load candidate details on mount
  useEffect(() => {
    if (!token) {
      setErrorType('invalid');
      setPageState('error');
      return;
    }

    getVendorBgvDetails(token)
      .then((data) => {
        setReviewData(data);
        setPageState('ready');
      })
      .catch((err) => {
        const msg = err.message || '';
        setErrorType(classify(msg));
        setErrorMsg(msg);
        setPageState('error');
      });
  }, [token]);

  // Submit BGV result
  async function handleSubmit(e) {
    e.preventDefault();
    if (!bgvStatus || submitting) return;

    setSubmitError('');
    setSubmitting(true);
    try {
      await submitVendorBgvResult(token, bgvStatus, remarks);
      setPageState('submitted');
    } catch (err) {
      const msg = err.message || 'Submission failed. Please try again.';
      const type = classify(msg);
      if (type === 'used' || type === 'expired') {
        setErrorType(type);
        setErrorMsg(msg);
        setPageState('error');
      } else {
        setSubmitError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ── Render states ───────────────────────────────────────────────────────────

  if (pageState === 'loading')   return <LoadingCard />;
  if (pageState === 'submitted') return <SuccessCard />;
  if (pageState === 'error')     return <ErrorCard type={errorType} message={errorMsg} />;

  const { candidate, documents, token_expires_at } = reviewData;
  const expiresAt = token_expires_at
    ? new Date(token_expires_at).toLocaleString(undefined, {
        dateStyle: 'medium', timeStyle: 'short',
      })
    : null;

  return (
    <PageShell>
      <PortalHeader />

      {/* Expiry notice */}
      {expiresAt && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-2.5 text-xs text-amber-700 flex items-center gap-2">
          <span>⏰</span>
          <span>This link expires on <strong>{expiresAt}</strong> and can only be used once.</span>
        </div>
      )}

      {/* Candidate Details */}
      <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-6">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4">
          Candidate Information
        </h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-slate-400 text-xs mb-0.5">Full Name</dt>
            <dd className="font-semibold text-slate-800">{candidate.name}</dd>
          </div>
          <div>
            <dt className="text-slate-400 text-xs mb-0.5">Candidate ID</dt>
            <dd className="font-semibold text-slate-800">{candidate.candidate_ref}</dd>
          </div>
          <div>
            <dt className="text-slate-400 text-xs mb-0.5">Role Applied For</dt>
            <dd className="font-semibold text-slate-800">{candidate.role}</dd>
          </div>
          <div>
            <dt className="text-slate-400 text-xs mb-0.5">Department</dt>
            <dd className="font-semibold text-slate-800">{candidate.department || '—'}</dd>
          </div>
        </dl>
      </div>

      {/* Documents */}
      <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-6">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4">
          Documents for Verification
          <span className="ml-2 rounded-full bg-slate-100 text-slate-500 px-2 py-0.5 text-xs font-normal">
            {documents.length}
          </span>
        </h2>
        {documents.length === 0 ? (
          <p className="text-sm text-slate-400">No documents available for this candidate.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {documents.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between py-3 gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-700">
                    {DOC_LABELS[doc.doc_type] || doc.doc_type}
                  </p>
                  <p className="text-xs text-slate-400 truncate">{doc.original_filename}</p>
                </div>
                <a
                  href={`${API_BASE}${doc.file_url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition"
                >
                  View / Download
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Submit Form */}
      <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-6">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-5">
          Submit BGV Result
        </h2>

        {submitError && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Status selection */}
          <div className="grid grid-cols-3 gap-3">
            {/* CLEAR */}
            <button
              type="button"
              onClick={() => setBgvStatus('CLEAR')}
              className={`rounded-xl border-2 px-3 py-4 text-sm font-semibold transition text-left ${
                bgvStatus === 'CLEAR'
                  ? 'border-green-500 bg-green-50 text-green-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-green-300 hover:bg-green-50 hover:text-green-700'
              }`}
            >
              <div className="text-2xl mb-1">✅</div>
              <div>BGV Cleared</div>
              <div className="text-xs font-normal mt-0.5 opacity-70">Verification passed</div>
            </button>

            {/* HOLD */}
            <button
              type="button"
              onClick={() => setBgvStatus('HOLD')}
              className={`rounded-xl border-2 px-3 py-4 text-sm font-semibold transition text-left ${
                bgvStatus === 'HOLD'
                  ? 'border-orange-500 bg-orange-50 text-orange-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700'
              }`}
            >
              <div className="text-2xl mb-1">⏸️</div>
              <div>BGV On Hold</div>
              <div className="text-xs font-normal mt-0.5 opacity-70">Pending further review</div>
            </button>

            {/* FAILED */}
            <button
              type="button"
              onClick={() => setBgvStatus('FAILED')}
              className={`rounded-xl border-2 px-3 py-4 text-sm font-semibold transition text-left ${
                bgvStatus === 'FAILED'
                  ? 'border-red-500 bg-red-50 text-red-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-red-300 hover:bg-red-50 hover:text-red-700'
              }`}
            >
              <div className="text-2xl mb-1">❌</div>
              <div>BGV Rejected</div>
              <div className="text-xs font-normal mt-0.5 opacity-70">Issues found</div>
            </button>
          </div>

          {/* Remarks */}
          <div>
            <label
              htmlFor="remarks"
              className="block text-xs font-medium text-slate-500 mb-1.5"
            >
              Remarks <span className="text-red-500">*</span>
              <span className="ml-1 text-slate-400 font-normal">(mandatory for all decisions)</span>
            </label>
            <textarea
              id="remarks"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              rows={3}
              placeholder="Add verification notes, observations, or reasons for flagging…"
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700 placeholder-slate-300 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 resize-none"
            />
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={!bgvStatus || !remarks.trim() || submitting}
            className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {submitting ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Submitting…
              </span>
            ) : (
              'Submit BGV Result'
            )}
          </button>

          {(!bgvStatus || !remarks.trim()) && (
            <p className="text-center text-xs text-slate-400">
              {!bgvStatus ? 'Select a result above' : 'Remarks are required'}
              {bgvStatus && !remarks.trim() ? ' — add a remark to continue' : ''}
            </p>
          )}
        </form>
      </div>

      <p className="text-center text-xs text-slate-400 pb-4">
        This is a secure, one-time use link. Do not share or reuse it.
      </p>
    </PageShell>
  );
}
