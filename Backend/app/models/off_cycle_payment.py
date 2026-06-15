"""Off-Cycle Payment model — standalone bonus disbursement, completely separate from payroll runs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OffCyclePayment(Base):
    """One off-cycle bonus payment record per bonus request approval."""
    __tablename__ = "off_cycle_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source
    bonus_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("bonus_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )

    # Payment details
    bonus_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status flow: approved_off_cycle → payment_ready → paid
    payment_status: Mapped[str] = mapped_column(
        String(30), default="approved_off_cycle", nullable=False, index=True
    )

    # Approval
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Document paths (relative file paths stored; served via /uploads or generated on demand)
    payslip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bank_advice_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Payment confirmation
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    paid_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reference number for bank advice
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    employee:    Mapped["Employee"] = relationship(foreign_keys=[employee_id])       # type: ignore[name-defined]
    approved_by: Mapped["Employee | None"] = relationship(foreign_keys=[approved_by_id])  # type: ignore[name-defined]
    paid_by:     Mapped["Employee | None"] = relationship(foreign_keys=[paid_by_id])      # type: ignore[name-defined]


class OffCycleAuditLog(Base):
    """Immutable audit trail for every status change on an OffCyclePayment."""
    __tablename__ = "off_cycle_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    off_cycle_payment_id: Mapped[int] = mapped_column(
        ForeignKey("off_cycle_payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    payment: Mapped["OffCyclePayment"] = relationship(foreign_keys=[off_cycle_payment_id])
    actor:   Mapped["Employee | None"] = relationship(foreign_keys=[actor_id])  # type: ignore[name-defined]
