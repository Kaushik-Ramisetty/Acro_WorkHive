"""phase3: payroll sync columns on leave_requests.

Tracks per-request payroll-bridge state so a sync failure can be retried
without re-running the entire consumption pipeline.

Revision ID: 0003_phase3_payroll_sync
Revises: 0002_phase2_sla_delegates
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3_payroll_sync"
down_revision: Union[str, None] = "0002_phase2_sla_delegates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    add = lambda col, type_, **kw: op.add_column("leave_requests", sa.Column(col, type_, **kw))  # noqa: E731
    if not _has_column(bind, "leave_requests", "payroll_sync_status"):
        add("payroll_sync_status", sa.String(length=20), nullable=False, server_default="na")
    if not _has_column(bind, "leave_requests", "payroll_synced_at"):
        add("payroll_synced_at", sa.DateTime(), nullable=True)
    if not _has_column(bind, "leave_requests", "payroll_sync_attempts"):
        add("payroll_sync_attempts", sa.Integer(), nullable=False, server_default="0")
    if not _has_column(bind, "leave_requests", "payroll_last_error"):
        add("payroll_last_error", sa.String(length=500), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    for col in ("payroll_last_error", "payroll_sync_attempts",
                "payroll_synced_at", "payroll_sync_status"):
        if _has_column(bind, "leave_requests", col):
            op.drop_column("leave_requests", col)
