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
async def test_unmatched_feed_is_skipped_but_marked_read(db_session):
    # E14-S1 — unmatched (orphan-feed) entries are never inserted in DB but
    # are marked read in Miniflux so they can't saturate the oldest-first
    # fetch window and block the pipeline.
    await _seed_source(db_session)  # only feed 1 is registered
    put_route = _mock_miniflux([_entry(100, feed_id=1), _entry(200, feed_id=999)])

    marked = await fetch.run()

    # Return value reflects ingested entries only.
    assert marked == 1
    assert await _article_count(db_session) == 1
    # Both matched and unmatched marked read in a single Miniflux call.
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [100, 200]


@respx.mock
async def test_only_unmatched_entries_marks_all_read_no_insert(db_session):
    # E14-S1 — when the whole batch is orphan-feed entries (the regression
    # that blocked prod on 2026-06-07), they all get marked read in one PUT
    # and nothing lands in articles.
    await _seed_source(db_session)
    put_route = _mock_miniflux(
        [_entry(200, feed_id=999), _entry(201, feed_id=999), _entry(202, feed_id=888)]
    )

    marked = await fetch.run()

    assert marked == 0
    assert await _article_count(db_session) == 0
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [
        200,
        201,
        202,
    ]


@respx.mock
async def test_db_failure_skips_mark_read(db_session, monkeypatch):
    # E14-S1 — if the DB insert raises, the session_scope rolls back and we
    # must NOT mark anything read in Miniflux (matched OR unmatched), so a
    # retry on the next tick can still pick up the matched entries.
    await _seed_source(db_session)
    put_route = _mock_miniflux([_entry(100, feed_id=1), _entry(200, feed_id=999)])

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(fetch, "_insert_articles", boom)

    with pytest.raises(RuntimeError, match="simulated DB failure"):
        await fetch.run()

    assert not put_route.called
    assert await _article_count(db_session) == 0


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


@respx.mock
async def test_dedup_skips_url_already_present_via_another_source_of_same_user(
    db_session,
):
    # E15-S1 — Le Monde + Le Monde Sciences publish the same URL with
    # different Miniflux entry_ids. The user has both flux subscribed; the
    # second one to arrive must NOT create a second article row, and the
    # entry must still be marked read in Miniflux.
    user = User(email="dup@test.dev", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    s1 = Source(user_id=user.id, miniflux_feed_id=1, url="https://lemonde", name="LM")
    s2 = Source(
        user_id=user.id, miniflux_feed_id=5, url="https://lemonde-sciences", name="LMS"
    )
    db_session.add_all([s1, s2])
    await db_session.flush()  # populate s1.id before referencing it below
    # Pre-existing article ingested through s1 — the duplicate guard target.
    db_session.add(
        Article(
            source_id=s1.id,
            miniflux_entry_id=42,
            url="https://shared.example/article",
            title="Already here",
            status="pending",
        )
    )
    await db_session.commit()

    # New entry arrives via feed_id=5 (s2), same URL, different entry_id.
    new_entry = _entry(43, feed_id=5)
    new_entry["url"] = "https://shared.example/article"
    put_route = _mock_miniflux([new_entry])

    marked = await fetch.run()

    # No new row, but the entry was still marked read (so it can't loop forever).
    assert await _article_count(db_session) == 1
    assert marked == 1  # the entry was matched + handled (skipped is still handled)
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [43]


@respx.mock
async def test_dedup_within_same_batch_when_two_sources_of_same_user_match(
    db_session,
):
    # E15-S1 — fan-out edge case. No pre-existing row, but a single Miniflux
    # entry would land via two sources of the same user (e.g. the user is
    # subscribed to two flux that both republish the same URL, and the same
    # batch carries one entry per flux). The first fan-out target wins; the
    # second is skipped intra-batch.
    user = User(email="batch-dup@test.dev", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    s1 = Source(user_id=user.id, miniflux_feed_id=1, url="https://a", name="A")
    s2 = Source(user_id=user.id, miniflux_feed_id=5, url="https://b", name="B")
    db_session.add_all([s1, s2])
    await db_session.commit()

    # Same URL on both feeds, different entry_ids.
    e1 = _entry(100, feed_id=1)
    e2 = _entry(101, feed_id=5)
    e1["url"] = e2["url"] = "https://shared.example/x"
    put_route = _mock_miniflux([e1, e2])

    marked = await fetch.run()

    # Exactly one row, both entries marked read.
    assert await _article_count(db_session) == 1
    assert marked == 2
    assert sorted(
        json.loads(put_route.calls[0].request.content)["entry_ids"]
    ) == [100, 101]


@respx.mock
async def test_dedup_is_per_user_not_global(db_session):
    # E15-S1 — two distinct users each subscribed to a source matching the
    # same URL must each get their own article row. Dedup must NOT collapse
    # rows across users.
    user_a = User(email="a@test.dev", password_hash="x")
    user_b = User(email="b@test.dev", password_hash="x")
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    db_session.add_all(
        [
            Source(user_id=user_a.id, miniflux_feed_id=1, url="https://a", name="A"),
            Source(user_id=user_b.id, miniflux_feed_id=1, url="https://b", name="B"),
        ]
    )
    await db_session.commit()

    entry = _entry(100, feed_id=1)
    entry["url"] = "https://shared.example/cross-user"
    put_route = _mock_miniflux([entry])

    marked = await fetch.run()

    assert await _article_count(db_session) == 2
    assert marked == 1
    assert json.loads(put_route.calls[0].request.content)["entry_ids"] == [100]
