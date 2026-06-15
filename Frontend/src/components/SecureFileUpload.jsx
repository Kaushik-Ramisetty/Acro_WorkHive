/**
 * SecureFileUpload — reusable upload widget enforcing the HRMS upload
 * contract (JPG/JPEG/PNG only, 250 KB hard cap, async malware scan).
 *
 * Drop-in usage:
 *
 *   <SecureFileUpload
 *     module="leave"
 *     referenceId={request.id}
 *     onComplete={(row) => attachToRequest(row.id)}
 *   />
 *
 * Props:
 *   module            (required) — "leave" | "onboarding" | "regularization" | …
 *   referenceId       (optional) — the workflow entity the file belongs to
 *   onComplete(row)   — called once the row reaches scan_status='safe'
 *   onError(error)    — called on every rejected upload (validation, malware, etc.)
 *   label             — button text (default: "Upload file")
 *   accept            — input[type=file] accept string (default: image/jpeg,image/png)
 *
 * Visual style intentionally matches the rest of the HRMS shell — no new
 * design tokens introduced.
 */
import { useRef, useState } from 'react';
import {
  uploadFile,
  waitForScan,
  validateFile,
  MAX_BYTES,
  ALLOWED_EXT,
  SecureUploadError,
} from '../services/secureUploads';

const STATE_IDLE      = 'idle';
const STATE_UPLOAD    = 'uploading';
const STATE_SCAN      = 'scanning';
const STATE_DONE      = 'done';
const STATE_ERROR     = 'error';

export default function SecureFileUpload({
  module,
  referenceId,
  onComplete,
  onError,
  label = 'Upload file',
  accept = 'image/jpeg,image/png',
  disabled = false,
  className = '',
}) {
  const inputRef = useRef(null);
  const [state, setState]       = useState(STATE_IDLE);
  const [progress, setProgress] = useState(0);
  const [error, setError]       = useState(null);
  const [fileName, setFileName] = useState('');

  const reset = () => {
    setState(STATE_IDLE); setProgress(0); setError(null); setFileName('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const handle = async (file) => {
    setFileName(file.name);
    setError(null);
    const v = validateFile(file);
    if (v) {
      setState(STATE_ERROR);
      setError(v);
      onError?.(v);
      return;
    }
    try {
      setState(STATE_UPLOAD);
      setProgress(0);
      const row = await uploadFile(file, {
        module,
        referenceId,
        onProgress: (p) => setProgress(p),
      });
      setState(STATE_SCAN);
      const safeRow = await waitForScan(row.id, { intervalMs: 1200, timeoutMs: 45000 });
      setState(STATE_DONE);
      onComplete?.(safeRow);
    } catch (e) {
      const err = e instanceof SecureUploadError
        ? e
        : new SecureUploadError('rejected', e?.message || 'Upload failed.');
      setState(STATE_ERROR);
      setError(err);
      onError?.(err);
    }
  };

  const onChange = (e) => {
    const f = e.target.files?.[0];
    if (f) handle(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) handle(f);
  };

  const busy = state === STATE_UPLOAD || state === STATE_SCAN;

  return (
    <div className={'space-y-2 ' + className}>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className={
          'flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-5 text-center transition ' +
          (state === STATE_ERROR
            ? 'border-red-300 bg-red-50'
            : state === STATE_DONE
            ? 'border-emerald-300 bg-emerald-50'
            : busy
            ? 'border-teal-300 bg-teal-50'
            : 'border-slate-300 bg-white hover:border-teal-400')
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={onChange}
          disabled={disabled || busy}
          className="hidden"
        />
        {state === STATE_IDLE && (
          <>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={disabled}
              className="rounded-lg bg-teal-500 px-3 py-1.5 text-xs font-semibold text-white hover:brightness-110 disabled:opacity-50"
            >
              {label}
            </button>
            <p className="text-[11px] text-slate-500">
              JPG, JPEG or PNG · max {MAX_BYTES / 1024} KB · scanned for malware
            </p>
          </>
        )}

        {state === STATE_UPLOAD && (
          <>
            <p className="text-xs font-semibold text-slate-700">Uploading "{fileName}"…</p>
            <div className="w-full max-w-xs h-1.5 rounded-full bg-slate-200 overflow-hidden">
              <div
                className="h-full bg-teal-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-[10px] uppercase tracking-wider text-slate-400">{progress}%</p>
          </>
        )}

        {state === STATE_SCAN && (
          <>
            <p className="text-xs font-semibold text-slate-700">Scanning "{fileName}" for threats…</p>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
              <span className="inline-block h-2 w-2 rounded-full bg-teal-500 animate-pulse" />
              Running security checks
            </div>
          </>
        )}

        {state === STATE_DONE && (
          <>
            <p className="text-xs font-semibold text-emerald-700">"{fileName}" passed security checks.</p>
            <button
              type="button"
              onClick={reset}
              className="text-[11px] font-semibold text-teal-600 hover:underline"
            >
              Upload another
            </button>
          </>
        )}

        {state === STATE_ERROR && (
          <>
            <p className="text-xs font-semibold text-red-700">
              {messageFor(error)}
            </p>
            <button
              type="button"
              onClick={reset}
              className="text-[11px] font-semibold text-red-700 hover:underline"
            >
              Try again
            </button>
          </>
        )}
      </div>

      {state === STATE_IDLE && (
        <p className="text-[10px] text-slate-400">
          Allowed: {ALLOWED_EXT.join(', ')}.
        </p>
      )}
    </div>
  );
}

// User-facing messages — never leak malware engine internals.
function messageFor(error) {
  if (!error) return 'Something went wrong. Please try again.';
  switch (error.code) {
    case 'invalid_type':
      return error.message || 'Only JPG, JPEG, and PNG files are allowed.';
    case 'too_large':
      return error.message || 'File exceeds the 250 KB limit.';
    case 'empty':
      return 'The selected file is empty.';
    case 'malware':
      return 'This file failed our security check and has been rejected.';
    case 'scan_failed':
      return 'We could not verify this file right now. Please try again in a few minutes.';
    case 'timeout':
      return 'Security scan is taking longer than expected.';
    case 'network':
      return error.message || 'Network error during upload.';
    case 'rejected':
    default:
      return error.message || 'Upload was rejected.';
  }
}
