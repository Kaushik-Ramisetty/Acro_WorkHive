"""api/Onboarding_Model/offers.py — Offer letter generation, dispatch, acceptance."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from utils.response import ok
from api.Onboarding_Model.schemas import OfferSendRequest
from api.Onboarding_Model.services import offer_service as svc
from utils.jwt_auth import requires_role

logger = logging.getLogger(__name__)
_HR_ROLES = ("admin", "hr")
router = APIRouter(prefix="/offer", tags=["Onboarding — Offers"],
                   dependencies=[Depends(requires_role(*_HR_ROLES))])


@router.post("/generate/{candidate_id}")
def generate_offer(candidate_id: int, db: Session = Depends(get_db)):
    candidate = svc.generate_offer(candidate_id, db)
    return ok(data={"candidate_id": candidate.id, "offer_letter_url": candidate.offer_letter_url, "status": candidate.status},
              message="Offer letter generated successfully")


@router.post("/send/{candidate_id}")
def send_offer(candidate_id: int, payload: OfferSendRequest = None, db: Session = Depends(get_db)):
    req = payload or OfferSendRequest()
    candidate = svc.send_offer(candidate_id=candidate_id, db=db,
                                to_email=req.to_email, subject=req.subject, body=req.body)
    return ok(data={
        "candidate_id": candidate.id, "email": candidate.email,
        "sent_at": candidate.offer_sent_at.isoformat() if candidate.offer_sent_at else None,
        "status": candidate.status,
    }, message=f"Offer email sent to {candidate.email}")


@router.post("/regenerate/{candidate_id}")
def regenerate_offer(candidate_id: int, db: Session = Depends(get_db)):
    candidate = svc.regenerate_offer(candidate_id, db)
    return ok(data={"candidate_id": candidate.id, "offer_letter_url": candidate.offer_letter_url, "status": candidate.status},
              message="Offer letter regenerated successfully")


@router.post("/accept/{candidate_id}")
def accept_offer(candidate_id: int, db: Session = Depends(get_db)):
    candidate = svc.accept_offer(candidate_id, db)
    return ok(data={
        "candidate_id": candidate.id,
        "accepted_at": candidate.offer_accepted_at.isoformat() if candidate.offer_accepted_at else None,
        "status": candidate.status,
    }, message="Offer accepted. Candidate may now upload documents.")


@router.post("/reject/{candidate_id}")
def reject_offer(candidate_id: int, db: Session = Depends(get_db)):
    candidate = svc.reject_offer(candidate_id, db)
    return ok(data={"candidate_id": candidate.id, "status": candidate.status},
              message="Offer rejected. Candidate pipeline closed.")
