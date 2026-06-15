"""Alembic env. Reads DATABASE_URL from the same place the app does."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure the Backend/ root is on sys.path so `app.*` imports resolve when
# alembic is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import after sys.path tweak. These imports pull in all models so
# Base.metadata is fully populated for autogenerate.
from app.db.base import Base  # noqa: E402
import app.models  # noqa: F401, E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull the URL from env at runtime (CLAUDE.md: DATABASE_URL is the source of truth).
db_url = os.getenv("DATABASE_URL") or "sqlite:///./hrms.db"
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=db_url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=db_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
