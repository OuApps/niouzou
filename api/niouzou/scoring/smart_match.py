"""Smart Match — instance-based (k-NN) semantic scoring (E16-S3).

A candidate article is compared to the K most similar articles the user has
already feedbacked, separately for positive and negative signal:

    S+ = Σ_{i ∈ topK(liked)}    sim(a, e_i) · value_i · decay(t_i)
    S− = Σ_{j ∈ topK(disliked)} sim(a, e_j) · |value_j| · decay(t_j)

    raw   = S+ − λ·S−
    score = sigmoid(β·raw + Σ_{pinned kw ∩ keywords(a)} weight·salience)

``value`` is the E9-S1 feedback signal ((±1 reaction) + 0.5·saved + 0.5·read)
and ``decay(t) = 0.5^(age_days / halflife)`` so last week's likes outweigh
last year's. There is deliberately NO single user-profile vector: a user who
likes both rugby and Rust would average into a centroid in the semantic void
between the two. Top-K per polarity judges a rugby candidate against the
rugby likes only — multi-interest by construction.

Unlike the ``BaseScorer`` implementations (pure, no I/O), Smart Match needs
the database (the user's feedback neighbours), so it lives outside the
scorer hierarchy: ``ScoringService.score_article_for_user`` branches here
when ``scoring_mode = 'smart'``.

No ANN index needed: the k-NN runs over the *user's feedbacked articles*
(hundreds of rows at most), not the whole corpus — a plain
``ORDER BY embedding <=> :a LIMIT k`` on that join is plenty.
"""

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.models import Article, ArticleFeedback, ArticleKeyword, KeywordWeight

SCORER_NAME = "smart_match"

# E9-S1 feedback signal, as a SQLAlchemy expression (the SQL-string twin
# lives in services/weights.py::_FEEDBACK_VALUE).
_VALUE = (
    case(
        (ArticleFeedback.reaction == "like", 1.0),
        (ArticleFeedback.reaction == "dislike", -1.0),
        else_=0.0,
    )
    + case((ArticleFeedback.is_saved, 0.5), else_=0.0)
    + case((ArticleFeedback.read_full_article, 0.5), else_=0.0)
)

# Age of the feedback in days. ``updated_at`` rather than ``created_at``: it
# tracks the latest expression of the preference (a re-confirmed save is
# fresh signal).
_AGE_DAYS = func.extract("epoch", func.now() - ArticleFeedback.updated_at) / 86400.0


@dataclass(slots=True)
class SmartMatchParams:
    """Tuning knobs, snapshotted from app_settings once per cron run."""

    topk: int = 5
    lambda_: float = 0.8
    beta: float = 0.5
    decay_halflife_days: float = 90.0


def _sigmoid(x: float) -> float:
    # Same clamp as ScoringPipeline._normalize: saturate instead of overflow.
    x = max(-60.0, min(60.0, x))
    return 1.0 / (1.0 + math.exp(-x))


async def _topk_neighbours(
    session: AsyncSession,
    user_id: uuid.UUID,
    candidate_embedding,
    k: int,
    *,
    positive: bool,
) -> list[tuple[float, float, float]]:
    """(similarity, value, age_days) of the K feedbacks nearest the candidate.

    One polarity per call: ``positive`` selects feedbacks with value > 0,
    otherwise value < 0. Only feedbacked articles that have an embedding can
    be neighbours.
    """
    distance = Article.embedding.cosine_distance(candidate_embedding)
    stmt = (
        select(
            (1.0 - distance).label("sim"),
            _VALUE.label("value"),
            _AGE_DAYS.label("age_days"),
        )
        .select_from(ArticleFeedback)
        .join(Article, Article.id == ArticleFeedback.article_id)
        .where(
            ArticleFeedback.user_id == user_id,
            Article.embedding.is_not(None),
            _VALUE > 0 if positive else _VALUE < 0,
        )
        .order_by(distance)
        .limit(k)
    )
    return [(row.sim, row.value, row.age_days) for row in await session.execute(stmt)]


async def _pinned_boost(
    session: AsyncSession, article_id: uuid.UUID, user_id: uuid.UUID
) -> float:
    """Σ weight·salience over the user's pinned keywords on this article.

    Pinned (= ``manually_overridden``) weights are a user contract (E16-S5):
    learned weights stop driving the score in smart mode, but explicit
    overrides stay hard levers, added inside the sigmoid.
    """
    return (
        await session.scalar(
            select(
                func.coalesce(
                    func.sum(KeywordWeight.weight * ArticleKeyword.salience), 0.0
                )
            )
            .select_from(ArticleKeyword)
            .join(
                KeywordWeight,
                (KeywordWeight.term == ArticleKeyword.term)
                & (KeywordWeight.user_id == user_id),
            )
            .where(
                ArticleKeyword.article_id == article_id,
                KeywordWeight.manually_overridden.is_(True),
            )
        )
    ) or 0.0


async def _has_positive_feedback(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(ArticleFeedback.user_id == user_id, _VALUE > 0)
            )
        )
    )


async def smart_score(
    session: AsyncSession,
    article_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    params: SmartMatchParams | None = None,
) -> tuple[float, bool] | None:
    """Score one article for one user with the Smart Match formula.

    Returns ``(score, is_cold_start)``, or ``None`` when the article has no
    embedding yet (legacy row not backfilled) — the caller then falls back to
    the active Classic scorer so no article is ever left unscored.

    ``is_cold_start`` is TRUE iff the user has no feedback with value > 0
    (the smart-mode definition — keyword vocabulary overlap is irrelevant
    here).
    """
    params = params or SmartMatchParams()

    candidate = await session.scalar(
        select(Article.embedding).where(Article.id == article_id)
    )
    if candidate is None:
        return None

    liked = await _topk_neighbours(
        session, user_id, candidate, params.topk, positive=True
    )
    disliked = await _topk_neighbours(
        session, user_id, candidate, params.topk, positive=False
    )

    def decayed_sum(rows: list[tuple[float, float, float]]) -> float:
        return sum(
            sim * abs(value) * 0.5 ** (max(age_days, 0.0) / params.decay_halflife_days)
            for sim, value, age_days in rows
        )

    raw = decayed_sum(liked) - params.lambda_ * decayed_sum(disliked)
    boost = await _pinned_boost(session, article_id, user_id)
    score = _sigmoid(params.beta * raw + boost)

    if liked:
        is_cold_start = False
    else:
        # No positive neighbour with an embedding — cold iff the user has no
        # positive feedback at all (per the E16 spec definition).
        is_cold_start = not await _has_positive_feedback(session, user_id)

    return score, is_cold_start
