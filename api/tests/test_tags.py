"""Tags & Loupe tests (E24).

Covers the /tags CRUD (case-insensitive uniqueness, 409, threshold null vs
bounded), PUT /sources/{id}/tags (set-semantics, foreign-tag 422), the Loupe
on GET /feed (source filter + effective-threshold precedence min_score > tag >
global; cold-start bypass preserved; foreign tag 422) and on Explore
(new/history/search: pure source filter — the per-tag threshold applies ONLY
on /feed, pinned by a dedicated test).
"""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from niouzou.config import get_settings
from niouzou.errors import APIError
from niouzou.models import ArticleFeedback, ArticleImpression, SourceTag
from niouzou.schemas.tags import TagCreate, TagUpdate
from niouzou.services.explore_service import ExploreService
from niouzou.services.feed_service import FeedService
from niouzou.services.sources_service import SourcesService
from niouzou.services.tags_service import TagsService
from tests.factories import (
    make_article,
    make_source,
    make_tag,
    make_user,
    set_relevance,
    tag_source,
)

# ── /tags CRUD ──────────────────────────────────────────────────────────────


async def test_create_and_list_tags_sorted_with_source_count(db_session):
    from datetime import datetime, timezone

    user = await make_user(db_session)
    src_active = await make_source(db_session, user, feed_id=1)
    src_paused = await make_source(db_session, user, feed_id=2)
    src_paused.deleted_at = datetime.now(timezone.utc)

    svc = TagsService(db_session)
    created = await svc.create_tag(user.id, "rugby")
    tech = await svc.create_tag(user.id, "Tech", threshold=0.4)
    assert created.source_count == 0
    assert tech.threshold == 0.4

    from niouzou.models import Tag

    rugby = await db_session.get(Tag, created.id)
    await tag_source(db_session, src_active, rugby)
    await tag_source(db_session, src_paused, rugby)
    await db_session.commit()

    res = await svc.list_tags(user.id)
    assert [t.name for t in res.tags] == ["rugby", "Tech"]  # ci-sorted
    by_name = {t.name: t for t in res.tags}
    # Paused source excluded from the count.
    assert by_name["rugby"].source_count == 1
    assert by_name["Tech"].source_count == 0


async def test_create_duplicate_name_case_insensitive_409(db_session):
    user = await make_user(db_session)
    svc = TagsService(db_session)
    await svc.create_tag(user.id, "Rugby")
    with pytest.raises(APIError) as exc:
        await svc.create_tag(user.id, "rugby")
    assert exc.value.status_code == 409


async def test_same_name_allowed_across_users(db_session):
    u1 = await make_user(db_session, email="a@test.dev")
    u2 = await make_user(db_session, email="b@test.dev")
    svc = TagsService(db_session)
    await svc.create_tag(u1.id, "Rugby")
    created = await svc.create_tag(u2.id, "Rugby")
    assert created.name == "Rugby"


def test_tag_name_is_trimmed_and_bounded():
    assert TagCreate(name="  Rugby  ").name == "Rugby"
    with pytest.raises(ValidationError):
        TagCreate(name="   ")
    with pytest.raises(ValidationError):
        TagCreate(name="x" * 41)
    with pytest.raises(ValidationError):
        TagCreate(name="ok", threshold=1.5)


async def test_update_tag_rename_conflict_409(db_session):
    user = await make_user(db_session)
    svc = TagsService(db_session)
    await svc.create_tag(user.id, "Rugby")
    tech = await svc.create_tag(user.id, "Tech")
    with pytest.raises(APIError) as exc:
        await svc.update_tag(user.id, tech.id, TagUpdate(name="RUGBY"))
    assert exc.value.status_code == 409
    # Renaming to itself (case change) is fine.
    out = await svc.update_tag(user.id, tech.id, TagUpdate(name="tech"))
    assert out.name == "tech"


async def test_update_tag_threshold_null_vs_absent(db_session):
    user = await make_user(db_session)
    svc = TagsService(db_session)
    tag = await svc.create_tag(user.id, "Rugby", threshold=0.4)

    # Absent threshold key → untouched.
    out = await svc.update_tag(user.id, tag.id, TagUpdate(name="Rugby XV"))
    assert out.threshold == 0.4

    # Explicit null → back to inheriting the global threshold.
    out = await svc.update_tag(
        user.id, tag.id, TagUpdate.model_validate({"threshold": None})
    )
    assert out.threshold is None


