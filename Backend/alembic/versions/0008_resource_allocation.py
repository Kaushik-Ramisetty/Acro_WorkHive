"""resource_allocations + employee_skills + scheduler_health.

Revision ID: 0008_resource_allocation
Revises: 0007_phase5c_encashment_brackets
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_resource_allocation"
down_revision: Union[str, None] = "0007_phase5c_encashment_brackets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "resource_allocations"):
        op.create_table(
            "resource_allocations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("project_id", sa.String(length=20),
                      sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("manager_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True, index=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("actual_end_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False,
                      server_default="active", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("status IN ('active','completed')",
                               name="ck_resource_alloc_status"),
        )

    if not _has_table(bind, "employee_skills"):
        op.create_table(
            "employee_skills",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("skill", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("employee_id", "skill", name="uq_employee_skill"),
        )

    if not _has_table(bind, "scheduler_health"):
        op.create_table(
            "scheduler_health",
            sa.Column("task_name", sa.String(length=60), primary_key=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_status", sa.String(length=20), nullable=True),
            sa.Column("last_summary", sa.String(length=500), nullable=True),
            sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for t in ("scheduler_health", "employee_skills", "resource_allocations"):
        if _has_table(bind, t):
            op.drop_table(t)
