"""Shared test fixtures.

Env vars are set before any niouzou module is imported so config.get_settings
(lru-cached) picks them up. The cron_fetch integration tests need a reachable
Postgres; they skip cleanly when DATABASE_URL is unset or unreachable.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://niouzou:niouzou@localhost:5432/niouzou"
)
os.environ.setdefault("MINIFLUX_URL", "http://miniflux.test")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
import pytest_asyncio
from sqlalchemy import text

from niouzou.db import async_session_factory, engine
from niouzou.services import embedding_service, miniflux_bootstrap

# Stub the Miniflux token bootstrap for the entire test suite. Production code
# resolves the token by connecting to a sibling `miniflux` database (see
# miniflux_bootstrap.py); tests mock the Miniflux HTTP API with respx, so the
# token value is irrelevant — short-circuit the cache so no DB call happens.
miniflux_bootstrap._cached_key = "test-miniflux-token"


# E16 absolute rule: the real embedding model is NEVER loaded in tests.
# Two layers of defence: the module singleton is pre-seeded with a
# deterministic fake encoder, and the real loader is replaced with a tripwire
# in case some code path constructs its own EmbeddingService.
from tests.fake_embeddings import HashEncoder  # noqa: E402

embedding_service._service = embedding_service.EmbeddingService(HashEncoder())


def _no_real_model() -> embedding_service.Encoder:
    raise RuntimeError(
        "tests must never load the real embedding model — inject a fake "
        "encoder (see tests/fake_embeddings.py)"
    )


embedding_service._load_encoder = _no_real_model


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def db_session():
    """Yield a session against a truncated schema, or skip if no DB."""
    # pytest-asyncio gives each test a fresh event loop; asyncpg connections are
    # loop-bound, so rebuild the pool on the current loop before connecting.
    await engine.dispose()
    if not await _db_reachable():
        pytest.skip("Postgres not reachable — start docker-compose.dev.yml")

    # Clean slate. CASCADE handles FK order; RESTART IDENTITY is harmless here.
    async with async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE users, sources, articles, article_keywords, "
                "article_relevance_scores, article_impressions, "
                "article_feedbacks, keyword_weights, app_settings, "
                "pipeline_runs, compaction_runs, llm_usage_log, "
                "service_account_keys "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session
