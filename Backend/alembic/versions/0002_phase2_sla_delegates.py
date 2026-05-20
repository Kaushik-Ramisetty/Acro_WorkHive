"""phase2: delegate assignments + SLA escalation columns.

Adds:
  - delegate_assignments table
  - leave_requests.sla_escalation_level
  - leave_requests.sla_last_alert_at
  - leave_requests.approver_override_id

Revision ID: 0002_phase2_sla_delegates
Revises: 0001_baseline
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_sla_delegates"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ---- delegate_assignments ---------------------------------------
    if not _has_table(bind, "delegate_assignments"):
        op.create_table(
            "delegate_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("manager_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("delegate_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.String(length=300), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    # ---- leave_requests SLA columns ---------------------------------
    if not _has_column(bind, "leave_requests", "sla_escalation_level"):
        op.add_column(
            "leave_requests",
            sa.Column("sla_escalation_level", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(bind, "leave_requests", "sla_last_alert_at"):
        op.add_column(
            "leave_requests",
            sa.Column("sla_last_alert_at", sa.DateTime(), nullable=True),
        )
    if not _has_column(bind, "leave_requests", "approver_override_id"):
        op.add_column(
            "leave_requests",
            sa.Column("approver_override_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "leave_requests", "approver_override_id"):
        op.drop_column("leave_requests", "approver_override_id")
    if _has_column(bind, "leave_requests", "sla_last_alert_at"):
        op.drop_column("leave_requests", "sla_last_alert_at")
    if _has_column(bind, "leave_requests", "sla_escalation_level"):
        op.drop_column("leave_requests", "sla_escalation_level")
    if _has_table(bind, "delegate_assignments"):
        op.drop_table("delegate_assignments")
