"""
api/Onboarding_Model/documents.py - HR-side document admin endpoints.

Candidates upload via /api/v1/candidate/documents/upload (the candidate portal,
which has its own JWT-based auth path).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from utils.response import ok, created, error
from api.Onboarding_Model.services import document_service as svc
from utils.jwt_auth import CurrentUser, requires_role

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Onboarding - Documents"],
    dependencies=[Depends(requires_role("admin", "hr"))],
)


@router.post("/upload")
async def upload_documents(
    candidate_id: int               = Form(...),
    doc_type:     str               = Form("general"),
    files:        List[UploadFile]  = File(...),
    db: Session = Depends(get_db),
):
    saved, failures = svc.upload_documents(candidate_id, doc_type, files, db)
    if not saved and failures:
        return error("All uploads failed. Check file types and sizes.", status_code=400)
    return ok(
        data={
            "uploaded":  len(saved),
            "failed":    failures,
            "documents": [
                {
                    "id":                d.id,
                    "doc_type":          d.doc_type,
                    "original_filename": d.original_filename,
                    "file_url":          d.file_url,
                    "status":            d.status,
                    "uploaded_at":       d.uploaded_at.isoformat() if d.uploaded_at else None,
                }
                for d in saved
            ],
        },
        message=f"{len(saved)} document(s) uploaded successfully"
        + (f", {failures} failed" if failures else ""),
    )


@router.get("/{candidate_id}")
def get_candidate_documents(candidate_id: int, db: Session = Depends(get_db)):
    docs = svc.get_candidate_documents(candidate_id, db)
    return ok(
        data=[
            {
                "id":                d.id,
                "doc_type":          d.doc_type,
                "original_filename": d.original_filename,
                "file_url":          d.file_url,
                "file_size_kb":      d.file_size_kb,
                "status":            d.status,
                "uploaded_at":       d.uploaded_at.isoformat() if d.uploaded_at else None,
                "verified_at":       d.verified_at.isoformat() if d.verified_at else None,
                "remarks":           d.remarks,
            }
            for d in docs
        ],
        message=f"{len(docs)} document(s) found",
    )


class VerifyDocumentPayload(BaseModel):
    # JSON body for HR Admin document verify / reject action.
    approved: bool
    remarks: Optional[str] = None


@router.patch("/{doc_id}/verify")
def verify_document(
    doc_id:  int,
    payload: VerifyDocumentPayload,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(requires_role("admin", "hr")),
):
    # HR Admin verifies or rejects a candidate document.
    # Business rules:
    #   - Only admin / hr roles (router-level dependency).
    #   - Sets document.status to VERIFIED or REJECTED.
    #   - Appends an audit-log row via document_service.verify_document().
    # BGV gate:
    #   - BGV can only be initiated AFTER every required document is VERIFIED.
    #   - bgv_service.assert_documents_verified() enforces this on initiate.
    doc = svc.verify_document(
        doc_id,
        payload.approved,
        payload.remarks,
        db,
        actor_employee_id=actor.employee_id,
    )
    action = "verified" if payload.approved else "rejected"
    return ok(
        data={
            "id":           doc.id,
            "doc_type":     doc.doc_type,
            "candidate_id": doc.candidate_id,
            "status":       doc.status,
            "remarks":      doc.remarks,
            "verified_at":  doc.verified_at.isoformat() if doc.verified_at else None,
        },
        message=f"Document {action} successfully",
    )
