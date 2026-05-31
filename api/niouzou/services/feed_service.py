"""Feed business logic: HN-ranked, keyset-paginated, impression-filtered.

Ranking (docs/API_SPEC.md):
    feed_rank = relevance_score / (age_in_hours + 2) ^ FEED_GRAVITY

Pagination is keyset on (feed_rank, id) so pages never overlap. With the
default SCORE_THRESHOLD of 0.0 every enriched article clears the threshold, so
the RANDOM_SURFACE_RATE branch is inert and ordering is fully deterministic;
it only kicks in to occasionally surface sub-threshold articles when a positive
threshold is configured (anti echo chamber).

The ranked SELECT projection is shared with ExploreService.list_new (E9-S3)
via ``_build_ranked_query`` — Explore reuses the same gravity ordering but
turns the threshold + random-surface filters off.
"""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import Article, ArticleFeedback, ArticleImpression, Source
from niouzou.models.article import STATUS_ENRICHED
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.feed import FeedArticle, FeedResponse, SourceRef

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 50

# feed_rank, computed once and reused in SELECT, ORDER BY and the keyset filter.
_FEED_RANK = (
    "ars.relevance_score / power("
    "GREATEST(EXTRACT(EPOCH FROM (now() - COALESCE(a.published_at, a.created_at)))"
    "/ 3600.0, 0) + 2, :gravity)"
)

# Projection shared by /feed and /explore/new. Aliased so the outer SELECT
# can keyset on (feed_rank, id) without recomputing the rank.
_RANKED_COLUMNS = f"""
    a.id AS id,
    a.title AS title,
    a.summary_short AS summary_short,
    a.summary_executive AS summary_executive,
    a.content AS content,
    a.og_image_url AS og_image_url,
    a.url AS url,
    a.published_at AS published_at,
    s.id AS source_id,
    s.name AS source_name,
    ars.relevance_score AS relevance_score,
    ars.scorer AS scorer,
    (a.content IS NOT NULL
     AND char_length(a.content) < :premium_max_chars
    ) AS is_premium,
    COALESCE(fb.reaction, 'none') AS reaction,
    COALESCE(fb.is_saved, false) AS is_saved,
    COALESCE(fb.read_full_article, false) AS read_full_article,
    {_FEED_RANK} AS feed_rank,
    COALESCE(
        (SELECT array_agg(ak.term ORDER BY ak.salience DESC, ak.term ASC)
         FROM article_keywords ak WHERE ak.article_id = a.id),
        ARRAY[]::text[]
    ) AS keywords
"""

_FROM_JOINS = """
FROM articles a
JOIN sources s ON s.id = a.source_id
JOIN article_relevance_scores ars
    ON ars.article_id = a.id AND ars.user_id = :user_id
LEFT JOIN article_impressions ai
    ON ai.article_id = a.id AND ai.user_id = :user_id
LEFT JOIN article_feedbacks fb
    ON fb.article_id = a.id AND fb.user_id = :user_id
"""


def _build_ranked_query(
    *,
    apply_threshold: bool,
    apply_random_surface: bool,
    keyset: str = "",
    impression_exclusion: str = "AND ai.article_id IS NULL",
) -> text:
    """Assemble the ranked SELECT used by /feed and /explore/new.

    Args:
        apply_threshold: keep ``ars.relevance_score >= :threshold`` filter.
        apply_random_surface: enable the random-surface escape hatch.
        keyset: extra ``AND (feed_rank, id) < (:cursor_rank, :cursor_id)``
            predicate, or empty string for the first page.
        impression_exclusion: overridable so /feed?start=:id can let one
            already-impressed article through.
    """
    score_filter = ""
    if apply_threshold and apply_random_surface:
        score_filter = "AND (ars.relevance_score >= :threshold OR random() < :random_rate)"
    elif apply_threshold:
        score_filter = "AND ars.relevance_score >= :threshold"
    elif apply_random_surface:
        score_filter = "AND random() < :random_rate"
    # else: no score gate at all (Explore New).

    return text(
        f"""
        WITH ranked AS (
            SELECT
                {_RANKED_COLUMNS}
            {_FROM_JOINS}
            WHERE s.user_id = :user_id
                AND a.status = '{STATUS_ENRICHED}'
                {impression_exclusion}
                {score_filter}
        )
        SELECT * FROM ranked
        WHERE true {keyset}
        ORDER BY feed_rank DESC, id DESC
        LIMIT :limit
        """
    )


def _row_to_article(row) -> FeedArticle:
    return FeedArticle(
        id=row["id"],
        title=row["title"],
        summary_short=row["summary_short"],
        summary_executive=row["summary_executive"],
        content=row["content"],
        og_image_url=row["og_image_url"],
        url=row["url"],
        source=SourceRef(id=row["source_id"], name=row["source_name"]),
        published_at=row["published_at"],
        relevance_score=row["relevance_score"],
        scorer=row["scorer"],
        keywords=list(row["keywords"] or []),
        is_premium=bool(row["is_premium"]),
        reaction=row["reaction"],
        is_saved=bool(row["is_saved"]),
        read_full_article=bool(row["read_full_article"]),
    )


