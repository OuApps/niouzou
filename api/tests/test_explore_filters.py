"""Explore filtering tests (E11-S1).

Covers ``min_score`` and ``source_ids`` on both ``/explore/new`` and
``/explore/history``: cold-start bypass, AND-combination, cross-user 422,
and pagination stability under filters.

The ``StatsService`` smoke test confirms ``score_threshold`` is surfaced
through the response — the Explore filter bar relies on the value.
"""

import uuid

import pytest

from niouzou.config import get_settings
from niouzou.errors import APIError
from niouzou.models import ArticleImpression
from niouzou.services.explore_service import ExploreService
from niouzou.services.settings_service import SettingsService
from niouzou.services.stats_service import StatsService
from tests.factories import make_article, make_source, make_user, set_relevance

# ── /explore/new ────────────────────────────────────────────────────────────


async def test_new_min_score_filters_below_threshold(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    low = await make_article(db_session, source, title="low")
    high = await make_article(db_session, source, title="high")
    await set_relevance(db_session, low, user, 0.2)
    await set_relevance(db_session, high, user, 0.8)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, min_score=0.5
    )
    assert [a.title for a in res.articles] == ["high"]


async def test_new_min_score_keeps_cold_start_articles(db_session):
    """Cold-start articles bypass min_score — same rule as E10-S4."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    cold = await make_article(db_session, source, title="cold")
    low = await make_article(db_session, source, title="low")
    await set_relevance(db_session, cold, user, 0.0, is_cold_start=True)
    await set_relevance(db_session, low, user, 0.2)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, min_score=0.5
    )
    titles = {a.title for a in res.articles}
    assert "cold" in titles
    assert "low" not in titles


async def test_new_source_ids_filters_to_listed_sources(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1, name="A")
    src_b = await make_source(db_session, user, feed_id=2, name="B")
    art_a = await make_article(db_session, src_a, title="from_a")
    art_b = await make_article(db_session, src_b, title="from_b")
    await set_relevance(db_session, art_a, user, 0.5)
    await set_relevance(db_session, art_b, user, 0.5)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, source_ids=[src_a.id]
    )
    assert [a.title for a in res.articles] == ["from_a"]


async def test_new_combined_min_score_and_source_ids(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1, name="A")
    src_b = await make_source(db_session, user, feed_id=2, name="B")
    a_low = await make_article(db_session, src_a, title="a_low")
    a_high = await make_article(db_session, src_a, title="a_high")
    b_high = await make_article(db_session, src_b, title="b_high")
    await set_relevance(db_session, a_low, user, 0.2)
    await set_relevance(db_session, a_high, user, 0.8)
    await set_relevance(db_session, b_high, user, 0.9)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id,
        cursor=None,
        limit=None,
        min_score=0.5,
        source_ids=[src_a.id],
    )
    assert [a.title for a in res.articles] == ["a_high"]


async def test_new_foreign_source_id_raises_422(db_session):
    """A UUID belonging to another user must 422, not silently filter."""
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    await make_source(db_session, me, feed_id=1)
    their_src = await make_source(db_session, other, feed_id=2)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await ExploreService(db_session).list_new(
            me.id, cursor=None, limit=None, source_ids=[their_src.id]
        )
    assert exc.value.status_code == 422


async def test_new_unknown_source_id_raises_422(db_session):
    user = await make_user(db_session)
    await make_source(db_session, user)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await ExploreService(db_session).list_new(
            user.id, cursor=None, limit=None, source_ids=[uuid.uuid4()]
        )
    assert exc.value.status_code == 422


async def test_new_pagination_stable_with_filters(db_session):
    """Two pages with the same filters must not overlap."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    for i in range(5):
        art = await make_article(
            db_session,
            source,
            title=f"a{i}",
            published_at=now - timedelta(hours=i),
        )
        await set_relevance(db_session, art, user, 0.6 + i * 0.01)
    await db_session.commit()

    svc = ExploreService(db_session)
    page1 = await svc.list_new(
        user.id, cursor=None, limit=2, min_score=0.5
    )
    page2 = await svc.list_new(
        user.id,
        cursor=page1.next_cursor,
        limit=2,
        min_score=0.5,
    )
    ids = [a.id for p in (page1, page2) for a in p.articles]
    assert len(ids) == len(set(ids))


# ── /explore/history ────────────────────────────────────────────────────────


async def test_history_min_score_filters_below_threshold(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    low = await make_article(db_session, source, title="low")
    high = await make_article(db_session, source, title="high")
    await set_relevance(db_session, low, user, 0.2)
    await set_relevance(db_session, high, user, 0.8)
    db_session.add(ArticleImpression(article_id=low.id, user_id=user.id))
    db_session.add(ArticleImpression(article_id=high.id, user_id=user.id))
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None, min_score=0.5
    )
    assert [a.title for a in res.articles] == ["high"]


async def test_history_min_score_keeps_cold_start_articles(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    cold = await make_article(db_session, source, title="cold")
    low = await make_article(db_session, source, title="low")
    await set_relevance(db_session, cold, user, 0.0, is_cold_start=True)
    await set_relevance(db_session, low, user, 0.2)
    db_session.add(ArticleImpression(article_id=cold.id, user_id=user.id))
    db_session.add(ArticleImpression(article_id=low.id, user_id=user.id))
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None, min_score=0.5
    )
    titles = {a.title for a in res.articles}
    assert "cold" in titles
    assert "low" not in titles


async def test_history_source_ids_filters_to_listed_sources(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1, name="A")
    src_b = await make_source(db_session, user, feed_id=2, name="B")
    art_a = await make_article(db_session, src_a, title="from_a")
    art_b = await make_article(db_session, src_b, title="from_b")
    await set_relevance(db_session, art_a, user, 0.5)
    await set_relevance(db_session, art_b, user, 0.5)
    db_session.add(ArticleImpression(article_id=art_a.id, user_id=user.id))
    db_session.add(ArticleImpression(article_id=art_b.id, user_id=user.id))
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None, source_ids=[src_a.id]
    )
    assert [a.title for a in res.articles] == ["from_a"]


async def test_history_foreign_source_id_raises_422(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    await make_source(db_session, me, feed_id=1)
    their_src = await make_source(db_session, other, feed_id=2)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await ExploreService(db_session).list_history(
            me.id, cursor=None, limit=None, source_ids=[their_src.id]
        )
    assert exc.value.status_code == 422


# ── /stats — score_threshold ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_exposes_score_threshold_from_env(db_session, monkeypatch):
    """Default value comes from the env var when no DB override is set."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.42")
    try:
        user = await make_user(db_session)
        await db_session.commit()
        stats = await StatsService(db_session).get(user.id)
        assert stats.score_threshold == pytest.approx(0.42)
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_stats_exposes_score_threshold_from_db_override(db_session):
    """A DB override takes precedence over the env var."""
    user = await make_user(db_session)
    await SettingsService(db_session).set("score_threshold", 0.77)
    await db_session.commit()
    stats = await StatsService(db_session).get(user.id)
    assert stats.score_threshold == pytest.approx(0.77)
