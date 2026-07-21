"""Feed business logic: HN-ranked, keyset-paginated, impression-filtered.

Ranking (docs/API_SPEC.md):
    feed_rank = active_score / (age_in_hours + 2) ^ FEED_GRAVITY

where ``active_score`` is ``keyword_score`` or ``smart_score`` depending on
``scoring_mode`` (E16-S9) — flipping the mode re-ranks instantly, with no
rescore. Pagination is keyset on (feed_rank, id) so pages never overlap. With
the default SCORE_THRESHOLD of 0.0 every enriched article clears the
threshold, so the RANDOM_SURFACE_RATE branch is inert and ordering is fully
deterministic; it only kicks in to occasionally surface sub-threshold articles
when a positive threshold is configured (anti echo chamber).

The ranked SELECT projection is shared with ExploreService (E9-S3) via
``services.ranked_query`` — Explore reuses the same gravity ordering but
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
from niouzou.schemas.feed import FeedArticle, FeedResponse
from niouzou.services.ranked_query import (
    FROM_JOINS,
    build_ranked_query,
    clamp_limit,
    feed_rank_sql,
    interleave_by_source,
    ranked_columns,
    row_to_article,
)
from niouzou.services.settings_service import SettingsService
from niouzou.services.tags_service import TagsService

# E24-S4 — Loupe: restrict the feed to the sources carrying the selected tag.
# Injected via ``extra_filters`` so it composes with the score gate: the
# random-surface draw then happens WITHIN the tagged subset only.
TAG_FILTER_SQL = (
    "AND EXISTS (SELECT 1 FROM source_tags st "
    "WHERE st.source_id = a.source_id AND st.tag_id = :tag_id)"
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
        tag: uuid.UUID | None = None,
    ) -> FeedResponse:
        settings = get_settings()
        page_size = clamp_limit(limit)

        # E24-S4 — Loupe. Ownership gate first (422 on unknown/foreign/deleted
        # tag, so a stale client selection fails loudly and the PWA falls back
        # to "no Loupe"); the row also carries the per-tag threshold.
        tag_row = None
        if tag is not None:
            tag_row = await TagsService(self.session).require_owned(
                user_id, tag
            )

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

        # Effective threshold precedence (E24-S4): an explicit ``min_score``
        # always wins; then the Loupe tag's own threshold; then the global
        # SCORE_THRESHOLD. Cold start keeps bypassing everything, Loupe
        # included — the tag threshold only bites for a "warm" user.
        if cold_start:
            threshold = 0.0
        elif min_score is not None:
            threshold = min_score
        elif tag_row is not None and tag_row.threshold is not None:
            threshold = tag_row.threshold
        else:
            # Admin can tune the threshold live via PATCH /admin/config; read
            # through SettingsService so the change takes effect on the very
            # next request (env var stays the fallback default).
            override = await SettingsService(self.session).get("score_threshold")
            threshold = float(
                override if override is not None else settings.score_threshold
            )

        # E16-S9 — the active score column (filter + ranking) follows the
        # admin-tunable scoring_mode, read per request so a flip is instant.
        settings_svc = SettingsService(self.session)
        scoring_mode = str(await settings_svc.get("scoring_mode"))

        # Anti echo chamber: the share of sub-threshold articles randomly let
        # through is admin-tunable live via PATCH /admin/config (env var stays
        # the fallback default), so an operator can widen exploration without a
        # redeploy. Inert while cold_start forces threshold 0.0 (nothing is
        # sub-threshold to surface).
        random_override = await settings_svc.get("random_surface_rate")
        random_rate = float(
            random_override
            if random_override is not None
            else settings.random_surface_rate
        )

        params: dict = {
            "user_id": user_id,
            "gravity": settings.feed_gravity,
            "threshold": threshold,
            "random_rate": random_rate,
            "limit": page_size + 1,  # +1 row tells us whether more remain
            "premium_max_chars": settings.premium_content_max_chars,
        }

        extra_filters = ""
        if tag_row is not None:
            params["tag_id"] = tag_row.id
            extra_filters = TAG_FILTER_SQL

        # /feed?start=:id (E9-S3) — only honoured on the first page. When a
        # cursor is provided the user is paginating an existing deck and the
        # pivot logic has already been applied.
        pivot_article: FeedArticle | None = None
        if start is not None and cursor is None:
            pivot_article = await self._fetch_pivot(
                user_id, start, params, scoring_mode
            )
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
            pivot_rank = await self._compute_feed_rank(
                user_id, pivot_article.id, params, scoring_mode
            )
            params["cursor_rank"] = float(pivot_rank)
            params["cursor_id"] = pivot_article.id
            keyset = "AND (feed_rank, id) < (:cursor_rank, :cursor_id)"
            # The pivot takes one slot — fetch one fewer regular article so
            # the response still totals page_size.
            params["limit"] = page_size  # (+1 was already added; pivot is the +1)

        query = build_ranked_query(
            scoring_mode=scoring_mode,
            apply_threshold=True,
            apply_random_surface=True,
            keyset=keyset,
            extra_filters=extra_filters,
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

        # Keyset cursor is the page's rank-minimum row — capture it BEFORE the
        # anti-tunnel reorder shuffles the display order (E feed diversity), so
        # the next page still continues strictly below this rank.
        cursor_row = rows[-1] if rows else None
        rows = interleave_by_source(rows)

        articles: list[FeedArticle] = []
        if pivot_article is not None:
            articles.append(pivot_article)
        articles.extend(row_to_article(r, scoring_mode) for r in rows)

        next_cursor: str | None = None
        if has_more and cursor_row is not None:
            next_cursor = encode_cursor(
                {"rank": cursor_row["feed_rank"], "id": cursor_row["id"]}
            )

        return FeedResponse(
            articles=articles,
            next_cursor=next_cursor,
            has_more=has_more,
            cold_start=cold_start,
        )

    async def _fetch_pivot(
        self,
        user_id: uuid.UUID,
        article_id: uuid.UUID,
        base_params: dict,
        scoring_mode: str,
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
                {ranked_columns(scoring_mode)}
            {FROM_JOINS}
            WHERE s.user_id = :user_id
                AND a.status = '{STATUS_ENRICHED}'
                AND a.id = :article_id
            LIMIT 1
            """
        )
        row = (await self.session.execute(query, params)).mappings().first()
        return row_to_article(row, scoring_mode) if row else None

    async def _compute_feed_rank(
        self,
        user_id: uuid.UUID,
        article_id: uuid.UUID,
        base_params: dict,
        scoring_mode: str,
    ) -> float:
        """Recompute feed_rank for a known article. Cheaper than re-running the
        full ranked query just to learn the pivot's rank."""
        params = {**base_params, "article_id": article_id}
        query = text(
            f"""
            SELECT {feed_rank_sql(scoring_mode)} AS feed_rank
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
