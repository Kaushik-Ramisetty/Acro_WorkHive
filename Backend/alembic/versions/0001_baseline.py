"""baseline — captures current schema as the migration starting point.

Existing databases were built by `Base.metadata.create_all` + the
idempotent ALTER blocks in `app/main.py::_run_onboarding_migrations`.
This migration is intentionally empty: run

    alembic stamp head

on an existing database to mark it as already at the baseline. Brand-new
databases continue to be built by `create_all` for now; future revisions
will start replacing the idempotent ALTERs one schema change at a time.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-18
"""
from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
