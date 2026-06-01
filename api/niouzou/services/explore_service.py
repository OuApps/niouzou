"""Explore tab business logic (E9-S3).

Two modes — history (already-seen articles) and new (enriched-but-unseen,
gravity-ranked without the score-threshold / random-surface filters used by
the regular feed). Scrolling Explore does *not* emit impressions, so users can
scan the queue without consuming articles from their feed.
"""

import uuid
from datetime import datetime

from sqlalchemy import text

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.explore import (
    ExploreHistoryArticle,
    ExploreHistoryResponse,
    ExploreNewResponse,
)
from niouzou.schemas.feed import SourceRef
from niouzou.services.ranked_query import (
    build_ranked_query,
    clamp_limit,
    row_to_article,
)


class ExploreService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def list_history(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int | None,
    ) -> ExploreHistoryResponse:
        """Already-impressed articles, newest seen first. Keyset on (seen_at, id)
        so pages never overlap even when many impressions share a timestamp."""
        page_size = clamp_limit(limit)
        params: dict = {
            "user_id": user_id,
            "limit": page_size + 1,
            "premium_max_chars": get_settings().premium_content_max_chars,
        }

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            # asyncpg refuses strings for timestamptz, even via CAST — must pass
            # a datetime instance.
            params["cursor_seen_at"] = datetime.fromisoformat(str(decoded["seen_at"]))
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (ai.seen_at, a.id) < (:cursor_seen_at, :cursor_id)"

        query = text(
            f"""
            SELECT
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
                COALESCE(ars.relevance_score, 0.0) AS relevance_score,
                ars.scorer AS scorer,
                a.enrichment_model AS enrichment_model,
                (a.content IS NOT NULL
                 AND char_length(a.content) < :premium_max_chars
                ) AS is_premium,
                COALESCE(fb.reaction, 'none') AS reaction,
                COALESCE(fb.is_saved, false) AS is_saved,
                COALESCE(fb.read_full_article, false) AS read_full_article,
                ai.seen_at AS seen_at,
                COALESCE(
                    (SELECT array_agg(ak.term ORDER BY ak.salience DESC, ak.term ASC)
                     FROM article_keywords ak WHERE ak.article_id = a.id),
                    ARRAY[]::text[]
                ) AS keywords
            FROM article_impressions ai
            JOIN articles a ON a.id = ai.article_id
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN article_relevance_scores ars
                ON ars.article_id = a.id AND ars.user_id = :user_id
            LEFT JOIN article_feedbacks fb
                ON fb.article_id = a.id AND fb.user_id = :user_id
            WHERE ai.user_id = :user_id
                AND s.user_id = :user_id
                {keyset}
            ORDER BY ai.seen_at DESC, a.id DESC
            LIMIT :limit
            """
        )

        rows = (await self.session.execute(query, params)).mappings().all()
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [
            ExploreHistoryArticle(
                id=r["id"],
                title=r["title"],
                summary_short=r["summary_short"],
                summary_executive=r["summary_executive"],
                content=r["content"],
                og_image_url=r["og_image_url"],
                url=r["url"],
                source=SourceRef(id=r["source_id"], name=r["source_name"]),
                published_at=r["published_at"],
                relevance_score=r["relevance_score"],
                scorer=r["scorer"],
                enrichment_model=r["enrichment_model"],
                keywords=list(r["keywords"] or []),
                is_premium=bool(r["is_premium"]),
                reaction=r["reaction"],
                is_saved=bool(r["is_saved"]),
                read_full_article=bool(r["read_full_article"]),
                seen_at=r["seen_at"],
            )
            for r in rows
        ]

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(
                {"seen_at": last["seen_at"].isoformat(), "id": str(last["id"])}
            )

        return ExploreHistoryResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )

    async def list_new(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int | None,
    ) -> ExploreNewResponse:
        """Enriched articles the user hasn't seen yet, ranked by gravity. No
        score threshold / random-surface gates — the user is explicitly
        scanning the queue."""
        settings = get_settings()
        page_size = clamp_limit(limit)

        params: dict = {
            "user_id": user_id,
            "gravity": settings.feed_gravity,
            "limit": page_size + 1,
            "premium_max_chars": settings.premium_content_max_chars,
        }

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            params["cursor_rank"] = float(decoded["rank"])
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"

        query = build_ranked_query(
            apply_threshold=False,
            apply_random_surface=False,
            keyset=keyset,
        )
        rows = (await self.session.execute(query, params)).mappings().all()
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [row_to_article(r) for r in rows]

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor({"rank": last["feed_rank"], "id": last["id"]})

        return ExploreNewResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )
