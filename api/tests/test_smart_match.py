"""E16-S3 — Smart Match scorer maths + ScoringService branching + nightly rescore.

All embeddings here are synthetic axis/blend vectors (tests/fake_embeddings.py)
so cosine similarities are exact: same axis → 1.0, different axes → 0.0,
blend → 0.7071 with each parent axis. The real model is never loaded.
DB-backed throughout (pgvector ``<=>`` is the unit under test); skips cleanly
without Postgres.
"""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from niouzou.crons.refresh_weights import rescore_recent_smart
from niouzou.models import (
    Article,
    ArticleFeedback,
    ArticleRelevanceScore,
    KeywordWeight,
)
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.scoring.smart_match import SmartMatchParams, smart_score
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService
from tests.factories import add_keyword, make_article, make_source, make_user
from tests.fake_embeddings import axis_vector, blend_vector

PARAMS = SmartMatchParams()  # the documented defaults: k=5, λ=0.8, β=0.5, h=90


async def _embedded_article(session, source, vec, *, title="A", age_days=None):
    article = await make_article(session, source, title=title)
    article.embedding = vec
    if age_days is not None:
        article.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    await session.flush()
    return article


async def _feedback(
    session,
    user,
    article,
    *,
    reaction="like",
    is_saved=False,
    read=False,
    age_days=0.0,
):
    ts = datetime.now(timezone.utc) - timedelta(days=age_days)
    session.add(
        ArticleFeedback(
            article_id=article.id,
            user_id=user.id,
            reaction=reaction,
            is_saved=is_saved,
            read_full_article=read,
            created_at=ts,
            updated_at=ts,
        )
    )
    await session.flush()


def _logit(score: float) -> float:
    return math.log(score / (1.0 - score))


# ── smart_score maths ─────────────────────────────────────────────────────────


async def test_likes_raise_close_candidates_and_ignore_orthogonal(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        liked = await _embedded_article(db_session, source, axis_vector(0), title=f"rugby {i}")
        await _feedback(db_session, user, liked)

    rugby = await _embedded_article(db_session, source, axis_vector(0), title="rugby new")
    bourse = await _embedded_article(db_session, source, axis_vector(1), title="bourse")

    rugby_score, rugby_cold = await smart_score(
        db_session, rugby.id, user.id, params=PARAMS
    )
    bourse_score, bourse_cold = await smart_score(
        db_session, bourse.id, user.id, params=PARAMS
    )

    assert rugby_score > 0.5
    # Orthogonal candidate: no relevant neighbour → neutral, NOT penalised.
    assert abs(bourse_score - 0.5) < 1e-6
    assert rugby_cold is False and bourse_cold is False


async def test_multi_interest_clusters_no_centroid_effect(db_session):
    """Two orthogonal like-clusters must both win, and a halfway candidate
    must not beat either — the k-NN judges each candidate against its own
    cluster, never against an averaged profile."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        rugby = await _embedded_article(db_session, source, axis_vector(0), title=f"rugby {i}")
        await _feedback(db_session, user, rugby)
        tech = await _embedded_article(db_session, source, axis_vector(1), title=f"tech {i}")
        await _feedback(db_session, user, tech)

    # k = cluster size so each candidate is judged against one full cluster.
    params = SmartMatchParams(topk=3)
    cand_rugby = await _embedded_article(db_session, source, axis_vector(0), title="r cand")
    cand_tech = await _embedded_article(db_session, source, axis_vector(1), title="t cand")
    cand_mid = await _embedded_article(db_session, source, blend_vector(0, 1), title="mid cand")

    s_rugby, _ = await smart_score(db_session, cand_rugby.id, user.id, params=params)
    s_tech, _ = await smart_score(db_session, cand_tech.id, user.id, params=params)
    s_mid, _ = await smart_score(db_session, cand_mid.id, user.id, params=params)

    assert s_rugby > 0.5 and s_tech > 0.5
    assert s_mid <= s_rugby and s_mid <= s_tech


async def test_dislikes_push_close_candidates_below_neutral(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(2):
        disliked = await _embedded_article(db_session, source, axis_vector(0), title=f"d{i}")
        await _feedback(db_session, user, disliked, reaction="dislike")
    # One unrelated like so the user isn't cold.
    liked = await _embedded_article(db_session, source, axis_vector(5), title="liked")
    await _feedback(db_session, user, liked)

    candidate = await _embedded_article(db_session, source, axis_vector(0), title="cand")
    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert score < 0.5
    assert is_cold is False


async def test_decay_halves_twice_at_double_halflife(db_session):
    """A like aged 2×halflife contributes 4× less raw signal than a fresh one."""
    user_fresh = await make_user(db_session, email="fresh@test.dev")
    user_old = await make_user(db_session, email="old@test.dev")
    src_fresh = await make_source(db_session, user_fresh, feed_id=1)
    src_old = await make_source(db_session, user_old, feed_id=2)

    fresh_like = await _embedded_article(db_session, src_fresh, axis_vector(0), title="f")
    await _feedback(db_session, user_fresh, fresh_like, age_days=0.0)
    old_like = await _embedded_article(db_session, src_old, axis_vector(0), title="o")
    await _feedback(
        db_session, user_old, old_like, age_days=2 * PARAMS.decay_halflife_days
    )

    cand_fresh = await _embedded_article(db_session, src_fresh, axis_vector(0), title="cf")
    cand_old = await _embedded_article(db_session, src_old, axis_vector(0), title="co")

    s_fresh, _ = await smart_score(db_session, cand_fresh.id, user_fresh.id, params=PARAMS)
    s_old, _ = await smart_score(db_session, cand_old.id, user_old.id, params=PARAMS)

    # logit(score) = β·raw, so the raw ratio is recoverable exactly.
    raw_fresh = _logit(s_fresh) / PARAMS.beta
    raw_old = _logit(s_old) / PARAMS.beta
    assert abs(raw_fresh - 1.0) < 0.01  # sim 1 × value 1 × decay(0) = 1
    assert abs(raw_fresh / raw_old - 4.0) < 0.05


async def test_user_without_feedback_is_neutral_and_cold(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    candidate = await _embedded_article(db_session, source, axis_vector(0))

    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert abs(score - 0.5) < 1e-9
    assert is_cold is True


async def test_feedback_value_uses_saved_and_read_dimensions(db_session):
    """value = reaction ± 1 + 0.5·saved + 0.5·read (E9-S1) — a save+read with
    no reaction is positive signal."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    saved = await _embedded_article(db_session, source, axis_vector(0))
    await _feedback(db_session, user, saved, reaction="none", is_saved=True, read=True)

    candidate = await _embedded_article(db_session, source, axis_vector(0), title="cand")
    score, is_cold = await smart_score(db_session, candidate.id, user.id, params=PARAMS)

    assert score > 0.5
    assert is_cold is False


# ── ScoringService branching ──────────────────────────────────────────────────


def _smart_service() -> ScoringService:
    return ScoringService(
        ScoringPipeline(TFIDFScorer()),
        max_keywords_per_article=6,
        scoring_mode="smart",
        smart_params=PARAMS,
    )


async def test_smart_mode_stamps_smart_match_scorer(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))

    await _smart_service().score_article_for_user(db_session, article.id, user.id)

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.scorer == "smart_match"
    assert row.is_cold_start is True  # no feedback yet


async def test_article_without_embedding_falls_back_to_classic(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)  # embedding stays NULL
    await add_keyword(db_session, article, "rugby", 0.9)

    score = await _smart_service().score_article_for_user(
        db_session, article.id, user.id
    )

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.scorer == "tfidf"  # the active classic engine, not smart_match
    assert 0.0 <= score <= 1.0


async def test_classic_mode_is_untouched_by_smart_params(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    await add_keyword(db_session, article, "rugby", 0.9)

    classic = ScoringService(
        ScoringPipeline(TFIDFScorer()), max_keywords_per_article=6
    )
    await classic.score_article_for_user(db_session, article.id, user.id)

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.scorer == "tfidf"


# ── nightly rescoring (E16-S3) ────────────────────────────────────────────────


async def test_rescore_is_noop_in_classic_mode(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await _embedded_article(db_session, source, axis_vector(0))
    db_session.add(
        ArticleRelevanceScore(
            article_id=article.id, user_id=user.id, relevance_score=0.5, scorer="tfidf"
        )
    )
    await db_session.flush()

    assert await rescore_recent_smart(db_session) == 0

    row = await db_session.get(ArticleRelevanceScore, (article.id, user.id))
    assert row.relevance_score == 0.5 and row.scorer == "tfidf"


async def test_rescore_lifts_frozen_neutral_score_after_likes(db_session):
    """The frozen-score fix: a 0.5 stamped before the user had any history
    rises once the user likes similar articles."""
    await SettingsService(db_session).set("scoring_mode", "smart")

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    candidate = await _embedded_article(db_session, source, axis_vector(0))
    db_session.add(
        ArticleRelevanceScore(
            article_id=candidate.id,
            user_id=user.id,
            relevance_score=0.5,
            scorer="smart_match",
            is_cold_start=True,
        )
    )
    for i in range(3):
        liked = await _embedded_article(db_session, source, axis_vector(0), title=f"l{i}")
        await _feedback(db_session, user, liked)
    await db_session.flush()

    rescored = await rescore_recent_smart(db_session)
    assert rescored >= 1

    row = await db_session.get(ArticleRelevanceScore, (candidate.id, user.id))
    await db_session.refresh(row)
    assert row.relevance_score > 0.5
    assert row.scorer == "smart_match"
    assert row.is_cold_start is False


async def test_rescore_only_touches_the_recent_window(db_session):
    await SettingsService(db_session).set("scoring_mode", "smart")

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    # Ingested well outside smart_rescore_window_days (default 14).
    stale = await _embedded_article(db_session, source, axis_vector(0), age_days=60)
    db_session.add(
        ArticleRelevanceScore(
            article_id=stale.id, user_id=user.id, relevance_score=0.5, scorer="tfidf"
        )
    )
    liked = await _embedded_article(db_session, source, axis_vector(0), title="l")
    await _feedback(db_session, user, liked)
    await db_session.flush()

    await rescore_recent_smart(db_session)

    row = await db_session.get(ArticleRelevanceScore, (stale.id, user.id))
    await db_session.refresh(row)
    # Outside the window → frozen, even though a like would now lift it.
    assert row.relevance_score == 0.5
    assert row.scorer == "tfidf"
