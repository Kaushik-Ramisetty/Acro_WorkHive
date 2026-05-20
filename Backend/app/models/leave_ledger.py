"""Immutable balance ledger for leave_balances.

Every change to a LeaveBalance row — reserve on approval, release on
cancellation, debit on consumption, credit on reversal, monthly accrual,
year-end carry-forward, encashment, manual adjustment — MUST be recorded
here with a transaction type and full before/after snapshot. Rows are
never UPDATEd or DELETEd; corrections happen by writing a compensating
entry.

Why double-bookkeeping the snapshot fields?
  - `delta` alone is fine for math, but during incident triage the
    before/after pair lets you spot a corrupted balance row instantly
    without replaying the full history.
  - SQL Server CHECK constraints can enforce `after = before + delta`
    once a future migration adds them; we don't gate Phase 5A on that.

Reference fields point at the originating object:
  - reference_type ∈ {'leave_request', 'comp_off_credit',
                      'accrual_run', 'carry_forward_run',
                      'manual_adjustment', 'system_backfill'}
  - reference_id   : free-form string (LR023, CO12, ACC-2026-04, …)
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# Enum-style constants — kept as strings (not a Python Enum) so SQL Server's
# CHECK constraint can pin them without an ALTER TYPE round trip later.
class LedgerTxn:
    # ── Legacy primitives (one bucket per row) ────────────────────────────
    RESERVE        = "RESERVE"
    RELEASE        = "RELEASE"
    DEBIT          = "DEBIT"           # consumed (final deduction)
    CREDIT         = "CREDIT"          # reversal of a previous DEBIT
    ACCRUAL        = "ACCRUAL"         # monthly/yearly automatic top-up
    CARRY_FORWARD  = "CARRY_FORWARD"   # year-end roll-over
    ENCASHMENT     = "ENCASHMENT"      # cashout removes days from balance
    ADJUSTMENT     = "ADJUSTMENT"      # admin manual fix
    CANCELLATION   = "CANCELLATION"    # synonym for RELEASE used for clarity in cancel flow

    # ── Hybrid v2 composite transactions ───────────────────────────────────
    # Each composite atomically moves more than one bucket in a single
    # ledger row. `bucket` is set to 'multi' and the before/after triples
    # capture the full state change so audit replay still works.
    LEAVE_DEDUCTION             = "LEAVE_DEDUCTION"
    # ↑ on manager approval (new architecture):
    #     reserved += days   AND   used += days
    LEAVE_COMPLETION            = "LEAVE_COMPLETION"
    # ↑ scheduler when leave dates pass:
    #     reserved -= days   (used was already incremented at approval)
    LEAVE_CANCELLATION_REVERSAL = "LEAVE_CANCELLATION_REVERSAL"
    # ↑ full cancellation of a future-dated approved leave:
    #     reserved -= days   AND   used -= days
    PARTIAL_CANCELLATION        = "PARTIAL_CANCELLATION"
    # ↑ partial cancellation (cancel only the future-dated tail):
    #     reserved -= remaining   AND   used -= remaining
    #     (already-consumed portion stays in `used` — payroll-safe.)

    ALL = (
        RESERVE, RELEASE, DEBIT, CREDIT,
        ACCRUAL, CARRY_FORWARD, ENCASHMENT, ADJUSTMENT, CANCELLATION,
        LEAVE_DEDUCTION, LEAVE_COMPLETION,
        LEAVE_CANCELLATION_REVERSAL, PARTIAL_CANCELLATION,
    )

    # Composite types — `post_ledger_entry` takes the multi-bucket path.
    # LEAVE_COMPLETION is technically single-bucket (reserved-) but is
    # routed through the same dispatcher so all v2 transactions share one
    # consistent code path.
    COMPOSITE = frozenset({
        LEAVE_DEDUCTION,
        LEAVE_COMPLETION,
        LEAVE_CANCELLATION_REVERSAL,
        PARTIAL_CANCELLATION,
    })


class LeaveBalanceLedger(Base):
    __tablename__ = "leave_balance_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    employee_id: Mapped[int]   = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[str] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    year: Mapped[int]          = mapped_column(Integer, nullable=False, index=True)

    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # Days transacted. Always stored positive; the bucket (`bucket`) +
    # `transaction_type` together define the sign.
    days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Which sub-balance was moved:
    #   'allocated' (= the grant pool, hit by ACCRUAL/CARRY_FORWARD/ADJUSTMENT/ENCASHMENT)
    #   'reserved'  (RESERVE/RELEASE)
    #   'used'      (DEBIT/CREDIT)
    bucket: Mapped[str] = mapped_column(String(20), nullable=False)

    # Before/after triple snapshot of the affected balance row.
    before_allocated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    before_reserved:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    before_used:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    after_allocated:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    after_reserved:   Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    after_used:       Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    reference_id:   Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    note:     Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    actor: Mapped["Employee | None"] = relationship(foreign_keys=[actor_id])  # type: ignore[name-defined]

    __table_args__ = (
        Index("ix_leave_ledger_lookup",
              "employee_id", "leave_type_id", "year", "created_at"),
        Index("ix_leave_ledger_reference", "reference_type", "reference_id"),
    )
