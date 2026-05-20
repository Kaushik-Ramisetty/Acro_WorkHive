"""phase5b: accrual policy on leave_types + optional flag on holidays.

Revision ID: 0006_phase5b_accrual_carryforward
Revises: 0005_phase5a_ledger
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase5b_accrual_carryforward"
down_revision: Union[str, None] = "0005_phase5a_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "leave_types", "accrual_frequency"):
        op.add_column("leave_types",
                      sa.Column("accrual_frequency", sa.String(length=10), nullable=True))
    if not _has_column(bind, "leave_types", "accrual_days_per_cycle"):
        op.add_column("leave_types",
                      sa.Column("accrual_days_per_cycle", sa.Integer(), nullable=True))
    if not _has_column(bind, "leave_types", "probation_months"):
        op.add_column("leave_types",
                      sa.Column("probation_months", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column(bind, "holidays", "is_optional"):
        op.add_column("holidays",
                      sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    bind = op.get_bind()
    for col in ("probation_months", "accrual_days_per_cycle", "accrual_frequency"):
        if _has_column(bind, "leave_types", col):
            op.drop_column("leave_types", col)
    if _has_column(bind, "holidays", "is_optional"):
        op.drop_column("holidays", "is_optional")
