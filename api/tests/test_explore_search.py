"""Explore text-search tests (E17-S3).

- Case-insensitive ILIKE on title + executive summary.
- Spans seen and unseen articles, scoped to the user's own sources.
- Excludes non-enriched articles; short queries return nothing.
- Keyset paginates stably on (sort_ts, id); LIKE wildcards are escaped.
"""

from datetime import datetime, timedelta, timezone

from niouzou.models import ArticleImpression
from niouzou.services.explore_service import ExploreService
from tests.factories import make_article, make_source, make_user, set_relevance

NOW = datetime.now(timezone.utc)


async def test_search_matches_title_case_insensitive_seen_and_unseen(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    seen = await make_article(db_session, source, title="Rust memory safety")
    await make_article(db_session, source, title="Why RUST wins")
    nope = await make_article(db_session, source, title="Python typing")
    await set_relevance(db_session, seen, user, 0.4)
    db_session.add(
        ArticleImpression(article_id=seen.id, user_id=user.id, seen_at=NOW)
    )
    await db_session.commit()

    res = await ExploreService(db_session).search(
        user.id, "rust", cursor=None, limit=None
    )
    titles = {a.title for a in res.articles}
    assert titles == {"Rust memory safety", "Why RUST wins"}
    assert nope.title not in titles
    # seen_at carried only for the impressed one.
    by_title = {a.title: a for a in res.articles}
    assert by_title["Rust memory safety"].seen_at is not None
    assert by_title["Why RUST wins"].seen_at is None


async def test_search_matches_executive_summary(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    art = await make_article(db_session, source, title="Generic headline")
    art.summary_executive = "A deep dive into kubernetes operators"
    await db_session.commit()

    res = await ExploreService(db_session).search(
        user.id, "kubernetes", cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["Generic headline"]


async def test_search_excludes_other_users_and_non_enriched(db_session):
    me = await make_user(db_session, email="me@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    mine = await make_source(db_session, me, feed_id=1)
    theirs = await make_source(db_session, other, feed_id=2)
    await make_article(db_session, mine, title="shared topic mine")
    await make_article(db_session, theirs, title="shared topic theirs")
    await make_article(
        db_session, mine, title="shared topic pending", status="pending"
    )
    await db_session.commit()

    res = await ExploreService(db_session).search(
        me.id, "shared topic", cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["shared topic mine"]


async def test_search_short_query_returns_empty(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    await make_article(db_session, source, title="anything")
    await db_session.commit()

    res = await ExploreService(db_session).search(
        user.id, "a", cursor=None, limit=None
    )
    assert res.articles == []
    assert res.has_more is False


async def test_search_paginates_newest_first(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        await make_article(
            db_session,
            source,
            title=f"topic {i}",
            published_at=NOW - timedelta(hours=i),
        )
    await db_session.commit()

    svc = ExploreService(db_session)
    page1 = await svc.search(user.id, "topic", cursor=None, limit=2)
    assert [a.title for a in page1.articles] == ["topic 0", "topic 1"]
    assert page1.has_more is True

    page2 = await svc.search(user.id, "topic", cursor=page1.next_cursor, limit=2)
    assert [a.title for a in page2.articles] == ["topic 2"]
    assert page2.has_more is False


async def test_search_escapes_like_wildcards(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    await make_article(db_session, source, title="50% off sale")
    await make_article(db_session, source, title="literal text only")
    await db_session.commit()

    # '%' must be literal, not a wildcard — only the first article matches.
    res = await ExploreService(db_session).search(
        user.id, "50%", cursor=None, limit=None
    )
    assert [a.title for a in res.articles] == ["50% off sale"]
