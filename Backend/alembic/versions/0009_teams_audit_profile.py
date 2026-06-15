"""teams + team_members + resource_allocation_audit + employee profile fields.

Revision ID: 0009_teams_audit_profile
Revises: 0008_resource_allocation
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_teams_audit_profile"
down_revision: Union[str, None] = "0008_resource_allocation"
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

    if not _has_table(bind, "teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=120), nullable=False, index=True),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("department_id", sa.String(length=20),
                      sa.ForeignKey("departments.id"), nullable=True, index=True),
            sa.Column("lead_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True, index=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", "department_id", name="uq_team_name_per_dept"),
        )

    if not _has_table(bind, "team_members"):
        op.create_table(
            "team_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("team_id", sa.Integer(),
                      sa.ForeignKey("teams.id"), nullable=False, index=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=False, index=True),
            sa.Column("role_in_team", sa.String(length=60), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("added_by", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("removed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("team_id", "employee_id", name="uq_team_member"),
        )

    if not _has_table(bind, "resource_allocation_audit"):
        op.create_table(
            "resource_allocation_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("action", sa.String(length=40), nullable=False, index=True),
            sa.Column("employee_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True, index=True),
            sa.Column("project_id", sa.String(length=20),
                      sa.ForeignKey("projects.id"), nullable=True, index=True),
            sa.Column("allocation_id", sa.Integer(),
                      sa.ForeignKey("resource_allocations.id"), nullable=True, index=True),
            sa.Column("team_id", sa.Integer(),
                      sa.ForeignKey("teams.id"), nullable=True, index=True),
            sa.Column("actor_id", sa.Integer(),
                      sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        )

    if not _has_column(bind, "employees", "experience_years"):
        op.add_column("employees",
                      sa.Column("experience_years", sa.Integer(), nullable=True))
    if not _has_column(bind, "employees", "certifications"):
        op.add_column("employees",
                      sa.Column("certifications", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for col in ("certifications", "experience_years"):
        if _has_column(bind, "employees", col):
            op.drop_column("employees", col)
    for t in ("resource_allocation_audit", "team_members", "teams"):
        if _has_table(bind, t):
            op.drop_table(t)
