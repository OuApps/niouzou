"""Async SQLAlchemy engine, session factory, and the declarative Base.

One session per request is wired in the API layer (Epic 3); cron jobs open
their own short-lived sessions via ``session_scope``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from niouzou.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.sqlalchemy_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session for scripts and cron jobs.

    Commits on success, rolls back on exception, always closes.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one transactional session per request.

    Commits when the handler returns successfully, rolls back on any error.
    Services do their work and let this dependency own the commit boundary.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
