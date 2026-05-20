"""phase5a: immutable leave balance ledger + additive balance columns.

Adds:
  - leave_balance_ledger table (immutable transaction log)
  - leave_balances.allocated_balance        (= opening + accruals, ledger-managed)
  - leave_balances.pending_balance          (days locked by status='pending')
  - leave_balances.row_version              (optimistic-concurrency token)

A separate startup hook (`app.services.leave_ledger_backfill.seed_allocated_from_opening`)
copies `opening_balance` into `allocated_balance` on first run so existing
rows have a sensible starting value without a data migration here.

Revision ID: 0005_phase5a_ledger
Revises: 0004_phase4_docs_capacity
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase5a_ledger"
down_revision: Union[str, None] = "0004_phase4_docs_capacity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ---- leave_balance_ledger --------------------------------------
    if not _has_table(bind, "leave_balance_ledger"):
        op.create_table(
            "leave_balance_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("leave_type_id", sa.String(length=20),
                      sa.ForeignKey("leave_types.id"), nullable=False, index=True),
            sa.Column("year", sa.Integer(), nullable=False, index=True),
            sa.Column("transaction_type", sa.String(length=30), nullable=False, index=True),
            sa.Column("days", sa.Integer(), nullable=False),
            sa.Column("bucket", sa.String(length=20), nullable=False),
            sa.Column("before_allocated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("before_reserved",  sa.Integer(), nullable=False, server_default="0"),
            sa.Column("before_used",      sa.Integer(), nullable=False, server_default="0"),
            sa.Column("after_allocated",  sa.Integer(), nullable=False, server_default="0"),
            sa.Column("after_reserved",   sa.Integer(), nullable=False, server_default="0"),
            sa.Column("after_used",       sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reference_type", sa.String(length=40), nullable=True, index=True),
            sa.Column("reference_id",   sa.String(length=40), nullable=True, index=True),
            sa.Column("actor_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "transaction_type IN ('RESERVE','RELEASE','DEBIT','CREDIT',"
                "'ACCRUAL','CARRY_FORWARD','ENCASHMENT','ADJUSTMENT','CANCELLATION')",
                name="ck_leave_ledger_txn_type",
            ),
            sa.CheckConstraint(
                "bucket IN ('allocated','reserved','used')",
                name="ck_leave_ledger_bucket",
            ),
            sa.CheckConstraint("days >= 0", name="ck_leave_ledger_days_nonneg"),
        )
        op.create_index(
            "ix_leave_ledger_lookup", "leave_balance_ledger",
            ["employee_id", "leave_type_id", "year", "created_at"],
        )
        op.create_index(
            "ix_leave_ledger_reference", "leave_balance_ledger",
            ["reference_type", "reference_id"],
        )

    # ---- leave_balances additive columns ---------------------------
    if not _has_column(bind, "leave_balances", "allocated_balance"):
        op.add_column("leave_balances",
                      sa.Column("allocated_balance", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column(bind, "leave_balances", "pending_balance"):
        op.add_column("leave_balances",
                      sa.Column("pending_balance", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column(bind, "leave_balances", "row_version"):
        op.add_column("leave_balances",
                      sa.Column("row_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    for col in ("row_version", "pending_balance", "allocated_balance"):
        if _has_column(bind, "leave_balances", col):
            op.drop_column("leave_balances", col)
    if _has_table(bind, "leave_balance_ledger"):
        op.drop_table("leave_balance_ledger")
