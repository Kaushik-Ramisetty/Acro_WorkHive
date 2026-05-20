"""api/Onboarding_Model/admin_portal.py — Admin summary view for candidates."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from utils.response import ok
from api.models import Candidate, DocumentStatus
from utils.jwt_auth import requires_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["Admin Portal"],
                   dependencies=[Depends(requires_role("admin", "hr"))])

REQUIRED_DOC_TYPES = {"aadhar", "pan", "degree", "exp", "photo", "bank"}
_REQUIRED_COUNT = len(REQUIRED_DOC_TYPES)


@router.get("/candidates")
def admin_list_candidates(db: Session = Depends(get_db)):
    candidates = db.query(Candidate).order_by(Candidate.id.desc()).all()
    result = []
    for c in candidates:
        uploaded_types = {
            d.doc_type for d in c.documents
            if d.status in (DocumentStatus.UPLOADED.value, DocumentStatus.VERIFIED.value)
        }
        done_count = len(uploaded_types & REQUIRED_DOC_TYPES)
        doc_status = ("Completed" if done_count >= _REQUIRED_COUNT
                      else "Partial" if done_count > 0 else "Pending")
        bgv_status = c.bgv_check.status if c.bgv_check else "Not Initiated"
        result.append({
            "candidate_id":    c.id,
            "candidate_ref":   c.candidate_ref,
            "name":            c.name,
            "email":           c.email,
            "role":            c.role,
            "department":      c.department,
            "status":          c.status,
            "current_status":  c.status,
            "document_count":  done_count,
            "total_required_documents": _REQUIRED_COUNT,
            "document_status": doc_status,
            "bgv_status":      bgv_status,
        })
    return ok(data=result, message=f"{len(result)} candidate(s) found")
