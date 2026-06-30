"""Alembic environment, async-aware and driven by niouzou.config.

Run with: ``uv run alembic upgrade head`` from the ``api/`` directory.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# Import all models so their tables are registered on Base.metadata.
import niouzou.models  # noqa: F401
from niouzou.config import get_settings
from niouzou.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# Arbitrary, stable key for the migration advisory lock (any bigint works).
_MIGRATION_LOCK_ID = 776610291


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        # Serialize concurrent ``alembic upgrade head`` runs (e.g. overlapping
        # Railway deploy retries against a fresh DB). Without this, two processes
        # both find no ``alembic_version`` table and race to ``CREATE TABLE``
        # it → ``UniqueViolationError`` on ``pg_type`` and a failed deploy. This
        # transaction-scoped advisory lock makes a second runner block here until
        # the first commits, after which it simply finds the DB already at head.
        # Released automatically at transaction end; a no-op once migrated.
        connection.exec_driver_sql(
            f"SELECT pg_advisory_xact_lock({_MIGRATION_LOCK_ID})"
        )
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
