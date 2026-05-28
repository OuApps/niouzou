"""cron_fetch — pull new entries from Miniflux into the Niouzou DB.

Run with: ``uv run python -m niouzou.crons.fetch`` (or via the cron container).

Flow:
  1. Pull unread entries from Miniflux (oldest first).
  2. Map each entry to a Niouzou source via its Miniflux feed id.
  3. Insert new articles with status='pending', deduplicating on
     miniflux_entry_id (ON CONFLICT DO NOTHING — running twice is a no-op).
  4. Mark the handled entries as read in Miniflux so they aren't re-fetched.

Entries whose feed has no registered Niouzou source are left untouched
(not ingested, not marked read) and logged — they belong to a feed nobody
subscribed to through Niouzou.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.db import session_scope
from niouzou.models import Article, Source
from niouzou.models.article import STATUS_PENDING
from niouzou.services.miniflux_client import MinifluxClient, MinifluxEntry

logger = logging.getLogger("niouzou.cron_fetch")


async def _source_id_by_feed(session: AsyncSession) -> dict[int, str]:
    """Map Miniflux feed id → Niouzou source id.

    Within a single shared Miniflux instance a feed id is unique, so the
    mapping is unambiguous for the MVP single-tenant deployment.
    """
    rows = await session.execute(select(Source.miniflux_feed_id, Source.id))
    return {feed_id: source_id for feed_id, source_id in rows.all()}


async def _insert_articles(
    session: AsyncSession, entries: list[MinifluxEntry], feed_to_source: dict[int, str]
) -> int:
    """Insert articles for matched entries; skip duplicates. Returns # rows tried."""
    values = [
        {
            "source_id": feed_to_source[e.feed_id],
            "miniflux_entry_id": e.id,
            "url": e.url,
            "title": e.title,
            "content": e.content,
            "og_image_url": e.og_image_url,
            "published_at": e.published_at,
            "status": STATUS_PENDING,
        }
        for e in entries
        if e.feed_id in feed_to_source
    ]
    if not values:
        return 0
    stmt = pg_insert(Article).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=["miniflux_entry_id"])
    await session.execute(stmt)
    return len(values)


async def run() -> int:
    """Execute one fetch cycle. Returns the number of entries marked read."""
    settings = get_settings()

    async with MinifluxClient(
        settings.miniflux_url, settings.miniflux_api_key
    ) as miniflux:
        entries = await miniflux.list_unread_entries(
            max_entries=settings.miniflux_fetch_batch_size
        )
        if not entries:
            logger.info("cron_fetch: no unread entries")
            return 0

        async with session_scope() as session:
            feed_to_source = await _source_id_by_feed(session)
            matched = [e for e in entries if e.feed_id in feed_to_source]
            unmatched = len(entries) - len(matched)
            await _insert_articles(session, matched, feed_to_source)

        if unmatched:
            logger.warning(
                "cron_fetch: %d entries skipped (no Niouzou source for their feed)",
                unmatched,
            )

        # Only mark read the entries we ingested. Done after the DB commit so a
        # crash mid-insert leaves them unread for the next run.
        handled_ids = [e.id for e in matched]
        await miniflux.mark_entries_read(handled_ids)
        logger.info(
            "cron_fetch: ingested %d entries (%d total fetched)",
            len(handled_ids),
            len(entries),
        )
        return len(handled_ids)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
