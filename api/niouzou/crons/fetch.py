"""cron_fetch — pull new entries from Miniflux into the Niouzou DB.

Run with: ``uv run python -m niouzou.crons.fetch`` (or via the cron container).

Flow:
  1. Pull unread entries from Miniflux (oldest first).
  2. Map each entry to a Niouzou source via its Miniflux feed id.
  3. Insert new articles with status='pending', deduplicating on
     miniflux_entry_id (ON CONFLICT DO NOTHING — running twice is a no-op).
  4. Mark **both** matched (ingested) AND unmatched (orphan-feed) entries as
     read in Miniflux so neither category re-surfaces on the next tick.

Entries whose feed has no active registered Niouzou source (E14-S1) are
noise: never inserted in DB, never enriched, no LLM tokens spent. They are
marked read defensively so they can't saturate the oldest-first fetch
window and block the pipeline when a source is paused/deleted without the
Miniflux side being synced (e.g., manual changes via Miniflux UI, or a
transient failure in the source-lifecycle propagation).
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
from niouzou.services.miniflux_bootstrap import get_miniflux_token
from niouzou.services.miniflux_client import MinifluxClient, MinifluxEntry

logger = logging.getLogger("niouzou.cron_fetch")


async def _source_ids_by_feed(session: AsyncSession) -> dict[int, list[str]]:
    """Map Miniflux feed id → list of Niouzou source ids.

    Multiple users can subscribe to the same RSS URL — Miniflux deduplicates
    those at the feed level, so a single ``miniflux_feed_id`` may back several
    ``Source`` rows (one per user). Each entry needs to be ingested as a
    separate article for every subscribing source.
    """
    rows = await session.execute(
        select(Source.miniflux_feed_id, Source.id).where(Source.deleted_at.is_(None))
    )
    mapping: dict[int, list[str]] = {}
    for feed_id, source_id in rows.all():
        mapping.setdefault(feed_id, []).append(source_id)
    return mapping


async def _insert_articles(
    session: AsyncSession,
    entries: list[MinifluxEntry],
    feed_to_sources: dict[int, list[str]],
) -> int:
    """Insert articles for matched entries; skip duplicates. Returns # rows tried."""
    values = [
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
        for e in entries
        if e.feed_id in feed_to_sources
        for source_id in feed_to_sources[e.feed_id]
    ]
    if not values:
        return 0
    # (source_id, miniflux_entry_id) is the per-user uniqueness key: two users
    # subscribed to the same feed each get their own article row, but a rerun
    # for the same user is a no-op.
    stmt = pg_insert(Article).values(values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["source_id", "miniflux_entry_id"]
    )
    await session.execute(stmt)
    return len(values)


async def run() -> int:
    """Execute one fetch cycle. Returns the number of entries marked read."""
    settings = get_settings()

    logger.info("cron_fetch: start (batch_size=%d)", settings.miniflux_fetch_batch_size)
    token = await get_miniflux_token()
    async with MinifluxClient(settings.miniflux_url, token) as miniflux:
        logger.info("cron_fetch: fetching unread entries from Miniflux...")
        entries = await miniflux.list_unread_entries(
            max_entries=settings.miniflux_fetch_batch_size
        )
        logger.info("cron_fetch: received %d entries from Miniflux", len(entries))
        if not entries:
            logger.info("cron_fetch: no unread entries — done")
            return 0

        async with session_scope() as session:
            feed_to_sources = await _source_ids_by_feed(session)
            matched = [e for e in entries if e.feed_id in feed_to_sources]
            unmatched = [e for e in entries if e.feed_id not in feed_to_sources]
            logger.info(
                "cron_fetch: %d entries match a Niouzou source (%d unmatched)",
                len(matched),
                len(unmatched),
            )
            inserted = await _insert_articles(session, matched, feed_to_sources)
            logger.info("cron_fetch: inserted %d article rows (post-fanout)", inserted)

        if unmatched:
            logger.warning(
                "cron_fetch: %d entries skipped (no active Niouzou source for "
                "their feed) — marking read so they can't saturate the fetch "
                "window",
                len(unmatched),
            )

        # E14-S1 — Mark BOTH matched (ingested) and unmatched (orphan) entries
        # as read. Done after the DB commit above so a crash during insertion
        # raises before we reach this line, leaving everything unread for the
        # next run (crash-safe). Unmatched are never inserted in DB and never
        # enriched, so no LLM tokens are spent on them.
        matched_ids = [e.id for e in matched]
        unmatched_ids = [e.id for e in unmatched]
        await miniflux.mark_entries_read(matched_ids + unmatched_ids)
        logger.info(
            "cron_fetch: marked %d matched + %d unmatched as read in Miniflux",
            len(matched_ids),
            len(unmatched_ids),
        )
        logger.info(
            "cron_fetch: done — ingested %d entries (%d total fetched)",
            len(matched_ids),
            len(entries),
        )
        return len(matched_ids)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
