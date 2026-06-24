"""Sources business logic: list, add (via Miniflux), update, pause/hard-delete."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import bad_request, conflict, not_found
from niouzou.models import Article, Source
from niouzou.models.article import STATUS_PENDING
from niouzou.schemas.sources import SourceOut, SourcesListResponse
from niouzou.services.miniflux_bootstrap import get_miniflux_token
from niouzou.services.miniflux_client import MinifluxClient

logger = logging.getLogger("niouzou.sources")

# E19-S5 — how many of a feed's recent entries to seed a freshly-added source
# with. ~30 ≈ what an RSS feed typically exposes; enough for instant content
# without a heavy first enrichment pass.
_BACKFILL_ENTRIES = 30


class SourcesService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def _client(self) -> MinifluxClient:
        settings = get_settings()
        token = await get_miniflux_token()
        return MinifluxClient(settings.miniflux_url, token)

    async def list_sources(self, user_id: uuid.UUID) -> SourcesListResponse:
        # E13-S5: paused sources (deleted_at NOT NULL) are returned too — the
        # Sources screen shows them dimmed with an OFF switch so the user can
        # re-enable them. Feed/Explore still filter them out via the SQL
        # ``s.deleted_at IS NULL`` predicate added to ranked_query.
        rows = (
            await self.session.scalars(
                select(Source)
                .where(Source.user_id == user_id)
                .order_by(Source.created_at.desc())
            )
        ).all()
        if not rows:
            return SourcesListResponse(sources=[])

        # The crawler flag lives on the shared Miniflux feed — fetch the whole
        # feed list once and join client-side rather than N requests.
        crawler_by_feed = await self._crawler_state_map()

        # E17-S6 — article volume per source (total + last 24h), one grouped
        # query rather than N counts.
        counts = await self._article_counts([s.id for s in rows])

        sources: list[SourceOut] = []
        for s in rows:
            out = SourceOut.model_validate(s)
            out.fetch_full_content = crawler_by_feed.get(s.miniflux_feed_id, False)
            out.active = s.deleted_at is None
            total, last_24h = counts.get(s.id, (0, 0))
            out.article_count_total = total
            out.article_count_24h = last_24h
            sources.append(out)
        return SourcesListResponse(sources=sources)

    async def _article_counts(
        self, source_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, int]]:
        """Map source id → (total articles, articles ingested in last 24h).

        Counts every ingested article (status-agnostic) — a source's raw
        output — keyed on ``created_at`` for the rolling window. Sources with
        no articles are absent from the map; callers default to ``(0, 0)``.
        """
        if not source_ids:
            return {}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            await self.session.execute(
                select(
                    Article.source_id,
                    func.count().label("total"),
                    func.count(case((Article.created_at > cutoff, 1))).label("last_24h"),
                )
                .where(Article.source_id.in_(source_ids))
                .group_by(Article.source_id)
            )
        ).all()
        return {r.source_id: (r.total, r.last_24h) for r in rows}

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
            await self._backfill_source(
                existing.id, user_id, existing.miniflux_feed_id
            )
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
        await self._backfill_source(source.id, user_id, feed_id)
        out = SourceOut.model_validate(source)
        out.fetch_full_content = fetch_full_content
        return out

    async def _backfill_source(
        self,
        source_id: uuid.UUID,
        user_id: uuid.UUID,
        miniflux_feed_id: int,
    ) -> int:
        """Seed a freshly-added source with the feed's recent backlog (E19-S5).

        ``cron_fetch`` only ever pulls *unread* entries and marks them read, so
        a new subscriber to an already-consumed feed (common on a shared
        Miniflux) would otherwise see nothing until brand-new entries are
        published. This pulls the feed's recent entries directly — read ones
        included — and inserts them as pending articles for this source, with
        the same per-``(user, url)`` dedup as ``cron_fetch``. The subsequent
        ``trigger_pipeline_run`` (router background task) enriches them.

        Best-effort: a Miniflux hiccup logs and returns 0 rather than failing
        the source add. Returns the number of articles inserted.
        """
        try:
            async with await self._client() as client:
                entries = await client.list_feed_entries(
                    miniflux_feed_id, max_entries=_BACKFILL_ENTRIES
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "backfill: Miniflux fetch failed for feed %s — %s",
                miniflux_feed_id,
                exc,
            )
            return 0
        if not entries:
            return 0

        # Drop URLs this user already has via any of their sources, and any
        # duplicate URL within this batch (two entries reprinting one URL).
        urls = list({e.url for e in entries})
        existing_rows = await self.session.execute(
            select(Article.url)
            .join(Source, Source.id == Article.source_id)
            .where(Source.user_id == user_id, Article.url.in_(urls))
        )
        existing: set[str] = {r[0] for r in existing_rows.all()}

        seen: set[str] = set()
        values: list[dict] = []
        for e in entries:
            if e.url in existing or e.url in seen:
                continue
            seen.add(e.url)
            values.append(
                {
                    "source_id": source_id,
                    "miniflux_entry_id": e.id,
                    "url": e.url,
                    "title": e.title,
                    "content": e.content,
                    "og_image_url": e.og_image_url,
                    "published_at": e.published_at,
                    "status": STATUS_PENDING,
                }
            )
        if not values:
            return 0

        stmt = pg_insert(Article).values(values).on_conflict_do_nothing(
            index_elements=["source_id", "miniflux_entry_id"]
        )
        await self.session.execute(stmt)
        logger.info(
            "backfill: seeded %d article(s) for source %s (feed %s)",
            len(values),
            source_id,
            miniflux_feed_id,
        )
        return len(values)

    async def update_source(
        self,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        *,
        fetch_full_content: bool | None = None,
        active: bool | None = None,
    ) -> SourceOut:
        if fetch_full_content is None and active is None:
            raise bad_request("No fields to update")
        # ``active`` toggles the soft state (paused vs running) and is allowed
        # on rows currently inactive too; ``fetch_full_content`` only applies
        # to active rows since it round-trips to Miniflux on the shared feed.
        require_active = active is None and fetch_full_content is not None
        source = await self.session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                *(
                    (Source.deleted_at.is_(None),)
                    if require_active
                    else ()
                ),
            )
        )
        if source is None:
            raise not_found("Source not found")

        if active is not None:
            was_active = source.deleted_at is None
            source.deleted_at = None if active else datetime.now(timezone.utc)
            # E14-S2 — propagate the pause/resume to Miniflux only when no
            # other active subscriber shares this feed. Failures are logged
            # but don't roll back the Niouzou transition (cron_fetch will
            # mark-read any leftover entries via E14-S1).
            if active and not was_active:
                await self._maybe_resume_feed(source)
            elif not active and was_active:
                await self._maybe_pause_feed(source)

        if fetch_full_content is not None:
            await self._set_crawler(source.miniflux_feed_id, fetch_full_content)

        # Derive the response: fetch_full_content from the request when set,
        # otherwise fall back to whatever Miniflux currently reports.
        crawler = fetch_full_content
        if crawler is None:
            crawler_by_feed = await self._crawler_state_map()
            crawler = crawler_by_feed.get(source.miniflux_feed_id, False)

        out = SourceOut.model_validate(source)
        out.fetch_full_content = crawler
        out.active = source.deleted_at is None
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

    async def deactivate_source(
        self, user_id: uuid.UUID, source_id: uuid.UUID
    ) -> None:
        """Soft pause: keeps articles in DB but hides them from Feed/Explore.

        E14-S2 — also tells Miniflux to stop polling the feed if no other
        active source shares it, so its unread entries don't pile up and
        eventually saturate ``cron_fetch``'s oldest-first window.
        """
        source = await self.session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                Source.deleted_at.is_(None),
            )
        )
        if source is None:
            raise not_found("Source not found")
        source.deleted_at = datetime.now(timezone.utc)
        await self._maybe_pause_feed(source)

    async def hard_delete_source(
        self, user_id: uuid.UUID, source_id: uuid.UUID
    ) -> None:
        """Wipe the source + dependents via FK CASCADE (E13-S5).

        E14-S2 — also unsubscribes Miniflux from the feed if no other source
        (active or paused) references it; otherwise leaves it alone so the
        other subscribers keep receiving entries.
        """
        source = await self.session.scalar(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
            )
        )
        if source is None:
            raise not_found("Source not found")
        feed_id = source.miniflux_feed_id
        others = await self._count_other_subscribers(feed_id, source.id)
        await self.session.delete(source)
        if others == 0:
            await self._safe_delete_feed(feed_id)

    # ── E14-S2 — Miniflux propagation helpers ─────────────────────────────

    async def _count_other_active_subscribers(
        self, feed_id: int, source_id: uuid.UUID
    ) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Source)
                .where(
                    Source.miniflux_feed_id == feed_id,
                    Source.deleted_at.is_(None),
                    Source.id != source_id,
                )
            )
        ) or 0

    async def _count_other_subscribers(
        self, feed_id: int, source_id: uuid.UUID
    ) -> int:
        """Count any source (active or paused) referencing this feed, except
        the one in transition. Used by ``hard_delete_source`` to decide
        whether to delete the Miniflux feed itself."""
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Source)
                .where(
                    Source.miniflux_feed_id == feed_id,
                    Source.id != source_id,
                )
            )
        ) or 0

    async def _maybe_pause_feed(self, source: Source) -> None:
        """Disable polling in Miniflux iff this source was the last active
        subscriber on the shared feed."""
        if await self._count_other_active_subscribers(
            source.miniflux_feed_id, source.id
        ):
            return
        await self._safe_set_disabled(source.miniflux_feed_id, True)

    async def _maybe_resume_feed(self, source: Source) -> None:
        """Re-enable polling in Miniflux iff no other active subscriber
        already kept the feed enabled."""
        if await self._count_other_active_subscribers(
            source.miniflux_feed_id, source.id
        ):
            return
        await self._safe_set_disabled(source.miniflux_feed_id, False)

    async def _safe_set_disabled(self, feed_id: int, disabled: bool) -> None:
        """Best-effort ``PUT /v1/feeds/:id {disabled}``. WARN on failure but
        do not propagate — Niouzou is the source of truth; ``cron_fetch``
        (E14-S1) cleans up any unread that slip through."""
        try:
            async with await self._client() as miniflux:
                await miniflux.update_feed(feed_id, disabled=disabled)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Miniflux update_feed(%s, disabled=%s) failed: %s",
                feed_id,
                disabled,
                exc,
            )

    async def _safe_delete_feed(self, feed_id: int) -> None:
        """Best-effort ``DELETE /v1/feeds/:id``. Same failure policy as
        ``_safe_set_disabled`` — orphaned Miniflux feeds will be drained by
        ``cron_fetch`` regardless."""
        try:
            async with await self._client() as miniflux:
                await miniflux.delete_feed(feed_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Miniflux delete_feed(%s) failed: %s", feed_id, exc
            )