class FeedService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get_feed(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int | None,
        min_score: float | None = None,
        start: uuid.UUID | None = None,
    ) -> FeedResponse:
        settings = get_settings()
        page_size = _clamp_limit(limit)

        # Cold start (E7-S6): users with little feedback get an unfiltered feed,
        # otherwise they'd see nothing on day one (all weights = 0 → all scores
        # ≈ 0.5, blocked by any positive threshold). The PWA override (E7-S8)
        # only kicks in once the user has graduated out of cold start.
        feedback_count = await self.session.scalar(
            select(func.count())
            .select_from(ArticleFeedback)
            .where(ArticleFeedback.user_id == user_id)
        ) or 0
        cold_start = feedback_count < settings.cold_start_threshold

        if cold_start:
            threshold = 0.0
        else:
            threshold = (
                min_score if min_score is not None else settings.score_threshold
            )

        params: dict = {
            "user_id": user_id,
            "gravity": settings.feed_gravity,
            "threshold": threshold,
            "random_rate": settings.random_surface_rate,
            "limit": page_size + 1,  # +1 row tells us whether more remain
            "premium_max_chars": settings.premium_content_max_chars,
        }

        # /feed?start=:id (E9-S3) — only honoured on the first page. When a
        # cursor is provided the user is paginating an existing deck and the
        # pivot logic has already been applied.
        pivot_article: FeedArticle | None = None
        if start is not None and cursor is None:
            pivot_article = await self._fetch_pivot(user_id, start, params)
            if pivot_article is None:
                raise not_found("Article not found")

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            params["cursor_rank"] = float(decoded["rank"])
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"
        elif pivot_article is not None:
            # Continue ranking immediately after the pivot using a synthetic
            # cursor — the keyset's strict `<` naturally excludes the pivot
            # from this branch so we don't get a duplicate.
            pivot_rank = await self._compute_feed_rank(user_id, pivot_article.id, params)
            params["cursor_rank"] = float(pivot_rank)
            params["cursor_id"] = pivot_article.id
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"
            # The pivot takes one slot — fetch one fewer regular article so
            # the response still totals page_size.
            params["limit"] = page_size  # (+1 was already added; pivot is the +1)

        query = _build_ranked_query(
            apply_threshold=True,
            apply_random_surface=True,
            keyset=keyset,
        )
        rows = (await self.session.execute(query, params)).mappings().all()

        # `has_more` is decided by the +1 sentinel only on the regular branch.
        # When a pivot is present we already trimmed `limit` to page_size, so
        # has_more is true iff we have a full page worth of follow-ups.
        if pivot_article is not None:
            has_more = len(rows) == page_size
        else:
            has_more = len(rows) > page_size
            rows = rows[:page_size]

        articles: list[FeedArticle] = []
        if pivot_article is not None:
            articles.append(pivot_article)
        articles.extend(_row_to_article(r) for r in rows)

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor({"rank": last["feed_rank"], "id": last["id"]})

        return FeedResponse(
            articles=articles,
            next_cursor=next_cursor,
            has_more=has_more,
            cold_start=cold_start,
        )

    async def _fetch_pivot(
        self, user_id: uuid.UUID, article_id: uuid.UUID, base_params: dict
    ) -> FeedArticle | None:
        """Fetch a single article as if it were a feed row, ignoring impressions
        and the score gates so we can place it at the top of /feed?start=:id."""
        params = {**base_params, "article_id": article_id, "limit": 1}
        # No threshold / random gating — the user explicitly asked for THIS
        # article. No impression filter either — re-surfacing an
        # already-impressed pivot is the whole point of /explore/history.
        query = text(
            f"""
            SELECT
                {_RANKED_COLUMNS}
            {_FROM_JOINS}
            WHERE s.user_id = :user_id
                AND a.status = '{STATUS_ENRICHED}'
                AND a.id = :article_id
            LIMIT 1
            """
        )
        row = (await self.session.execute(query, params)).mappings().first()
        return _row_to_article(row) if row else None

    async def _compute_feed_rank(
        self, user_id: uuid.UUID, article_id: uuid.UUID, base_params: dict
    ) -> float:
        """Recompute feed_rank for a known article. Cheaper than re-running the
        full ranked query just to learn the pivot's rank."""
        params = {**base_params, "article_id": article_id}
        query = text(
            f"""
            SELECT {_FEED_RANK} AS feed_rank
            FROM articles a
            JOIN article_relevance_scores ars
                ON ars.article_id = a.id AND ars.user_id = :user_id
            WHERE a.id = :article_id
            """
        )
        result = await self.session.scalar(query, params)
        return float(result or 0.0)

    async def record_impression(
        self, user_id: uuid.UUID, article_id: uuid.UUID
    ) -> None:
        """Mark an article as seen so it never re-surfaces. Idempotent."""
        owns = await self.session.scalar(
            select(Article.id)
            .join(Source, Source.id == Article.source_id)
            .where(Article.id == article_id, Source.user_id == user_id)
        )
        if owns is None:
            raise not_found("Article not found")
        await self.session.execute(
            pg_insert(ArticleImpression)
            .values(article_id=article_id, user_id=user_id)
            .on_conflict_do_nothing(index_elements=["article_id", "user_id"])
        )


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))


# Re-exported so ExploreService can build its own ranked query (E9-S3).
__all__ = [
    "FeedService",
    "_FEED_RANK",
    "_RANKED_COLUMNS",
    "_FROM_JOINS",
    "_build_ranked_query",
    "_row_to_article",
    "_clamp_limit",
    "_DEFAULT_LIMIT",
    "_MAX_LIMIT",
]
