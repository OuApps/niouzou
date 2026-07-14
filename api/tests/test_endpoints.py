"""Service tests for the remaining read endpoints (E3-S7).

Covers article detail, saved list, and keyword listing/override.
"""

import pytest

from niouzou.errors import APIError
from niouzou.services.articles_service import ArticlesService
from niouzou.services.feedback_service import FeedbackService
from niouzou.services.keywords_service import KeywordsService
from niouzou.services.saved_service import SavedService
from niouzou.services.stats_service import StatsService
from tests.factories import (
    add_keyword,
    feedback_request,
    make_article,
    make_source,
    make_user,
    set_relevance,
)


async def test_article_detail_shape(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="Why Rust")
    await set_relevance(db_session, article, user, 0.87)
    await db_session.commit()

    detail = await ArticlesService(db_session).get(user.id, article.id)
    assert detail.title == "Why Rust"
    assert detail.keyword_score == 0.87
    assert detail.smart_score is None
    assert detail.active_method == "keyword"
    assert detail.source.name == "Feed"
    # Article from the caller's own source (E23-S3).
    assert detail.owned is True
    # No interaction yet — defaults apply.
    assert detail.reaction == "none"
    assert detail.is_saved is False
    assert detail.read_full_article is False


async def test_article_detail_includes_feedback_after_action(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="like")
    )
    await db_session.commit()

    detail = await ArticlesService(db_session).get(user.id, article.id)
    assert detail.reaction == "like"
    assert detail.is_saved is False


async def test_score_debug_returns_keywords_with_weights(db_session):
    """E10-S2 — debug panel surfaces per-keyword user weights, ``None`` when unset."""
    from niouzou.models import KeywordWeight

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    article.enrichment_model = "google/gemma-4-28b"
    await set_relevance(db_session, article, user, 0.74)
    await add_keyword(db_session, article, "football", 0.9)
    await add_keyword(db_session, article, "fc barcelone", 0.7)
    await add_keyword(db_session, article, "ligue des champions", 0.5)
    db_session.add(
        KeywordWeight(user_id=user.id, term="football", weight=1.2)
    )
    db_session.add(
        KeywordWeight(user_id=user.id, term="fc barcelone", weight=0.8)
    )
    await db_session.commit()

    debug = await ArticlesService(db_session).score_debug(user.id, article.id)
    assert debug.keyword_score == 0.74
    assert debug.enrichment_model == "google/gemma-4-28b"
    weights = {kw.term: kw.weight for kw in debug.keywords}
    assert weights == {
        "football": 1.2,
        "fc barcelone": 0.8,
        # No row for this user → null in the response.
        "ligue des champions": None,
    }


