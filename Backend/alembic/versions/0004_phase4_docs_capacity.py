"""phase4: leave documents + team capacity + blackout periods.

Revision ID: 0004_phase4_docs_capacity
Revises: 0003_phase3_payroll_sync
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4_docs_capacity"
down_revision: Union[str, None] = "0003_phase3_payroll_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "leave_documents"):
        op.create_table(
            "leave_documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("leave_request_id", sa.String(length=20),
                      sa.ForeignKey("leave_requests.id"), nullable=False, index=True),
            sa.Column("uploaded_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_path", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scan_status", sa.String(length=20), nullable=False,
                      server_default="pending", index=True),
            sa.Column("scan_engine", sa.String(length=40), nullable=True),
            sa.Column("scan_detail", sa.String(length=300), nullable=True),
            sa.Column("scanned_at", sa.DateTime(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table(bind, "team_capacity_policies"):
        op.create_table(
            "team_capacity_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("manager_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("max_concurrent_on_leave", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table(bind, "blackout_periods"):
        op.create_table(
            "blackout_periods",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope_type", sa.String(length=20), nullable=False, index=True),
            sa.Column("scope_id", sa.String(length=40), nullable=True, index=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.String(length=300), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for t in ("blackout_periods", "team_capacity_policies", "leave_documents"):
        if _has_table(bind, t):
            op.drop_table(t)
