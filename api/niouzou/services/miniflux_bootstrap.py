"""Lazy resolution of the Miniflux access token.

Miniflux exposes no HTTP endpoint to mint API keys, but stores them as plain
text in its own ``api_keys`` table. Niouzou shares Postgres with Miniflux on
both stacks (compose and Railway), so the API/crons can read or create a
token directly from that table on first call instead of going through env
vars or shared volumes.

This module:
  1. Derives the miniflux DB URL from ``DATABASE_URL`` (same server, db named
     ``miniflux``).
  2. Polls until Miniflux has finished its own migrations + provisioned the
     admin user (``api_keys`` + ``users`` exist, admin row present).
  3. Returns an existing token with description='niouzou', or generates +
     INSERTs one if none exists. Idempotent.

Result is cached in-process for the lifetime of the API/cron.
"""

import asyncio
import logging
import secrets
from urllib.parse import urlparse, urlunparse

import asyncpg

from niouzou.config import get_settings

logger = logging.getLogger("niouzou.miniflux_bootstrap")

_MINIFLUX_DB = "miniflux"
_DESCRIPTION = "niouzou"
_POLL_INTERVAL_S = 2.0
_POLL_MAX_ATTEMPTS = 60  # ~2 minutes total

_cached_key: str | None = None
_lock = asyncio.Lock()


def _miniflux_dsn() -> str:
    """Build the asyncpg DSN for the sibling miniflux database."""
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{_MINIFLUX_DB}"))


async def _wait_for_miniflux_ready(conn: asyncpg.Connection) -> None:
    """Block until Miniflux has run its migrations + inserted the admin user."""
    for attempt in range(1, _POLL_MAX_ATTEMPTS + 1):
        try:
            row = await conn.fetchval(
                "SELECT 1 FROM users WHERE is_admin = true LIMIT 1"
            )
            if row:
                return
        except asyncpg.UndefinedTableError:
            # Miniflux migrations haven't run yet — `users` / `api_keys` absent.
            pass
        logger.info(
            "miniflux_bootstrap: waiting for Miniflux to be ready (attempt %d)",
            attempt,
        )
        await asyncio.sleep(_POLL_INTERVAL_S)
    raise RuntimeError(
        "Miniflux never became ready (admin user not found within timeout)"
    )


async def _resolve() -> str:
    conn = await asyncpg.connect(_miniflux_dsn())
    try:
        await _wait_for_miniflux_ready(conn)
        existing = await conn.fetchval(
            "SELECT token FROM api_keys WHERE description = $1 LIMIT 1",
            _DESCRIPTION,
        )
        if existing:
            return existing
        token = secrets.token_hex(32)
        await conn.execute(
            """
            INSERT INTO api_keys (user_id, token, description)
            SELECT id, $1, $2 FROM users WHERE is_admin = true
            ORDER BY id LIMIT 1
            ON CONFLICT (user_id, description) DO UPDATE
              SET token = EXCLUDED.token
            """,
            token,
            _DESCRIPTION,
        )
        logger.info("miniflux_bootstrap: provisioned a new API key")
        return token
    finally:
        await conn.close()


async def get_miniflux_token() -> str:
    """Return the Miniflux API key, creating it on first call if needed."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key
    async with _lock:
        if _cached_key is None:
            _cached_key = await _resolve()
        return _cached_key