async def test_score_debug_forbids_cross_user(db_session):
    owner = await make_user(db_session, email="owner@test.dev")
    intruder = await make_user(db_session, email="intruder@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await ArticlesService(db_session).score_debug(intruder.id, article.id)
    # Never leak owner's keyword_weights — 403 distinct from 404 so the PWA
    # can tell the difference between "not yours" and "doesn't exist".
    assert exc.value.status_code == 403


async def test_article_of_another_user_is_readonly(db_session):
    """E23-S3 — any article opens by id (deep/shared link), but a foreign one
    comes back ``owned=False`` with no scores: displayed, not scored."""
    owner = await make_user(db_session, email="owner@test.dev")
    intruder = await make_user(db_session, email="intruder@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source, title="Not yours")
    article.content = "Readable body."
    await set_relevance(db_session, article, owner, 0.9)
    await db_session.commit()

    detail = await ArticlesService(db_session).get(intruder.id, article.id)
    assert detail.title == "Not yours"
    assert detail.owned is False
    # The score row belongs to the owner, not the intruder → nothing scored.
    assert detail.keyword_score is None
    assert detail.smart_score is None
    assert detail.reaction == "none"
    # Content still renders for reading.
    assert detail.content == "Readable body."


async def test_missing_article_still_404(db_session):
    import uuid

    user = await make_user(db_session)
    await db_session.commit()
    with pytest.raises(APIError) as exc:
        await ArticlesService(db_session).get(user.id, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_feedback_on_foreign_article_404(db_session):
    owner = await make_user(db_session, email="o@test.dev")
    intruder = await make_user(db_session, email="i@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await FeedbackService(db_session).record(
            intruder.id, feedback_request(article.id, reaction="like")
        )
    assert exc.value.status_code == 404


async def test_saved_lists_only_saved_newest_first(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    a1 = await make_article(db_session, source, title="first")
    a2 = await make_article(db_session, source, title="second")
    liked = await make_article(db_session, source, title="liked-not-saved")
    await db_session.commit()

    svc = FeedbackService(db_session)
    await svc.record(user.id, feedback_request(a1.id, is_saved=True))
    await db_session.commit()
    await svc.record(user.id, feedback_request(a2.id, is_saved=True))
    await db_session.commit()
    await svc.record(user.id, feedback_request(liked.id, reaction="like"))
    await db_session.commit()

    saved = await SavedService(db_session).list_saved(user.id, cursor=None, limit=None)
    titles = [a.title for a in saved.articles]
    assert "liked-not-saved" not in titles
    assert titles == ["second", "first"]  # newest save first


async def test_keywords_listed_by_absolute_weight(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await add_keyword(db_session, article, "rust", 0.9)
    await add_keyword(db_session, article, "php", 0.2)
    await db_session.commit()

    await FeedbackService(db_session).record(
        user.id, feedback_request(article.id, reaction="dislike")
    )
    await db_session.commit()

    listed = await KeywordsService(db_session).list_keywords(
        user.id, cursor=None, limit=None
    )
    # Both negative; rust has larger |weight| so it comes first.
    assert [k.term for k in listed.keywords] == ["rust", "php"]


async def test_patch_keyword_overrides_and_pins(db_session):
    user = await make_user(db_session)
    await db_session.commit()

    svc = KeywordsService(db_session)
    out = await svc.patch_keyword(user.id, "rust", weight=0.0, manually_overridden=None)
    await db_session.commit()

    assert out.term == "rust"
    assert out.weight == 0.0
    assert out.manually_overridden is True
    # Re-running listing reflects the override.
    listed = await svc.list_keywords(user.id, cursor=None, limit=None)
    assert listed.keywords[0].term == "rust"

    # Clearing the pin without changing the weight.
    cleared = await svc.patch_keyword(
        user.id, "rust", weight=None, manually_overridden=False
    )
    assert cleared.manually_overridden is False
    assert cleared.weight == 0.0


async def test_stats_aggregates_user_scoped_counts(db_session):
    from datetime import datetime, timezone

    from niouzou.models import Article
    from niouzou.models.article import STATUS_PENDING

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    # Enriched article with AI success.
    a1 = await make_article(db_session, source, title="ai")
    a1.enriched_at = datetime.now(timezone.utc)
    a1.enrichment_method = "ai"
    # Legacy TF-IDF enrichment (pre-E16-S8) with an error captured.
    a2 = await make_article(db_session, source, title="legacy-tfidf")
    a2.enriched_at = datetime.now(timezone.utc)
    a2.enrichment_method = "tfidf"
    a2.enrichment_error = "boom"
    # Pending article (not yet enriched).
    pending = Article(
        source_id=source.id,
        miniflux_entry_id=999_111,
        url="https://example.com/p",
        title="pending",
        status=STATUS_PENDING,
    )
    db_session.add(pending)
    await db_session.commit()

    stats = await StatsService(db_session).get(user.id)
    assert stats.articles.total == 3
    assert stats.articles.pending_enrichment == 1
    assert stats.sources.total == 1
    assert stats.enrichment.total_ai == 1
    assert stats.enrichment.total_tfidf == 1
    assert stats.enrichment.last_error == "boom"

    # E19-S7 — the lightweight non-admin freshness slice: pending count is
    # user-scoped, and one article is still pending here.
    freshness = await StatsService(db_session).freshness(user.id)
    assert freshness.pending_enrichment == 1
    assert freshness.pipeline_status == "never_run"
