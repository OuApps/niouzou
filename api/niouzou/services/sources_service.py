"""Sources business logic: list, add (via Miniflux), soft-delete."""

import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import bad_request, conflict, not_found
from niouzou.models import Source
from niouzou.schemas.sources import SourceOut, SourcesListResponse
from niouzou.services.miniflux_bootstrap import get_miniflux_token
from niouzou.services.miniflux_client import MinifluxClient

logger = logging.getLogger("niouzou.sources")


class SourcesService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def _client(self) -> MinifluxClient:
        settings = get_settings()
        token = await get_miniflux_token()
        return MinifluxClient(settings.miniflux_url, token)

    async def list_sources(self, user_id: uuid.UUID) -> SourcesListResponse:
        rows = await self.session.scalars(
            select(Source)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
            .order_by(Source.created_at.desc())
        )
        return SourcesListResponse(
            sources=[SourceOut.model_validate(s) for s in rows.all()]
        )

    async def create_source(self, user_id: uuid.UUID, url: str) -> SourceOut:
        existing = await self.session.scalar(
            select(Source).where(Source.user_id == user_id, Source.url == url)
        )
        if existing is not None:
            if existing.deleted_at is None:
                raise conflict("Source already exists for this user")
            # Re-subscribing to a previously removed feed: revive the row,
            # reusing its Miniflux feed id rather than creating a duplicate.
            existing.deleted_at = None
            await self.session.flush()
            return SourceOut.model_validate(existing)

        feed_id, name = await self._register_in_miniflux(url)

        source = Source(
            user_id=user_id, miniflux_feed_id=feed_id, url=url, name=name
        )
        self.session.add(source)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # (user_id, miniflux_feed_id) already taken — same feed, other URL.
            raise conflict("Source already exists for this user") from exc
        return SourceOut.model_validate(source)

    async def _register_in_miniflux(self, url: str) -> tuple[int, str]:
        async with await self._client() as miniflux:
            try:
                category_id = await miniflux.default_category_id()
                feed_id = await miniflux.create_feed(url, category_id=category_id)
                feed = await miniflux.get_feed(feed_id)
            except httpx.HTTPStatusError as exc:
                logger.warning("Miniflux feed creation failed for %s: %s", url, exc)
                raise bad_request(
                    "Could not subscribe to this feed — check the URL"
                ) from exc
        return feed.id, feed.title

    async def delete_source(self, user_id: uuid.UUID, source_id: uuid.UUID) -> None:
        source = await self.session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                Source.deleted_at.is_(None),
            )
        )
        if source is None:
            raise not_found("Source not found")
        # Soft delete: keep the row so existing articles keep a valid FK.
        source.deleted_at = datetime.now(timezone.utc)
