/**
 * Maps any backend workflow status to one of four display buckets:
 * draft | pending | approved | rejected | unknown
 *
 * Use this as the single source of truth for filtering and metrics.
 * All canonical WF.* status strings are handled; includes legacy
 * abbreviated keys (pending_RM, HR_approved, etc.) for backwards compat.
 */
export function getDisplayStatus(status) {
  if (!status) return 'unknown';
  if (status === 'draft') return 'draft';
  if (status === 'rejected' || status === 'client_rejected') return 'rejected';
  if (status.includes('pending') || status === 'processing') return 'pending';
  if (status.includes('approved') || status === 'completed') return 'approved';
  return 'unknown';
}
