/**
 * Centralized secure-upload client.
 *
 * Flow (mirrors backend `secure_upload_service`):
 *   1. uploadFile(file, { module, referenceId, onProgress })
 *        → POST /secure-uploads  (multipart)
 *        → returns the SecureUpload row (status='uploaded_temp' or 'scanning')
 *   2. waitForScan(uploadId)
 *        → polls GET /secure-uploads/{id} until status is terminal
 *        → resolves with the final row, or rejects with a typed Error
 *
 * Hard frontend rules (defence in depth — backend enforces them again):
 *   - Only .jpg / .jpeg / .png   (case-insensitive)
 *   - 250 KB MAX   (256000 bytes — matches SECURE_UPLOAD_MAX_BYTES)
 *
 * Errors thrown by uploadFile / waitForScan are real `Error` instances with
 * an extra `code` property so the UI can branch:
 *   'invalid_type'   → wrong extension
 *   'too_large'      → file > 250 KB
 *   'empty'          → 0-byte file
 *   'malware'        → backend flagged it infected
 *   'scan_failed'    → scan errored (admin must review)
 *   'rejected'       → backend rejected for some other reason
 *   'timeout'        → polling exceeded the deadline
 *   'network'        → transport failure
 */
import { api, API_BASE_URL, getToken } from './api';

export const MAX_BYTES = 250 * 1024;                  // 256000 — 250 KB strict
export const ALLOWED_EXT = ['.jpg', '.jpeg', '.png'];
export const ALLOWED_MIME = ['image/jpeg', 'image/png'];

export class SecureUploadError extends Error {
  constructor(code, message, detail) {
    super(message);
    this.code = code;
    this.detail = detail;
  }
}

/** Synchronous client-side validation. Returns null if OK, or a SecureUploadError. */
export function validateFile(file) {
  if (!file) return new SecureUploadError('invalid_type', 'No file selected.');
  if (file.size === 0) return new SecureUploadError('empty', 'The selected file is empty.');
  if (file.size > MAX_BYTES) {
    return new SecureUploadError(
      'too_large',
      `File is ${(file.size / 1024).toFixed(1)} KB — the limit is 250 KB.`,
    );
  }
  const name = (file.name || '').toLowerCase();
  const dot  = name.lastIndexOf('.');
  const ext  = dot >= 0 ? name.slice(dot) : '';
  if (!ALLOWED_EXT.includes(ext)) {
    return new SecureUploadError(
      'invalid_type',
      'Only JPG, JPEG, and PNG files are allowed.',
    );
  }
  // Reject double-extension shenanigans (e.g. "foo.png.exe" wouldn't pass the
  // .exe check anyway, but "foo.exe.png" would — block that too).
  const parts = name.split('.');
  if (parts.length >= 3) {
    const interior = parts.slice(1, -1).map((p) => '.' + p);
    const ok = interior.every((e) => ALLOWED_EXT.includes(e));
    if (!ok) {
      return new SecureUploadError(
        'invalid_type',
        'File has a suspicious double extension.',
      );
    }
  }
  if (file.type && !ALLOWED_MIME.includes(file.type)) {
    return new SecureUploadError(
      'invalid_type',
      `Unsupported MIME type "${file.type}".`,
    );
  }
  return null;
}

/**
 * POST a file to /secure-uploads using XHR so we can report upload progress.
 * Resolves with the parsed JSON row when the request settles (the row is
 * still pre-scan — call waitForScan(row.id) next to await the verdict).
 */
export function uploadFile(file, { module, referenceId, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const err = validateFile(file);
    if (err) { reject(err); return; }
    if (!module) {
      reject(new SecureUploadError('rejected', 'module is required.'));
      return;
    }

    const form = new FormData();
    form.append('file', file);
    form.append('module', module);
    if (referenceId != null && referenceId !== '') form.append('reference_id', String(referenceId));

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/secure-uploads`);
    const token = getToken && getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && typeof onProgress === 'function') {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      let body = null;
      try { body = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch { /* keep null */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body);
      } else {
        const detail = body?.detail || `Upload failed (${xhr.status})`;
        const code   = xhr.status === 413 ? 'too_large'
                     : xhr.status === 400 ? 'invalid_type'
                     : 'rejected';
        reject(new SecureUploadError(code, detail, body));
      }
    };
    xhr.onerror   = () => reject(new SecureUploadError('network', 'Network error during upload.'));
    xhr.ontimeout = () => reject(new SecureUploadError('network', 'Upload timed out.'));
    xhr.send(form);
  });
}

/**
 * Poll /secure-uploads/{id} until the row reaches a terminal state.
 *
 *   safe         → resolve(row)
 *   infected     → reject(SecureUploadError('malware', generic_message))
 *   scan_failed  → reject(SecureUploadError('scan_failed', generic_message))
 *   rejected     → reject(SecureUploadError('rejected', generic_message))
 *
 * Generic messages by design — we never leak engine internals or signature
 * names to end-users (per spec).
 */
export async function waitForScan(uploadId, {
  intervalMs = 1200,
  timeoutMs  = 30000,
  onTick,
} = {}) {
  const started = Date.now();
  // First tick immediately so the UI flips from "uploading" → "scanning" fast.
  while (true) {
    let row;
    try {
      row = await api.get(`/secure-uploads/${uploadId}`);
    } catch (e) {
      throw new SecureUploadError('network', 'Lost connection while scanning.');
    }
    if (typeof onTick === 'function') onTick(row);
    if (row?.scan_status === 'safe') return row;
    if (row?.scan_status === 'infected') {
      throw new SecureUploadError(
        'malware',
        'This file failed our security check and has been rejected.',
      );
    }
    if (row?.scan_status === 'scan_failed') {
      throw new SecureUploadError(
        'scan_failed',
        'We could not verify this file right now. Please try again in a few minutes.',
      );
    }
    if (row?.scan_status === 'rejected') {
      throw new SecureUploadError('rejected', 'File was rejected.');
    }
    if (Date.now() - started > timeoutMs) {
      throw new SecureUploadError(
        'timeout',
        'Security scan is taking longer than expected. The file will appear once verified.',
      );
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** Convenience: upload + scan in one call. Returns the final 'safe' row. */
export async function uploadAndScan(file, opts = {}) {
  const row = await uploadFile(file, opts);
  return waitForScan(row.id, opts);
}

export const secureUploadsApi = {
  upload: uploadFile,
  status: (id) => api.get(`/secure-uploads/${id}`),
  remove: (id) => api.delete(`/secure-uploads/${id}`),
  mine:   (params = {}) => {
    const qs = new URLSearchParams();
    if (params.module) qs.set('module', params.module);
    if (params.limit)  qs.set('limit', String(params.limit));
    return api.get('/secure-uploads/mine/list' + (qs.toString() ? `?${qs}` : ''));
  },
  // Admin
  adminList:   (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status)        qs.set('status', params.status);
    if (params.module)        qs.set('module', params.module);
    if (params.infectedOnly)  qs.set('infected_only', 'true');
    if (params.limit  != null) qs.set('limit',  String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    return api.get('/admin/secure-uploads' + (qs.toString() ? `?${qs}` : ''));
  },
  adminRescan: (id) => api.post(`/admin/secure-uploads/${id}/rescan`),
};

export default secureUploadsApi;
