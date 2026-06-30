"""Explore tab business logic (E9-S3).

Two modes — history (already-seen articles) and new (enriched-but-unseen,
gravity-ranked without the score-threshold / random-surface filters used by
the regular feed). Scrolling Explore does *not* emit impressions, so users can
scan the queue without consuming articles from their feed.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import APIError
from niouzou.models import Source
from niouzou.models.article import STATUS_ENRICHED
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.explore import (
    ExploreHistoryArticle,
    ExploreHistoryResponse,
    ExploreNewResponse,
    ExploreSearchArticle,
    ExploreSearchResponse,
)
from niouzou.schemas.feed import SourceRef
from niouzou.services.ranked_query import (
    active_columns,
    build_ranked_query,
    clamp_limit,
    row_to_article,
)
from niouzou.services.settings_service import SettingsService

# E17-S3 — below this many characters a search is too broad to be useful.
MIN_SEARCH_CHARS = 2


class ExploreService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def _validated_source_ids(
        self,
        user_id: uuid.UUID,
        source_ids: list[uuid.UUID] | None,
    ) -> list[uuid.UUID] | None:
        """Return ``source_ids`` after confirming each belongs to ``user_id``.

        Returns ``None`` when the caller didn't pass any filter (preserves the
        "no filter" semantic on the SQL side). An unknown or foreign UUID
        raises a 422 — the spec is explicit that we never silently filter the
        list down, to avoid leaking ownership information through diff sizes.
        """
        if not source_ids:
            return None
        rows = (
            await self.session.scalars(
                select(Source.id).where(
                    Source.id.in_(source_ids),
                    Source.user_id == user_id,
                    Source.deleted_at.is_(None),
                )
            )
        ).all()
        owned = set(rows)
        for sid in source_ids:
            if sid not in owned:
                raise APIError(
                    422,
                    "validation_error",
                    f"Unknown source id: {sid}",
                )
        return source_ids

    async def list_history(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int | None,
        *,
        min_score: float = 0.0,
        source_ids: list[uuid.UUID] | None = None,
    ) -> ExploreHistoryResponse:
        """Already-impressed articles, newest seen first. Keyset on (seen_at, id)
        so pages never overlap even when many impressions share a timestamp."""
        validated_source_ids = await self._validated_source_ids(
            user_id, source_ids
        )

        page_size = clamp_limit(limit)
        params: dict = {
            "user_id": user_id,
            "limit": page_size + 1,
            "premium_max_chars": get_settings().premium_content_max_chars,
        }

        # E16-S9 — min_score filters on the active method's score.
        scoring_mode = str(
            await SettingsService(self.session).get("scoring_mode")
        )
        active_score, active_cold = active_columns(scoring_mode)

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            # asyncpg refuses strings for timestamptz, even via CAST — must pass
            # a datetime instance.
            params["cursor_seen_at"] = datetime.fromisoformat(str(decoded["seen_at"]))
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (ai.seen_at, a.id) < (:cursor_seen_at, :cursor_id)"

        # E11-S1 — score filter on history. ``ars`` is LEFT JOINed so an
        # article without a score row would slip through; when
        # ``min_score > 0`` we exclude those explicitly (the user clearly
        # wants ranked rows). A scored row whose *active* score is NULL is
        # treated as cold (E16-S9) and passes.
        score_filter = ""
        if min_score > 0.0:
            params["min_score"] = min_score
            score_filter = (
                "AND (ars.article_id IS NOT NULL "
                f"AND ({active_score} >= :min_score "
                f"OR {active_cold} = TRUE OR {active_score} IS NULL))"
            )

        source_filter = ""
        if validated_source_ids:
            # asyncpg accepts ``list[uuid.UUID]`` as a uuid[] array — passing
            # the typed objects keeps the CAST honest.
            params["source_ids"] = [str(sid) for sid in validated_source_ids]
            source_filter = "AND a.source_id = ANY(CAST(:source_ids AS uuid[]))"

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
                ars.keyword_score AS keyword_score,
                COALESCE(ars.keyword_cold_start, FALSE) AS keyword_cold_start,
                ars.smart_score AS smart_score,
                COALESCE(ars.smart_cold_start, FALSE) AS smart_cold_start,
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
                {score_filter}
                {source_filter}
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
                keyword_score=r["keyword_score"],
                keyword_cold_start=bool(r["keyword_cold_start"]),
                smart_score=r["smart_score"],
                smart_cold_start=bool(r["smart_cold_start"]),
                active_method=scoring_mode,
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
        *,
        min_score: float = 0.0,
        source_ids: list[uuid.UUID] | None = None,
    ) -> ExploreNewResponse:
        """Enriched articles the user hasn't seen yet, ranked by gravity. No
        score threshold / random-surface gates — the user is explicitly
        scanning the queue."""
        validated_source_ids = await self._validated_source_ids(
            user_id, source_ids
        )

        settings = get_settings()
        page_size = clamp_limit(limit)

        params: dict = {
            "user_id": user_id,
            "gravity": settings.feed_gravity,
            "limit": page_size + 1,
            "premium_max_chars": settings.premium_content_max_chars,
        }

        # E16-S9 — active score drives both the ranking and the min_score cap.
        scoring_mode = str(
            await SettingsService(self.session).get("scoring_mode")
        )
        active_score, active_cold = active_columns(scoring_mode)

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            params["cursor_rank"] = float(decoded["rank"])
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"

        # E11-S1 — explicit min_score on Explore New (separate knob from the
        # global SCORE_THRESHOLD, which still isn't applied here). Cold-start
        # articles — and NULL active scores (E16-S9) — bypass the cap,
        # mirroring the Feed's policy in E10-S4.
        explore_filter_parts: list[str] = []
        if min_score > 0.0:
            params["min_score"] = min_score
            explore_filter_parts.append(
                f"AND ({active_score} >= :min_score "
                f"OR {active_cold} = TRUE OR {active_score} IS NULL)"
            )
        if validated_source_ids:
            params["source_ids"] = [str(sid) for sid in validated_source_ids]
            explore_filter_parts.append(
                "AND a.source_id = ANY(CAST(:source_ids AS uuid[]))"
            )
        extra_filters = "\n            ".join(explore_filter_parts)

        query = build_ranked_query(
            scoring_mode=scoring_mode,
            apply_threshold=False,
            apply_random_surface=False,
            keyset=keyset,
            extra_filters=extra_filters,
        )
        rows = (await self.session.execute(query, params)).mappings().all()
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [row_to_article(r, scoring_mode) for r in rows]

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor({"rank": last["feed_rank"], "id": last["id"]})

        return ExploreNewResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )

    async def search(
        self,
        user_id: uuid.UUID,
        query_text: str,
        cursor: str | None,
        limit: int | None,
    ) -> ExploreSearchResponse:
        """Full-text-ish search over ALL the user's enriched articles (E17-S3).

        Case-insensitive ``ILIKE`` on title + executive summary, spanning both
        seen and unseen articles. Newest first; keyset on
        ``(COALESCE(published_at, created_at), id)`` so pages never overlap.
        A query shorter than ``MIN_SEARCH_CHARS`` returns nothing — too broad
        to be useful and cheap to short-circuit.
        """
        term = query_text.strip()
        if len(term) < MIN_SEARCH_CHARS:
            return ExploreSearchResponse(articles=[], next_cursor=None, has_more=False)

        page_size = clamp_limit(limit)
        # Escape LIKE wildcards in user input so '%' / '_' are literal.
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params: dict = {
            "user_id": user_id,
            "limit": page_size + 1,
            "pattern": f"%{escaped}%",
            "premium_max_chars": get_settings().premium_content_max_chars,
        }

        scoring_mode = str(await SettingsService(self.session).get("scoring_mode"))

        keyset = ""
        if cursor:
            decoded = decode_cursor(cursor)
            params["cursor_sort_ts"] = datetime.fromisoformat(str(decoded["sort_ts"]))
            params["cursor_id"] = uuid.UUID(str(decoded["id"]))
            keyset = (
                "AND (COALESCE(a.published_at, a.created_at), a.id) "
                "< (:cursor_sort_ts, :cursor_id)"
            )

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
                COALESCE(a.published_at, a.created_at) AS sort_ts,
                s.id AS source_id,
                s.name AS source_name,
                ars.keyword_score AS keyword_score,
                COALESCE(ars.keyword_cold_start, FALSE) AS keyword_cold_start,
                ars.smart_score AS smart_score,
                COALESCE(ars.smart_cold_start, FALSE) AS smart_cold_start,
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
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN article_relevance_scores ars
                ON ars.article_id = a.id AND ars.user_id = :user_id
            LEFT JOIN article_feedbacks fb
                ON fb.article_id = a.id AND fb.user_id = :user_id
            LEFT JOIN article_impressions ai
                ON ai.article_id = a.id AND ai.user_id = :user_id
            WHERE s.user_id = :user_id
                AND s.deleted_at IS NULL
                AND a.status = '{STATUS_ENRICHED}'
                AND (
                    a.title ILIKE :pattern ESCAPE '\\'
                    OR a.summary_executive ILIKE :pattern ESCAPE '\\'
                )
                {keyset}
            ORDER BY COALESCE(a.published_at, a.created_at) DESC, a.id DESC
            LIMIT :limit
            """
        )

        rows = (await self.session.execute(query, params)).mappings().all()
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        articles = [
            ExploreSearchArticle(
                id=r["id"],
                title=r["title"],
                summary_short=r["summary_short"],
                summary_executive=r["summary_executive"],
                content=r["content"],
                og_image_url=r["og_image_url"],
                url=r["url"],
                source=SourceRef(id=r["source_id"], name=r["source_name"]),
                published_at=r["published_at"],
                keyword_score=r["keyword_score"],
                keyword_cold_start=bool(r["keyword_cold_start"]),
                smart_score=r["smart_score"],
                smart_cold_start=bool(r["smart_cold_start"]),
                active_method=scoring_mode,
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
                {"sort_ts": last["sort_ts"].isoformat(), "id": str(last["id"])}
            )

        return ExploreSearchResponse(
            articles=articles, next_cursor=next_cursor, has_more=has_more
        )
