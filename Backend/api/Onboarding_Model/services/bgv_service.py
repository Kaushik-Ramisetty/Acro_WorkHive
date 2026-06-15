"""services/bgv_service.py — Background Verification (BGV) logic."""
import logging
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from api.models import BGVCheck, BGVStatus, Candidate, CandidateStatus
from api.Onboarding_Model.schemas import BGVUpdateRequest
from api.Onboarding_Model.services.candidate_service import get_candidate_or_404
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)

# ── Mandatory documents that must be VERIFIED before BGV can start ────────────
# Mirrors REQUIRED_DOC_TYPES from candidate_portal.py.
REQUIRED_DOC_TYPES: set[str] = {
    "bgv_form", "aadhar", "pan", "qualification", "address_proof", "cif",
}


def _doc_verified_map(candidate) -> dict[str, bool]:
    """Return {doc_type: is_verified} across the candidate's uploaded documents."""
    from api.models import DocumentStatus
    out: dict[str, bool] = {dt: False for dt in REQUIRED_DOC_TYPES}
    for d in candidate.documents:
        if d.doc_type in out and d.status == DocumentStatus.VERIFIED.value:
            out[d.doc_type] = True
    return out


def assert_documents_verified(candidate, db: Session) -> None:
    """
    Enforce: every required document for this candidate must be in VERIFIED state.
    Raises HTTPException(409) listing the documents that still block BGV.

    This is the single gate that ALL BGV-initiate paths funnel through.
    """
    from api.models import DocumentStatus
    verified = _doc_verified_map(candidate)
    blocking: list[str] = [k for k, ok in verified.items() if not ok]
    if blocking:
        raise HTTPException(
            status_code=409,
            detail=(
                "Documents must be verified before initiating BGV. "
                f"Pending verification: {sorted(blocking)}"
            ),
        )


def write_bgv_audit(
    db: Session,
    actor_employee_id: int | None,
    action: str,
    candidate_id: int,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Append-only audit row for BGV / document-verify actions. Best-effort."""
    try:
        from app.models import AuditLog
        import uuid, json
        audit = AuditLog(
            id=f"AUD-{uuid.uuid4().hex[:14]}".upper(),
            actor_employee_id=actor_employee_id,
            action=action,
            target_table="bgv_checks" if "bgv" in action.lower() else "candidate_documents",
            target_id=str(candidate_id),
            old_value=old_value,
            new_value=new_value,
        )
        db.add(audit)
        # Caller commits; we just stage.
    except Exception as exc:
        logger.warning("AuditLog write failed (action=%s, candidate=%s): %s",
                       action, candidate_id, exc)



def _get_bgv_or_404(candidate_id: int, db: Session) -> BGVCheck:
    bgv = db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first()
    if not bgv:
        raise HTTPException(status_code=404,
            detail=f"No BGV record found for candidate {candidate_id}. Start BGV first.")
    return bgv


def start_bgv(
    candidate_id: int,
    vendor_name: Optional[str],
    db: Session,
    actor_employee_id: int | None = None,
) -> BGVCheck:
    candidate = get_candidate_or_404(candidate_id, db)
    early = {CandidateStatus.CREATED.value, CandidateStatus.OFFER_GENERATED.value, CandidateStatus.OFFER_SENT.value}
    if candidate.status in early:
        raise HTTPException(status_code=400,
            detail="BGV can only be started after the offer is accepted.")
    if db.query(BGVCheck).filter(BGVCheck.candidate_id == candidate_id).first():
        raise HTTPException(status_code=409,
            detail=f"BGV already initiated for candidate {candidate_id}.")

    # ── New gate: all required documents must be VERIFIED ─────────────────────
    assert_documents_verified(candidate, db)

    bgv = BGVCheck(candidate_id=candidate_id, status=BGVStatus.IN_PROGRESS.value,
                   vendor_name=vendor_name, initiated_at=now_utc())
    db.add(bgv)
    if candidate.status in (CandidateStatus.OFFER_ACCEPTED.value,
                            CandidateStatus.DOCS_PENDING.value,
                            CandidateStatus.DOCS_SUBMITTED.value):
        candidate.status = CandidateStatus.BGV_IN_PROGRESS.value
    write_bgv_audit(
        db, actor_employee_id, "bgv.initiate",
        candidate_id=candidate_id,
        new_value=f"vendor={vendor_name}",
    )
    db.commit()
    db.refresh(bgv)
    logger.info("BGV initiated by actor=%s for candidate=%d", actor_employee_id, candidate_id)
    return bgv


def get_bgv(candidate_id: int, db: Session) -> BGVCheck:
    get_candidate_or_404(candidate_id, db)
    return _get_bgv_or_404(candidate_id, db)


def update_bgv(candidate_id: int, payload: BGVUpdateRequest, db: Session) -> BGVCheck:
    candidate = get_candidate_or_404(candidate_id, db)
    bgv = _get_bgv_or_404(candidate_id, db)
    # Include ON_HOLD as terminal so the legacy endpoint can't undo a hold.
    if bgv.status in (BGVStatus.CLEAR.value, BGVStatus.FAILED.value, BGVStatus.ON_HOLD.value):
        raise HTTPException(status_code=409,
            detail=f"BGV already completed with status '{bgv.status}'.")
    bgv.status = payload.status.value
    bgv.remarks = payload.remarks
    bgv.completed_at = now_utc()
    # Mirror to candidate. ON_HOLD must be in the map or candidate state drifts.
    status_map = {
        BGVStatus.CLEAR.value:   CandidateStatus.BGV_CLEAR.value,
        BGVStatus.FAILED.value:  CandidateStatus.BGV_FAILED.value,
        BGVStatus.ON_HOLD.value: CandidateStatus.BGV_ON_HOLD.value,
        BGVStatus.REVIEW.value:  CandidateStatus.BGV_IN_PROGRESS.value,
    }
    new_cand = status_map.get(payload.status.value)
    if new_cand:
        candidate.status = new_cand
    db.commit()
    db.refresh(bgv)
    return bgv
