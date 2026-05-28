"""Feed business logic: HN-ranked, keyset-paginated, impression-filtered.

Ranking (docs/API_SPEC.md):
    feed_rank = relevance_score / (age_in_hours + 2) ^ FEED_GRAVITY

Pagination is keyset on (feed_rank, id) so pages never overlap. With the
default SCORE_THRESHOLD of 0.0 every enriched article clears the threshold, so
the RANDOM_SURFACE_RATE branch is inert and ordering is fully deterministic;
it only kicks in to occasionally surface sub-threshold articles when a positive
threshold is configured (anti echo chamber).
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import Article, ArticleImpression, Source
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


class FeedService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get_feed(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int | None,
        min_score: float | None = None,
    ) -> FeedResponse:
        settings = get_settings()
        page_size = _clamp_limit(limit)

        # Per-request override beats the env default (E7-S8); the random-surface
        # branch still applies on top.
        threshold = (
            min_score if min_score is not None else settings.score_threshold
        )

        params: dict = {
            "user_id": user_id,
            "gravity": settings.feed_gravity,
            "threshold": threshold,
            "random_rate": settings.random_surface_rate,
            "limit": page_size + 1,  # +1 row tells us whether more remain
        }

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            params["cursor_rank"] = float(decoded["rank"])
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"

        query = text(
            f"""
            WITH ranked AS (
                SELECT
                    a.id AS id,
                    a.title AS title,
                    a.summary_short AS summary_short,
                    a.og_image_url AS og_image_url,
                    a.url AS url,
                    a.published_at AS published_at,
                    s.id AS source_id,
                    s.name AS source_name,
                    ars.relevance_score AS relevance_score,
                    ars.scorer AS scorer,
                    {_FEED_RANK} AS feed_rank,
                    COALESCE(
                        (SELECT array_agg(ak.term ORDER BY ak.salience DESC, ak.term ASC)
                         FROM article_keywords ak WHERE ak.article_id = a.id),
                        ARRAY[]::text[]
                    ) AS keywords
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                JOIN article_relevance_scores ars
                    ON ars.article_id = a.id AND ars.user_id = :user_id
                LEFT JOIN article_impressions ai
                    ON ai.article_id = a.id AND ai.user_id = :user_id
                WHERE s.user_id = :user_id
                    AND a.status = '{STATUS_ENRICHED}'
                    AND ai.article_id IS NULL
                    AND (ars.relevance_score >= :threshold
                         OR random() < :random_rate)
            )
            SELECT * FROM ranked
            WHERE true {keyset}
            ORDER BY feed_rank DESC, id DESC
            LIMIT :limit
            """
        )

        rows = (await self.session.execute(query, params)).mappings().all()

        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [
            FeedArticle(
                id=r["id"],
                title=r["title"],
                summary_short=r["summary_short"],
                og_image_url=r["og_image_url"],
                url=r["url"],
                source=SourceRef(id=r["source_id"], name=r["source_name"]),
                published_at=r["published_at"],
                relevance_score=r["relevance_score"],
                scorer=r["scorer"],
                keywords=list(r["keywords"] or []),
            )
            for r in rows
        ]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor({"rank": last["feed_rank"], "id": last["id"]})

        return FeedResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )

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
