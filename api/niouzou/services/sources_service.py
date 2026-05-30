"""Sources business logic: list, add (via Miniflux), update, soft-delete."""

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
        rows = (
            await self.session.scalars(
                select(Source)
                .where(Source.user_id == user_id, Source.deleted_at.is_(None))
                .order_by(Source.created_at.desc())
            )
        ).all()
        if not rows:
            return SourcesListResponse(sources=[])

        # The crawler flag lives on the shared Miniflux feed — fetch the whole
        # feed list once and join client-side rather than N requests.
        crawler_by_feed = await self._crawler_state_map()

        sources: list[SourceOut] = []
        for s in rows:
            out = SourceOut.model_validate(s)
            out.fetch_full_content = crawler_by_feed.get(s.miniflux_feed_id, False)
            sources.append(out)
        return SourcesListResponse(sources=sources)

    async def _crawler_state_map(self) -> dict[int, bool]:
        """Map of Miniflux feed id → current ``crawler`` flag.

        Returns an empty map on any Miniflux failure so a degraded backend
        doesn't 500 ``GET /sources`` — the PWA will just see crawler=false
        until the next reload.
        """
        try:
            async with await self._client() as miniflux:
                feeds = await miniflux.list_feeds()
        except Exception as exc:  # noqa: BLE001 — crawler flag is informational
            logger.warning("Miniflux list_feeds failed; defaulting crawler=false: %s", exc)
            return {}
        return {f.id: f.crawler for f in feeds}

    async def create_source(
        self,
        user_id: uuid.UUID,
        url: str,
        *,
        fetch_full_content: bool = False,
    ) -> SourceOut:
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
            if fetch_full_content:
                await self._set_crawler(existing.miniflux_feed_id, True)
            out = SourceOut.model_validate(existing)
            out.fetch_full_content = fetch_full_content
            return out

        feed_id, name = await self._register_in_miniflux(
            url, fetch_full_content=fetch_full_content
        )

        source = Source(
            user_id=user_id, miniflux_feed_id=feed_id, url=url, name=name
        )
        self.session.add(source)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # (user_id, miniflux_feed_id) already taken — same feed, other URL.
            raise conflict("Source already exists for this user") from exc
        out = SourceOut.model_validate(source)
        out.fetch_full_content = fetch_full_content
        return out

    async def update_source(
        self,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        *,
        fetch_full_content: bool,
    ) -> SourceOut:
        source = await self.session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                Source.deleted_at.is_(None),
            )
        )
        if source is None:
            raise not_found("Source not found")

        await self._set_crawler(source.miniflux_feed_id, fetch_full_content)
        out = SourceOut.model_validate(source)
        out.fetch_full_content = fetch_full_content
        return out

    async def _set_crawler(self, feed_id: int, crawler: bool) -> None:
        async with await self._client() as miniflux:
            try:
                await miniflux.update_feed(feed_id, crawler=crawler)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Miniflux update_feed(%s, crawler=%s) failed: %s",
                    feed_id,
                    crawler,
                    exc,
                )
                raise bad_request(
                    "Could not update this source on Miniflux"
                ) from exc

    async def _register_in_miniflux(
        self, url: str, *, fetch_full_content: bool
    ) -> tuple[int, str]:
        async with await self._client() as miniflux:
            try:
                category_id = await miniflux.default_category_id()
                feed_id = await miniflux.create_feed(
                    url, category_id=category_id, crawler=fetch_full_content
                )
            except httpx.HTTPStatusError as exc:
                # Miniflux rejects a second subscription to the same URL with a
                # 4xx ("This feed already exists."). In a multi-user deployment
                # that is a normal case: reuse the existing feed id instead of
                # erroring out, so both users can subscribe to the same source.
                existing_id = await miniflux.find_feed_by_url(url)
                if existing_id is None:
                    logger.warning(
                        "Miniflux feed creation failed for %s: %s", url, exc
                    )
                    raise bad_request(
                        "Could not subscribe to this feed — check the URL"
                    ) from exc
                feed_id = existing_id
                # Last-write-wins: if this subscriber explicitly opted into
                # full-content fetching, propagate it to the shared feed.
                # If they did not, leave whatever value the prior subscriber
                # set so we don't silently downgrade other users.
                if fetch_full_content:
                    await miniflux.update_feed(feed_id, crawler=True)
            feed = await miniflux.get_feed(feed_id)
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
