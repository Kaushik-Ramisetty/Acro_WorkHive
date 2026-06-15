"""
skill_set  — master table of all approved skills
skill_requests — global skill approval requests from managers to HR Admin
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class SkillSet(Base):
    __tablename__ = "skill_set"

    id: Mapped[str]        = mapped_column(String(20),  primary_key=True)  # SKL001 …
    skill_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[int]  = mapped_column(Integer, nullable=False, default=1)
    added_by: Mapped[str | None]    = mapped_column(String(50),  nullable=True)   # employee_code
    added_at: Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SkillRequest(Base):
    __tablename__ = "skill_requests"

    id: Mapped[int]         = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # employee integer id of the requesting manager
    requested_by: Mapped[int | None]    = mapped_column(ForeignKey("employees.id"), nullable=True)
    requested_at: Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), nullable=False)
    status: Mapped[str]                 = mapped_column(String(20), nullable=False, default="pending")
    # pending / approved / rejected
    approved_by: Mapped[int | None]     = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    requester = relationship("Employee", foreign_keys=[requested_by])
    approver  = relationship("Employee", foreign_keys=[approved_by])
