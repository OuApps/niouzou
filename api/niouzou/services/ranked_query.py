"""SQL helpers shared by FeedService and ExploreService.

Both services rank articles by ``feed_rank`` (HN-style gravity formula) and
project the same row shape — these constants and helpers were extracted out
of ``feed_service`` so the dependency between the two services is explicit
and the names don't have to live behind a leading underscore.
"""

from sqlalchemy import text

from niouzou.models.article import STATUS_ENRICHED
from niouzou.schemas.feed import FeedArticle, SourceRef

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

# feed_rank, computed once and reused in SELECT, ORDER BY and the keyset filter.
# Cold-start articles (E10-S4) use a synthetic 0.5 baseline so they sort
# between bona-fide good and bad articles instead of clumping at whatever
# neutral value the scorer happened to emit (TF-IDF and AI scorers both
# return ~0.5 when nothing in the user's vocab matches, but the boundary
# isn't stable enough to rank on).
FEED_RANK = (
    "(CASE WHEN ars.is_cold_start THEN 0.5 ELSE ars.relevance_score END)"
    " / power("
    "GREATEST(EXTRACT(EPOCH FROM (now() - COALESCE(a.published_at, a.created_at)))"
    "/ 3600.0, 0) + 2, :gravity)"
)

# Projection shared by /feed and /explore/new. Aliased so the outer SELECT
# can keyset on (feed_rank, id) without recomputing the rank.
RANKED_COLUMNS = f"""
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
    ars.is_cold_start AS is_cold_start,
    a.enrichment_model AS enrichment_model,
    (a.content IS NOT NULL
     AND char_length(a.content) < :premium_max_chars
    ) AS is_premium,
    COALESCE(fb.reaction, 'none') AS reaction,
    COALESCE(fb.is_saved, false) AS is_saved,
    COALESCE(fb.read_full_article, false) AS read_full_article,
    {FEED_RANK} AS feed_rank,
    COALESCE(
        (SELECT array_agg(ak.term ORDER BY ak.salience DESC, ak.term ASC)
         FROM article_keywords ak WHERE ak.article_id = a.id),
        ARRAY[]::text[]
    ) AS keywords
"""

FROM_JOINS = """
FROM articles a
JOIN sources s ON s.id = a.source_id
JOIN article_relevance_scores ars
    ON ars.article_id = a.id AND ars.user_id = :user_id
LEFT JOIN article_impressions ai
    ON ai.article_id = a.id AND ai.user_id = :user_id
LEFT JOIN article_feedbacks fb
    ON fb.article_id = a.id AND fb.user_id = :user_id
"""


def build_ranked_query(
    *,
    apply_threshold: bool,
    apply_random_surface: bool,
    keyset: str = "",
    impression_exclusion: str = "AND ai.article_id IS NULL",
    extra_filters: str = "",
) -> text:
    """Assemble the ranked SELECT used by /feed and /explore/new.

    Args:
        apply_threshold: keep ``ars.relevance_score >= :threshold`` filter.
        apply_random_surface: enable the random-surface escape hatch.
        keyset: extra ``AND (feed_rank, id) < (:cursor_rank, :cursor_id)``
            predicate, or empty string for the first page.
        impression_exclusion: overridable so /feed?start=:id can let one
            already-impressed article through.
        extra_filters: caller-supplied ``AND ...`` predicates injected into
            the inner WHERE (E11-S1: per-request ``min_score`` and
            ``source_ids`` on /explore/new).
    """
    # Cold-start articles (E10-S4) bypass the score threshold unconditionally
    # — they're the only chance for the user to ever feedback unfamiliar
    # keywords. The random-surface escape hatch keeps its independent role
    # (broad exploration over already-warm articles).
    score_filter = ""
    if apply_threshold and apply_random_surface:
        score_filter = (
            "AND (ars.relevance_score >= :threshold "
            "OR ars.is_cold_start = TRUE "
            "OR random() < :random_rate)"
        )
    elif apply_threshold:
        score_filter = (
            "AND (ars.relevance_score >= :threshold OR ars.is_cold_start = TRUE)"
        )
    elif apply_random_surface:
        score_filter = "AND random() < :random_rate"
    # else: no score gate at all (Explore New).

    return text(
        f"""
        WITH ranked AS (
            SELECT
                {RANKED_COLUMNS}
            {FROM_JOINS}
            WHERE s.user_id = :user_id
                AND a.status = '{STATUS_ENRICHED}'
                {impression_exclusion}
                {score_filter}
                {extra_filters}
        )
        SELECT * FROM ranked
        WHERE true {keyset}
        ORDER BY feed_rank DESC, id DESC
        LIMIT :limit
        """
    )


def row_to_article(row) -> FeedArticle:
    """Map a ranked-query result mapping into the public FeedArticle schema."""
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
        is_cold_start=bool(row["is_cold_start"]),
        enrichment_model=row["enrichment_model"],
        keywords=list(row["keywords"] or []),
        is_premium=bool(row["is_premium"]),
        reaction=row["reaction"],
        is_saved=bool(row["is_saved"]),
        read_full_article=bool(row["read_full_article"]),
    )


def clamp_limit(limit: int | None) -> int:
    """Clamp a user-supplied page size to the configured range."""
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))
