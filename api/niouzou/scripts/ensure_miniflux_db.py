"""Ensure the `miniflux` database exists on the same Postgres instance.

On Railway we run one Postgres service shared between the API and Miniflux.
The API connects to its own database (whatever `DATABASE_URL` points at);
Miniflux needs a sibling database called `miniflux` on the same server, so
its tables (notably `users`) don't collide with ours.

Runs as a preDeploy step before `alembic upgrade head`. Idempotent: no-op if
the database already exists. Safe to run repeatedly.
"""

import asyncio
import sys
from urllib.parse import urlparse, urlunparse

import asyncpg

from niouzou.config import get_settings

MINIFLUX_DB = "miniflux"


async def _main() -> None:
    url = get_settings().database_url
    # asyncpg wants the plain postgresql:// scheme, not postgresql+asyncpg://.
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)

    # Connect to the maintenance `postgres` database — you cannot CREATE
    # DATABASE while connected to the database you'd be creating, and the
    # `postgres` DB is guaranteed to exist on any Postgres instance.
    parsed = urlparse(url)
    admin_url = urlunparse(parsed._replace(path="/postgres"))

    conn = await asyncpg.connect(admin_url)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", MINIFLUX_DB
        )
        if exists:
            print(f"ensure_miniflux_db: '{MINIFLUX_DB}' already exists, skipping")
            return
        # CREATE DATABASE can't run inside a transaction block; asyncpg
        # auto-commits simple execute() calls, so this is fine.
        await conn.execute(f'CREATE DATABASE "{MINIFLUX_DB}"')
        print(f"ensure_miniflux_db: created database '{MINIFLUX_DB}'")
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except Exception as exc:
        print(f"ensure_miniflux_db: failed — {exc}", file=sys.stderr)
        sys.exit(1)
