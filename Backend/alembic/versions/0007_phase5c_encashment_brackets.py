"""phase5c: encashment_requests, leave_accrual_brackets,
team_capacity_policies.max_concurrent_percent, and a SQL Server
INSTEAD OF UPDATE/DELETE trigger to enforce ledger immutability.

The trigger is created only on `mssql` dialects; on SQLite/Postgres it's
a no-op (immutability is contractually enforced by the service layer).

Revision ID: 0007_phase5c_encashment_brackets
Revises: 0006_phase5b_accrual_carryforward
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase5c_encashment_brackets"
down_revision: Union[str, None] = "0006_phase5b_accrual_carryforward"
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
    dialect = bind.dialect.name

    # ---- encashment_requests --------------------------------------
    if not _has_table(bind, "encashment_requests"):
        op.create_table(
            "encashment_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("leave_type_id", sa.String(length=20),
                      sa.ForeignKey("leave_types.id"), nullable=False, index=True),
            sa.Column("year", sa.Integer(), nullable=False, index=True),
            sa.Column("days", sa.Integer(), nullable=False),
            sa.Column("rate_per_day", sa.Float(), nullable=True),
            sa.Column("reason", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", index=True),
            sa.Column("approved_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("rejected_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
            sa.Column("rejection_reason", sa.String(length=500), nullable=True),
            sa.Column("payroll_sync_status", sa.String(length=20), nullable=False,
                      server_default="na", index=True),
            sa.Column("payroll_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("days > 0", name="ck_encashment_days_positive"),
        )

    # ---- leave_accrual_brackets -----------------------------------
    if not _has_table(bind, "leave_accrual_brackets"):
        op.create_table(
            "leave_accrual_brackets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("leave_type_id", sa.String(length=20),
                      sa.ForeignKey("leave_types.id"), nullable=False, index=True),
            sa.Column("min_years", sa.Integer(), nullable=False),
            sa.Column("bonus_days_per_cycle", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("min_years >= 0", name="ck_bracket_min_years"),
            sa.CheckConstraint("bonus_days_per_cycle > 0", name="ck_bracket_bonus_positive"),
        )

    # ---- team_capacity_policies.max_concurrent_percent ------------
    if not _has_column(bind, "team_capacity_policies", "max_concurrent_percent"):
        op.add_column(
            "team_capacity_policies",
            sa.Column("max_concurrent_percent", sa.Integer(), nullable=True),
        )

    # ---- SQL Server ledger immutability trigger -------------------
    # SQL Server is the only target where we add an in-database trigger;
    # SQLite (dev) and Postgres rely on the service-layer contract.
    if dialect == "mssql":
        op.execute("""
        IF OBJECT_ID('trg_leave_balance_ledger_immutable', 'TR') IS NOT NULL
            DROP TRIGGER trg_leave_balance_ledger_immutable;
        """)
        op.execute("""
        CREATE TRIGGER trg_leave_balance_ledger_immutable
        ON leave_balance_ledger
        INSTEAD OF UPDATE, DELETE
        AS
        BEGIN
            RAISERROR ('leave_balance_ledger is append-only; UPDATE/DELETE rejected. Post a compensating entry instead.', 16, 1);
            ROLLBACK TRANSACTION;
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "mssql":
        op.execute("""
        IF OBJECT_ID('trg_leave_balance_ledger_immutable', 'TR') IS NOT NULL
            DROP TRIGGER trg_leave_balance_ledger_immutable;
        """)

    if _has_column(bind, "team_capacity_policies", "max_concurrent_percent"):
        op.drop_column("team_capacity_policies", "max_concurrent_percent")

    if _has_table(bind, "leave_accrual_brackets"):
        op.drop_table("leave_accrual_brackets")
    if _has_table(bind, "encashment_requests"):
        op.drop_table("encashment_requests")
