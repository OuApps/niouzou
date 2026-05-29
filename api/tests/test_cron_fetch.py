"""Integration tests for cron_fetch (E2-S3).

Miniflux HTTP is mocked with respx; the DB is the real local Postgres
(skipped if unreachable, see conftest).
"""

import json

import httpx
import pytest
import respx
from sqlalchemy import func, select

from niouzou.crons import fetch
from niouzou.models import Article, Source, User

BASE = "http://miniflux.test"


def _entry(entry_id: int, feed_id: int) -> dict:
    return {
        "id": entry_id,
        "feed_id": feed_id,
        "title": f"Title {entry_id}",
        "url": f"https://example.com/{entry_id}",
        "content": "<p>body</p>",
        "published_at": "2024-01-15T10:00:00Z",
    }


async def _seed_source(session) -> int:
    """Create a user + one source on Miniflux feed 1. Returns the feed id."""
    user = User(email="u@test.dev", password_hash="x")
    session.add(user)
    await session.flush()
    session.add(
        Source(user_id=user.id, miniflux_feed_id=1, url="https://feed", name="Feed")
    )
    await session.commit()
    return 1


def _mock_miniflux(entries: list[dict]):
    """Mock the unread-entries GET (one page then empty) and the read PUT."""
    respx.get(f"{BASE}/v1/entries").mock(
        side_effect=[
            httpx.Response(200, json={"entries": entries}),
            httpx.Response(200, json={"entries": []}),
        ]
    )
    return respx.put(f"{BASE}/v1/entries").mock(return_value=httpx.Response(204))


async def _article_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Article))


@respx.mock
async def test_ingests_matched_entries_and_marks_read(db_session):
    await _seed_source(db_session)
    put_route = _mock_miniflux([_entry(100, feed_id=1), _entry(101, feed_id=1)])

    marked = await fetch.run()

    assert marked == 2
    assert await _article_count(db_session) == 2
    # Both entries marked read in Miniflux.
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [100, 101]


@respx.mock
async def test_running_twice_does_not_duplicate(db_session):
    await _seed_source(db_session)
    _mock_miniflux([_entry(100, feed_id=1)])
    await fetch.run()

    # Second run: Miniflux still serves the same entry (re-mock for fresh calls).
    respx.reset()
    _mock_miniflux([_entry(100, feed_id=1)])
    await fetch.run()

    assert await _article_count(db_session) == 1


@respx.mock
async def test_unmatched_feed_is_skipped_and_not_marked_read(db_session):
    await _seed_source(db_session)  # only feed 1 is registered
    put_route = _mock_miniflux([_entry(100, feed_id=1), _entry(200, feed_id=999)])

    marked = await fetch.run()

    assert marked == 1
    assert await _article_count(db_session) == 1
    # The orphan entry (feed 999) is left unread.
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [100]


@respx.mock
async def test_multi_user_same_feed_ingests_per_source(db_session):
    # Two users subscribed to the same Miniflux feed each get their own row
    # for the same entry (E7-S14).
    user_a = User(email="a@test.dev", password_hash="x")
    user_b = User(email="b@test.dev", password_hash="x")
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    db_session.add_all(
        [
            Source(
                user_id=user_a.id,
                miniflux_feed_id=1,
                url="https://feed",
                name="Feed",
            ),
            Source(
                user_id=user_b.id,
                miniflux_feed_id=1,
                url="https://feed",
                name="Feed",
            ),
        ]
    )
    await db_session.commit()
    put_route = _mock_miniflux([_entry(100, feed_id=1)])

    marked = await fetch.run()

    # One entry × two sources = two article rows; Miniflux still sees one
    # handled entry (the return value is the entry count, not row count).
    assert marked == 1
    assert await _article_count(db_session) == 2
    rows = await db_session.execute(select(Article.source_id))
    assert {sid for (sid,) in rows.all()} == {
        s.id
        for s in (
            await db_session.scalars(select(Source).where(Source.miniflux_feed_id == 1))
        ).all()
    }
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [100]


@respx.mock
async def test_no_unread_entries_is_a_noop(db_session):
    await _seed_source(db_session)
    put_route = _mock_miniflux([])

    marked = await fetch.run()

    assert marked == 0
    assert await _article_count(db_session) == 0
    assert not put_route.called