async def test_update_foreign_tag_404(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    theirs = await make_tag(db_session, other)
    with pytest.raises(APIError) as exc:
        await TagsService(db_session).update_tag(
            me.id, theirs.id, TagUpdate(name="mine now")
        )
    assert exc.value.status_code == 404


async def test_delete_tag_cascades_links_articles_untouched(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    tag = await make_tag(db_session, user)
    await tag_source(db_session, source, tag)
    await db_session.commit()

    await TagsService(db_session).delete_tag(user.id, tag.id)
    await db_session.commit()

    links = (await db_session.scalars(select(SourceTag))).all()
    assert links == []
    # The article survives untouched.
    assert (await db_session.get(type(article), article.id)) is not None


async def test_delete_foreign_tag_404(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    theirs = await make_tag(db_session, other)
    with pytest.raises(APIError) as exc:
        await TagsService(db_session).delete_tag(me.id, theirs.id)
    assert exc.value.status_code == 404


# ── PUT /sources/{id}/tags ──────────────────────────────────────────────────


async def test_set_source_tags_replaces_the_whole_set(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    rugby = await make_tag(db_session, user, "Rugby")
    tech = await make_tag(db_session, user, "Tech")
    await db_session.commit()

    svc = SourcesService(db_session)
    out = await svc.set_source_tags(user.id, source.id, [rugby.id])
    assert [t.name for t in out.tags] == ["Rugby"]

    # Set-semantics: the new list replaces, not appends.
    out = await svc.set_source_tags(user.id, source.id, [tech.id])
    assert [t.name for t in out.tags] == ["Tech"]

    # Empty list clears everything.
    out = await svc.set_source_tags(user.id, source.id, [])
    assert out.tags == []


async def test_set_source_tags_foreign_tag_422(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    source = await make_source(db_session, me)
    theirs = await make_tag(db_session, other)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).set_source_tags(
            me.id, source.id, [theirs.id]
        )
    assert exc.value.status_code == 422


async def test_set_source_tags_foreign_source_404(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    their_source = await make_source(db_session, other)
    mine = await make_tag(db_session, me)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).set_source_tags(
            me.id, their_source.id, [mine.id]
        )
    assert exc.value.status_code == 404


# ── GET /feed?tag= (E24-S4) ─────────────────────────────────────────────────


async def _warm_user(db_session, user, source, n=1):
    """Graduate the user out of the global cold start (COLD_START_THRESHOLD
    must be monkeypatched to <= n by the caller)."""
    for i in range(n):
        art = await make_article(db_session, source, title=f"warm-{i}")
        await set_relevance(db_session, art, user, 0.9)
        db_session.add(ArticleImpression(article_id=art.id, user_id=user.id))
        db_session.add(
            ArticleFeedback(article_id=art.id, user_id=user.id, reaction="like")
        )


async def test_feed_tag_filters_to_tagged_sources(db_session, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.0")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    try:
        user = await make_user(db_session)
        src_rugby = await make_source(db_session, user, feed_id=1, name="R")
        src_other = await make_source(db_session, user, feed_id=2, name="O")
        rugby = await make_tag(db_session, user, "Rugby")
        await tag_source(db_session, src_rugby, rugby)
        a_in = await make_article(db_session, src_rugby, title="in")
        a_out = await make_article(db_session, src_other, title="out")
        await set_relevance(db_session, a_in, user, 0.5)
        await set_relevance(db_session, a_out, user, 0.5)
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, tag=rugby.id
        )
        assert [a.title for a in feed.articles] == ["in"]
    finally:
        get_settings.cache_clear()


async def test_feed_tag_threshold_overrides_global(db_session, monkeypatch):
    """Warm user, global threshold 0.8, tag threshold 0.4 → a 0.5-scored
    article surfaces under the Loupe but not without it."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.8")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    monkeypatch.setenv("COLD_START_THRESHOLD", "1")
    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        rugby = await make_tag(db_session, user, "Rugby", threshold=0.4)
        await tag_source(db_session, source, rugby)
        await _warm_user(db_session, user, source)
        art = await make_article(db_session, source, title="mid")
        await set_relevance(db_session, art, user, 0.5)
        await db_session.commit()

        svc = FeedService(db_session)
        without = await svc.get_feed(user.id, cursor=None, limit=None)
        assert [a.title for a in without.articles] == []

        with_loupe = await svc.get_feed(
            user.id, cursor=None, limit=None, tag=rugby.id
        )
        assert [a.title for a in with_loupe.articles] == ["mid"]
    finally:
        get_settings.cache_clear()


async def test_feed_min_score_wins_over_tag_threshold(db_session, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.0")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    monkeypatch.setenv("COLD_START_THRESHOLD", "1")
    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        rugby = await make_tag(db_session, user, "Rugby", threshold=0.4)
        await tag_source(db_session, source, rugby)
        await _warm_user(db_session, user, source)
        art = await make_article(db_session, source, title="mid")
        await set_relevance(db_session, art, user, 0.5)
        await db_session.commit()

        # min_score 0.7 beats the tag's lenient 0.4 → filtered out.
        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, min_score=0.7, tag=rugby.id
        )
        assert feed.articles == []
    finally:
        get_settings.cache_clear()


async def test_feed_tag_null_threshold_inherits_global(db_session, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.8")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    monkeypatch.setenv("COLD_START_THRESHOLD", "1")
    try:
        user = await make_user(db_session)
        source = await make_source(db_session, user)
        rugby = await make_tag(db_session, user, "Rugby")  # threshold NULL
        await tag_source(db_session, source, rugby)
        await _warm_user(db_session, user, source)
        art = await make_article(db_session, source, title="mid")
        await set_relevance(db_session, art, user, 0.5)
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, tag=rugby.id
        )
        # Inherits the 0.8 global → 0.5 stays hidden.
        assert feed.articles == []
    finally:
        get_settings.cache_clear()


async def test_feed_cold_start_bypasses_tag_threshold(db_session, monkeypatch):
    """A cold-start user ignores every threshold, Loupe included — the tag
    still filters the sources though."""
    get_settings.cache_clear()
    monkeypatch.setenv("SCORE_THRESHOLD", "0.0")
    monkeypatch.setenv("RANDOM_SURFACE_RATE", "0.0")
    try:
        user = await make_user(db_session)  # zero feedback → cold start
        src_rugby = await make_source(db_session, user, feed_id=1)
        src_other = await make_source(db_session, user, feed_id=2)
        rugby = await make_tag(db_session, user, "Rugby", threshold=0.9)
        await tag_source(db_session, src_rugby, rugby)
        low = await make_article(db_session, src_rugby, title="low")
        out = await make_article(db_session, src_other, title="out")
        await set_relevance(db_session, low, user, 0.1)
        await set_relevance(db_session, out, user, 0.9)
        await db_session.commit()

        feed = await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, tag=rugby.id
        )
        assert feed.cold_start is True
        assert [a.title for a in feed.articles] == ["low"]
    finally:
        get_settings.cache_clear()


async def test_feed_foreign_tag_422(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    await make_source(db_session, me)
    theirs = await make_tag(db_session, other)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await FeedService(db_session).get_feed(
            me.id, cursor=None, limit=None, tag=theirs.id
        )
    assert exc.value.status_code == 422


async def test_feed_unknown_tag_422(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    with pytest.raises(APIError) as exc:
        await FeedService(db_session).get_feed(
            user.id, cursor=None, limit=None, tag=uuid.uuid4()
        )
    assert exc.value.status_code == 422


# ── Explore + tag (E24-S5) ──────────────────────────────────────────────────


async def test_explore_new_tag_filters_sources(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1)
    src_b = await make_source(db_session, user, feed_id=2)
    rugby = await make_tag(db_session, user, "Rugby")
    await tag_source(db_session, src_a, rugby)
    a = await make_article(db_session, src_a, title="in")
    b = await make_article(db_session, src_b, title="out")
    await set_relevance(db_session, a, user, 0.5)
    await set_relevance(db_session, b, user, 0.5)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, tag=rugby.id
    )
    assert [x.title for x in res.articles] == ["in"]


async def test_explore_new_tag_threshold_not_applied(db_session):
    """Pin (E24-S5): the per-tag threshold only bites on /feed — Explore New
    surfaces a low-scored article even when the tag carries a high threshold."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    rugby = await make_tag(db_session, user, "Rugby", threshold=0.9)
    await tag_source(db_session, source, rugby)
    art = await make_article(db_session, source, title="low")
    await set_relevance(db_session, art, user, 0.1)
    await db_session.commit()

    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, tag=rugby.id
    )
    assert [x.title for x in res.articles] == ["low"]


async def test_explore_new_tag_combines_with_source_ids(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1)
    src_b = await make_source(db_session, user, feed_id=2)
    rugby = await make_tag(db_session, user, "Rugby")
    await tag_source(db_session, src_a, rugby)
    await tag_source(db_session, src_b, rugby)
    a = await make_article(db_session, src_a, title="a")
    b = await make_article(db_session, src_b, title="b")
    await set_relevance(db_session, a, user, 0.5)
    await set_relevance(db_session, b, user, 0.5)
    await db_session.commit()

    # AND-combination: tagged AND in source_ids.
    res = await ExploreService(db_session).list_new(
        user.id, cursor=None, limit=None, tag=rugby.id, source_ids=[src_a.id]
    )
    assert [x.title for x in res.articles] == ["a"]


async def test_explore_history_tag_filters_sources(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1)
    src_b = await make_source(db_session, user, feed_id=2)
    rugby = await make_tag(db_session, user, "Rugby")
    await tag_source(db_session, src_a, rugby)
    a = await make_article(db_session, src_a, title="in")
    b = await make_article(db_session, src_b, title="out")
    await set_relevance(db_session, a, user, 0.5)
    await set_relevance(db_session, b, user, 0.5)
    db_session.add(ArticleImpression(article_id=a.id, user_id=user.id))
    db_session.add(ArticleImpression(article_id=b.id, user_id=user.id))
    await db_session.commit()

    res = await ExploreService(db_session).list_history(
        user.id, cursor=None, limit=None, tag=rugby.id
    )
    assert [x.title for x in res.articles] == ["in"]


async def test_explore_search_tag_filters_sources(db_session):
    user = await make_user(db_session)
    src_a = await make_source(db_session, user, feed_id=1)
    src_b = await make_source(db_session, user, feed_id=2)
    rugby = await make_tag(db_session, user, "Rugby")
    await tag_source(db_session, src_a, rugby)
    a = await make_article(db_session, src_a, title="rust in scrum")
    b = await make_article(db_session, src_b, title="rust elsewhere")
    await set_relevance(db_session, a, user, 0.5)
    await set_relevance(db_session, b, user, 0.5)
    await db_session.commit()

    res = await ExploreService(db_session).search(
        user.id, "rust", cursor=None, limit=None, tag=rugby.id
    )
    assert [x.title for x in res.articles] == ["rust in scrum"]


async def test_explore_foreign_tag_422(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    theirs = await make_tag(db_session, other)
    await db_session.commit()

    svc = ExploreService(db_session)
    for call in (
        lambda: svc.list_new(me.id, cursor=None, limit=None, tag=theirs.id),
        lambda: svc.list_history(me.id, cursor=None, limit=None, tag=theirs.id),
        lambda: svc.search(me.id, "rust", cursor=None, limit=None, tag=theirs.id),
    ):
        with pytest.raises(APIError) as exc:
            await call()
        assert exc.value.status_code == 422


# ── GET /sources carries tags ───────────────────────────────────────────────


async def test_list_sources_carries_tags_sorted(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    zebra = await make_tag(db_session, user, "zebra")
    alpha = await make_tag(db_session, user, "Alpha")
    await tag_source(db_session, source, zebra)
    await tag_source(db_session, source, alpha)
    await db_session.commit()

    # The Miniflux crawler lookup inside list_sources is best-effort (returns
    # an empty map on failure), so no HTTP mock is needed here.
    res = await SourcesService(db_session).list_sources(user.id)
    assert [t.name for t in res.sources[0].tags] == ["Alpha", "zebra"]
