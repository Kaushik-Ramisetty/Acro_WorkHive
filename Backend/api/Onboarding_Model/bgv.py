"""api/Onboarding_Model/bgv.py — Background Verification router."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from utils.response import ok, created
from api.Onboarding_Model.schemas import BGVStartRequest, BGVUpdateRequest
from api.Onboarding_Model.services import bgv_service as svc
from utils.jwt_auth import requires_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bgv", tags=["Onboarding — BGV"],
                   dependencies=[Depends(requires_role("admin", "hr"))])


@router.post("/start/{candidate_id}")
def start_bgv(
    candidate_id: int,
    payload: BGVStartRequest = BGVStartRequest(),
    db: Session = Depends(get_db),
    actor: "CurrentUser" = Depends(requires_role("admin", "hr")),
):
    bgv = svc.start_bgv(
        candidate_id,
        payload.vendor_name,
        db,
        actor_employee_id=actor.employee_id,
    )
    return created(data=_serialize(bgv), message=f"BGV initiated for candidate {candidate_id}")


@router.get("/{candidate_id}")
def get_bgv(candidate_id: int, db: Session = Depends(get_db)):
    return ok(data=_serialize(svc.get_bgv(candidate_id, db)))


@router.patch("/update/{candidate_id}")
def update_bgv(candidate_id: int, payload: BGVUpdateRequest, db: Session = Depends(get_db)):
    bgv = svc.update_bgv(candidate_id, payload, db)
    return ok(data=_serialize(bgv), message=f"BGV updated to '{bgv.status}'")


def _serialize(bgv) -> dict:
    return {
        "id":            bgv.id,
        "candidate_id":  bgv.candidate_id,
        "status":        bgv.status,
        "vendor_name":   bgv.vendor_name,
        "initiated_at":  bgv.initiated_at.isoformat() if bgv.initiated_at else None,
        "completed_at":  bgv.completed_at.isoformat() if bgv.completed_at else None,
        "remarks":       bgv.remarks,
    }
