"""
api/Designation_Model/designation.py — Designation CRUD router.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from api.models import Designation
from api.Employee_Model.schemas import DesignationCreate, DesignationUpdate, DesignationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/designations", tags=["HR — Designations"])


@router.post("/", response_model=DesignationResponse)
def create_designation(data: DesignationCreate, db: Session = Depends(get_db)):
    if db.query(Designation).filter(Designation.id == data.id).first():
        raise HTTPException(400, "Designation ID already exists")
    desig = Designation(**data.model_dump())
    db.add(desig)
    db.commit()
    db.refresh(desig)
    return desig


@router.get("/", response_model=List[DesignationResponse])
def list_designations(
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    db: Session = Depends(get_db),
):
    """List all designations, optionally filtered by department_id."""
    q = db.query(Designation)
    if department_id:
        q = q.filter(Designation.department_id == department_id)
        logger.debug("Listing designations filtered by department_id=%s", department_id)
    return q.order_by(Designation.title).all()


@router.get("/{desig_id}", response_model=DesignationResponse)
def get_designation(desig_id: str, db: Session = Depends(get_db)):
    d = db.query(Designation).filter(Designation.id == desig_id).first()
    if not d:
        raise HTTPException(404, "Designation not found")
    return d


@router.put("/{desig_id}", response_model=DesignationResponse)
def update_designation(desig_id: str, data: DesignationUpdate, db: Session = Depends(get_db)):
    d = db.query(Designation).filter(Designation.id == desig_id).first()
    if not d:
        raise HTTPException(404, "Designation not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(d, field, val)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{desig_id}")
def delete_designation(desig_id: str, db: Session = Depends(get_db)):
    d = db.query(Designation).filter(Designation.id == desig_id).first()
    if not d:
        raise HTTPException(404, "Designation not found")
    db.delete(d)
    db.commit()
    return {"message": "Designation deleted"}
